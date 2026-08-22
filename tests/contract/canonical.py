"""ONE canonical request per port, shared by the structural and behavioural contract suites.

Parity means the same request through every implementation, so the request needs a single home.
Retyping it per suite is how two "parity" tests end up asserting different things.

Each :class:`PortCase` answers three questions about one port:

* ``invoke``   : what a single canonical call to this port looks like;
* ``answered`` : what it means for the OFFLINE family to have actually answered (a port that
  returns ``None`` and records nothing has not answered, it has merely not raised);
* ``managed_refusal`` : what the MANAGED family must do when called with no cloud reachable.
  Never a silent success: either it refuses because it is unconfigured, or its lazy SDK import
  fails. Both are honest; returning as if the work happened is not.

Adding a port means adding a case here. ``test_port_parity.py`` fails the build if this table
and the port map ever disagree, so the touch list in ``CONTRIBUTING.md`` is enforced rather than
merely written down.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_eval_kit import EvalReport
from hex_service_kit.identity import IdentityError, Principal, RequestContext
from hex_service_kit.observability import TokenUsage

from continuous_controls_monitoring.domain.kernel import (
    AuditEvent,
    Citation,
    Decision,
    Severity,
)
from continuous_controls_monitoring.domain.models import (
    ControlTestResult,
    InventoryControl,
)
from continuous_controls_monitoring.domain.narration import (
    build_prompt,
    validate_narration,
)

from tests.fixtures import sample_cases

#: The audit record every audit-port implementation is handed. Already redacted, as the port
#: requires: a raw identifier must never reach a WORM record.
CANONICAL_EVENT = AuditEvent(
    action="control_test",
    actor=sample_cases.ACTOR,
    decision=Decision.ESCALATED,
    severity=Severity.HIGH,
    redacted_summary="SC-7-egress [config_scan] FAIL: design effective, operating deficient",
    citations=(Citation(source_id="sox-404-icfr", title="ICFR", snippet="control effectiveness"),),
)

#: The escalated result every review-router / write-back / time-series implementation is handed.
CANONICAL_RESULT: ControlTestResult = sample_cases.ESCALATING_RESULT

#: The narration prompt the generation port is handed (built from the engine's own facts).
CANONICAL_PROMPT = build_prompt(CANONICAL_RESULT)

#: The inbound transport context every identity implementation is handed.
CANONICAL_CONTEXT = RequestContext(headers={"x-dev-persona": "auditor"})


@dataclass(frozen=True, slots=True)
class PortCase:
    """One port's canonical call plus the two verdicts the parity suites need."""

    invoke: Callable[[Any], Any]
    answered: Callable[[Any, Any], bool]
    managed_refusal: tuple[type[BaseException], ...]
    detail: str


def _audit_invoke(adapter: Any) -> Any:
    return adapter.record(CANONICAL_EVENT)


def _audit_answered(adapter: Any, _result: Any) -> bool:
    stored = adapter.log.read_all()
    return bool(stored) and stored[-1]["actor"] == sample_cases.ACTOR and adapter.verify().ok


def _identity_invoke(adapter: Any) -> Any:
    return adapter.resolve(CANONICAL_CONTEXT)


def _identity_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, Principal) and bool(result.actor)


def _review_invoke(adapter: Any) -> Any:
    return adapter.route(CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def _review_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.outbox.pending()) == 1


def _inventory_invoke(adapter: Any) -> Any:
    return adapter.list_controls(sample_cases.TENANT)


def _inventory_answered(_adapter: Any, result: Any) -> bool:
    return bool(result) and all(isinstance(c, InventoryControl) for c in result)


def _scanner_invoke(adapter: Any) -> Any:
    return adapter.scan(sample_cases.PACK)


def _scanner_answered(_adapter: Any, result: Any) -> bool:
    return bool(result) and all(r.control_id == sample_cases.PACK.control_id for r in result)


def _evidence_invoke(adapter: Any) -> Any:
    return adapter.fetch("AC-2-recert")


def _evidence_answered(_adapter: Any, result: Any) -> bool:
    return bool(result) and all(r.source == "rsk1_evidence_pack" for r in result)


def _writeback_invoke(adapter: Any) -> Any:
    return adapter.append_result(CANONICAL_RESULT, tenant=sample_cases.TENANT)


def _writeback_answered(adapter: Any, result: Any) -> bool:
    nodes = adapter.read_evidence(CANONICAL_RESULT.control_id)
    return (
        bool(result) and len(nodes) == 1 and nodes[0]["control_id"] == CANONICAL_RESULT.control_id
    )


def _timeseries_invoke(adapter: Any) -> Any:
    return adapter.export(CANONICAL_RESULT)


def _timeseries_answered(adapter: Any, result: Any) -> bool:
    return result == 1 and len(adapter.rows) == 1


def _generation_invoke(adapter: Any) -> Any:
    return adapter.generate(CANONICAL_PROMPT)


def _generation_answered(_adapter: Any, result: Any) -> bool:
    # Answered means it produced a narration that is VALID and grounded in the engine's figures.
    return validate_narration(result, CANONICAL_RESULT) is not None


def _tracer_invoke(adapter: Any) -> Any:
    with adapter.span("canonical.unit", action="canonical"):
        adapter.record_token_usage(TokenUsage(input_tokens=7, output_tokens=2), "canonical-model")
    return True


def _tracer_answered(adapter: Any, result: Any) -> bool:
    return bool(result)


def _evaluation_invoke(adapter: Any) -> Any:
    return adapter.evaluate("eval/datasets/canonical.jsonl")


def _evaluation_answered(adapter: Any, result: Any) -> bool:
    return isinstance(result, EvalReport) and result.dataset.endswith("canonical.jsonl")


CANONICAL_CALLS: dict[str, PortCase] = {
    "audit": PortCase(
        invoke=_audit_invoke,
        answered=_audit_answered,
        managed_refusal=(ImportError,),
        detail="write one already-redacted WORM record",
    ),
    "identity": PortCase(
        invoke=_identity_invoke,
        answered=_identity_answered,
        managed_refusal=(IdentityError,),
        detail="resolve a verified principal from transport context",
    ),
    "review_router": PortCase(
        invoke=_review_invoke,
        answered=_review_answered,
        managed_refusal=(RuntimeError,),
        detail="route one escalated result to human review",
    ),
    "control_inventory": PortCase(
        invoke=_inventory_invoke,
        answered=_inventory_answered,
        managed_refusal=(ImportError,),
        detail="read the tenant's controls from the Rgc7 inventory",
    ),
    "evidence_scanner": PortCase(
        invoke=_scanner_invoke,
        answered=_scanner_answered,
        managed_refusal=(ImportError,),
        detail="scan live evidence for the pack's control",
    ),
    "control_evidence": PortCase(
        invoke=_evidence_invoke,
        answered=_evidence_answered,
        managed_refusal=(ImportError,),
        detail="fetch the Rsk1 evidence pack for a control",
    ),
    "writeback": PortCase(
        invoke=_writeback_invoke,
        answered=_writeback_answered,
        managed_refusal=(ImportError,),
        detail="append an effectiveness evidence node to Rgc7",
    ),
    "timeseries": PortCase(
        invoke=_timeseries_invoke,
        answered=_timeseries_answered,
        managed_refusal=(ImportError,),
        detail="export one effectiveness row to the time-series",
    ),
    "generation": PortCase(
        invoke=_generation_invoke,
        answered=_generation_answered,
        managed_refusal=(ImportError,),
        detail="narrate an exception grounded in the engine facts",
    ),
    "tracer": PortCase(
        invoke=_tracer_invoke,
        answered=_tracer_answered,
        # NOTHING. Tracing is not essential to correctness, so the managed adapter must not refuse
        # offline either: with no SDK it degrades to a no-op and the traced body still runs. An
        # adapter that raised here would take a request down over a diagnostic.
        managed_refusal=(),
        detail="open one span and report the cost of a model call",
    ),
    "evaluation": PortCase(
        invoke=_evaluation_invoke,
        answered=_evaluation_answered,
        # The managed gate reaches Hrz4 over HTTP, which is unreachable offline.
        managed_refusal=(Exception,),
        detail="score one golden dataset through the promotion authority",
    ),
}
