"""Managed ControlInventoryPort: READ Rgc7's control inventory over its authenticated read API.

The S2S credential is a Google-signed OIDC ID token addressed to Rgc7's IAP audience, so the
lazy ``google.auth`` import is the first thing each method does and an offline caller gets an
ImportError there rather than at construction. The HTTP itself is stdlib ``urllib``, so no extra
runtime dependency is pulled in. Cross-tenant reads are refused with a 403, never a 404, by
propagating Rgc7's own status.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ...config import Settings
from ...domain.kernel import Citation
from ...domain.models import InventoryControl
from ...ports.control_inventory import CrossTenantError


class RemoteControlInventory:
    """Read the Rgc7 inventory over its REST read API under the managed profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_controls(self, tenant: str) -> tuple[InventoryControl, ...]:
        body = self._get(f"/v1/controls?tenant={urllib.parse.quote(tenant)}")
        return tuple(_control_from_json(item) for item in body.get("controls", []))

    def get_control(self, control_id: str, *, tenant: str) -> InventoryControl | None:
        status, body = self._get_status(
            f"/v1/controls/{urllib.parse.quote(control_id)}?tenant={urllib.parse.quote(tenant)}"
        )
        if status == 404:
            return None
        if status == 403:
            raise CrossTenantError(f"control {control_id!r} is not in tenant {tenant!r}")
        return _control_from_json(body)

    # ------------------------------------------------------------------ #
    def _token(self) -> str:
        # Lazy import: the offline profiles bind this adapter too, and must construct with no SDK.
        import google.auth.transport.requests
        from google.oauth2 import id_token

        request = google.auth.transport.requests.Request()
        return str(id_token.fetch_id_token(request, self._settings.rgc7_read_url))

    def _get(self, path: str) -> Any:
        _status, body = self._get_status(path)
        return body

    def _get_status(self, path: str) -> tuple[int, Any]:
        token = self._token()
        req = urllib.request.Request(
            self._settings.rgc7_read_url.rstrip("/") + path,
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https base
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - needs live Rgc7
            return exc.code, {}


def _control_from_json(item: Any) -> InventoryControl:
    return InventoryControl(
        control_id=str(item.get("control_id", "")),
        title=str(item.get("title", "")),
        owner=str(item.get("owner", "")),
        framework=str(item.get("framework", "")),
        sox_significant=bool(item.get("sox_significant", False)),
        citations=(Citation(source_id=f"rgc7:{item.get('control_id', '')}", title="Rgc7"),),
    )
