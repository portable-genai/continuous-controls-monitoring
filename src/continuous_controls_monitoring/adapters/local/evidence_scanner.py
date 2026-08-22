"""Local EvidenceScannerPort: deterministic fixture snapshots of config/txn/threshold evidence.

The offline stand-in for Cloud Asset Inventory, Security Command Center and the transaction
sampler. It returns the canned evidence for the pack's control and never fabricates a record to
avoid an empty result: a control with no snapshot returns nothing, and the engine treats that as
a deficiency.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ControlTestPack, EvidenceRecord
from . import _fixtures


class LocalEvidenceScanner:
    """Serve fixture evidence snapshots for the SDK-free profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def scan(self, pack: ControlTestPack) -> tuple[EvidenceRecord, ...]:
        return _fixtures.SCANNER_EVIDENCE.get(pack.control_id, ())
