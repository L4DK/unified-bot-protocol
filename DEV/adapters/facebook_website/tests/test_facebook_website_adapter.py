import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from facebook_website_adapter import FacebookWebsiteAdapter


@pytest.fixture
def config():
    return {
        "app_id": "test_app_id",
        "app_secret": "test_app_secret",
        "page_access_token": "test_page_token",
        "verify_token": "test_verify_token",
        "security_key": "test_security_key",
    }


@pytest.mark.asyncio
async def test_webhook_verification_success(config):
    adapter = FacebookWebsiteAdapter(config)
    request = MagicMock()
    request.rel_url.query = {
        "hub.mode": "subscribe",
        "hub.verify_token": config["verify_token"],
        "hub.challenge": "challenge_code",
    }
    response = await adapter._handle_verification(request)
    assert response.status == 200
    text = await response.text()
    assert text == "challenge_code"


@pytest.mark.asyncio
async def test_webhook_verification_failure(config):
    adapter = FacebookWebsiteAdapter(config)
    request = MagicMock()
    request.rel_url.query = {
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token",
        "hub.challenge": "challenge_code",
    }
    response = await adapter._handle_verification(request)
    assert response.status == 403


@pytest.mark.asyncio
async def test_signature_verification(config):
    adapter = FacebookWebsiteAdapter(config)
    payload = b'{"test": "data"}'
    valid_signature = (
        "sha1="
        + hmac.new(
            config["app_secret"].encode(), msg=payload, digestmod=hashlib.sha1
        ).hexdigest()
    )
    assert adapter._verify_signature(payload, valid_signature) is True
    assert adapter._verify_signature(payload, "sha1=invalid") is False
    assert adapter._verify_signature(payload, None) is False


@pytest.mark.asyncio
async def test_handle_platform_event_queueing(monkeypatch, config):
    adapter = FacebookWebsiteAdapter(config)
    adapter.send_event_to_orchestrator = AsyncMock()

    event = {
        "event_type": "login_status",
        "timestamp": 1234567890,
        "user_id": "user123",
        "status": "connected",
        "auth_response": {"accessToken": "token"},
    }

    await adapter._handle_platform_event(event)
    queued_event = await adapter.message_queue.get()
    assert queued_event["event_type"] == "fb_website.login.status"


@pytest.mark.asyncio
@patch("facebook_website_adapter.ClientSession.post")
async def test_handle_command_send_success(mock_post, config):
    adapter = FacebookWebsiteAdapter(config)
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"message_id": "123"})
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value.__aenter__.return_value = mock_response

    command = {
        "command_name": "fb_website.customer_chat.send",
        "parameters": {"recipient_id": "user123", "message": {"text": "Hello"}},
    }

    result = await adapter.handle_command(command)
    assert result["status"] == "SUCCESS"
    adapter.metrics.increment.assert_called_with("facebook_website.messages.sent")


@pytest.mark.asyncio
@patch("facebook_website_adapter.ClientSession.post")
async def test_handle_command_send_failure(mock_post, config):
    adapter = FacebookWebsiteAdapter(config)
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()

    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.json = AsyncMock(return_value={"error": "Bad Request"})
    mock_response.raise_for_status.side_effect = Exception("Bad Request")
    mock_post.return_value.__aenter__.return_value = mock_response

    command = {
        "command_name": "fb_website.customer_chat.send",
        "parameters": {"recipient_id": "user123", "message": {"text": "Hello"}},
    }

    result = await adapter.handle_command(command)
    assert result["status"] == "ERROR"
    adapter.metrics.increment.assert_called_with("facebook_website.commands.failed")


@pytest.mark.asyncio
async def test_handle_command_unknown_command(config):
    adapter = FacebookWebsiteAdapter(config)
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()

    command = {"command_name": "unknown_command", "parameters": {}}

    result = await adapter.handle_command(command)
    assert result["status"] == "ERROR"
    adapter.logger.exception.assert_called()
