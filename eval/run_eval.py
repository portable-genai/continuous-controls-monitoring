#!/usr/bin/env python3
"""Evaluation gate for Continuous Controls Monitoring (Aud2).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the pure
  ``ControlTestEngine`` against a golden set with SDK-free code and scores four metrics.
* **gate** - the promotion verdict from the shared Hrz4 authority (requires the ``gcp``
  profile), via ``agent_eval_kit.PromotionGateClient``.

The metrics score against the dataset's OWN ``expected_*`` labels, an independent oracle, NEVER
against the pipeline's own verdict: a metric that graded the engine by the engine would be
green by construction. Each metric is provable red (see ``tests/unit/test_eval_metrics.py``).

``pii_safety`` scores what the REAL service handed its sinks, which is why smoke mode builds a
local container and drives ``MonitoringService.evaluate_pack`` rather than calling the engine on
its own. The metric it replaced redacted a string it had assembled itself and then asked whether
that string was clean, so it was green by construction and could not see a leak anywhere.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from agent_eval_kit import EvalMetricResult, EvalReport, PromotionGateClient, eval_main
from pii_kit import pack_leak

from continuous_controls_monitoring.config import Container, Settings, build_container
from continuous_controls_monitoring.domain.kernel import Severity
from continuous_controls_monitoring.domain.models import (
    ControlTestPack,
    ControlTestResult,
    Dimension,
    EffectivenessRating,
    EvidenceRecord,
    InventoryControl,
    PassCriteria,
    TestKind,
)
from continuous_controls_monitoring.domain.monitoring_service import MonitoringService
from continuous_controls_monitoring.domain.narration import validate_narration
from continuous_controls_monitoring.domain.packs import all_valid, default_packs
from continuous_controls_monitoring.domain.pii import PII_PATTERNS
from continuous_controls_monitoring.domain.testing import ControlTestEngine

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

THRESHOLDS: dict[str, float] = {
    "effectiveness_accuracy": 0.90,
    "groundedness": 0.99,
    "pii_safety": 0.99,
    "pack_schema_validity": 1.0,
}
#: The registered Hrz4 metric bundle for this vertical (Hrz4 owns the metrics + thresholds).
_BUNDLE = "continuous-controls-monitoring"

_AS_OF = date(2026, 8, 1)
_ENGINE = ControlTestEngine()

#: The principal the eval attributes its runs to. An address, deliberately: it is the shape a
#: verified principal has, and the leak scan has to stay green with it in the store.
_EVAL_ACTOR = "eval-harness@bank.example"


def _load(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 1.0


def _pack_from_case(case: dict[str, object]) -> ControlTestPack:
    criteria_raw = dict(case.get("criteria") or {})  # type: ignore[arg-type]
    threshold = criteria_raw.get("threshold_value")
    criteria = PassCriteria(
        gate_severity=Severity(str(criteria_raw.get("gate_severity", "high"))),
        max_exceptions=int(criteria_raw.get("max_exceptions", 0)),
        max_recert_age_days=int(criteria_raw.get("max_recert_age_days", 90)),
        threshold_value=float(threshold) if threshold is not None else None,
        threshold_direction=str(criteria_raw.get("threshold_direction", "max")),
        expected_attributes=tuple(
            (str(k), str(v)) for k, v in (criteria_raw.get("expected_attributes") or {}).items()
        ),
    )
    return ControlTestPack(
        pack_id=str(case["id"]),
        control_id=str(case.get("control_id", "C1")),
        title="",
        test_kind=TestKind(str(case["test_kind"])),
        evidence_source="src",
        cadence="daily",
        dimensions=(Dimension.DESIGN, Dimension.OPERATING),
        severity=Severity(str(case.get("severity", "high"))),
        criteria=criteria,
    )


def _evidence_from_case(case: dict[str, object]) -> tuple[EvidenceRecord, ...]:
    kind = TestKind(str(case["test_kind"]))
    control_id = str(case.get("control_id", "C1"))
    out: list[EvidenceRecord] = []
    for i, record in enumerate(case.get("records") or []):  # type: ignore[union-attr]
        attrs = {str(k): str(v) for k, v in dict(record).items() if k != "id"}
        out.append(
            EvidenceRecord(
                control_id=control_id,
                kind=kind,
                source="src",
                identifier=str(dict(record).get("id", f"rec-{i}")),
                attributes=attrs,
            )
        )
    return tuple(out)


def _control_for(case: dict[str, object]) -> InventoryControl | None:
    """The Rgc7 control the case says exists, or ``None`` for the not-in-inventory case."""
    if not case.get("in_inventory", True):
        return None
    return InventoryControl(
        control_id=str(case.get("control_id", "C1")), title="", owner="owner@bank.example"
    )


def _result_for(case: dict[str, object]) -> ControlTestResult:
    """Grade one case with the pure engine alone (no service, no sinks)."""
    return _ENGINE.evaluate(
        _pack_from_case(case), _control_for(case), _evidence_from_case(case), as_of=_AS_OF
    )


class _CaseInventory:
    """A ControlInventoryPort that answers with the case's own ``in_inventory`` label."""

    def __init__(self, control: InventoryControl | None) -> None:
        self._control = control

    def get_control(self, control_id: str, *, tenant: str) -> InventoryControl | None:
        return self._control

    def list_controls(self, tenant: str) -> tuple[InventoryControl, ...]:
        return () if self._control is None else (self._control,)


class _CaseScanner:
    """An EvidenceScannerPort that returns the case's own records."""

    def __init__(self, records: tuple[EvidenceRecord, ...]) -> None:
        self._records = records

    def scan(self, pack: ControlTestPack) -> tuple[EvidenceRecord, ...]:
        return self._records


class _NoControlEvidence:
    """The Rsk1 evidence port, empty: a golden case carries all of its own evidence."""

    def fetch(self, control_id: str) -> tuple[EvidenceRecord, ...]:
        return ()


class _PromptTap:
    """The real local narrator with a tap on what the model boundary was handed.

    The prompt is a sink like the audit record is. Under the managed profile it leaves the
    process, and it is assembled from finding prose, which the engine cuts from the evidence
    record. Scoring only what came BACK from the model would miss it entirely: a narrator is free
    to drop a fact it was given.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._inner.generate(prompt)


def _drive_case(case: dict[str, object], container: Container, narration: Any) -> ControlTestResult:
    """Run one golden case through the REAL service, so its real sinks are really written.

    Only the two ports that supply upstream data are swapped for the case's own rows. The
    service, the engine, the redaction seam, the WORM audit adapter, the narrator, the write-back
    and the R8 routing are the shipped local ones, which is the whole point: a metric that scores
    a re-implementation scores the re-implementation. A case must name a control the offline
    write-back knows, or the write-back refuses it, which is the correct refusal and not a bug.
    """
    service = MonitoringService(
        audit=container.audit,
        inventory=_CaseInventory(_control_for(case)),
        scanner=_CaseScanner(_evidence_from_case(case)),
        control_evidence=_NoControlEvidence(),
        writeback=container.writeback,
        timeseries=container.timeseries,
        generation=narration,
        review_router=container.review_router,
        tracer=container.tracer,
        policy=container.settings.policy,
    )
    monitored = service.evaluate_pack(
        _pack_from_case(case), as_of=_AS_OF, tenant=container.settings.tenant, actor=_EVAL_ACTOR
    )
    return monitored.result


def effectiveness_score(case: dict[str, object], result: ControlTestResult) -> float:
    """1.0 iff the engine's verdict and operating rating match the case's OWN labels."""
    passed_ok = result.passed is bool(case["expected_passed"])
    operating_ok = result.operating.rating is EffectivenessRating(str(case["expected_operating"]))
    return 1.0 if passed_ok and operating_ok else 0.0


def groundedness_score(case: dict[str, object], result: ControlTestResult) -> float | None:
    """1.0 iff the validator's accept/reject of the case's narration matches its label.

    Cases carry a candidate ``narration`` (raw JSON) and ``narration_grounded`` label. A
    grounded narration must validate; an ungrounded one (a fabricated figure) must be discarded.
    Returns ``None`` for cases with no narration, so they do not dilute the metric.
    """
    narration = case.get("narration")
    if narration is None:
        return None
    accepted = validate_narration(str(narration), result) is not None
    return 1.0 if accepted is bool(case["narration_grounded"]) else 0.0


def audit_texts(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Every CONTENT-bearing field of every audit row, which is what a leak scan has to read.

    Scanning no stored field at all is the defect this avoids: a metric that builds its own
    string out of the result, redacts THAT, and scans the thing it just redacted asks the
    redactor whether it redacted and believes the answer, never opening the store. This reads the
    rows the service actually wrote, summary and citations both, because citations travel inside
    the record and carry upstream text in ``snippet`` and, routinely, in ``source_id``.

    ``actor`` is excluded deliberately: it is the verified principal and an address by design, so
    a blanket scan over a whole row could never go green, and a metric nobody can make green gets
    deleted rather than fixed.
    """
    texts: list[str] = []
    for row in rows:
        texts.append(str(row.get("redacted_summary", "")))
        texts.append(json.dumps(row.get("citations", []), sort_keys=True))
    return texts


def review_texts(entries: Iterable[Any]) -> list[str]:
    """Every content-bearing field of every payload queued for the shared Hrz7 console.

    The console is the other place a control test publishes to, and it is a SHARED sink. ``maker``
    is excluded for exactly the reason ``actor`` is in :func:`audit_texts`.
    """
    return [
        json.dumps(
            {k: v for k, v in entry.review.to_payload().items() if k != "maker"},
            sort_keys=True,
            default=str,
        )
        for entry in entries
    ]


def pii_safety(records: Sequence[str], planted: Sequence[str]) -> float:
    """No identifier may survive into anything the service published, by pack row OR by literal.

    Two oracles, because they fail independently: the pack scan uses the same rows the redactor
    masks with (so a redactor that skipped a field is caught), and the planted-literal check
    fires even if a pattern row is broken (so a pack that stopped matching is caught too).
    """
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in records)
    literal_leaked = any(token in text for token in planted for text in records)
    return 0.0 if (pack_leaked or literal_leaked) else 1.0


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)

    # One container for the whole run, so the audit chain, the outbox and the write-back
    # accumulate across cases exactly as they do in a real sweep.
    container = build_container(Settings(profile="local", audit_path=":memory:"))
    narrator = _PromptTap(container.generation)

    effectiveness: list[float] = []
    grounded: list[float] = []
    for case in cases:
        result = _drive_case(case, container, narrator)
        effectiveness.append(effectiveness_score(case, result))
        g = groundedness_score(case, result)
        if g is not None:
            grounded.append(g)

    # pii_safety: no raw identifier may survive into anything the service published. The scan
    # covers the three sinks a control test writes to, because covering only one is how the
    # previous version stayed green: the WORM record, the model prompt (assembled from finding
    # prose, which the engine cuts from the evidence record) and the Hrz7 review payload.
    records = [
        *audit_texts(container.audit.log.read_all()),  # type: ignore[attr-defined]
        *narrator.prompts,
        *review_texts(container.review_router.outbox.pending()),  # type: ignore[attr-defined]
    ]
    planted = [str(case["planted"]) for case in cases if case.get("planted")]

    pack_valid = 1.0 if all_valid(default_packs()) else 0.0

    results = (
        EvalMetricResult.scored(
            "effectiveness_accuracy",
            _mean(effectiveness),
            THRESHOLDS["effectiveness_accuracy"],
        ),
        EvalMetricResult.scored("groundedness", _mean(grounded), THRESHOLDS["groundedness"]),
        EvalMetricResult.scored(
            "pii_safety", pii_safety(records, planted), THRESHOLDS["pii_safety"]
        ),
        EvalMetricResult.scored(
            "pack_schema_validity", pack_valid, THRESHOLDS["pack_schema_validity"]
        ),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"CCM_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("CCM_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-2.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / Hrz4 evaluation gate for Aud2.",
        )
    )
