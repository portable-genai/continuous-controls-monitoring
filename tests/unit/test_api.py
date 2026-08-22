"""API surface: verified-principal identity, fail-closed S2S, security headers.

The client comes from the shared ``api_client`` fixture, which pins a loopback peer: the
app-object exposure guard refuses the unauthenticated local posture to any other peer, and
TestClient's default peer is the literal host "testclient".
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

_TOKEN_ENV = "CCM_S2S_TOKEN"

#: The default egress config-scan pack, whose offline evidence drifts, so the control FAILS.
_FAILING_PACK = {"pack_id": "pack-egress-config"}


def test_control_test_uses_the_verified_principal_as_actor(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/controls/test",
        json=_FAILING_PACK,
        headers={"X-Dev-Persona": "auditor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["control_id"] == "SC-7-egress"
    assert body["passed"] is False
    assert body["operating"]["rating"] == "deficient"
    assert body["requires_human_review"] is True
    # Rule R8: the escalation was routed, not merely flagged (see test_review_routing.py).
    assert body["review_ref"]
    # The consequential figures come from the engine; the write-back landed on the control.
    assert body["writeback_ref"]


def test_a_passing_control_is_not_escalated(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/controls/test",
        json={"pack_id": "pack-patch-sla"},
        headers={"X-Dev-Persona": "auditor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["passed"] is True
    assert body["requires_human_review"] is False
    assert body["review_ref"] == "", "a passing control must not manufacture a review"


def test_a_full_run_returns_a_batch(api_client: TestClient) -> None:
    resp = api_client.post("/v1/run", json={}, headers={"X-Dev-Persona": "auditor"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    assert body["exceptions"] >= 1


def test_unknown_pack_is_404(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/controls/test",
        json={"pack_id": "does-not-exist"},
        headers={"X-Dev-Persona": "auditor"},
    )
    assert resp.status_code == 404


def test_unknown_persona_is_401(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/controls/test",
        json=_FAILING_PACK,
        headers={"X-Dev-Persona": "ghost"},
    )
    assert resp.status_code == 401


def test_healthz_reports_profile_and_region(api_client: TestClient) -> None:
    body = api_client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["profile"] == "local"
    assert body["region"] == "asia-southeast1"


def test_security_headers_present(api_client: TestClient) -> None:
    headers = api_client.get("/healthz").headers
    assert headers["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.fixture()
def token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv(_TOKEN_ENV, "s3cret-service-token")
    yield "s3cret-service-token"


def test_s2s_endpoint_open_when_secret_unset(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_TOKEN_ENV, raising=False)
    assert api_client.post("/v1/audit/ping").status_code == 200


def test_s2s_endpoint_rejects_missing_token_when_enforced(
    api_client: TestClient, token_env: str
) -> None:
    assert api_client.post("/v1/audit/ping").status_code == 401


def test_s2s_endpoint_accepts_correct_token(api_client: TestClient, token_env: str) -> None:
    resp = api_client.post("/v1/audit/ping", headers={"Authorization": f"Bearer {token_env}"})
    assert resp.status_code == 200
