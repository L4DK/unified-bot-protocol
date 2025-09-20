import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from adapters.slack.slack_adapter import SlackAdapter


@pytest.fixture
def sample_config():
    return {"bot_token": "xoxb-fake-bot-token", "app_token": "xapp-fake-app-token"}


@pytest.mark.asyncio
async def test_adapter_initialization(sample_config):
    adapter = SlackAdapter(sample_config)
    assert adapter.platform_name == "slack"
    assert "slack.message.send" in adapter.capabilities
    assert adapter.metadata.platform == "slack"
    assert adapter.metadata.version == "1.0.0"


@pytest.mark.asyncio
async def test_handle_slack_event_acknowledges_and_processes(sample_config):
    adapter = SlackAdapter(sample_config)
    adapter.handle_platform_event = AsyncMock()

    class DummyRequest:
        type = "events_api"
        envelope_id = "env123"
        payload = {
            "event": {
                "type": "message",
                "channel": "C123",
                "user": "U123",
                "text": "Hello",
                "ts": "1234567890.1234",
            }
        }

    dummy_req = DummyRequest()
    dummy_client = MagicMock()
    dummy_client.send_socket_mode_response = AsyncMock()

    await adapter._handle_slack_event(dummy_client, dummy_req)

    dummy_client.send_socket_mode_response.assert_awaited_once()
    adapter.handle_platform_event.assert_awaited_once_with(dummy_req.payload["event"])


@pytest.mark.asyncio
async def test_handle_platform_event_message(sample_config):
    adapter = SlackAdapter(sample_config)
    adapter.message_queue = asyncio.Queue()

    event = {
        "type": "message",
        "channel": "C123",
        "user": "U123",
        "text": "Test message",
        "ts": "1234567890.1234",
    }

    await adapter.handle_platform_event(event)
    queued = await adapter.message_queue.get()
    assert queued["event"]["event_type"] == "slack.message.received"
    assert queued["event"]["platform"] == "slack"
    assert queued["event"]["data"]["text"] == "Test message"


@pytest.mark.asyncio
async def test_handle_command_send_message_success(sample_config):
    adapter = SlackAdapter(sample_config)
    adapter.slack_client = MagicMock()
    adapter.slack_client.chat_postMessage = AsyncMock(
        return_value=MagicMock(data={"ok": True})
    )

    command = {
        "command_name": "slack.message.send",
        "parameters": {"channel": "C123", "text": "Hello"},
    }

    response = await adapter.handle_command(command)
    assert response["status"] == "SUCCESS"
    assert response["result"]["ok"] is True


@pytest.mark.asyncio
async def test_handle_command_update_message_success(sample_config):
    adapter = SlackAdapter(sample_config)
    adapter.slack_client = MagicMock()
    adapter.slack_client.chat_update = AsyncMock(
        return_value=MagicMock(data={"ok": True})
    )

    command = {
        "command_name": "slack.message.update",
        "parameters": {
            "channel": "C123",
            "message_ts": "12345.6789",
            "text": "Updated text",
        },
    }

    response = await adapter.handle_command(command)
    assert response["status"] == "SUCCESS"
    assert response["result"]["ok"] is True


@pytest.mark.asyncio
async def test_handle_command_add_reaction_success(sample_config):
    adapter = SlackAdapter(sample_config)
    adapter.slack_client = MagicMock()
    adapter.slack_client.reactions_add = AsyncMock(
        return_value=MagicMock(data={"ok": True})
    )

    command = {
        "command_name": "slack.reaction.add",
        "parameters": {
            "channel": "C123",
            "message_ts": "12345.6789",
            "reaction": "thumbsup",
        },
    }

    response = await adapter.handle_command(command)
    assert response["status"] == "SUCCESS"
    assert response["result"]["ok"] is True


@pytest.mark.asyncio
async def test_handle_command_unknown_command(sample_config):
    adapter = SlackAdapter(sample_config)

    command = {"command_name": "slack.unknown.command", "parameters": {}}

    response = await adapter.handle_command(command)
    assert response["status"] == "ERROR"
    assert "Unknown command" in response["error_details"]
