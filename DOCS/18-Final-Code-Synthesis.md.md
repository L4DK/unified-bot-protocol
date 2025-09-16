### 18\. Final Code Synthesis: A Runnable UBP Framework

This section provides a complete, runnable implementation of a simplified UBP Orchestrator and a Bot Agent. We will use Python with modern libraries to demonstrate the core concepts.

**Technology Stack for this Example:**

  * **Web Server (for REST/Health Checks):** FastAPI
  * **Real-Time C2 Channel:** WebSockets (using the `websockets` library)
  * **Observability (Logging):** `python-json-logger`
  * **Observability (Metrics):** `prometheus-client`

**Note on Serialization:** For this runnable example, we will use JSON over the WebSocket for simplicity and to avoid requiring a Protobuf compilation step. However, as defined in our architecture, a production implementation **MUST** use serialized Protocol Buffers as the binary payload for maximum efficiency and type safety.

-----

### Component 1: The Bot Orchestrator Server

This server will:

1.  Run a WebSocket server to handle the real-time C2 connections.
2.  Manage a simple, in-memory registry of connected bots.
3.  Implement the Handshake and Heartbeat logic.
4.  Periodically "dispatch" a command to a connected bot.
5.  Use structured JSON logging for all events.

**File: `orchestrator.py`**

```python
import asyncio
import websockets
import json
import logging
import uuid
from pythonjsonlogger import jsonlogger

# --- 1. Observability: Structured Logging Setup ---
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(trace_id)s %(message)s')
logHandler.setFormatter(formatter)
logger = logging.getLogger("orchestrator")
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

# --- 2. Core Component: In-memory Bot Registry (simulates Service Registry) ---
# In a real system, this would be a distributed database like Consul or Redis.
connected_bots = {}

async def handle_bot_connection(websocket, path):
    """
    Manages the entire lifecycle of a single bot connection.
    """
    bot_info = None
    try:
        # --- 3. C2 API: Handshake & Authentication ---
        initial_msg_str = await websocket.recv()
        initial_msg = json.loads(initial_msg_str)
        
        if initial_msg.get("type") == "handshake_request":
            bot_id = initial_msg["payload"]["bot_id"]
            instance_id = initial_msg["payload"]["instance_id"]
            # (In production, validate the auth_token against a database)
            
            bot_info = {
                "bot_id": bot_id,
                "instance_id": instance_id,
                "websocket": websocket,
                "capabilities": initial_msg["payload"]["capabilities"]
            }
            connected_bots[instance_id] = bot_info
            
            handshake_response = {
                "type": "handshake_response",
                "payload": {
                    "status": "SUCCESS",
                    "heartbeat_interval_sec": 10
                }
            }
            await websocket.send(json.dumps(handshake_response))
            logger.info(f"Handshake successful for bot {bot_id} (instance: {instance_id})", extra={'trace_id': initial_msg.get('trace_id')})
        else:
            await websocket.close(1008, "Handshake required")
            logger.warning("Connection closed: First message was not a handshake.")
            return

        # --- 4. C2 API: Real-time Communication Loop ---
        async for message_str in websocket:
            message = json.loads(message_str)
            trace_id = message.get('trace_id')
            
            if message.get("type") == "heartbeat":
                logger.info(f"Heartbeat received from {instance_id}", extra={'trace_id': trace_id})
            
            elif message.get("type") == "command_response":
                logger.info(f"Received command response for '{message['payload']['command_id']}' from {instance_id}", extra={'trace_id': trace_id})
                
            elif message.get("type") == "event":
                logger.info(f"Received event '{message['payload']['event_name']}' from {instance_id}", extra={'trace_id': trace_id})

    except websockets.ConnectionClosed as e:
        logger.warning(f"Connection closed for {bot_info['instance_id'] if bot_info else 'unknown bot'}. Code: {e.code}, Reason: {e.reason}")
    finally:
        if bot_info and bot_info["instance_id"] in connected_bots:
            del connected_bots[bot_info["instance_id"]]

async def command_dispatcher():
    """
    Simulates the Orchestrator's logic for sending commands to bots.
    """
    while True:
        await asyncio.sleep(15) # Dispatch a command every 15 seconds
        if not connected_bots:
            continue

        # Find a bot that can handle 'task.execute'
        for instance_id, bot in list(connected_bots.items()):
            if "task.execute" in bot["capabilities"]:
                trace_id = str(uuid.uuid4())
                command = {
                    "type": "command_request",
                    "trace_id": trace_id,
                    "payload": {
                        "command_id": f"cmd-{uuid.uuid4()}",
                        "command_name": "task.execute",
                        "arguments": {"task_name": "process_data"}
                    }
                }
                try:
                    logger.info(f"Dispatching command 'task.execute' to {instance_id}", extra={'trace_id': trace_id})
                    await bot["websocket"].send(json.dumps(command))
                    break # Send to only one bot for this example
                except websockets.ConnectionClosed:
                    logger.warning(f"Could not send command to {instance_id}; connection is closed.", extra={'trace_id': trace_id})


async def main():
    # Start the command dispatcher as a background task
    dispatcher_task = asyncio.create_task(command_dispatcher())

    # Start the WebSocket server
    async with websockets.serve(handle_bot_connection, "localhost", 8765):
        logger.info("Orchestrator C2 Server started on ws://localhost:8765")
        await asyncio.Future() # Run forever

if __name__ == "__main__":
    asyncio.run(main())
```

-----

### Component 2: The Bot Agent

This agent will:

1.  Run a FastAPI server to expose health check and metrics endpoints.
2.  Connect to the Orchestrator's WebSocket server and perform the handshake.
3.  Run a background task to send periodic heartbeats.
4.  Listen for commands, simulate executing a task, and send a response.
5.  Implement distinct Liveness and Readiness probes.

**File: `bot_agent.py`**

```python
import asyncio
import websockets
import json
import logging
import uuid
import threading
import time
from fastapi import FastAPI, Response, status
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from pythonjsonlogger import jsonlogger

# --- 1. Configuration ---
ORCHESTRATOR_URL = "ws://localhost:8765"
BOT_ID = "bot-data-processor-01"
INSTANCE_ID = f"instance-{uuid.uuid4()}"
API_KEY = "secret-key" # Sent during handshake

# --- 2. Observability: Structured Logging Setup ---
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(instance_id)s %(trace_id)s %(message)s')
logHandler.setFormatter(formatter)
logger = logging.getLogger("bot-agent")
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)
extra_context = {'instance_id': INSTANCE_ID}

# --- 3. Observability: Metrics Definition ---
UBP_CONNECTION_STATUS = Gauge("ubp_connection_status", "Agent's connection state to Orchestrator (1=connected, 0=disconnected)")
COMMANDS_PROCESSED_TOTAL = Counter("ubp_commands_processed_total", "Total commands processed", ["command_name", "status"])

# --- 4. Health Checking: Simulate a dependency ---
db_is_connected = True 

# --- 5. FastAPI App for Health & Metrics ---
app = FastAPI()

@app.get("/health/live")
async def liveness_probe():
    """Liveness Probe: Is the application process running?"""
    return {"status": "ALIVE"}

@app.get("/health/ready")
async def readiness_probe(response: Response):
    """Readiness Probe: Is the application ready to handle work?"""
    if db_is_connected and UBP_CONNECTION_STATUS._value.get() == 1:
        return {"status": "READY", "dependencies": {"database": "ok", "orchestrator": "connected"}}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "NOT_READY", "dependencies": {"database": "ok" if db_is_connected else "disconnected", "orchestrator": "connected" if UBP_CONNECTION_STATUS._value.get() == 1 else "disconnected"}}

@app.get("/metrics")
async def metrics():
    """Exposes metrics for Prometheus to scrape."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# --- 6. UBP Client Logic ---
async def ubp_client_logic():
    """Handles the main WebSocket connection and logic."""
    while True: # Main reconnect loop
        try:
            async with websockets.connect(ORCHESTRATOR_URL) as websocket:
                UBP_CONNECTION_STATUS.set(1)
                logger.info("Connected to Orchestrator.", extra=extra_context)

                # 1. Handshake
                trace_id = str(uuid.uuid4())
                handshake_req = {
                    "type": "handshake_request",
                    "trace_id": trace_id,
                    "payload": {
                        "bot_id": BOT_ID,
                        "instance_id": INSTANCE_ID,
                        "auth_token": API_KEY,
                        "capabilities": ["task.execute"]
                    }
                }
                await websocket.send(json.dumps(handshake_req))
                
                response_str = await websocket.recv()
                response = json.loads(response_str)
                
                if response.get("type") == "handshake_response" and response["payload"]["status"] == "SUCCESS":
                    logger.info("Handshake successful.", extra={'trace_id': trace_id, **extra_context})
                    heartbeat_interval = response["payload"]["heartbeat_interval_sec"]
                else:
                    logger.error("Handshake failed.", extra={'trace_id': trace_id, **extra_context})
                    return

                # 2. Start Heartbeat Task
                async def send_heartbeats():
                    while True:
                        await asyncio.sleep(heartbeat_interval)
                        heartbeat_msg = {"type": "heartbeat", "trace_id": str(uuid.uuid4())}
                        try:
                            await websocket.send(json.dumps(heartbeat_msg))
                        except websockets.ConnectionClosed:
                            break
                
                heartbeat_task = asyncio.create_task(send_heartbeats())

                # 3. Listen for Commands
                async for message_str in websocket:
                    message = json.loads(message_str)
                    trace_id = message.get('trace_id')
                    
                    if message.get("type") == "command_request":
                        command = message["payload"]
                        logger.info(f"Received command '{command['command_name']}'", extra={'trace_id': trace_id, **extra_context})
                        
                        # Simulate task execution
                        time.sleep(2) 
                        
                        response_payload = {
                            "command_id": command["command_id"],
                            "status": "SUCCESS",
                            "result": {"message": f"Task {command['arguments']['task_name']} completed."}
                        }
                        command_response = {
                            "type": "command_response",
                            "trace_id": trace_id,
                            "payload": response_payload
                        }
                        await websocket.send(json.dumps(command_response))
                        COMMANDS_PROCESSED_TOTAL.labels(command_name=command['command_name'], status="success").inc()

                heartbeat_task.cancel()

        except (websockets.ConnectionClosed, ConnectionRefusedError) as e:
            logger.warning(f"Connection lost: {e}. Reconnecting in 5 seconds...", extra=extra_context)
            UBP_CONNECTION_STATUS.set(0)
            await asyncio.sleep(5)

def run_fastapi_server():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # Run FastAPI in a separate thread
    fastapi_thread = threading.Thread(target=run_fastapi_server, daemon=True)
    fastapi_thread.start()
    
    # Run the UBP client logic in the main thread
    asyncio.run(ubp_client_logic())
```

-----

### How to Run the Synthesis

1.  **Prerequisites:** Install the necessary Python libraries.

    ```bash
    pip install fastapi uvicorn websockets python-json-logger prometheus-client
    ```

2.  **Start the Orchestrator:** Open a terminal window and run:

    ```bash
    python orchestrator.py
    ```

    You will see a log message indicating the server has started.

3.  **Start the Bot Agent:** Open a *second* terminal window and run:

    ```bash
    python bot_agent.py
    ```

    You will see logs from the agent as it connects, performs the handshake, and then receives commands from the Orchestrator every 15 seconds.

4.  **Interact and Observe:**

      * **Check Health:** While the agent is running, open a web browser or use cURL to check its health endpoints:
        ```bash
        # Check liveness
        curl http://localhost:8000/health/live

        # Check readiness
        curl http://localhost:8000/health/ready
        ```
      * **Check Metrics:** View the Prometheus metrics:
        ```bash
        curl http://localhost:8000/metrics
        ```
      * **Observe Logs:** Watch the structured JSON logs appear in both terminal windows, and note how the `trace_id` from the Orchestrator's command appears in the agent's logs when it processes that command.
      * **Simulate Failure:** Stop the Orchestrator (`Ctrl+C`). You will see the Bot Agent detect the connection loss, set its connection status metric to 0, and attempt to reconnect. Its readiness probe (`/health/ready`) will now fail if you check it. Once you restart the Orchestrator, the agent will automatically reconnect and become ready again, demonstrating self-healing principles.

This concludes our deep dive into the architecture and implementation of the Unified Bot Protocol framework. These runnable examples provide a tangible foundation, demonstrating how all the theoretical principles come together to create a system that is robust, observable, and ready for scalable, real-world deployment.
