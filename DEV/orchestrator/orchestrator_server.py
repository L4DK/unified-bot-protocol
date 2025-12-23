# FilePath: "/DEV/orchestrator/orchestrator_server.py"
# Projekt: Unified Bot Protocol (UBP)
# Beskrivelse: Main entry point. Binder API, C2, Security og Tasks sammen i én applikation.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.3.0.0" (Modular Architecture)

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# Import Settings
try:
    from .settings import get_settings
except ImportError:
    from settings import get_settings

# Import API Routers
from api import tasks_router, management_router

# Import C2 Handlers
from c2.secure_handler import SecureC2Handler
from c2.handler import SecureC2ConnectionHandler

# Import Security
from security import AuditLogger

# ==========================================
# Configuration & Setup
# ==========================================
settings = get_settings()

# Setup Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("UBP.Orchestrator")

# Initialize Services
c2_handler = SecureC2Handler()
onboarding_handler = SecureC2ConnectionHandler()
audit_logger = AuditLogger()

# ==========================================
# App Lifecycle
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.APP_NAME} in {settings.UBP_ENV} mode...")

    # Her kunne vi initialisere DB connections eller Redis pools

    yield

    # Shutdown
    logger.info("Shutting down Orchestrator...")
    # Cleanup tasks...

app = FastAPI(
    title=settings.APP_NAME,
    version="3.0.0",
    description="Unified Bot Protocol - Orchestrator Server",
    lifespan=lifespan
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
    return {
        "system": settings.APP_NAME,
        "status": "running",
        "docs": "/docs"
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
        bot_id = data.get('bot_id')

        # Kør onboarding logik
        response = await onboarding_handler.handle_handshake(data, client_ip, bot_id)

        # Send svar (indeholder ny API key hvis success)
        await websocket.send_json(response)

        # Luk forbindelsen (Bot skal reconnecte på /ws/c2 med den nye nøgle)
        await websocket.close(code=1000)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Onboarding error: {e}")
        try:
            await websocket.close(code=1011)
        except:
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
        reload=(settings.UBP_ENV == "development")
    )
