# orchestrator/security/encryption.py
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os

class CredentialEncryption:
    """Handles secure encryption of sensitive data"""

    def __init__(self, key_file: str = "encryption.key"):
        self.key_file = key_file
        self.encryption_key = self._load_or_create_key()
        self.fernet = Fernet(self.encryption_key)

    def _load_or_create_key(self) -> bytes:
        """Load existing key or create a new one"""
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f:
                return base64.urlsafe_b64decode(f.read())

        # Generate new key
        key = Fernet.generate_key()
        with open(self.key_file, "wb") as f:
            f.write(base64.urlsafe_b64encode(key))
        return key

    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data"""
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        return self.fernet.decrypt(encrypted_data.encode()).decode()