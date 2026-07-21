import jwt
import datetime

class JWTManager:
    def __init__(self, secret_key: str = "mezo_secret"):
        self.secret_key = secret_key

    def create_token(self, payload: dict) -> str:
        payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def verify_token(self, token: str) -> dict:
        return jwt.decode(token, self.secret_key, algorithms=["HS256"])
