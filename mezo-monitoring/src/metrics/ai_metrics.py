import time

class AIMetricsCollector:
    def __init__(self):
        self.local_requests = 0
        self.gemini_requests = 0
        self.fallback_events = 0
        self.total_latency_ms = 0.0

    def record_request(self, provider_name: str, fallback_occurred: bool = False, latency_ms: float = 0.0):
        if provider_name == "local":
            self.local_requests += 1
        elif provider_name == "gemini":
            self.gemini_requests += 1

        if fallback_occurred:
            self.fallback_events += 1

        self.total_latency_ms += latency_ms

    def collect(self) -> dict:
        total = self.local_requests + self.gemini_requests
        avg_latency = (self.total_latency_ms / total) if total > 0 else 0.0
        fallback_rate = (self.fallback_events / total) if total > 0 else 0.0

        return {
            "total_requests": total,
            "local_requests": self.local_requests,
            "gemini_requests": self.gemini_requests,
            "fallback_events": self.fallback_events,
            "fallback_rate_percent": round(fallback_rate * 100, 2),
            "average_latency_ms": round(avg_latency, 2)
        }
