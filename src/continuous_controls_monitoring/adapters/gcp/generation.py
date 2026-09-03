"""Managed GenerationPort: narrate exceptions with Gemini (SDK imported lazily).

The import lives inside :meth:`generate`, so the module is importable and constructible with no
cloud SDK present (the offline profiles bind it too). The import root is ``google.*``, which the
repo's mypy override already covers. The model narrates only; the caller validates the output
against a schema and a groundedness check and discards it on failure, so a model that
hallucinates a figure changes nothing consequential.

The SDK is ``google-genai``, the unified Google GenAI SDK. It replaced ``google-generativeai``,
which is RETIRED; this module used the retired one until 2026-08-31 and the migration was not a
pin bump, because the call shape differs: a stateful ``GenerativeModel`` holding the system
instruction became a client plus a per-call ``GenerateContentConfig`` that carries it. The client
is constructed with no arguments on purpose, which is what the retired SDK also did: credentials
and backend come from the environment, so a deployment can send this at either the Gemini
Developer API or Vertex (``GOOGLE_GENAI_USE_VERTEXAI``) without a code change here.
"""

from __future__ import annotations

from ...config import Settings

_MODEL = "gemini-3.5-flash"
_SYSTEM = "You restate control-test facts as JSON. You never introduce a figure not given."


class VertexNarrationGenerator:
    """Draft exception narration via Gemini under the managed profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, prompt: str) -> str:
        # Lazy: the SDK import is the first thing the method does, so an offline caller gets an
        # ImportError here rather than at construction (which every profile performs).
        from google import genai
        from google.genai import types

        client = genai.Client()
        response = client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=_SYSTEM),
        )
        return str(response.text)
