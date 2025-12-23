"""
FilePath: "/adapters/slack/slack_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: Slack Adapter Implementation
Version: 1.2.0 (Refactored for BaseAdapter 1.3.0)
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.socket_mode.request import SocketModeRequest

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

class SlackAdapter(PlatformAdapter):
    """
    Official UBP Slack Adapter.
    Uses Slack Socket Mode for firewall-friendly, real-time communication.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Hent config (støtter både direkte keys og nested 'slack' key)
        self.slack_config = config.get('slack', config)
        self.bot_token = self.slack_config.get("bot_token")
        self.app_token = self.slack_config.get("app_token")

        if not self.bot_token or not self.app_token:
            self.logger.error("Slack Bot Token (xoxb-) or App Token (xapp-) is missing!")

        # Clients init
        self.web_client = AsyncWebClient(token=self.bot_token)
        self.socket_client = SocketModeClient(
            app_token=self.app_token,
            web_client=self.web_client
        )

        self._socket_task: Optional[asyncio.Task] = None

    # --- Properties ---

    @property
    def platform_name(self) -> str:
        return "slack"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supported_capabilities={
                PlatformCapability.SEND_MESSAGE,
                PlatformCapability.REPLY_MESSAGE,
                PlatformCapability.SEND_REACTION,
                PlatformCapability.SEND_IMAGE,
                PlatformCapability.SEND_DOCUMENT,
                PlatformCapability.CREATE_THREAD
            },
            max_message_length=40000, # Slacks limit er højt
            supported_media_types=["image/png", "image/jpeg", "application/pdf", "text/plain"],
            rate_limits={"message.send": 1} # Ca. 1 request per sec per channel
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="slack",
            display_name="Slack Integration",
            version="1.2.0",
            author="Michael Landbo",
            description="Socket Mode Slack adapter for UBP",
            supports_real_time=True,
            supports_threading=True,
            supports_reactions=True
        )

    # --- Lifecycle ---

    async def _setup_platform(self) -> None:
        """Klargør Slack Socket Mode"""
        # 1. Registrer event listener
        self.socket_client.socket_mode_request_listeners.append(self._handle_socket_request)

        # 2. Test Auth
        try:
            auth_test = await self.web_client.auth_test()
            self.logger.info(f"Slack connected as {auth_test.get('bot_id')} (User: {auth_test.get('user')})")
        except Exception as e:
            self.logger.error(f"Slack Auth Failed: {e}")
            self.status = AdapterStatus.ERROR
            return

        # 3. Start Socket Mode i baggrunden
        # connect() er async og holder forbindelsen åben, så vi kører den som task
        self._socket_task = asyncio.create_task(self.socket_client.connect())

    async def stop(self) -> None:
        """Lukker forbindelserne"""
        if self._socket_task:
            await self.socket_client.close()
            self._socket_task.cancel()

        # Der er ikke en eksplicit close på AsyncWebClient (den bruger aiohttp session internt),
        # men SocketModeClient tager sig typisk af sessionen.
        await super().stop()

    # --- Core Logic: Send Message ---

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """Sender besked til Slack kanal eller tråd"""
        try:
            channel_id = context.channel_id
            if not channel_id:
                return SimpleSendResult(False, error_message="Missing channel_id")

            content = message.get("content", "")

            # Parametre til chat_postMessage
            params = {
                "channel": channel_id,
                "text": content
            }

            # Threading support
            # Hvis vi svarer i en tråd, eller context har thread_ts
            if context.extras.get("thread_ts"):
                params["thread_ts"] = context.extras.get("thread_ts")

            # Blocks / Rich Text support (hvis UBP message indeholder 'blocks')
            if "blocks" in message:
                params["blocks"] = message["blocks"]

            # Udfør kaldet
            resp = await self.web_client.chat_postMessage(**params)

            if not resp.get("ok"):
                return SimpleSendResult(False, error_message=f"Slack API Error: {resp.get('error')}")

            return SimpleSendResult(
                success=True,
                platform_message_id=resp.get("ts"),
                details={
                    "channel": resp.get("channel"),
                    "thread_ts": resp.get("thread_ts")
                }
            )

        except Exception as e:
            self.logger.error(f"Slack Send Error: {e}")
            return SimpleSendResult(success=False, error_message=str(e))

    # --- Event Handling (Slack -> UBP) ---

    async def _handle_socket_request(self, client: SocketModeClient, req: SocketModeRequest):
        """Modtager events fra Socket Mode"""
        # 1. Acknowledge med det samme (krævet af Slack)
        if req.type == "events_api" or req.type == "interactive":
            await client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        # 2. Behandl payload
        if req.type == "events_api":
            event = req.payload.get("event", {})

            # Ignorer bot beskeder for at undgå loops
            if event.get("bot_id") or event.get("subtype") == "bot_message":
                return

            if event.get("type") == "message":
                await self._process_message_event(event)

        # Her kan vi tilføje håndtering af "interactive" (knapper) og "slash_commands"

    async def _process_message_event(self, event: Dict[str, Any]):
        """Konverterer Slack Message til UBP"""

        # Context
        context = AdapterContext(
            tenant_id="default",
            user_id=event.get("user"),
            channel_id=event.get("channel"),
            extras={
                "thread_ts": event.get("thread_ts"), # Vigtig for tråde
                "event_ts": event.get("ts")
            }
        )

        # Payload
        payload = {
            "type": "text",
            "content": event.get("text", ""),
            "metadata": {
                "ts": event.get("ts")
            }
        }

        # Send til Runtime/Orchestrator
        if self.connected:
            await self._send_to_orchestrator({
                "type": "user_message",
                "context": context.to_dict(),
                "payload": payload
            })
            self.metrics["messages_received"] += 1

    async def handle_platform_event(self, event: Dict[str, Any]) -> None:
        # Bruges hvis vi kørte HTTP webhook i stedet for Socket Mode
        pass

    async def handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Ekstra Slack-specifikke kommandoer"""
        cmd = command.get("command_name")
        params = command.get("parameters", {})

        if cmd == "slack.reaction.add":
            try:
                await self.web_client.reactions_add(
                    channel=params["channel"],
                    name=params["reaction"],
                    timestamp=params["message_ts"]
                )
                return {"status": "SUCCESS"}
            except Exception as e:
                return {"status": "ERROR", "error": str(e)}

        return {"status": "UNKNOWN_COMMAND"}
