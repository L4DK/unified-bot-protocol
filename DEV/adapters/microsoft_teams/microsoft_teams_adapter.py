"""
FilePath: "/adapters/microsoft_teams/microsoft_teams_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: Microsoft Teams Adapter
Version: 1.1.0 (Refactored for BaseAdapter 1.3.0)
"""

import asyncio
import logging
import json
import time
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

class MicrosoftTeamsAdapter(PlatformAdapter):
    """
    Official UBP Microsoft Teams Adapter.
    Uses Microsoft Graph API for messaging and runs a webhook server
    to receive events from Azure Bot Service.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Config Config
        self.teams_config = config.get('microsoft_teams', config)

        self.tenant_id = self.teams_config.get("tenant_id")
        self.client_id = self.teams_config.get("client_id")
        self.client_secret = self.teams_config.get("client_secret")
        self.bot_app_id = self.teams_config.get("bot_app_id")

        # Webhook Server Config
        self.host = self.teams_config.get("host", "0.0.0.0")
        self.port = self.teams_config.get("port", 3978) # Standard Bot Framework port

        # Auth State
        self.token_endpoint = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        self.graph_api_base = "https://graph.microsoft.com/v1.0"
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0
        self._token_lock = asyncio.Lock()

        # Webhook Server State
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

        if not self.client_id or not self.client_secret:
            self.logger.error("Microsoft Teams config missing 'client_id' or 'client_secret'")

    # --- Properties ---

    @property
    def platform_name(self) -> str:
        return "microsoft_teams"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supported_capabilities={
                PlatformCapability.SEND_MESSAGE,
                PlatformCapability.REPLY_MESSAGE,
                PlatformCapability.SEND_REACTION,
                PlatformCapability.CREATE_THREAD,
                PlatformCapability.WEBHOOK_SUPPORT
            },
            max_message_length=20000, # Teams har høje limits
            supported_media_types=["image/png", "image/jpeg", "application/pdf"],
            rate_limits={"message.send": 30}
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="microsoft_teams",
            display_name="Microsoft Teams",
            version="1.1.0",
            author="Michael Landbo",
            description="Microsoft Graph API integration for Teams",
            supports_webhooks=True,
            supports_real_time=True,
            supports_threading=True
        )

    # --- Lifecycle ---

    async def _setup_platform(self) -> None:
        """Starter webhook server og henter første token"""
        # 1. Setup Webhook Routes
        self._app.router.add_post("/api/messages", self._handle_inbound_activity)

        # 2. Start Server
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        self.logger.info(f"Teams Webhook listening on {self.host}:{self.port}")

        # 3. Initial Token Fetch (fail-fast hvis config er forkert)
        try:
            await self._get_access_token()
            self.logger.info("Successfully authenticated with Microsoft Graph")
        except Exception as e:
            self.logger.error(f"Failed Teams Authentication: {e}")
            # Vi stopper ikke nødvendigvis, da det kan være netværk

    async def stop(self) -> None:
        """Lukker serveren"""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        await super().stop()

    # --- Auth Helper ---

    async def _get_access_token(self) -> str:
        """Henter eller refresher OAuth2 token (thread-safe)"""
        async with self._token_lock:
            now = time.time()
            # Brug cachet token hvis gyldig (buffer på 60 sek)
            if self._access_token and self._token_expiry > now + 60:
                return self._access_token

            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            }

            # Vi bruger base-klassens http_session
            async with self.http_session.post(self.token_endpoint, data=data) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Token fetch failed: {resp.status} {text}")

                token_data = await resp.json()
                self._access_token = token_data["access_token"]
                self._token_expiry = now + token_data.get("expires_in", 3600)

                return self._access_token

    # --- Core Logic: Send Message ---

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """
        Sender besked til en kanal eller chat.
        Kræver 'team_id' og 'channel_id' i context for kanalbeskeder.
        """
        try:
            token = await self._get_access_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            # Extract IDs from context extras or direct fields
            team_id = context.extras.get("team_id")
            channel_id = context.channel_id

            if not team_id or not channel_id:
                # Fallback: Check om det er en 1:1 chat (conversation resource)
                # Note: Graph API for 1:1 chats er anderledes end Team Channel beskeder.
                # Her implementerer vi Team Channel logik som default.
                return SimpleSendResult(False, error_message="Missing 'team_id' or 'channel_id' in context")

            # API Endpoint
            # Hvis det er et svar i en tråd
            if context.extras.get("reply_to_id"):
                url = f"{self.graph_api_base}/teams/{team_id}/channels/{channel_id}/messages/{context.extras['reply_to_id']}/replies"
            else:
                url = f"{self.graph_api_base}/teams/{team_id}/channels/{channel_id}/messages"

            # Payload
            payload = {"body": {"content": message.get("content", "")}}

            # Send Request
            async with self.http_session.post(url, headers=headers, json=payload) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    return SimpleSendResult(False, error_message=f"Graph API Error {resp.status}: {text}")

                result = await resp.json()
                return SimpleSendResult(
                    success=True,
                    platform_message_id=result.get("id"),
                    details={"web_url": result.get("webUrl")}
                )

        except Exception as e:
            self.logger.error(f"Teams Send Error: {e}")
            return SimpleSendResult(success=False, error_message=str(e))

    # --- Webhook Handling (Inbound) ---

    async def _handle_inbound_activity(self, request: web.Request) -> web.Response:
        """Modtager events fra Azure Bot Service"""
        # I production bør man validere Authorization header (Bearer token)

        try:
            activity = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400)

        # Vi håndterer kun 'message' aktiviteter for nu
        if activity.get("type") == "message":
            await self._process_message_activity(activity)

        # Svar altid 200 OK hurtigt til Azure
        return web.Response(status=200)

    async def _process_message_activity(self, activity: Dict[str, Any]):
        """Konverterer Bot Framework Activity til UBP Message"""

        # Find ID'er
        channel_data = activity.get("channelData", {})
        team_id = channel_data.get("team", {}).get("id")
        channel_id = channel_data.get("channel", {}).get("id")
        tenant_id = channel_data.get("tenant", {}).get("id")

        # Context
        context = AdapterContext(
            tenant_id=tenant_id or "default",
            user_id=activity.get("from", {}).get("id"),
            channel_id=channel_id,
            extras={
                "team_id": team_id,
                "reply_to_id": activity.get("replyToId"), # Hvis brugeren svarede på en tråd
                "service_url": activity.get("serviceUrl"),
                "username": activity.get("from", {}).get("name")
            }
        )

        # Payload
        payload = {
            "type": "text",
            "content": activity.get("text", ""), # Note: Teams sender ofte HTML i text feltet
            "metadata": {
                "source": "microsoft_teams",
                "id": activity.get("id")
            }
        }

        if self.connected:
            await self._send_to_orchestrator({
                "type": "user_message",
                "context": context.to_dict(),
                "payload": payload
            })
            self.metrics["messages_received"] += 1

    async def handle_platform_event(self, event): pass

    async def handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Teams Specifikke Kommandoer (Reactions, etc.)"""
        cmd_name = command.get("command_name")
        params = command.get("parameters", {})

        if cmd_name == "teams.reaction.add":
            # Implementation af reaktioner via Graph API
            # (Kræver access token og POST request til /reactions endpoint)
            return {"status": "not_implemented_yet"}

        return {"status": "unknown_command"}
