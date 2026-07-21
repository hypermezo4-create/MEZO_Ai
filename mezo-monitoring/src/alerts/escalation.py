class EscalationPolicy:
    def escalate(self, alert_id: str, level: int = 1) -> dict:
        return {"alert_id": alert_id, "escalation_level": level, "action": "notified_admin"}
