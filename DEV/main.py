"""
FilePath: "/main.py"
Project: Unified Bot Protocol (UBP) - Core Entry Point
Description: Central Orchestrator that bridges Adapters with the LLM Runtime and Core Services.
Author: "Michael Landbo"
Date created: "22/12/2025"
Version: "1.1.0"
"""

# --- 0. Imports ---
import asyncio
import logging
import os
import sys
import json
from typing import Dict, Any
from termcolor import colored
from dotenv import load_dotenv

# --- 0. Local Imports ---
from runtime.llm_tool_calling.standardized_llm_tool_calling_runtime import UnifiedBotRuntime, CONFIG as RUNTIME_CONFIG
from adapters.registry import registry, create_adapter
from adapters.base_adapter import AdapterContext

# --- 0. Core Modules ---
from runtime.core.conversation_manager import conversation_manager
from runtime.core.analytics import analytics
from runtime.core.ai_enhancer import ai_enhancer

# --- 0. Environment Setup ---

# Ensures that we can import from subfolders
current_dir = os.path.dirname(os.path.abspath(__file__))
# Load den centrale .env fil fra roden af DEV mappen
env_path = os.path.join(current_dir, ".env")
# Load environment variables
load_dotenv(env_path, override=True)


# --- 1. Path Setup ---

# Path Setup
sys.path.append(os.path.join(current_dir, "runtime", "llm_tool_calling"))
sys.path.append(os.path.join(current_dir, "adapters"))


# --- 2. Logging Setup ---
logging.basicConfig(
     level=logging.INFO,
     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
     handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("UBP-Core")


# --- Configuration ---

# ADAPTERS
# Choose which adapters to start automatically
ENABLED_ADAPTERS = [
     "console",   # Your terminal CLI chat
     # "discord",
     # "telegram",
     # "slack",
     # "whatsapp",
     # "mqtt",
     # "zabbix",
     # "email_imap"
]

# --- 3. Orchestrator (Example of a Local Orchestrator) ---
class LocalOrchestrator:
     """
     Simulates a UBP Server with full memory and logic.
     """
     def __init__(self):
          self.runtime = UnifiedBotRuntime(RUNTIME_CONFIG)
          self.active_adapters = {}
          self.running = True

          # Initialize conversation manager
          conversation_manager.initialize()

          # Initialize analytics
          analytics.initialize()

          # Initialize AI Enhancer
          ai_enhancer.initialize()

          # Initialize runtime
          asyncio.create_task(self.runtime.start())

          # Initialize analytics
          asyncio.create_task(analytics.start())

          # Initialize AI Enhancer
          asyncio.create_task(ai_enhancer.start())


     # Main Loop
     async def start(self):
          logger.info(colored("--- UBP System Starting (Smart Mode) ---", "green", attrs=['bold']))

          # 1. Start Adapters
          if not ENABLED_ADAPTERS:
               logger.warning(colored("⚠ No adapters enabled in main.py. Edit ENABLED_ADAPTERS list.", "yellow"))

          # Start enabled adapters
          for adapter_name in ENABLED_ADAPTERS:
               try:
                    # Initialize adapter logger
                    logger.info(f"Initializing adapter: {adapter_name}")
                    adapter = create_adapter(adapter_name)

                    # Monkey-patch send_to_orchestrator for at route beskeder lokalt
                    adapter._send_to_orchestrator = self.handle_incoming_message
                    adapter.connected = True

                    # Start adapterens loop
                    asyncio.create_task(adapter._setup_platform())

                    # Add adapter to active_adapters
                    self.active_adapters[adapter_name] = adapter
                    logger.info(colored(f"✔ {adapter_name} started", "green"))

               except Exception as e:
                    logger.error(colored(f"✘ Failed to start {adapter_name}: {e}", "red"))

          # 2. Keep Alive Loop
          logger.info(colored("--- System Ready & Listening ---", "cyan"))
          try:
               while self.running:
                    await asyncio.sleep(1)
          except asyncio.CancelledError:
               await self.shutdown()

     # Callback: Handles incoming messages
     async def handle_incoming_message(self, message: Dict[str, Any]):
          """
          Callback: Handles incoming messages with memory and AI.
          """
          try:
               msg_type = message.get("type")
               payload = message.get("payload", {})
               context_dict = message.get("context", {})

               # Identificer kilde
               channel_id = context_dict.get("channel_id", "unknown")
               user_id = context_dict.get("user_id", "unknown")
               adapter_name = payload.get("metadata", {}).get("source", "unknown")

               logger.info(f"📨 Inbound ({msg_type}) from {user_id} via {adapter_name}")

               # Analytics Tracking
               await analytics.track_interaction(adapter_name, user_id, msg_type, metadata=payload.get("metadata"))

               # If it is a chat message
               if msg_type == "user_message":
                    user_text = payload.get("content")

                    # 1. Get Context & History
                    # We use adapter_name + channel_id as a unique key for the conversation
                    conversation_id = conversation_manager.get_conversation_id(user_id, channel_id, adapter_name)
                    history = conversation_manager.get_history(conversation_id)

                    # 2. Build Prompt with History (Memory Injection)
                    # Since our Runtime takes a string, we build the history into the prompt
                    full_prompt = ""

                    if history:
                         full_prompt += "Previous conversation history:\n"
                         for msg in history:
                              role_name = "User" if msg["role"] == "user" else "AI"
                              full_prompt += f"{role_name}: {msg['content']}\n"
                              full_prompt += "\nCurrent message:\n"

                    full_prompt += user_text

                    # 3. Analyze Sentiment (Just for log)
                    sentiment = await ai_enhancer.analyze_sentiment(user_text)
                    logger.info(f"Sentiment: {sentiment}")

                    # 4. Run through LLM Runtime
                    logger.info("Thinking...")
                    raw_response = await self.runtime.process_message(full_prompt)

                    # 5. Optimize Response (Formatting/Tone)
                    final_response = await ai_enhancer.enhance_response(raw_response)

                    logger.info(f"🤖 Response: {final_response[:50]}...")

                    # 6. Save to Memory
                    conversation_manager.add_message(conversation_id, "user", user_text)
                    conversation_manager.add_message(conversation_id, "assistant", final_response)

                    # 7. Send a reply back
                    await self._send_reply(context_dict, final_response, adapter_name)

               # If it is a reset message
               elif msg_type == "reset":
                    conversation_manager.clear_history(conversation_id)
                    await self._send_reply(context_dict, "Chat has been reset.", adapter_name)

          except Exception as e:
               logger.error(f"Error handling inbound message: {e}")

     # Helper function
     async def _send_reply(self, context_dict: Dict, content: str, adapter_name: str):
          """Hjælpefunktion til at finde den rette adapter og svare"""
          target_adapter = self.active_adapters.get(adapter_name)

          # Fallback logic to find the adapter
          if not target_adapter:
               # Try guessing from channel ID or context
               for name, adapter in self.active_adapters.items():
                    if name in str(context_dict) or name == adapter_name:
                         target_adapter = adapter
                         break

          if target_adapter:
               ctx = AdapterContext(**context_dict)
               await target_adapter.send_message(ctx, {"content": content})
          else:
               logger.warning(f"Could not find adapter '{adapter_name}' to reply via.")

     # Shutdown
     async def shutdown(self):
          logger.info("Shutting down...")
          for name, adapter in self.active_adapters.items():
               await adapter.stop()
          self.running = False

if __name__ == "__main__":
     # Load environment variables
     load_dotenv(os.path.join(os.path.dirname(__file__), "runtime", "llm_tool_calling", ".env"))

     orchestrator = LocalOrchestrator()
     try:
          asyncio.run(orchestrator.start())
     except KeyboardInterrupt:
          print("\nGoodbye!")
