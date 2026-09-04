"""Local EffectivenessWritebackPort: an in-memory obligations-control-mapping graph stand-in that
actually records.

Appends a result as an evidence node linked to the tested control, exactly as the managed adapter
appends it to obligations-control-mapping's graph, and refuses a write-back naming a control the
inventory does not contain. It is deliberately not a no-op: a silent local writer would let the gate
pass while the write-back path proved nothing, so this one stores what it was given and exposes it
for the "a written result is readable back, attached to the control" assertion.
"""

from __future__ import annotations

from typing import Any

from ...config import Settings
from ...domain.models import ControlTestResult
from ...ports.writeback import UnknownControlError
from . import _fixtures

#: The known control ids, across every tenant: a write-back to anything else is rejected, never
#: silently created, so continuous-controls-monitoring cannot mint a control by writing an evidence
#: node to it.
_KNOWN_CONTROL_IDS = frozenset(
    control_id for controls in _fixtures.CONTROLS.values() for control_id in controls
)


class LocalEffectivenessWriteback:
    """Record effectiveness evidence nodes in memory, keyed by control, for the local profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graph: dict[str, list[dict[str, Any]]] = {}

    def append_result(self, result: ControlTestResult, *, tenant: str = "") -> str:
        if result.control_id not in _KNOWN_CONTROL_IDS:
            raise UnknownControlError(
                f"write-back names control {result.control_id!r}, which is not in the "
                f"obligations-control-mapping "
                "inventory; effectiveness evidence is only ever attached to a known control"
            )
        node = {
            "control_id": result.control_id,
            "pack_id": result.pack_id,
            "as_of": result.as_of.isoformat(),
            "passed": result.passed,
            "design": result.design.rating.value,
            "operating": result.operating.rating.value,
            "findings": len(result.findings),
            "tenant": tenant or self._settings.tenant,
        }
        appended = self._graph.setdefault(result.control_id, [])
        appended.append(node)
        return f"rgc7-evidence:{result.control_id}:{len(appended)}"

    def read_evidence(self, control_id: str) -> tuple[dict[str, Any], ...]:
        """The evidence nodes appended to ``control_id`` (for tests, the demo and inspection)."""
        return tuple(self._graph.get(control_id, ()))
