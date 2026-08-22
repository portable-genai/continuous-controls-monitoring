"""Nothing redaction removes survives into any sink the service writes to (check C3).

The service masked the audit summary and handed every OTHER sink the engine's raw result: the
model prompt carried the evidence identifier verbatim (``build_prompt`` interpolates
``ControlFinding.detail``, which the engine builds as ``f"{record.identifier}: ..."``), and the
Rgc7 write-back and the time-series export were handed the whole result object, summary, owner,
findings and all. It also handed the audit event its citations untouched while masking the
summary beside them. One masking step now sits where the graded result crosses out of the
service, so every sink is covered once.

Two rules this suite holds, and they pull in opposite directions, which is why both are written
down:

* every CONTENT field is scanned: the audit summary, each citation's locator, title and snippet,
  each finding's prose and evidence locator, and the FACTS block the model is handed. All of
  them are built from raw upstream text wearing a structural-looking name.
* the ATTRIBUTION and JOIN-KEY fields are not masked. ``AuditEvent.actor`` is the verified
  principal and is an address by design, so a blanket scan over a whole audit row could never go
  green; ``control_id`` and ``pack_id`` are the keys Rgc7 attaches evidence by, and a masked one
  would detach the result from the control it grades.

Scored two ways, as the eval metric is: the shared pack's own rows, plus the planted literals,
which still fire if a pattern row is broken.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, replace
from typing import Any

from pii_kit import pack_leak

from continuous_controls_monitoring.adapters._review_payload import result_to_review
from continuous_controls_monitoring.config import Container, build_container
from continuous_controls_monitoring.domain.kernel import AuditEvent, Decision, Severity
from continuous_controls_monitoring.domain.models import (
    ControlTestPack,
    EvidenceRecord,
    MonitoredControl,
)
from continuous_controls_monitoring.domain.monitoring_service import MonitoringService
from continuous_controls_monitoring.domain.pii import PII_PATTERNS

from tests.conftest import local_settings
from tests.fixtures import sample_cases

_PLANTED = (sample_cases.PLANTED_NRIC, sample_cases.PLANTED_EMAIL)


class _PlantingScanner:
    """The real local scanner plus one record naming a person, as a real estate scan would.

    The scanner is where upstream text enters the pipeline, so this is the honest place to plant:
    swapping the port keeps the service, the engine, the redaction seam, the audit adapter, the
    narrator and the review payload all real.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def scan(self, pack: ControlTestPack) -> tuple[EvidenceRecord, ...]:
        return tuple(self._inner.scan(pack)) + sample_cases.PII_EVIDENCE


class _SpyGeneration:
    """The real local narrator, with a tap on what the model boundary was actually handed.

    Asserting on the narration alone cannot see this: a narrator is free to drop a fact it was
    given, so the write-up can read clean while the raw identifier still crossed into the model's
    context. Under the managed profile that context leaves the process entirely.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._inner.generate(prompt)


class _SpyWriteback:
    """Records the object the Rgc7 write-back PORT was handed, not the row an adapter kept."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.seen: list[Any] = []

    def append_result(self, result: Any, *, tenant: str = "") -> str:
        self.seen.append(result)
        return str(self._inner.append_result(result, tenant=tenant))


class _SpyTimeSeries:
    """Records the object the time-series export PORT was handed, for the same reason."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.seen: list[Any] = []

    def export(self, result: Any) -> int:
        self.seen.append(result)
        return int(self._inner.export(result))


def _wire_content(review: Any) -> dict[str, Any]:
    """The serialised Hrz7 payload minus the one attribution field.

    ``maker`` is skipped for the same reason ``actor`` is on an audit row: it is the verified
    principal and an address by design, so a whole-payload scan could never go green. Everything
    else the ``Review`` carries is in scope, including any field added to it later.
    """
    return {key: value for key, value in review.to_payload().items() if key != "maker"}


def _content(row: Mapping[str, Any]) -> str:
    """Every content-bearing field of one audit row, as one scannable blob.

    ``actor`` and the structural columns are excluded deliberately: see the module docstring.
    """
    return " ".join(
        (
            str(row.get("redacted_summary", "")),
            json.dumps(row.get("citations", []), sort_keys=True),
        )
    )


def _drive() -> tuple[MonitoredControl, Container, _SpyGeneration, _SpyWriteback, _SpyTimeSeries]:
    """One real run of the real service over evidence that names a person."""
    container = build_container(local_settings())
    generation = _SpyGeneration(container.generation)
    writeback = _SpyWriteback(container.writeback)
    timeseries = _SpyTimeSeries(container.timeseries)
    service = MonitoringService(
        audit=container.audit,
        inventory=container.control_inventory,
        scanner=_PlantingScanner(container.evidence_scanner),
        control_evidence=container.control_evidence,
        writeback=writeback,
        timeseries=timeseries,
        generation=generation,
        review_router=container.review_router,
        tracer=container.tracer,
        policy=container.settings.policy,
    )
    monitored = service.evaluate_pack(
        sample_cases.PII_CITATION_PACK,
        as_of=sample_cases.AS_OF,
        tenant=sample_cases.TENANT,
        actor=sample_cases.ACTOR,
    )
    return monitored, container, generation, writeback, timeseries


def _assert_clean(blob: str, where: str) -> None:
    assert not pack_leak(blob, PII_PATTERNS), f"a pack row matched in {where}: {blob}"
    for token in _PLANTED:
        assert token not in blob, f"planted {token!r} survived into {where}: {blob}"


def test_no_identifier_reaches_the_worm_audit_record() -> None:
    _monitored, container, _gen, _wb, _ts = _drive()
    rows = list(container.audit.log.read_all())  # type: ignore[attr-defined]
    assert rows, "the evaluate path wrote no audit record, so this proves nothing"
    for row in rows:
        _assert_clean(_content(row), "the WORM record")


def test_no_identifier_reaches_the_model() -> None:
    """The FACTS block is assembled from finding prose, which is cut from the evidence record."""
    _monitored, _container, generation, _wb, _ts = _drive()
    assert generation.prompts, "guard the guard: nothing is proved if generate was never called"
    for prompt in generation.prompts:
        _assert_clean(prompt, "the model prompt")


def test_no_identifier_reaches_the_rgc7_writeback_or_the_timeseries_export() -> None:
    """The PORT is scanned, not the row today's adapter happens to keep.

    Both adapters currently serialise figures only, so scanning their output would pass with the
    defect still in place. What the service HANDS them is the contract, and it is the whole
    result object: the day either adapter adds the summary to its payload, this is what decides
    whether that is a leak.
    """
    _monitored, _container, _gen, writeback, timeseries = _drive()
    assert writeback.seen, "no result reached the write-back port; this proves nothing"
    assert timeseries.seen, "no result reached the time-series port; this proves nothing"
    for result in (*writeback.seen, *timeseries.seen):
        _assert_clean(json.dumps(asdict(result), default=str), "an outbound port payload")


def test_no_identifier_reaches_the_routed_review_payload() -> None:
    """The console is a shared sink, and a citation LOCATOR crosses the wire like a snippet does.

    The payload actually enqueued by the R8 routing call is scanned, not one this test builds
    for itself: a re-created payload would prove that ``result_to_review`` can redact, not that
    the service handed it something it could.
    """
    monitored, container, _gen, _wb, _ts = _drive()
    assert monitored.review_ref, "the escalation was not routed, so there is no payload to scan"
    pending = container.review_router.outbox.pending()  # type: ignore[attr-defined]
    assert pending, "the outbox is empty; this proves nothing"
    _assert_clean(
        json.dumps([_wire_content(entry.review) for entry in pending], sort_keys=True, default=str),
        "the Hrz7 review payload",
    )


def test_the_whole_review_payload_is_redacted_not_only_its_narrative_fields() -> None:
    """Every field that crosses to the console, including the ones with structural names.

    ``subject`` was masked and ``case_ref`` and ``source_key`` were not, so an identifier the
    payload had just removed from one field crossed the wire in the two beside it. This repo
    never mints a control id, but it does not constrain one either: the managed inventory adapter
    builds every field of an ``InventoryControl`` out of whatever Rgc7's response carries
    (``adapters/gcp/control_inventory.py``), so a subject naming a person is Rgc7's to produce and
    this boundary's to mask. The scan is over the SERIALISED payload rather than a chosen list of
    fields, so a field added later is covered by default.
    """
    result = replace(
        sample_cases.PII_RESULT, control_id=f"SC-7-egress-for-{sample_cases.PLANTED_NRIC}"
    )
    review = result_to_review(result, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)
    _assert_clean(json.dumps(_wire_content(review), sort_keys=True, default=str), "the payload")
    assert review.case_ref == review.subject, "the case reference must be the masked subject"
    assert review.subject in review.source_key, "the idempotency key must be built from it too"


def test_the_audit_event_type_masks_every_content_field_by_construction() -> None:
    """The WORM boundary holds for callers that never go through the service at all.

    ``scripts/demo.py`` builds an ``AuditEvent`` directly and passes the engine's citations into
    it, and any surface added later can do the same. Masking inside the type is what makes the
    invariant true for all of them instead of true by convention for the ones written so far.
    """
    container = build_container(local_settings())
    container.audit.record(
        AuditEvent(
            action="control_test",
            actor=sample_cases.ACTOR,
            decision=Decision.ESCALATED,
            severity=Severity.HIGH,
            redacted_summary=f"SC-7-egress FAIL, raised by {sample_cases.PLANTED_EMAIL}",
            citations=(sample_cases.PII_CITATION,),
        )
    )
    rows = list(container.audit.log.read_all())  # type: ignore[attr-defined]
    assert rows, "nothing was recorded; this proves nothing"
    _assert_clean(_content(rows[-1]), "the WORM record")


def test_the_actor_is_kept_verbatim_because_it_is_attribution() -> None:
    """The caveat, pinned: the principal is an address and must NOT be masked away."""
    _monitored, container, _gen, _wb, _ts = _drive()
    actors = [str(row.get("actor", "")) for row in container.audit.log.read_all()]  # type: ignore[attr-defined]
    assert actors == [sample_cases.ACTOR]


def test_redaction_changes_no_figure_the_engine_produced() -> None:
    """Masking is masking. A changed number would be a changed verdict wearing a safety label.

    The write-back and the export exist to carry the effectiveness figures, so the projection
    they are handed has to be figure-for-figure identical to the engine's own result. The join
    keys are pinned here too: a masked ``control_id`` would be rejected by Rgc7, which only
    attaches evidence to a control it already knows.
    """
    monitored, _container, _gen, writeback, timeseries = _drive()
    engine = monitored.result
    for outbound in (*writeback.seen, *timeseries.seen):
        assert outbound.control_id == engine.control_id
        assert outbound.pack_id == engine.pack_id
        assert outbound.as_of == engine.as_of
        assert outbound.passed is engine.passed
        assert outbound.decision is engine.decision
        assert outbound.severity is engine.severity
        assert outbound.requires_human_review is engine.requires_human_review
        assert outbound.design == engine.design
        assert outbound.operating == engine.operating
        assert outbound.evidence_count == engine.evidence_count
        assert len(outbound.findings) == len(engine.findings)
        assert [f.rule_id for f in outbound.findings] == [f.rule_id for f in engine.findings]
        assert [f.severity for f in outbound.findings] == [f.severity for f in engine.findings]


def test_the_caller_still_receives_the_estate_detail_it_has_to_act_on() -> None:
    """The API contract is not narrowed: the auditor driving the test sees the real estate.

    Redaction is about what crosses OUT of the service, not about what the authenticated caller
    who asked for the test is allowed to read back. An auditor who cannot see which bucket
    drifted cannot remediate it.
    """
    monitored, _container, _gen, _wb, _ts = _drive()
    detail = " ".join(f.detail for f in monitored.result.findings)
    assert sample_cases.PLANTED_NRIC in detail, "the caller lost the evidence identifier"
    assert monitored.result.owner == "sc7-owner@bank.example", "the caller lost the control owner"
