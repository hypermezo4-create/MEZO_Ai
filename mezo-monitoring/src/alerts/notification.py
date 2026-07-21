class NotificationService:
    def send(self, channel: str, message: str) -> dict:
        return {"channel": channel, "message": message, "sent": True}
