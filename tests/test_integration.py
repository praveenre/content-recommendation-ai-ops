"""
Integration Testing Framework
Verifies that components interoperate seamlessly across the end-to-end deployment lifecycle:
Dependency Validation Gate -> Deployment Orchestrator -> Monitoring Engine -> Health RCA.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.dependency_validator import DependencyValidator
from src.monitoring_dashboard import MetricsEngine
from src.deployment_orchestrator import DeploymentOrchestrator
from src.health_analyzer import HealthAnalyzer


class TestPipelineIntegration(unittest.TestCase):
    """Integration test suite connecting pipeline components."""

    def setUp(self):
        self.orchestrator = DeploymentOrchestrator()
        self.monitoring_engine = MetricsEngine({
            "thresholds": {
                "latency_ms": {"warning": 95.0, "critical": 140.0, "metric_label": "Latency", "unit": "ms"},
                "error_rate_pct": {"warning": 1.5, "critical": 5.0, "metric_label": "Error Rate", "unit": "%"}
            },
            "history": {"max_datapoints": 30, "sample_interval_sec": 1.0},
            "simulation": {"default_profile": "normal"}
        })

    def test_integration_dependency_gate_blocks_deployment(self):
        """
        Integration: Dependency Validator acts as an automated deployment gate.
        Conflicting dependencies must abort deployment before any canary traffic routes to Green.
        """
        conflicting_reqs = os.path.join(os.path.dirname(__file__), "..", "requirements_conflict.txt")
        result = self.orchestrator.execute_canary_deployment(
            candidate_version="v2.0.0-incompatible",
            candidate_reqs_path=conflicting_reqs
        )

        self.assertEqual(result["status"], "ABORTED_DEPENDENCY_CONFLICT")
        self.assertGreater(len(result["conflicts"]), 0)
        self.assertEqual(self.orchestrator.traffic_split["blue"], 100)
        self.assertEqual(self.orchestrator.traffic_split["green"], 0)

    def test_integration_canary_monitoring_triggers_auto_rollback(self):
        """
        Integration: Telemetry during canary soak feeds into rollback triggers.
        When canary p95 latency violates the 100ms SLA, the orchestrator triggers immediate rollback.
        """
        candidate_reqs = os.path.join(os.path.dirname(__file__), "..", "requirements_candidate.txt")
        result = self.orchestrator.execute_canary_deployment(
            candidate_version="v1.2.0-canary-degraded",
            candidate_reqs_path=candidate_reqs,
            inject_fault_at_stage=2,
            fault_type="latency"
        )

        self.assertEqual(result["status"], "ROLLED_BACK_TO_STABLE")
        self.assertEqual(result["failed_stage"], 2)
        self.assertIn("p95 Latency", result["trigger_reason"])

        # Also push failed metrics to monitoring engine to confirm alert registration
        metrics = result["metrics_at_failure"]
        self.monitoring_engine.record_datapoint({
            "timestamp": 2000.0,
            "time_label": "13:00:00",
            "latency_avg_ms": metrics["latency_avg_ms"],
            "latency_p95_ms": metrics["latency_p95_ms"],
            "latency_p99_ms": metrics["latency_p95_ms"] * 1.2,
            "rps": 30.0,
            "rpm": 1800,
            "error_rate_pct": metrics["error_rate_pct"],
            "cpu_usage_pct": metrics["cpu_pct"],
            "memory_usage_pct": 60.0,
            "profile": "canary_failure"
        })

        self.assertGreater(len(self.monitoring_engine.active_alerts), 0)
        active_metric_names = {a["metric"] for a in self.monitoring_engine.active_alerts}
        self.assertIn("latency_ms", active_metric_names)

    def test_integration_deployment_failure_to_health_rca(self):
        """
        Integration: Deployment degradation events logged in app.log
        are ingested by the Health Analyzer to formulate root cause and remediation.
        """
        log_path = os.path.join(os.path.dirname(__file__), "..", "logs", "app.log")
        analyzer = HealthAnalyzer(log_path)
        report = analyzer.generate_health_report()

        self.assertIn(report["health_status"], ["HEALTHY", "DEGRADED", "CRITICAL_ATTENTION_REQUIRED"])
        self.assertTrue(len(report["primary_root_causes"]) > 0 or report["health_status"] == "HEALTHY")
        self.assertIn("correlation_analysis", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)

