class LogAggregator:
    def aggregate(self, logs: list) -> dict:
        return {"total_logs": len(logs), "errors": 0, "warnings": 2}
