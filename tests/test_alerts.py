from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gpu_insights_agent.alerts import propose_alert
from gpu_insights_agent.config import Settings


class AlertsTest(unittest.TestCase):
    def test_low_utilization_alert(self):
        proposal = propose_alert(
            "Alert me when GPU utilization is below 10% for 2 hours",
            Settings(alert_namespace="gpu-usage-monitor"),
        )
        rule = proposal.manifest["spec"]["groups"][0]["rules"][0]
        self.assertEqual(proposal.intent, "gpu_low_utilization")
        self.assertEqual(rule["for"], "2h")
        self.assertIn("DCGM_FI_DEV_GPU_UTIL", rule["expr"])
        self.assertIn("kind: PrometheusRule", proposal.yaml)

    def test_memory_alert_defaults(self):
        proposal = propose_alert("Create an alert when GPU memory is high")
        rule = proposal.manifest["spec"]["groups"][0]["rules"][0]
        self.assertEqual(proposal.intent, "gpu_memory_pressure")
        self.assertIn("> 90", rule["expr"])


if __name__ == "__main__":
    unittest.main()

