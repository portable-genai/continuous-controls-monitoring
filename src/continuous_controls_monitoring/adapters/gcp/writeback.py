"""Managed EffectivenessWritebackPort: WRITE results to obligations-control-mapping's effectiveness
write-back endpoint.

Appends the result as an evidence node linked to the tested control via
obligations-control-mapping's authenticated write-back API. The lazy ``google.auth`` import is the
offline ImportError point; the HTTP is stdlib ``urllib``. obligations-control-mapping rejects an
unknown control id with a 404, which this adapter surfaces as :class:`UnknownControlError` rather
than swallowing.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ...config import Settings
from ...domain.models import ControlTestResult
from ...ports.writeback import UnknownControlError


class RemoteEffectivenessWriteback:
    """Append effectiveness evidence nodes to obligations-control-mapping
    under the managed profile.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def append_result(self, result: ControlTestResult, *, tenant: str = "") -> str:
        token = self._token()
        payload = json.dumps(
            {
                "control_id": result.control_id,
                "pack_id": result.pack_id,
                "as_of": result.as_of.isoformat(),
                "passed": result.passed,
                "design": result.design.rating.value,
                "operating": result.operating.rating.value,
                "findings": len(result.findings),
                "tenant": tenant or self._settings.tenant,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self._settings.rgc7_writeback_url.rstrip("/") + "/v1/effectiveness",
            data=payload,
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https base
                body = json.loads(resp.read().decode("utf-8"))
        except (
            urllib.error.HTTPError
        ) as exc:  # pragma: no cover - needs live obligations-control-mapping
            if exc.code == 404:
                raise UnknownControlError(
                    f"obligations-control-mapping rejected the write-back: control "
                    f"{result.control_id!r} is unknown"
                ) from exc
            raise
        return str(body.get("evidence_ref", ""))

    def _token(self) -> str:
        import google.auth.transport.requests
        from google.oauth2 import id_token

        request = google.auth.transport.requests.Request()
        return str(id_token.fetch_id_token(request, self._settings.rgc7_writeback_url))
