# GPU Insights Agent

GPU Insights Agent is a Kubernetes-friendly assistant for NVIDIA GPU Usage Monitor deployments. It answers natural-language questions about GPU usage by querying Prometheus directly, and it can propose Prometheus alert rules for common GPU operations conditions.

The first version is deliberately conservative:

- It uses curated PromQL templates for GPU operations questions.
- It does not let the model invent arbitrary production PromQL.
- Alert application is disabled by default.
- It can run entirely inside a customer network.

## What It Can Answer

Examples:

```text
Which workloads are wasting GPUs this week?
Which pods have high GPU memory pressure?
Are any GPU pods pending?
Which workloads are the busiest right now?
Do we have GPU XID errors?
How many GPUs do we have by model?
```

## What It Can Configure

Examples:

```text
Alert me when GPU utilization is below 10% for 2 hours.
Create an alert when GPU memory is above 90% for 30 minutes.
Alert when any GPU reports XID errors.
```

The agent returns a `PrometheusRule` manifest first. Applying that manifest requires `ALLOW_ALERT_APPLY=true` and a request with `confirm=true`.

## Local Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[server,test]"
export PROMETHEUS_URL=http://localhost:9090
uvicorn gpu_insights_agent.api:app --reload
```

Ask a question:

```bash
curl -s http://localhost:8000/v1/chat \
  -H 'content-type: application/json' \
  -d '{"question":"Which workloads are wasting GPUs over the last 6 hours?"}'
```

Propose an alert:

```bash
curl -s http://localhost:8000/v1/alerts/propose \
  -H 'content-type: application/json' \
  -d '{"request":"Alert me when GPU utilization is below 10% for 2 hours."}'
```

## CLI

```bash
PROMETHEUS_URL=http://localhost:9090 \
python -m gpu_insights_agent "Which GPU pods are idle?"
```

## Kubernetes Install

Build and push an image:

```bash
docker build -t registry.example.com/gpu-insights-agent:0.1.0 .
docker push registry.example.com/gpu-insights-agent:0.1.0
```

Install:

```bash
helm install gpu-insights-agent charts/gpu-insights-agent \
  --namespace gpu-usage-monitor \
  --set image.repository=registry.example.com/gpu-insights-agent \
  --set image.tag=0.1.0 \
  --set prometheus.url=http://gpu-usage-monitor-prometheus-server.gpu-usage-monitor.svc:9090
```

Enable alert application only after reviewing RBAC:

```bash
helm upgrade gpu-insights-agent charts/gpu-insights-agent \
  --namespace gpu-usage-monitor \
  --reuse-values \
  --set alerting.apply.enabled=true
```

## Optional LLM Wording

By default, answers are generated locally from deterministic summaries. You can enable an OpenAI-compatible chat completion endpoint for nicer wording:

```bash
export LLM_ENABLED=true
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-4.1-mini
```

Only compact summarized observations are sent to the LLM layer, not raw time series.

## Security Notes

- Keep `ALLOW_ALERT_APPLY=false` for read-only deployments.
- Use network policy so the service can only reach Prometheus, Kubernetes API, and an approved LLM endpoint if used.
- Scope the service account to the namespaces and resources customers want managed.
- Log every question, generated query ID, alert proposal, and alert application event.

