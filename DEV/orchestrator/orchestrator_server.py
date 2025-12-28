"""
FilePath: "/DEV/orchestrator/orchestrator_server.py"
Project: Unified Bot Protocol (UBP)
Description: Main entry point. Binds API, C2, Security, and Routing logic together.
Author: "Michael Landbo"
Date created: "21/12/2025"
Date Modified: "27/12/2025"
Version: "v.3.1.2" (Pylint compliant)
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# --- PATH SETUP ---
# Vi tilføjer stier før imports, så Python kan finde modulerne.
# pylint: disable=wrong-import-position
sys.path.append(os.path.dirname(os.path.abspath(__file__)))  # /orchestrator
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # /DEV

# Import Settings
try:
    from .settings import get_settings
except ImportError:
    from settings import get_settings

# Import API Routers
from adapters.base_adapter import AdapterStatus
from adapters.registry import create_adapter
from api import management_router, tasks_router
from c2.handler import SecureC2ConnectionHandler

# Import C2 Handlers
from c2.secure_handler import SecureC2Handler

# Import Routing Components
from integrations.core.routing.message_router import MessageRouter
from integrations.core.routing.policy_engine import PolicyEngine

# Import Security & Core
from security import AuditLogger
from tasks.manager import TaskManager

# ==========================================
# Configuration & Setup
# ==========================================
settings = get_settings()

# Setup Structured Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("UBP.Orchestrator")


# ==========================================
# Active Adapter Registry (Runtime)
# ==========================================
class ActiveAdapterManager:
    """
    Wraps the static metadata registry to hold actual instantiated adapter objects.
    This satisfies MessageRouter's need for 'get_healthy_adapters'.
    """

    def __init__(self):
        self.active_adapters = {}  # id -> adapter_instance

    async def initialize_adapters(self, adapter_names: List[str]):
        """Factory loop to create enabled adapters"""
        for name in adapter_names:
            try:
                logger.info("Initializing adapter: %s", name)
                adapter = create_adapter(name)
                # Ensure we set a unique ID if not present
                if not hasattr(adapter, "adapter_id") or not adapter.adapter_id:
                    adapter.adapter_id = name

                # Mock status to CONNECTED for now so Router sees them as healthy
                adapter.status = AdapterStatus.CONNECTED

                self.active_adapters[name] = adapter
                logger.info("✔ Adapter %s active", name)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("✘ Failed to start adapter %s: %s", name, e)

    def get_healthy_adapters(self, platform_name: str) -> List[Any]:
        """Returns list of active adapter instances for a platform"""
        found = []
        for name, adapter in self.active_adapters.items():
            # Check if name matches or if the adapter's internal platform_name matches
            if (
                name == platform_name
                or getattr(adapter, "platform_name", "") == platform_name
            ):
                if getattr(adapter, "status", None) == AdapterStatus.CONNECTED:
                    found.append(adapter)
        return found

    def get(self, adapter_id: str) -> Any:
        """Get a specific adapter instance by ID."""
        return self.active_adapters.get(adapter_id)

    def all(self) -> List[Any]:
        """Get all active adapters."""
        return list(self.active_adapters.values())

    def list_by_platform(self, platform: str) -> List[Any]:
        """List active adapters for a specific platform."""
        return self.get_healthy_adapters(platform)


# Initialize Core Services
audit_logger = AuditLogger()
task_manager = TaskManager()

# Define policies (Example)
policy_engine = PolicyEngine(
    policies={
        "allow_platforms": ["discord", "telegram", "slack", "console", "email"],
        "max_content_length": 10000,
    }
)

adapter_manager = ActiveAdapterManager()

# Initialize Message Router with our Active Manager
message_router = MessageRouter(
    adapter_registry=adapter_manager,
    policy_engine=policy_engine,
    config={"load_balancer": {"strategy": "round_robin"}},
)

# Initialize C2 Handlers with dependencies
# NOTE: We inject message_router and task_manager here!
c2_handler = SecureC2Handler(message_router=message_router, task_manager=task_manager)
onboarding_handler = SecureC2ConnectionHandler()


# ==========================================
# App Lifecycle
# ==========================================
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Lifecycle manager for the FastAPI application.
    Handles startup (Adapter initialization) and shutdown (Cleanup).
    """
    # Startup
    logger.info("Starting %s in %s mode...", settings.APP_NAME, settings.UBP_ENV)

    # 1. Initialize Adapters
    # You can customize this list based on your .env or desired configuration.
    enabled_adapters = ["console", "discord", "telegram"]
    await adapter_manager.initialize_adapters(enabled_adapters)

    # 2. Configure Default Routes
    # Route for standard chat
    message_router.add_route(
        route_id="default_chat",
        platforms=["console"],  # Default to console for testing
        conditions={},
        priority=1,
        strategy="round_robin",
    )

    # Route for high priority alerts
    message_router.add_route(
        route_id="alerts",
        platforms=["discord"],
        conditions={"priority": 5},  # High priority
        priority=10,
    )

    yield

    # Shutdown
    logger.info("Shutting down Orchestrator...")
    await message_router.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    version="3.1.2",
    description="Unified Bot Protocol - Orchestrator Server",
    lifespan=lifespan,
)

# ==========================================
# Include API Routers
# ==========================================
# Management API (Bot Registration, Admin)
app.include_router(management_router, prefix="/api/v1")

# Async Tasks API (Long-running operations)
app.include_router(tasks_router, prefix="/api/v1")


# ==========================================
# Root & Health Endpoints
# ==========================================
@app.get("/")
async def root():
    """Root endpoint providing system status."""
    return {
        "system": settings.APP_NAME,
        "status": "running",
        "active_adapters": len(adapter_manager.active_adapters),
        "docs": "/docs",
    }


@app.get("/health/live")
async def health_check():
    """Liveness probe for Kubernetes/Docker."""
    return {"status": "healthy"}


# ==========================================
# WebSocket: Onboarding Channel
# ==========================================
@app.websocket("/ws/onboarding")
async def onboarding_endpoint(websocket: WebSocket):
    """
    Dedikeret kanal til nye bots.
    Håndterer: Handshake, OTT (One-Time-Token) validering, Udstedelse af API Key.
    """
    await websocket.accept()
    client_ip = websocket.client.host if websocket.client else "unknown"

    try:
        # Modtag handshake payload
        data = await websocket.receive_json()
        bot_id = data.get("bot_id")

        # Kør onboarding logik
        response = await onboarding_handler.handle_handshake(data, client_ip, bot_id)

        # Send svar (indeholder ny API key hvis success)
        await websocket.send_json(response)

        # Luk forbindelsen (Bot skal reconnecte på /ws/c2 med den nye nøgle)
        await websocket.close(code=1000)

    except WebSocketDisconnect:
        pass
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Onboarding error: %s", e)
        try:
            await websocket.close(code=1011)
        except Exception:  # pylint: disable=broad-except
            pass


# ==========================================
# WebSocket: Secure Command & Control (C2)
# ==========================================
@app.websocket("/ws/c2")
async def c2_endpoint(websocket: WebSocket):
    """
    Primær C2 kanal for driftsklare bots.
    Håndterer: Krypteret kommunikation, Heartbeats, Kommandoer.
    """
    # Vi accepterer forbindelsen her for at kunne læse headers og handshake i handleren
    await websocket.accept()
    client_ip = websocket.client.host if websocket.client else "unknown"

    # Deleger al logik til SecureC2Handler
    await c2_handler.handle_connection(websocket, client_ip)


# ==========================================
# Main Entry Point
# ==========================================
if __name__ == "__main__":
    import uvicorn

    # Kør med: uvicorn orchestrator_server:app --host 0.0.0.0 --port 8000 --reload
    uvicorn.run(
        "orchestrator_server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.UBP_ENV == "development"),
    )

    # Run health server (which also starts bot loop via lifespan)
    uvicorn.run(app, host=settings.HTTP_HOST, port=settings.HTTP_PORT)
