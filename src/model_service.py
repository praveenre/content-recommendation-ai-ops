"""
Content Recommendation AI Model Service
Media Streaming Platform - Production Model Microservice
"""

import time
import random
import os
import logging
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s'
)
logger = logging.getLogger("recommendation_service")

app = Flask(__name__)

# Service metadata & runtime configuration
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "v1.0.0")
ENVIRONMENT = os.getenv("APP_ENV", "production")
SIMULATE_LATENCY = float(os.getenv("SIMULATE_LATENCY_MS", "0"))
SIMULATE_ERROR_RATE = float(os.getenv("SIMULATE_ERROR_RATE", "0"))

# In-memory metrics tracking
METRICS = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "total_latency_ms": 0.0,
    "recent_latencies": [],
    "start_time": time.time()
}

# Catalog of streaming media for recommendations
MEDIA_CATALOG = [
    {"id": "m101", "title": "Cyberpunk Odyssey", "genre": "Sci-Fi", "rating": 4.8},
    {"id": "m102", "title": "The Quantum Paradox", "genre": "Sci-Fi", "rating": 4.6},
    {"id": "m103", "title": "Echoes of Eternity", "genre": "Drama", "rating": 4.9},
    {"id": "m104", "title": "Velocity Chase", "genre": "Action", "rating": 4.3},
    {"id": "m105", "title": "Midnight Shadows", "genre": "Thriller", "rating": 4.7},
    {"id": "m106", "title": "Laughing Matters", "genre": "Comedy", "rating": 4.2},
    {"id": "m107", "title": "Secrets of the Deep", "genre": "Documentary", "rating": 4.9},
    {"id": "m108", "title": "Neon Horizon", "genre": "Cyberpunk", "rating": 4.5}
]

@app.route("/api/health", methods=["GET"])
def health_check():
    """Liveness and readiness health probe."""
    uptime_sec = round(time.time() - METRICS["start_time"], 2)
    return jsonify({
        "status": "healthy",
        "service": "content-recommendation-engine",
        "version": SERVICE_VERSION,
        "environment": ENVIRONMENT,
        "uptime_seconds": uptime_sec,
        "timestamp": time.time()
    }), 200

@app.route("/recommend", methods=["POST"])
def get_recommendations():
    """
    Generate personalized content recommendations for streaming users.
    Enforces target sub-100ms response time.
    """
    start_time = time.perf_counter()
    METRICS["total_requests"] += 1
    
    # Check for simulated error injection
    if SIMULATE_ERROR_RATE > 0 and random.random() < SIMULATE_ERROR_RATE:
        METRICS["failed_requests"] += 1
        logger.error(f"Inference failure: simulated error triggered for version {SERVICE_VERSION}")
        return jsonify({
            "error": "InferenceException",
            "message": "Model inference failed to converge within deadline.",
            "version": SERVICE_VERSION
        }), 500

    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "guest_user")
    preferred_genre = data.get("preferred_genre")
    top_k = min(int(data.get("top_k", 5)), 10)

    # Simulate model embedding scoring & matrix factorization
    # Baseline latency: 15ms - 45ms (well within sub-100ms SLA)
    base_latency = random.uniform(0.015, 0.045)
    if SIMULATE_LATENCY > 0:
        base_latency += (SIMULATE_LATENCY / 1000.0)

    time.sleep(base_latency)

    # Filter and rank candidates
    scored_candidates = []
    for item in MEDIA_CATALOG:
        score = item["rating"] * random.uniform(0.85, 1.0)
        if preferred_genre and item["genre"].lower() == preferred_genre.lower():
            score *= 1.3
        scored_candidates.append({**item, "recommendation_score": round(score, 3)})

    scored_candidates.sort(key=lambda x: x["recommendation_score"], reverse=True)
    recommendations = scored_candidates[:top_k]

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    METRICS["successful_requests"] += 1
    METRICS["total_latency_ms"] += elapsed_ms
    METRICS["recent_latencies"].append(elapsed_ms)
    if len(METRICS["recent_latencies"]) > 100:
        METRICS["recent_latencies"].pop(0)

    logger.info(f"User {user_id} served {len(recommendations)} recommendations in {elapsed_ms:.2f}ms (version: {SERVICE_VERSION})")

    return jsonify({
        "user_id": user_id,
        "recommendations": recommendations,
        "model_version": SERVICE_VERSION,
        "latency_ms": round(elapsed_ms, 2),
        "status": "success"
    }), 200

@app.route("/metrics", methods=["GET"])
def get_service_metrics():
    """Return runtime performance metrics."""
    total = max(METRICS["total_requests"], 1)
    avg_latency = METRICS["total_latency_ms"] / total if total > 0 else 0
    recent = METRICS["recent_latencies"]
    p95_latency = sorted(recent)[int(len(recent) * 0.95)] if recent else avg_latency
    error_rate = (METRICS["failed_requests"] / total) * 100.0

    return jsonify({
        "service_version": SERVICE_VERSION,
        "environment": ENVIRONMENT,
        "total_requests": METRICS["total_requests"],
        "successful_requests": METRICS["successful_requests"],
        "failed_requests": METRICS["failed_requests"],
        "error_rate_pct": round(error_rate, 2),
        "avg_latency_ms": round(avg_latency, 2),
        "p95_latency_ms": round(p95_latency, 2),
        "uptime_seconds": round(time.time() - METRICS["start_time"], 2)
    }), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"Starting Content Recommendation AI Service [{SERVICE_VERSION}] on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

