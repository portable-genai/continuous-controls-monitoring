"""On-prem TimeSeriesExportPort: fail-fast placeholder (bind the client's own warehouse)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ControlTestResult


class OnPremTimeSeriesExport:
    """Satisfies TimeSeriesExportPort but refuses at call time: wire the client's warehouse."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def export(self, result: ControlTestResult) -> int:
        raise NotImplementedError(
            "on-prem time-series export is a portability placeholder: bind the client's own "
            "data warehouse (see docs/onprem-migration.md)"
        )
