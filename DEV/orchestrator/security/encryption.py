"""
FilePath: "/DEV/orchestrator/security/encryption.py"
Project: Unified Bot Protocol (UBP)
Component: Credential Encryption
Description: Handles symmetric encryption for sensitive data (At-Rest) using Fernet (AES-128-CBC).
Author: "Michael Landbo"
Date created: "21/12/2025"
Date Modified: "27/12/2025"
Version: "1.1.0"
"""

import logging
import os
from cryptography.fernet import Fernet, InvalidToken

# Setup Logging
logger = logging.getLogger(__name__)

# Base directory for relative file loading
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class CredentialEncryption:
    """
    Handles secure encryption of sensitive data (like stored API keys).
    Uses cryptography.fernet which guarantees confidentiality and authenticity (HMAC).
    """

    def __init__(self):
        # Store keys in a dedicated 'keys' subdirectory
        self.key_dir = os.path.join(BASE_DIR, "keys")
        self.key_file = os.path.join(self.key_dir, "secret.key")

        # Ensure directory exists
        os.makedirs(self.key_dir, exist_ok=True)

        self.encryption_key = self._load_or_create_key()
        try:
            self.fernet = Fernet(self.encryption_key)
        except Exception as e:
            logger.error("Failed to initialize Fernet with key: %s", e)
            raise

    def _load_or_create_key(self) -> bytes:
        """
        Load existing key from disk or create a new one if missing.
        Note: In production, consider using a Key Management Service (KMS).
        """
        if os.path.exists(self.key_file):
            try:
                with open(self.key_file, "rb") as f:
                    logger.info("Loading encryption key from %s", self.key_file)
                    return f.read()
            except Exception as e:
                logger.error("Error loading encryption key: %s", e)
                raise

        # Generate new key
        # Fernet.generate_key() returns a URL-safe base64-encoded 32-byte key
        logger.info("Generating new encryption key at %s", self.key_file)
        key = Fernet.generate_key()

        # Save key to file
        with open(self.key_file, "wb") as f:
            f.write(key)

        return key

    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data string -> encrypted token string."""
        if not data:
            return ""
        try:
            return self.fernet.encrypt(data.encode()).decode()
        except Exception as e:
            logger.error("Encryption failed: %s", e)
            raise

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt encrypted token string -> original data string."""
        if not encrypted_data:
            return ""
        try:
            return self.fernet.decrypt(encrypted_data.encode()).decode()
        except InvalidToken:
            logger.error("Decryption failed: Invalid Token (Key mismatch or tampering).")
            raise
        except Exception as e:
            logger.error("Decryption failed: %s", e)
            raise
