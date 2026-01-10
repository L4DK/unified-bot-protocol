"""
FilePath: "/DEV/orchestrator/c2/secure_handler.py"
Project: Unified Bot Protocol (UBP)
Component: C2 Secure Handler
Description: Handles WebSocket connection, Encryption, Zero Trust validation, Message Routing.
Author: "Michael Landbo"
Date created: "21/12/2025"
Date Modified: "31/12/2025"
Version: "1.3.0"
"""

import logging
import time
from typing import Dict, Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

# Relative imports from security module
from ..security.authenticator import SecureBotAuthenticator
from ..security.compliance_manager import ComplianceManager
from ..security.threat_protection import ThreatProtection
from ..security.zero_trust import ZeroTrustManager

# Type checking imports (undgår cirkulære imports ved runtime)
try:
    from integrations.core.routing.message_router import MessageRouter
    from orchestrator.tasks.manager import TaskManager
except ImportError:
    MessageRouter = Any
    TaskManager = Any

logger = logging.getLogger(__name__)


class SecureC2Handler:
    """
    Responsible for maintaining a secure, encrypted WebSocket channel.
    Includes:
        - Threat Protection scan upon connection.
        - Zero Trust authentication.
        - Ongoing message encryption and compliance checks.
        - Routing of decrypted messages to MessageRouter or TaskManager.
    """

    def __init__(
        self,
        message_router: Optional[MessageRouter] = None,
        task_manager: Optional[TaskManager] = None
    ):
        """
        Initialize security components and inject core services.
        Arguments match dependency injection from orchestrator_server.py
        """
        self.zero_trust = ZeroTrustManager()
        self.bot_auth = SecureBotAuthenticator(self.zero_trust)
        self.threat_protection = ThreatProtection()
        self.compliance_manager = ComplianceManager()

        # Injected Core services
        self.message_router = message_router
        self.task_manager = task_manager

    async def handle_connection(self, websocket: WebSocket, client_ip: str):
        """Handle incoming bot connections with enhanced security"""
        try:
            # 1. Initial threat assessment (Metadata only check)
            threat_analysis = await self.threat_protection.analyze_request(
                client_ip,
                {},  # Initial connection has no payload body
                dict(websocket.headers),
            )

            if threat_analysis["blocked"]:
                logger.warning(
                    "Blocking connection from %s: %s",
                    client_ip,
                    threat_analysis["reason"],
                )
                await websocket.close(code=4403)
                return

            # 2. Receive initial handshake (JSON payload)
            handshake_data = await websocket.receive_json()

            # 3. Build security context
            context = {
                "ip": client_ip,
                "headers": dict(websocket.headers),
                "time": {
                    "timestamp": time.time(),
                    "allowed_hours": range(24),
                },
                "network": {
                    "ip": client_ip,
                    "protocol": "WSS",
                    "port": websocket.url.port,
                },
            }

            # 4. Authenticate bot
            is_authenticated, auth_response = await self.bot_auth.authenticate_bot(
                handshake_data.get("bot_id", "unknown"), handshake_data, context
            )

            if not is_authenticated:
                logger.warning("Authentication failed for %s", client_ip)
                await websocket.send_json(auth_response)
                await websocket.close(code=4401)
                return

            # 5. Start secure session loop
            await self._handle_secure_session(
                websocket,
                handshake_data.get("bot_id"),
                auth_response,
                context,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Connection handler error: %s", str(e), exc_info=True)
            try:
                await websocket.close(code=4500)
            except RuntimeError:
                pass  # Websocket might be already closed

    async def _handle_secure_session(
        self,
        websocket: WebSocket,
        bot_id: str,
        auth_response: Dict,
        context: Dict,
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
                    message.get("session_token"), context
                )

                if not is_valid:
                    await websocket.send_json(
                        {"status": "AUTH_FAILED", "reason": error}
                    )
                    break

                # Process message
                response = await self._process_secure_message(
                    bot_id, message, context
                )

                # Send response back to bot
                await websocket.send_json(response)

        except WebSocketDisconnect:
            logger.info("Bot %s disconnected", bot_id)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Session handler error: %s", str(e))
        finally:
            try:
                await websocket.close()
            except Exception: # pylint: disable=broad-exception-caught
                pass

    async def _process_secure_message(
        self, bot_id: str, message: Dict, context: Dict
    ) -> Dict:
        """
        Process authenticated message, handle decryption, compliance, and ROUTING.
        """
        try:
            # 1. Decrypt sensitive data if present
            if "encrypted_data" in message:
                message_data = self.bot_auth.decrypt_sensitive_data(
                    message["encrypted_data"]
                )
            else:
                message_data = message.get("data", {})

            # 2. Validate compliance
            violations = self.compliance_manager.validate_compliance(
                message_data, {"classification": {"level": "confidential"}}
            )

            if violations:
                return {
                    "status": "REJECTED",
                    "reason": "Compliance violations",
                    "violations": violations,
                }

            # 3. ROUTING LOGIC
            routing_result = {}

            # Route to Task Manager if 'action' is present
            if "action" in message_data and self.task_manager:
                logger.info("Routing message to TaskManager: %s", message_data.get("action"))
                task_id = self.task_manager.create_task(
                    action=message_data["action"],
                    params=message_data.get("params", {})
                )
                routing_result = {"status": "task_queued", "task_id": task_id}

            # Route to Message Router otherwise
            elif self.message_router:
                logger.info("Routing message via MessageRouter")
                routing_context = context.copy()
                routing_context.update({
                    "bot_id": bot_id,
                    "source_platform": "c2_client",
                    "user_id": bot_id
                })

                routing_result = await self.message_router.route_message(
                    message_data,
                    routing_context
                )

            else:
                routing_result = {"status": "ignored", "reason": "No router configured"}

            # 4. Prepare Response
            response_data = {
                "processed": True,
                "timestamp": time.time(),
                "routing_result": routing_result
            }

            return {
                "status": "SUCCESS",
                "encrypted_data": self.bot_auth.encrypt_sensitive_data(
                    response_data
                ),
                # pylint: disable=protected-access
                "next_challenge": self.bot_auth._generate_challenge(bot_id),
            }

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error processing secure message: %s", str(e))
            return {"status": "ERROR", "reason": str(e)}
