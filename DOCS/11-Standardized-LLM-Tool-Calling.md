### 11\. Standardized LLM Tool Calling via UBP

Modern LLMs are evolving from simple text generators into capable agents that can perform meaningful work by interacting with external systems, APIs, and databases. This capability is commonly known as "tool calling" or "function calling".[1, 2, 3] However, each LLM provider (OpenAI, Anthropic, Google, etc.) has its own proprietary format for defining and calling tools. This creates vendor lock-in and makes it difficult to build model-agnostic orchestration logic.

The UBP framework solves this by providing a standardized, universal mechanism for orchestrating LLMs that support tool calling. It abstracts away the provider-specific implementations, allowing the entire ecosystem to interact with any LLM agent through a single, consistent protocol.

#### Design Philosophy

The philosophy is to **decouple the LLM's reasoning capability from the tool's execution environment**. The LLM's job is to understand a user's intent and determine *which* tool to use and with *what* parameters. It should not be responsible for the actual execution of that tool. The UBP acts as the standardized communication layer for this "intent to act."

  * **Model Agnosticism:** The Orchestrator and the bots that execute tools should not need to know whether the reasoning is being done by GPT-4, Claude 3, or a local Llama model. They interact solely through standardized UBP `CommandRequest` and `CommandResponse` messages.[4]
  * **Centralized Routing and Governance:** By funneling all tool-use requests through the Orchestrator as UBP commands, we gain a central point of control. The Orchestrator can apply security policies, log all tool usage, and intelligently route the request to the correct specialized bot for execution.
  * **Separation of Concerns:** We create a clear distinction between "reasoning agents" (LLM-based bots that decide what to do) and "acting agents" (simpler bots that are experts at a specific task, like querying a database or calling a third-party API). This makes the system highly modular, scalable, and easier to maintain.

#### Technical Implementation & Interaction Flow

The entire process is managed through the standard UBP message flow, with specific conventions for registering and invoking tools.

1.  **Tool Registration (Agent Startup):**

      * An LLM-based Bot Agent, upon connecting to the Orchestrator, must declare the tools it is capable of reasoning about.
      * It does this by sending a specialized UBP `CommandRequest` with `command_name: "agent.register_tools"`.
      * The `arguments` payload of this command contains a list of `ToolDefinition` objects. Each definition includes the tool's name, a clear description, and a schema for its parameters (often a subset of the OpenAPI or JSON Schema specification).[1, 3] This description is critical, as it's what the LLM uses to decide when to use the tool.[3]

2.  **User Prompt & LLM Reasoning:**

      * A user sends a prompt (e.g., "What is the status of order \#123?").
      * The Orchestrator routes this prompt to the appropriate LLM agent.
      * The agent's internal logic passes the prompt and the registered tool definitions to its underlying LLM.
      * The LLM analyzes the prompt and determines that to answer the question, it needs to call the `get_order_status` tool with the parameter `order_id: 123`.

3.  **Tool Invocation (LLM Agent -\> Orchestrator):**

      * The LLM does not respond with natural language. Instead, its response is a structured object indicating a tool call.
      * The Bot Agent receives this structured response and translates it into a standard UBP `CommandRequest`.
      * The `command_name` is set to the tool name (`get_order_status`).
      * The `arguments` payload contains the parameters inferred by the LLM (`{"order_id": 123}`).
      * The agent sends this UBP command to the Orchestrator.

4.  **Orchestrator Routing:**

      * The Orchestrator receives the `CommandRequest` for `get_order_status`.
      * It consults its service registry to find which connected agent has registered the capability to execute this command. It finds that the "Database Query Bot" is the designated executor.
      * The Orchestrator forwards the exact same `CommandRequest` to the "Database Query Bot".

5.  **Tool Execution & Response (Executing Agent -\> Orchestrator):**

      * The "Database Query Bot" receives the command. It executes its internal logic (e.g., runs a SQL query `SELECT status FROM orders WHERE id = 123`).
      * It gets the result (e.g., "Shipped").
      * It packages this result into a UBP `CommandResponse`, making sure to include the original `command_id`, and sends it back to the Orchestrator.

6.  **Result Synthesis (Orchestrator -\> LLM Agent -\> User):**

      * The Orchestrator receives the `CommandResponse` and routes it back to the original LLM agent that made the request.
      * The LLM agent receives the tool's output ("Shipped").
      * It now makes a second call to its underlying LLM, providing the original prompt, the tool call it made, and the tool's result.
      * The LLM synthesizes this information into a final, natural-language response.
      * The agent sends this final response to the user: "The status of order \#123 is: Shipped."

-----

### Real-Life Code Examples

#### 1\. Protobuf Schema for Tool Definitions

We need to extend our Protobuf schema to include a message for defining tools.

File: `ubp/v1/tools.proto`

```protobuf
syntax = "proto3";

package ubp.v1;

// Defines the structure for a single tool parameter.
message ToolParameter {
  string name = 1;
  string type = 2; // e.g., "string", "integer", "boolean"
  string description = 3;
  bool required = 4;
}

// Defines a single tool that an LLM agent can use.
message ToolDefinition {
  string name = 1; // The name of the tool, e.g., "get_order_status"
  string description = 2; // A clear, semantic description for the LLM.
  repeated ToolParameter parameters = 3;
}

// The payload for the "agent.register_tools" command.
message RegisterToolsArguments {
  repeated ToolDefinition tools = 1;
}
```

#### 2\. LLM Agent: Registering and Invoking a Tool (Conceptual Python)

```python
import ubp.v1.core_pb2 as ubp_v1
import ubp.v1.tools_pb2 as ubp_tools_v1
from google.protobuf.any_pb2 import Any
import my_llm_provider # A fictional LLM SDK

class LlmReasoningAgent:
    def __init__(self, ubp_connection):
        self.ubp_connection = ubp_connection
        self.tools =
            }
        ]

    def register_tools_with_orchestrator(self):
        """Sends the tool definitions to the Orchestrator on startup."""
        tool_defs =
        for tool in self.tools:
            params =]
            tool_defs.append(ubp_tools_v1.ToolDefinition(
                name=tool['name'],
                description=tool['description'],
                parameters=params
            ))
        
        args = ubp_tools_v1.RegisterToolsArguments(tools=tool_defs)
        any_payload = Any()
        any_payload.Pack(args)

        register_command = ubp_v1.CommandRequest(
            command_name="agent.register_tools",
            arguments=any_payload
        )
        # This would be wrapped in a UbpMessage and sent
        self.ubp_connection.send(register_command)
        print("LLM Agent: Registered tools with Orchestrator.")

    def handle_user_prompt(self, prompt: str):
        """Processes a user prompt, decides if a tool is needed."""
        # The LLM provider's SDK would handle the reasoning.
        llm_response = my_llm_provider.chat(prompt, tools=self.tools)

        if llm_response.has_tool_call():
            tool_call = llm_response.tool_calls
            print(f"LLM Agent: Model decided to call tool '{tool_call.name}' with args {tool_call.arguments}")

            # Translate the LLM's decision into a UBP CommandRequest
            # (Here we would need to pack the arguments dict into an Any proto)
            tool_command = ubp_v1.CommandRequest(
                command_name=tool_call.name,
                # arguments=... packed arguments...
            )
            self.ubp_connection.send(tool_command)
        else:
            # Send the natural language response
            print(f"LLM Agent: Sending direct response: {llm_response.text}")
```

#### 3\. Tool-Executing Agent (Conceptual Python)

This is a simple, specialized bot that only knows how to query a database.

```python
class DatabaseQueryAgent:
    def __init__(self, ubp_connection):
        self.ubp_connection = ubp_connection

    def listen_for_commands(self):
        """Listens for commands from the Orchestrator."""
        while True:
            command = self.ubp_connection.receive() # Blocking call
            if command.command_name == "get_order_status":
                # Unpack arguments
                order_id = command.arguments["order_id"]
                
                # Execute the actual logic
                status = self._query_database(order_id)
                
                # Send the response back to the Orchestrator
                response = ubp_v1.CommandResponse(
                    command_id=command.command_id,
                    status=ubp_v1.CommandResponse.Status.SUCCESS,
                    # result=... packed result payload...
                )
                self.ubp_connection.send(response)

    def _query_database(self, order_id: str) -> str:
        """Simulates a database lookup."""
        print(f"Executing Agent: Querying DB for order {order_id}")
        #... database logic...
        return "Shipped"
```

This standardized flow transforms the UBP framework into a powerful, model-agnostic platform for building complex, multi-agent AI systems.
