"""
FilePath: "/adapters/facebook_messenger/facebook_messenger_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: Facebook Messenger Adapter
Version: 1.1.0 (Refactored for BaseAdapter 1.3.0)
"""

import asyncio
import hashlib
import hmac
import logging
import json
from typing import Dict, Any, Optional

from aiohttp import web, ClientSession

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

class FacebookMessengerAdapter(PlatformAdapter):
    """
    Official UBP Facebook Messenger Adapter.
    Handles Webhook events from Meta and sends messages via Graph API.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # FB Config
        self.fb_config = config.get('facebook_messenger', config)
        self.app_secret = self.fb_config.get("app_secret")
        self.page_access_token = self.fb_config.get("page_access_token")
        self.verify_token = self.fb_config.get("verify_token")
        self.port = self.fb_config.get("port", 8080)
        self.host = self.fb_config.get("host", "0.0.0.0")

        if not self.page_access_token or not self.app_secret:
            self.logger.error("Facebook Messenger config missing 'page_access_token' or 'app_secret'")

        # Webhook Server State
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    # --- Properties ---

    @property
    def platform_name(self) -> str:
        return "facebook_messenger"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supported_capabilities={
                PlatformCapability.SEND_MESSAGE,
                PlatformCapability.SEND_IMAGE,
                PlatformCapability.SEND_BUTTONS,
                PlatformCapability.SEND_CAROUSEL,
                PlatformCapability.WEBHOOK_SUPPORT
            },
            max_message_length=2000,
            supported_media_types=["image/jpeg", "image/png", "image/gif", "video/mp4", "audio/mpeg"],
            rate_limits={"message.send": 250} # Facebook har høje limits
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="facebook_messenger",
            display_name="Meta Messenger",
            version="1.1.0",
            author="Michael Landbo",
            description="Facebook Messenger Graph API Integration",
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

        self.logger.info(f"Messenger Webhook listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        await super().stop()

    # --- Core Logic: Send Message ---

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """Sender besked til Facebook bruger (PSID)"""
        try:
            recipient_id = context.channel_id or context.user_id # På FB er channel ofte = user PSID

            if not recipient_id:
                return SimpleSendResult(False, error_message="Missing recipient ID (PSID)")

            url = f"https://graph.facebook.com/v16.0/me/messages"
            params = {"access_token": self.page_access_token}

            payload = {
                "recipient": {"id": recipient_id},
                "messaging_type": "RESPONSE"
            }

            # Indhold
            content_text = message.get("content")
            if content_text:
                payload["message"] = {"text": content_text}
            elif message.get("attachment"):
                # Simpel attachment håndtering
                payload["message"] = {
                    "attachment": {
                        "type": message["attachment"].get("type", "image"),
                        "payload": {
                            "url": message["attachment"]["url"],
                            "is_reusable": True
                        }
                    }
                }

            # Send Request via Base Class http_session
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
            self.logger.error(f"FB Send Error: {e}")
            return SimpleSendResult(success=False, error_message=str(e))

    # --- Webhook Handling ---

    async def _handle_verification(self, request: web.Request) -> web.Response:
        """Facebook Verify Token Check (bruges når du sætter webhook op)"""
        mode = request.query.get("hub.mode")
        token = request.query.get("hub.verify_token")
        challenge = request.query.get("hub.challenge")

        if mode == "subscribe" and token == self.verify_token:
            return web.Response(text=challenge)
        return web.Response(status=403)

    async def _handle_webhook_event(self, request: web.Request) -> web.Response:
        """Modtager beskeder fra brugere"""
        # 1. Signatur Verifikation
        signature = request.headers.get("X-Hub-Signature-256") # Eller X-Hub-Signature
        body_bytes = await request.read()

        if self.app_secret and not self._verify_signature(body_bytes, signature):
            self.logger.warning("Invalid FB Signature")
            return web.Response(status=403)

        data = await request.json()

        if data.get("object") == "page":
            for entry in data.get("entry", []):
                # En entry kan indeholde flere messaging events
                webhook_event = entry.get("messaging", [])[0]

                sender_psid = webhook_event.get("sender", {}).get("id")

                if "message" in webhook_event:
                    await self._process_incoming_message(sender_psid, webhook_event["message"])
                elif "postback" in webhook_event:
                    await self._process_postback(sender_psid, webhook_event["postback"])

            return web.Response(text="EVENT_RECEIVED")

        return web.Response(status=404)

    async def _process_incoming_message(self, sender_id: str, message_data: Dict):
        """Konverter til UBP format"""
        context = AdapterContext(
            tenant_id="default",
            user_id=sender_id,
            channel_id=sender_id,
            extras={"mid": message_data.get("mid")}
        )

        payload = {
            "type": "text",
            "content": message_data.get("text", ""),
            "metadata": {"source": "facebook_messenger"}
        }

        # Attachments?
        if "attachments" in message_data:
            payload["type"] = "file"
            payload["attachments"] = message_data["attachments"]

        if self.connected:
            await self._send_to_orchestrator({
                "type": "user_message",
                "context": context.to_dict(),
                "payload": payload
            })
            self.metrics["messages_received"] += 1

    async def _process_postback(self, sender_id: str, postback: Dict):
        # Håndtering af knap-tryk
        payload_data = postback.get("payload")
        # Logik til at sende dette som en event eller besked til UBP...
        pass

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verificer HMAC SHA256"""
        if not signature: return False
        expected = "sha256=" + hmac.new(
            key=self.app_secret.encode(),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_platform_event(self, event): pass
    async def handle_command(self, command): return {}
