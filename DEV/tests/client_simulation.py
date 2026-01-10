"""
FilePath: "/DEV/tests/client_simulation.py"
Description: Simulates a Bot Agent connecting to UBP Orchestrator.
    1. Performs Onboarding (gets API Key).
    2. Connects to C2 (gets Session Token).
    3. Sends a test message.

Usage: Run manually to test the full flow: `python tests/client_simulation.py`

Author: "Michael Landbo"
Date created: "31/12/2025"
Last modified: "31/12/2025"
Version: "1.0.0"
"""

# Internal imports
import asyncio  # Async IO library used for websockets
import json  # JSON handling
import logging  # Logging for debugging

# Websocket imports
import websockets

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - SIMULATION - %(levelname)s - %(message)s"
)
logger = logging.getLogger("BotClient")

SERVER_URL = "ws://localhost:8000"
BOT_ID = "test_bot_001"


# Simulate a Bot Agent
async def run_bot():
    """
    Simulates a Bot Agent connecting to UBP Orchestrator.
    1. Performs Onboarding (gets API Key).
    2. Connects to C2 (gets Session Token).
    3. Sends a test message.
    """
    logger.info("--- STARTING BOT SIMULATION: %s ---", BOT_ID)

    # ==========================================
    # PHASE 1: ONBOARDING
    # ==========================================
    api_key = None
    logger.info("1. Connecting to Onboarding Channel...")

    try:
        async with websockets.connect(f"{SERVER_URL}/ws/onboarding") as websocket:
            # Send Handshake
            handshake = {
                "bot_id": BOT_ID,
                "version": "1.0.0",
                "capabilities": ["text", "commands"],
                "public_key": "mock_public_key_pem_string",  # In production, generate a real key
            }
            await websocket.send(json.dumps(handshake))
            logger.info("   -> Sent Onboarding Handshake: %s", handshake)

            # Receive Response
            response = await websocket.recv()
            data = json.loads(response)
            logger.info("   <- Received: %s", data)

            if data.get("status") == "REGISTERED":
                api_key = data.get("api_key")
                logger.info("   [SUCCESS] Onboarding complete. Got API Key.")
            else:
                logger.error("   [FAILED] Onboarding failed.")
                return

    # Exception handling
    except ConnectionRefusedError:
        logger.error(
            "Could not connect to server at %s. Is the server running?", SERVER_URL
        )
        return
    except websockets.exceptions.ConnectionClosed:
        logger.error("Server closed connection.")
        return
    except json.JSONDecodeError as e:
        logger.error("JSON decoding error: %s", e)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(
            "Error: %s\nCould not connect to server at %s. Is the server running?",
            e,
            SERVER_URL,
        )
        return

    # ==========================================
    # PHASE 2: C2 CONNECTION (Secure Channel)
    # ==========================================
    logger.info("\n2. Connecting to Secure C2 Channel...")

    # We send the API key in headers (Zero Trust style) or in the handshake
    headers = {"x-bot-id": BOT_ID, "x-api-key": api_key}

    async with websockets.connect(
        f"{SERVER_URL}/ws/c2", extra_headers=headers
    ) as websocket:

        # 2A. Send C2 Handshake (Authentication)
        # Note: In a real implementation we have to sign a challenge,
        # but here we send credentials to get a session token.
        auth_payload = {"bot_id": BOT_ID, "api_key": api_key, "timestamp": 1234567890}
        await websocket.send(json.dumps(auth_payload))
        logger.info("   -> Sent Auth Handshake")

        # 2B. Wait for Auth Response
        response = await websocket.recv()
        auth_data = json.loads(response)
        logger.info("   <- Auth Response: %s", auth_data)

        if auth_data.get("status") != "SUCCESS":
            logger.error("   [FAILED] C2 Authentication failed.")
            return

        session_token = auth_data.get("session_token")
        logger.info(
            "   [SUCCESS] Authenticated! Session Token: %s...", session_token[:10]
        )

        # ==========================================
        # PHASE 3: SEND MESSAGES
        # ==========================================
        logger.info("\n3. Sending Test Message...")

        # Vi sender en besked der skal routes til 'console' adapteren (default)
        message = {
            "session_token": session_token,
            "data": {
                "content": "Hello from the Python Client!",
                "source": "client_script",
                "action": "chat",  # Dette trigger routing logic
            },
        }

        await websocket.send(json.dumps(message))
        logger.info("   -> Sent Message: %s", message["data"]["content"])

        # 2C. Wait for Server Acknowledgment / Response
        while True:
            try:
                response = await websocket.recv()
                msg_data = json.loads(response)
                logger.info("   <- Received from Server: %s", msg_data)

                # Hvis vi modtager success, bryder vi (for testen)
                if msg_data.get("status") == "SUCCESS":
                    logger.info("   [TEST COMPLETE] Message processed successfully.")
                    break
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Server closed connection.")
                break


# Run the bot
if __name__ == "__main__":
    try:
        asyncio.run(run_bot())

    # Exception handling
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
    except websockets.exceptions.ConnectionClosed:
        logger.warning("Server closed connection.")
    except websockets.exceptions.WebSocketException as e:
        logger.error("WebSocket error: %s", e)
    except json.JSONDecodeError as e:
        logger.error("JSON decoding error: %s", e)
    except asyncio.TimeoutError as e:
        logger.error("Timeout error: %s", e)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error: %s", e)
