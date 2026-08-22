"""EffectivenessWritebackPort: WRITE Aud2 results back to Rgc7 as evidence nodes.

The write-back side of the control-triad boundary. A result is appended to Rgc7's graph as an
evidence node LINKED to the tested control; it never mutates control-catalog membership. A
write-back naming a control id Rgc7 does not know is REJECTED (:class:`UnknownControlError`),
never silently created, so Aud2 cannot invent a control by writing to it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ControlTestResult


class UnknownControlError(ValueError):
    """Raised when a write-back names a control id the inventory does not contain."""


@runtime_checkable
class EffectivenessWritebackPort(Protocol):
    def append_result(self, result: ControlTestResult, *, tenant: str = "") -> str:
        """Append ``result`` as an evidence node linked to its control; return the node ref.

        Raises :class:`UnknownControlError` when ``result.control_id`` is not in the inventory.
        The returned reference is never empty, so a caller can record where the evidence landed.
        """
        ...
