"""
Facebook Website Platform Adapter for Unified Bot Protocol (UBP)
================================================================

File: facebook_website_adapter.py
Project: Unified Bot Protocol (UBP)
Version: 1.0.0
Last Edited: 2025-09-19
Author: Michael Landbo (UBP BDFL)
License: Apache-2.0

Description:
Production-grade Facebook Website adapter for UBP.
Handles Facebook Login status, Social Plugins, and Customer Chat Plugin events.
Supports inbound webhook event processing, outbound messaging, security,
observability, and resilience.

Features:
- Webhook verification and signature validation
- Async event processing with queueing
- Secure event signing before sending to UBP Orchestrator
- Outbound message sending via Facebook Messenger API
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


class FacebookWebsiteAdapter(BasePlatformAdapter):
    adapter_id = "facebook_website"
    display_name = "Facebook Website"
    capabilities = AdapterCapabilities(
        supports_text=True,
        supports_media=True,
        supports_buttons=True,
        supports_threads=False,
    )

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.app_id: str = config["app_id"]
        self.app_secret: str = config["app_secret"]
        self.page_access_token: str = config["page_access_token"]
        self.verify_token: Optional[str] = config.get("verify_token")
        self.logger = StructuredLogger("facebook_website_adapter")
        self.metrics = MetricsCollector("facebook_website_adapter")
        self.security = SecurityManager(config.get("security_key", ""))
        self.http_session = ClientSession()
        self._webhook_app = web.Application()
        self._setup_routes()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.message_queue: asyncio.Queue = asyncio.Queue()

    def _setup_routes(self):
        self._webhook_app.router.add_get("/webhook", self._handle_verification)
        self._webhook_app.router.add_post("/webhook", self._handle_webhook_event)

    async def start(self, host: str = "0.0.0.0", port: int = 8081):
        """Start the webhook HTTP server."""
        self.logger.info(f"Starting Facebook Website webhook server on {host}:{port}")
        self._runner = web.AppRunner(self._webhook_app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host, port)
        await self._site.start()
        self.logger.info("Facebook Website webhook server started")

        # Start background task to process queued events
        asyncio.create_task(self._process_message_queue())

    async def stop(self):
        """Stop the webhook HTTP server and cleanup."""
        self.logger.info("Stopping Facebook Website webhook server")
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        await self.http_session.close()
        self.logger.info("Facebook Website adapter stopped")

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
        """Handle incoming webhook POST events from Facebook Website plugins."""
        signature = request.headers.get("X-Hub-Signature")
        body = await request.read()

        if not self._verify_signature(body, signature):
            self.logger.warning("Invalid webhook signature")
            self.metrics.increment("facebook_website.webhook.signature_failures")
            return web.Response(status=403)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.logger.error("Invalid JSON payload received")
            self.metrics.increment("facebook_website.webhook.invalid_json")
            return web.Response(status=400)

        await self._handle_platform_event(data)
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

    async def _handle_platform_event(self, event: Dict[str, Any]):
        """
        Handle incoming Facebook Website events from webhooks or SDK callbacks.
        Converts events into UBP events and queues them.
        """
        event_type = event.get("event_type")
        if event_type == "login_status":
            ubp_event = {
                "event_type": "fb_website.login.status",
                "platform": "facebook_website",
                "timestamp": event.get("timestamp"),
                "data": {
                    "user_id": event.get("user_id"),
                    "status": event.get("status"),
                    "auth_response": event.get("auth_response"),
                    "raw_event": event,
                },
                "adapter_id": self.adapter_id,
            }
            await self.message_queue.put(ubp_event)

        elif event_type == "social_plugin_interaction":
            ubp_event = {
                "event_type": "fb_website.social_plugin.interaction",
                "platform": "facebook_website",
                "timestamp": event.get("timestamp"),
                "data": {
                    "plugin": event.get("plugin"),
                    "action": event.get("action"),
                    "user_id": event.get("user_id"),
                    "raw_event": event,
                },
                "adapter_id": self.adapter_id,
            }
            await self.message_queue.put(ubp_event)

        elif event_type == "customer_chat_message":
            ubp_event = {
                "event_type": "fb_website.customer_chat.message",
                "platform": "facebook_website",
                "timestamp": event.get("timestamp"),
                "data": {
                    "sender_id": event.get("sender_id"),
                    "message": event.get("message"),
                    "raw_event": event,
                },
                "adapter_id": self.adapter_id,
            }
            await self.message_queue.put(ubp_event)

        else:
            self.logger.warning(f"Unknown Facebook Website event type: {event_type}")
            self.metrics.increment("facebook_website.events.unknown")

    async def _process_message_queue(self):
        """Background task to send queued UBP events to orchestrator."""
        while True:
            event = await self.message_queue.get()
            try:
                await self.send_event_to_orchestrator(event)
                self.metrics.increment("facebook_website.events.sent")
            except Exception as e:
                self.logger.error(f"Failed to send event to orchestrator: {e}")
                self.metrics.increment("facebook_website.events.failed")
            self.message_queue.task_done()

    async def send_event_to_orchestrator(self, event: Dict[str, Any]):
        """Send event to UBP Orchestrator with signing and observability."""
        if not hasattr(self, "orchestrator_ws") or self.orchestrator_ws is None:
            self.logger.warning("No orchestrator connection available, dropping event")
            self.metrics.increment("facebook_website.events.dropped")
            return

        event_json = json.dumps(event)
        signature = self.security.sign_message(event_json)

        payload = {
            "message": event,
            "signature": signature,
        }

        await self.orchestrator_ws.send(json.dumps(payload))
        self.logger.info(f"Sent event to orchestrator: {event['event_type']}")

    async def handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle UBP commands for Facebook Website platform.
        Currently supports sending messages via Customer Chat Plugin.

        Note: Actual sending requires integration with Facebook Messenger API.
        """
        try:
            command_name = command["command_name"]
            params = command["parameters"]

            if command_name == "fb_website.customer_chat.send":
                recipient_id = params.get("recipient_id")
                message_payload = params.get("message")

                if not recipient_id or not message_payload:
                    raise ValueError("Missing recipient_id or message payload")

                url = f"https://graph.facebook.com/v15.0/me/messages?access_token={self.page_access_token}"
                payload = {
                    "recipient": {"id": recipient_id},
                    "message": message_payload,
                }

                async with self.http_session.post(url, json=payload) as resp:
                    resp.raise_for_status()
                    resp_json = await resp.json()
                    self.metrics.increment("facebook_website.messages.sent")
                    self.logger.info(f"Sent customer chat message to {recipient_id}")
                    return {"status": "SUCCESS", "result": resp_json}

            else:
                raise ValueError(f"Unknown command: {command_name}")

        except Exception as e:
            self.logger.exception("Facebook Website command failed")
            self.metrics.increment("facebook_website.commands.failed")
            return {"status": "ERROR", "error_details": str(e)}

    async def close(self):
        """Cleanup resources."""
        await self.http_session.close()
