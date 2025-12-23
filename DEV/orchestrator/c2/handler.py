# FilePath: "/DEV/orchestrator/c2/handler.py"
# Projekt: Unified Bot Protocol (UBP)
# Beskrivelse: Håndterer initiell handshake og API Key rotation.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.0.0"

import logging
import secrets

from ..security.audit import AuditLogger
from ..security.encryption import CredentialEncryption
from ..security.rate_limiter import RateLimiter
from ..storage import BotStorage

logger = logging.getLogger(__name__)

def generate_api_key() -> str:
    """Helper til at generere ny API nøgle."""
    return secrets.token_urlsafe(48)

class SecureC2ConnectionHandler:
    """
    Håndterer logikken for første gangs forbindelse (Onboarding).
    Validerer One-Time-Tokens og udsteder permanente API nøgler.
    """

    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.encryption = CredentialEncryption()
        self.audit_logger = AuditLogger()
        self.bot_storage = BotStorage()

    async def handle_handshake(
        self,
        handshake_request: dict,
        client_ip: str,
        bot_id: str
    ) -> dict:
        """Handle bot handshake with enhanced security logic."""

        # 1. Check connection rate limits
        is_limited, retry_after = await self.rate_limiter.is_rate_limited(
            client_ip,
            "connection"
        )

        if is_limited:
            return {
                'status': 'RATE_LIMITED',
                'error_message': f'Too many connection attempts. Try again in {retry_after} seconds'
            }

        bot_id = handshake_request.get('bot_id', '') or bot_id
        auth_token = handshake_request.get('auth_token')

        # 2. Log connection attempt
        event_id = await self.audit_logger.log_security_event(
            event_type="BOT_CONNECTION_ATTEMPT",
            user_id=bot_id,
            ip_address=client_ip,
            details={"handshake_type": "initial"},
        )

        try:
            # 3. Retrieve Credentials
            stored_creds = await self.bot_storage.get_bot_credentials(bot_id)

            # Scenario A: First time setup using One-Time-Token (OTT)
            if stored_creds and stored_creds.one_time_token:
                try:
                    decrypted_token = self.encryption.decrypt(stored_creds.one_time_token)
                except Exception:
                    decrypted_token = None

                if auth_token == decrypted_token:
                    # Generate and encrypt new permanent API key
                    new_api_key = generate_api_key()
                    encrypted_api_key = self.encryption.encrypt(new_api_key)

                    # Update storage: Set API Key and invalidate OTT
                    await self.bot_storage.set_api_key(bot_id, encrypted_api_key)

                    # Log successful registration
                    await self.audit_logger.log_security_event(
                        event_type="BOT_REGISTERED",
                        user_id=bot_id,
                        ip_address=client_ip,
                        details={"event_id": event_id}
                    )

                    return {
                        'status': 'SUCCESS',
                        'api_key': new_api_key, # Send raw key once!
                        'heartbeat_interval_sec': 30
                    }

            # Scenario B: Reconnection using API Key
            if stored_creds and stored_creds.api_key:
                try:
                    decrypted_api_key = self.encryption.decrypt(stored_creds.api_key)
                except Exception:
                     decrypted_api_key = None

                if auth_token == decrypted_api_key:
                    # Log successful connection
                    await self.audit_logger.log_security_event(
                        event_type="BOT_CONNECTED",
                        user_id=bot_id,
                        ip_address=client_ip,
                        details={"event_id": event_id}
                    )

                    return {
                        'status': 'SUCCESS',
                        'heartbeat_interval_sec': 30
                    }

            # 4. Auth Failed
            await self.audit_logger.log_security_event(
                event_type="BOT_AUTH_FAILED",
                user_id=bot_id,
                ip_address=client_ip,
                details={"event_id": event_id},
                success=False
            )

            return {
                'status': 'AUTH_FAILED',
                'error_message': 'Invalid authentication token'
            }

        except Exception as e:
            # Log error
            await self.audit_logger.log_security_event(
                event_type="BOT_CONNECTION_ERROR",
                user_id=bot_id,
                ip_address=client_ip,
                details={"error": str(e), "event_id": event_id},
                success=False
            )

            return {
                'status': 'ERROR',
                'error_message': 'Internal server error'
            }
