"""TimeSeriesExportPort: append a result to the effectiveness time-series (BigQuery under gcp).

Continuous monitoring is a trend, not a snapshot, so every result is also exported to a
time-series store the Looker effectiveness view reads. Under the managed profile this is
BigQuery; offline it is an in-memory sink that actually records (so the gate exercises the path,
not a no-op); on-prem it fail-fasts. The Looker view itself stays outside the gate.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ControlTestResult


@runtime_checkable
class TimeSeriesExportPort(Protocol):
    def export(self, result: ControlTestResult) -> int:
        """Append one effectiveness row for ``result``; return the number of rows written (1)."""
        ...
