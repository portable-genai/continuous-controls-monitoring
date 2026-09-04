"""On-prem ControlInventoryPort: fail-fast placeholder (bind the client's own
obligations-control-mapping read API).
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import InventoryControl


class OnPremControlInventory:
    """Satisfies ControlInventoryPort but refuses at call time: wire the client's inventory."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_controls(self, tenant: str) -> tuple[InventoryControl, ...]:
        raise NotImplementedError(
            "on-prem control inventory is a portability placeholder: bind the client's own "
            "obligations-control-mapping "
            "read API (see docs/onprem-migration.md)"
        )

    def get_control(self, control_id: str, *, tenant: str) -> InventoryControl | None:
        raise NotImplementedError(
            "on-prem control inventory is a portability placeholder: bind the client's own "
            "obligations-control-mapping "
            "read API (see docs/onprem-migration.md)"
        )
