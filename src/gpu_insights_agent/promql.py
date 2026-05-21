from __future__ import annotations

import re
from dataclasses import dataclass


WINDOW_RE = re.compile(r"^(?P<count>[1-9][0-9]*)(?P<unit>[smhdw])$")
WINDOW_HOURS = {"s": 1 / 3600, "m": 1 / 60, "h": 1, "d": 24, "w": 24 * 7}


@dataclass(frozen=True)
class InsightTemplate:
    id: str
    title: str
    description: str
    promql: str
    unit: str
    empty_message: str
    suggestions: tuple[str, ...] = ()


def validate_window(window: str, max_hours: int = 168) -> str:
    match = WINDOW_RE.match(window.strip())
    if not match:
        raise ValueError("Window must look like 30m, 6h, 7d, or 1w.")
    count = int(match.group("count"))
    unit = match.group("unit")
    hours = count * WINDOW_HOURS[unit]
    if hours > max_hours:
        raise ValueError(f"Window must be <= {max_hours} hours.")
    return f"{count}{unit}"


def idle_allocated_gpus(window: str, threshold_percent: float = 10) -> InsightTemplate:
    return InsightTemplate(
        id="idle_allocated_gpus",
        title="Allocated GPUs with low utilization",
        description=f"Pods that requested GPUs but averaged below {threshold_percent:g}% utilization.",
        promql=f"""
(
  avg by (namespace, pod) (
    avg_over_time(DCGM_FI_DEV_GPU_UTIL{{pod!=""}}[{window}])
  ) < {threshold_percent:g}
)
and on (namespace, pod)
(
  sum by (namespace, pod) (
    kube_pod_container_resource_requests{{resource=~"nvidia.*gpu"}}
  ) > 0
)
""".strip(),
        unit="%",
        empty_message="I did not find GPU-requesting pods below the utilization threshold.",
        suggestions=(
            "Consider lowering requested GPUs, improving batching, or scheduling work onto shared/MIG partitions.",
            "Check whether these pods are waiting on CPU, storage, network, or input pipeline bottlenecks.",
        ),
    )


def top_gpu_consumers(window: str, limit: int = 10) -> InsightTemplate:
    return InsightTemplate(
        id="top_gpu_consumers",
        title="Top GPU-utilizing workloads",
        description=f"Highest average GPU utilization over {window}.",
        promql=f"""
topk(
  {limit},
  avg by (namespace, pod) (
    avg_over_time(DCGM_FI_DEV_GPU_UTIL{{pod!=""}}[{window}])
  )
)
""".strip(),
        unit="%",
        empty_message="I did not find pod-level GPU utilization series.",
        suggestions=(
            "Compare these workloads against allocation and priority before making scheduling changes.",
        ),
    )


def memory_pressure(window: str, threshold_percent: float = 80) -> InsightTemplate:
    used = f"""
sum by (namespace, pod) (
  avg_over_time(DCGM_FI_DEV_FB_USED{{pod!=""}}[{window}])
)
""".strip()
    free = f"""
sum by (namespace, pod) (
  avg_over_time(DCGM_FI_DEV_FB_FREE{{pod!=""}}[{window}])
)
""".strip()
    return InsightTemplate(
        id="memory_pressure",
        title="GPU memory pressure",
        description=f"Pods above {threshold_percent:g}% framebuffer memory usage.",
        promql=f"""
(
  100 * ({used}) / (({used}) + ({free}))
) > {threshold_percent:g}
""".strip(),
        unit="%",
        empty_message="I did not find GPU pods above the memory pressure threshold.",
        suggestions=(
            "Inspect batch size, model parallelism, activation checkpointing, and memory fragmentation.",
        ),
    )


def pending_gpu_pods() -> InsightTemplate:
    return InsightTemplate(
        id="pending_gpu_pods",
        title="Pending GPU pods",
        description="Pending pods that request NVIDIA GPU resources.",
        promql="""
(
  sum by (namespace, pod) (
    kube_pod_status_phase{phase="Pending"}
  ) > 0
)
and on (namespace, pod)
(
  sum by (namespace, pod) (
    kube_pod_container_resource_requests{resource=~"nvidia.*gpu"}
  ) > 0
)
""".strip(),
        unit="pods",
        empty_message="I did not find pending pods with GPU resource requests.",
        suggestions=(
            "Check requested GPU type, node selectors, taints, quotas, and fragmentation across MIG profiles.",
        ),
    )


def xid_errors(window: str) -> InsightTemplate:
    return InsightTemplate(
        id="xid_errors",
        title="GPU XID errors",
        description=f"GPU devices that reported XID errors over {window}.",
        promql=f"""
sum by (Hostname, UUID, device) (
  increase(DCGM_FI_DEV_XID_ERRORS[{window}])
) > 0
""".strip(),
        unit="errors",
        empty_message="I did not find GPU XID errors in the selected window.",
        suggestions=(
            "Inspect node events, driver health, workload logs, and whether the same UUID repeatedly fails.",
        ),
    )


def gpu_inventory() -> InsightTemplate:
    return InsightTemplate(
        id="gpu_inventory",
        title="GPU inventory by model and host",
        description="Visible GPUs grouped by model and host labels from DCGM.",
        promql="""
count by (modelName, Hostname) (
  DCGM_FI_DEV_GPU_UTIL
)
""".strip(),
        unit="gpus",
        empty_message="I did not find DCGM GPU utilization series to infer inventory.",
        suggestions=(
            "Verify DCGM Exporter is running and Prometheus is scraping DCGM_FI_DEV_GPU_UTIL.",
        ),
    )
