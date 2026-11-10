"""
Live Streaming Traffic & Load Generator
Simulates active user sessions sending content recommendation queries
to the Model Service and streaming live telemetry to the Monitoring Dashboard.
"""

import time
import random
import requests
import argparse

MODEL_ENDPOINT = "http://localhost:5000/recommend"
METRICS_PUSH_ENDPOINT = "http://localhost:5001/api/metrics/push"

GENRES = ["Sci-Fi", "Action", "Drama", "Thriller", "Comedy", "Documentary", "Cyberpunk"]

def run_traffic_stream(num_requests: int = 50, delay_sec: float = 0.2):
    print(f"\n🚀 Streaming {num_requests} personalized recommendation requests to {MODEL_ENDPOINT}...")
    successful = 0
    failed = 0
    latencies = []

    for i in range(1, num_requests + 1):
        user_id = f"user_{random.randint(100, 999)}"
        genre = random.choice(GENRES)
        payload = {
            "user_id": user_id,
            "preferred_genre": genre,
            "top_k": 4
        }

        start = time.perf_counter()
        try:
            res = requests.post(MODEL_ENDPOINT, json=payload, timeout=2.0)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)

            if res.status_code == 200:
                successful += 1
                data = res.json()
                top_item = data["recommendations"][0]["title"] if data.get("recommendations") else "N/A"
                print(f"[{i:02d}/{num_requests}] User: {user_id} | Genre: {genre:11s} | Top Rec: '{top_item}' | Latency: {elapsed_ms:5.1f}ms (HTTP 200)")
            else:
                failed += 1
                print(f"[{i:02d}/{num_requests}] User: {user_id} | FAILED (Status: {res.status_code}) | Latency: {elapsed_ms:5.1f}ms")
        except Exception as e:
            failed += 1
            print(f"[{i:02d}/{num_requests}] Request error: {e}")

        # Send aggregated metric sample every 5 requests
        if i % 5 == 0 and latencies:
            recent = latencies[-5:]
            avg_lat = round(sum(recent) / len(recent), 2)
            p95_lat = round(sorted(recent)[int(len(recent) * 0.95)], 2)
            err_rate = round((failed / i) * 100.0, 2)
            
            try:
                requests.post(METRICS_PUSH_ENDPOINT, json={
                    "latency_avg_ms": avg_lat,
                    "latency_p95_ms": p95_lat,
                    "latency_p99_ms": round(p95_lat * 1.2, 2),
                    "rps": round(1.0 / max(delay_sec, 0.05), 1),
                    "rpm": int((1.0 / max(delay_sec, 0.05)) * 60),
                    "error_rate_pct": err_rate,
                    "cpu_usage_pct": round(random.uniform(42.0, 58.0), 1),
                    "memory_usage_pct": round(random.uniform(50.0, 62.0), 1),
                    "profile": "live_streaming"
                }, timeout=1.0)
            except Exception:
                pass

        time.sleep(delay_sec)

    total = successful + failed
    avg_total = sum(latencies) / len(latencies) if latencies else 0
    p95_total = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    print("\n" + "=" * 60)
    print("TRAFFIC STREAM SUMMARY:")
    print(f"Total Requests: {total} (Success: {successful}, Failed: {failed})")
    print(f"Average Latency: {avg_total:.2f}ms")
    print(f"p95 Latency:     {p95_total:.2f}ms (SLA Sub-100ms Target: {'MET ✅' if p95_total < 100 else 'BREACHED ❌'})")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live Streaming Traffic Generator")
    parser.add_argument("--count", type=int, default=20, help="Number of requests to send")
    parser.add_argument("--delay", type=float, default=0.15, help="Delay between requests in seconds")
    args = parser.parse_args()
    run_traffic_stream(args.count, args.delay)

