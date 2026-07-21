import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.metrics.ai_metrics import AIMetricsCollector

def test_ai_metrics_collection():
    collector = AIMetricsCollector()
    collector.record_request("local", fallback_occurred=False, latency_ms=15.0)
    collector.record_request("gemini", fallback_occurred=True, latency_ms=120.0)

    stats = collector.collect()
    assert stats["total_requests"] == 2
    assert stats["local_requests"] == 1
    assert stats["gemini_requests"] == 1
    assert stats["fallback_events"] == 1
    assert stats["fallback_rate_percent"] == 50.0
    print("[OK] AIMetricsCollector unit tests passed!")

if __name__ == "__main__":
    test_ai_metrics_collection()
