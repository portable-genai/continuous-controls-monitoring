"""The runtime-control seam: what switched-off routing binds, and what a caller reports.

**Disabled adapter.** When a deployment switches review routing off
(``CCM_REVIEW_ROUTING=off``), the container binds :class:`DisabledReviewRouter` instead
of the profile's class. It satisfies the port and submits nothing, and the container logs the
posture at startup.

**Recording wrapper.** The domain service routes each failed control test itself, so every
caller (the two API routes, the two agent tools, the two CLI commands) builds its service
around a :class:`RecordingReviewRouter` for that one call, and what it returns can say what
happened to each pack's hand-off: ``routed``, ``failed``, ``off`` or ``not_required``. A
failure is logged and absorbed here rather than failing an already-graded, already-audited
control test, but it is never invisible: the caller reports ``failed`` and an empty reference,
which nobody can mistake for a reviewed result.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from ..config import Settings
from ..domain.models import ControlTestResult

_log = logging.getLogger(__name__)


class ReviewRouting(StrEnum):
    """What happened to the human-review hand-off for one result."""

    ROUTED = "routed"
    FAILED = "failed"
    OFF = "off"
    NOT_REQUIRED = "not_required"


class DisabledReviewRouter:
    """ReviewRouterPort with routing switched off: nothing is submitted anywhere."""

    enabled = False

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def route(self, result: ControlTestResult, *, maker: str, tenant: str = "") -> str:
        return ""


class RecordingReviewRouter:
    """Wraps the bound review router for one caller and records each hand-off's outcome."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        #: One outcome per pack: a run hands off several results, and each is reported on its own.
        self._outcomes: dict[str, ReviewRouting] = {}

    def route(self, result: ControlTestResult, *, maker: str, tenant: str = "") -> str:
        """Hand ``result`` off if it requires review; return the reference, empty if none."""
        if not result.requires_human_review:
            return ""
        if not getattr(self._inner, "enabled", True):
            self._outcomes[result.pack_id] = ReviewRouting.OFF
            return ""
        try:
            reference = self._inner.route(result, maker=maker, tenant=tenant)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - the outcome is reported, never raised
            _log.warning("human-review hand-off failed: %s", type(exc).__name__)
            self._outcomes[result.pack_id] = ReviewRouting.FAILED
            return ""
        self._outcomes[result.pack_id] = ReviewRouting.ROUTED
        return str(reference)

    def outcome_for(self, pack_id: str) -> ReviewRouting:
        """What happened to one pack's hand-off; ``not_required`` when it was never handed off."""
        return self._outcomes.get(pack_id, ReviewRouting.NOT_REQUIRED)

    @property
    def outcome(self) -> ReviewRouting:
        """One value for the whole call: any failure wins, then off, then routed."""
        for worst in (ReviewRouting.FAILED, ReviewRouting.OFF, ReviewRouting.ROUTED):
            if worst in self._outcomes.values():
                return worst
        return ReviewRouting.NOT_REQUIRED
