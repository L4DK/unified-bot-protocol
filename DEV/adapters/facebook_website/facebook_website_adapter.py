"""
FilePath: "/adapters/facebook_website/facebook_website_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: Facebook Website Adapter
Version: 1.1.0 (Refactored for BaseAdapter 1.3.0)
"""

import asyncio
import logging
import hmac
import hashlib
import json
from typing import Dict, Any, Optional

from aiohttp import web, ClientResponseError

# Import Base Adapter Classes
from adapters.base_adapter import (
    PlatformAdapter,
    AdapterCapabilities,
    AdapterMetadata,
    AdapterContext,
    PlatformCapability,
    SendResult,
    SimpleSendResult,
    AdapterStatus
)

class FacebookWebsiteAdapter(PlatformAdapter):
    """
    Official UBP Facebook Website Adapter.
    Handles events from Facebook Login, Social Plugins, and Customer Chat.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Konfiguration
        self.fb_config = config.get('facebook_website', config)
        self.app_id = self.fb_config.get("app_id")
        self.app_secret = self.fb_config.get("app_secret")
        self.page_access_token = self.fb_config.get("page_access_token")
        self.verify_token = self.fb_config.get("verify_token")
        self.host = self.fb_config.get("host", "0.0.0.0")
        self.port = self.fb_config.get("port", 8081) # Standard port 8081 for Website events

        if not self.app_secret or not self.page_access_token:
            self.logger.error("Facebook Website config missing 'app_secret' or 'page_access_token'")

        # Webhook Server State
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    # --- Properties ---

    @property
    def platform_name(self) -> str:
        return "facebook_website"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supported_capabilities={
                PlatformCapability.SEND_MESSAGE,    # Via Customer Chat Plugin
                PlatformCapability.WEBHOOK_SUPPORT, # Login status, plugin events
                PlatformCapability.REAL_TIME_EVENTS
            },
            max_message_length=2000,
            rate_limits={"message.send": 100}
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="facebook_website",
            display_name="Facebook Website Integration",
            version="1.1.0",
            author="Michael Landbo",
            description="Integration for FB Login, Social Plugins & Customer Chat",
            supports_webhooks=True,
            supports_real_time=True
        )

    # --- Lifecycle ---

    async def _setup_platform(self) -> None:
        """Sætter webhook routes op og starter serveren"""
        self._app.router.add_get("/webhook", self._handle_verification)
        self._app.router.add_post("/webhook", self._handle_webhook_event)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        self.logger.info(f"Facebook Website Webhook listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Lukker serveren pænt ned"""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        await super().stop()

    # --- Core Logic: Send Message ---

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """
        Sender besked via Facebook Customer Chat (Messenger API).
        Target er typisk en PSID (Page Scoped ID) fra en bruger der har startet en chat.
        """
        try:
            recipient_id = context.channel_id or context.user_id

            if not recipient_id:
                return SimpleSendResult(False, error_message="Missing recipient ID (PSID)")

            # Vi bruger samme API endpoint som Messenger, da Customer Chat er en extension af Messenger
            url = f"https://graph.facebook.com/v16.0/me/messages"
            params = {"access_token": self.page_access_token}

            payload = {
                "recipient": {"id": recipient_id},
                "messaging_type": "RESPONSE",
                "message": {"text": message.get("content", "")}
            }

            # Hvis der er attachments
            if message.get("attachment"):
                payload["message"]["attachment"] = message["attachment"]

            # Brug base-klassens http_session til outbound calls
            async with self.http_session.post(url, params=params, json=payload) as resp:
                resp_data = await resp.json()

                if resp.status != 200:
                    return SimpleSendResult(
                        success=False,
                        error_message=f"FB API Error: {resp_data.get('error', {}).get('message')}",
                        details=resp_data
                    )

                return SimpleSendResult(
                    success=True,
                    platform_message_id=resp_data.get("message_id"),
                    details={"recipient_id": resp_data.get("recipient_id")}
                )

        except Exception as e:
            self.logger.error(f"FB Website Send Error: {e}")
            return SimpleSendResult(success=False, error_message=str(e))

    # --- Webhook Handling ---

    async def _handle_verification(self, request: web.Request) -> web.Response:
        """Håndterer Facebooks 'Verify Token' challenge"""
        mode = request.query.get("hub.mode")
        token = request.query.get("hub.verify_token")
        challenge = request.query.get("hub.challenge")

        if mode == "subscribe" and token == self.verify_token:
            return web.Response(text=challenge)
        return web.Response(status=403)

    async def _handle_webhook_event(self, request: web.Request) -> web.Response:
        """Modtager events fra Facebook (Login, Plugins)"""
        signature = request.headers.get("X-Hub-Signature")
        body = await request.read()

        if self.app_secret and not self._verify_signature(body, signature):
            self.logger.warning("Invalid FB Signature")
            return web.Response(status=403)

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400)

        # Processer data asynkront
        await self._process_incoming_data(data)
        return web.Response(status=200)

    async def _process_incoming_data(self, data: Dict[str, Any]):
        """Konverterer events til UBP format"""
        # Facebook Website events kan variere meget afhængig af plugin
        # Her håndterer vi de mest gængse typer (custom implementation)

        event_type = data.get("event_type") # Hvis data kommer fra en custom JS integration

        # Hvis det er en standard webhook entry struktur (ligesom Messenger)
        if data.get("object") == "page":
            for entry in data.get("entry", []):
                for messaging in entry.get("messaging", []):
                    await self._process_messaging_event(messaging)
            return

        # Hvis det er Login Status eller Social Plugin events
        if event_type:
            context = AdapterContext(
                tenant_id="default",
                user_id=data.get("user_id"),
                channel_id="facebook_website",
                extras={"plugin": data.get("plugin")}
            )

            payload = {
                "type": "event",
                "content": data,
                "metadata": {"event_type": event_type, "source": "facebook_website"}
            }

            if self.connected:
                await self._send_to_orchestrator({
                    "type": "platform_event",
                    "context": context.to_dict(),
                    "payload": payload
                })

    async def _process_messaging_event(self, event: Dict):
        """Håndterer Customer Chat beskeder"""
        sender_id = event.get("sender", {}).get("id")
        if "message" in event:
            context = AdapterContext(
                tenant_id="default",
                user_id=sender_id,
                channel_id=sender_id, # I Customer Chat er kanal = bruger
                extras={"source": "customer_chat_plugin"}
            )

            payload = {
                "type": "text",
                "content": event["message"].get("text", ""),
                "metadata": {"mid": event["message"].get("mid")}
            }

            if self.connected:
                await self._send_to_orchestrator({
                    "type": "user_message",
                    "context": context.to_dict(),
                    "payload": payload
                })
                self.metrics["messages_received"] += 1

    def _verify_signature(self, payload: bytes, signature: Optional[str]) -> bool:
        """Verificer HMAC SHA1 (Facebook bruger SHA1 til nogle webhooks, SHA256 til andre)"""
        if not signature: return False
        try:
            sha_name, signature_hash = signature.split("=")
        except ValueError:
            return False

        if sha_name != "sha1":
            return False

        mac = hmac.new(self.app_secret.encode(), msg=payload, digestmod=hashlib.sha1)
        return hmac.compare_digest(mac.hexdigest(), signature_hash)

    async def handle_platform_event(self, event): pass
    async def handle_command(self, command): return {}
