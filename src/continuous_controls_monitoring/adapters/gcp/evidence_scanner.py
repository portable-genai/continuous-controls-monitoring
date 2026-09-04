"""Managed EvidenceScannerPort: Cloud Asset Inventory + Security Command Center evidence.

Mirrors architecture-validator's ``adapters/gcp/cloud_asset_scanner.py``: the config-scan and
threshold evidence come from Cloud Asset Inventory and Security Command Center. The SDK imports are
lazy (inside :meth:`scan`), so the offline profiles construct this adapter with no cloud SDK
present.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ControlTestPack, EvidenceRecord, TestKind


class CloudEvidenceScanner:
    """Gather live config / transaction / threshold evidence under the managed profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def scan(self, pack: ControlTestPack) -> tuple[EvidenceRecord, ...]:
        # Lazy: Cloud Asset Inventory for config scans, Security Command Center for thresholds.
        if pack.test_kind is TestKind.THRESHOLD:
            from google.cloud import securitycenter_v1

            # Distinct names, because these are different clients. Reusing one name bound
            # its type to whichever branch came first, so the second assignment was a type
            # error that only a checker able to SEE the SDK could report.
            scc_client = securitycenter_v1.SecurityCenterClient()
            return _from_scc(scc_client, pack)  # pragma: no cover - needs live SCC
        from google.cloud import asset_v1

        asset_client = asset_v1.AssetServiceClient()
        return _from_asset_inventory(asset_client, pack)  # pragma: no cover - needs live CAI


def _from_asset_inventory(
    client: object, pack: ControlTestPack
) -> tuple[EvidenceRecord, ...]:  # pragma: no cover - needs live Cloud Asset Inventory
    raise NotImplementedError(
        "wire the Cloud Asset Inventory query for "
        f"{pack.control_id} (see docs/runbook.md); the offline profile uses fixture snapshots"
    )


def _from_scc(
    client: object, pack: ControlTestPack
) -> tuple[EvidenceRecord, ...]:  # pragma: no cover - needs live Security Command Center
    raise NotImplementedError(
        "wire the Security Command Center query for "
        f"{pack.control_id} (see docs/runbook.md); the offline profile uses fixture snapshots"
    )
