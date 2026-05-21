from __future__ import annotations

from typing import Any

from gpu_insights_agent.config import Settings
from gpu_insights_agent.llm import OpenAICompatibleLLM
from gpu_insights_agent.models import AgentResponse, Observation, QueryRecord
from gpu_insights_agent.prometheus import PrometheusClient, vector_rows
from gpu_insights_agent.promql import (
    InsightTemplate,
    gpu_inventory,
    idle_allocated_gpus,
    memory_pressure,
    pending_gpu_pods,
    top_gpu_consumers,
    validate_window,
    xid_errors,
)


class GpuInsightsAgent:
    def __init__(
        self,
        prometheus: PrometheusClient,
        settings: Settings | None = None,
        llm: OpenAICompatibleLLM | None = None,
    ):
        self.prometheus = prometheus
        self.settings = settings or Settings.from_env()
        self.llm = llm

    @classmethod
    def from_env(cls) -> "GpuInsightsAgent":
        settings = Settings.from_env()
        llm = None
        if settings.llm_enabled and settings.openai_api_key:
            llm = OpenAICompatibleLLM(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
                model=settings.openai_model,
            )
        return cls(
            prometheus=PrometheusClient(
                settings.prometheus_url,
                timeout_seconds=settings.query_timeout_seconds,
            ),
            settings=settings,
            llm=llm,
        )

    def answer(self, question: str, window: str | None = None) -> AgentResponse:
        selected_window = validate_window(
            window or self.settings.default_window,
            max_hours=self.settings.max_query_window_hours,
        )
        intent = classify_intent(question)
        templates = templates_for_intent(intent, selected_window)
        observations = [self._run_template(template) for template in templates]
        suggestions = sorted(
            {suggestion for observation in observations for suggestion in observation.suggestions}
        )
        answer = self._compose_answer(question, intent, observations, suggestions)
        return AgentResponse(
            question=question,
            intent=intent,
            answer=answer,
            observations=observations,
            suggestions=suggestions,
        )

    def _run_template(self, template: InsightTemplate) -> Observation:
        data = self.prometheus.query(template.promql)
        rows = normalize_rows(vector_rows(data, limit=10))
        observation = Observation(
            title=template.title,
            description=template.description,
            rows=rows,
            unit=template.unit,
            empty_message=template.empty_message,
            suggestions=template.suggestions,
            query=QueryRecord(
                id=template.id,
                title=template.title,
                promql=template.promql,
            ),
        )
        return observation

    def _compose_answer(
        self,
        question: str,
        intent: str,
        observations: list[Observation],
        suggestions: list[str],
    ) -> str:
        compact = render_deterministic_answer(intent, observations, suggestions)
        if not self.llm:
            return compact
        return self.llm.polish_answer(question, compact)


def classify_intent(question: str) -> str:
    q = question.lower()
    if any(word in q for word in ("pending", "queued", "unscheduled", "waiting")):
        return "pending_gpu_pods"
    if any(word in q for word in ("memory", "vram", "framebuffer", "oom")):
        return "memory_pressure"
    if any(word in q for word in ("xid", "error", "fault", "health", "failed", "failure")):
        return "gpu_health"
    if any(word in q for word in ("inventory", "capacity", "how many", "gpu type", "model")):
        return "gpu_inventory"
    if any(word in q for word in ("top", "busy", "busiest", "consume", "consumer", "hot")):
        return "top_gpu_consumers"
    if any(word in q for word in ("idle", "waste", "wasting", "underutil", "low utilization")):
        return "idle_allocated_gpus"
    return "summary"


def templates_for_intent(intent: str, window: str) -> list[InsightTemplate]:
    if intent == "pending_gpu_pods":
        return [pending_gpu_pods()]
    if intent == "memory_pressure":
        return [memory_pressure(window)]
    if intent == "gpu_health":
        return [xid_errors(window)]
    if intent == "gpu_inventory":
        return [gpu_inventory()]
    if intent == "top_gpu_consumers":
        return [top_gpu_consumers(window)]
    if intent == "idle_allocated_gpus":
        return [idle_allocated_gpus(window)]
    return [
        idle_allocated_gpus(window),
        top_gpu_consumers(window),
        memory_pressure(window),
        pending_gpu_pods(),
        xid_errors(window),
    ]


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        metric = row.get("metric", {})
        labels = {
            key: value
            for key, value in metric.items()
            if key not in {"__name__", "endpoint", "instance", "job", "pod_template_hash"}
        }
        normalized.append(
            {
                "labels": labels,
                "value": row.get("value"),
                "timestamp": row.get("timestamp"),
            }
        )
    return normalized


def render_deterministic_answer(
    intent: str,
    observations: list[Observation],
    suggestions: list[str],
) -> str:
    lines = [f"Intent: {intent}"]
    for observation in observations:
        lines.append("")
        lines.append(observation.title)
        lines.append(observation.description)
        if not observation.rows:
            lines.append(observation.empty_message)
            continue
        for index, row in enumerate(observation.rows[:5], start=1):
            labels = compact_labels(row.get("labels", {}))
            value = row.get("value")
            if value is None:
                rendered_value = "unknown"
            elif observation.unit == "%":
                rendered_value = f"{value:.1f}%"
            else:
                rendered_value = f"{value:g} {observation.unit}".strip()
            lines.append(f"{index}. {labels}: {rendered_value}")
        if len(observation.rows) > 5:
            lines.append(f"...and {len(observation.rows) - 5} more.")
    if suggestions:
        lines.append("")
        lines.append("Suggested next steps")
        for suggestion in suggestions[:3]:
            lines.append(f"- {suggestion}")
    return "\n".join(lines)


def compact_labels(labels: dict[str, Any]) -> str:
    preferred = [
        "namespace",
        "pod",
        "Hostname",
        "host",
        "node",
        "device",
        "UUID",
        "modelName",
        "GPU_I_PROFILE",
    ]
    parts = [f"{key}={labels[key]}" for key in preferred if labels.get(key)]
    if not parts:
        parts = [f"{key}={value}" for key, value in sorted(labels.items())[:5]]
    return ", ".join(parts) or "series"
