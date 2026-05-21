from __future__ import annotations

import json
import os
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SERVICE_ACCOUNT_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"


class KubernetesError(RuntimeError):
    pass


class KubernetesClient:
    def __init__(
        self,
        api_server: str | None = None,
        token: str | None = None,
        ca_path: str | None = None,
        timeout_seconds: float = 10.0,
    ):
        host = os.getenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
        port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
        self.api_server = api_server or f"https://{host}:{port}"
        self.token = token or self._read_token()
        self.ca_path = ca_path or f"{SERVICE_ACCOUNT_DIR}/ca.crt"
        self.timeout_seconds = timeout_seconds

    def apply_prometheus_rule(
        self,
        manifest: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        namespace = manifest["metadata"]["namespace"]
        name = manifest["metadata"]["name"]
        collection = (
            f"/apis/monitoring.coreos.com/v1/namespaces/{namespace}/prometheusrules"
        )
        item_path = f"{collection}/{name}"
        existing = self._request("GET", item_path, allow_404=True)
        if existing is None:
            return self._request("POST", collection, manifest, dry_run=dry_run)
        manifest["metadata"]["resourceVersion"] = existing["metadata"]["resourceVersion"]
        return self._request("PUT", item_path, manifest, dry_run=dry_run)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        dry_run: bool = False,
        allow_404: bool = False,
    ) -> dict[str, Any] | None:
        query = urlencode({"dryRun": "All"}) if dry_run else ""
        url = f"{self.api_server}{path}"
        if query:
            url = f"{url}?{query}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        try:
            with urlopen(
                request,
                timeout=self.timeout_seconds,
                context=self._ssl_context(),
            ) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if allow_404 and exc.code == 404:
                return None
            raise KubernetesError(f"Kubernetes returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise KubernetesError(f"Could not reach Kubernetes API: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise KubernetesError("Kubernetes API returned invalid JSON") from exc

    def _ssl_context(self) -> ssl.SSLContext:
        if self.ca_path and os.path.exists(self.ca_path):
            return ssl.create_default_context(cafile=self.ca_path)
        return ssl.create_default_context()

    @staticmethod
    def _read_token() -> str:
        token_path = f"{SERVICE_ACCOUNT_DIR}/token"
        try:
            with open(token_path, "r", encoding="utf-8") as token_file:
                return token_file.read().strip()
        except OSError as exc:
            raise KubernetesError(
                "Kubernetes service account token was not found. "
                "Run in-cluster or pass a token explicitly."
            ) from exc

