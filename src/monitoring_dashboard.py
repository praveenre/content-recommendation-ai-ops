"""
Performance Monitoring Dashboard & Alerting Engine
Flask-based monitoring dashboard displaying system KPIs, performance trends,
and triggering multi-level alerts based on configurable thresholds.
"""

import os
import time
import math
import yaml
import random
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional
from flask import Flask, render_template, jsonify, request

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "..", "static")
)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "monitoring_config.yaml")

# Load configuration
def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "thresholds": {
            "latency_ms": {"warning": 95.0, "critical": 140.0, "metric_label": "Inference Latency", "unit": "ms"},
            "error_rate_pct": {"warning": 1.5, "critical": 5.0, "metric_label": "Error Rate", "unit": "%"},
            "cpu_usage_pct": {"warning": 80.0, "critical": 90.0, "metric_label": "CPU Usage", "unit": "%"},
            "memory_usage_pct": {"warning": 80.0, "critical": 92.0, "metric_label": "Memory Usage", "unit": "%"}
        },
        "history": {"max_datapoints": 60, "sample_interval_sec": 2.0},
        "simulation": {"default_profile": "normal"}
    }

CONFIG = load_config()


class MetricsEngine:
    """Thread-safe store for real-time and historical performance metrics and alerts."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.lock = threading.Lock()
        self.max_points = config.get("history", {}).get("max_datapoints", 60)
        self.history: List[Dict[str, Any]] = []
        self.active_alerts: List[Dict[str, Any]] = []
        self.alert_history: List[Dict[str, Any]] = []
        self.alert_counter = 0
        self.simulation_profile = config.get("simulation", {}).get("default_profile", "normal")
        self.current_deployment_version = "v1.0.0 (Blue - Stable)"
        self.canary_traffic_pct = 0
        self.memory_leak_accum = 0.0

        # Initialize with baseline historical data points
        self._seed_initial_history()

    def _seed_initial_history(self):
        now = time.time()
        for i in range(25, -1, -1):
            ts = now - (i * 2)
            pt = self._generate_simulated_datapoint(ts, profile="normal")
            self.history.append(pt)

    def _generate_simulated_datapoint(self, timestamp: float, profile: str) -> Dict[str, Any]:
        """Generates realistic metrics reflecting specific operational conditions."""
        time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

        if profile == "normal":
            latency = random.uniform(28.0, 48.0)
            rpm = random.randint(1800, 2400)
            rps = round(rpm / 60.0, 1)
            error_rate = round(random.uniform(0.0, 0.4), 2)
            cpu = round(random.uniform(35.0, 55.0), 1)
            memory = round(random.uniform(48.0, 58.0), 1)

        elif profile == "high_load":
            latency = random.uniform(72.0, 94.0)
            rpm = random.randint(4800, 6200)
            rps = round(rpm / 60.0, 1)
            error_rate = round(random.uniform(0.6, 1.4), 2)
            cpu = round(random.uniform(76.0, 84.0), 1)
            memory = round(random.uniform(68.0, 78.0), 1)

        elif profile == "latency_spike":
            # Exceeds sub-100ms SLA, triggering WARNING and CRITICAL thresholds
            latency = random.uniform(135.0, 185.0)
            rpm = random.randint(3500, 4500)
            rps = round(rpm / 60.0, 1)
            error_rate = round(random.uniform(1.8, 3.5), 2)
            cpu = round(random.uniform(88.0, 95.0), 1)
            memory = round(random.uniform(70.0, 82.0), 1)

        elif profile == "error_burst":
            # Significant error burst
            latency = random.uniform(55.0, 85.0)
            rpm = random.randint(2200, 3100)
            rps = round(rpm / 60.0, 1)
            error_rate = round(random.uniform(6.5, 14.2), 2)
            cpu = round(random.uniform(60.0, 75.0), 1)
            memory = round(random.uniform(55.0, 65.0), 1)

        elif profile == "memory_leak":
            self.memory_leak_accum = min(self.memory_leak_accum + 1.2, 40.0)
            latency = random.uniform(40.0, 70.0) + (self.memory_leak_accum * 1.5)
            rpm = random.randint(2000, 2600)
            rps = round(rpm / 60.0, 1)
            error_rate = round(random.uniform(0.2, 1.8), 2)
            cpu = round(random.uniform(50.0, 70.0), 1)
            memory = round(min(55.0 + self.memory_leak_accum, 96.5), 1)

        else:
            latency = random.uniform(30.0, 50.0)
            rps = 35.0
            rpm = 2100
            error_rate = 0.1
            cpu = 40.0
            memory = 50.0

        p95_latency = round(latency * 1.18, 2)
        p99_latency = round(latency * 1.45, 2)

        return {
            "timestamp": timestamp,
            "time_label": time_str,
            "latency_avg_ms": round(latency, 2),
            "latency_p95_ms": p95_latency,
            "latency_p99_ms": p99_latency,
            "rps": rps,
            "rpm": rpm,
            "error_rate_pct": error_rate,
            "cpu_usage_pct": cpu,
            "memory_usage_pct": memory,
            "profile": profile
        }

    def record_datapoint(self, point: Dict[str, Any]):
        """Records a new datapoint and runs threshold alerting logic."""
        with self.lock:
            self.history.append(point)
            if len(self.history) > self.max_points:
                self.history.pop(0)

            self._evaluate_thresholds(point)

    def generate_next_sample(self) -> Dict[str, Any]:
        """Generates the next sample based on current simulation profile."""
        pt = self._generate_simulated_datapoint(time.time(), self.simulation_profile)
        self.record_datapoint(pt)
        return pt

    def _evaluate_thresholds(self, point: Dict[str, Any]):
        """Evaluates metrics against configured WARNING and CRITICAL thresholds."""
        thresholds = self.config.get("thresholds", {})
        active_keys = set()

        metric_mapping = {
            "latency_ms": point["latency_p95_ms"],
            "error_rate_pct": point["error_rate_pct"],
            "cpu_usage_pct": point["cpu_usage_pct"],
            "memory_usage_pct": point["memory_usage_pct"]
        }

        for metric_key, val in metric_mapping.items():
            rule = thresholds.get(metric_key)
            if not rule:
                continue

            warn_thresh = rule.get("warning")
            crit_thresh = rule.get("critical")
            label = rule.get("metric_label", metric_key)
            unit = rule.get("unit", "")

            severity = None
            thresh_hit = None

            if crit_thresh is not None and val >= crit_thresh:
                severity = "CRITICAL"
                thresh_hit = crit_thresh
            elif warn_thresh is not None and val >= warn_thresh:
                severity = "WARNING"
                thresh_hit = warn_thresh

            if severity:
                active_keys.add(metric_key)
                # Check if this alert is already active
                existing = next((a for a in self.active_alerts if a["metric"] == metric_key), None)
                if existing:
                    existing["value"] = val
                    existing["severity"] = severity
                    existing["threshold"] = thresh_hit
                    existing["updated_at"] = point["time_label"]
                else:
                    self.alert_counter += 1
                    alert = {
                        "id": f"ALT-{self.alert_counter:04d}",
                        "timestamp": point["time_label"],
                        "updated_at": point["time_label"],
                        "metric": metric_key,
                        "metric_label": label,
                        "value": val,
                        "threshold": thresh_hit,
                        "unit": unit,
                        "severity": severity,
                        "status": "ACTIVE",
                        "message": f"{label} exceeded {severity} threshold ({val}{unit} >= {thresh_hit}{unit})"
                    }
                    self.active_alerts.append(alert)
                    self.alert_history.insert(0, alert)

        # Auto-resolve alerts that fell below warning thresholds
        remaining_alerts = []
        for alert in self.active_alerts:
            m_key = alert["metric"]
            if m_key not in active_keys:
                alert["status"] = "RESOLVED"
                alert["resolved_at"] = point["time_label"]
            else:
                remaining_alerts.append(alert)
        self.active_alerts = remaining_alerts

    def get_latest_metrics(self) -> Dict[str, Any]:
        with self.lock:
            latest = self.history[-1] if self.history else self._generate_simulated_datapoint(time.time(), "normal")
            return {
                "current": latest,
                "history": list(self.history),
                "active_alerts": list(self.active_alerts),
                "alert_history": self.alert_history[:20],
                "simulation_profile": self.simulation_profile,
                "deployment_version": self.current_deployment_version,
                "canary_traffic_pct": self.canary_traffic_pct
            }

    def set_simulation_profile(self, profile: str):
        with self.lock:
            self.simulation_profile = profile
            if profile != "memory_leak":
                self.memory_leak_accum = 0.0

    def clear_alerts(self):
        with self.lock:
            for a in self.active_alerts:
                a["status"] = "ACKNOWLEDGED"
            self.active_alerts = []


ENGINE = MetricsEngine(CONFIG)

# Background worker for ongoing telemetry generation
def background_telemetry_worker():
    while True:
        try:
            ENGINE.generate_next_sample()
        except Exception:
            pass
        time.sleep(CONFIG.get("history", {}).get("sample_interval_sec", 2.0))

worker_thread = threading.Thread(target=background_telemetry_worker, daemon=True)
worker_thread.start()


# --- HTTP Routes ---

@app.route("/")
def index():
    """Renders the performance monitoring dashboard UI."""
    data = ENGINE.get_latest_metrics()
    return render_template(
        "dashboard.html",
        initial_data=data,
        config=CONFIG
    )

@app.route("/api/metrics", methods=["GET"])
def api_metrics():
    """Returns real-time and historical KPI metrics."""
    return jsonify(ENGINE.get_latest_metrics()), 200

@app.route("/api/metrics/push", methods=["POST"])
def api_push_metrics():
    """Allows external services/orchestrators to push external metrics."""
    data = request.get_json(force=True) or {}
    if "latency_p95_ms" in data or "latency_avg_ms" in data:
        now = time.time()
        point = {
            "timestamp": now,
            "time_label": datetime.fromtimestamp(now).strftime("%H:%M:%S"),
            "latency_avg_ms": data.get("latency_avg_ms", 35.0),
            "latency_p95_ms": data.get("latency_p95_ms", 45.0),
            "latency_p99_ms": data.get("latency_p99_ms", 60.0),
            "rps": data.get("rps", 30.0),
            "rpm": data.get("rpm", 1800),
            "error_rate_pct": data.get("error_rate_pct", 0.0),
            "cpu_usage_pct": data.get("cpu_usage_pct", 40.0),
            "memory_usage_pct": data.get("memory_usage_pct", 50.0),
            "profile": data.get("profile", "external")
        }
        ENGINE.record_datapoint(point)
        return jsonify({"status": "recorded", "point": point}), 200
    return jsonify({"error": "Invalid metric payload"}), 400

@app.route("/api/alerts", methods=["GET"])
def api_alerts():
    """Returns active and acknowledged alerts."""
    with ENGINE.lock:
        return jsonify({
            "active_alerts": ENGINE.active_alerts,
            "history": ENGINE.alert_history[:30],
            "total_active": len(ENGINE.active_alerts)
        }), 200

@app.route("/api/alerts/clear", methods=["POST"])
def api_clear_alerts():
    """Acknowledges and clears active alerts."""
    ENGINE.clear_alerts()
    return jsonify({"status": "cleared"}), 200

@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    """Switches the traffic profile to test alert thresholds."""
    data = request.get_json(silent=True) or {}
    profile = data.get("profile", "normal")
    ENGINE.set_simulation_profile(profile)
    return jsonify({
        "status": "profile_updated",
        "current_profile": profile
    }), 200

@app.route("/api/health", methods=["GET"])
def api_health():
    """Monitoring system health check."""
    return jsonify({
        "status": "healthy",
        "service": "performance-monitoring-engine",
        "uptime": round(time.time() - ENGINE.history[0]["timestamp"], 2) if ENGINE.history else 0
    }), 200


if __name__ == "__main__":
    port = int(os.getenv("MONITOR_PORT", 5001))
    print(f"\n🚀 Launching Performance Monitoring Dashboard on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

