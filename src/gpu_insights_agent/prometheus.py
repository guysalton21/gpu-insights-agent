from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PrometheusError(RuntimeError):
    pass


class PrometheusClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def query(self, promql: str, at: str | None = None) -> dict[str, Any]:
        params: dict[str, str] = {"query": promql}
        if at:
            params["time"] = at
        return self._get("query", params)

    def query_range(
        self,
        promql: str,
        start: str,
        end: str,
        step: str,
    ) -> dict[str, Any]:
        return self._get(
            "query_range",
            {"query": promql, "start": start, "end": end, "step": step},
        )

    def labels(self, match: str | None = None) -> list[str]:
        params: dict[str, list[str]] = {}
        if match:
            params["match[]"] = [match]
        data = self._get("labels", params)
        return list(data)

    def label_values(self, label_name: str, match: str | None = None) -> list[str]:
        params: dict[str, list[str]] = {}
        if match:
            params["match[]"] = [match]
        data = self._get(f"label/{label_name}/values", params)
        return list(data)

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        query = urlencode(params, doseq=True)
        url = f"{self.base_url}/api/v1/{path}"
        if query:
            url = f"{url}?{query}"
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PrometheusError(f"Prometheus returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise PrometheusError(f"Could not reach Prometheus at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise PrometheusError("Prometheus returned invalid JSON") from exc

        if payload.get("status") != "success":
            message = payload.get("error") or payload
            raise PrometheusError(f"Prometheus query failed: {message}")
        return payload.get("data")


def vector_rows(data: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    if data.get("resultType") != "vector":
        return []
    rows: list[dict[str, Any]] = []
    for item in data.get("result", [])[:limit]:
        timestamp, raw_value = item.get("value", [None, None])
        try:
            value: float | None = float(raw_value)
        except (TypeError, ValueError):
            value = None
        rows.append(
            {
                "metric": item.get("metric", {}),
                "value": value,
                "timestamp": timestamp,
            }
        )
    return rows

