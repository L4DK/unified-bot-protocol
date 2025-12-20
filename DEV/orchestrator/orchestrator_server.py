# FilePath: "/DEV/orchestrator/orchestrator_server.py"
# Project: Unified Bot Protocol (UBP)
# Description: Main entry point for the Orchestrator. Handles both HTTP REST API and WebSocket C2 connections.
# Author: "Michael Landbo"
# Date created: "20/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.2.0.0" (Refactored architecture)

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Set, Optional, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Import settings (remember to create settings.py first as shown in Step 2)
# If running this without settings.py, you can uncomment the import and hardcode values temporarily.
try:
    from .settings import get_settings
except ImportError:
    # Fallback if the file is run directly without module context
    from settings import get_settings

# ==========================================
# Logging Setup
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("UBP.Orchestrator")

# ==========================================
# Models
# ==========================================
class BotInstance:
    """Representation of a connected Bot in memory."""
    def __init__(self, bot_id: str, instance_id: str, websocket: WebSocket, capabilities: Set[str]):
        self.bot_id = bot_id
        self.instance_id = instance_id
        self.websocket = websocket
        self.capabilities = capabilities
        self.last_heartbeat = datetime.utcnow()
        self.session_id = str(uuid.uuid4())
        self.connected_at = datetime.utcnow()

class CommandRequest(BaseModel):
    """Model for sending commands via HTTP API."""
    bot_id: str
    command_name: str
    arguments: Dict[str, Any]
    timeout_sec: int = 30

# ==========================================
# Connection Manager
# ==========================================
class Orchestrator:
    """Core logic for handling bot connections and routing."""
    
    def __init__(self):
        # In the future: Replace Dict with Redis for distributed systems
        self.connected_bots: Dict[str, BotInstance] = {}
        self.settings = get_settings()

    async def connect(self, websocket: WebSocket, bot_instance: BotInstance):
        """Registers a new bot connection."""
        await websocket.accept()
        self.connected_bots[bot_instance.instance_id] = bot_instance
        logger.info(f"Bot connected: {bot_instance.bot_id} (Instance: {bot_instance.instance_id})")

    def disconnect(self, instance_id: str):
        """Removes a bot connection."""
        if instance_id in self.connected_bots:
            bot = self.connected_bots[instance_id]
            logger.info(f"Bot disconnected: {bot.bot_id} (Instance: {instance_id})")
            del self.connected_bots[instance_id]

    async def broadcast(self, message: str):
        """Sends a message to all bots (mostly for debug/admin)."""
        for bot in self.connected_bots.values():
            await bot.websocket.send_text(message)

    async def dispatch_command(self, bot_id: str, command_data: CommandRequest) -> Dict[str, Any]:
        """Routes a command to a specific bot instance."""
        target_bot = self._find_bot(bot_id, command_data.command_name)
        
        if not target_bot:
            logger.warning(f"No suitable bot found for ID: {bot_id} with capability: {command_data.command_name}")
            raise HTTPException(status_code=404, detail="Bot not found or missing capability")

        command_id = str(uuid.uuid4())
        payload = {
            'command_request': {
                'command_id': command_id,
                'command_name': command_data.command_name,
                'arguments': command_data.arguments,
                'timeout_sec': command_data.timeout_sec
            }
        }

        try:
            logger.info(f"Dispatching command {command_id} to {target_bot.instance_id}")
            await target_bot.websocket.send_json(payload)
            return {"status": "dispatched", "command_id": command_id, "target_instance": target_bot.instance_id}
        except Exception as e:
            logger.error(f"Failed to send command to bot: {e}")
            raise HTTPException(status_code=500, detail="Failed to communicate with bot")

    def _find_bot(self, bot_id: str, capability: str) -> Optional[BotInstance]:
        """Finds a suitable bot instance based on ID and capabilities."""
        # Simple routing logic - can be extended to Round-Robin if there are multiple instances of the same bot
        for bot in self.connected_bots.values():
            if bot.bot_id == bot_id and capability in bot.capabilities:
                return bot
        return None

    def validate_auth(self, token: str) -> bool:
        """Simple token validation. Should be extended to Database/JWT check."""
        # Uses settings from env vars instead of hardcoded values
        return token == self.settings.UBP_API_KEY

# Instantiate manager globally (Singleton pattern for in-memory state)
orchestrator = Orchestrator()

# ==========================================
# FastAPI App Lifecycle
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("UBP Orchestrator starting up...")
    yield
    # Shutdown logic
    logger.info("UBP Orchestrator shutting down...")
    # Here we could gracefully close all websocket connections

app = FastAPI(
    title="UBP Orchestrator",
    version="2.0.0",
    description="Unified Bot Protocol Command & Control Server",
    lifespan=lifespan
)

# ==========================================
# HTTP Endpoints (Management API)
# ==========================================

@app.get("/health/live")
async def health_check():
    """Liveness probe for Kubernetes/Docker."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": app.version
    }

@app.get("/metrics")
async def get_metrics():
    """System metrics."""
    return {
        "connected_bots_count": len(orchestrator.connected_bots),
        "bots": [
            {
                "bot_id": b.bot_id, 
                "instance_id": b.instance_id, 
                "connected_at": b.connected_at,
                "capabilities": list(b.capabilities)
            } 
            for b in orchestrator.connected_bots.values()
        ]
    }

@app.post("/api/v1/command/dispatch")
async def dispatch_command_endpoint(request: CommandRequest):
    """REST endpoint for sending commands to bots."""
    return await orchestrator.dispatch_command(request.bot_id, request)

# ==========================================
# WebSocket Endpoint (C2 Channel)
# ==========================================

@app.websocket("/ws/c2")
async def websocket_endpoint(websocket: WebSocket):
    """
    Primary WebSocket handler for Bot Agents.
    Flow: Connect -> Handshake -> Main Loop
    """
    # 1. Wait for connection but do not accept before handshake (or accept and wait for handshake message)
    # In FastAPI, we typically accept first to be able to communicate
    await websocket.accept()
    
    bot_instance: Optional[BotInstance] = None
    
    try:
        # 2. Handshake Phase
        # We expect the first message to be a JSON handshake
        data = await websocket.receive_json()
        
        # Simple validation
        if 'handshake' not in data:
            await websocket.close(code=1008, reason="Invalid Protocol: Missing handshake")
            return

        handshake = data['handshake']
        auth_token = handshake.get('auth', {}).get('api_key')

        if not orchestrator.validate_auth(auth_token):
            logger.warning(f"Auth failed for bot: {handshake.get('bot_id')}")
            await websocket.close(code=1008, reason="Authentication failed")
            return

        # 3. Register Bot
        bot_instance = BotInstance(
            bot_id=handshake['bot_id'],
            instance_id=handshake['instance_id'],
            websocket=websocket,
            capabilities=set(handshake.get('capabilities', []))
        )
        
        # Store in the manager (note: we called accept() earlier, so we just add to the dict here)
        orchestrator.connected_bots[bot_instance.instance_id] = bot_instance
        logger.info(f"Handshake successful for {bot_instance.bot_id}")

        # Send success response
        await websocket.send_json({
            'handshake_response': {
                'status': 'SUCCESS',
                'heartbeat_interval_sec': 30,
                'session_id': bot_instance.session_id
            }
        })

        # 4. Main Loop
        while True:
            # Wait for messages from the Bot Agent
            message = await websocket.receive_json()
            
            # Update heartbeat
            bot_instance.last_heartbeat = datetime.utcnow()
            
            if 'heartbeat' in message:
                logger.debug(f"Heartbeat: {bot_instance.instance_id}")
                # Optional: Reply with pong if the protocol requires it
                
            elif 'command_response' in message:
                logger.info(f"Response from {bot_instance.instance_id}: {message['command_response']}")
                # Here we can implement logic to forward the response back to a waiting HTTP request (via async events/Redis)

            elif 'event' in message:
                logger.info(f"Event from {bot_instance.instance_id}: {message['event']}")

    except WebSocketDisconnect:
        if bot_instance:
            orchestrator.disconnect(bot_instance.instance_id)
    except json.JSONDecodeError:
        logger.error("Invalid JSON received")
        await websocket.close(code=1003)
    except Exception as e:
        logger.error(f"Unexpected error in WS handler: {e}")
        if bot_instance:
             orchestrator.disconnect(bot_instance.instance_id)
        try:
            await websocket.close(code=1011)
        except:
            pass

# Main entry point for debugging
if __name__ == "__main__":
    import uvicorn
    # Runs the server directly. In production use: uvicorn orchestrator_server:app --host 0.0.0.0 --port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
