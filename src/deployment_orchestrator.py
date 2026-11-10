"""
Automated Deployment Orchestrator
Manages Blue/Green environment switching, canary traffic routing,
and automated rollback triggers based on real-time performance thresholds.
"""

import os
import sys
import time
import json
import yaml
import random
import logging
from typing import Dict, List, Any, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.dependency_validator import DependencyValidator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [Orchestrator] %(message)s'
)
logger = logging.getLogger("DeploymentOrchestrator")

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "deployment_config.yaml")


class DeploymentOrchestrator:
    """
    Automates progressive canary deployments and safeguards uptime
    via automated rollbacks when performance SLA thresholds are breached.
    """

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.blue_env = dict(self.config["environments"]["blue"])
        self.green_env = dict(self.config["environments"]["green"])
        self.traffic_split = {"blue": 100, "green": 0}
        self.active_production_env = "blue"
        self.deployment_history: List[Dict[str, Any]] = []

    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Deployment config not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def validate_candidate_dependencies(
        self,
        candidate_reqs_path: str,
        dockerfile_path: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Gate 1: Verifies dependency compatibility before spinning up candidate instances.
        """
        logger.info(f"Running Pre-Deployment Dependency Gate on: {candidate_reqs_path}")
        validator = DependencyValidator()
        validator.parse_requirements_file(candidate_reqs_path)
        
        base_reqs = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
        if os.path.exists(base_reqs) and os.path.abspath(base_reqs) != os.path.abspath(candidate_reqs_path):
            validator.parse_requirements_file(base_reqs)

        if dockerfile_path and os.path.exists(dockerfile_path):
            validator.parse_dockerfile(dockerfile_path)

        validator.detect_conflicts()
        report = validator.generate_report()

        if not report["ready_for_deployment"]:
            logger.error(f"Deployment Gate REJECTED: {len(report['conflicts'])} dependency conflict(s) found!")
            return False, report

        logger.info("Deployment Gate PASSED: All dependencies compatible.")
        return True, report

    def simulate_container_healthcheck(self, env_name: str, port: int) -> bool:
        """Simulates container healthcheck probe."""
        logger.info(f"Probing container health on {env_name} (port {port}/api/health)...")
        time.sleep(0.5)
        return True

    def sample_canary_metrics(
        self,
        green_traffic_pct: int,
        inject_fault: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Samples simulated or live metrics during a canary soak stage.
        Supports fault injection to demonstrate automated rollback triggers.
        """
        if inject_fault == "latency":
            # Simulate recommendation latency degradation exceeding 100ms SLA
            latency_p95 = round(random.uniform(125.0, 160.0), 2)
            latency_avg = round(latency_p95 * 0.85, 2)
            error_rate = round(random.uniform(0.2, 0.8), 2)
            cpu = round(random.uniform(86.0, 93.0), 1)
        elif inject_fault == "error":
            # Simulate high error burst
            latency_p95 = round(random.uniform(40.0, 65.0), 2)
            latency_avg = round(latency_p95 * 0.8, 2)
            error_rate = round(random.uniform(4.5, 9.5), 2)
            cpu = round(random.uniform(50.0, 65.0), 1)
        else:
            # Healthy normal candidate performance meeting sub-100ms SLA
            latency_p95 = round(random.uniform(32.0, 52.0), 2)
            latency_avg = round(latency_p95 * 0.78, 2)
            error_rate = round(random.uniform(0.0, 0.3), 2)
            cpu = round(random.uniform(40.0, 58.0), 1)

        return {
            "latency_p95_ms": latency_p95,
            "latency_avg_ms": latency_avg,
            "error_rate_pct": error_rate,
            "cpu_pct": cpu,
            "green_traffic_pct": green_traffic_pct
        }

    def evaluate_rollback_conditions(
        self,
        metrics: Dict[str, float]
    ) -> Tuple[bool, Optional[str]]:
        """
        Checks if candidate performance metrics violate rollback thresholds.
        """
        triggers = self.config.get("rollback_triggers", {})
        max_latency = triggers.get("max_latency_p95_ms", 100.0)
        max_error = triggers.get("max_error_rate_pct", 2.0)
        max_cpu = triggers.get("max_cpu_pct", 85.0)

        if metrics["latency_p95_ms"] > max_latency:
            reason = f"p95 Latency {metrics['latency_p95_ms']}ms breached SLA threshold ({max_latency}ms)"
            return True, reason

        if metrics["error_rate_pct"] > max_error:
            reason = f"Error rate {metrics['error_rate_pct']}% breached threshold ({max_error}%)"
            return True, reason

        if metrics["cpu_pct"] > max_cpu:
            reason = f"CPU utilization {metrics['cpu_pct']}% breached safety threshold ({max_cpu}%)"
            return True, reason

        return False, None

    def execute_rollback(self, trigger_reason: str, failed_stage: int) -> Dict[str, Any]:
        """
        Executes automated rollback: restores 100% traffic to stable Blue environment.
        """
        logger.warning("=" * 60)
        logger.warning(f"🚨 AUTOMATED ROLLBACK INITIATED AT STAGE {failed_stage}!")
        logger.warning(f"Reason: {trigger_reason}")
        logger.warning("=" * 60)

        # Instant traffic redirect to Blue
        self.traffic_split = {"blue": 100, "green": 0}
        self.green_env["healthy"] = False
        self.green_env["role"] = "isolated_failed"

        event = {
            "action": "AUTOMATED_ROLLBACK",
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "trigger_reason": trigger_reason,
            "failed_stage": failed_stage,
            "active_version": self.blue_env["version"],
            "traffic_split": dict(self.traffic_split),
            "status": "ROLLED_BACK_TO_STABLE"
        }
        self.deployment_history.append(event)
        self._save_history()

        logger.info(f"Rollback Complete: 100% traffic routed back to {self.blue_env['version']} (Blue).")
        return event

    def execute_canary_deployment(
        self,
        candidate_version: str,
        candidate_reqs_path: str,
        inject_fault_at_stage: Optional[int] = None,
        fault_type: Optional[str] = "latency"
    ) -> Dict[str, Any]:
        """
        Executes the end-to-end canary deployment lifecycle:
        1. Dependency Gate Check
        2. Environment Provisioning & Health Probe
        3. Progressive Canary Traffic Stages (10% -> 25% -> 50% -> 100%)
        4. Real-time metric evaluation & automated rollback trigger
        5. Cutover & Promotion
        """
        logger.info(f"Starting Canary Deployment for candidate {candidate_version}")
        self.green_env["version"] = candidate_version

        # Step 1: Pre-flight Dependency Gate
        passed, val_report = self.validate_candidate_dependencies(candidate_reqs_path)
        if not passed:
            result = {
                "status": "ABORTED_DEPENDENCY_CONFLICT",
                "candidate_version": candidate_version,
                "reason": "Candidate dependencies failed compatibility validation.",
                "conflicts": val_report.get("conflicts", []),
                "traffic_split": self.traffic_split
            }
            self.deployment_history.append(result)
            self._save_history()
            return result

        # Step 2: Spin up Green candidate instance
        healthy = self.simulate_container_healthcheck("Green Candidate", self.green_env["port"])
        if not healthy:
            return self.execute_rollback("Candidate container failed initial health probe", 0)

        # Step 3: Progressive Canary Stages
        stages = self.config.get("canary_stages", [])
        for stage_cfg in stages:
            stage_num = stage_cfg["stage"]
            green_pct = stage_cfg["traffic_pct_green"]
            blue_pct = 100 - green_pct
            soak_time = stage_cfg.get("soak_time_sec", 2)

            self.traffic_split = {"blue": blue_pct, "green": green_pct}
            logger.info(f"\n--- [Stage {stage_num}/{len(stages)}] Traffic Split: Blue={blue_pct}%, Green={green_pct}% ---")
            logger.info(f"Soaking for {soak_time}s to observe operational health...")
            time.sleep(soak_time)

            # Check if fault is scheduled for injection at this stage
            current_fault = fault_type if (inject_fault_at_stage == stage_num) else None
            metrics = self.sample_canary_metrics(green_pct, inject_fault=current_fault)

            logger.info(
                f"Metrics Sample: p95 Latency={metrics['latency_p95_ms']}ms, "
                f"Error Rate={metrics['error_rate_pct']}%, CPU={metrics['cpu_pct']}%"
            )

            # Evaluate rollback triggers
            should_rollback, reason = self.evaluate_rollback_conditions(metrics)
            if should_rollback:
                rollback_event = self.execute_rollback(reason, stage_num)
                rollback_event["metrics_at_failure"] = metrics
                return rollback_event

        # Step 4: Promotion & Cutover
        logger.info("=" * 60)
        logger.info(f"🎉 CANARY COMPLETED SUCCESSFULLY! Promoting {candidate_version} to Production.")
        logger.info("=" * 60)

        self.traffic_split = {"blue": 0, "green": 100}
        self.active_production_env = "green"
        # Blue becomes standby, Green becomes primary
        self.blue_env["role"] = "standby_previous"
        self.green_env["role"] = "production"

        event = {
            "action": "PROMOTION_SUCCESS",
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "candidate_version": candidate_version,
            "status": "DEPLOYED_AND_ACTIVE",
            "traffic_split": dict(self.traffic_split),
            "final_metrics": metrics
        }
        self.deployment_history.append(event)
        self._save_history()
        return event

    def _save_history(self):
        log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
        os.makedirs(log_dir, exist_ok=True)
        hist_file = os.path.join(log_dir, "deployment_history.json")
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump(self.deployment_history, f, indent=2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Automated Deployment Orchestrator")
    parser.add_argument("--candidate", default="v1.1.0", help="Candidate version string")
    parser.add_argument("--reqs", default="requirements_candidate.txt", help="Candidate requirements file")
    parser.add_argument("--fault-stage", type=int, default=None, help="Inject fault at stage (1-4) to test rollback")
    parser.add_argument("--fault-type", default="latency", choices=["latency", "error"], help="Type of fault to inject")
    parser.add_argument("--status", action="store_true", help="Print current deployment state")

    args = parser.parse_args()
    orchestrator = DeploymentOrchestrator()

    if args.status:
        print("\n=== DEPLOYMENT ENVIRONMENT STATUS ===")
        print(f"Active Production: {orchestrator.active_production_env}")
        print(f"Traffic Split: Blue={orchestrator.traffic_split['blue']}%, Green={orchestrator.traffic_split['green']}%")
        print(f"Blue Env: {orchestrator.blue_env}")
        print(f"Green Env: {orchestrator.green_env}\n")
        sys.exit(0)

    result = orchestrator.execute_canary_deployment(
        candidate_version=args.candidate,
        candidate_reqs_path=args.reqs,
        inject_fault_at_stage=args.fault_stage,
        fault_type=args.fault_type
    )

    print("\n" + "=" * 60)
    print(f"DEPLOYMENT RESULT: {result.get('status')}")
    if result.get("status") == "DEPLOYED_AND_ACTIVE":
        print(f"Successfully promoted {args.candidate} to production!")
    elif result.get("status") == "ROLLED_BACK_TO_STABLE":
        print(f"Rollback Triggered: {result.get('trigger_reason')}")
    elif result.get("status") == "ABORTED_DEPENDENCY_CONFLICT":
        print(f"Deployment Aborted: {result.get('reason')}")
    print("=" * 60 + "\n")
