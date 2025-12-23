"""
FilePath: "/adapters/zabbix/zabbix_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: Zabbix Monitoring Adapter
Version: 2.1.0 (Refactored for BaseAdapter 1.3.0)
"""

import asyncio
import json
import time
import logging
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urljoin

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

class ZabbixAdapter(PlatformAdapter):
    """
    Official UBP Zabbix Adapter.
    Provides bidirectional integration:
    - Inbound: Polls for active triggers and accepts webhooks.
    - Outbound: Acknowledges events and updates host inventory.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Zabbix Config
        self.zabbix_config = config.get('zabbix', config)

        self.url = self.zabbix_config.get("zabbix_url")
        self.username = self.zabbix_config.get("username")
        self.password = self.zabbix_config.get("password")
        self.api_token = self.zabbix_config.get("api_token") # Preferred

        # Polling Settings
        self.poll_interval = self.zabbix_config.get("poll_interval", 30)

        # Webhook Settings
        self.webhook_host = self.zabbix_config.get("webhook_host", "0.0.0.0")
        self.webhook_port = self.zabbix_config.get("webhook_port", 8083)
        self.webhook_path = self.zabbix_config.get("webhook_path", "/zabbix/webhook")
        self.webhook_secret = self.zabbix_config.get("webhook_secret")

        # State
        self.auth_token = self.api_token
        self._processed_events = set()
        self._poll_task: Optional[asyncio.Task] = None

        # Webhook Server
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

        if not self.url:
            self.logger.error("Zabbix URL is missing in config")

    # --- Properties ---

    @property
    def platform_name(self) -> str:
        return "zabbix"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supported_capabilities={
                PlatformCapability.SEND_MESSAGE, # Bruges til Acknowledge
                PlatformCapability.WEBHOOK_SUPPORT,
                PlatformCapability.REAL_TIME_EVENTS
            },
            max_message_length=2048,
            rate_limits={"message.send": 100}
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="zabbix",
            display_name="Zabbix Monitoring",
            version="2.1.0",
            author="Michael Landbo",
            description="Enterprise Zabbix Integration with Bi-directional support",
            supports_webhooks=True,
            supports_real_time=True
        )

    # --- Lifecycle ---

    async def _setup_platform(self) -> None:
        """Starter login flow, webhook server og poller"""

        # 1. Login (hvis ikke token)
        if not self.auth_token and self.username and self.password:
            await self._authenticate()

        # 2. Start Webhook Server
        self._app.router.add_post(self.webhook_path, self._handle_webhook)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.webhook_host, self.webhook_port)
        await self._site.start()
        self.logger.info(f"Zabbix Webhook listening on {self.webhook_host}:{self.webhook_port}")

        # 3. Start Poller
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Lukker ned"""
        if self._poll_task:
            self._poll_task.cancel()

        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

        # Logout (Best practice)
        if self.auth_token and not self.api_token:
            await self._api_call("user.logout", [])

        await super().stop()

    # --- Core Logic: Send Message (Acknowledge) ---

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """
        I Zabbix kontekst bruges 'send_message' til at interagere med Events.
        F.eks. Acknowledge et problem.

        context.channel_id bør være 'event_id'.
        """
        try:
            event_id = context.channel_id
            content = message.get("content", "Acknowledged via UBP")

            # Hvis det er en Acknowledge kommando
            if message.get("type") == "acknowledge" or "ack" in content.lower():
                if not event_id:
                     return SimpleSendResult(False, error_message="Missing event_id (channel_id)")

                result = await self._api_call("event.acknowledge", {
                    "eventids": event_id,
                    "action": 6, # 2 (Ack) + 4 (Message)
                    "message": content
                })

                if "error" in result:
                     return SimpleSendResult(False, error_message=str(result["error"]))

                return SimpleSendResult(True, details=result.get("result"))

            # Fallback: Sender Command til Script (hvis implementeret) eller Trap
            return SimpleSendResult(False, error_message="Only 'acknowledge' supported for send_message currently")

        except Exception as e:
            self.logger.error(f"Zabbix Send Error: {e}")
            return SimpleSendResult(False, error_message=str(e))

    # --- API Helper ---

    async def _api_call(self, method: str, params: Any) -> Dict:
        """Udfører JSON-RPC kald til Zabbix"""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": int(time.time() * 1000)
        }

        if self.auth_token:
            payload["auth"] = self.auth_token

        api_endpoint = urljoin(self.url, "api_jsonrpc.php")

        try:
            async with self.http_session.post(api_endpoint, json=payload) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP Error {resp.status}")
                return await resp.json()
        except Exception as e:
            self.logger.error(f"Zabbix API Call Failed ({method}): {e}")
            return {"error": str(e)}

    async def _authenticate(self):
        """Logger ind og henter token"""
        res = await self._api_call("user.login", {
            "user": self.username,
            "password": self.password
        })

        if "result" in res:
            self.auth_token = res["result"]
            self.logger.info(f"Zabbix Authenticated. Token: {self.auth_token[:5]}...")
        else:
            self.logger.error(f"Zabbix Login Failed: {res.get('error')}")

    # --- Polling Logic ---

    async def _poll_loop(self):
        """Henter aktive triggers periodisk"""
        while not self._shutdown_event.is_set():
            try:
                if self.connected and self.auth_token:
                    await self._check_triggers()
            except Exception as e:
                self.logger.error(f"Polling Error: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _check_triggers(self):
        """Henter aktive problemer"""
        res = await self._api_call("trigger.get", {
            "output": ["triggerid", "description", "priority"],
            "filter": {"value": 1, "status": 0}, # Active problems, Enabled triggers
            "selectHosts": ["host"],
            "sortfield": "lastchange",
            "sortorder": "DESC",
            "limit": 20
        })

        if "result" not in res: return

        for trigger in res["result"]:
            trigger_id = trigger["triggerid"]

            # Simpel de-duplikering (i en rigtig DB løsning ville vi tjekke state)
            if trigger_id in self._processed_events:
                continue

            # Send til UBP
            await self._process_trigger(trigger)
            self._processed_events.add(trigger_id)

    async def _process_trigger(self, trigger: Dict):
        """Konverterer Zabbix Trigger til UBP Event"""
        host_name = trigger["hosts"][0]["host"] if trigger.get("hosts") else "Unknown"
        priority_map = {
            "0": "Not classified", "1": "Information", "2": "Warning",
            "3": "Average", "4": "High", "5": "Disaster"
        }
        severity = priority_map.get(trigger["priority"], "Unknown")

        context = AdapterContext(
            tenant_id="default",
            user_id="zabbix_system",
            channel_id=trigger["triggerid"], # Vi bruger triggerID som kanal ID for kontekst
            extras={"severity": severity, "host": host_name}
        )

        payload = {
            "type": "event",
            "content": f"PROBLEM: {trigger['description']} on {host_name} ({severity})",
            "metadata": {
                "source": "zabbix",
                "event_type": "trigger",
                "trigger_id": trigger["triggerid"],
                "severity_code": trigger["priority"]
            }
        }

        if self.connected:
            await self._send_to_orchestrator({
                "type": "platform_event",
                "context": context.to_dict(),
                "payload": payload
            })

    # --- Webhook Handling ---

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """Modtager Zabbix Macro Webhooks"""
        # Verificer evt. token fra header eller query param
        # if self.webhook_secret ...

        try:
            data = await request.json()

            # Zabbix sender typisk data struktureret via scriptet
            # { "event_id": "{EVENT.ID}", "trigger_name": "{TRIGGER.NAME}", ... }

            context = AdapterContext(
                tenant_id="default",
                user_id="zabbix_webhook",
                channel_id=str(data.get("event_id", "unknown")),
                extras={"host": data.get("host_name")}
            )

            payload = {
                "type": "event",
                "content": f"{data.get("status", "ALERT")}: {data.get('trigger_name')}",
                "metadata": {
                    "source": "zabbix_webhook",
                    "raw_data": data
                }
            }

            if self.connected:
                await self._send_to_orchestrator({
                    "type": "platform_event",
                    "context": context.to_dict(),
                    "payload": payload
                })

            return web.Response(text="OK")

        except Exception as e:
            self.logger.error(f"Webhook Error: {e}")
            return web.Response(status=500, text="Internal server error")

    async def handle_platform_event(self, event): pass
    async def handle_command(self, command): return {}
