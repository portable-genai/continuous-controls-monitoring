"""The application service: gather evidence, grade controls, route exceptions, write back.

This is the orchestration layer. The consequential decision is NOT here: it is in the pure
``ControlTestEngine``. This service only coordinates the ports around that engine, in the order
the discipline requires:

1. READ the control from the obligations-control-mapping inventory (never a parallel catalog); 2.
   GATHER evidence from the scanner and from compliance-advisory's evidence packs; 3. GRADE with the
   pure engine (design and operating effectiveness, deterministic); 4. REDACT the graded result
   ONCE, at the edge of the service (see :func:`redacted_result`); 5. write the audit record, WRITE
   the result back to obligations-control-mapping as an evidence node, and export the time-series
   row, all from the redacted projection; 6. NARRATE an exception with the model, validate it
   against a schema and groundedness, and DISCARD on failure (the model never produces a figure); 7.
   ROUTE every exception to the control owner via human-review-console (rule R8) and never
   auto-close.

The model touches only step 6, and even there its output is discarded unless it is grounded in
the engine's own figures.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from typing import Any

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.control_evidence import ControlEvidencePort
from ..ports.control_inventory import ControlInventoryPort
from ..ports.evidence_scanner import EvidenceScannerPort
from ..ports.generation import GenerationPort
from ..ports.observability import ObservabilityTracerPort
from ..ports.review_router import ReviewRouterPort
from ..ports.timeseries import TimeSeriesExportPort
from ..ports.writeback import EffectivenessWritebackPort
from .kernel import AuditEvent, redacted_citations, utcnow
from .models import (
    ControlFinding,
    ControlTestPack,
    ControlTestResult,
    MonitoredControl,
    MonitoringRun,
)
from .narration import build_prompt, validate_narration
from .packs import load_packs
from .pii import PII_PATTERNS
from .testing import ControlTestEngine

#: The run span is a PARENT: a run is a fan-out over packs, so the parent times the whole sweep
#: and each child times exactly one pack. Structural attributes only: see :meth:`.run`.
_RUN_SPAN = "controls_monitoring.run"

#: One span per graded pack, nested under the run span when reached through it.
_EVALUATE_SPAN = "controls_monitoring.evaluate_pack"


def redacted_findings(findings: tuple[ControlFinding, ...]) -> tuple[ControlFinding, ...]:
    """Mask a finding's prose and its evidence locator, and nothing else.

    ``detail`` is assembled from the evidence record the detector read (``testing.py`` writes
    ``f"{record.identifier}: ..."``) and ``evidence_ref`` is ``record.source_ref or
    record.identifier``, so both are raw upstream text: an asset name, an entitlement, a
    transaction reference, any of which a real estate names after a person.

    ``kind``, ``dimension``, ``severity``, ``rule_id``, ``control_id`` and ``pack_id`` are left
    exactly as the engine produced them. They are the taxonomy and the join keys, they carry no
    upstream text, and masking a join key would silently detach a finding from its control.
    """
    return tuple(
        replace(
            finding,
            detail=redact(finding.detail, PII_PATTERNS),
            evidence_ref=redact(finding.evidence_ref, PII_PATTERNS),
            citations=redacted_citations(finding.citations),
        )
        for finding in findings
    )


def redacted_result(result: ControlTestResult) -> ControlTestResult:
    """The graded result with every CONTENT field masked and every FIGURE left alone.

    This is the one seam. A graded result reaches four sinks outside this service (the WORM
    audit write, the obligations-control-mapping write-back, the time-series export and the
    human-review-console review payload) and
    one inside the process that is really outside it under the managed profile (the model, via
    ``build_prompt``). Masking at each sink means getting it right five times, and the write-back
    and the export are the two nobody thinks of because today's adapters happen to serialise
    only figures: the port is handed the WHOLE result, so the day either adapter adds
    ``summary`` to its payload the leak is already wired. So the projection is built HERE, where
    the result crosses out of the service, and every sink is handed the same masked object.

    What is masked is content: ``summary`` (which the service concatenates with ``owner``, an
    address by design), ``owner`` itself, and each finding's prose, locator and citations.

    What is NOT masked is anything the deterministic engine computed or keyed on: ``passed``,
    both :class:`EffectivenessScore` records, ``evidence_count``, ``decision``,
    ``requires_human_review``, ``as_of``, ``test_kind``, ``control_id`` and ``pack_id``. A
    masked figure would be a changed figure, and a masked control id would be rejected by the
    obligations-control-mapping write-back, which only ever attaches evidence to a control it
    already knows.
    """
    return replace(
        result,
        owner=redact(result.owner, PII_PATTERNS),
        summary=redact(result.summary, PII_PATTERNS),
        findings=redacted_findings(result.findings),
        citations=redacted_citations(result.citations),
    )


class MonitoringService:
    """Coordinate the ports around the pure engine for one tenant's control tests."""

    def __init__(
        self,
        *,
        audit: AuditSinkPort,
        inventory: ControlInventoryPort,
        scanner: EvidenceScannerPort,
        control_evidence: ControlEvidencePort,
        writeback: EffectivenessWritebackPort,
        timeseries: TimeSeriesExportPort,
        generation: GenerationPort,
        review_router: ReviewRouterPort,
        tracer: ObservabilityTracerPort,
        policy: Mapping[str, Any] | None = None,
    ) -> None:
        self._audit = audit
        self._inventory = inventory
        self._scanner = scanner
        self._control_evidence = control_evidence
        self._writeback = writeback
        self._timeseries = timeseries
        self._generation = generation
        self._review = review_router
        self._tracer = tracer
        self._engine = ControlTestEngine()
        self._packs = load_packs(policy)

    @property
    def packs(self) -> tuple[ControlTestPack, ...]:
        return self._packs

    def run(self, *, as_of: date, tenant: str, actor: str) -> MonitoringRun:
        """Test every configured pack for ``tenant`` as of ``as_of``.

        The sweep runs inside one PARENT span with one child per pack: a run is a fan-out, not
        an alias for a single grade, so the parent times the whole sweep and each child exactly
        one pack. Attributes on both are STRUCTURAL only; see :meth:`evaluate_pack` for why.
        """
        with self._tracer.span(
            _RUN_SPAN,
            action="run",
            actor=actor,
            tenant=tenant,
            pack_count=str(len(self._packs)),
        ):
            monitored = tuple(
                self.evaluate_pack(pack, as_of=as_of, tenant=tenant, actor=actor)
                for pack in self._packs
            )
            return MonitoringRun(as_of=as_of, monitored=monitored)

    def evaluate_pack(
        self, pack: ControlTestPack, *, as_of: date, tenant: str, actor: str
    ) -> MonitoredControl:
        """Grade one pack end to end and perform every side effect its result demands.

        The whole path runs inside one span. Its attributes are STRUCTURAL only, never an
        evidence identifier, an owner, a finding or any narration text: a trace backend is not
        the WORM audit trail. It has no redaction stage, a wider read audience and no retention
        rule written against a regulator's requirement, so anything content-shaped that reaches
        a span has left the boundary the ``redact`` call exists to hold, and left it silently.

        The engine grades the RAW evidence, because a masked figure would be a changed figure.
        Everything downstream of the grade is handed :func:`redacted_result` instead, so the
        audit write, the obligations-control-mapping write-back, the time-series export, the model
        and the human-review-console payload
        are covered by one masking step rather than by five that each have to remember.

        The engine's OWN result is what goes back to the caller. The API contract returns the
        control owner and the finding detail to an authenticated auditor who has to act on them,
        and redacting the return value would mask the estate from the person testing it. The
        narration is the exception: it is built from the redacted projection, so what the model
        was allowed to see is exactly what the model is allowed to say back.
        """
        with self._tracer.span(
            _EVALUATE_SPAN,
            action="evaluate_pack",
            actor=actor,
            tenant=tenant,
            control_id=pack.control_id,
        ):
            control = self._inventory.get_control(pack.control_id, tenant=tenant)
            evidence = self._scanner.scan(pack) + self._control_evidence.fetch(pack.control_id)
            result = self._engine.evaluate(pack, control, evidence, as_of=as_of)
            outbound = redacted_result(result)

            self._record_audit(outbound, actor=actor)

            # Write the effectiveness evidence back to obligations-control-mapping and export the
            # time-series row. A
            # result for a control that is not in the inventory has nothing to attach to, so it
            # is not written back (that is itself a design finding on the result).
            writeback_ref = ""
            if control is not None:
                writeback_ref = self._writeback.append_result(outbound, tenant=tenant)
            self._timeseries.export(outbound)

            headline, body = self._narrate(outbound)

            review_ref = ""
            if result.requires_human_review:
                # Rule R8: an exception is ROUTED to the control owner, in the same call that
                # produced it, and never auto-closes.
                review_ref = self._review.route(outbound, maker=actor, tenant=tenant)

            return MonitoredControl(
                result=result,
                review_ref=review_ref,
                writeback_ref=writeback_ref,
                narration_headline=headline,
                narration_body=body,
            )

    # ------------------------------------------------------------------ #
    def _record_audit(self, result: ControlTestResult, *, actor: str) -> None:
        """Write one WORM record. ``result`` is already the :func:`redacted_result` projection.

        The ``redact`` call stays anyway, and so does the one inside ``AuditEvent``: redaction
        is idempotent, and this method is the last thing standing between a future caller that
        forgot the projection and an immutable record.
        """
        summary = redact(f"{result.summary} :: {result.owner}", PII_PATTERNS)
        self._audit.record(
            AuditEvent(
                action="control_test",
                actor=actor,
                decision=result.decision,
                severity=result.severity,
                redacted_summary=summary,
                citations=result.citations,
                timestamp=utcnow(),
            )
        )

    def _narrate(self, result: ControlTestResult) -> tuple[str, str]:
        """Draft and validate an exception narration; return empty strings when discarded.

        Only exceptions are narrated: a passing control needs no write-up. The model output is
        validated against the schema and the groundedness check, and DISCARDED (empty strings)
        on any failure, so the figure that reaches a reader is always the engine's.

        ``result`` is the :func:`redacted_result` projection, so the prompt's FACTS block carries
        masked finding prose. Grounding is checked against the SAME projection, which is what
        keeps the two consistent: the fact set is derived from the text the model actually saw,
        so masking cannot turn a faithful restatement into an ungrounded one, and a model that
        echoed a digit from an identifier it was never shown would be rejected.
        """
        if not result.requires_human_review:
            return ("", "")
        raw = self._generation.generate(build_prompt(result))
        narration = validate_narration(raw, result)
        if narration is None:
            return ("", "")
        return (narration.headline, narration.body)
