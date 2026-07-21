class OAuthHandler:
    def handle_callback(self, provider: str, code: str) -> dict:
        return {"provider": provider, "status": "authenticated", "user_email": "user@mezo.ai"}
