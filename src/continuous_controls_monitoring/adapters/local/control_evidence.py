"""Local ControlEvidencePort: canned Rsk1 cloud control evidence packs (the ex-Rsk2 surface).

Returns the offline Rsk1 evidence for a control. The access-recertification control's evidence
lives only here, so a test that swaps this adapter for one returning nothing flips that control
from pass to fail, which is the slice proof that the Rsk1 source is a real dependency and not
decoration.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import EvidenceRecord
from . import _fixtures


class LocalControlEvidence:
    """Serve canned Rsk1 evidence packs for the SDK-free profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, control_id: str) -> tuple[EvidenceRecord, ...]:
        return _fixtures.RSK1_EVIDENCE.get(control_id, ())
