class MonitoringAgent:
    def check_health(self) -> dict:
        return {"agent": "MonitoringAgent", "health": "healthy", "active_nodes": 1, "cpu_usage": "12%"}
