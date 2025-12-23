# FilePath: "/DEV/orchestrator/security/secure_communication.py"
# Project: Unified Bot Protocol (UBP)
# Description: Handles Hybrid Encryption (RSA + AES-GCM) for secure communication.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.1.0.0"

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import os
import base64
from typing import Tuple

class SecureCommunication:
    """
    Manages secure channel establishment and message encryption.
    Uses RSA (2048-bit) for key exchange and AES-GCM (256-bit) for message confidentiality and integrity.
    """

    def __init__(self):
        self.private_key = self._load_or_generate_key()

    def _load_or_generate_key(self) -> rsa.RSAPrivateKey:
        """Load existing private key from disk or generate a new one if missing."""
        key_file = "private_key.pem"

        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                return serialization.load_pem_private_key(
                    f.read(),
                    password=None
                )

        # Generate new key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

        # Save private key
        with open(key_file, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))

        return private_key

    def get_public_key(self) -> str:
        """Get public key in PEM format for distribution to bots."""
        public_key = self.private_key.public_key()
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()

    def generate_session_key(self) -> Tuple[bytes, bytes]:
        """Generate a random AES session key (256-bit) and IV (128-bit)."""
        key = os.urandom(32)  # 256-bit key
        iv = os.urandom(16)   # 128-bit IV
        return key, iv

    def encrypt_session_key(
        self,
        session_key: bytes,
        public_key_pem: str
    ) -> str:
        """Encrypt the AES session key using a recipient's RSA public key (Key Exchange)."""
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode()
        )

        encrypted_key = public_key.encrypt(
            session_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        return base64.b64encode(encrypted_key).decode()

    def decrypt_session_key(self, encrypted_key: str) -> bytes:
        """Decrypt a received AES session key using our RSA private key."""
        encrypted_key_bytes = base64.b64decode(encrypted_key)

        session_key = self.private_key.decrypt(
            encrypted_key_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        return session_key

    def encrypt_message(
        self,
        message: str,
        session_key: bytes,
        iv: bytes
    ) -> str:
        """Encrypt a message string using AES-GCM."""
        cipher = Cipher(
            algorithms.AES(session_key),
            modes.GCM(iv)
        )
        encryptor = cipher.encryptor()

        ciphertext = encryptor.update(message.encode()) + encryptor.finalize()

        # Combine IV, auth tag, and ciphertext into a single base64 string
        # Format: IV (16 bytes) + Tag (16 bytes) + Ciphertext (n bytes)
        return base64.b64encode(
            iv + encryptor.tag + ciphertext
        ).decode()

    def decrypt_message(
        self,
        encrypted_message: str,
        session_key: bytes
    ) -> str:
        """Decrypt a message string using AES-GCM."""
        decoded = base64.b64decode(encrypted_message)

        # Extract components based on known sizes
        iv = decoded[:16]
        tag = decoded[16:32]
        ciphertext = decoded[32:]

        cipher = Cipher(
            algorithms.AES(session_key),
            modes.GCM(iv, tag)
        )
        decryptor = cipher.decryptor()

        return (decryptor.update(ciphertext) + decryptor.finalize()).decode()
