"""
FilePath: "/DEV/orchestrator/orchestrator_server.py"
Project: Unified Bot Protocol (UBP)
Description: Main entry point. Binds API, C2, Security, and Routing logic together.
Author: "Michael Landbo"
Date created: "31/12/2025"
Version: "3.2.1"
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, List

# Adapter Imports
from adapters.base_adapter import AdapterStatus
from adapters.registry import AdapterRegistry, create_adapter

# FastAPI Imports
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# Integration Imports
from integrations.core.routing.message_router import MessageRouter
from integrations.core.routing.policy_engine import PolicyEngine

# Orchestrator Imports
from orchestrator.api import management_router, tasks_router
from orchestrator.c2.handler import SecureC2ConnectionHandler
from orchestrator.c2.secure_handler import SecureC2Handler
from orchestrator.database import Settings
from orchestrator.security.audit import AuditLogger
from orchestrator.storage import BotStorage
from orchestrator.tasks.manager import TaskManager

# Path Setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Imports
try:
    from orchestrator.settings import get_settings
except ImportError:
    from .settings import get_settings


# Configuration
settings = get_settings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("UBP.Orchestrator")

# Global Variables
active_registry = AdapterRegistry()

# Service Instances
bot_storage = BotStorage()
task_manager = TaskManager()
audit_logger = AuditLogger()


# Active Adapter Registry
class ActiveAdapterManager:
    """
    Initializes the Active Adapters Registry.

    self.active_adapters will contain adapter_name -> Adapter instance mappings.
    """

    def __init__(self):
        self.active_adapters = {}

    async def initialize_adapters(self, adapter_names: List[str]):
        for name in adapter_names:
            try:
                logger.info("Initializing adapter: %s", name)
                adapter = create_adapter(name)
                if not hasattr(adapter, "adapter_id") or not adapter.adapter_id:
                    adapter.adapter_id = name
                adapter.status = AdapterStatus.CONNECTED
                self.active_adapters[name] = adapter
                logger.info("✔ Adapter %s active", name)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("✘ Failed to start adapter %s: %s", name, e)

    def get_healthy_adapters(self, platform_name: str) -> List[Any]:
        found = []
        for name, adapter in self.active_adapters.items():
            if name == platform_name or getattr(adapter, "platform_name", "") == platform_name:
                if getattr(adapter, "status", None) == AdapterStatus.CONNECTED:
                    found.append(adapter)
        return found

    def get(self, adapter_id: str) -> Any:
        return self.active_adapters.get(adapter_id)

    def all(self) -> List[Any]:
        return list(self.active_adapters.values())


# Initialize Services
init_db = Settings().DATABASE_URL

policy_engine = PolicyEngine(policies={"allow_platforms": ["discord", "telegram", "slack", "console", "email"], "max_content_length": 10000})

adapter_manager = ActiveAdapterManager()

message_router = MessageRouter(adapter_registry=adapter_manager, policy_engine=policy_engine, config={"load_balancer": {"strategy": "round_robin"}})

c2_handler = SecureC2Handler(message_router=MessageRouter, task_manager=TaskManager)
onboarding_handler = SecureC2ConnectionHandler()


# App Lifecycle
@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Starting %s in %s mode...", settings.APP_NAME, settings.UBP_ENV)
    await init_db()
    logger.info("Database initialized.")

    enabled_adapters = ["console"]
    await adapter_manager.initialize_adapters(enabled_adapters)

    # Type ignore added: String 'round_robin' is valid at runtime even if Pylance wants Enum
    message_router.add_route(route_id="default_chat", platforms=["console"], conditions={}, priority=1, strategy="round_robin")  # type: ignore

    yield

    logger.info("Shutting down Orchestrator...")
    await message_router.shutdown()


app = FastAPI(title=settings.APP_NAME, version="3.2.1", description="Unified Bot Protocol - Orchestrator Server", lifespan=lifespan)

app.include_router(management_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"system": settings.APP_NAME, "status": "running", "active_adapters": len(adapter_manager.active_adapters), "docs": "/docs"}


@app.get("/health/live")
async def health_check():
    return {"status": "healthy"}


@app.websocket("/ws/onboarding")
async def onboarding_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Pylance fix: Explicit check on client object
    client = websocket.client
    client_ip = client.host if client else "unknown"

    try:
        data = await websocket.receive_json()
        bot_id = data.get("bot_id")
        response = await onboarding_handler.handle_handshake(data, client_ip, bot_id)
        await websocket.send_json(response)
        await websocket.close(code=1000)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Onboarding error: %s", e)
        try:
            await websocket.close(code=1011)
        except Exception:  # pylint: disable=broad-except
            pass


@app.websocket("/ws/c2")
async def c2_endpoint(websocket: WebSocket):
    await websocket.accept()
    client = websocket.client
    client_ip = client.host if client else "unknown"
    await c2_handler.handle_connection(websocket, client_ip)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("orchestrator.orchestrator_server:app", host=settings.HOST, port=settings.PORT, reload=settings.UBP_ENV == "development")
