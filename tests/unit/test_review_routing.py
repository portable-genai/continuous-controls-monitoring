"""Rule R8: a control-test exception is ROUTED to human-review-console, not left in a per-repo
boolean.

This is the standing gate for the failure the rule exists to prevent. A repo can set
``requires_human_review = True``, pass every other test, and still auto-execute in practice
because nothing ever reads the flag. So the assertions here are about the ROUTING, not the flag:
an exception produces an outbound review, a passing control produces none, the payload leaves
redacted, and the on-prem placeholder refuses rather than swallowing the escalation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from continuous_controls_monitoring.adapters.gcp.review_router import (
    CloudReviewRouter,
)
from continuous_controls_monitoring.adapters.local.review_router import (
    LocalReviewRouter,
)
from continuous_controls_monitoring.adapters.onprem.review_router import (
    OnPremReviewRouter,
)
from continuous_controls_monitoring.api.app import (
    app,
)
from continuous_controls_monitoring.config import (
    Settings,
)
from continuous_controls_monitoring.domain.kernel import (
    Severity,
)

from tests.fixtures import sample_cases


def _settings(profile: str = "local") -> Settings:
    return Settings(profile=profile, audit_path=":memory:", tenant="demo-bank")


def test_an_exception_produces_an_outbound_review() -> None:
    router = LocalReviewRouter(_settings())
    ref = router.route(sample_cases.ESCALATING_RESULT, maker=sample_cases.ACTOR)
    assert ref, "routing must return a reference, so the caller can record where it went"
    pending = router.outbox.pending()
    assert len(pending) == 1
    review = pending[0].review
    assert review.maker == sample_cases.ACTOR
    assert review.tenant == "demo-bank"
    assert review.severity == Severity.HIGH.value
    assert review.source_key, "a durable outbox needs an idempotency key"


def test_the_payload_is_redacted_before_it_leaves_the_process() -> None:
    """human-review-console is a shared sink; a raw identifier must never reach the wire."""
    router = LocalReviewRouter(_settings())
    router.route(sample_cases.PII_RESULT, maker=sample_cases.ACTOR)
    review = router.outbox.pending()[0].review
    wire = repr(review.to_payload())
    assert sample_cases.PLANTED_NRIC not in wire
    assert "REDACTED" in wire


def test_the_managed_router_refuses_when_no_console_is_configured() -> None:
    """An escalation with nowhere to go must fail loudly, not return as if it were reviewed."""
    router = CloudReviewRouter(Settings(profile="gcp", audit_path=":memory:", review_url=""))
    with pytest.raises(RuntimeError, match="R8"):
        router.route(sample_cases.ESCALATING_RESULT, maker=sample_cases.ACTOR)


def test_the_onprem_placeholder_refuses_rather_than_dropping_the_escalation() -> None:
    router = OnPremReviewRouter(_settings("onprem"))
    with pytest.raises(NotImplementedError, match="R8"):
        router.route(sample_cases.ESCALATING_RESULT, maker=sample_cases.ACTOR)


def test_the_api_routes_the_exception_in_the_same_request() -> None:
    """The serving path, not just the adapter: an exception must not depend on a later job."""
    client = TestClient(app, client=("127.0.0.1", 50000))
    failed = client.post(
        "/v1/controls/test",
        json={"pack_id": "pack-egress-config"},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert failed["requires_human_review"] is True
    assert failed["review_ref"], "an exception with no routing reference went nowhere"

    passing = client.post(
        "/v1/controls/test",
        json={"pack_id": "pack-patch-sla"},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert passing["requires_human_review"] is False
    assert passing["review_ref"] == "", "a passing control must not manufacture a review"
