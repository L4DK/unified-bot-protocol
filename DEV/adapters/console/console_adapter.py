"""
FilePath: "/DEV/adapters/console/console_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: Console/CLI Adapter
Description: Allows chatting with the bot directly via terminal stdin/stdout.
Author: "Michael Landbo"
"""

import asyncio
import sys
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone

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

# Import Unified Message Models
try:
    from orchestrator.models import UnifiedMessage, MessageType, Participant
except ImportError:
    pass # Håndteres ved runtime

class ConsoleAdapter(PlatformAdapter):
     """
     Simpel adapter der læser fra tastaturet og skriver til skærmen.
     Implementerer nu UnifiedMessage oversættelse.
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
               version="1.1.0",
               author="Michael Landbo",
               description="Local command line interface for testing",
               supports_real_time=True
          )

     # --- TRANSLATION IMPLEMENTATION (NYT) ---

     async def to_unified(self, platform_event: Any) -> Optional[UnifiedMessage]:
          """
          Oversætter Console Input (Dict) -> UnifiedMessage
          """
          if not isinstance(platform_event, dict): return None

          content = platform_event.get("content", "")
          user_id = platform_event.get("user_id", "console_user")

          if not content: return None

          return UnifiedMessage(
               id=str(uuid.uuid4()),
               timestamp=datetime.now(timezone.utc),
               type=MessageType.TEXT,
               text=content,
               sender=Participant(
                    id=user_id,
                    name=self.username,
                    platform="console",
                    role="user"
               ),
               recipient=Participant(
                    id="system",
                    name="System",
                    platform="internal",
                    role="system"
               ),
               metadata={"raw": platform_event}
          )

     async def to_platform(self, unified_msg: UnifiedMessage) -> Dict[str, Any]:
          """
          Oversætter UnifiedMessage -> Console Output (Dict)
          """
          # Simpel tekst repræsentation
          text_content = unified_msg.text or ""

          # Håndter attachments
          if unified_msg.attachments:
               text_content += f" [Attachments: {len(unified_msg.attachments)}]"

          return {
               "content": text_content,
               "sender": unified_msg.sender.name if unified_msg.sender else "Unknown"
          }

     # --- STANDARD ADAPTER METHODS ---

     async def _setup_platform(self) -> None:
          """Starter input loopet i en baggrundstråd"""
          print(f"\n--- Console Adapter Started. Chat as '{self.username}' ---")
          print("Type your message and press Enter. (Type 'exit' to quit)\n")
          self._listen_task = asyncio.create_task(self._input_loop())

     async def stop(self) -> None:
          if self._listen_task:
               self._listen_task.cancel()
          await super().stop()

     async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
          """
          Low-level sender: Printer beskeden til terminalen.
          """
          content = message.get("content", "")
          sender = message.get("sender", "Bot")

          try:
               from termcolor import colored
               print(colored(f"\n🤖 {sender}: {content}\n", "yellow"))
          except ImportError:
               print(f"\n🤖 {sender}: {content}\n")

          return SimpleSendResult(True)

     async def _input_loop(self):
          loop = asyncio.get_running_loop()
          while not self._shutdown_event.is_set():
               try:
                    user_input = await loop.run_in_executor(None, sys.stdin.readline)
                    user_input = user_input.strip()

                    if not user_input: continue
                    if user_input.lower() in ["exit", "quit"]:
                         print("Exiting console...")
                         self._shutdown_event.set()
                         break

                    # Construct raw event
                    raw_event = {
                         "content": user_input,
                         "user_id": "console_user"
                    }

                    # Translate to Unified (Test the logic)
                    unified = await self.to_unified(raw_event)

                    # Her ville vi normalt sende 'unified' til Routeren via WebSocket
                    # For nu simulerer vi bare at vi har modtaget det
                    if self.connected:
                         # Placeholder for sending logic
                         pass

               except asyncio.CancelledError:
                    break
               except Exception as e:
                    print(f"Console Input Error: {e}")

     async def handle_platform_event(self, event): pass
     async def handle_command(self, command): return {}
