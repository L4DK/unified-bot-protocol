"""
FilePath: "/runtime/llm-tool-calling/standardized_llm_tool_calling_runtime.py"
Project: Unified Bot Protocol (UBP) - Standardized LLM Tool Calling Runtime
Description: Model-agnostic orchestrator capable of bridging directly to UBP Adapters.
Author: "Michael Landbo"
Date created: "22/12/2025"
Date Modified: "22/12/2025"
Version: "v.1.1.0"
"""

import os
import sys
import json
import asyncio
import inspect
import logging
from typing import Dict, Any, List, Optional, Callable
from termcolor import colored
from dotenv import load_dotenv

# --- 0. Path & Environment Setup ---
# Add parent directory to path so we can import the 'adapters' folder
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir)) # Going up to the root of DEV
sys.path.append(parent_dir)

load_dotenv()

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UBP-Runtime")

# Attempt to import adapter registry
try:
     from adapters.registry import registry, create_adapter
     from adapters.base_adapter import AdapterContext, MessagePriority
     ADAPTERS_AVAILABLE = True
     logger.info(colored("✔ Adapter Registry loaded successfully", "green"))
except ImportError as e:
     ADAPTERS_AVAILABLE = False
     logger.warning(colored(f"⚠ Could not load Adapter Registry: {e}. Ensure integration paths are correct.", "yellow"))

# --- 1. Configuration
CONFIG = {
     'llm_providers': {
          'openai': {
               'api_key': os.getenv('OPENAI_API_KEY'),
               'model': 'gpt-4-turbo-preview',
               'max_tokens': 4096,
               'temperature': 0.7,
               'enabled': True
          },
          'anthropic': {
               'api_key': os.getenv('ANTHROPIC_API_KEY'),
               'model': 'claude-3-opus-20240229',
               'max_tokens': 4096,
               'temperature': 0.7,
               'enabled': False
          },
          'google': {
               'api_key': os.getenv('GOOGLE_API_KEY'),
               'model': 'gemini-pro',
               'enabled': False
          }
     },
     'runtime': {
          'default_provider': 'openai',
          'fallback_providers': ['anthropic', 'google'],
          'max_parallel_tools': 5,
          'tool_timeout': 30,
          'security_key': os.getenv('UBP_SECURITY_KEY', 'default-dev-key')
     }
}

class UnifiedBotRuntime:
     def __init__(self, config: Dict[str, Any]):
          self.config = config
          self.tools: Dict[str, Callable] = {}
          self.tool_definitions: List[Dict[str, Any]] = []
          self.active_adapters = {} # Cache for running adapter instances

          logger.info(colored("UBP Runtime Initialized", "green"))

     def register_tool(self, func: Callable):
          """Decorator to register a tool with the runtime."""
          self.tools[func.__name__] = func

          sig = inspect.signature(func)
          doc = func.__doc__ or "No description provided."

          params = {}
          required = []
          for name, param in sig.parameters.items():
               param_type = "string"
               if param.annotation == int: param_type = "integer"
               elif param.annotation == bool: param_type = "boolean"
               elif param.annotation == float: param_type = "number"
               elif param.annotation == dict: param_type = "object"

               params[name] = {
                    "type": param_type,
                    "description": f"Parameter {name}"
               }
               if param.default == inspect.Parameter.empty:
                    required.append(name)

          tool_def = {
               "type": "function",
               "function": {
                    "name": func.__name__,
                    "description": doc,
                    "parameters": {
                         "type": "object",
                         "properties": params,
                         "required": required
                    }
               }
          }
          self.tool_definitions.append(tool_def)
          logger.info(f"Tool registered: {func.__name__}")
          return func

     async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
          """Executes a specific tool securely."""
          if tool_name not in self.tools:
               return {"error": f"Tool {tool_name} not found"}

          try:
               logger.info(colored(f"Executing tool: {tool_name} args: {arguments}", "cyan"))
               result = await self.tools[tool_name](**arguments)
               return result
          except Exception as e:
               logger.error(f"Error executing tool {tool_name}: {e}")
               return {"error": str(e)}

     async def _call_openai(self, messages: List[Dict], tools: List[Dict]) -> Dict:
          """Internal handler for OpenAI API calls."""
          try:
               from openai import AsyncOpenAI
               cfg = self.config['llm_providers']['openai']
               client = AsyncOpenAI(api_key=cfg['api_key'])

               response = await client.chat.completions.create(
                    model=cfg['model'],
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                    temperature=cfg['temperature']
               )
               return response.choices[0].message
          except Exception as e:
               logger.error(f"OpenAI API Error: {e}")
               raise e

     async def process_message(self, user_message: str, provider: str = "openai") -> str:
          """Main orchestration loop."""
          conversation = [{"role": "user", "content": user_message}]

          # 1. Initial Call
          try:
               message = await self._call_openai(conversation, self.tool_definitions)
          except Exception as e:
               return f"Error: {e}"

          # 2. Tool Execution Loop
          if message.tool_calls:
               conversation.append(message)

               for tool_call in message.tool_calls:
                    fn_name = tool_call.function.name
                    fn_args = json.loads(tool_call.function.arguments)

                    tool_result = await self.execute_tool(fn_name, fn_args)

                    conversation.append({
                         "role": "tool",
                         "tool_call_id": tool_call.id,
                         "name": fn_name,
                         "content": json.dumps(str(tool_result))
                    })

               # 3. Final Response
               final_response = await self._call_openai(conversation, tools=None)
               return final_response.content

          return message.content

# --- Initialize Runtime ---
runtime = UnifiedBotRuntime(CONFIG)

# --- TOOLS (Integration for Adapters) ---
@runtime.register_tool
async def list_available_platforms() -> dict:
     """Returns a list of all available communication platforms (adapters)."""
     if not ADAPTERS_AVAILABLE:
          return {"error": "Adapter registry not available"}

     adapters = registry.list_adapters()
     return {
          "count": len(adapters),
          "platforms": [
               {"name": a.name, "category": a.category, "description": a.description}
               for a in adapters
          ]
     }

@runtime.register_tool
async def send_platform_message(platform: str, message_content: str, target_id: str = None) -> dict:
     """
     Sends a message via a specific platform adapter (e.g., 'discord', 'telegram').

     Args:
          platform: Name of the platform (discord, telegram, slack, email)
          message_content: The text to send
          target_id: (Optional) Channel ID, User ID or Email address.
     """
     if not ADAPTERS_AVAILABLE:
          return {"error": "Adapter registry system is missing."}

     logger.info(f"Requesting adapter for: {platform}")

     # 1. Check if adapter exists in registry
     metadata = registry.get_adapter(platform)
     if not metadata:
          return {"error": f"Platform '{platform}' is not supported/registered."}

     try:
          # 2. Instantiate Adapter (or get from cache)
          # Note: In a full prod setup, adapters run as separate services.
          # Here we instantiate directly for the tool call or use a bridge.
          if platform not in runtime.active_adapters:
               logger.info(f"Initializing new adapter instance for {platform}...")
               # We use the factory method from registry.py
               adapter_instance = create_adapter(platform)
               # Note: 'start()' is normally async and requires connection to Orchestrator.
               # In this "Tool Mode" we can call send_message directly if the adapter allows HTTP/API calls without full WS loop.
               # For now, we assume we can instantiate it.
               runtime.active_adapters[platform] = adapter_instance

          adapter = runtime.active_adapters[platform]

          # 3. Create Context
          context = AdapterContext(
               tenant_id="default-tenant",
               channel_id=target_id,
               user_id="llm-system"
          )

          # 4. Construct Message Payload
          msg_payload = {
               "type": "text",
               "content": message_content,
               "metadata": {"source": "ubp-llm-runtime"}
          }

          # 5. Send (Using the Base Adapter's queue or direct send)
          # If the adapter is not 'started' (connected to WS), queue may fail if it is waiting for loop.
          # We try to use send_message directly.
          logger.info(f"Sending message via {platform} adapter...")
          result = await adapter.send_message(context, msg_payload)

          return {
               "status": "success" if result.success else "failed",
               "platform_id": result.platform_message_id,
               "error": result.error_message
          }

     except Exception as e:
          logger.error(f"Failed to send via {platform}: {e}")
          return {"error": f"Adapter execution failed: {str(e)}"}

# --- Main Execution Block ---
async def main():
     print(colored("--- UBP Standardized Runtime (Integrated) Started ---", "green"))

     if ADAPTERS_AVAILABLE:
          print(colored("✔ Integration System Active", "cyan"))
     else:
          print(colored("✘ Integration System Inactive (Check paths)", "red"))

     # Test Scenario
     user_input = "List available platforms and then send a test message to Discord saying 'Hello from UBP Core'"
     print(f"\nUser: {user_input}\n")

     try:
          response = await runtime.process_message(user_input)
          print(colored(f"\nAssistant: {response}", "yellow"))
     except Exception as e:
          print(colored(f"Runtime Error: {e}", "red"))

if __name__ == "__main__":
     asyncio.run(main())
