"""Local TimeSeriesExportPort: an in-memory effectiveness time-series that actually records.

The offline stand-in for the BigQuery effectiveness table the Looker view reads. It stores one
row per result and exposes them, so the export path is exercised by the gate rather than being a
no-op that proves nothing.
"""

from __future__ import annotations

from typing import Any

from ...config import Settings
from ...domain.models import ControlTestResult


class LocalTimeSeriesExport:
    """Append effectiveness rows in memory for the SDK-free profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._rows: list[dict[str, Any]] = []

    def export(self, result: ControlTestResult) -> int:
        self._rows.append(
            {
                "control_id": result.control_id,
                "pack_id": result.pack_id,
                "as_of": result.as_of.isoformat(),
                "design_score": result.design.score,
                "operating_score": result.operating.score,
                "passed": result.passed,
            }
        )
        return 1

    @property
    def rows(self) -> tuple[dict[str, Any], ...]:
        """The exported rows (for tests, the demo and inspection)."""
        return tuple(self._rows)
