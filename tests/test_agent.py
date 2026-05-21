from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gpu_insights_agent.agent import GpuInsightsAgent, classify_intent
from gpu_insights_agent.config import Settings


class FakePrometheus:
    def __init__(self):
        self.queries: list[str] = []

    def query(self, promql: str):
        self.queries.append(promql)
        return {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"namespace": "team-a", "pod": "trainer-0"},
                    "value": [1710000000, "4.2"],
                }
            ],
        }


class AgentTest(unittest.TestCase):
    def test_classifies_idle_question(self):
        self.assertEqual(
            classify_intent("Which workloads are wasting GPUs?"),
            "idle_allocated_gpus",
        )

    def test_answers_with_template_query(self):
        fake = FakePrometheus()
        agent = GpuInsightsAgent(
            fake,
            settings=Settings(prometheus_url="http://prometheus", default_window="6h"),
        )
        response = agent.answer("Which pods are idle?", "6h")
        self.assertEqual(response.intent, "idle_allocated_gpus")
        self.assertIn("trainer-0", response.answer)
        self.assertIn("DCGM_FI_DEV_GPU_UTIL", fake.queries[0])


if __name__ == "__main__":
    unittest.main()

