# FilePath: "/DEV/orchestrator/security/encryption.py"
# Project: Unified Bot Protocol (UBP)
# Description: Handles symmetric encryption for sensitive data (At-Rest) using Fernet (AES-128-CBC).
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.1.0.0"

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os
import logging

logger = logging.getLogger(__name__)

class CredentialEncryption:
    """
    Handles secure encryption of sensitive data (like stored API keys).
    Uses cryptography.fernet which guarantees confidentiality and authenticity (HMAC).
    """

    def __init__(self, key_file: str = "encryption.key"):
        self.key_file = key_file
        self.encryption_key = self._load_or_create_key()
        try:
            self.fernet = Fernet(self.encryption_key)
        except Exception as e:
            logger.error(f"Failed to initialize Fernet with key: {e}")
            raise

    def _load_or_create_key(self) -> bytes:
        """
        Load existing key from disk or create a new one if missing.
        Note: In production, use a Key Management Service (KMS) or Kubernetes Secrets.
        """
        if os.path.exists(self.key_file):
            try:
                with open(self.key_file, "rb") as f:
                    # We store the key base64 encoded for safety, decode to get raw bytes
                    return base64.urlsafe_b64decode(f.read())
            except Exception as e:
                logger.error(f"Error loading encryption key: {e}")
                raise

        # Generate new key
        logger.info(f"Generating new encryption key at {self.key_file}")
        key = Fernet.generate_key()

        # Save key to file (base64 encoded for text-safety)
        with open(self.key_file, "wb") as f:
            f.write(base64.urlsafe_b64encode(key))

        return key

    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data string -> encrypted token string."""
        if not data:
            return ""
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt encrypted token string -> original data string."""
        if not encrypted_data:
            return ""
        try:
            return self.fernet.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            logger.error("Decryption failed. Key mismatch or data corruption.")
            raise
