"""EvidenceScannerPort: gather live config/access/transaction evidence for a control test.

Under the managed profile this is Cloud Asset Inventory and Security Command Center; offline it
is deterministic fixture snapshots; on-prem it fail-fasts. The scanner returns already
normalised :class:`EvidenceRecord` items, so the pure engine in ``testing.py`` reasons over one
evidence shape whatever produced it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ControlTestPack, EvidenceRecord


@runtime_checkable
class EvidenceScannerPort(Protocol):
    def scan(self, pack: ControlTestPack) -> tuple[EvidenceRecord, ...]:
        """Return the evidence records for ``pack``'s control (empty when nothing was found).

        An empty return is not an error: the engine treats no evidence as a deficiency, so the
        scanner never fabricates a record to avoid one.
        """
        ...
