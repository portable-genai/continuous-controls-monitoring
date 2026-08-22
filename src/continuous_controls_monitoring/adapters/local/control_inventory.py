"""Local ControlInventoryPort: the offline copy of a read of Rgc7's control inventory.

Serves the shared synthetic estate in ``_fixtures.py``. Cross-tenant reads are refused the same
way the managed adapter must refuse them: a control that exists under another tenant raises
:class:`CrossTenantError` (403), while a wholly unknown id returns ``None`` (404), so the
offline gate proves the authorisation rule rather than assuming it.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import InventoryControl
from ...ports.control_inventory import CrossTenantError
from . import _fixtures


class LocalControlInventory:
    """Read controls from the deterministic offline estate, tenant-scoped."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_controls(self, tenant: str) -> tuple[InventoryControl, ...]:
        return tuple(_fixtures.CONTROLS.get(tenant, {}).values())

    def get_control(self, control_id: str, *, tenant: str) -> InventoryControl | None:
        own = _fixtures.CONTROLS.get(tenant, {})
        if control_id in own:
            return own[control_id]
        # Exists, but under another tenant: 403, never 404, so the difference cannot be used to
        # enumerate another tenant's controls.
        for other_tenant, controls in _fixtures.CONTROLS.items():
            if other_tenant != tenant and control_id in controls:
                raise CrossTenantError(f"control {control_id!r} is not in tenant {tenant!r}")
        return None
