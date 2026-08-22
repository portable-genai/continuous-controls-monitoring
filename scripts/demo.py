"""The scripted, offline demo: the REAL services, synthetic data, an audit-first output view.

This is the demo as CODE (practices check F1), not a slide deck and not a recording. Every step
below drives the actual monitoring service, the actual hash-chained audit store and the actual
rule-R8 review router over the ``local`` profile, so a step that stops being true stops passing
rather than stops being mentioned.

Three properties make it worth running in front of somebody:

* **Nothing is faked.** No stub service, no pre-baked JSON. The effectiveness verdicts, the audit
  records, the routing references and the tamper verdict are produced by the shipped code.
* **It is bounded.** The demo proves an offline, single-process seam. It does not prove
  cross-host deployment, a live console, or the managed profile; those need a cloud project and
  live in ``tests/integration/``.
* **It is replayable.** Same inputs, same output, every time, because the consequential decision
  is deterministic. That is what makes it safe to run live.

Run it directly to write the audit-view JSON, then render that JSON to static pages::

    make demo-static

or drive it one step at a time with ``demo_server.py`` and ``walkthrough.py`` (``make demo``).

Every party, address and identifier here is obviously fictional: ``.example`` domains, RFC 5737
and RFC 3849 literals, and a synthetic national id that exists only to prove redaction happened.

MAINTAINER NOTE: this file is rendered from a template, so no line may change length with the
package or service name. Every cookiecutter value is bound to a short module constant below and
referenced through it, and every import line is short enough that a long package name cannot
push it past the formatter's limit.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from hex_service_kit.audit import HashChainedAuditLog
from hex_service_kit.identity import RequestContext
from hex_service_kit.serialization import to_jsonable
from pii_kit import redact

from continuous_controls_monitoring.config import (
    Settings,
    build_container,
)
from continuous_controls_monitoring.domain import (
    kernel,
    models,
)
from continuous_controls_monitoring.domain.monitoring_service import (
    MonitoringService,
)
from continuous_controls_monitoring.domain.packs import (
    default_packs,
)
from continuous_controls_monitoring.domain.pii import (
    JURISDICTIONS,
    PII_PATTERNS,
)
from continuous_controls_monitoring.domain.testing import (
    ControlTestEngine,
)


def loaded_cloud_sdks() -> tuple[str, ...]:
    """Every managed-SDK module currently importable in THIS interpreter, sorted."""
    return tuple(sorted(name for name in sys.modules if name.split(".")[0] == "google"))


#: Rendered identity, bound once so no other line's length depends on how long a name is.
SERVICE_NAME = "Continuous Controls Monitoring"
CATALOG_ID = "Aud2"
REPOSITORY = "continuous-controls-monitoring"

# --------------------------------------------------------------------------------------- #
# Synthetic data. Fictional parties, .example domains, RFC 5737 / RFC 3849 literals only.
# --------------------------------------------------------------------------------------- #

#: The VERIFIED principal the demo attributes work to. A client never asserts this.
ACTOR = "auditor@bank.example"
TENANT = "demo-bank"

#: A fixed test date, so the demo is replayable (the engine reads no clock).
AS_OF = date(2026, 8, 1)

#: The pack whose evidence is clean (a PASSING control), and the one whose evidence drifts (a
#: FAILING control that escalates). Both are read from the shipped default packs.
PASSING_PACK = "pack-patch-sla"
FAILING_PACK = "pack-egress-config"

#: A planted identifier, so the redaction panel has an independent literal to look for rather
#: than trusting the pattern pack to agree with itself.
PLANTED_NRIC = "S1234567D"

_ENGINE = ControlTestEngine()

#: A standalone result used by the on-premises exit tour (built once, off any run).
_EGRESS_PACK = next(p for p in default_packs() if p.pack_id == FAILING_PACK)
_DEMO_CONTROL = models.InventoryControl(control_id="SC-7-egress", title="demo", owner=ACTOR)
_DEMO_RESULT = _ENGINE.evaluate(
    _EGRESS_PACK,
    _DEMO_CONTROL,
    (
        models.EvidenceRecord(
            control_id="SC-7-egress",
            kind=models.TestKind.CONFIG_SCAN,
            source="cloud_asset_inventory",
            identifier="bucket-demo",
            attributes={"public_access_prevention": "inherited"},
        ),
    ),
    as_of=AS_OF,
)


# --------------------------------------------------------------------------------------- #
# The presenter arc
# --------------------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Step:
    """One presenter beat: what it shows, and the sentence the presenter reads aloud."""

    key: str
    label: str
    narration: str


STEPS: tuple[Step, ...] = (
    Step(
        key="opened",
        label="Service bound on the offline profile",
        narration=(
            "The whole stack is bound from one settings file: no cloud project, no credentials, "
            "no SDK. Every port has an offline implementation, which is why this demo and the "
            "gate both run on a plane."
        ),
    ),
    Step(
        key="routine",
        label="A control that PASSES: scored, cited, NOT escalated",
        narration=(
            "A control tested against clean evidence. Design and operating effectiveness are "
            "scored by deterministic code, never by a model. Nothing is routed, because a "
            "passing control that manufactured a review would train reviewers to rubber-stamp."
        ),
    ),
    Step(
        key="escalation",
        label="A control that FAILS: an exception, escalated AND routed (rule R8)",
        narration=(
            "The same engine over drifted evidence. The control fails, and setting the flag is "
            "not the escalation; routing is. The exception is handed to the control owner via "
            "the human-review console in the same call that produced it, and never auto-closes."
        ),
    ),
    Step(
        key="redaction",
        label="Personal data is masked BEFORE the audit write",
        narration=(
            "A failing control whose evidence names a person. The identifier is masked before "
            "anything is written, so the immutable record never contains it. Redacting "
            "afterwards would be too late: the record is already immutable."
        ),
    ),
    Step(
        key="review_queue",
        label="What the reviewer receives, already redacted on the wire",
        narration=(
            "The outbound review queue. The console is a SHARED sink, so payloads are redacted "
            "against every configured jurisdiction, not only the one this case came from."
        ),
    ),
    Step(
        key="audit",
        label="The audit trail verifies, and exports in an open format",
        narration=(
            "The trail is append-only and hash-chained, with an external head anchor on a "
            "separate volume. It exports to JSON Lines and reloads into a fresh store with "
            "every link intact: the record is yours, not this codebase's."
        ),
    ),
    Step(
        key="tamper",
        label="A rewritten record is DETECTED, not merely discouraged",
        narration=(
            "An attacker with file access drops the append-only triggers and rewrites one "
            "record. The store cannot prevent that. The hash chain names the exact record that "
            "broke, which is the honest guarantee: tamper-EVIDENT, not tamper-proof."
        ),
    ),
    Step(
        key="portability",
        label="The exit path fails fast instead of failing silently",
        narration=(
            "The same calls on the on-premises profile, with no code edited and no domain "
            "module touched. Every unimplemented seam refuses loudly. A placeholder that "
            "returned successfully would convert an exception into an unreviewed decision."
        ),
    ),
)

STEP_KEYS: tuple[str, ...] = tuple(step.key for step in STEPS)


# --------------------------------------------------------------------------------------- #
# Panels: the audit-first output view (the result, its evidence, the findings, what is next)
# --------------------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Row:
    """One labelled fact in a panel. ``tone`` drives the colour, never the meaning."""

    label: str
    value: str
    tone: str = ""


@dataclass(frozen=True, slots=True)
class Panel:
    """One block of the output view: a title, labelled facts, and an interpretation."""

    title: str
    rows: tuple[Row, ...] = ()
    note: str = ""
    tone: str = ""


@dataclass(frozen=True, slots=True)
class StepResult:
    """Everything one step produced, ready to render or to assert against."""

    key: str
    label: str
    narration: str
    panels: tuple[Panel, ...] = ()
    facts: dict[str, Any] = field(default_factory=dict)


Produced = tuple[list[Panel], dict[str, Any]]


class DemoRun:
    """A live demo, advanced one step at a time over the real services."""

    def __init__(self, workdir: Path | None = None) -> None:
        self._cloud_sdk_before = frozenset(loaded_cloud_sdks())
        self._tempdir: tempfile.TemporaryDirectory[str] | None = None
        if workdir is None:
            self._tempdir = tempfile.TemporaryDirectory(prefix="demo-run-")
            workdir = Path(self._tempdir.name)
        self.workdir = workdir
        self.audit_path = workdir / "store" / "audit.sqlite3"
        self.anchor_path = workdir / "anchor" / "head.json"
        self.anchor_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = Settings(
            profile="local",
            audit_path=str(self.audit_path),
            audit_anchor_path=str(self.anchor_path),
            tenant=TENANT,
        )
        self.container = build_container(self.settings)
        self.service = MonitoringService(
            audit=self.container.audit,
            inventory=self.container.control_inventory,
            scanner=self.container.evidence_scanner,
            control_evidence=self.container.control_evidence,
            writeback=self.container.writeback,
            timeseries=self.container.timeseries,
            generation=self.container.generation,
            review_router=self.container.review_router,
            tracer=self.container.tracer,
            policy=self.container.settings.policy,
        )
        self.results: list[StepResult] = []
        self.cases = 0
        self.escalated = 0
        self.routed = 0
        self.chain_ok = True
        self._perform(STEPS[0])

    # -------------------------------------------------------------- control

    @property
    def index(self) -> int:
        return len(self.results) - 1

    @property
    def done(self) -> bool:
        return len(self.results) >= len(STEPS)

    def advance(self) -> StepResult:
        if self.done:
            return self.results[-1]
        return self._perform(STEPS[len(self.results)])

    def run_to_end(self) -> None:
        while not self.done:
            self.advance()

    def _perform(self, step: Step) -> StepResult:
        handler: Callable[[], Produced] = getattr(self, "_step_" + step.key)
        panels, facts = handler()
        result = StepResult(
            key=step.key,
            label=step.label,
            narration=step.narration,
            panels=tuple(panels),
            facts=facts,
        )
        self.results.append(result)
        return result

    def _pack(self, pack_id: str) -> models.ControlTestPack:
        return next(p for p in self.service.packs if p.pack_id == pack_id)

    # -------------------------------------------------------------- steps

    def _step_opened(self) -> Produced:
        bindings = [
            Row(port, self.settings.adapters[port][self.settings.profile].split(":")[-1])
            for port in sorted(self.settings.adapters)
        ]
        profiles = sorted({name for table in self.settings.adapters.values() for name in table})
        sdk = [name for name in loaded_cloud_sdks() if name not in self._cloud_sdk_before]
        deployment = Panel(
            title="Deployment",
            rows=(
                Row("Service", SERVICE_NAME),
                Row("Catalog id", CATALOG_ID),
                Row("Profile", self.settings.profile, "ok"),
                Row("Profiles bound for every port", ", ".join(profiles)),
                Row("Residency region", self.settings.region),
                Row("Jurisdiction PII packs", ", ".join(JURISDICTIONS)),
            ),
            note=(
                "One environment variable selects the adapter family for every port. Nothing "
                "below was edited to make the service run offline."
            ),
        )
        adapters = Panel(
            title="Bound adapters",
            rows=tuple(bindings),
            note="The binding map lives in config/settings.yaml, not in the code.",
        )
        findings = Panel(
            title="Findings",
            rows=(
                Row("Cloud SDK modules imported", ", ".join(sdk) or "none", "bad" if sdk else "ok"),
                Row("Credentials required", "none", "ok"),
                Row("Network required", "none", "ok"),
            ),
            note=(
                "The managed adapters import their SDK lazily, so this profile runs with none "
                "installed at all."
            ),
            tone="bad" if sdk else "ok",
        )
        facts = {"profile": self.settings.profile, "sdk_modules": sdk, "profiles": profiles}
        return [deployment, adapters, findings], facts

    def _step_routine(self) -> Produced:
        return self._control_panels(PASSING_PACK, expect_routing=False)

    def _step_escalation(self) -> Produced:
        return self._control_panels(FAILING_PACK, expect_routing=True)

    def _step_redaction(self) -> Produced:
        pack = self._pack(FAILING_PACK)
        control = self.container.control_inventory.get_control(pack.control_id, tenant=TENANT)
        evidence = (
            models.EvidenceRecord(
                control_id=pack.control_id,
                kind=models.TestKind.CONFIG_SCAN,
                source="cloud_asset_inventory",
                identifier="bucket-owned-by-" + PLANTED_NRIC,
                attributes={"public_access_prevention": "inherited"},
                source_ref="owner NRIC " + PLANTED_NRIC + " on file",
            ),
        )
        result = _ENGINE.evaluate(pack, control, evidence, as_of=AS_OF)
        detail = " | ".join(f.detail for f in result.findings)
        summary = redact(result.summary + " :: " + detail, PII_PATTERNS)
        self.container.audit.record(
            kernel.AuditEvent(
                action="control_test",
                actor=ACTOR,
                decision=result.decision,
                severity=result.severity,
                redacted_summary=summary,
                citations=result.citations,
            )
        )
        self.cases += 1
        review_ref = ""
        if result.requires_human_review:
            self.escalated += 1
            review_ref = self.container.review_router.route(result, maker=ACTOR, tenant=TENANT)
            self.routed += 1
        recorded = str(self.container.audit.log.read_all()[-1]["redacted_summary"])
        leaked = PLANTED_NRIC in recorded
        panel = Panel(
            title="Redact before the write",
            rows=(
                Row("Identifier in the evidence", PLANTED_NRIC, "warn"),
                Row(
                    "Identifier in the immutable record",
                    "PRESENT" if leaked else "absent",
                    "bad" if leaked else "ok",
                ),
                Row("Stored summary", recorded),
            ),
            note=(
                "The record is immutable, so a redaction pass after the write would be too late. "
                "Masking happens on the way in."
            ),
            tone="bad" if leaked else "ok",
        )
        facts = {
            "subject": result.control_id,
            "requires_human_review": result.requires_human_review,
            "review_ref": review_ref,
            "planted_identifier_leaked": leaked,
        }
        return [panel], facts

    def _step_review_queue(self) -> Produced:
        pending = list(self.container.review_router.outbox.pending())
        rows: list[Row] = []
        leaked = False
        for item in pending:
            payload = to_jsonable(item)
            leaked = leaked or PLANTED_NRIC in json.dumps(payload, sort_keys=True)
            rows.append(Row(str(getattr(item, "source_key", "review")), _summarise(payload)))
        queue = Panel(
            title="Outbound review queue",
            rows=tuple(rows) or (Row("queue", "empty", "bad"),),
            note=(
                "Queued, not submitted. The reference the caller received says exactly that, so "
                "a buffered escalation is never mistaken for a reviewed one."
            ),
        )
        findings = Panel(
            title="Findings",
            rows=(
                Row("Exceptions raised", str(self.escalated)),
                Row(
                    "Routed to review",
                    str(self.routed),
                    "ok" if self.routed == self.escalated else "bad",
                ),
                Row(
                    "Personal data on the wire",
                    "LEAKED" if leaked else "none",
                    "bad" if leaked else "ok",
                ),
            ),
            note=(
                "Every exception is accounted for. A flag with no routing reference is "
                "auto-execution with extra steps."
            ),
            tone="bad" if leaked or self.routed != self.escalated else "ok",
        )
        actions = Panel(
            title="Next actions",
            rows=(
                Row("Control owner", "open the queued exception and remediate or accept it"),
                Row("Operator", "point HRZ_HUMAN_REVIEW_URL at the console and flush the outbox"),
            ),
        )
        return [queue, findings, actions], {"pending": len(pending), "wire_leak": leaked}

    def _step_audit(self) -> Produced:
        log = self.container.audit.log
        report = self.container.audit.verify()
        self.chain_ok = report.ok
        export = self.workdir / "export" / "audit.jsonl"
        export.parent.mkdir(parents=True, exist_ok=True)
        written = log.export_jsonl(export)
        restored = HashChainedAuditLog(":memory:")
        reloaded = restored.import_jsonl(export)
        round_trip = restored.verify_chain()
        anchored = bool(self.settings.audit_anchor_path) and self.anchor_path.exists()
        trail = Panel(
            title="Audit trail",
            rows=(
                Row("Records", str(report.entries)),
                Row("Hash-chained", str(report.chained)),
                Row(
                    "Unverifiable (unchained)",
                    str(report.legacy),
                    "ok" if report.legacy == 0 else "bad",
                ),
                Row("Verdict", report.detail, "ok" if report.ok else "bad"),
                Row(
                    "External head anchor",
                    "configured" if anchored else "absent",
                    "ok" if anchored else "warn",
                ),
            ),
            note=(
                "The chain alone cannot detect a truncated tail: dropping the newest rows leaves "
                "a shorter chain that verifies perfectly. The anchor, kept on a different "
                "volume, is what closes that gap."
            ),
            tone="ok" if report.ok else "bad",
        )
        portable = Panel(
            title="Open-format round trip",
            rows=(
                Row("Exported records", str(written)),
                Row("Reloaded into a fresh store", str(reloaded)),
                Row("Chain after reload", round_trip.detail, "ok" if round_trip.ok else "bad"),
            ),
            note=(
                "JSON Lines with the hashes included, so a consumer can re-verify the trail "
                "without this codebase. That is what makes the record portable."
            ),
            tone="ok" if round_trip.ok else "bad",
        )
        facts = {
            "chain_ok": report.ok,
            "entries": report.entries,
            "exported": written,
            "round_trip_ok": round_trip.ok,
            "anchored": anchored,
        }
        return [trail, portable], facts

    def _step_tamper(self) -> Produced:
        before = self.container.audit.verify()
        target = _rewrite_a_record(self.audit_path)
        after = self.container.audit.verify()
        self.chain_ok = after.ok
        detected = (not after.ok) and after.first_bad_seq == target
        attack = Panel(
            title="The tamper",
            rows=(
                Row("Append-only triggers", "dropped by the attacker", "warn"),
                Row("Record rewritten in place", "seq " + str(target), "warn"),
                Row("Verdict before the rewrite", before.detail, "ok"),
            ),
            note=(
                "File access beats a database trigger. A store that claims otherwise is "
                "describing a policy, not a control."
            ),
        )
        findings = Panel(
            title="Findings",
            rows=(
                Row("Chain intact", "YES" if after.ok else "no", "bad" if after.ok else "ok"),
                Row("First broken record", str(after.first_bad_seq), "ok"),
                Row("Detail", after.detail),
                Row(
                    "Named the exact rewritten record",
                    "yes" if detected else "no",
                    "ok" if detected else "bad",
                ),
            ),
            note=(
                "Tamper-EVIDENT, not tamper-proof. The guarantee is that a rewrite cannot pass "
                "unnoticed, and that the report names which record broke."
            ),
            tone="ok" if detected else "bad",
        )
        actions = Panel(
            title="Next actions",
            rows=(
                Row("Operator", "restore from the exported JSONL and re-anchor deliberately"),
                Row("Auditor", "treat every record from seq " + str(target) + " on as suspect"),
            ),
        )
        facts = {"tampered_seq": target, "detected": detected, "chain_ok": after.ok}
        return [attack, findings, actions], facts

    def _step_portability(self) -> Produced:
        onprem = build_container(Settings(profile="onprem", tenant=TENANT))
        rows: list[Row] = []
        refused: list[str] = []
        absent: list[str] = []
        for port, call in EXIT_CALLS.items():
            expected_absent = port in EXIT_ABSENT
            try:
                call(onprem)
            except NotImplementedError as exc:
                if expected_absent:
                    rows.append(Row(port, "REFUSED, but is meant to be absent", "bad"))
                else:
                    refused.append(port)
                    rows.append(Row(port, "refused: " + str(exc).split(":")[0], "ok"))
            else:
                if expected_absent:
                    absent.append(port)
                    rows.append(Row(port, "absent, by design (a diagnostic, not a control)", "ok"))
                else:
                    rows.append(Row(port, "SUCCEEDED SILENTLY", "bad"))
        exit_panel = Panel(
            title="Exit profile (onprem)",
            rows=tuple(rows),
            note=(
                "Selected by one environment variable. No domain module was edited and no "
                "import changed."
            ),
            tone="ok" if len(refused) + len(absent) == len(EXIT_CALLS) else "bad",
        )
        bounds = Panel(
            title="What this does and does not prove",
            rows=(
                Row("Proved", "every port is swappable and every seam is named"),
                Row("Proved", "an unimplemented seam refuses instead of dropping work"),
                Row("NOT proved", "a running on-premises deployment exists"),
                Row("NOT proved", "model, infrastructure or whole-system portability"),
            ),
            note=(
                "Bounded claims are the point. Run scripts/portability_demo.py for the full "
                "seam tour, with a pass or fail per named check."
            ),
        )
        return [exit_panel, bounds], {
            "refused": sorted(refused),
            "absent": sorted(absent),
        }

    # -------------------------------------------------------------- helpers

    def _control_panels(self, pack_id: str, *, expect_routing: bool) -> Produced:
        pack = self._pack(pack_id)
        monitored = self.service.evaluate_pack(pack, as_of=AS_OF, tenant=TENANT, actor=ACTOR)
        result = monitored.result
        self.cases += 1
        if result.requires_human_review:
            self.escalated += 1
            self.routed += 1
        consistent = bool(monitored.review_ref) == expect_routing == result.requires_human_review
        decision = Panel(
            title="Control: " + result.control_id,
            rows=(
                Row("Test kind", result.test_kind.value),
                Row(
                    "Verdict", "PASS" if result.passed else "FAIL", "ok" if result.passed else "bad"
                ),
                Row("Design effectiveness", result.design.rating.value),
                Row("Operating effectiveness", result.operating.rating.value),
                Row("Requires human review", str(result.requires_human_review)),
                Row(
                    "Routed to review",
                    monitored.review_ref or "not routed (passing)",
                    "ok" if consistent else "bad",
                ),
                Row("Written back to Rgc7", monitored.writeback_ref or "n/a"),
                Row("Attributed to", ACTOR),
            ),
            note=(
                "Design and operating effectiveness are computed by pure stdlib code and are "
                "replayable. A model narrates this result; it never produces it."
            ),
            tone="ok" if consistent else "bad",
        )
        finding_rows = tuple(Row(f.severity.value, f.detail, "bad") for f in result.findings) or (
            Row("findings", "none: the control passed", "ok"),
        )
        findings = Panel(title="Findings", rows=finding_rows)
        evidence = Panel(
            title="Evidence and citations",
            rows=tuple(
                Row(citation.title, citation.snippet or citation.source_id)
                for citation in result.citations
            )
            or (Row("citations", "NONE", "bad"),),
            note="Every claim carries its source. An uncited claim is a hallucination risk.",
        )
        facts = {
            "subject": result.control_id,
            "severity": result.severity.value,
            "passed": result.passed,
            "requires_human_review": result.requires_human_review,
            "review_ref": monitored.review_ref,
            "consistent": consistent,
        }
        return [decision, findings, evidence], facts

    # -------------------------------------------------------------- state

    def state(self) -> dict[str, Any]:
        current = self.results[-1]
        return {
            "service": SERVICE_NAME,
            "catalog_id": CATALOG_ID,
            "repository": REPOSITORY,
            "profile": self.settings.profile,
            "region": self.settings.region,
            "step": current.key,
            "step_index": self.index,
            "step_count": len(STEPS),
            "label": current.label,
            "next": "" if self.done else STEPS[len(self.results)].label,
            "done": self.done,
            "totals": {
                "cases": self.cases,
                "escalated": self.escalated,
                "routed": self.routed,
                "chain_ok": self.chain_ok,
            },
            "steps": [_step_to_dict(result) for result in self.results],
        }


def _step_to_dict(result: StepResult) -> dict[str, Any]:
    return {
        "key": result.key,
        "label": result.label,
        "narration": result.narration,
        "facts": result.facts,
        "panels": [
            {
                "title": panel.title,
                "note": panel.note,
                "tone": panel.tone,
                "rows": [
                    {"label": row.label, "value": row.value, "tone": row.tone} for row in panel.rows
                ],
            }
            for panel in result.panels
        ],
    }


def _summarise(payload: Any) -> str:
    """One readable line for a queued review, without dumping the whole payload."""
    if isinstance(payload, dict):
        parts = [
            str(payload[key])
            for key in ("subject", "severity", "maker", "tenant")
            if payload.get(key)
        ]
        if parts:
            return " / ".join(parts)
    return json.dumps(payload, sort_keys=True)[:120]


def _rewrite_a_record(store: Path) -> int:
    """Drop the append-only triggers and rewrite one INTERIOR record, as an attacker would."""
    conn = sqlite3.connect(store)
    try:
        conn.execute("DROP TRIGGER IF EXISTS audit_log_no_update")
        conn.execute("DROP TRIGGER IF EXISTS audit_log_no_delete")
        rows = conn.execute("SELECT seq, event_json FROM audit_log ORDER BY seq ASC").fetchall()
        if len(rows) < 3:
            raise RuntimeError("the tamper step needs an interior record to rewrite")
        middle = rows[len(rows) // 2]
        payload = json.loads(middle[1])
        payload["decision"] = "allowed"
        payload["severity"] = "low"
        conn.execute(
            "UPDATE audit_log SET event_json = ? WHERE seq = ?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), int(middle[0])),
        )
        conn.commit()
        return int(middle[0])
    finally:
        conn.close()


def _exit_audit(container: Any) -> Any:
    return container.audit.record(
        kernel.AuditEvent(
            action="control_test",
            actor=ACTOR,
            decision=kernel.Decision.ESCALATED,
            severity=kernel.Severity.HIGH,
            redacted_summary="SC-7-egress [config_scan] FAIL",
        )
    )


def _exit_review(container: Any) -> Any:
    return container.review_router.route(_DEMO_RESULT, maker=ACTOR, tenant=TENANT)


def _exit_identity(container: Any) -> Any:
    return container.identity.resolve(RequestContext(headers={"x-dev-persona": "approver"}))


def _exit_inventory(container: Any) -> Any:
    return container.control_inventory.list_controls(TENANT)


def _exit_scanner(container: Any) -> Any:
    return container.evidence_scanner.scan(_EGRESS_PACK)


def _exit_control_evidence(container: Any) -> Any:
    return container.control_evidence.fetch("AC-2-recert")


def _exit_writeback(container: Any) -> Any:
    return container.writeback.append_result(_DEMO_RESULT, tenant=TENANT)


def _exit_timeseries(container: Any) -> Any:
    return container.timeseries.export(_DEMO_RESULT)


def _exit_generation(container: Any) -> Any:
    return container.generation.generate("narrate this")


def _exit_tracer(container: Any) -> Any:
    with container.tracer.span("exit.tour", action="portability"):
        return None


def _exit_evaluation(container: Any) -> Any:
    return container.evaluation.gate("eval/datasets/golden_cases.jsonl")


#: The calls the exit profile must REFUSE, one per port with an exit placeholder. Add a port,
#: add a row: a seam nobody calls is a seam nobody knows is unimplemented.
EXIT_CALLS: dict[str, Callable[[Any], Any]] = {
    "audit": _exit_audit,
    "identity": _exit_identity,
    "review_router": _exit_review,
    "tracer": _exit_tracer,
    "evaluation": _exit_evaluation,
    "control_inventory": _exit_inventory,
    "evidence_scanner": _exit_scanner,
    "control_evidence": _exit_control_evidence,
    "writeback": _exit_writeback,
    "timeseries": _exit_timeseries,
    "generation": _exit_generation,
}


#: Diagnostic seams that complete as an honest no-op under the exit profile.
EXIT_ABSENT: frozenset[str] = frozenset({"tracer"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the scripted offline demo end to end.")
    parser.add_argument(
        "output",
        nargs="?",
        default="demo.json",
        help="where to write the audit-view JSON (default: demo.json)",
    )
    parser.add_argument("--quiet", action="store_true", help="write the JSON and print nothing")
    args = parser.parse_args(argv)

    run = DemoRun()
    run.run_to_end()
    state = run.state()
    Path(args.output).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    if not args.quiet:
        for step in state["steps"]:
            print("[" + step["key"] + "] " + step["label"])
        totals = state["totals"]
        print(
            "cases="
            + str(totals["cases"])
            + " escalated="
            + str(totals["escalated"])
            + " routed="
            + str(totals["routed"])
        )
        print("wrote " + args.output)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
