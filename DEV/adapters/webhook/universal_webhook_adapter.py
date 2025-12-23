"""
FilePath: "/adapters/webhook/universal_webhook_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: Universal Webhook Adapter
Version: 1.1.0 (Refactored for BaseAdapter 1.3.0)
"""

import asyncio
import hmac
import hashlib
import ipaddress
import logging
import json
from typing import Dict, Any, List, Optional
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse

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

class UniversalWebhookAdapter(PlatformAdapter):
    """
    Official UBP Universal Webhook Adapter.
    Runs an embedded FastAPI server to receive webhooks from various platforms,
    verify their signatures, and forward them to the UBP Orchestrator.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Config parsing
        self.webhook_config = config.get('webhook', config)
        self.platforms_config = config.get('platforms', {})

        self.host = self.webhook_config.get("host", "0.0.0.0")
        self.port = self.webhook_config.get("port", 8000)
        self.allowed_ips = self.webhook_config.get("allowed_ips", ["0.0.0.0/0"])

        # Internal server state
        self._server_task: Optional[asyncio.Task] = None
        self._server: Optional[uvicorn.Server] = None
        self.app = FastAPI(title="UBP Universal Webhook Adapter")

    # --- Properties ---

    @property
    def platform_name(self) -> str:
        return "webhook"

    @property
    def capabilities(self) -> AdapterCapabilities:
        # Denne adapter understøtter både indgående (webhook) og udgående (HTTP POST)
        return AdapterCapabilities(
            supported_capabilities={
                PlatformCapability.WEBHOOK_SUPPORT,
                PlatformCapability.SEND_MESSAGE # Outbound webhooks
            },
            rate_limits={"message.send": 100}
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="webhook",
            display_name="Universal Webhook Receiver",
            version="1.1.0",
            author="Michael Landbo",
            description="Multi-platform webhook ingestion with signature verification",
            supports_webhooks=True,
            supports_real_time=True
        )

    # --- Lifecycle ---

    async def _setup_platform(self) -> None:
        """Konfigurerer FastAPI routes og starter serveren"""
        self._configure_routes()

        # Start Uvicorn Server i en baggrunds-task
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False # Vi bruger vores egen logger
        )
        self._server = uvicorn.Server(config)

        self.logger.info(f"Starting Webhook Server on {self.host}:{self.port}")
        self._server_task = asyncio.create_task(self._server.serve())

    async def stop(self) -> None:
        """Lukker serveren pænt ned"""
        if self._server:
            self._server.should_exit = True
            if self._server_task:
                await self._server_task
        await super().stop()

    # --- Core Logic: Outbound Webhooks (Send Message) ---

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """
        Sender et udgående HTTP POST request (Outbound Webhook).
        Target URL hentes fra context.channel_id eller message['url'].
        """
        try:
            target_url = message.get("url") or context.channel_id
            if not target_url or not target_url.startswith("http"):
                return SimpleSendResult(False, error_message="Invalid or missing target URL")

            payload = message.get("content") or message.get("payload", {})
            headers = message.get("headers", {"Content-Type": "application/json"})

            self.logger.info(f"Sending outbound webhook to {target_url}")

            async with self.http_session.post(target_url, json=payload, headers=headers) as resp:
                success = 200 <= resp.status < 300
                response_text = await resp.text()

                return SimpleSendResult(
                    success=success,
                    details={
                        "status_code": resp.status,
                        "response": response_text[:200] # Log de første 200 tegn
                    }
                )

        except Exception as e:
            self.logger.error(f"Outbound Webhook Error: {e}")
            return SimpleSendResult(success=False, error_message=str(e))

    # --- Internal: Route Configuration ---

    def _configure_routes(self):
        """Binder endpoints til klassens metoder"""

        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy", "adapter_status": self.status.value}

        @self.app.post("/webhook/slack")
        async def slack_webhook(
            request: Request,
            x_slack_signature: str = Header(None),
            x_slack_request_timestamp: str = Header(None),
        ):
            await self._check_ip(request)

            body = await request.body()
            secret = self.platforms_config.get("slack", {}).get("signing_secret")

            if secret and not self._verify_slack_signature(secret, body, x_slack_request_timestamp, x_slack_signature):
                self.logger.warning("Invalid Slack signature")
                raise HTTPException(status_code=401, detail="Unauthorized")

            payload = await request.json()
            # Ignorer challenge requests (Slack URL verification)
            if "challenge" in payload:
                return {"challenge": payload["challenge"]}

            await self._process_webhook("slack", payload.get("type", "unknown"), payload)
            return {"status": "ok"}

        @self.app.post("/webhook/github")
        async def github_webhook(request: Request, x_hub_signature: str = Header(None)):
            await self._check_ip(request)

            body = await request.body()
            secret = self.platforms_config.get("github", {}).get("webhook_secret")

            if secret and not self._verify_hmac_sha1(secret, body, x_hub_signature):
                 self.logger.warning("Invalid GitHub signature")
                 raise HTTPException(status_code=401, detail="Unauthorized")

            payload = await request.json()
            event_type = request.headers.get("X-GitHub-Event", "unknown")
            await self._process_webhook("github", event_type, payload)
            return {"status": "ok"}

        @self.app.post("/webhook/telegram")
        async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(None)):
            await self._check_ip(request)

            secret = self.platforms_config.get("telegram", {}).get("webhook_secret")
            if secret and secret != x_telegram_bot_api_secret_token:
                raise HTTPException(status_code=401, detail="Unauthorized")

            payload = await request.json()
            await self._process_webhook("telegram", "update", payload)
            return {"status": "ok"}

        @self.app.post("/webhook/{platform}")
        async def generic_webhook(platform: str, request: Request):
            await self._check_ip(request)
            payload = await request.json()
            await self._process_webhook(platform, "generic", payload)
            return {"status": "ok"}

    # --- Helper Methods ---

    async def _process_webhook(self, platform: str, event_type: str, payload: Dict[str, Any]):
        """Sender data til UBP Orchestrator"""

        # Context
        context = AdapterContext(
            tenant_id="default",
            user_id=payload.get("user_id") or payload.get("sender", {}).get("login"),
            channel_id=platform,
            extras={"event_type": event_type}
        )

        # UBP Message Structure
        ubp_msg = {
            "type": "event", # Webhooks er typisk events
            "content": payload,
            "metadata": {
                "source": f"webhook_{platform}",
                "event_type": event_type
            }
        }

        if self.connected:
            await self._send_to_orchestrator({
                "type": "platform_event",
                "context": context.to_dict(),
                "payload": ubp_msg
            })
            self.metrics["messages_received"] += 1

    async def _check_ip(self, request: Request):
        client_ip = request.client.host
        if not self._ip_allowed(client_ip):
            self.logger.warning(f"Blocked IP {client_ip}")
            raise HTTPException(status_code=403, detail="Forbidden")

    def _ip_allowed(self, client_ip: str) -> bool:
        if "0.0.0.0/0" in self.allowed_ips:
            return True
        try:
            ip = ipaddress.ip_address(client_ip)
            for cidr in self.allowed_ips:
                if ip in ipaddress.ip_network(cidr):
                    return True
        except ValueError:
            pass
        return False

    def _verify_slack_signature(self, secret: str, body: bytes, timestamp: str, signature: str) -> bool:
        if not timestamp or not signature: return False
        # Prevent replay attacks (5 min)
        # import time; if abs(time.time() - int(timestamp)) > 60 * 5: return False

        basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
        computed = "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, signature)

    def _verify_hmac_sha1(self, secret: str, body: bytes, signature: str) -> bool:
        if not signature: return False
        if signature.startswith("sha1="): signature = signature[5:]
        computed = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
        return hmac.compare_digest(computed, signature)

    async def handle_platform_event(self, event): pass
    async def handle_command(self, command): return {}
