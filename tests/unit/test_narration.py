"""The model-narration boundary: grounded output is accepted, ungrounded output is discarded.

The model never produces a figure. This suite proves the validator keeps it that way: a
narration that only restates the engine's figures validates, and one that introduces a figure
the engine did not produce is DISCARDED, whatever else is right about it. That is the
groundedness oracle the eval's metric drives, and it is proved able to go red here.
"""

from __future__ import annotations

import json

from continuous_controls_monitoring.domain.narration import (
    build_prompt,
    is_grounded,
    narration_facts,
    validate_narration,
)

from tests.fixtures import sample_cases

_RESULT = sample_cases.ESCALATING_RESULT


def test_a_grounded_narration_is_accepted() -> None:
    facts = narration_facts(_RESULT)
    # Use a figure the engine actually produced, so the narration is grounded.
    a_real_figure = next(iter(facts))
    raw = json.dumps(
        {"headline": "Egress control failed", "body": f"One drift; score {a_real_figure}."}
    )
    narration = validate_narration(raw, _RESULT)
    assert narration is not None
    assert narration.headline


def test_an_ungrounded_figure_is_discarded() -> None:
    """A number the engine never produced is a fabrication; the whole narration is discarded."""
    raw = json.dumps({"headline": "Egress control failed", "body": "There were 4242 breaches."})
    assert "4242" not in narration_facts(_RESULT)
    assert validate_narration(raw, _RESULT) is None


def test_malformed_json_is_discarded() -> None:
    assert validate_narration("not json at all", _RESULT) is None
    assert validate_narration(json.dumps(["a", "list"]), _RESULT) is None
    assert validate_narration(json.dumps({"headline": "x"}), _RESULT) is None


def test_the_prompt_carries_the_facts_and_forbids_new_figures() -> None:
    prompt = build_prompt(_RESULT)
    assert "FACTS (do not add to these):" in prompt
    assert _RESULT.control_id in prompt
    assert "Do not introduce any number" in prompt


def test_is_grounded_rejects_a_single_fabricated_number() -> None:
    assert is_grounded("design and operating deficiencies", _RESULT)
    assert not is_grounded("exactly 9999 findings", _RESULT)
