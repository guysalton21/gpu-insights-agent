from __future__ import annotations

import argparse
import json
import sys

from gpu_insights_agent.agent import GpuInsightsAgent
from gpu_insights_agent.prometheus import PrometheusError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask GPU usage questions.")
    parser.add_argument("question", help="Natural-language GPU usage question.")
    parser.add_argument("--window", default=None, help="Duration such as 30m, 6h, or 7d.")
    parser.add_argument("--json", action="store_true", help="Print full JSON response.")
    args = parser.parse_args(argv)

    try:
        response = GpuInsightsAgent.from_env().answer(args.question, args.window)
    except (PrometheusError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(response.to_dict(), indent=2))
    else:
        print(response.answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

