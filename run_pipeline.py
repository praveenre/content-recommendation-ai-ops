"""
Master Deployment Pipeline & Operations Orchestrator
Executes the complete end-to-end lifecycle:
1. Dependency Validation Gate
2. Canary Blue/Green Rollout
3. Telemetry Monitoring & Alert Evaluation
4. Automated Rollback Verification
5. Health Observability & Root-Cause Diagnosis
6. Pipeline Test Scorecard
"""

import os
import sys
import time
import json
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.dependency_validator import validate_deployment_files
from src.deployment_orchestrator import DeploymentOrchestrator
from src.health_analyzer import HealthAnalyzer


def print_banner(title: str):
    print("\n" + "=" * 70)
    print(f"  🚀 {title.upper()}")
    print("=" * 70)


def run_complete_pipeline():
    start_time = time.time()
    print_banner("Media Streaming AI Recommendation Deployment Pipeline")
    print("Target SLA: Sub-100ms Inference Latency | 99.9% Production Uptime")

    # -------------------------------------------------------------
    # Step 1: Dependency Validation System
    # -------------------------------------------------------------
    print_banner("Step 1: Dependency Validation System")
    reqs_prod = "requirements.txt"
    dockerfile_prod = "Dockerfile"
    print(f"[*] Scanning container definitions: {reqs_prod}, {dockerfile_prod}...")

    val_report = validate_deployment_files(
        requirements_files=[reqs_prod],
        dockerfiles=[dockerfile_prod],
        output_json="reports/validation_report.json",
        output_md="reports/validation_report.md"
    )

    print(f"[✓] Validation Status: {val_report['validation_status']}")
    print(f"[✓] Tracked Packages: {val_report['summary']['total_packages_tracked']}")
    print(f"[✓] Conflicts Detected: {val_report['summary']['total_conflicts']}")
    print("[✓] Validation reports generated: reports/validation_report.json & .md")

    # -------------------------------------------------------------
    # Step 2 & 3: Automated Deployment Workflow & Canary Rollout
    # -------------------------------------------------------------
    print_banner("Step 2 & 3: Automated Deployment & Canary Release")
    orchestrator = DeploymentOrchestrator()

    # Scenario A: Incompatible candidate rejected by gate
    print("\n[Scenario A] Testing Deployment Gate with Incompatible Candidate (v2.0.0-incompatible)...")
    gate_result = orchestrator.execute_canary_deployment(
        candidate_version="v2.0.0-incompatible",
        candidate_reqs_path="requirements_conflict.txt"
    )
    assert gate_result["status"] == "ABORTED_DEPENDENCY_CONFLICT"
    print(" --> Gate Verification: Succeeded in halting broken deployment before rollout!")

    # Scenario B: Healthy candidate canary rollout
    print("\n[Scenario B] Executing Canary Rollout for Compatible Candidate (v1.1.0)...")
    success_result = orchestrator.execute_canary_deployment(
        candidate_version="v1.1.0",
        candidate_reqs_path="requirements_candidate.txt"
    )
    assert success_result["status"] == "DEPLOYED_AND_ACTIVE"
    print(f" --> Promotion Verification: {success_result['status']} (100% traffic on Green)!")

    # Scenario C: Canary deployment with performance anomaly triggering automated rollback
    print("\n[Scenario C] Executing Canary Rollout with SLA Latency Spike (v1.2.0-slow)...")
    rollback_result = orchestrator.execute_canary_deployment(
        candidate_version="v1.2.0-slow",
        candidate_reqs_path="requirements_candidate.txt",
        inject_fault_at_stage=2,
        fault_type="latency"
    )
    assert rollback_result["status"] == "ROLLED_BACK_TO_STABLE"
    print(f" --> Rollback Verification: {rollback_result['status']}")
    print(f" --> Trigger: {rollback_result['trigger_reason']}")
    print(" --> Traffic safely restored to stable Blue environment!")

    # -------------------------------------------------------------
    # Step 4: System Health Analysis & Root Cause Diagnosis
    # -------------------------------------------------------------
    print_banner("Step 4: System Health Observability & RCA")
    log_file = "logs/app.log"
    print(f"[*] Parsing application log telemetry from {log_file}...")
    if not os.path.exists(log_file):
        HealthAnalyzer.generate_sample_logs(log_file)

    analyzer = HealthAnalyzer(log_file)
    health_rep = analyzer.export_reports(
        json_path="reports/health_report.json",
        md_path="reports/health_report.md"
    )

    print(f"[✓] System Health Status: {health_rep['health_status']} (Score: {health_rep['health_score']}/100)")
    print(f"[✓] Metric Correlation (Stress -> UX): r = {health_rep['correlation_analysis']['pearson_r']} ({health_rep['correlation_analysis']['correlation_strength']})")
    print("[✓] Primary Root Causes Diagnosed:")
    for idx, rc in enumerate(health_rep["primary_root_causes"], 1):
        print(f"    {idx}. [{rc['severity']}] {rc['name']} (Incidents: {rc['count']}, Peak: {rc['max_val']})")
        print(f"       Remediation: {rc['recommendation']}")
    print("[✓] Health reports exported: reports/health_report.json & .md")

    # -------------------------------------------------------------
    # Step 5: Test Verification Scorecard
    # -------------------------------------------------------------
    print_banner("Step 5: Pipeline Test Verification Scorecard")
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=1)
    test_result = runner.run(suite)

    elapsed = round(time.time() - start_time, 2)
    print_banner("Pipeline Execution Summary")
    print(f"Total Execution Time: {elapsed} seconds")
    print(f"Tests Run: {test_result.testsRun}")
    print(f"Failures: {len(test_result.failures)}, Errors: {len(test_result.errors)}")
    print("Deployment Safety Safeguards:")
    print("  [✓] Dependency Validation Gate: OPERATIONAL")
    print("  [✓] Canary Traffic Controller: OPERATIONAL")
    print("  [✓] Performance SLA Alerting: OPERATIONAL")
    print("  [✓] Automated Rollback Engine: OPERATIONAL")
    print("  [✓] Observability & Health RCA: OPERATIONAL")

    if test_result.wasSuccessful():
        print("\n🏆 ALL SYSTEMS VERIFIED & READY FOR PRODUCTION DEPLOYMENT!\n")
        return 0
    else:
        print("\n❌ PIPELINE VERIFICATION FAILED!\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_complete_pipeline())

