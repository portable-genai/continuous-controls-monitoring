"""On-prem GenerationPort: fail-fast portability placeholder (bind the client's own model)."""

from __future__ import annotations

from ...config import Settings


class OnPremNarrationGenerator:
    """Satisfies GenerationPort but refuses at call time: wire the client's own model gateway."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, prompt: str) -> str:
        raise NotImplementedError(
            "on-prem narration model is a portability placeholder: bind the client's own model "
            "gateway (see docs/onprem-migration.md)"
        )
