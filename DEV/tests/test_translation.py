"""
FilePath: "/DEV/tests/test_translation.py"
Description: Tests the UnifiedMessage translation logic in ConsoleAdapter.
Usage: python tests/test_translation.py
"""
import asyncio
import sys
import os

# Fix path to include DEV root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.console.console_adapter import ConsoleAdapter
from orchestrator.models import UnifiedMessage, MessageType, Participant

async def test_console_translation():
    print("--- STARTING TRANSLATION TEST ---")

    # Setup
    adapter = ConsoleAdapter({"adapter_id": "test_console", "console": {"username": "Tester"}})

    # 1. Test: Platform -> Unified (Input)
    print("\n1. Testing to_unified (Input)...")
    raw_input = {"content": "Hello World", "user_id": "mike"}
    unified_msg = await adapter.to_unified(raw_input)

    if unified_msg and unified_msg.text == "Hello World" and unified_msg.sender.id == "mike":
        print(f"   [SUCCESS] Converted Dict -> UnifiedMessage correctly.")
        print(f"   - Text: {unified_msg.text}")
        print(f"   - Sender: {unified_msg.sender.name}")
    else:
        print(f"   [FAILED] Got: {unified_msg}")

    # 2. Test: Unified -> Platform (Output)
    print("\n2. Testing to_platform (Output)...")
    msg_to_send = UnifiedMessage(
        type=MessageType.TEXT,
        text="This is a reply from the bot",
        sender=Participant(id="bot", platform="internal", role="bot", name="UBP Bot"),
        recipient=Participant(id="mike", platform="console", role="user")
    )

    platform_output = await adapter.to_platform(msg_to_send)

    if platform_output.get("content") == "This is a reply from the bot":
        print(f"   [SUCCESS] Converted UnifiedMessage -> Dict correctly.")
        print(f"   - Payload: {platform_output}")
    else:
        print(f"   [FAILED] Got: {platform_output}")

    # 3. Test: High-Level Send (Integration)
    print("\n3. Testing send_unified_message (Integration)...")
    await adapter.send_unified_message(msg_to_send)
    print("   [SUCCESS] If you see the yellow bot message above, it worked.")

    print("\n--- TEST COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(test_console_translation())
