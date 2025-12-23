"""
FilePath: "/adapters/console/console_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: Console/CLI Adapter
Description: Allows chatting with the bot directly via terminal stdin/stdout.
Author: "Michael Landbo"
"""

import asyncio
import sys
from typing import Dict, Any

# Import Base Adapter Classes
from adapters.base_adapter import (
     PlatformAdapter,
     AdapterCapabilities,
     AdapterMetadata,
     AdapterContext,
     PlatformCapability,
     SendResult,
     SimpleSendResult,
     AdapterStatus
)

class ConsoleAdapter(PlatformAdapter):
     """
     Simpel adapter der læser fra tastaturet og skriver til skærmen.
     Perfekt til lokal test af LLM og tools uden netværkskald.
     """

     def __init__(self, config: Dict[str, Any]):
          super().__init__(config)
          self.username = config.get("console", {}).get("username", "User")
          self._listen_task = None

     @property
     def platform_name(self) -> str:
          return "console"

     @property
     def capabilities(self) -> AdapterCapabilities:
          return AdapterCapabilities(
               supported_capabilities={PlatformCapability.SEND_MESSAGE},
               max_message_length=10000,
               rate_limits={"message.send": 1000}
          )

     @property
     def metadata(self) -> AdapterMetadata:
          return AdapterMetadata(
               platform="console",
               display_name="Terminal CLI",
               version="1.0.0",
               author="Michael Landbo",
               description="Local command line interface for testing",
               supports_real_time=True
          )

     async def _setup_platform(self) -> None:
          """Starter input loopet i en baggrundstråd"""
          print(f"\n--- Console Adapter Started. Chat as '{self.username}' ---")
          print("Type your message and press Enter. (Type 'exit' to quit)\n")

          # Vi bruger run_in_executor til input(), da det er blokerende
          self._listen_task = asyncio.create_task(self._input_loop())

     async def stop(self) -> None:
          if self._listen_task:
               self._listen_task.cancel()
          await super().stop()

     async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
          """Printer svaret fra AI til terminalen"""
          content = message.get("content", "")
          # Brug farver hvis muligt, ellers bare tekst
          try:
               from termcolor import colored
               print(colored(f"\n🤖 Bot: {content}\n", "yellow"))
          except ImportError:
               print(f"\n🤖 Bot: {content}\n")

          return SimpleSendResult(True)

     async def _input_loop(self):
          loop = asyncio.get_running_loop()
          while not self._shutdown_event.is_set():
               try:
                    # Kør input() i en thread så vi ikke blokerer asyncio loopet
                    user_input = await loop.run_in_executor(None, sys.stdin.readline)
                    user_input = user_input.strip()

                    if not user_input: continue
                    if user_input.lower() in ["exit", "quit"]:
                         print("Exiting console...")
                         self._shutdown_event.set()
                         break

                    # Send til Orchestrator (Main.py)
                    context = AdapterContext(
                         tenant_id="local",
                         user_id="console_user",
                         channel_id="console", # Vigtigt: Matcher navnet i main.py
                         extras={"username": self.username}
                    )

                    payload = {
                         "type": "user_message",
                         "content": user_input,
                         "metadata": {"source": "console"}
                    }

                    if self.connected:
                         # Vi kalder den monkey-patchede metode fra main.py
                         await self._send_to_orchestrator({
                         "type": "user_message",
                         "context": context.to_dict(),
                         "payload": payload
                         })

               except asyncio.CancelledError:
                    break
               except Exception as e:
                    print(f"Console Input Error: {e}")

     async def handle_platform_event(self, event): pass
     async def handle_command(self, command): return {}
