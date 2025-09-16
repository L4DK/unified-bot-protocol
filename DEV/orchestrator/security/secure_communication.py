# orchestrator/security/secure_communication.py
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import os
import base64
from typing import Tuple

class SecureCommunication:
    def __init__(self):
        self.private_key = self._load_or_generate_key()

    def _load_or_generate_key(self) -> rsa.RSAPrivateKey:
        """Load existing or generate new RSA key pair"""
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
        """Get public key in PEM format"""
        public_key = self.private_key.public_key()
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()

    def generate_session_key(self) -> Tuple[bytes, bytes]:
        """Generate AES session key and IV"""
        key = os.urandom(32)  # 256-bit key
        iv = os.urandom(16)   # 128-bit IV
        return key, iv

    def encrypt_session_key(
        self,
        session_key: bytes,
        public_key_pem: str
    ) -> str:
        """Encrypt session key with recipient's public key"""
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
        """Decrypt session key using private key"""
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
        """Encrypt message using AES-GCM"""
        cipher = Cipher(
            algorithms.AES(session_key),
            modes.GCM(iv)
        )
        encryptor = cipher.encryptor()

        ciphertext = encryptor.update(message.encode()) + encryptor.finalize()

        # Combine IV, ciphertext, and tag
        return base64.b64encode(
            iv + encryptor.tag + ciphertext
        ).decode()

    def decrypt_message(
        self,
        encrypted_message: str,
        session_key: bytes
    ) -> str:
        """Decrypt message using AES-GCM"""
        decoded = base64.b64decode(encrypted_message)

        iv = decoded[:16]
        tag = decoded[16:32]
        ciphertext = decoded[32:]

        cipher = Cipher(
            algorithms.AES(session_key),
            modes.GCM(iv, tag)
        )
        decryptor = cipher.decryptor()

        return (decryptor.update(ciphertext) + decryptor.finalize()).decode()