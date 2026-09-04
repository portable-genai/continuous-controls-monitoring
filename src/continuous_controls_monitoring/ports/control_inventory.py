"""ControlInventoryPort: READ the obligations-control-mapping control inventory. This repo keeps no
parallel catalog.

Per the control-triad boundary, obligations-control-mapping is the single system of record for the
obligation to policy to control to evidence graph. continuous-controls-monitoring reads the control
inventory and writes effectiveness results back; it never stores control-catalog membership of its
own. This port is the read side; ``ports/writeback.py`` is the write-back side.

Cross-tenant authorisation is the port's, not a caller's: :meth:`get_control` returns ``None``
for a control that does not exist, but raises :class:`CrossTenantError` (a 403, never a 404) for
a control that exists under a DIFFERENT tenant, so a probe cannot use the 404/403 difference to
enumerate another tenant's controls.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import InventoryControl


class CrossTenantError(PermissionError):
    """Raised when a principal asks for a control owned by another tenant (403, not 404)."""

    http_status = 403


@runtime_checkable
class ControlInventoryPort(Protocol):
    def list_controls(self, tenant: str) -> tuple[InventoryControl, ...]:
        """Every control in ``tenant``'s inventory (empty tuple when the tenant has none)."""
        ...

    def get_control(self, control_id: str, *, tenant: str) -> InventoryControl | None:
        """One control by id within ``tenant``.

        Returns ``None`` when no such control exists anywhere; raises
        :class:`CrossTenantError` when it exists under a different tenant.
        """
        ...
