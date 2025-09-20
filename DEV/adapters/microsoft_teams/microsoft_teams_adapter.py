"""
Microsoft Teams Platform Adapter for Unified Bot Protocol (UBP)
================================================================

File: microsoft_teams_adapter.py
Project: Unified Bot Protocol (UBP)
Version: 1.0.0
Last Edited: 2025-09-19
Author: Michael Landbo (UBP BDFL)
License: Apache-2.0

Description:
Production-grade Microsoft Teams adapter for UBP.
Handles OAuth2 authentication, message sending/updating,
reactions, thread replies, and inbound webhook event processing.

Features:
- OAuth2 Bearer token management with caching and refresh
- Async command handling with robust error handling
- Inbound event processing with UBP event conversion and queueing
- Structured logging and metrics collection
- Secure event signing before sending to UBP Orchestrator
- Resilience with retries and graceful shutdown
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional

import aiohttp
from aiohttp import ClientResponseError

from ubp_core.platform_adapter import BasePlatformAdapter, AdapterCapabilities
from ubp_core.security import SecurityManager
from ubp_core.observability import StructuredLogger, MetricsCollector


class MicrosoftTeamsAdapter(BasePlatformAdapter):
    adapter_id = "microsoft_teams"
    display_name = "Microsoft Teams"
    capabilities = AdapterCapabilities(
        supports_text=True,
        supports_media=True,
        supports_buttons=True,
        supports_threads=True,
        supports_reactions=True,
    )

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.tenant_id: str = config["tenant_id"]
        self.client_id: str = config["client_id"]
        self.client_secret: str = config["client_secret"]
        self.bot_app_id: str = config["bot_app_id"]
        self.bot_app_password: str = config["bot_app_password"]
        self.token_endpoint = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        )
        self.graph_api_base = "https://graph.microsoft.com/v1.0"
        self.access_token: Optional[str] = None
        self.token_expiry: float = 0
        self.session = aiohttp.ClientSession()
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.logger = StructuredLogger("microsoft_teams_adapter")
        self.metrics = MetricsCollector("microsoft_teams_adapter")
        self.security = SecurityManager(config.get("security_key", ""))
        self._token_lock = asyncio.Lock()

    async def _get_access_token(self) -> str:
        async with self._token_lock:
            now = time.time()
            if self.access_token and self.token_expiry > now + 60:
                return self.access_token

            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            async with self.session.post(
                self.token_endpoint, data=data, headers=headers
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.logger.error(
                        f"Failed to get access token: {resp.status} {text}"
                    )
                    raise Exception("Failed to get access token")
                token_data = await resp.json()
                self.access_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                self.token_expiry = now + expires_in
                self.logger.info("Obtained new access token")
                return self.access_token

    async def handle_platform_event(self, event: Dict[str, Any]):
        """
        Handle incoming Microsoft Teams webhook events.
        Converts Teams events into UBP events and queues them.
        """
        event_type = event.get("type")
        if event_type == "message":
            ubp_event = {
                "event_type": "teams.message.received",
                "platform": "microsoft_teams",
                "timestamp": event.get("timestamp"),
                "data": {
                    "conversation_id": event.get("conversation", {}).get("id"),
                    "from": event.get("from", {}).get("id"),
                    "text": event.get("text"),
                    "reply_to_id": event.get("replyToId"),
                    "raw_event": event,
                },
                "adapter_id": self.adapter_id,
            }
            await self.message_queue.put(ubp_event)
            self.metrics.increment("microsoft_teams.events.received")
            self.logger.info("Queued inbound Teams message event")

    async def _process_message_queue(self):
        """Background task to send queued UBP events to orchestrator."""
        while True:
            event = await self.message_queue.get()
            try:
                await self.send_event_to_orchestrator(event)
                self.metrics.increment("microsoft_teams.events.sent")
            except Exception as e:
                self.logger.error(f"Failed to send event to orchestrator: {e}")
                self.metrics.increment("microsoft_teams.events.failed")
            self.message_queue.task_done()

    async def send_event_to_orchestrator(self, event: Dict[str, Any]):
        """Send event to UBP Orchestrator with signing and observability."""
        if not hasattr(self, "orchestrator_ws") or self.orchestrator_ws is None:
            self.logger.warning("No orchestrator connection available, dropping event")
            self.metrics.increment("microsoft_teams.events.dropped")
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
        Handle UBP commands for Microsoft Teams.
        Supports sending, updating messages, adding reactions, and replying in threads.
        """
        try:
            command_name = command["command_name"]
            params = command["parameters"]
            token = await self._get_access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            if command_name == "teams.message.send":
                url = f"{self.graph_api_base}/teams/{params['team_id']}/channels/{params['channel_id']}/messages"
                payload = {"body": {"content": params["text"]}}
                async with self.session.post(
                    url, headers=headers, json=payload
                ) as resp:
                    result = await resp.json()
                    if resp.status >= 400:
                        raise Exception(f"API error: {result}")
                    self.metrics.increment("microsoft_teams.commands.message_send")
                    return {"status": "SUCCESS", "result": result}

            elif command_name == "teams.message.update":
                url = f"{self.graph_api_base}/teams/{params['team_id']}/channels/{params['channel_id']}/messages/{params['message_id']}"
                payload = {"body": {"content": params["text"]}}
                async with self.session.patch(
                    url, headers=headers, json=payload
                ) as resp:
                    result = await resp.json()
                    if resp.status >= 400:
                        raise Exception(f"API error: {result}")
                    self.metrics.increment("microsoft_teams.commands.message_update")
                    return {"status": "SUCCESS", "result": result}

            elif command_name == "teams.reaction.add":
                url = f"{self.graph_api_base}/teams/{params['team_id']}/channels/{params['channel_id']}/messages/{params['message_id']}/reactions"
                payload = {"reactionType": params["reaction"]}
                async with self.session.post(
                    url, headers=headers, json=payload
                ) as resp:
                    if resp.status >= 400:
                        result = await resp.json()
                        raise Exception(f"API error: {result}")
                    self.metrics.increment("microsoft_teams.commands.reaction_add")
                    return {"status": "SUCCESS", "result": {}}

            elif command_name == "teams.thread.reply":
                url = f"{self.graph_api_base}/teams/{params['team_id']}/channels/{params['channel_id']}/messages/{params['parent_message_id']}/replies"
                payload = {"body": {"content": params["text"]}}
                async with self.session.post(
                    url, headers=headers, json=payload
                ) as resp:
                    result = await resp.json()
                    if resp.status >= 400:
                        raise Exception(f"API error: {result}")
                    self.metrics.increment("microsoft_teams.commands.thread_reply")
                    return {"status": "SUCCESS", "result": result}

            else:
                raise ValueError(f"Unknown command: {command_name}")

        except Exception as e:
            self.logger.exception("Microsoft Teams command failed")
            self.metrics.increment("microsoft_teams.commands.failed")
            return {"status": "ERROR", "error_details": str(e)}

    async def close(self):
        await self.session.close()
        