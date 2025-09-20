import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from microsoft_teams_adapter import MicrosoftTeamsAdapter


@pytest.fixture
def config():
    return {
        "tenant_id": "test_tenant",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "bot_app_id": "test_bot_app_id",
        "bot_app_password": "test_bot_app_password",
        "security_key": "test_security_key",
    }


@pytest.mark.asyncio
async def test_get_access_token_success(config):
    adapter = MicrosoftTeamsAdapter(config)
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={"access_token": "fake_token", "expires_in": 3600}
    )
    mock_response.text = AsyncMock(return_value="")

    with patch.object(adapter.session, "post", return_value=mock_response):
        token = await adapter._get_access_token()
        assert token == "fake_token"
        # Second call should return cached token
        token2 = await adapter._get_access_token()
        assert token2 == "fake_token"


@pytest.mark.asyncio
async def test_handle_platform_event_queues_event(config):
    adapter = MicrosoftTeamsAdapter(config)
    event = {
        "type": "message",
        "timestamp": "2025-09-19T12:00:00Z",
        "conversation": {"id": "conv1"},
        "from": {"id": "user1"},
        "text": "Hello",
        "replyToId": None,
    }
    await adapter.handle_platform_event(event)
    queued_event = await adapter.message_queue.get()
    assert queued_event["event_type"] == "teams.message.received"
    assert queued_event["data"]["text"] == "Hello"


@pytest.mark.asyncio
@patch("microsoft_teams_adapter.aiohttp.ClientSession.post")
async def test_handle_command_send_success(mock_post, config):
    adapter = MicrosoftTeamsAdapter(config)
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"id": "msg123"})
    mock_post.return_value.__aenter__.return_value = mock_response

    command = {
        "command_name": "teams.message.send",
        "parameters": {
            "team_id": "team1",
            "channel_id": "channel1",
            "text": "Hello Teams",
        },
    }

    with patch.object(
        adapter, "_get_access_token", return_value=asyncio.Future()
    ) as mock_token:
        mock_token.return_value.set_result("fake_token")
        result = await adapter.handle_command(command)
        assert result["status"] == "SUCCESS"
        adapter.metrics.increment.assert_called_with(
            "microsoft_teams.commands.message_send"
        )


@pytest.mark.asyncio
@patch("microsoft_teams_adapter.aiohttp.ClientSession.post")
async def test_handle_command_failure(mock_post, config):
    adapter = MicrosoftTeamsAdapter(config)
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()

    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.json = AsyncMock(return_value={"error": "Bad Request"})
    mock_post.return_value.__aenter__.return_value = mock_response

    command = {
        "command_name": "teams.message.send",
        "parameters": {
            "team_id": "team1",
            "channel_id": "channel1",
            "text": "Hello Teams",
        },
    }

    with patch.object(
        adapter, "_get_access_token", return_value=asyncio.Future()
    ) as mock_token:
        mock_token.return_value.set_result("fake_token")
        result = await adapter.handle_command(command)
        assert result["status"] == "ERROR"
        adapter.metrics.increment.assert_called_with("microsoft_teams.commands.failed")


@pytest.mark.asyncio
async def test_handle_command_unknown_command(config):
    adapter = MicrosoftTeamsAdapter(config)
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()

    command = {"command_name": "unknown_command", "parameters": {}}

    result = await adapter.handle_command(command)
    assert result["status"] == "ERROR"
    adapter.logger.exception.assert_called()
