### **Phase 1: Core Protocol and C2 Channel**

This phase focuses on establishing the fundamental communication contract and the real-time channel.

	#### **Step 1: Generate Foundational Schemas and Documentation**

	*   **Goal:** Create the non-negotiable contract for all communication (the `.proto` files) and the initial GitHub documentation. This is the absolute foundation of the project.
	*   **Prompt:**
			> "Acting as the principal architect of the UBP framework, generate the initial project structure for the official GitHub repository. Create the necessary `.proto` files for the core UBP message schemas as defined in the specification documents. Specifically, generate the content for `ubp/v1/core.proto` and `ubp/v1/tools.proto`. Also, generate the initial `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, and `LICENSE` (using Apache 2.0) files."

			
	#### **Step 2: Compile Protocol Buffers**

	*   **Goal:** This is a local step for you. After the AI generates the `.proto` files, you need to compile them into Python code so your application can use them.
	*   **Action (for you):** Run the `protoc` command as specified in the generated `README.md`. This creates the necessary Python gRPC/Protobuf library files.

	
	#### **Step 3: Build the Core Orchestrator Server**

	*   **Goal:** Create the first runnable component: a basic Orchestrator server that can accept connections, manage a fleet of agents, and dispatch commands.
	*   **Prompt:**
			> "Based on the schemas and Document #18 (Final Code Synthesis), generate the Python code for the initial **Bot Orchestrator server**. The server must:
			> 1.  Use Python with `websockets` for the C2 channel and `FastAPI` to serve a basic `/health/live` endpoint.
			> 2.  Implement the C2 connection handler to manage the full UBP handshake, validate credentials (use a simple in-memory dictionary for now), and handle incoming heartbeats.
			> 3.  Maintain an in-memory registry of all connected bot instances.
			> 4.  Include a background task that periodically dispatches a sample `task.execute` command to a capable, connected agent.
			> 5.  Integrate structured JSON logging for all major events (connection, handshake, command dispatch)."

			
	#### **Step 4: Build the Reference Bot Agent**

	*   **Goal:** Create the client-side counterpart to the Orchestrator. This reference agent will be the template for all future bots.
	*   **Prompt:**
			> "Now, generate the Python code for a reference **Bot Agent** that can connect to the Orchestrator. The agent must:
			> 1.  Use the `websockets` library to connect to the C2 endpoint and automatically handle reconnections.
			> 2.  Implement the client-side logic for the UBP handshake and send periodic heartbeats.
			> 3.  Listen for incoming `CommandRequest` messages from the Orchestrator, log the request, simulate work, and send back a `CommandResponse`.
			> 4.  Run a `FastAPI` server in a background thread to expose its own `/health/live` and `/health/ready` endpoints, as well as a `/metrics` endpoint using `prometheus-client`.
			> 5.  Implement structured JSON logging for all its activities."

---