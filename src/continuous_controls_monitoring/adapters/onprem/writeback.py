"""On-prem EffectivenessWritebackPort: fail-fast placeholder (bind the client's own
obligations-control-mapping).
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ControlTestResult


class OnPremEffectivenessWriteback:
    """Satisfies the write-back port but refuses at call time: wire the client's own
    obligations-control-mapping.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def append_result(self, result: ControlTestResult, *, tenant: str = "") -> str:
        raise NotImplementedError(
            "on-prem effectiveness write-back is a portability placeholder: bind the client's "
            "own obligations-control-mapping write-back endpoint (see docs/onprem-migration.md)"
        )
