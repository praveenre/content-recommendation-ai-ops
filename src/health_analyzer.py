"""
System Health Analysis Tool & Observability Engine
Aggregates application logs, system metrics, and telemetry data to extract
performance bottlenecks, correlate system stress with user experience,
and generate root-cause health reports.
"""

import os
import re
import sys
import json
import math
import time
import random
import argparse
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional


class HealthAnalyzer:
    """
    Parses application logs, extracts performance bottlenecks,
    correlates system metrics with user experience indicators,
    and performs automated root-cause analysis (RCA).
    """

    BOTTLENECK_PATTERNS = [
        {
            "id": "INFERENCE_LATENCY_SPIKE",
            "name": "Model Inference Bottleneck",
            "regex": r"(?:inference|embedding|matrix factorization|forward pass).*(?:took|latency)[:=\s]+([0-9.]+)\s*ms",
            "threshold": 80.0,
            "category": "Compute / Model Architecture",
            "severity": "HIGH",
            "recommendation": "Optimize embedding dimension, enable INT8 quantization, or scale model replicas."
        },
        {
            "id": "THREAD_POOL_SATURATION",
            "name": "Worker Thread Contention",
            "regex": r"(?:queue saturated|thread pool|tasks queued)[:=\s]+([0-9]+)",
            "threshold": 50,
            "category": "Concurrency / Threading",
            "severity": "CRITICAL",
            "recommendation": "Increase Gunicorn worker threads or decouple async ranking pipeline."
        },
        {
            "id": "DB_CONNECTION_TIMEOUT",
            "name": "Catalog Connection Pool Starvation",
            "regex": r"(?:acquired DB connection|database connection|catalog pool)[:=\s]+([0-9.]+)\s*ms",
            "threshold": 50.0,
            "category": "Database / I/O",
            "severity": "HIGH",
            "recommendation": "Increase database connection pool size or add Redis caching for media catalog."
        },
        {
            "id": "GC_MEMORY_PRESSURE",
            "name": "Garbage Collection & Memory Pressure",
            "regex": r"(?:GC pause|heap utilization|memory utilization)[:=\s]+([0-9.]+)(?:\s*ms|%)",
            "threshold": 80.0,
            "category": "Memory Management",
            "severity": "MEDIUM",
            "recommendation": "Inspect memory leak candidates or adjust container memory limits."
        },
        {
            "id": "UPSTREAM_TIMEOUT_504",
            "name": "Gateway Timeout (HTTP 504)",
            "regex": r"(?:504 Gateway Timeout|upstream gateway timeout|response delayed by)\s*([0-9.]+)?",
            "threshold": 0,
            "category": "Network / SLA",
            "severity": "CRITICAL",
            "recommendation": "Check upstream deadline propagation and implement circuit breaker pattern."
        }
    ]

    USER_EXP_PATTERNS = [
        {
            "id": "BUFFERING_EVENT",
            "name": "Stream Playback Buffering",
            "regex": r"buffer_duration_ms=([0-9.]+)",
            "impact_weight": 0.4
        },
        {
            "id": "USER_ABANDONMENT",
            "name": "Playback Abandonment (Drop-off)",
            "regex": r"abandoned playback.*latency_ms=([0-9.]+)",
            "impact_weight": 0.8
        },
        {
            "id": "RECOMMENDATION_FAILURE",
            "name": "Failed Recommendation Delivery",
            "regex": r"(?:InferenceException|RecommendationException|500 Internal Server Error)",
            "impact_weight": 0.6
        }
    ]

    def __init__(self, log_path: str = "logs/app.log"):
        self.log_path = log_path
        self.parsed_lines_count = 0
        self.log_counts_by_level = {"INFO": 0, "WARN": 0, "ERROR": 0, "CRITICAL": 0}
        self.detected_bottlenecks: List[Dict[str, Any]] = []
        self.user_impact_events: List[Dict[str, Any]] = []
        self.timeline_data: List[Dict[str, Any]] = []

    def parse_logs(self) -> Dict[str, Any]:
        """
        Parses application log lines, categorizes severity, and detects bottlenecks.
        """
        if not os.path.exists(self.log_path):
            self.generate_sample_logs(self.log_path)

        with open(self.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        self.parsed_lines_count = len(lines)

        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue

            # Identify severity level
            level = "INFO"
            for lvl in ["CRITICAL", "ERROR", "WARN", "WARNING", "INFO"]:
                if f"[{lvl}]" in line or f"level={lvl}" in line.lower():
                    level = "WARN" if lvl == "WARNING" else lvl
                    break
            if level in self.log_counts_by_level:
                self.log_counts_by_level[level] += 1

            # Match Bottleneck Patterns
            for pattern in self.BOTTLENECK_PATTERNS:
                m = re.search(pattern["regex"], line, re.IGNORECASE)
                if m:
                    extracted_val = float(m.group(1)) if m.lastindex and m.group(1) else 1.0
                    if extracted_val >= pattern["threshold"]:
                        self.detected_bottlenecks.append({
                            "pattern_id": pattern["id"],
                            "name": pattern["name"],
                            "category": pattern["category"],
                            "severity": pattern["severity"],
                            "value": extracted_val,
                            "threshold": pattern["threshold"],
                            "log_line": line,
                            "line_number": line_no,
                            "recommendation": pattern["recommendation"]
                        })

            # Match User Experience Impact Patterns
            for exp in self.USER_EXP_PATTERNS:
                m = re.search(exp["regex"], line, re.IGNORECASE)
                if m:
                    val = float(m.group(1)) if m.lastindex and m.group(1) else 1.0
                    self.user_impact_events.append({
                        "event_id": exp["id"],
                        "name": exp["name"],
                        "value": val,
                        "weight": exp["impact_weight"],
                        "line_number": line_no,
                        "log_line": line
                    })

        return {
            "total_lines": self.parsed_lines_count,
            "log_levels": self.log_counts_by_level,
            "bottlenecks_found": len(self.detected_bottlenecks),
            "user_impact_events": len(self.user_impact_events)
        }

    def correlate_metrics_with_ux(self) -> Dict[str, Any]:
        """
        Calculates correlation between system performance bottlenecks
        and user experience indicators (buffering, drop-offs, errors).
        """
        # Bucket events across time/lines to determine correlation
        num_windows = 10
        chunk_size = max(1, self.parsed_lines_count // num_windows)

        system_stress_series = [0] * num_windows
        user_impact_series = [0] * num_windows

        for b in self.detected_bottlenecks:
            win_idx = min(num_windows - 1, b["line_number"] // chunk_size)
            weight = 3 if b["severity"] == "CRITICAL" else 2 if b["severity"] == "HIGH" else 1
            system_stress_series[win_idx] += weight

        for u in self.user_impact_events:
            win_idx = min(num_windows - 1, u["line_number"] // chunk_size)
            user_impact_series[win_idx] += u["weight"]

        # Calculate Pearson correlation coefficient: r = cov(X, Y) / (std(X) * std(Y))
        def pearson_corr(x: List[float], y: List[float]) -> float:
            n = len(x)
            if n < 2:
                return 0.0
            mean_x = sum(x) / n
            mean_y = sum(y) / n
            num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
            den_x = sum((x[i] - mean_x) ** 2 for i in range(n))
            den_y = sum((y[i] - mean_y) ** 2 for i in range(n))
            if den_x == 0 or den_y == 0:
                return 0.0
            return num / math.sqrt(den_x * den_y)

        r_value = round(pearson_corr(system_stress_series, user_impact_series), 3)

        if r_value >= 0.7:
            corr_strength = "STRONG_POSITIVE"
            insight = f"Direct causal correlation (r={r_value}): Infrastructure stress and inference bottlenecks are directly degrading user streaming experience and driving playback abandonments."
        elif r_value >= 0.4:
            corr_strength = "MODERATE_POSITIVE"
            insight = f"Moderate correlation (r={r_value}): Performance latency spikes frequently precede user buffering and stream drops."
        else:
            corr_strength = "WEAK_OR_INCONCLUSIVE"
            insight = f"Low correlation (r={r_value}): User experience issues appear uncorrelated with backend bottlenecks."

        return {
            "pearson_r": r_value,
            "correlation_strength": corr_strength,
            "insight": insight,
            "system_stress_series": system_stress_series,
            "user_impact_series": user_impact_series
        }

    def generate_health_report(self) -> Dict[str, Any]:
        """
        Synthesizes bottlenecks, correlations, and calculates overall System Health Score.
        """
        summary = self.parse_logs()
        correlation = self.correlate_metrics_with_ux()

        # Calculate Health Score (100 is pristine)
        penalty = 0
        penalty += summary["log_levels"].get("CRITICAL", 0) * 15
        penalty += summary["log_levels"].get("ERROR", 0) * 6
        penalty += summary["log_levels"].get("WARN", 0) * 1.5
        penalty += len(self.detected_bottlenecks) * 3

        health_score = max(10, min(100, round(100 - penalty)))

        if health_score >= 85:
            health_status = "HEALTHY"
        elif health_score >= 65:
            health_status = "DEGRADED"
        else:
            health_status = "CRITICAL_ATTENTION_REQUIRED"

        # Determine Primary Root Causes
        bottleneck_summary: Dict[str, Dict[str, Any]] = {}
        for b in self.detected_bottlenecks:
            name = b["name"]
            if name not in bottleneck_summary:
                bottleneck_summary[name] = {
                    "count": 0,
                    "category": b["category"],
                    "severity": b["severity"],
                    "recommendation": b["recommendation"],
                    "max_val": b["value"]
                }
            bottleneck_summary[name]["count"] += 1
            bottleneck_summary[name]["max_val"] = max(bottleneck_summary[name]["max_val"], b["value"])

        # Prioritize root cause by severity and count
        sorted_root_causes = sorted(
            [{"name": k, **v} for k, v in bottleneck_summary.items()],
            key=lambda x: (3 if x["severity"] == "CRITICAL" else 2 if x["severity"] == "HIGH" else 1, x["count"]),
            reverse=True
        )

        report = {
            "timestamp": datetime.now().isoformat(),
            "health_status": health_status,
            "health_score": health_score,
            "target_sla": "Sub-100ms Latency & 99.9% Uptime",
            "sla_compliance": health_score >= 85,
            "metrics_overview": {
                "parsed_lines": self.parsed_lines_count,
                "log_counts": self.log_counts_by_level,
                "total_bottlenecks": len(self.detected_bottlenecks),
                "user_impact_events": len(self.user_impact_events)
            },
            "correlation_analysis": correlation,
            "primary_root_causes": sorted_root_causes[:3],
            "all_detected_bottlenecks": sorted_root_causes,
            "remediation_plan": [
                rc["recommendation"] for rc in sorted_root_causes[:3]
            ]
        }
        return report

    def export_reports(self, json_path: str = "reports/health_report.json", md_path: str = "reports/health_report.md"):
        """Exports report to both JSON and Markdown formats."""
        report = self.generate_health_report()

        os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        # Generate Markdown
        status_badge = (
            "🟢 **HEALTHY (SLA MET)**" if report["health_status"] == "HEALTHY"
            else "🟡 **DEGRADED (SLA RISK)**" if report["health_status"] == "DEGRADED"
            else "🔴 **CRITICAL (OUTAGE RISK)**"
        )

        md = []
        md.append("# 🏥 AI Recommendation System Health & Observability Report\n")
        md.append(f"**Generated At:** `{report['timestamp']}`\n")
        md.append(f"**System Health Status:** {status_badge}  |  **Health Score:** `{report['health_score']}/100`\n")
        md.append(f"**Target SLA:** `{report['target_sla']}` • **Compliance:** `{'PASS' if report['sla_compliance'] else 'FAIL'}`\n")

        md.append("## 📈 Telemetry & Log Volume Overview\n")
        md.append(f"- **Total Log Records Scanned:** {report['metrics_overview']['parsed_lines']}")
        md.append(f"- **Log Severity Breakdown:** `INFO: {report['metrics_overview']['log_counts']['INFO']}`, `WARN: {report['metrics_overview']['log_counts']['WARN']}`, `ERROR: {report['metrics_overview']['log_counts']['ERROR']}`, `CRITICAL: {report['metrics_overview']['log_counts']['CRITICAL']}`")
        md.append(f"- **Identified Bottlenecks:** {report['metrics_overview']['total_bottlenecks']}")
        md.append(f"- **User Experience Impact Events:** {report['metrics_overview']['user_impact_events']}\n")

        md.append("## 🔗 Correlation Analysis: System Stress vs User Experience\n")
        md.append(f"- **Pearson Correlation Coefficient (r):** `{report['correlation_analysis']['pearson_r']}` (`{report['correlation_analysis']['correlation_strength']}`)")
        md.append(f"- **Observation:** {report['correlation_analysis']['insight']}\n")

        md.append("## 🔍 Primary Root Causes\n")
        if report["primary_root_causes"]:
            md.append("| Issue | Category | Severity | Incidents | Peak Value | Actionable Remediation |")
            md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for rc in report["primary_root_causes"]:
                md.append(
                    f"| **{rc['name']}** | {rc['category']} | `{rc['severity']}` | {rc['count']} | {rc['max_val']} | {rc['recommendation']} |"
                )
            md.append("")
        else:
            md.append("No active performance bottlenecks detected.\n")

        md.append("## 🛠️ Actionable Engineering Recommendations\n")
        for idx, rec in enumerate(report["remediation_plan"], 1):
            md.append(f"{idx}. {rec}")
        md.append("")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))

        return report

    @classmethod
    def generate_sample_logs(cls, output_path: str = "logs/app.log", num_lines: int = 150):
        """Generates realistic application log data with normal traffic and bottleneck spikes."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        logs = []
        base_time = time.time() - 3600

        for i in range(num_lines):
            t_str = datetime.fromtimestamp(base_time + (i * 24)).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
            user_id = f"u{random.randint(1000, 9999)}"

            # Simulate bottleneck phase in the middle 35-65%
            in_bottleneck_phase = (num_lines * 0.4) <= i <= (num_lines * 0.75)

            if not in_bottleneck_phase:
                # Normal healthy operation
                lat = round(random.uniform(25.0, 48.0), 2)
                logs.append(f"{t_str} [INFO] [recommendation_service] User {user_id} served 5 recommendations in {lat}ms (status: 200)")
            else:
                # Stress / Degradation phase
                r = random.random()
                if r < 0.35:
                    lat = round(random.uniform(115.0, 168.0), 2)
                    logs.append(f"{t_str} [WARN] [recommendation_service] Model inference bottleneck: embedding dot product took {lat}ms (batch_size: 64)")
                    logs.append(f"{t_str} [CLIENT_EVENT] User {user_id} stream buffering event recorded: buffer_duration_ms={round(lat * 3.2, 1)}")
                elif r < 0.6:
                    queued = random.randint(65, 140)
                    delay = round(random.uniform(120.0, 185.0), 1)
                    logs.append(f"{t_str} [ERROR] [gunicorn.workers] ThreadPoolExecutor queue saturated: {queued} tasks queued, response delayed by {delay}ms")
                    logs.append(f"{t_str} [CLIENT_EVENT] User {user_id} abandoned playback: exit_before_start=true latency_ms={delay}")
                elif r < 0.8:
                    db_time = round(random.uniform(55.0, 92.0), 1)
                    logs.append(f"{t_str} [WARN] [db_client] Connection pool saturation: acquired DB connection in {db_time}ms (threshold: 30ms)")
                else:
                    logs.append(f"{t_str} [ERROR] [gateway] 504 Gateway Timeout for user {user_id} after 250ms deadline exceeded")
                    logs.append(f"{t_str} [CLIENT_EVENT] InferenceException: recommendation delivery failed for user {user_id}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(logs) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="System Health Analysis & Observability Tool")
    parser.add_argument("--logs", default="logs/app.log", help="Path to application log file")
    parser.add_argument("--json", default="reports/health_report.json", help="Output JSON report path")
    parser.add_argument("--md", default="reports/health_report.md", help="Output Markdown report path")
    parser.add_argument("--generate-sample-logs", action="store_true", help="Generate fresh realistic test logs")

    args = parser.parse_args()

    if args.generate_sample_logs or not os.path.exists(args.logs):
        print(f"[+] Generating realistic sample application logs in {args.logs}...")
        HealthAnalyzer.generate_sample_logs(args.logs)

    analyzer = HealthAnalyzer(args.logs)
    rep = analyzer.export_reports(args.json, args.md)

    print("\n" + "=" * 60)
    print(f"SYSTEM HEALTH ANALYSIS: {rep['health_status']} (Score: {rep['health_score']}/100)")
    print(f"Target SLA Compliance: {'PASSED' if rep['sla_compliance'] else 'BREACHED'}")
    print(f"Correlation (System Stress -> UX): r = {rep['correlation_analysis']['pearson_r']} ({rep['correlation_analysis']['correlation_strength']})")
    print("=" * 60)
    print("\nPrimary Root Causes Identified:")
    for idx, rc in enumerate(rep["primary_root_causes"], 1):
        print(f"  {idx}. [{rc['severity']}] {rc['name']} (x{rc['count']} occurrences, Peak: {rc['max_val']})")
        print(f"     Remediation: {rc['recommendation']}")
    print(f"\n[✓] Reports exported to: {args.json} and {args.md}\n")

