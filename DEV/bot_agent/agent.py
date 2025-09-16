# filepath: bot_agent/agent.py
# project: Unified Bot Protocol (UBP)
# component: Bot Agent (Reference Implementation)
# license: Apache-2.0
# author: Michael Landbo (Founder & BDFL of UBP)
# description:
#   Reference Bot Agent for UBP. Implements:
#     - Secure Orchestrator WebSocket connection with handshake
#     - One-time token onboarding -> long-lived API key persistence
#     - Heartbeats, command handling, reconnection logic
#     - Structured logging with trace context
#     - Prometheus metrics + FastAPI health endpoints
#     - Capability advertisement and runtime metadata exchange
# version: 1.4.0
# last_edit: 2025-09-16
#
# CHANGELOG:
# - 1.4.0: Merge credential persistence (initial_token -> api_key) with full lifecycle:
#           websockets, heartbeat, metrics, structured logging, reconnection, health.
# - 1.3.0: Added exponential backoff for reconnection; improved error reporting.
# - 1.2.0: Added Prometheus metrics and FastAPI health/metrics endpoints.
# - 1.1.0: Added capabilities, metadata, and trace context to handshake & logs.
# - 1.0.0: Initial Agent with connect/handshake/heartbeat/command handling.

import asyncio
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set

import websockets
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, generate_latest
from starlette.responses import Response
from websockets.client import WebSocketClientProtocol

# =========================
# Configuration & Constants
# =========================

DEFAULT_HEARTBEAT_SEC = 30
DEFAULT_RECONNECT_BASE_DELAY_SEC = 2
DEFAULT_RECONNECT_MAX_DELAY_SEC = 30
DEFAULT_AGENT_VERSION = "1.4.0"

# Prometheus metrics
CONNECTED = Gauge('ubp_bot_agent_connected', 'Connection status to orchestrator (1=connected,0=disconnected)')
COMMANDS_RECEIVED = Counter('ubp_bot_agent_commands_total', 'Total commands received', ['command_name'])
COMMAND_DURATION = Gauge('ubp_bot_agent_command_duration_seconds', 'Time taken to execute last command (s)')
HANDSHAKE_FAILURES = Counter('ubp_bot_agent_handshake_failures_total', 'Handshake failures')
SENT_HEARTBEATS = Counter('ubp_bot_agent_heartbeats_total', 'Total heartbeats sent')
RECONNECT_ATTEMPTS = Counter('ubp_bot_agent_reconnect_attempts_total', 'Total reconnect attempts')

# =================
# Structured Logging
# =================

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": "ubp_bot_agent",
            "message": record.getMessage(),
        }
        # Enrich with custom attributes when available
        for attr in ("bot_id", "instance_id", "trace_id", "session_id"):
            value = getattr(record, attr, None)
            if value:
                payload[attr] = value
        return json.dumps(payload, ensure_ascii=False)

def _configure_logging() -> logging.LoggerAdapter:
    logger = logging.getLogger("ubp_bot_agent")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    if not logger.handlers:
        logger.addHandler(handler)
    # Default context; will be overridden per instance
    return logging.LoggerAdapter(logger, {"trace_id": "boot"})

base_log = _configure_logging()

# ===========
# Data Models
# ===========

@dataclass
class AgentConfig:
    bot_id: str
    orchestrator_url: str
    capabilities: Set[str]
    config_dir: Path
    initial_token: Optional[str] = None  # one-time token for first connection
    api_key_file_suffix: str = "_credentials.json"
    agent_version: str = DEFAULT_AGENT_VERSION

    @property
    def credentials_file(self) -> Path:
        return self.config_dir / f"{self.bot_id}{self.api_key_file_suffix}"


# ==========
# Bot Agent
# ==========

class BotAgent:
    """
    UBP Bot Agent reference implementation.

    Design Philosophy:
    - Interoperability: strictly uses UBP handshake fields and message shapes
    - Scalability: lightweight, async, decoupled metrics and health endpoints
    - Security: one-time token onboarding -> long-lived API key persisted locally
    - Observability: structured logging, metrics, health, trace context
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.bot_id = config.bot_id
        self.instance_id = f"{self.bot_id}-{str(uuid.uuid4())[:8]}"
        self.orchestrator_url = config.orchestrator_url
        self.capabilities = config.capabilities
        self.config_dir = config.config_dir

        # Credentials
        self.api_key: str = self._load_credentials()
        if not self.api_key and config.initial_token:
            # Use one-time token for first handshake
            self.api_key = ""  # explicit empty; initial token is sent separately
            self._initial_token = config.initial_token
        else:
            self._initial_token = None

        # Connection state
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.heartbeat_interval = DEFAULT_HEARTBEAT_SEC
        self.connected = False
        self.session_id: Optional[str] = None
        self._stop_event = asyncio.Event()

        # Logger with context
        self.log = logging.LoggerAdapter(
            logging.getLogger("ubp_bot_agent"),
            {
                "bot_id": self.bot_id,
                "instance_id": self.instance_id,
                "trace_id": "boot",
            },
        )

    # ---------------
    # Credential I/O
    # ---------------

    def _load_credentials(self) -> str:
        """Load long-lived API key from credential file, if present."""
        try:
            if self.config.credentials_file.exists():
                with open(self.config.credentials_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                    return payload.get("api_key", "")
        except Exception as e:
            self.log.warning(f"Failed to load credentials: {e}")
        return ""

    def _save_credentials(self, api_key: str) -> None:
        """Persist long-lived API key to credential file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config.credentials_file, "w", encoding="utf-8") as f:
                json.dump({"api_key": api_key}, f)
            self.log.info("API key persisted to credentials file")
        except Exception as e:
            self.log.error(f"Failed to save credentials: {e}")

    # -----------------------
    # Lifecycle & Connection
    # -----------------------

    async def run(self) -> None:
        """Run the agent until stop() is called."""
        await self.connect_loop()

    async def stop(self) -> None:
        """Signal the agent to stop and close the connection."""
        self._stop_event.set()
        try:
            if self.websocket:
                await self.websocket.close()
        except Exception:
            pass

    async def connect_loop(self) -> None:
        """Establish connection with exponential backoff on failures."""
        delay = DEFAULT_RECONNECT_BASE_DELAY_SEC
        while not self._stop_event.is_set():
            try:
                RECONNECT_ATTEMPTS.inc()
                self.log.info("Connecting to orchestrator...", extra={"trace_id": str(uuid.uuid4())})
                async with websockets.connect(self.orchestrator_url) as ws:
                    self.websocket = ws
                    await self._handle_connection()
                    # If connection returns normally, reset backoff
                    delay = DEFAULT_RECONNECT_BASE_DELAY_SEC
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Connection error: {e}")
                self.connected = False
                CONNECTED.set(0)
                await asyncio.sleep(delay)
                delay = min(DEFAULT_RECONNECT_MAX_DELAY_SEC, delay * 2)

    async def _handle_connection(self) -> None:
        """Handle handshake, heartbeats, and message loop."""
        try:
            await self._perform_handshake()
            self.connected = True
            CONNECTED.set(1)

            # Heartbeat task
            heartbeat_task = asyncio.create_task(self._send_heartbeats())

            # Message loop
            while not self._stop_event.is_set():
                raw = await self.websocket.recv()
                asyncio.create_task(self._handle_message(raw))
        except websockets.exceptions.ConnectionClosed as e:
            self.log.warning(f"Connection closed by orchestrator: {e}")
            self.connected = False
            CONNECTED.set(0)
        except Exception as e:
            self.log.error(f"Connection handler error: {e}")
            self.connected = False
            CONNECTED.set(0)

    # ----------
    # Handshake
    # ----------

    async def _perform_handshake(self) -> None:
        """
        Perform UBP handshake. If first-time onboarding, present initial_token.
        Otherwise, present long-lived api_key.
        """
        auth_block: Dict[str, str]
        if self.api_key:
            auth_block = {"api_key": self.api_key}
        elif self._initial_token:
            auth_block = {"initial_token": self._initial_token}
        else:
            HANDSHAKE_FAILURES.inc()
            raise RuntimeError("No credentials available (api_key or initial_token)")

        handshake_request = {
            "handshake": {
                "bot_id": self.bot_id,
                "instance_id": self.instance_id,
                "auth": auth_block,
                "capabilities": sorted(list(self.capabilities)),
                "metadata": {
                    "agent_version": self.config.agent_version,
                    "platform": "python",
                    "start_time": datetime.utcnow().isoformat() + "Z",
                },
            }
        }

        await self.websocket.send(json.dumps(handshake_request))
        raw = await self.websocket.recv()
        resp = json.loads(raw)

        # Expect schema: {"handshake_response": {...}}
        hresp = resp.get("handshake_response") or resp  # tolerate older shape
        status = hresp.get("status")
        if status != "SUCCESS":
            HANDSHAKE_FAILURES.inc()
            raise RuntimeError(f"Handshake failed: {hresp.get('error_message')}")

        # Extract session and heartbeat
        self.session_id = hresp.get("session_id")
        if self.session_id:
            # enrich logger default context
            self.log = logging.LoggerAdapter(
                logging.getLogger("ubp_bot_agent"),
                {
                    "bot_id": self.bot_id,
                    "instance_id": self.instance_id,
                    "trace_id": self.session_id,
                    "session_id": self.session_id,
                },
            )
        self.heartbeat_interval = int(hresp.get("heartbeat_interval_sec", DEFAULT_HEARTBEAT_SEC))

        # If server returned a new long-lived api_key during onboarding, persist it
        new_api_key = hresp.get("api_key")
        if new_api_key:
            self.api_key = new_api_key
            self._save_credentials(self.api_key)
            # Once persisted, initial token is no longer needed
            self._initial_token = None

        self.log.info("Handshake successful")

    # -----------
    # Heartbeats
    # -----------

    async def _send_heartbeats(self) -> None:
        """Periodically send heartbeats with lightweight metrics."""
        while self.connected and not self._stop_event.is_set():
            try:
                heartbeat = {
                    "heartbeat": {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "metrics": {
                            # TODO: integrate psutil for real CPU/Mem if allowed
                            "cpu_usage": "0.5",
                            "memory_usage": "100MB",
                        },
                    }
                }
                await self.websocket.send(json.dumps(heartbeat))
                SENT_HEARTBEATS.inc()
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Failed to send heartbeat: {e}")
                break

    # ---------------
    # Message Routing
    # ---------------

    async def _handle_message(self, message: str) -> None:
        """Route incoming messages from Orchestrator."""
        try:
            msg = json.loads(message)
        except json.JSONDecodeError:
            self.log.error("Received invalid JSON message")
            return

        # Allocate a per-message trace id if none on session
        trace_id = str(uuid.uuid4())
        try:
            # Proxy simple patterns:
            if "command_request" in msg:
                await self._handle_command(msg["command_request"], trace_id)
            elif "policy_update" in msg:
                await self._handle_policy_update(msg["policy_update"], trace_id)
            elif "control" in msg and msg["control"].get("type") == "disconnect":
                self.log.info("Received disconnect control signal", extra={"trace_id": trace_id})
                await self.stop()
            else:
                self.log.warning(f"Unknown message type: {list(msg.keys())}", extra={"trace_id": trace_id})
        except Exception as e:
            self.log.error(f"Error handling message: {e}", extra={"trace_id": trace_id})

    async def _handle_command(self, command: Dict, trace_id: str) -> None:
        """Execute a command and return result."""
        command_id = command.get("command_id") or str(uuid.uuid4())
        command_name = command.get("command_name", "unknown")

        self.log.info(f"Received command: {command_name}", extra={"trace_id": trace_id})
        COMMANDS_RECEIVED.labels(command_name=command_name).inc()

        start_time = datetime.utcnow()
        try:
            # TODO: Dispatch to actual skill/plugin logic by command_name
            await asyncio.sleep(1)  # simulate work

            response = {
                "command_response": {
                    "command_id": command_id,
                    "status": "SUCCESS",
                    "result": {
                        "message": f"Executed {command_name} successfully",
                    },
                }
            }
            await self.websocket.send(json.dumps(response))

            duration = (datetime.utcnow() - start_time).total_seconds()
            COMMAND_DURATION.set(duration)
            self.log.info(
                f"Command {command_name} completed",
                extra={"trace_id": trace_id, "duration": duration},
            )
        except Exception as e:
            self.log.error(f"Command {command_name} failed: {e}", extra={"trace_id": trace_id})
            error_response = {
                "command_response": {
                    "command_id": command_id,
                    "status": "EXECUTION_ERROR",
                    "error_details": str(e),
                }
            }
            try:
                await self.websocket.send(json.dumps(error_response))
            except Exception:
                pass

    async def _handle_policy_update(self, policy: Dict, trace_id: str) -> None:
        """React to policy updates (e.g., heartbeat interval, capability toggles)."""
        try:
            new_hb = policy.get("heartbeat_interval_sec")
            if isinstance(new_hb, int) and new_hb > 0:
                self.heartbeat_interval = new_hb
                self.log.info(
                    f"Updated heartbeat interval to {new_hb}s",
                    extra={"trace_id": trace_id},
                )
        except Exception as e:
            self.log.error(f"Policy update error: {e}", extra={"trace_id": trace_id})


# ===========================
# FastAPI Health & Metrics UI
# ===========================

app = FastAPI(title="UBP Bot Agent")

@app.get("/health/live")
async def health_live():
    # Liveness: process is running
    return {"status": "healthy"}

@app.get("/health/ready")
async def health_ready():
    # Readiness: option to check internal dependencies
    # TODO: verify essential config exists and DNS for orchestrator resolves
    return {"status": "ready"}

@app.get("/metrics")
async def metrics():
    data = generate_latest()
    return Response(content=data, media_type="text/plain; version=0.0.4")


# ===========
# Entrypoint
# ===========

def _env(var: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(var)
    return v if v is not None and v != "" else default

def build_agent_from_env() -> BotAgent:
    """
    Environment variable configuration for quick starts and containerization.

    UBP_BOT_ID                - required
    UBP_ORCH_URL             - required (e.g., ws://localhost:8765 or wss://host/agent)
    UBP_CAPABILITIES         - optional, comma-separated (e.g., task.execute,message.send)
    UBP_CONFIG_DIR           - optional, default ~/.ubp
    UBP_INITIAL_TOKEN        - optional, only needed for first-time onboarding
    UBP_AGENT_VERSION        - optional, override agent version string
    """
    bot_id = _env("UBP_BOT_ID")
    orch = _env("UBP_ORCH_URL")
    if not bot_id or not orch:
        raise RuntimeError("UBP_BOT_ID and UBP_ORCH_URL are required environment variables")

    caps = set()
    caps_raw = _env("UBP_CAPABILITIES", "")
    if caps_raw:
        caps = {c.strip() for c in caps_raw.split(",") if c.strip()}

    config_dir = Path(_env("UBP_CONFIG_DIR", str(Path.home() / ".ubp")))
    initial_token = _env("UBP_INITIAL_TOKEN")
    agent_version = _env("UBP_AGENT_VERSION", DEFAULT_AGENT_VERSION)

    cfg = AgentConfig(
        bot_id=bot_id,
        orchestrator_url=orch,
        capabilities=caps or {"task.execute", "message.send"},
        config_dir=config_dir,
        initial_token=initial_token,
        agent_version=agent_version,
    )
    return BotAgent(cfg)

def run_api_server():
    """Runs the FastAPI server (health + metrics)."""
    import uvicorn
    host = _env("UBP_HTTP_HOST", "0.0.0.0")
    port = int(_env("UBP_HTTP_PORT", "8001"))
    uvicorn.run(app, host=host, port=port, log_level="info")

async def _main_async():
    # Build agent from environment and run
    agent = build_agent_from_env()

    # Run health/metrics server in background
    loop = asyncio.get_event_loop()
    loop.create_task(asyncio.to_thread(run_api_server))

    # Run the agent main loop
    await agent.run()

def main():
    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()