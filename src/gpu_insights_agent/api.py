from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "Install server dependencies with: pip install -e '.[server]'"
    ) from exc

from gpu_insights_agent.agent import GpuInsightsAgent
from gpu_insights_agent.alerts import propose_alert
from gpu_insights_agent.config import Settings
from gpu_insights_agent.kubernetes import KubernetesClient, KubernetesError
from gpu_insights_agent.prometheus import PrometheusError


app = FastAPI(
    title="GPU Insights Agent",
    version="0.1.0",
    description="Natural-language GPU usage insights and guarded alert rule generation.",
)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3)
    window: str | None = Field(
        default=None,
        description="Prometheus duration such as 30m, 6h, or 7d.",
    )


class AlertRequest(BaseModel):
    request: str = Field(..., min_length=3)


class ApplyAlertRequest(BaseModel):
    request: str = Field(..., min_length=3)
    confirm: bool = False
    dry_run: bool = True


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat")
def chat(body: ChatRequest) -> dict[str, Any]:
    try:
        return GpuInsightsAgent.from_env().answer(body.question, body.window).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PrometheusError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/alerts/propose")
def propose(body: AlertRequest) -> dict[str, Any]:
    try:
        return propose_alert(body.request).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/alerts/apply")
def apply_alert(body: ApplyAlertRequest) -> dict[str, Any]:
    settings = Settings.from_env()
    if not settings.allow_alert_apply:
        raise HTTPException(
            status_code=403,
            detail="Alert application is disabled. Set ALLOW_ALERT_APPLY=true to enable it.",
        )
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true after reviewing the proposed PrometheusRule.",
        )
    proposal = propose_alert(body.request, settings)
    try:
        result = KubernetesClient().apply_prometheus_rule(
            proposal.manifest,
            dry_run=body.dry_run,
        )
    except KubernetesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "dry_run": body.dry_run,
        "proposal": proposal.to_dict(),
        "kubernetes": result,
    }

