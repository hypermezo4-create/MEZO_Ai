from cryptography.fernet import Fernet

class KeyManager:
    def generate_master_key(self) -> bytes:
        return Fernet.generate_key()
