import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from adapters.discord.discord_platform_adapter import (
    DiscordPlatformAdapter,
    DiscordMessage,
    DiscordContext,
)
from ubp_core.message_schema import MessageType, ContentType


@pytest.fixture
def sample_config():
    return {
        "discord": {
            "bot_token": "fake_token",
            "application_id": "1234567890",
            "guild_ids": [],
            "command_prefix": "!",
        },
        "ubp": {
            "orchestrator_url": "ws://localhost:8080/ws/adapters",
            "adapter_id": "discord_adapter_test",
            "security_key": "test_security_key",
        },
    }


@pytest.mark.asyncio
async def test_adapter_initialization(sample_config):
    adapter = DiscordPlatformAdapter(sample_config)
    assert adapter.bot_token == "fake_token"
    assert adapter.adapter_id == "discord_adapter_test"
    assert adapter.bot.command_prefix == "!"
    assert adapter.orchestrator_url == "ws://localhost:8080/ws/adapters"


@pytest.mark.asyncio
async def test_discord_message_to_ubp_conversion(sample_config):
    adapter = DiscordPlatformAdapter(sample_config)
    discord_msg = DiscordMessage(
        content="Hello World",
        author_id=111,
        channel_id=222,
        guild_id=333,
        message_id=444,
        timestamp=datetime.now(timezone.utc),
        attachments=[],
        embeds=[],
        reactions=[],
    )
    ubp_msg = await adapter._discord_message_to_ubp(discord_msg)
    assert ubp_msg.message_type == MessageType.USER_MESSAGE
    assert ubp_msg.content["text"] == "Hello World"
    assert ubp_msg.platform == "discord"
    assert ubp_msg.adapter_id == adapter.adapter_id


@pytest.mark.asyncio
async def test_send_to_orchestrator_logs_error(sample_config):
    adapter = DiscordPlatformAdapter(sample_config)
    adapter.orchestrator_ws = None  # No connection
    ubp_msg = await adapter._discord_message_to_ubp(
        DiscordMessage(
            content="Test",
            author_id=1,
            channel_id=1,
            guild_id=1,
            message_id=1,
            timestamp=datetime.now(timezone.utc),
        )
    )
    # Should log warning and not raise
    await adapter._send_to_orchestrator(ubp_msg)


@pytest.mark.asyncio
async def test_handle_orchestrator_command_unknown(sample_config):
    adapter = DiscordPlatformAdapter(sample_config)
    ubp_msg = MagicMock()
    ubp_msg.content = {"command": "unknown_command"}
    with patch.object(adapter.logger, "warning") as mock_warn:
        await adapter._handle_orchestrator_command(ubp_msg)
        mock_warn.assert_called_with(
            "Unknown command from orchestrator: unknown_command"
        )


@pytest.mark.asyncio
async def test_rate_limiter_wait(monkeypatch):
    from adapters.discord.discord_platform_adapter import DiscordRateLimiter

    rate_limiter = DiscordRateLimiter()
    # Simulate global rate limit active
    rate_limiter.global_rate_limit = True
    rate_limiter.global_reset_time = asyncio.get_event_loop().time() + 0.1
    await rate_limiter.wait_if_rate_limited("test_endpoint")


@pytest.mark.asyncio
async def test_interaction_handler_register_and_handle(sample_config):
    adapter = DiscordPlatformAdapter(sample_config)
    handler = adapter.interaction_handler

    called = False

    async def dummy_command(interaction):
        nonlocal called
        called = True

    handler.register_command("testcmd", dummy_command)

    class DummyInteraction:
        type = 1  # application_command
        data = {"name": "testcmd"}
        response = MagicMock()
        response.is_done = lambda: False

        async def response_send_message(self, *args, **kwargs):
            pass

        response.send_message = response_send_message

    interaction = DummyInteraction()
    await handler.handle_interaction(interaction)
    assert called
