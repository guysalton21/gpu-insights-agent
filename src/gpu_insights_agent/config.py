from __future__ import annotations

import os
from dataclasses import dataclass


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    prometheus_url: str = "http://localhost:9090"
    default_window: str = "6h"
    query_timeout_seconds: float = 10.0
    max_query_window_hours: int = 168
    alert_namespace: str = "monitoring"
    alert_group_name: str = "gpu-insights-agent.rules"
    allow_alert_apply: bool = False
    llm_enabled: bool = False
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            prometheus_url=os.getenv("PROMETHEUS_URL", cls.prometheus_url).rstrip("/"),
            default_window=os.getenv("DEFAULT_QUERY_WINDOW", cls.default_window),
            query_timeout_seconds=float(
                os.getenv("PROMETHEUS_QUERY_TIMEOUT_SECONDS", cls.query_timeout_seconds)
            ),
            max_query_window_hours=int(
                os.getenv("MAX_QUERY_WINDOW_HOURS", cls.max_query_window_hours)
            ),
            alert_namespace=os.getenv("ALERT_NAMESPACE", cls.alert_namespace),
            alert_group_name=os.getenv("ALERT_GROUP_NAME", cls.alert_group_name),
            allow_alert_apply=_bool_env("ALLOW_ALERT_APPLY", cls.allow_alert_apply),
            llm_enabled=_bool_env("LLM_ENABLED", cls.llm_enabled),
            openai_base_url=os.getenv("OPENAI_BASE_URL", cls.openai_base_url).rstrip("/"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", cls.openai_model),
        )

