"""ControlEvidencePort: READ compliance-advisory's cloud control evidence packs (the formerly the
cloud control-mapping toolkit module).

The continuous-controls-monitoring CSV row mandates reading compliance-advisory's cloud control
evidence as one more evidence kind beside the scanners. This port is the seam: a remote adapter over
compliance-advisory's evidence-pack surface under the managed profile, canned packs offline,
fail-fast on-prem. The engine consumes the returned :class:`EvidenceRecord` items exactly as it
consumes scanner output, so a control can be graded on scanner evidence, compliance-advisory
evidence, or both.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import EvidenceRecord


@runtime_checkable
class ControlEvidencePort(Protocol):
    def fetch(self, control_id: str) -> tuple[EvidenceRecord, ...]:
        """Return the compliance-advisory evidence-pack records for ``control_id`` (empty when
        compliance-advisory has none).
        """
        ...
