"""The A2A discovery card: what this agent can be asked to do, in one machine-readable place.

Served at ``/.well-known/agent-card.json`` and registrable with Hrz3 (rule R4). The card is
built from the SAME tool table the runtime binds, so an agent cannot advertise a skill it does
not implement or implement one it never advertises; ``tests/unit/test_agent_surface.py`` fails
the build when the two disagree.

Pure: domain types and stdlib only, no ADK and no cloud SDK, so the card can be generated and
inspected offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hex_service_kit.serialization import to_jsonable

from ..config import Settings

_CARD_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class AgentSkill:
    """One advertised capability. ``id`` is the tool function's name, never a prose label."""

    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class AgentCard:
    """The minimal A2A discovery document a peer agent or the registry reads."""

    name: str
    description: str
    url: str
    version: str = _CARD_VERSION
    provider: str = "continuous-controls-monitoring"
    skills: tuple[AgentSkill, ...] = field(default_factory=tuple)


SKILLS: tuple[AgentSkill, ...] = (
    AgentSkill(
        id="test_control",
        name="Control test",
        description=(
            "Run one control's test now, by pack id: read the control from the Rgc7 inventory, "
            "gather evidence, and score design and operating effectiveness with pure stdlib "
            "code (never a model). Write the result back to Rgc7, export the time-series row, "
            "and ROUTE a failing control to the owner for human review (rule R8)."
        ),
    ),
    AgentSkill(
        id="run_monitoring",
        name="Monitoring run",
        description=(
            "Run every configured control test for a tenant and summarise the batch: how many "
            "controls passed, how many exceptions were raised and routed, and each control's "
            "cited design and operating effectiveness result."
        ),
    ),
)

#: Joined from short pieces, each carrying at most one template variable, so a longer
#: ``friendly_name`` cannot push a line past the formatter's limit in the rendered repo while
#: the template itself still looks fine. The vertical's own prose belongs in ``README.md``;
#: the card says what the agent IS and what it guarantees.
_DESCRIPTION = " ".join(
    (
        "Continuous Controls Monitoring",
        "(Aud2).",
        "Deterministic decision, cited output, redact-before-audit, and every",
        "consequential result routed to a human reviewer.",
    )
)


def build_agent_card(settings: Settings | None = None) -> AgentCard:
    """Construct the A2A card for this agent in the configured deployment."""
    resolved = settings or Settings.load()
    return AgentCard(
        name="continuous-controls-monitoring",
        description=_DESCRIPTION,
        url=_resolve_url(resolved),
        skills=SKILLS,
    )


def agent_card_document(settings: Settings | None = None) -> dict[str, Any]:
    """The JSON-safe body served at ``/.well-known/agent-card.json``."""
    document = to_jsonable(build_agent_card(settings))
    if not isinstance(document, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("an agent card must serialise to a JSON object")
    return document


def _resolve_url(settings: Settings) -> str:
    """Best-effort public URL for the card, region-qualified so residency is visible on it."""
    return f"https://continuous-controls-monitoring.{settings.region}.internal.example/a2a"
