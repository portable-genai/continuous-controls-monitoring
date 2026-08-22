"""On-prem EvidenceScannerPort: fail-fast placeholder (bind the client's own asset/SIEM feeds)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ControlTestPack, EvidenceRecord


class OnPremEvidenceScanner:
    """Satisfies EvidenceScannerPort but refuses at call time: wire the client's own feeds."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def scan(self, pack: ControlTestPack) -> tuple[EvidenceRecord, ...]:
        raise NotImplementedError(
            "on-prem evidence scanner is a portability placeholder: bind the client's own asset "
            "and configuration feeds (see docs/onprem-migration.md)"
        )
