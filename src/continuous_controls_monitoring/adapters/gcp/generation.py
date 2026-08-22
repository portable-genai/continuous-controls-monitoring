"""Managed GenerationPort: narrate exceptions with Gemini (SDK imported lazily).

The import lives inside :meth:`generate`, so the module is importable and constructible with no
cloud SDK present (the offline profiles bind it too). The import root is ``google.*``, which the
repo's mypy override already covers. The model narrates only; the caller validates the output
against a schema and a groundedness check and discards it on failure, so a model that
hallucinates a figure changes nothing consequential.
"""

from __future__ import annotations

from ...config import Settings

_MODEL = "gemini-2.5-flash"
_SYSTEM = "You restate control-test facts as JSON. You never introduce a figure not given."


class VertexNarrationGenerator:
    """Draft exception narration via Gemini under the managed profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, prompt: str) -> str:
        # Lazy: the SDK import is the first thing the method does, so an offline caller gets an
        # ImportError here rather than at construction (which every profile performs).
        import google.generativeai as genai

        model = genai.GenerativeModel(_MODEL, system_instruction=_SYSTEM)
        response = model.generate_content(prompt)
        return str(response.text)
