"""Local GenerationPort: a deterministic, grounded narrator for the SDK-free profile.

No model call. It restates the FACTS block the prompt carries, so every figure in its output is
one the engine already produced and the groundedness check passes offline. This is not a fake
that dodges the validation: it exercises the real narration path (schema-validated, discarded on
failure) with a narrator that cannot hallucinate a figure, which is exactly what the offline
gate needs.
"""

from __future__ import annotations

import json
import re

from ...config import Settings

_FACTS_MARKER = "FACTS (do not add to these):"
_CONTROL = re.compile(r"- control: (.+)")
_VERDICT = re.compile(r"- verdict: (\w+)")


class LocalNarrationGenerator:
    """Restate the engine's own facts as strict JSON. Grounded by construction."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, prompt: str) -> str:
        control_match = _CONTROL.search(prompt)
        verdict_match = _VERDICT.search(prompt)
        control = control_match.group(1).strip() if control_match else "the control"
        verdict = verdict_match.group(1).strip() if verdict_match else "reviewed"
        _, _, facts = prompt.partition(_FACTS_MARKER)
        body = re.sub(r"\s+", " ", facts).strip() or "See the engine result."
        headline = f"{control} control test {verdict}"
        return json.dumps({"headline": headline, "body": body})
