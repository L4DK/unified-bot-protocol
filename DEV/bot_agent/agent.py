# FilePath: "/DEV/bot_agent/agent.py"
# Project: Unified Bot Protocol (UBP)
# Description: Reference Bot Agent. Handles Onboarding, C2 connection, Heartbeats, and Commands.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.2.0.0" (Updated for Split URL Architecture)

import asyncio
import json
import logging
import sys
import uuid
import os
from contextlib import asynccontextmanager
from typing import Dict, Optional

import websockets
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, generate_latest
from starlette.responses import Response
from websockets.client import WebSocketClientProtocol

# Import Settings
try:
    from .settings import get_settings
except ImportError:
    from settings import get_settings

# =========================
# Setup & Logging
# =========================
settings = get_settings()

class JsonFormatter(logging.Formatter):
    """Formats logs as JSON for better machine reading (Splunk/ELK)."""
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": record.created,
            "level": record.levelname,
            "service": "ubp_bot",
            "bot_id": settings.BOT_ID,
            "message": record.getMessage(),
        }
        if hasattr(record, "trace_id"):
            payload["trace_id"] = record.trace_id
        return json.dumps(payload)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("UBP.Bot")
# For production: logger.handlers[0].setFormatter(JsonFormatter())

# =========================
# Metrics
# =========================
CONNECTED_GAUGE = Gauge('ubp_connected', 'Is bot connected to orchestrator')
COMMANDS_COUNTER = Counter('ubp_commands_total', 'Total commands received', ['command'])
HEARTBEAT_COUNTER = Counter('ubp_heartbeats_total', 'Total heartbeats sent')

# =========================
# Bot Logic
# =========================
class BotAgent:
    def __init__(self):
        self.settings = settings
        self.instance_id = f"{settings.BOT_ID}-{str(uuid.uuid4())[:8]}"
        self.api_key: Optional[str] = self._load_credentials()

        self.websocket: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self.heartbeat_interval = 30
        self._stop_event = asyncio.Event()

    def _load_credentials(self) -> Optional[str]:
        """Loads API Key from disk if it exists."""
        try:
            if self.settings.credentials_file.exists():
                with open(self.settings.credentials_file, "r") as f:
                    data = json.load(f)
                    return data.get("api_key")
        except Exception as e:
            logger.warning(f"Could not load credentials: {e}")
        return None

    def _save_credentials(self, api_key: str):
        """Saves API Key securely to disk."""
        try:
            self.settings.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.settings.credentials_file, "w") as f:
                json.dump({"api_key": api_key}, f)
            logger.info("Credentials saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")

    async def start(self):
        """Main loop: Controls connection logic."""
        logger.info(f"Starting Bot Agent: {self.settings.BOT_ID}")

        while not self._stop_event.is_set():
            if not self.api_key:
                # No key? Start Onboarding flow
                success = await self._perform_onboarding()
                if not success:
                    logger.error("Onboarding failed. Retrying in 10s...")
                    await asyncio.sleep(10)
                    continue

            # Have key? Start C2 flow
            await self._connect_c2()

            if not self._stop_event.is_set():
                logger.info("Connection lost. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _perform_onboarding(self) -> bool:
        """Connects to /ws/onboarding to exchange Initial Token for API Key."""
        url = f"{self.settings.ORCHESTRATOR_URL}/ws/onboarding"
        logger.info(f"Initiating onboarding at {url}")

        try:
            async with websockets.connect(url) as ws:
                # Send Handshake with Initial Token
                payload = {
                    "bot_id": self.settings.BOT_ID,
                    "auth_token": self.settings.INITIAL_TOKEN,
                    "metadata": {"version": self.settings.AGENT_VERSION}
                }
                await ws.send(json.dumps(payload))

                # Await response
                response = json.loads(await ws.recv())

                if response.get("status") == "SUCCESS":
                    new_key = response.get("api_key")
                    if new_key:
                        self.api_key = new_key
                        self._save_credentials(new_key)
                        logger.info("Onboarding successful! API Key obtained.")
                        return True

                logger.error(f"Onboarding failed: {response}")
                return False

        except Exception as e:
            logger.error(f"Onboarding connection error: {e}")
            return False

    async def _connect_c2(self) -> None:
        """Connects to /ws/c2 for operations."""
        url = f"{self.settings.ORCHESTRATOR_URL}/ws/c2"
        logger.info(f"Connecting to C2 at {url}")

        try:
            async with websockets.connect(url) as ws:
                self.websocket = ws
                self.connected = True
                CONNECTED_GAUGE.set(1)

                # 1. Send Handshake with API Key
                handshake = {
                    "handshake": {
                        "bot_id": self.settings.BOT_ID,
                        "instance_id": self.instance_id,
                        "auth": {"api_key": self.api_key},
                        "capabilities": list(self.settings.CAPABILITIES)
                    }
                }
                await ws.send(json.dumps(handshake))

                # 2. Wait for Auth Success
                resp = json.loads(await ws.recv())
                if resp.get("handshake_response", {}).get("status") != "SUCCESS":
                    logger.error(f"C2 Handshake failed: {resp}")
                    return

                logger.info("C2 Connected & Authenticated.")

                # 3. Start Heartbeat Task
                hb_task = asyncio.create_task(self._heartbeat_loop())

                # 4. Message Loop
                async for message in ws:
                    await self._handle_message(message)

                # Cleanup
                hb_task.cancel()

        except Exception as e:
            logger.error(f"C2 Connection error: {e}")
        finally:
            self.connected = False
            CONNECTED_GAUGE.set(0)

    async def _heartbeat_loop(self):
        """Sends periodic heartbeats."""
        try:
            while self.connected:
                await asyncio.sleep(self.heartbeat_interval)
                if self.websocket:
                    hb = {
                        "heartbeat": {
                            "timestamp": str(asyncio.get_event_loop().time()),
                            "metrics": {"uptime": "ok"}
                        }
                    }
                    await self.websocket.send(json.dumps(hb))
                    HEARTBEAT_COUNTER.inc()
        except asyncio.CancelledError:
            pass

    async def _handle_message(self, raw_msg: str):
        """Handles incoming messages (Commands)."""
        try:
            data = json.loads(raw_msg)

            if "command_request" in data:
                cmd = data["command_request"]
                cmd_name = cmd.get("command_name")
                cmd_id = cmd.get("command_id")

                COMMANDS_COUNTER.labels(command=cmd_name).inc()
                logger.info(f"Executing command: {cmd_name}")

                # Simulate work
                await asyncio.sleep(1)

                # Send response
                response = {
                    "command_response": {
                        "command_id": cmd_id,
                        "status": "SUCCESS",
                        "result": {"output": f"Executed {cmd_name}"}
                    }
                }
                await self.websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error handling message: {e}")

# =========================
# FastAPI Wrapper (Health)
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start Bot Agent in background
    agent_task = asyncio.create_task(agent.start())
    yield
    # Cleanup
    agent._stop_event.set()
    await agent_task

app = FastAPI(title="UBP Bot Agent", lifespan=lifespan)
agent = BotAgent()

@app.get("/health/live")
async def liveness():
    return {"status": "running"}

@app.get("/health/ready")
async def readiness():
    if agent.connected:
        return {"status": "connected"}
    return Response(status_code=503, content="Connecting...")

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    # Run health server (which also starts bot loop via lifespan)
    uvicorn.run(app, host=settings.HTTP_HOST, port=settings.HTTP_PORT)
