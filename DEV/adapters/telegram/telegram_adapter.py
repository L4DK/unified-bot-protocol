"""
FilePath: "/adapters/telegram/telegram_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: Telegram Adapter Implementation
Version: 2.1.0 (Refactored for BaseAdapter 1.3.0)
"""

import asyncio
import aiohttp
import logging
import json
import time
from typing import Dict, Any, List, Optional, Union
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

class TelegramAdapter(PlatformAdapter):
    """
    Official UBP Telegram Adapter.
    Supports Long Polling and Webhooks with full async capabilities.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Configuration
        self.tg_config = config.get('telegram', {}) if 'telegram' in config else config
        self.bot_token = self.tg_config.get('bot_token')
        self.use_webhook = self.tg_config.get('use_webhook', False)
        self.webhook_url = self.tg_config.get('webhook_url')
        self.webhook_port = self.tg_config.get('webhook_port', 8443)
        self.webhook_secret = self.tg_config.get('webhook_secret', '')

        if not self.bot_token:
            self.logger.error("Telegram Bot Token is missing in configuration!")

        # API Endpoints
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"
        self.file_base = f"https://api.telegram.org/file/bot{self.bot_token}"

        # State
        self.session: Optional[aiohttp.ClientSession] = None
        self._polling_task: Optional[asyncio.Task] = None
        self._webhook_site: Optional[web.TCPSite] = None
        self.update_offset = 0

    # --- Properties ---

    @property
    def platform_name(self) -> str:
        return "telegram"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supported_capabilities={
                PlatformCapability.SEND_MESSAGE,
                PlatformCapability.SEND_IMAGE,
                PlatformCapability.SEND_AUDIO,
                PlatformCapability.SEND_DOCUMENT,
                PlatformCapability.SEND_BUTTONS,
                PlatformCapability.EDIT_MESSAGE
            },
            max_message_length=4096,
            supported_media_types=["image/jpeg", "image/png", "audio/mpeg", "video/mp4"],
            rate_limits={"message.send": 30}
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="telegram",
            display_name="Telegram Bot API",
            version="2.1.0",
            author="Michael Landbo",
            description="Production-ready Telegram adapter with Polling/Webhook support",
            supports_webhooks=True,
            supports_real_time=True
        )

    # --- Lifecycle ---

    async def _setup_platform(self) -> None:
        """Initialize HTTP session and start polling/webhook"""
        self.session = aiohttp.ClientSession()

        # Verify Token & Connection
        try:
            me = await self._api_call("getMe")
            self.logger.info(f"Telegram connected as @{me.get('username')} (ID: {me.get('id')})")
        except Exception as e:
            self.logger.error(f"Failed to connect to Telegram: {e}")
            self.status = AdapterStatus.ERROR
            return

        # Start Listening Mode
        if self.use_webhook and self.webhook_url:
            await self._start_webhook()
        else:
            await self._start_polling()

    async def stop(self) -> None:
        """Cleanup resources"""
        if self._polling_task:
            self._polling_task.cancel()

        if self._webhook_site:
            await self._webhook_site.stop()

        if self.session:
            await self.session.close()

        await super().stop()

    # --- Core Logic: Send Message ---

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """Implementation of sending messages to Telegram"""
        try:
            chat_id = context.channel_id or context.user_id
            if not chat_id:
                return SimpleSendResult(False, error_message="Missing chat_id (channel_id or user_id)")

            content_text = message.get("content", "")
            msg_type = message.get("type", "text")

            payload = {"chat_id": chat_id}
            method = "sendMessage"

            # Message Type Handling
            if msg_type == "text":
                payload["text"] = content_text
                payload["parse_mode"] = "HTML" # Default to HTML for better formatting

            elif msg_type == "image":
                method = "sendPhoto"
                payload["photo"] = message.get("url") or message.get("file_id")
                if content_text:
                    payload["caption"] = content_text

            # Execute
            result = await self._api_call(method, payload)

            return SimpleSendResult(
                success=True,
                platform_message_id=str(result.get("message_id")),
                details={"chat_id": str(result.get("chat", {}).get("id"))}
            )

        except Exception as e:
            self.logger.error(f"Telegram Send Error: {e}")
            return SimpleSendResult(success=False, error_message=str(e))

    # --- Internal: API & Event Handling ---

    async def _api_call(self, method: str, data: Dict = None) -> Dict:
        """Helper for raw Telegram API calls"""
        url = f"{self.api_base}/{method}"
        async with self.session.post(url, json=data or {}) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Telegram API Error {resp.status}: {text}")
            result = await resp.json()
            if not result.get("ok"):
                raise Exception(f"Telegram API Logic Error: {result}")
            return result.get("result")

    # --- Polling Logic ---

    async def _start_polling(self):
        """Starts background task for Long Polling"""
        self.logger.info("Starting Telegram Long Polling...")
        # Clean existing webhooks first to ensure polling works
        await self._api_call("deleteWebhook", {"drop_pending_updates": True})
        self._polling_task = asyncio.create_task(self._polling_loop())

    async def _polling_loop(self):
        while not self._shutdown_event.is_set():
            try:
                updates = await self._api_call("getUpdates", {
                    "offset": self.update_offset,
                    "timeout": 30,
                    "allowed_updates": ["message", "callback_query"]
                })

                for update in updates:
                    self.update_offset = update["update_id"] + 1
                    await self._handle_telegram_update(update)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Polling error: {e}")
                await asyncio.sleep(5) # Wait before retry

    # --- Webhook Logic ---

    async def _start_webhook(self):
        """Sets up the Webhook server"""
        self.logger.info(f"Setting up Telegram Webhook at {self.webhook_url}")

        # 1. Register Webhook with Telegram
        await self._api_call("setWebhook", {
            "url": f"{self.webhook_url}/webhook/telegram",
            "secret_token": self.webhook_secret
        })

        # 2. Start Local Server
        app = web.Application()
        app.router.add_post("/webhook/telegram", self._webhook_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        self._webhook_site = web.TCPSite(runner, "0.0.0.0", self.webhook_port)
        await self._webhook_site.start()
        self.logger.info(f"Telegram Webhook Server listening on port {self.webhook_port}")

    async def _webhook_handler(self, request):
        """Handle incoming webhook requests"""
        # Security check
        if self.webhook_secret:
            token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if token != self.webhook_secret:
                return web.Response(status=403)

        data = await request.json()
        await self._handle_telegram_update(data)
        return web.Response(text="OK")

    # --- Event Processing ---

    async def _handle_telegram_update(self, update: Dict):
        """Converts incoming Telegram update to UBP format"""
        # Vi håndterer kun beskeder lige nu, kan udvides til callback_query osv.
        message = update.get("message")
        if not message:
            return

        # Build Context
        context = AdapterContext(
            tenant_id="default",
            user_id=str(message.get("from", {}).get("id")),
            channel_id=str(message.get("chat", {}).get("id")),
            extras={
                "username": message.get("from", {}).get("username"),
                "chat_type": message.get("chat", {}).get("type")
            }
        )

        # Build Payload
        payload = {
            "type": "text",
            "content": message.get("text", ""),
            "message_id": str(message.get("message_id"))
        }

        # Send to UBP Logic (hvis forbundet)
        if self.connected:
            await self._send_to_orchestrator({
                "type": "user_message",
                "context": context.to_dict(),
                "payload": payload
            })
            self.metrics["messages_received"] += 1

    async def handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Extra commands support"""
        return {"status": "not_implemented"}
