class AlertManager:
    def trigger_alert(self, title: str, severity: str = "warning") -> dict:
        return {"alert": title, "severity": severity, "status": "triggered"}
