# orchestrator/c2/handler.py
class SecureC2ConnectionHandler:
    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.encryption = CredentialEncryption()
        self.audit_logger = AuditLogger()

    async def handle_handshake(
        self,
        handshake_request: dict,
        client_ip: str
    ) -> dict:
        """Handle bot handshake with enhanced security"""

        # Check connection rate limits
        is_limited, retry_after = await self.rate_limiter.is_rate_limited(
            client_ip,
            "connection"
        )

        if is_limited:
            return {
                'status': 'RATE_LIMITED',
                'error_message': f'Too many connection attempts. Try again in {retry_after} seconds'
            }

        bot_id = handshake_request.get('bot_id')
        auth_token = handshake_request.get('auth_token')

        # Log connection attempt
        event_id = await self.audit_logger.log_security_event(
            event_type="BOT_CONNECTION_ATTEMPT",
            user_id=bot_id,
            ip_address=client_ip,
            details={"handshake_type": "initial"}
        )

        try:
            # Validate one-time token
            stored_creds = await self.bot_storage.get_bot_credentials(bot_id)
            if stored_creds and stored_creds.one_time_token:
                decrypted_token = self.encryption.decrypt(stored_creds.one_time_token)

                if auth_token == decrypted_token:
                    # Generate and encrypt new API key
                    new_api_key = generate_api_key()
                    encrypted_api_key = self.encryption.encrypt(new_api_key)

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
                        'api_key': new_api_key,
                        'heartbeat_interval_sec': 30
                    }

            # Validate existing API key
            if stored_creds and stored_creds.api_key:
                decrypted_api_key = self.encryption.decrypt(stored_creds.api_key)

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

            # Log failed attempt
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