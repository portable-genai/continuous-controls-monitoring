"""The monitoring paths open spans, and no span carries content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit store.
So the value of tracing these paths depends entirely on the spans carrying structural
attributes only: which action, whose, which tenant, which control, how many packs. An evidence
identifier, a control owner, a finding or any narration text reaching a span has left the
boundary the service's ``redact`` call exists to hold, and it has left it silently.

Two shapes are pinned here rather than one. ``evaluate_pack`` opens a leaf span, and ``run``
opens a PARENT with one child per pack: a run is a fan-out, not an alias, so the nesting is
honest and the depths are asserted rather than assumed. The planted-identifier case drives the
service with evidence carrying an NRIC, so the check runs against input that would leak.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from continuous_controls_monitoring.config import build_container
from continuous_controls_monitoring.domain.models import (
    ControlTestPack,
    EvidenceRecord,
    MonitoringRun,
    TestKind,
)
from continuous_controls_monitoring.domain.monitoring_service import MonitoringService

from tests.conftest import local_settings
from tests.fixtures import sample_cases

#: Every attribute key either span is allowed to carry. An exception that started explaining
#: itself on the span (a finding, an owner, an evidence ref) would widen these sets, which is
#: the point of asserting on the set rather than on the individual keys.
_RUN_KEYS = {"action", "actor", "tenant", "pack_count"}
_EVALUATE_KEYS = {"action", "actor", "tenant", "control_id"}


class _RecordingTracer:
    """Captures every span name, attribute and nesting depth so the test can inspect them."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []
        self.depths: list[int] = []
        self._open = 0

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        self.depths.append(self._open)
        self._open += 1
        try:
            yield
        finally:
            self._open -= 1

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


class _PlantedScanner:
    """A scanner whose evidence carries the planted identifier, for the leak proof."""

    def scan(self, pack: ControlTestPack) -> tuple[EvidenceRecord, ...]:
        return (
            EvidenceRecord(
                control_id=pack.control_id,
                kind=TestKind.CONFIG_SCAN,
                source="cloud_asset_inventory",
                identifier=f"bucket-owned-by-{sample_cases.PLANTED_NRIC}",
                attributes={"public_access_prevention": "inherited"},
                source_ref=f"note NRIC {sample_cases.PLANTED_NRIC} on file",
            ),
        )


def _service(tracer: _RecordingTracer, scanner: object | None = None) -> MonitoringService:
    """The REAL local adapters, exactly as ``tests.conftest.build_monitoring_service`` wires."""
    container = build_container(local_settings())
    return MonitoringService(
        audit=container.audit,
        inventory=container.control_inventory,
        scanner=scanner or container.evidence_scanner,  # type: ignore[arg-type]
        control_evidence=container.control_evidence,
        writeback=container.writeback,
        timeseries=container.timeseries,
        generation=container.generation,
        review_router=container.review_router,
        tracer=tracer,  # type: ignore[arg-type]
        policy=container.settings.policy,
    )


def _run() -> tuple[_RecordingTracer, MonitoringRun, MonitoringService]:
    tracer = _RecordingTracer()
    service = _service(tracer)
    run = service.run(
        as_of=sample_cases.AS_OF, tenant=sample_cases.TENANT, actor=sample_cases.ACTOR
    )
    return tracer, run, service


def _emitted(tracer: _RecordingTracer) -> str:
    """Every attribute VALUE that was emitted, and every KEY, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# The spans exist, with honest nesting
# --------------------------------------------------------------------------- #
def test_grading_one_pack_opens_exactly_one_named_span() -> None:
    tracer = _RecordingTracer()
    service = _service(tracer)
    pack = service.packs[0]
    service.evaluate_pack(
        pack, as_of=sample_cases.AS_OF, tenant=sample_cases.TENANT, actor=sample_cases.ACTOR
    )
    assert [name for name, _ in tracer.spans] == ["controls_monitoring.evaluate_pack"]
    assert tracer.depths == [0]


def test_a_run_opens_a_parent_span_with_one_child_per_pack() -> None:
    """The fan-out shape. A parent that timed a single child would be double counting."""
    tracer, run, service = _run()
    assert len(service.packs) > 1, "the shipped packs stopped being a fan-out worth a parent"
    names = [name for name, _ in tracer.spans]
    assert names[0] == "controls_monitoring.run"
    assert names[1:] == ["controls_monitoring.evaluate_pack"] * len(service.packs)
    assert tracer.depths[0] == 0, "the run span is the parent"
    assert set(tracer.depths[1:]) == {1}, "every pack span is a child of the run, not a sibling"


# --------------------------------------------------------------------------- #
# What the spans carry
# --------------------------------------------------------------------------- #
def test_the_spans_carry_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose run is slow, on which tenant, on which control", nothing more."""
    tracer, _, service = _run()
    _, run_attributes = tracer.spans[0]
    assert run_attributes["action"] == "run"
    assert run_attributes["actor"] == sample_cases.ACTOR
    assert run_attributes["tenant"] == sample_cases.TENANT
    assert run_attributes["pack_count"] == str(len(service.packs))

    for (_, attributes), pack in zip(tracer.spans[1:], service.packs, strict=True):
        assert attributes["action"] == "evaluate_pack"
        assert attributes["actor"] == sample_cases.ACTOR
        assert attributes["tenant"] == sample_cases.TENANT
        assert attributes["control_id"] == pack.control_id


def test_the_attribute_sets_are_a_fixed_allowlist_for_parent_and_children() -> None:
    """The estate contains a FAILING control, and its exception must not widen the sets."""
    tracer, run, _ = _run()
    assert any(m.result.requires_human_review for m in run.monitored), (
        "the seeded estate stopped failing; this test must cover a consequential grade"
    )
    assert set(tracer.spans[0][1]) == _RUN_KEYS
    for _, attributes in tracer.spans[1:]:
        assert set(attributes) == _EVALUATE_KEYS


# --------------------------------------------------------------------------- #
# What the spans must never carry
# --------------------------------------------------------------------------- #
def test_no_span_attribute_carries_evidence_content_owners_or_narration() -> None:
    """Every content-shaped value in reach of a run over the real offline estate."""
    tracer, run, _ = _run()
    emitted = _emitted(tracer)

    forbidden: list[str] = [
        "sc7-owner@bank.example",
        "bucket-kyc-archive",
        "bucket-scratch-exports",
        "//storage.googleapis.com/bucket-scratch-exports",
    ]
    for monitored in run.monitored:
        # Some per-result fields are legitimately empty (an unowned control, a discarded
        # narration); only the non-empty ones are meaningful needles.
        candidates = (
            monitored.result.summary,
            monitored.result.owner,
            monitored.narration_headline,
            *(f.detail for f in monitored.result.findings),
        )
        forbidden.extend(value for value in candidates if value)
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal not in emitted, f"a span attribute carried {literal!r}"
        assert literal.lower() not in emitted.lower(), f"a span attribute carried {literal!r}"


def test_no_span_attribute_carries_the_planted_identifier() -> None:
    """Evidence carrying an NRIC must not surface in any attribute, whatever the outcome."""
    tracer = _RecordingTracer()
    service = _service(tracer, scanner=_PlantedScanner())
    pack = next(p for p in service.packs if p.control_id == "SC-7-egress")
    service.evaluate_pack(
        pack, as_of=sample_cases.AS_OF, tenant=sample_cases.TENANT, actor=sample_cases.ACTOR
    )
    emitted = _emitted(tracer)
    assert sample_cases.PLANTED_NRIC not in emitted
    assert sample_cases.PLANTED_NRIC.lower() not in emitted.lower()
    for _, attributes in tracer.spans:
        assert set(attributes) == _EVALUATE_KEYS


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    tracer, _, _ = _run()
    values: list[Any] = [v for _, attributes in tracer.spans for v in attributes.values()]
    assert values
    assert all(isinstance(value, str) for value in values)
