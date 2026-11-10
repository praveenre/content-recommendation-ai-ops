"""
Unit Testing Framework - Component Isolation Tests
Validates each component (Dependency Validator, Monitoring Engine,
Deployment Orchestrator, Health Analyzer) works correctly in isolation.
"""

import os
import sys
import tempfile
import unittest

# Ensure workspace root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.dependency_validator import DependencyValidator
from src.monitoring_dashboard import MetricsEngine
from src.deployment_orchestrator import DeploymentOrchestrator
from src.health_analyzer import HealthAnalyzer


class TestDependencyValidator(unittest.TestCase):
    """Test suite for Dependency Validation System."""

    def setUp(self):
        self.validator = DependencyValidator()

    def test_clean_requirements_validation(self):
        """Clean requirements must pass with 0 conflicts and status READY_FOR_DEPLOYMENT."""
        reqs_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
        self.validator.parse_requirements_file(reqs_path)
        conflicts = self.validator.detect_conflicts()
        report = self.validator.generate_report()

        self.assertEqual(len(conflicts), 0, f"Expected 0 conflicts but found: {conflicts}")
        self.assertEqual(report["validation_status"], "READY_FOR_DEPLOYMENT")
        self.assertTrue(report["ready_for_deployment"])

    def test_conflicting_requirements_detection(self):
        """Conflicting candidate requirements must trigger VERSION_COLLISION and DEPLOYMENT_BLOCKED."""
        base_reqs = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
        conf_reqs = os.path.join(os.path.dirname(__file__), "..", "requirements_conflict.txt")

        self.validator.parse_requirements_file(base_reqs)
        self.validator.parse_requirements_file(conf_reqs)
        conflicts = self.validator.detect_conflicts()
        report = self.validator.generate_report()

        self.assertGreater(len(conflicts), 0, "Expected conflicts to be detected for conflicting file")
        self.assertEqual(report["validation_status"], "DEPLOYMENT_BLOCKED")
        self.assertFalse(report["ready_for_deployment"])

        # Check specific colliding package names
        conflicting_pkgs = {c["package"] for c in conflicts}
        self.assertTrue("numpy" in conflicting_pkgs or any("numpy" in p for p in conflicting_pkgs))
        self.assertTrue("flask" in conflicting_pkgs)

    def test_dockerfile_parsing(self):
        """Extracts dependencies accurately from Dockerfile RUN pip install statements."""
        dockerfile_path = os.path.join(os.path.dirname(__file__), "..", "Dockerfile.conflict")
        deps = self.validator.parse_dockerfile(dockerfile_path)

        extracted_names = {d["name"] for d in deps}
        self.assertIn("numpy", extracted_names)
        self.assertIn("scikit-learn", extracted_names)
        self.assertIn("flask", extracted_names)


class TestMonitoringEngine(unittest.TestCase):
    """Test suite for Performance Monitoring Dashboard and Alerting Engine."""

    def setUp(self):
        test_config = {
            "thresholds": {
                "latency_ms": {"warning": 95.0, "critical": 140.0, "metric_label": "Latency", "unit": "ms"},
                "error_rate_pct": {"warning": 1.5, "critical": 5.0, "metric_label": "Error Rate", "unit": "%"}
            },
            "history": {"max_datapoints": 30, "sample_interval_sec": 1.0},
            "simulation": {"default_profile": "normal"}
        }
        self.engine = MetricsEngine(test_config)

    def test_normal_metrics_generate_no_alerts(self):
        """Healthy telemetry points must not trigger alerts."""
        healthy_point = {
            "timestamp": 1000.0,
            "time_label": "12:00:00",
            "latency_avg_ms": 35.0,
            "latency_p95_ms": 42.0,
            "latency_p99_ms": 55.0,
            "rps": 30.0,
            "rpm": 1800,
            "error_rate_pct": 0.2,
            "cpu_usage_pct": 45.0,
            "memory_usage_pct": 52.0,
            "profile": "normal"
        }
        self.engine.record_datapoint(healthy_point)
        self.assertEqual(len(self.engine.active_alerts), 0)

    def test_latency_warning_threshold_trigger(self):
        """p95 Latency of 110ms must trigger a WARNING alert."""
        warn_point = {
            "timestamp": 1002.0,
            "time_label": "12:00:02",
            "latency_avg_ms": 85.0,
            "latency_p95_ms": 110.0,
            "latency_p99_ms": 130.0,
            "rps": 30.0,
            "rpm": 1800,
            "error_rate_pct": 0.5,
            "cpu_usage_pct": 55.0,
            "memory_usage_pct": 55.0,
            "profile": "high_load"
        }
        self.engine.record_datapoint(warn_point)
        self.assertEqual(len(self.engine.active_alerts), 1)
        alert = self.engine.active_alerts[0]
        self.assertEqual(alert["severity"], "WARNING")
        self.assertEqual(alert["metric"], "latency_ms")

    def test_latency_critical_threshold_trigger(self):
        """p95 Latency of 165ms must escalate to a CRITICAL alert."""
        crit_point = {
            "timestamp": 1004.0,
            "time_label": "12:00:04",
            "latency_avg_ms": 130.0,
            "latency_p95_ms": 165.0,
            "latency_p99_ms": 190.0,
            "rps": 30.0,
            "rpm": 1800,
            "error_rate_pct": 0.5,
            "cpu_usage_pct": 55.0,
            "memory_usage_pct": 55.0,
            "profile": "latency_spike"
        }
        self.engine.record_datapoint(crit_point)
        self.assertEqual(len(self.engine.active_alerts), 1)
        alert = self.engine.active_alerts[0]
        self.assertEqual(alert["severity"], "CRITICAL")
        self.assertEqual(alert["metric"], "latency_ms")

    def test_alert_auto_resolution(self):
        """Alerts must auto-resolve when metrics recover below warning thresholds."""
        # Step 1: Trigger alert
        spike_point = {
            "timestamp": 1006.0, "time_label": "12:00:06",
            "latency_avg_ms": 110.0, "latency_p95_ms": 150.0, "latency_p99_ms": 170.0,
            "rps": 30.0, "rpm": 1800, "error_rate_pct": 0.5, "cpu_usage_pct": 50.0,
            "memory_usage_pct": 50.0, "profile": "spike"
        }
        self.engine.record_datapoint(spike_point)
        self.assertEqual(len(self.engine.active_alerts), 1)

        # Step 2: Recover
        recovery_point = {
            "timestamp": 1008.0, "time_label": "12:00:08",
            "latency_avg_ms": 30.0, "latency_p95_ms": 40.0, "latency_p99_ms": 50.0,
            "rps": 30.0, "rpm": 1800, "error_rate_pct": 0.1, "cpu_usage_pct": 40.0,
            "memory_usage_pct": 45.0, "profile": "normal"
        }
        self.engine.record_datapoint(recovery_point)
        self.assertEqual(len(self.engine.active_alerts), 0)


class TestDeploymentOrchestrator(unittest.TestCase):
    """Test suite for Automated Deployment Workflow & Rollback."""

    def setUp(self):
        self.orchestrator = DeploymentOrchestrator()

    def test_successful_canary_rollout(self):
        """Compatible candidate with healthy metrics completes all stages and promotes."""
        candidate_reqs = os.path.join(os.path.dirname(__file__), "..", "requirements_candidate.txt")
        result = self.orchestrator.execute_canary_deployment(
            candidate_version="v1.1.0-test",
            candidate_reqs_path=candidate_reqs
        )

        self.assertEqual(result["status"], "DEPLOYED_AND_ACTIVE")
        self.assertEqual(self.orchestrator.traffic_split["green"], 100)
        self.assertEqual(self.orchestrator.traffic_split["blue"], 0)

    def test_automated_rollback_on_latency_breach(self):
        """Canary stage experiencing latency breach (>100ms) triggers automated rollback to Blue."""
        candidate_reqs = os.path.join(os.path.dirname(__file__), "..", "requirements_candidate.txt")
        result = self.orchestrator.execute_canary_deployment(
            candidate_version="v1.2.0-slow",
            candidate_reqs_path=candidate_reqs,
            inject_fault_at_stage=2,
            fault_type="latency"
        )

        self.assertEqual(result["status"], "ROLLED_BACK_TO_STABLE")
        self.assertIn("p95 Latency", result["trigger_reason"])
        self.assertEqual(self.orchestrator.traffic_split["blue"], 100)
        self.assertEqual(self.orchestrator.traffic_split["green"], 0)

    def test_automated_rollback_on_error_burst(self):
        """Canary stage experiencing error rate > 2.0% triggers automated rollback."""
        candidate_reqs = os.path.join(os.path.dirname(__file__), "..", "requirements_candidate.txt")
        result = self.orchestrator.execute_canary_deployment(
            candidate_version="v1.3.0-buggy",
            candidate_reqs_path=candidate_reqs,
            inject_fault_at_stage=1,
            fault_type="error"
        )

        self.assertEqual(result["status"], "ROLLED_BACK_TO_STABLE")
        self.assertIn("Error rate", result["trigger_reason"])
        self.assertEqual(self.orchestrator.traffic_split["blue"], 100)


class TestHealthAnalyzer(unittest.TestCase):
    """Test suite for System Health Analysis and RCA."""

    def test_health_analysis_and_rca(self):
        """Parses logs, extracts bottlenecks, computes correlation, and generates report."""
        log_path = os.path.join(os.path.dirname(__file__), "..", "logs", "app.log")
        if not os.path.exists(log_path):
            HealthAnalyzer.generate_sample_logs(log_path, num_lines=80)

        analyzer = HealthAnalyzer(log_path)
        report = analyzer.generate_health_report()

        self.assertIn("health_status", report)
        self.assertIn("health_score", report)
        self.assertIn("correlation_analysis", report)
        self.assertGreater(len(report["primary_root_causes"]), 0)
        self.assertGreater(len(report["remediation_plan"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

