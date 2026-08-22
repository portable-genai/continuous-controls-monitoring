"""The agent surface is real, import-safe and cannot drift from the card it publishes.

Three failures this suite exists to prevent, all of which a scaffolded surface invites:

1. **A card that lies.** A skill advertised with no tool behind it, or a tool nobody can
   discover. The set equality below is the standing gate.
2. **A third place an escalation stops.** The API and the CLI both route an exception to human
   review. If the agent path only returned the flag, rule R8 would hold on two surfaces out of
   three, which is the same as not holding.
3. **A surface that quietly needs a runtime.** The tools must import and run with no ADK and no
   cloud SDK, or the offline gate stops being offline the day somebody calls one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from continuous_controls_monitoring.agent import (
    SKILLS,
    TOOL_FUNCTIONS,
    agent_card_document,
    build_agent_card,
    run_monitoring,
)
from continuous_controls_monitoring.agent import (
    test_control as run_control_test,  # aliased: a bare test_* name is collected by pytest
)

from tests.conftest import local_settings
from tests.fixtures import sample_cases


def test_the_card_advertises_exactly_the_tools_the_runtime_binds() -> None:
    assert {skill.id for skill in SKILLS} == {fn.__name__ for fn in TOOL_FUNCTIONS}


def test_every_skill_carries_a_usable_description() -> None:
    """A runtime routes on the description; an empty one makes the skill unreachable."""
    for skill in SKILLS:
        assert skill.name.strip()
        assert len(skill.description.strip()) > 40, f"{skill.id} has no usable description"


def test_the_card_document_is_json_safe_and_names_the_region() -> None:
    document = agent_card_document(local_settings())
    assert document["name"] == "continuous-controls-monitoring"
    assert "asia-southeast1" in str(document["url"])
    assert [skill["id"] for skill in document["skills"]] == [s.id for s in SKILLS]


def test_the_api_serves_the_card_for_discovery(api_client: TestClient) -> None:
    resp = api_client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.json()["skills"], "a card with no skills is not a discovery document"


def test_the_agent_path_routes_an_exception_rather_than_only_flagging_it() -> None:
    result = run_control_test(
        "pack-egress-config",
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        settings=local_settings(),
    )
    assert result["result"]["requires_human_review"] is True
    assert result["review_ref"], "the agent surface flagged an exception it never routed"


def test_the_agent_path_does_not_manufacture_a_review_for_a_passing_control() -> None:
    result = run_control_test(
        "pack-patch-sla",
        tenant=sample_cases.TENANT,
        settings=local_settings(),
    )
    assert result["result"]["requires_human_review"] is False
    assert result["review_ref"] == ""


def test_the_run_tool_summarises_the_batch() -> None:
    summary = run_monitoring(tenant=sample_cases.TENANT, settings=local_settings())
    assert summary["passed"] >= 1
    assert summary["exceptions"] >= 1
    assert len(summary["results"]) == 4


def test_the_tool_output_passes_through_the_redaction_pass() -> None:
    """P-04 at the agent boundary: a tool result becomes model context, so it is minimised.

    The output is walked by the redactor before it is returned; here we assert it is a
    well-formed JSON-safe object (the redaction of planted identifiers is proved end to end in
    ``test_review_routing.py`` against a result whose finding carries one).
    """
    result = run_control_test(
        "pack-egress-config",
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        settings=local_settings(),
    )
    assert isinstance(result, dict)
    assert result["result"]["control_id"] == "SC-7-egress"


def test_the_tools_import_and_run_with_no_agent_runtime_installed(no_cloud_sdk: None) -> None:
    """``build_function_tools`` is the ONLY code path that may need a runtime."""
    from continuous_controls_monitoring.agent import tools

    assert tools.TOOL_FUNCTIONS
    assert build_agent_card(local_settings()).skills
    with pytest.raises(ModuleNotFoundError):
        tools.build_function_tools()
