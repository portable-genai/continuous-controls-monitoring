"""On-prem ControlEvidencePort: fail-fast placeholder (bind the client's own compliance-advisory
evidence).
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import EvidenceRecord


class OnPremControlEvidence:
    """Satisfies ControlEvidencePort but refuses at call time: wire the client's own evidence."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, control_id: str) -> tuple[EvidenceRecord, ...]:
        raise NotImplementedError(
            "on-prem control evidence is a portability placeholder: bind the client's own "
            "compliance-advisory "
            "evidence-pack surface (see docs/onprem-migration.md)"
        )
