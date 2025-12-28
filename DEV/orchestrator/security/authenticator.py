"""
FilePath: "/DEV/orchestrator/security/authenticator.py"
Project: Unified Bot Protocol (UBP)
Component: Bot Authenticator
Description: Standardized authenticator module for Bot Identity Verification.
             Combines Zero Trust checks with Challenge-Response protocols.
Author: "Michael Landbo"
Date created: "21/12/2025"
Date Modified: "27/12/2025"
Version: "1.1.0"
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Dict, Optional, Tuple

from cryptography.fernet import Fernet

# Use relative import for internal security modules
from .zero_trust import ZeroTrustManager

logger = logging.getLogger(__name__)


class SecureBotAuthenticator:
    """
    Handles the authentication lifecycle for bots:
    1. Zero Trust Identity Verification (Certificates, etc.)
    2. Challenge-Response (to prevent Replay Attacks)
    3. Session Token issuance
    """

    def __init__(self, zero_trust_manager: ZeroTrustManager):
        self.zero_trust = zero_trust_manager
        # Generate a transient key for this authenticator instance
        # (used for internal data encryption during the auth flow if needed)
        self.key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.key)
        self.auth_challenges = {}

    async def authenticate_bot(
        self, bot_id: str, auth_request: Dict, context: Dict
    ) -> Tuple[bool, Dict]:
        """
        Implement multi-factor bot authentication.

        Flow:
        1. Verify Identity (Zero Trust)
        2. Verify Challenge Response (if applicable)
        3. Issue Session Token
        4. Issue Next Challenge

        Returns: (is_authenticated, response_data)
        """
        try:
            # 1. Zero Trust Verification
            is_verified, trust_context = await self.zero_trust.verify_identity(
                bot_id, auth_request, context
            )

            if not is_verified:
                logger.warning(
                    "Authentication failed for %s: Zero Trust checks failed.", bot_id
                )
                return False, {
                    "status": "AUTH_FAILED",
                    "reason": "Zero trust verification failed",
                    "context": trust_context,
                }

            # 2. Challenge-Response Authentication
            # We verify the 'challenge_response' sent by the bot against our stored challenge.
            challenge_result = await self._process_challenge(
                bot_id, auth_request.get("challenge_response")
            )

            if not challenge_result:
                # Note: On first connection, this might fail if no challenge was previously issued.
                # The bot will receive AUTH_FAILED but should look for 'next_challenge'
                # (if we returned it) or re-initiate handshake to get a challenge.
                logger.warning(
                    "Authentication failed for %s: Invalid or missing challenge response.",
                    bot_id,
                )
                return False, {
                    "status": "AUTH_FAILED",
                    "reason": "Challenge verification failed",
                }

            # 3. Generate Session Token
            session_token = self.zero_trust.generate_session_token(
                bot_id, trust_context["trust_score"], context
            )

            # 4. Generate New Challenge for Next Authentication
            next_challenge = self._generate_challenge(bot_id)

            logger.info("Bot %s authenticated successfully.", bot_id)

            return True, {
                "status": "SUCCESS",
                "session_token": session_token,
                "next_challenge": next_challenge,
                "trust_context": trust_context,
            }

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error during bot authentication: %s", e, exc_info=True)
            return False, {"status": "ERROR", "reason": str(e)}

    def _generate_challenge(self, bot_id: str) -> str:
        """Generate a unique random challenge string for the bot to sign/return."""
        challenge = base64.b64encode(os.urandom(32)).decode()
        # Store the hash of the challenge for verification
        challenge_hash = hashlib.sha256(challenge.encode()).hexdigest()

        self.auth_challenges[bot_id] = {
            "challenge": challenge_hash,
            "timestamp": time.time(),
        }

        return challenge

    async def _process_challenge(self, bot_id: str, response: Optional[str]) -> bool:
        """Verify the bot's challenge response."""
        if not response:
            return False

        stored_challenge = self.auth_challenges.get(bot_id)
        if not stored_challenge:
            return False

        # Check if challenge has expired (5 minutes)
        if time.time() - stored_challenge["timestamp"] > 300:
            del self.auth_challenges[bot_id]
            return False

        # Verify response
        # We assume the bot returns the challenge string (or a signature of it).
        # We hash the received response and compare it to our stored hash.
        response_hash = hashlib.sha256(response.encode()).hexdigest()
        is_valid = hmac.compare_digest(
            response_hash, stored_challenge["challenge"]
        )

        # Clean up used challenge to prevent replay
        del self.auth_challenges[bot_id]

        return is_valid

    def encrypt_sensitive_data(self, data: Dict) -> str:
        """Encrypt sensitive data payload for secure transmission."""
        return self.cipher_suite.encrypt(json.dumps(data).encode()).decode()

    def decrypt_sensitive_data(self, encrypted_data: str) -> Dict:
        """Decrypt sensitive data payload received from bot."""
        decrypted = self.cipher_suite.decrypt(encrypted_data.encode()).decode()
        return json.loads(decrypted)
