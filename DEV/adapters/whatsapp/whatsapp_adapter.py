"""
FilePath: "/adapters/whatsapp/whatsapp_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: WhatsApp Business Adapter
Version: 1.1.0 (Refactored for BaseAdapter 1.3.0)
"""

import asyncio
import hmac
import hashlib
import logging
import json
from typing import Dict, Any, Optional

from aiohttp import web

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

class WhatsAppAdapter(PlatformAdapter):
    """
    Official UBP WhatsApp Adapter.
    Integrates with Meta's WhatsApp Cloud API.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Config
        self.wa_config = config.get('whatsapp', config)

        self.access_token = self.wa_config.get("access_token")
        self.phone_number_id = self.wa_config.get("phone_number_id")
        self.verify_token = self.wa_config.get("verify_token")
        self.app_secret = self.wa_config.get("app_secret")

        self.host = self.wa_config.get("host", "0.0.0.0")
        self.port = self.wa_config.get("port", 8082) # Standard port for WA

        self.api_version = "v17.0"
        self.api_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

        if not self.access_token or not self.phone_number_id:
            self.logger.error("WhatsApp config missing 'access_token' or 'phone_number_id'")

        # Webhook Server
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    # --- Properties ---

    @property
    def platform_name(self) -> str:
        return "whatsapp"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supported_capabilities={
                PlatformCapability.SEND_MESSAGE,
                PlatformCapability.SEND_IMAGE,
                PlatformCapability.SEND_DOCUMENT,
                PlatformCapability.SEND_AUDIO,
                PlatformCapability.SEND_VIDEO,
                PlatformCapability.SEND_BUTTONS, # Templates with buttons
                PlatformCapability.WEBHOOK_SUPPORT
            },
            max_message_length=4096,
            supported_media_types=["image/jpeg", "image/png", "application/pdf", "video/mp4"],
            rate_limits={"message.send": 80} # Cloud API limits varierer efter tier
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="whatsapp",
            display_name="WhatsApp Business",
            version="1.1.0",
            author="Michael Landbo",
            description="Meta WhatsApp Cloud API Integration",
            supports_webhooks=True,
            supports_real_time=True
        )

    # --- Lifecycle ---

    async def _setup_platform(self) -> None:
        """Starter webhook serveren"""
        self._app.router.add_get("/webhook", self._handle_verification)
        self._app.router.add_post("/webhook", self._handle_webhook_event)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        self.logger.info(f"WhatsApp Webhook listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        await super().stop()

    # --- Core Logic: Send Message ---

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """Sender besked til WhatsApp nummer"""
        try:
            recipient_id = context.channel_id or context.user_id
            if not recipient_id:
                return SimpleSendResult(False, error_message="Missing recipient phone number")

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            # Standard Text Message
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_id,
                "type": "text",
                "text": {"body": message.get("content", "")}
            }

            # Hvis template besked (krævet for at starte samtaler udenfor 24h vindue)
            if message.get("template"):
                payload["type"] = "template"
                payload.pop("text")
                payload["template"] = message["template"] # {name: "hello_world", language: {code: "en_US"}}

            # Media support
            elif message.get("image_url"):
                payload["type"] = "image"
                payload.pop("text")
                payload["image"] = {"link": message["image_url"]}

            # Send Request
            async with self.http_session.post(self.api_url, headers=headers, json=payload) as resp:
                resp_data = await resp.json()

                if resp.status >= 400:
                    return SimpleSendResult(
                        success=False,
                        error_message=f"WhatsApp API Error: {resp_data.get('error', {}).get('message')}",
                        details=resp_data
                    )

                return SimpleSendResult(
                    success=True,
                    platform_message_id=resp_data.get("messages", [{}])[0].get("id"),
                    details={"wa_id": resp_data.get("contacts", [{}])[0].get("wa_id")}
                )

        except Exception as e:
            self.logger.error(f"WhatsApp Send Error: {e}")
            return SimpleSendResult(success=False, error_message=str(e))

    # --- Webhook Handling ---

    async def _handle_verification(self, request: web.Request) -> web.Response:
        """Verify Token Check"""
        mode = request.query.get("hub.mode")
        token = request.query.get("hub.verify_token")
        challenge = request.query.get("hub.challenge")

        if mode == "subscribe" and token == self.verify_token:
            return web.Response(text=challenge)
        return web.Response(status=403)

    async def _handle_webhook_event(self, request: web.Request) -> web.Response:
        """Modtager beskeder"""
        # Signatur verificering (valgfri men anbefalet)
        signature = request.headers.get("X-Hub-Signature-256")
        body_bytes = await request.read()

        if self.app_secret and not self._verify_signature(body_bytes, signature):
            self.logger.warning("Invalid WhatsApp Signature")
            return web.Response(status=403)

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400)

        # Parse Event
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Check for messages
                if "messages" in value:
                    for msg in value["messages"]:
                        await self._process_incoming_message(value, msg)

                # Check for statuses (delivered, read)
                if "statuses" in value:
                    # Implementer status tracking her hvis ønsket
                    pass

        return web.Response(text="EVENT_RECEIVED")

    async def _process_incoming_message(self, value_data: Dict, message_data: Dict):
        """Konverterer WA besked til UBP"""

        sender_id = message_data.get("from") # Telefonnummer
        name = value_data.get("contacts", [{}])[0].get("profile", {}).get("name")

        context = AdapterContext(
            tenant_id="default",
            user_id=sender_id,
            channel_id=sender_id,
            extras={"name": name, "wa_id": message_data.get("id")}
        )

        msg_type = message_data.get("type")
        content = ""

        if msg_type == "text":
            content = message_data.get("text", {}).get("body", "")
        elif msg_type == "button":
            content = message_data.get("button", {}).get("text", "")
        else:
            content = f"[{msg_type} message]"

        payload = {
            "type": "text",
            "content": content,
            "metadata": {"source": "whatsapp", "type": msg_type}
        }

        if self.connected:
            await self._send_to_orchestrator({
                "type": "user_message",
                "context": context.to_dict(),
                "payload": payload
            })
            self.metrics["messages_received"] += 1

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        if not signature: return False
        expected = "sha256=" + hmac.new(
            key=self.app_secret.encode(),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_platform_event(self, event): pass
    async def handle_command(self, command): return {}
