# FilePath: "/DEV/orchestrator/c2/secure_handler.py"
# Projekt: Unified Bot Protocol (UBP)
# Beskrivelse: Håndterer den vedvarende WebSocket forbindelse med kryptering og Zero Trust validering.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.0.0"

import logging
import time
from typing import Dict
from fastapi import WebSocket, WebSocketDisconnect

# Retter imports til at bruge relative stier fra parent module
from ..security.authenticator import SecureBotAuthenticator
from ..security.compliance_manager import ComplianceManager
from ..security.threat_protection import ThreatProtection
from ..security.zero_trust import ZeroTrustManager

logger = logging.getLogger(__name__)

class SecureC2Handler:
    """
    Ansvarlig for at opretholde en sikker, krypteret WebSocket kanal.
    Inkluderer:
    - Threat Protection scan ved opkobling.
    - Zero Trust autentificering.
    - Løbende besked-kryptering og compliance checks.
    """

    def __init__(self):
        self.zero_trust = ZeroTrustManager()
        self.bot_auth = SecureBotAuthenticator(self.zero_trust)
        self.threat_protection = ThreatProtection()
        self.compliance_manager = ComplianceManager()

    async def handle_connection(
        self,
        websocket: WebSocket,
        client_ip: str
    ):
        """Handle incoming bot connections with enhanced security"""
        try:
            # 1. Initial threat assessment (Metadata only check)
            threat_analysis = await self.threat_protection.analyze_request(
                client_ip,
                {},  # Initial connection has no payload body
                dict(websocket.headers),
            )

            if threat_analysis['blocked']:
                logger.warning(f"Blocking connection from {client_ip}: {threat_analysis['reason']}")
                await websocket.close(code=4403)
                return

            # 2. Receive initial handshake (JSON payload)
            handshake_data = await websocket.receive_json()

            # 3. Build security context
            context = {
                'ip': client_ip,
                'headers': dict(websocket.headers),
                'time': {
                    'timestamp': time.time(),
                    'allowed_hours': range(24) # Tillad alle timer pt.
                },
                'network': {
                    'ip': client_ip,
                    'protocol': 'WSS',
                    'port': websocket.url.port
                }
            }

            # 4. Authenticate bot
            is_authenticated, auth_response = await self.bot_auth.authenticate_bot(
                handshake_data.get('bot_id', 'unknown'),
                handshake_data,
                context
            )

            if not is_authenticated:
                logger.warning(f"Authentication failed for {client_ip}")
                await websocket.send_json(auth_response)
                await websocket.close(code=4401)
                return

            # 5. Start secure session loop
            await self._handle_secure_session(
                websocket,
                handshake_data.get('bot_id'),
                auth_response,
                context
            )

        except Exception as e:
            logger.error(f"Connection handler error: {str(e)}")
            try:
                await websocket.close(code=4500)
            except RuntimeError:
                pass # Websocket might be already closed

    async def _handle_secure_session(
        self,
        websocket: WebSocket,
        bot_id: str,
        auth_response: Dict,
        context: Dict
    ):
        """Handle authenticated bot session loop"""
        try:
            # Send initial authentication success response
            await websocket.send_json(auth_response)

            # Session loop
            while True:
                # Receive message
                message = await websocket.receive_json()

                # Verify session token included in message
                is_valid, error = self.zero_trust.verify_session_token(
                    message.get('session_token'),
                    context
                )

                if not is_valid:
                    await websocket.send_json({
                        'status': 'AUTH_FAILED',
                        'reason': error
                    })
                    break

                # Process message
                response = await self._process_secure_message(
                    bot_id,
                    message,
                    context
                )

                # Send response back to bot
                await websocket.send_json(response)

        except WebSocketDisconnect:
            logger.info(f"Bot {bot_id} disconnected")
        except Exception as e:
            logger.error(f"Session handler error: {str(e)}")
        finally:
            # Ensure socket is closed
            try:
                await websocket.close()
            except:
                pass

    async def _process_secure_message(
        self,
        bot_id: str,
        message: Dict,
        context: Dict
    ) -> Dict:
        """Process authenticated message, handle decryption and compliance."""
        try:
            # Decrypt sensitive data if present
            if 'encrypted_data' in message:
                message_data = self.bot_auth.decrypt_sensitive_data(
                    message['encrypted_data']
                )
            else:
                message_data = message.get('data', {})

            # Validate compliance
            violations = self.compliance_manager.validate_compliance(
                message_data,
                {'classification': {'level': 'confidential'}}
            )

            if violations:
                return {
                    'status': 'REJECTED',
                    'reason': 'Compliance violations',
                    'violations': violations
                }

            # TODO: Add logic here to route message to relevant Orchestrator service
            # e.g., TaskManager or specific Integration
            # For now, we just acknowledge receipt

            # Encrypt sensitive response data
            response_data = {
                'processed': True,
                'timestamp': time.time(),
                'server_ack': 'Message received securely'
            }

            return {
                'status': 'SUCCESS',
                'encrypted_data': self.bot_auth.encrypt_sensitive_data(
                    response_data
                ),
                'next_challenge': self.bot_auth._generate_challenge(bot_id)
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'reason': str(e)
            }
