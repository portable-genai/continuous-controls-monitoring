"""ControlEvidencePort: READ Rsk1's cloud control evidence packs (the ex-Rsk2 module).

The Aud2 CSV row mandates reading Rsk1's cloud control evidence as one more evidence kind beside
the scanners. This port is the seam: a remote adapter over Rsk1's evidence-pack surface under
the managed profile, canned packs offline, fail-fast on-prem. The engine consumes the returned
:class:`EvidenceRecord` items exactly as it consumes scanner output, so a control can be graded
on scanner evidence, Rsk1 evidence, or both.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import EvidenceRecord


@runtime_checkable
class ControlEvidencePort(Protocol):
    def fetch(self, control_id: str) -> tuple[EvidenceRecord, ...]:
        """Return the Rsk1 evidence-pack records for ``control_id`` (empty when Rsk1 has none)."""
        ...
