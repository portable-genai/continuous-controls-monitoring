"""Managed TimeSeriesExportPort: append an effectiveness row to BigQuery (SDK imported lazily).

The BigQuery client import is the first thing :meth:`export` does, so the offline profiles bind
this adapter with no cloud SDK present. The Looker view over the table stays outside the gate.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ControlTestResult

_TABLE = "effectiveness_timeseries"


class BigQueryTimeSeriesExport:
    """Stream effectiveness rows into BigQuery under the managed profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def export(self, result: ControlTestResult) -> int:
        from google.cloud import bigquery

        client = bigquery.Client()
        table = f"{self._settings.bigquery_dataset}.{_TABLE}"
        rows = [
            {
                "control_id": result.control_id,
                "pack_id": result.pack_id,
                "as_of": result.as_of.isoformat(),
                "design_score": result.design.score,
                "operating_score": result.operating.score,
                "passed": result.passed,
            }
        ]
        errors = client.insert_rows_json(table, rows)  # pragma: no cover - needs live BigQuery
        if errors:  # pragma: no cover - needs live BigQuery
            raise RuntimeError(f"BigQuery rejected the effectiveness row: {errors}")
        return len(rows)  # pragma: no cover - needs live BigQuery
