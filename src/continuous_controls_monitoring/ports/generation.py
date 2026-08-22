"""GenerationPort: the model boundary for exception narration (narrate only, never decide).

The model turns engine facts into prose; it never produces a number or a verdict. The port
returns RAW text, which the caller validates against a schema and a groundedness check
(``domain/narration.py``) and DISCARDS on failure. Keeping the port this thin means the
consequential decision can never leak into the adapter.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GenerationPort(Protocol):
    def generate(self, prompt: str) -> str:
        """Return the model's raw response to ``prompt`` (expected to be strict JSON).

        The caller validates and may discard it; the port makes no promise the output is
        well-formed, only that it is what the model returned.
        """
        ...
