"""Tool functions an agent runtime calls: thin, side-effect-honest wrappers on the service.

Design rules, in the order they matter:

* **No business logic here.** The domain engine decides the effectiveness verdict; the model
  only decides WHICH tool to call. A rule that lives in a tool wrapper is a rule the CLI and the
  API do not have.
* **Rule R8 applies on this path too.** An exception is ROUTED from inside the service, in the
  same call that produced it, so an agent surface cannot be a third place an escalation stops.
* **Import-safe without a runtime.** ``google.adk`` is imported lazily inside
  :func:`build_function_tools`, so these callables are importable, testable and runnable with no
  ADK and no cloud SDK installed.
* **Typed and documented.** A runtime derives each tool's name, description and JSON parameter
  schema from the signature and the docstring, so both are part of the contract.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from hex_service_kit.serialization import to_jsonable
from pii_kit import redact

from ..config import Container, Settings, build_container
from ..domain.models import MonitoredControl
from ..domain.monitoring_service import MonitoringService
from ..domain.pii import PII_PATTERNS

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

#: The identity a tool call is attributed to when the runtime propagates none. It names the
#: SERVICE, not a person, so an unattributed action is never mistaken for a human's.
DEFAULT_ACTOR = "continuous-controls-monitoring-agent"


def _service(settings: Settings | None) -> MonitoringService:
    container: Container = build_container(settings)
    return MonitoringService(
        audit=container.audit,
        inventory=container.control_inventory,
        scanner=container.evidence_scanner,
        control_evidence=container.control_evidence,
        writeback=container.writeback,
        timeseries=container.timeseries,
        generation=container.generation,
        review_router=container.review_router,
        tracer=container.tracer,
        policy=container.settings.policy,
    )


def _redacted(node: Any) -> Any:
    """Mask personal data in every string of a tool result, however deeply it is nested.

    A tool result goes into a model's context, and P-04 says minimise the data that reaches a
    model. Walking the whole structure rather than named fields means a future field cannot
    arrive unredacted just because nobody remembered to add it.
    """
    if isinstance(node, str):
        return redact(node, PII_PATTERNS)
    if isinstance(node, dict):
        return {key: _redacted(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_redacted(value) for value in node]
    return node


def _payload(monitored: MonitoredControl) -> dict[str, Any]:
    payload = _redacted(to_jsonable(monitored))
    if not isinstance(payload, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("a control-test result must serialise to a JSON object")
    return payload


def test_control(
    pack_id: str,
    actor: str = DEFAULT_ACTOR,
    tenant: str = "demo-bank",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run one control's test now, by pack id, and route it for human review if it fails.

    The engine scores design and operating effectiveness deterministically, the result is
    written back to Rgc7 and exported to the time-series, and a FAIL is routed to the control
    owner via the human-review console (rule R8).

    Args:
      pack_id: The control-test pack to run.
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition whose inventory is read and whose reviews are asserted.

    Returns:
      A JSON-safe result dict with every string masked for personal data (P-04), including
      ``review_ref`` (where a FAIL was routed) and ``writeback_ref`` (where the evidence landed).
    """
    service = _service(settings)
    pack = next((p for p in service.packs if p.pack_id == pack_id), None)
    if pack is None:
        raise ValueError(f"unknown pack_id: {pack_id}")
    monitored = service.evaluate_pack(pack, as_of=date.today(), tenant=tenant, actor=actor)
    return _payload(monitored)


def run_monitoring(
    actor: str = DEFAULT_ACTOR,
    tenant: str = "demo-bank",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run every configured control test for a tenant and summarise the batch.

    Args:
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition whose controls are tested.

    Returns:
      A JSON-safe summary with the pass count, the exception count, and each control's result,
      every string masked for personal data (P-04).
    """
    service = _service(settings)
    run = service.run(as_of=date.today(), tenant=tenant, actor=actor)
    summary = {
        "as_of": run.as_of.isoformat(),
        "passed": run.passed_count,
        "exceptions": len(run.exceptions),
        "results": [_payload(m) for m in run.monitored],
    }
    masked = _redacted(summary)
    if not isinstance(masked, dict):  # pragma: no cover - dict in, dict out
        raise TypeError("a monitoring run must serialise to a JSON object")
    return masked


#: The tool table. The agent card advertises exactly these, by function name.
TOOL_FUNCTIONS = (test_control, run_monitoring)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each callable as a runtime FunctionTool (the only ADK-dependent code path)."""
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=function) for function in TOOL_FUNCTIONS]
