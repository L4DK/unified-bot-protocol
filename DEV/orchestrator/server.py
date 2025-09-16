# orchestrator/server.py

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Set

import websockets
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from websockets.server import WebSocketServerProtocol

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format=json.dumps({
        'timestamp': '%(asctime)s',
        'level': '%(levelname)s',
        'service': 'orchestrator',
        'message': '%(message)s',
        'trace_id': '%(trace_id)s'
    })
)

class BotInstance:
    def __init__(self, bot_id: str, instance_id: str, websocket: WebSocketServerProtocol, capabilities: Set[str]):
        self.bot_id = bot_id
        self.instance_id = instance_id
        self.websocket = websocket
        self.capabilities = capabilities
        self.last_heartbeat = datetime.utcnow()
        self.session_id = str(uuid.uuid4())

class Orchestrator:
    def __init__(self):
        self.connected_bots: Dict[str, BotInstance] = {}
        self.api_keys = {"test-key": "test-bot"}  # Simple in-memory auth store

    async def handle_connection(self, websocket: WebSocketServerProtocol):
        trace_id = str(uuid.uuid4())
        log = logging.LoggerAdapter(logging.getLogger(), {'trace_id': trace_id})

        try:
            # Handle handshake
            handshake = await self.receive_handshake(websocket)
            bot_instance = await self.process_handshake(websocket, handshake, trace_id)
            log.info(f"Bot {bot_instance.bot_id} ({bot_instance.instance_id}) connected")

            # Main message loop
            while True:
                message = await websocket.recv()
                await self.handle_message(bot_instance, message, trace_id)

        except websockets.exceptions.ConnectionClosed:
            if bot_instance:
                del self.connected_bots[bot_instance.instance_id]
                log.info(f"Bot {bot_instance.bot_id} ({bot_instance.instance_id}) disconnected")
        except Exception as e:
            log.error(f"Error handling connection: {str(e)}")
            await websocket.close(1011, "Internal server error")

    async def receive_handshake(self, websocket: WebSocketServerProtocol) -> dict:
        try:
            message = await websocket.recv()
            return json.loads(message)
        except json.JSONDecodeError:
            await websocket.close(1007, "Invalid handshake format")
            raise

    async def process_handshake(self, websocket: WebSocketServerProtocol, handshake: dict, trace_id: str) -> BotInstance:
        log = logging.LoggerAdapter(logging.getLogger(), {'trace_id': trace_id})

        # Validate auth token
        auth_token = handshake.get('auth_token')
        if auth_token not in self.api_keys:
            log.warning("Authentication failed")
            await websocket.close(1008, "Authentication failed")
            raise ValueError("Invalid auth token")

        # Create bot instance
        bot_instance = BotInstance(
            bot_id=handshake['bot_id'],
            instance_id=handshake['instance_id'],
            websocket=websocket,
            capabilities=set(handshake.get('capabilities', []))
        )

        # Store instance
        self.connected_bots[bot_instance.instance_id] = bot_instance

        # Send handshake response
        response = {
            'status': 'SUCCESS',
            'heartbeat_interval_sec': 30,
            'session_id': bot_instance.session_id
        }
        await websocket.send(json.dumps(response))

        return bot_instance

    async def handle_message(self, bot: BotInstance, message: str, trace_id: str):
        log = logging.LoggerAdapter(logging.getLogger(), {'trace_id': trace_id})

        try:
            msg = json.loads(message)
            if 'heartbeat' in msg:
                bot.last_heartbeat = datetime.utcnow()
                log.debug(f"Heartbeat received from {bot.instance_id}")
            elif 'command_response' in msg:
                log.info(f"Command response received from {bot.instance_id}: {msg['command_response']}")
            elif 'event' in msg:
                log.info(f"Event received from {bot.instance_id}: {msg['event']}")
        except json.JSONDecodeError:
            log.error(f"Invalid message format from {bot.instance_id}")

    async def dispatch_command(self, bot_id: str, command: dict) -> None:
        """Dispatches a command to a specific bot instance"""
        trace_id = str(uuid.uuid4())
        log = logging.LoggerAdapter(logging.getLogger(), {'trace_id': trace_id})

        # Find a suitable bot instance
        target_bot = None
        for bot in self.connected_bots.values():
            if bot.bot_id == bot_id and command['command_name'] in bot.capabilities:
                target_bot = bot
                break

        if not target_bot:
            log.error(f"No suitable bot found for command {command['command_name']}")
            raise ValueError("No suitable bot found")

        command_msg = {
            'command_request': {
                'command_id': str(uuid.uuid4()),
                'command_name': command['command_name'],
                'arguments': command['arguments'],
                'timeout_sec': command.get('timeout_sec', 30)
            }
        }

        try:
            await target_bot.websocket.send(json.dumps(command_msg))
            log.info(f"Command {command['command_name']} dispatched to {target_bot.instance_id}")
        except Exception as e:
            log.error(f"Failed to dispatch command: {str(e)}")
            raise

# FastAPI application
app = FastAPI(title="UBP Orchestrator")
orchestrator = Orchestrator()

@app.get("/health/live")
async def health_live():
    return {"status": "healthy"}

@app.get("/metrics")
async def metrics():
    return {
        "connected_bots": len(orchestrator.connected_bots),
        "uptime_seconds": 0  # TODO: Implement actual uptime tracking
    }

# WebSocket handler
async def websocket_handler(websocket: WebSocketServerProtocol, path: str):
    await orchestrator.handle_connection(websocket)

# Main entry point
if __name__ == "__main__":
    import uvicorn

    # Start WebSocket server
    ws_server = websockets.serve(websocket_handler, "localhost", 8765)

    # Run both servers
    asyncio.get_event_loop().run_until_complete(ws_server)
    uvicorn.run(app, host="localhost", port=8000)