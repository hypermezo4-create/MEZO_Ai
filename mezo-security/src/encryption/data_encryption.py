from cryptography.fernet import Fernet

class DataEncryption:
    def __init__(self, key: bytes = None):
        self.key = key or Fernet.generate_key()
        self.cipher = Fernet(self.key)

    def encrypt_data(self, data: str) -> bytes:
        return self.cipher.encrypt(data.encode())

    def decrypt_data(self, token: bytes) -> str:
        return self.cipher.decrypt(token).decode()
