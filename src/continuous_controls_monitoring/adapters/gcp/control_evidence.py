"""Managed ControlEvidencePort: READ Rsk1's cloud control evidence-pack surface (ex-Rsk2).

Authenticated with a Google-signed OIDC ID token addressed to Rsk1's audience (the lazy
``google.auth`` import is the offline ImportError point); the HTTP is stdlib ``urllib``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ...config import Settings
from ...domain.models import EvidenceRecord, TestKind


class RemoteControlEvidence:
    """Fetch Rsk1 evidence packs over their REST surface under the managed profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, control_id: str) -> tuple[EvidenceRecord, ...]:
        token = self._token()
        url = (
            self._settings.rsk1_evidence_url.rstrip("/")
            + f"/v1/evidence/{urllib.parse.quote(control_id)}"
        )
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https base
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError:  # pragma: no cover - needs live Rsk1
            return ()
        return tuple(_record_from_json(control_id, item) for item in body.get("records", []))

    def _token(self) -> str:
        import google.auth.transport.requests
        from google.oauth2 import id_token

        request = google.auth.transport.requests.Request()
        return str(id_token.fetch_id_token(request, self._settings.rsk1_evidence_url))


def _record_from_json(
    control_id: str, item: Any
) -> EvidenceRecord:  # pragma: no cover - needs live Rsk1
    return EvidenceRecord(
        control_id=control_id,
        kind=TestKind(str(item.get("kind", "access_recert"))),
        source="rsk1_evidence_pack",
        identifier=str(item.get("identifier", "")),
        attributes={str(k): str(v) for k, v in (item.get("attributes") or {}).items()},
        source_ref=str(item.get("source_ref", "")),
    )
