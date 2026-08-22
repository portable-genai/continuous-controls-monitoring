"""The model-narration boundary: draft an exception write-up, validate it, discard on failure.

The LLM NEVER produces a number or a verdict. The engine has already decided design and
operating effectiveness, the findings and the pass/fail; narration only turns those facts into
an auditor-ready paragraph. This module owns three pure functions:

* :func:`narration_facts` extracts the figures the engine produced (the grounding set);
* :func:`build_prompt` assembles the instruction plus those facts (data kept separate from
  instruction, so retrieved/So-far text cannot escalate the model's authority);
* :func:`validate_narration` parses the model's JSON, checks it against the declared schema, and
  rejects it if it introduces any figure not in the grounding set.

A narration that fails validation is DISCARDED (the caller falls back to the engine summary),
never passed through. Groundedness is the load-bearing check: a figure in the prose that the
engine did not compute is a fabrication, and the metric that scores it must be able to go red.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .models import ControlTestResult

#: A number token: integers and decimals. Percent signs and separators are stripped first.
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True, slots=True)
class ExceptionNarration:
    """The validated narration: a headline and a grounded body, both safe to show."""

    headline: str
    body: str


def narration_facts(result: ControlTestResult) -> frozenset[str]:
    """The set of figure tokens the engine produced, against which the model is grounded.

    Numbers only: the control id and rating words are strings the model may freely restate. A
    FIGURE it introduces that is not here is ungrounded, and that is what the groundedness check
    and its metric reject.
    """
    tokens: set[str] = set()
    for text in (
        str(result.evidence_count),
        str(result.design.score),
        str(result.operating.score),
        str(result.design.finding_count),
        str(result.operating.finding_count),
        str(len(result.findings)),
        # Identifiers the engine produced are restatable: a digit inside a control id (SC-7) or a
        # pack id is not a fabricated figure, so those digits are grounded too.
        result.control_id,
        result.pack_id,
        result.test_kind.value,
    ):
        tokens.update(_NUMBER.findall(text))
    for finding in result.findings:
        tokens.update(_NUMBER.findall(finding.detail))
        tokens.update(_NUMBER.findall(finding.rule_id))
    return frozenset(tokens)


def build_prompt(result: ControlTestResult) -> str:
    """Assemble the narration instruction plus the engine facts, data kept separate.

    The model is told, in the instruction, that it may not introduce a figure. The facts follow
    under a labelled block so the boundary between instruction and data is explicit.
    """
    lines = [
        "You are drafting an auditor-ready control-test exception write-up.",
        "Restate ONLY the facts below. Do not introduce any number, percentage or date that is",
        'not already present. Return STRICT JSON: {"headline": str, "body": str}.',
        "",
        "FACTS (do not add to these):",
        f"- control: {result.control_id}",
        f"- pack: {result.pack_id}",
        f"- test kind: {result.test_kind.value}",
        f"- verdict: {'PASS' if result.passed else 'FAIL'}",
        f"- design rating: {result.design.rating.value} (score {result.design.score})",
        f"- operating rating: {result.operating.rating.value} (score {result.operating.score})",
        f"- evidence records tested: {result.evidence_count}",
        f"- findings: {len(result.findings)}",
    ]
    for finding in result.findings:
        lines.append(f"  * [{finding.severity.value}] {finding.detail}")
    return "\n".join(lines)


def validate_narration(raw: str, result: ControlTestResult) -> ExceptionNarration | None:
    """Parse and validate the model's output; return ``None`` (discard) on any failure.

    Failure modes, all of which DISCARD rather than pass through:

    * not JSON, or not a JSON object;
    * missing or non-string ``headline`` / ``body``;
    * a figure in the prose that the engine did not produce (ungrounded).
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    headline = parsed.get("headline")
    body = parsed.get("body")
    if not isinstance(headline, str) or not isinstance(body, str):
        return None
    if not headline.strip() or not body.strip():
        return None
    if not is_grounded(f"{headline} {body}", result):
        return None
    return ExceptionNarration(headline=headline.strip(), body=body.strip())


def is_grounded(text: str, result: ControlTestResult) -> bool:
    """True iff every number in ``text`` is a figure the engine produced.

    An independent groundedness oracle: it does not trust the model, it checks the model's
    output against the engine's own facts. A single fabricated figure makes it False.
    """
    facts = narration_facts(result)
    return all(token in facts for token in _NUMBER.findall(text))
