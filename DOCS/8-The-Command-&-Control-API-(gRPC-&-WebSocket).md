### 8\. The Command & Control API (gRPC/WebSocket)

This API is the high-speed, persistent communication channel that forms the backbone of the entire orchestration framework. Unlike the stateless, request-response nature of the Management API, the Command & Control (C2) API is designed for stateful, low-latency, bidirectional interaction. It is the direct implementation of the Unified Bot Protocol's real-time specification.

#### Design Philosophy

The philosophy behind this API is a strict adherence to the **Command and Control (C2) operational model**.[1, 2, 3] The Orchestrator is not a passive message queue; it is an active fleet commander. This requires a communication channel that is fundamentally different from standard web APIs:

  * **Persistent and Stateful:** Connections are long-lived. Once a Bot Agent connects and authenticates, the connection remains open, allowing the Orchestrator to maintain a real-time awareness of the agent's status. This statefulness is critical for fleet management.[4, 5]
  * **Server-Initiated Communication (Push):** The core requirement of a C2 model is the ability for the central server to push commands to agents at any time. A traditional request-response model, where the client must always initiate communication, is insufficient. This API allows the Orchestrator to send unsolicited `CommandRequest` messages to any connected agent instantly.[4, 5, 6]
  * **Low Latency and High Throughput:** The exchange of commands, responses, and events must be as fast and efficient as possible. The design prioritizes binary protocols and modern transports (gRPC over HTTP/2, WebSockets) to minimize overhead and maximize performance.[4, 1, 6]
  * **Asynchronous and Bidirectional:** Communication is a two-way street. While the Orchestrator pushes commands, the agent can simultaneously and asynchronously push `Event` notifications (e.g., a new message was received) or `CommandResponse` messages back to the Orchestrator.[4, 5, 6]

#### Technical Implementation & Interaction Flow

The API is exposed over two parallel transports to achieve our core principle of interoperability: gRPC for backend services and WebSockets for browser-based agents. Regardless of the transport, the message flow and semantics are identical, enforced by the UBP Protobuf schema.

  * **gRPC Service Endpoint:** A gRPC service named `ControlStream` with a single bidirectional streaming method, `Connect`.
  * **WebSocket Endpoint:** A single WebSocket endpoint, e.g., `wss://orchestrator.example.com/v1/connect`.

The interaction for any connection follows a strict, four-stage lifecycle:

1.  **Connection Initiation:** The Bot Agent *always* initiates the connection to the Orchestrator's endpoint.
2.  **Handshake & Authentication:** This is the critical first step to establish a trusted session.
      * The **first message** sent by the agent **MUST** be a `UbpMessage` containing a `HandshakeRequest`. This message includes the agent's `bot_id`, a unique `instance_id` for this process, and its `auth_token`.
      * The Orchestrator receives this request, validates the credentials, and checks the bot's registration status.
      * The **first message** sent back by the Orchestrator **MUST** be a `UbpMessage` containing a `HandshakeResponse`. If successful, the connection is considered active and authenticated. If it fails, the connection is terminated.
3.  **Real-time Communication:** Once the handshake is complete, the channel is fully open for asynchronous, bidirectional communication.
      * The Orchestrator can send `CommandRequest` messages at any time.
      * The agent can send `Event` or `CommandResponse` messages at any time.
4.  **Liveness (Heartbeats):** To ensure the Orchestrator knows the agent is still alive and to prevent dead connections from accumulating, the agent is required to periodically send `Heartbeat` messages at the interval suggested in the `HandshakeResponse`. If the Orchestrator does not receive a heartbeat within a configured grace period, it will assume the agent has failed and will forcibly terminate the connection.

-----

### Real-Life Code Examples

#### 1\. gRPC Implementation

**A. Service Definition (`control_stream.proto`)**
This is the formal contract for the gRPC service.

```protobuf
syntax = "proto3";

import "ubp/v1/core.proto";

package ubp.v1;

service ControlStream {
  // Establishes a long-lived bidirectional stream. The first message from the
  // client MUST be a HandshakeRequest, and the first from the server MUST
  // be a HandshakeResponse. All subsequent messages can be sent
  // asynchronously by either party.
  rpc Connect(stream UbpMessage) returns (stream UbpMessage);
}
```

**B. Orchestrator Server (Python gRPC)**
This server implements the `Connect` method, handling the handshake and then echoing messages.

```python
import grpc
from concurrent import futures
import time
import uuid

# Assume ubp.v1.core_pb2 and control_stream_pb2_grpc are generated from.proto files
import ubp.v1.core_pb2 as ubp_v1
import ubp.v1.control_stream_pb2_grpc as control_stream_grpc

class ControlStreamServicer(control_stream_grpc.ControlStreamServicer):
    def Connect(self, request_iterator, context):
        print("Orchestrator: Client is attempting to connect...")

        # 1. HANDSHAKE: Expect the first message to be a HandshakeRequest
        initial_msg = next(request_iterator)
        if not initial_msg.HasField("handshake_request"):
            print("Orchestrator: Handshake failed. First message was not a HandshakeRequest.")
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Handshake failed.")
            return

        handshake = initial_msg.handshake_request
        print(f"Orchestrator: Received handshake from bot_id={handshake.bot_id}, instance_id={handshake.instance_id}")

        # (In a real system, you would validate the auth_token here)
        
        # 2. HANDSHAKE RESPONSE: Send a success response
        handshake_response = ubp_v1.HandshakeResponse(
            status=ubp_v1.HandshakeResponse.Status.SUCCESS,
            heartbeat_interval_sec=30
        )
        yield ubp_v1.UbpMessage(handshake_response=handshake_response)
        print("Orchestrator: Handshake successful. Connection active.")

        # 3. REAL-TIME COMMUNICATION LOOP
        for message in request_iterator:
            if message.HasField("heartbeat"):
                print(f"Orchestrator: Received heartbeat from {handshake.instance_id}")
            elif message.HasField("event"):
                print(f"Orchestrator: Received event '{message.event.event_name}'")
                # Example of pushing a command back in response to an event
                command = ubp_v1.CommandRequest(command_id=str(uuid.uuid4()), command_name="acknowledge_event")
                yield ubp_v1.UbpMessage(command_request=command)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    control_stream_grpc.add_ControlStreamServicer_to_server(ControlStreamServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("gRPC C2 Server started on port 50051")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
```

**C. Bot Agent Client (Python gRPC)**
This client connects, performs the handshake, and then uses threads to handle sending and receiving messages concurrently.

```python
import grpc
import threading
import time
import uuid

import ubp.v1.core_pb2 as ubp_v1
import ubp.v1.control_stream_pb2_grpc as control_stream_grpc

def generate_messages(stub):
    # 1. HANDSHAKE: Send the initial HandshakeRequest
    handshake_req = ubp_v1.HandshakeRequest(
        bot_id="bot-abc-123",
        instance_id=f"instance-{uuid.uuid4()}",
        auth_token="secret-api-key"
    )
    yield ubp_v1.UbpMessage(handshake_request=handshake_req)

    # 2. HEARTBEAT LOOP: Periodically send heartbeats
    while True:
        time.sleep(30) # Use interval from HandshakeResponse in a real client
        print("Agent: Sending heartbeat...")
        heartbeat = ubp_v1.Heartbeat()
        yield ubp_v1.UbpMessage(heartbeat=heartbeat)

def run_client():
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = control_stream_grpc.ControlStreamStub(channel)
        
        # The message generator runs in a separate thread to send heartbeats
        message_iterator = generate_messages(stub)
        
        print("Agent: Connecting to Orchestrator...")
        responses = stub.Connect(message_iterator)

        try:
            for response in responses:
                if response.HasField("handshake_response"):
                    if response.handshake_response.status == ubp_v1.HandshakeResponse.Status.SUCCESS:
                        print("Agent: Handshake successful!")
                    else:
                        print("Agent: Handshake failed!")
                        break
                elif response.HasField("command_request"):
                    print(f"Agent: Received command: {response.command_request.command_name}")
                    # (Execute command logic here)
        except grpc._channel._Rendezvous as e:
            print(f"Agent: Connection error: {e}")

if __name__ == '__main__':
    run_client()
```

-----

#### 2\. WebSocket Implementation

**A. Orchestrator Server (Python `websockets`)**
This server listens for WebSocket connections and expects binary Protobuf messages.

```python
import asyncio
import websockets
import ubp.v1.core_pb2 as ubp_v1

async def handler(websocket, path):
    print("Orchestrator: Client is attempting to connect via WebSocket...")
    try:
        # 1. HANDSHAKE: Expect the first message to be a HandshakeRequest
        initial_data = await websocket.recv()
        initial_msg = ubp_v1.UbpMessage()
        initial_msg.ParseFromString(initial_data)

        if not initial_msg.HasField("handshake_request"):
            print("Orchestrator: Handshake failed. Closing connection.")
            return

        handshake = initial_msg.handshake_request
        print(f"Orchestrator: Received WebSocket handshake from bot_id={handshake.bot_id}")

        # 2. HANDSHAKE RESPONSE: Send a success response
        handshake_response = ubp_v1.HandshakeResponse(status=ubp_v1.HandshakeResponse.Status.SUCCESS)
        response_wrapper = ubp_v1.UbpMessage(handshake_response=handshake_response)
        await websocket.send(response_wrapper.SerializeToString())
        print("Orchestrator: WebSocket handshake successful.")

        # 3. REAL-TIME COMMUNICATION LOOP
        async for message_data in websocket:
            message = ubp_v1.UbpMessage()
            message.ParseFromString(message_data)
            if message.HasField("heartbeat"):
                print(f"Orchestrator: Received WebSocket heartbeat from {handshake.instance_id}")

    except websockets.ConnectionClosed:
        print("Orchestrator: Client disconnected.")

async def main():
    async with websockets.serve(handler, "localhost", 8765):
        print("WebSocket C2 Server started on ws://localhost:8765")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
```

**B. Bot Agent Client (Browser JavaScript)**
This client runs in a browser. It requires a library like `protobufjs` to handle the serialization.

```html
<!DOCTYPE html>
<html>
<head>
    <title>WebSocket Bot Agent</title>
    <script src="https://cdn.jsdelivr.net/npm/protobufjs@7.2.5/dist/protobuf.min.js"></script>
</head>
<body>
    <h1>WebSocket Bot Agent Console</h1>
    <pre id="log"></pre>
    <script src="agent.js"></script>
</body>
</html>
```

```javascript
// agent.js

const logElement = document.getElementById('log');
function log(message) {
    console.log(message);
    logElement.textContent += message + '\n';
}

// Load the.proto file and then run the main logic
protobuf.load("ubp/v1/core.proto").then(function(root) {
    const UbpMessage = root.lookupType("ubp.v1.UbpMessage");
    const HandshakeRequest = root.lookupType("ubp.v1.HandshakeRequest");
    const Heartbeat = root.lookupType("ubp.v1.Heartbeat");

    const socket = new WebSocket('ws://localhost:8765');
    socket.binaryType = 'arraybuffer'; // Important for receiving binary data

    socket.onopen = function(event) {
        log('Agent: Connected to Orchestrator via WebSocket.');
        
        // 1. HANDSHAKE: Create and send the HandshakeRequest
        const handshakePayload = { 
            botId: "bot-web-789", 
            instanceId: `instance-browser-${Math.random().toString(16).slice(2)}`,
            authToken: "web-secret-key"
        };
        const handshakeRequest = HandshakeRequest.create(handshakePayload);
        
        const wrapperPayload = { handshakeRequest: handshakeRequest };
        const ubpMessage = UbpMessage.create(wrapperPayload);
        const buffer = UbpMessage.encode(ubpMessage).finish();
        
        socket.send(buffer);
        log('Agent: Sent HandshakeRequest.');
    };

    socket.onmessage = function(event) {
        // All incoming messages are binary ArrayBuffers
        const buffer = new Uint8Array(event.data);
        const message = UbpMessage.decode(buffer);

        if (message.handshakeResponse) {
            if (message.handshakeResponse.status === 0 /* SUCCESS */) {
                log('Agent: Handshake successful!');
                // 2. HEARTBEAT: Start sending periodic heartbeats
                setInterval(() => {
                    log('Agent: Sending heartbeat...');
                    const heartbeat = Heartbeat.create({});
                    const wrapper = UbpMessage.create({ heartbeat: heartbeat });
                    const hbBuffer = UbpMessage.encode(wrapper).finish();
                    socket.send(hbBuffer);
                }, 30000);
            } else {
                log('Agent: Handshake failed!');
                socket.close();
            }
        } else if (message.commandRequest) {
            log(`Agent: Received command: ${message.commandRequest.commandName}`);
        }
    };

    socket.onclose = () => log('Agent: Disconnected from Orchestrator.');
    socket.onerror = (error) => log(`Agent: WebSocket Error: ${error}`);
});
```

This dual-transport API provides the robust, real-time foundation necessary for the Orchestrator to effectively command and control its entire fleet of bots, whether they are running in a data center or a user's web browser.
