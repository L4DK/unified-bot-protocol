# universal_webhook_adapter.py
"""
Universal Webhook Adapter for Unified Bot Protocol (UBP)
========================================================

File: universal_webhook_adapter.py
Project: Unified Bot Protocol (UBP)
Version: 1.0.0
Last Edit: 2025-09-17
Author: Michael Landbo

Description:
A universal webhook adapter that supports bidirectional webhook integration
with multiple platforms (Slack, GitHub, Telegram, etc.) and the UBP Orchestrator.
Handles incoming webhook requests, verifies signatures, transforms payloads,
and sends standardized UBP messages to the orchestrator. Also sends responses
back to platforms as needed.

Features:
- FastAPI HTTP server for webhook endpoints
- Signature verification and IP whitelisting
- Dynamic payload transformation per platform
- WebSocket connection to UBP Orchestrator
- Structured logging, metrics, and tracing
- Health and metrics endpoints
"""

import asyncio
import hmac
import hashlib
import ipaddress
import json
import logging
from typing import Dict, Any, List, Optional

import uvicorn
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import websockets

from ubp_core.observability import StructuredLogger, MetricsCollector, TracingManager

# Configuration example (should be loaded from file or env)
CONFIG = {
    "webhook": {
        "host": "0.0.0.0",
        "port": 8000,
        "ssl_enabled": False,
        "ssl_cert_path": "",
        "ssl_key_path": "",
        "allowed_ips": ["0.0.0.0/0"],
        "max_payload_size": 10 * 1024 * 1024,  # 10MB
    },
    "platforms": {
        "slack": {
            "signing_secret": "your_slack_signing_secret",
            "bot_token": "xoxb-your-slack-bot-token",
            "verification_token": "your_verification_token",
        },
        "github": {
            "webhook_secret": "your_github_webhook_secret",
            "api_token": "ghp_your_github_token",
        },
        "telegram": {
            "bot_token": "your_telegram_bot_token",
            "webhook_secret": "your_webhook_secret",
        },
    },
    "ubp": {
        "orchestrator_url": "ws://localhost:8080/ws/adapters",
        "adapter_id": "webhook_adapter_001",
        "security_key": "your_security_key_here",
    },
}

app = FastAPI(title="Universal Webhook Adapter (UBP)")

logger = StructuredLogger("universal_webhook_adapter")
metrics = MetricsCollector("universal_webhook_adapter")
tracer = TracingManager("universal_webhook_adapter")

orchestrator_ws: Optional[websockets.WebSocketClientProtocol] = None
connection_lock = asyncio.Lock()


def ip_allowed(client_ip: str, allowed_ranges: List[str]) -> bool:
    ip = ipaddress.ip_address(client_ip)
    for cidr in allowed_ranges:
        if ip in ipaddress.ip_network(cidr):
            return True
    return False


def verify_slack_signature(
    signing_secret: str, request_body: bytes, timestamp: str, slack_signature: str
) -> bool:
    basestring = f"v0:{timestamp}:{request_body.decode('utf-8')}".encode("utf-8")
    computed_signature = (
        "v0="
        + hmac.new(signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(computed_signature, slack_signature)


async def send_to_orchestrator(message: Dict[str, Any]) -> None:
    global orchestrator_ws
    if orchestrator_ws is None or orchestrator_ws.closed:
        logger.warning("Orchestrator WebSocket not connected")
        return
    try:
        await orchestrator_ws.send(json.dumps(message))
        metrics.increment("orchestrator.messages.sent")
    except Exception as e:
        logger.error(f"Failed to send message to orchestrator: {e}")
        metrics.increment("orchestrator.errors")


async def connect_to_orchestrator():
    global orchestrator_ws
    async with connection_lock:
        if orchestrator_ws and not orchestrator_ws.closed:
            return
        url = CONFIG["ubp"]["orchestrator_url"]
        headers = {
            "X-Adapter-ID": CONFIG["ubp"]["adapter_id"],
            "Authorization": f"Bearer {CONFIG['ubp']['security_key']}",
        }
        try:
            orchestrator_ws = await websockets.connect(url, extra_headers=headers)
            logger.info("Connected to UBP Orchestrator")
            asyncio.create_task(orchestrator_message_handler())
        except Exception as e:
            logger.error(f"Failed to connect to orchestrator: {e}")
            orchestrator_ws = None


async def orchestrator_message_handler():
    global orchestrator_ws
    try:
        async for message in orchestrator_ws:
            data = json.loads(message)
            logger.info(f"Received from orchestrator: {data}")
            # Process orchestrator messages if needed
    except websockets.ConnectionClosed:
        logger.warning("Orchestrator connection closed, reconnecting...")
        await connect_to_orchestrator()
    except Exception as e:
        logger.error(f"Error in orchestrator message handler: {e}")


@app.on_event("startup")
async def startup_event():
    await connect_to_orchestrator()


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/metrics")
async def metrics_endpoint():
    return JSONResponse(content=metrics.get_metrics())


@app.post("/webhook/slack")
async def slack_webhook(
    request: Request,
    x_slack_signature: str = Header(None),
    x_slack_request_timestamp: str = Header(None),
):
    client_ip = request.client.host
    if not ip_allowed(client_ip, CONFIG["webhook"]["allowed_ips"]):
        logger.warning(f"Blocked IP {client_ip}")
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.body()
    if not verify_slack_signature(
        CONFIG["platforms"]["slack"]["signing_secret"],
        body,
        x_slack_request_timestamp,
        x_slack_signature,
    ):
        logger.warning("Invalid Slack signature")
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    ubp_message = {
        "platform": "slack",
        "event_type": payload.get("type", "unknown"),
        "payload": payload,
    }
    await send_to_orchestrator(ubp_message)
    return {"status": "ok"}


@app.post("/webhook/github")
async def github_webhook(request: Request, x_hub_signature: str = Header(None)):
    client_ip = request.client.host
    if not ip_allowed(client_ip, CONFIG["webhook"]["allowed_ips"]):
        logger.warning(f"Blocked IP {client_ip}")
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.body()
    secret = CONFIG["platforms"]["github"]["webhook_secret"]
    signature = "sha1=" + hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
    if not hmac.compare_digest(signature, x_hub_signature):
        logger.warning("Invalid GitHub signature")
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    ubp_message = {
        "platform": "github",
        "event_type": payload.get("action", "unknown"),
        "payload": payload,
    }
    await send_to_orchestrator(ubp_message)
    return {"status": "ok"}


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    client_ip = request.client.host
    if not ip_allowed(client_ip, CONFIG["webhook"]["allowed_ips"]):
        logger.warning(f"Blocked IP {client_ip}")
        raise HTTPException(status_code=403, detail="Forbidden")

    payload = await request.json()
    ubp_message = {
        "platform": "telegram",
        "event_type": "telegram.update",
        "payload": payload,
    }
    await send_to_orchestrator(ubp_message)
    return {"status": "ok"}


# Generic webhook endpoint for other platforms
@app.post("/webhook/{platform_name}")
async def generic_webhook(platform_name: str, request: Request):
    client_ip = request.client.host
    if not ip_allowed(client_ip, CONFIG["webhook"]["allowed_ips"]):
        logger.warning(f"Blocked IP {client_ip}")
        raise HTTPException(status_code=403, detail="Forbidden")

    payload = await request.json()
    ubp_message = {
        "platform": platform_name,
        "event_type": "generic.webhook",
        "payload": payload,
    }
    await send_to_orchestrator(ubp_message)
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "universal_webhook_adapter:app",
        host=CONFIG["webhook"]["host"],
        port=CONFIG["webhook"]["port"],
        ssl_certfile=(
            CONFIG["webhook"]["ssl_cert_path"]
            if CONFIG["webhook"]["ssl_enabled"]
            else None
        ),
        ssl_keyfile=(
            CONFIG["webhook"]["ssl_key_path"]
            if CONFIG["webhook"]["ssl_enabled"]
            else None
        ),
        log_level="info",
        reload=True,
    )

# Run FastAPI server
uvicorn.run(app, host="0.0.0.0", port=8000)
