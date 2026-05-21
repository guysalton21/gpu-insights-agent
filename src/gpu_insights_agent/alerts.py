from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from gpu_insights_agent.config import Settings
from gpu_insights_agent.promql import validate_window


PERCENT_RE = re.compile(r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*%")
DURATION_RE = re.compile(
    r"for\s+(?P<count>[1-9][0-9]*)\s*(?P<unit>seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d)",
    re.IGNORECASE,
)
NAME_RE = re.compile(r"[^a-z0-9-]+")


@dataclass(frozen=True)
class AlertProposal:
    intent: str
    summary: str
    manifest: dict[str, Any]
    yaml: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "summary": self.summary,
            "manifest": self.manifest,
            "yaml": self.yaml,
        }


def propose_alert(request: str, settings: Settings | None = None) -> AlertProposal:
    settings = settings or Settings.from_env()
    parsed = parse_alert_request(request)
    manifest = build_prometheus_rule(parsed, settings)
    return AlertProposal(
        intent=parsed["intent"],
        summary=parsed["summary"],
        manifest=manifest,
        yaml=manifest_to_yaml(manifest),
    )


def parse_alert_request(request: str) -> dict[str, Any]:
    q = request.lower()
    threshold = extract_percent(q)
    duration = extract_duration(q)

    if any(word in q for word in ("memory", "vram", "framebuffer")):
        threshold = threshold if threshold is not None else 90.0
        duration = duration or "30m"
        return {
            "intent": "gpu_memory_pressure",
            "alert": "GpuMemoryPressure",
            "name": "gpu-memory-pressure",
            "summary": f"Alert when GPU memory usage is above {threshold:g}% for {duration}.",
            "expr": memory_alert_expr(threshold),
            "for": duration,
            "severity": "warning",
        }

    if any(word in q for word in ("xid", "error", "fault", "health")):
        duration = duration or "5m"
        return {
            "intent": "gpu_xid_errors",
            "alert": "GpuXidErrors",
            "name": "gpu-xid-errors",
            "summary": f"Alert when any GPU reports XID errors over {duration}.",
            "expr": xid_alert_expr(duration),
            "for": "0m",
            "severity": "critical",
        }

    threshold = threshold if threshold is not None else 10.0
    duration = duration or "2h"
    return {
        "intent": "gpu_low_utilization",
        "alert": "GpuLowUtilization",
        "name": "gpu-low-utilization",
        "summary": f"Alert when allocated GPU utilization is below {threshold:g}% for {duration}.",
        "expr": low_utilization_expr(threshold),
        "for": duration,
        "severity": "warning",
    }


def extract_percent(text: str) -> float | None:
    match = PERCENT_RE.search(text)
    if not match:
        return None
    value = float(match.group("value"))
    if value < 0 or value > 100:
        raise ValueError("Percent thresholds must be between 0 and 100.")
    return value


def extract_duration(text: str) -> str | None:
    match = DURATION_RE.search(text)
    if not match:
        return None
    count = int(match.group("count"))
    unit = match.group("unit").lower()
    normalized_unit = {
        "second": "s",
        "seconds": "s",
        "sec": "s",
        "secs": "s",
        "s": "s",
        "minute": "m",
        "minutes": "m",
        "min": "m",
        "mins": "m",
        "m": "m",
        "hour": "h",
        "hours": "h",
        "hr": "h",
        "hrs": "h",
        "h": "h",
        "day": "d",
        "days": "d",
        "d": "d",
    }[unit]
    return validate_window(f"{count}{normalized_unit}", max_hours=168)


def low_utilization_expr(threshold: float) -> str:
    return f"""
(
  avg by (namespace, pod) (
    avg_over_time(DCGM_FI_DEV_GPU_UTIL{{pod!=""}}[30m])
  ) < {threshold:g}
)
and on (namespace, pod)
(
  sum by (namespace, pod) (
    kube_pod_container_resource_requests{{resource=~"nvidia.*gpu"}}
  ) > 0
)
""".strip()


def memory_alert_expr(threshold: float) -> str:
    used = """
sum by (namespace, pod) (
  avg_over_time(DCGM_FI_DEV_FB_USED{pod!=""}[30m])
)
""".strip()
    free = """
sum by (namespace, pod) (
  avg_over_time(DCGM_FI_DEV_FB_FREE{pod!=""}[30m])
)
""".strip()
    return f"""
(
  100 * ({used}) / (({used}) + ({free}))
) > {threshold:g}
""".strip()


def xid_alert_expr(window: str) -> str:
    return f"""
sum by (Hostname, UUID, device) (
  increase(DCGM_FI_DEV_XID_ERRORS[{window}])
) > 0
""".strip()


def build_prometheus_rule(parsed: dict[str, Any], settings: Settings) -> dict[str, Any]:
    name = sanitize_name(parsed["name"])
    return {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "PrometheusRule",
        "metadata": {
            "name": name,
            "namespace": settings.alert_namespace,
            "labels": {
                "app.kubernetes.io/name": "gpu-insights-agent",
                "app.kubernetes.io/managed-by": "gpu-insights-agent",
            },
        },
        "spec": {
            "groups": [
                {
                    "name": settings.alert_group_name,
                    "rules": [
                        {
                            "alert": parsed["alert"],
                            "expr": parsed["expr"],
                            "for": parsed["for"],
                            "labels": {
                                "severity": parsed["severity"],
                                "managed_by": "gpu-insights-agent",
                            },
                            "annotations": {
                                "summary": parsed["summary"],
                                "description": (
                                    "Generated from a GPU Insights Agent alert request. "
                                    "Review PromQL and routing before enabling in production."
                                ),
                            },
                        }
                    ],
                }
            ]
        },
    }


def sanitize_name(value: str) -> str:
    lowered = value.lower().strip()
    normalized = NAME_RE.sub("-", lowered).strip("-")
    return normalized[:63] or "gpu-insights-alert"


def manifest_to_yaml(value: Any, indent: int = 0) -> str:
    lines = _yaml_lines(value, indent)
    return "\n".join(lines) + "\n"


def _yaml_lines(value: Any, indent: int) -> list[str]:
    pad = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, str) and "\n" in item:
                lines.append(f"{pad}{key}: |")
                lines.extend(f"{pad}  {line}" for line in item.splitlines())
            elif isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{pad}{key}: {yaml_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                if not item:
                    lines.append(f"{pad}- {{}}")
                    continue
                first_key, first_value = next(iter(item.items()))
                rest = dict(list(item.items())[1:])
                if isinstance(first_value, str) and "\n" in first_value:
                    lines.append(f"{pad}- {first_key}: |")
                    lines.extend(f"{pad}    {line}" for line in first_value.splitlines())
                elif isinstance(first_value, (dict, list)):
                    lines.append(f"{pad}- {first_key}:")
                    lines.extend(_yaml_lines(first_value, indent + 4))
                else:
                    lines.append(f"{pad}- {first_key}: {yaml_scalar(first_value)}")
                if rest:
                    lines.extend(_yaml_lines(rest, indent + 2))
            elif isinstance(item, list):
                lines.append(f"{pad}-")
                lines.extend(_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{pad}- {yaml_scalar(item)}")
        return lines
    return [f"{pad}{yaml_scalar(value)}"]


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    text = str(value)
    if text == "":
        return '""'
    if re.match(r"^[A-Za-z0-9._/-]+$", text):
        return text
    return json.dumps(text)
