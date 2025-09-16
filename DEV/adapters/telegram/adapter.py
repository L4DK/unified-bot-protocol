# adapters/telegram/adapter.py
from typing import Dict, Optional, Any
import asyncio
import json
import logging
import aiohttp
from fastapi import FastAPI, Request
from pydantic import BaseModel
import websockets

class TelegramConfig(BaseModel):
    """Telegram bot configuration"""
    bot_token: str
    webhook_url: str
    orchestrator_url: str
    bot_id: str = "telegram-adapter"
    api_base_url: str = "https://api.telegram.org/bot"

class TelegramAdapter:
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.logger = logging.getLogger("telegram_adapter")
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.api_session: Optional[aiohttp.ClientSession] = None

        # Create FastAPI app
        self.app = FastAPI(title="Telegram UBP Adapter")
        self.setup_routes()

    def setup_routes(self):
        """Setup FastAPI routes"""
        @self.app.post("/webhook/telegram")
        async def telegram_webhook(request: Request):
            data = await request.json()
            await self._handle_telegram_update(data)
            return {"status": "ok"}

        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy"}

    async def start(self):
        """Start the adapter"""
        # Initialize HTTP session
        self.api_session = aiohttp.ClientSession()

        # Setup Telegram webhook
        await self._setup_webhook()

        # Connect to Orchestrator
        await self._connect_to_orchestrator()

        # Start message processing loop
        asyncio.create_task(self._process_messages())

    async def stop(self):
        """Stop the adapter"""
        if self.websocket:
            await self.websocket.close()
        if self.api_session:
            await self.api_session.close()

    async def _setup_webhook(self):
        """Setup Telegram webhook"""
        url = f"{self.config.api_base_url}{self.config.bot_token}/setWebhook"
        async with self.api_session.post(url, json={
            "url": self.config.webhook_url
        }) as response:
            if response.status != 200:
                raise Exception("Failed to setup Telegram webhook")

    async def _connect_to_orchestrator(self):
        """Connect to UBP Orchestrator"""
        try:
            self.websocket = await websockets.connect(self.config.orchestrator_url)

            # Perform handshake
            handshake = {
                "bot_id": self.config.bot_id,
                "capabilities": [
                    "telegram.message.send",
                    "telegram.message.edit",
                    "telegram.message.delete"
                ],
                "adapter_type": "telegram",
                "metadata": {
                    "version": "1.0.0",
                    "platform": "telegram"
                }
            }

            await self.websocket.send(json.dumps(handshake))
            response = await self.websocket.recv()

            if json.loads(response)["status"] != "SUCCESS":
                raise Exception("Handshake failed")

            self.logger.info("Connected to Orchestrator")

        except Exception as e:
            self.logger.error(f"Failed to connect to Orchestrator: {str(e)}")
            raise

    async def _process_messages(self):
        """Process messages from Orchestrator"""
        while True:
            try:
                if not self.websocket:
                    await self._connect_to_orchestrator()
                    continue

                message = await self.websocket.recv()
                command = json.loads(message)

                if "command_request" in command:
                    await self._handle_command(command["command_request"])

            except websockets.ConnectionClosed:
                self.logger.warning("Connection to Orchestrator closed")
                await asyncio.sleep(5)
            except Exception as e:
                self.logger.error(f"Error processing message: {str(e)}")
                await asyncio.sleep(1)

    async def _handle_telegram_update(self, update: Dict[str, Any]):
        """Handle incoming Telegram update"""
        try:
            # Convert Telegram update to UBP event
            event = self._convert_to_ubp_event(update)

            # Send event to Orchestrator
            if self.websocket and event:
                await self.websocket.send(json.dumps({
                    "event": event
                }))

        except Exception as e:
            self.logger.error(f"Error handling Telegram update: {str(e)}")

    async def _handle_command(self, command: Dict[str, Any]):
        """Handle incoming UBP command"""
        try:
            command_name = command["command_name"]
            params = command["parameters"]

            if command_name == "telegram.message.send":
                response = await self._send_telegram_message(params)
            elif command_name == "telegram.message.edit":
                response = await self._edit_telegram_message(params)
            elif command_name == "telegram.message.delete":
                response = await self._delete_telegram_message(params)
            else:
                raise ValueError(f"Unknown command: {command_name}")

            # Send command response
            await self.websocket.send(json.dumps({
                "command_response": {
                    "command_id": command["command_id"],
                    "status": "SUCCESS",
                    "result": response
                }
            }))

        except Exception as e:
            # Send error response
            await self.websocket.send(json.dumps({
                "command_response": {
                    "command_id": command["command_id"],
                    "status": "ERROR",
                    "error_details": str(e)
                }
            }))

    def _convert_to_ubp_event(self, update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert Telegram update to UBP event"""
        if "message" in update:
            message = update["message"]
            return {
                "event_type": "telegram.message.received",
                "platform": "telegram",
                "timestamp": message.get("date"),
                "data": {
                    "chat_id": message["chat"]["id"],
                    "message_id": message["message_id"],
                    "from_user": {
                        "id": message["from"]["id"],
                        "username": message["from"].get("username"),
                        "first_name": message["from"].get("first_name")
                    },
                    "text": message.get("text", ""),
                    "raw_update": update
                }
            }
        return None

    async def _send_telegram_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send message via Telegram API"""
        url = f"{self.config.api_base_url}{self.config.bot_token}/sendMessage"
        async with self.api_session.post(url, json={
            "chat_id": params["chat_id"],
            "text": params["text"],
            "parse_mode": params.get("parse_mode", "HTML")
        }) as response:
            if response.status != 200:
                raise Exception("Failed to send Telegram message")
            return await response.json()

    async def _edit_telegram_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Edit message via Telegram API"""
        url = f"{self.config.api_base_url}{self.config.bot_token}/editMessageText"
        async with self.api_session.post(url, json={
            "chat_id": params["chat_id"],
            "message_id": params["message_id"],
            "text": params["text"],
            "parse_mode": params.get("parse_mode", "HTML")
        }) as response:
            if response.status != 200:
                raise Exception("Failed to edit Telegram message")
            return await response.json()

    async def _delete_telegram_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Delete message via Telegram API"""
        url = f"{self.config.api_base_url}{self.config.bot_token}/deleteMessage"
        async with self.api_session.post(url, json={
            "chat_id": params["chat_id"],
            "message_id": params["message_id"]
        }) as response:
            if response.status != 200:
                raise Exception("Failed to delete Telegram message")
            return await response.json()

# Example usage
if __name__ == "__main__":
    import uvicorn

    config = TelegramConfig(
        bot_token="your_bot_token",
        webhook_url="https://your-domain.com/webhook/telegram",
        orchestrator_url="ws://localhost:8765"
    )

    adapter = TelegramAdapter(config)

    # Start adapter
    asyncio.get_event_loop().run_until_complete(adapter.start())

    # Run FastAPI server
    uvicorn.run(adapter.app, host="0.0.0.0", port=8080)