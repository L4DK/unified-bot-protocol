"""
Facebook Messenger Platform Adapter for Unified Bot Protocol (UBP)
==================================================================

File: facebook_messenger_adapter.py
Project: Unified Bot Protocol (UBP)
Version: 1.0.0
Last Edited: 2025-09-19
Author: Michael Landbo (UBP BDFL)
License: Apache-2.0

Description:
Production-grade Facebook Messenger adapter for UBP.
Handles inbound webhook events, outbound message sending,
security verification, observability, and resilience.

Features:
- Webhook verification and signature validation
- Async webhook event processing
- Secure event signing before sending to UBP Orchestrator
- Outbound message sending with error handling and metrics
- Structured logging and metrics collection
- Graceful shutdown and resource cleanup
"""

import asyncio
import logging
import hmac
import hashlib
import json
from typing import Dict, Any, Optional

from aiohttp import web, ClientSession, ClientResponseError

from ubp_core.platform_adapter import BasePlatformAdapter, AdapterCapabilities
from ubp_core.security import SecurityManager
from ubp_core.observability import StructuredLogger, MetricsCollector


class FacebookMessengerAdapter(BasePlatformAdapter):
    adapter_id = "facebook_messenger"
    display_name = "Facebook Messenger"
    capabilities = AdapterCapabilities(
        supports_text=True,
        supports_media=True,
        supports_buttons=True,
        supports_threads=False,
    )

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.app_secret: str = config["app_secret"]
        self.page_access_token: str = config["page_access_token"]
        self.verify_token: Optional[str] = config.get("verify_token")
        self.logger = StructuredLogger("facebook_messenger_adapter")
        self.metrics = MetricsCollector("facebook_messenger_adapter")
        self.security = SecurityManager(config.get("security_key", ""))
        self.http_session = ClientSession()
        self._webhook_app = web.Application()
        self._setup_routes()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    def _setup_routes(self):
        self._webhook_app.router.add_get("/webhook", self._handle_verification)
        self._webhook_app.router.add_post("/webhook", self._handle_webhook_event)

    async def start(self, host: str = "0.0.0.0", port: int = 8080):
        """Start the webhook HTTP server."""
        self.logger.info(f"Starting Facebook Messenger webhook server on {host}:{port}")
        self._runner = web.AppRunner(self._webhook_app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host, port)
        await self._site.start()
        self.logger.info("Facebook Messenger webhook server started")

    async def stop(self):
        """Stop the webhook HTTP server and cleanup."""
        self.logger.info("Stopping Facebook Messenger webhook server")
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        await self.http_session.close()
        self.logger.info("Facebook Messenger adapter stopped")

    async def _handle_verification(self, request: web.Request) -> web.Response:
        """Handle Facebook webhook verification challenge."""
        params = request.rel_url.query
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")

        if mode == "subscribe" and token == self.verify_token:
            self.logger.info("Webhook verification successful")
            return web.Response(text=challenge)
        else:
            self.logger.warning("Webhook verification failed")
            return web.Response(status=403)

    async def _handle_webhook_event(self, request: web.Request) -> web.Response:
        """Handle incoming webhook POST events from Facebook Messenger."""
        signature = request.headers.get("X-Hub-Signature")
        body = await request.read()

        if not self._verify_signature(body, signature):
            self.logger.warning("Invalid webhook signature")
            self.metrics.increment("facebook_messenger.webhook.signature_failures")
            return web.Response(status=403)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.logger.error("Invalid JSON payload received")
            self.metrics.increment("facebook_messenger.webhook.invalid_json")
            return web.Response(status=400)

        await self._process_events(data)
        return web.Response(status=200)

    def _verify_signature(self, payload: bytes, signature: Optional[str]) -> bool:
        """Verify X-Hub-Signature header using app secret."""
        if not signature:
            return False
        try:
            sha_name, signature_hash = signature.split("=")
        except ValueError:
            return False
        if sha_name != "sha1":
            return False
        mac = hmac.new(self.app_secret.encode(), msg=payload, digestmod=hashlib.sha1)
        return hmac.compare_digest(mac.hexdigest(), signature_hash)

    async def _process_events(self, data: Dict[str, Any]):
        """Process each messaging event and send to UBP Orchestrator."""
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                ubp_event = self._convert_to_ubp_event(messaging_event)
                if ubp_event:
                    await self.send_event_to_orchestrator(ubp_event)

    def _convert_to_ubp_event(
        self, messaging_event: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Convert Facebook Messenger event to UBP event schema."""
        sender_id = messaging_event.get("sender", {}).get("id")
        recipient_id = messaging_event.get("recipient", {}).get("id")
        timestamp = messaging_event.get("timestamp")

        event_type = None
        content = {}

        if "message" in messaging_event:
            event_type = "facebook_messenger.message.received"
            content = messaging_event["message"]
        elif "postback" in messaging_event:
            event_type = "facebook_messenger.postback.received"
            content = messaging_event["postback"]
        else:
            self.logger.info(f"Unhandled messaging event: {messaging_event}")
            return None

        return {
            "event_type": event_type,
            "platform": "facebook_messenger",
            "timestamp": timestamp,
            "content": content,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "adapter_id": self.adapter_id,
        }

    async def send_event_to_orchestrator(self, event: Dict[str, Any]):
        """Send event to UBP Orchestrator with signing and observability."""
        try:
            if not hasattr(self, "orchestrator_ws") or self.orchestrator_ws is None:
                self.logger.warning(
                    "No orchestrator connection available, dropping event"
                )
                self.metrics.increment("facebook_messenger.events.dropped")
                return

            event_json = json.dumps(event)
            signature = self.security.sign_message(event_json)

            payload = {
                "message": event,
                "signature": signature,
            }

            await self.orchestrator_ws.send(json.dumps(payload))
            self.metrics.increment("facebook_messenger.events.sent")
            self.logger.info(f"Sent event to orchestrator: {event['event_type']}")

        except Exception as e:
            self.logger.error(f"Failed to send event to orchestrator: {e}")
            self.metrics.increment("facebook_messenger.events.failed")

    async def send_message(
        self, context: Any, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send message to Facebook Messenger via Send API.

        Expected message dict keys:
          - recipient_id: str
          - message: dict (Facebook Messenger message payload)

        Returns:
            Dict with success status and details.
        """
        recipient_id = message.get("recipient_id")
        msg_payload = message.get("message")

        if not recipient_id or not msg_payload:
            self.logger.error("Missing recipient_id or message payload")
            return {"success": False, "error": "Missing recipient_id or message"}

        url = f"https://graph.facebook.com/v15.0/me/messages?access_token={self.page_access_token}"
        payload = {
            "recipient": {"id": recipient_id},
            "message": msg_payload,
        }

        try:
            async with self.http_session.post(url, json=payload) as resp:
                resp.raise_for_status()
                resp_json = await resp.json()
                self.metrics.increment("facebook_messenger.messages.sent")
                self.logger.info(f"Message sent to {recipient_id}")
                return {"success": True, "result": resp_json}
        except ClientResponseError as e:
            self.logger.error(f"Failed to send message: {e.status} {e.message}")
            self.metrics.increment("facebook_messenger.messages.failed")
            return {"success": False, "error": f"HTTP {e.status}: {e.message}"}
        except Exception as e:
            self.logger.error(f"Exception sending message: {e}")
            self.metrics.increment("facebook_messenger.messages.failed")
            return {"success": False, "error": str(e)}
