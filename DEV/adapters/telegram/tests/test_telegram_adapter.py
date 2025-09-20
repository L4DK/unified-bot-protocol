import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from telegram_adapter import TelegramAdapter, TelegramConfig, TelegramUpdateType


@pytest.fixture
def config():
    return TelegramConfig(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        webhook_url="https://example.com/webhook/telegram",
        webhook_secret="test_secret",
        security_key="test_security_key",
    )


@pytest.fixture
async def adapter(config):
    adapter = TelegramAdapter(config)
    adapter.session = AsyncMock()
    yield adapter
    await adapter.close()


@pytest.mark.asyncio
async def test_convert_message_to_ubp_event(adapter):
    update = {
        "update_id": 123,
        "message": {
            "message_id": 456,
            "from": {"id": 789, "username": "testuser"},
            "chat": {"id": 789, "type": "private"},
            "date": 1234567890,
            "text": "Hello, world!",
        },
    }

    event = await adapter._convert_to_ubp_event(update, TelegramUpdateType.MESSAGE)

    assert event["event_type"] == "telegram.message.received"
    assert event["data"]["text"] == "Hello, world!"
    assert event["data"]["message_id"] == 456


@pytest.mark.asyncio
async def test_send_message_command(adapter):
    adapter._api_request = AsyncMock(return_value={"message_id": 123})

    command = {
        "command_name": "telegram.message.send",
        "parameters": {"chat_id": 789, "text": "Test message"},
    }

    result = await adapter.handle_command(command)

    assert result["status"] == "SUCCESS"
    adapter._api_request.assert_called_with(
        "sendMessage", {"chat_id": 789, "text": "Test message"}
    )


@pytest.mark.asyncio
async def test_callback_query_handling(adapter):
    update = {
        "update_id": 123,
        "callback_query": {
            "id": "callback123",
            "from": {"id": 789, "username": "testuser"},
            "data": "button_clicked",
            "message": {"message_id": 456, "chat": {"id": 789}},
        },
    }

    event = await adapter._convert_to_ubp_event(
        update, TelegramUpdateType.CALLBACK_QUERY
    )

    assert event["event_type"] == "telegram.callback_query.received"
    assert event["data"]["data"] == "button_clicked"


@pytest.mark.asyncio
async def test_inline_query_handling(adapter):
    update = {
        "update_id": 123,
        "inline_query": {
            "id": "inline123",
            "from": {"id": 789, "username": "testuser"},
            "query": "search term",
            "offset": "",
        },
    }

    event = await adapter._convert_to_ubp_event(update, TelegramUpdateType.INLINE_QUERY)

    assert event["event_type"] == "telegram.inline_query.received"
    assert event["data"]["query"] == "search term"


@pytest.mark.asyncio
async def test_api_request_retry_on_rate_limit(adapter):
    # Mock rate limit response
    rate_limit_response = {
        "ok": False,
        "error_code": 429,
        "description": "Too Many Requests",
        "parameters": {"retry_after": 1},
    }

    success_response = {"ok": True, "result": {"message_id": 123}}

    mock_response = AsyncMock()
    mock_response.json.side_effect = [rate_limit_response, success_response]
    adapter.session.post.return_value.__aenter__.return_value = mock_response

    with patch("asyncio.sleep") as mock_sleep:
        result = await adapter._api_request(
            "sendMessage", {"chat_id": 123, "text": "test"}
        )

        assert result == {"message_id": 123}
        mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_webhook_secret_verification(adapter):
    from aiohttp import web

    # Mock request with correct secret
    request = MagicMock()
    request.headers = {"X-Telegram-Bot-Api-Secret-Token": "test_secret"}
    request.read = AsyncMock(return_value=b'{"update_id": 123}')

    response = await adapter._handle_webhook(request)
    assert response.status == 200


@pytest.mark.asyncio
async def test_webhook_secret_verification_failure(adapter):
    from aiohttp import web

    # Mock request with wrong secret
    request = MagicMock()
    request.headers = {"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"}
    request.read = AsyncMock(return_value=b'{"update_id": 123}')

    response = await adapter._handle_webhook(request)
    assert response.status == 403


@pytest.mark.asyncio
async def test_file_download(adapter):
    file_info = {"file_path": "photos/file_123.jpg"}
    adapter._api_request = AsyncMock(return_value=file_info)

    mock_response = AsyncMock()
    mock_response.content.iter_chunked = AsyncMock(return_value=[b"chunk1", b"chunk2"])
    adapter.session.get.return_value.__aenter__.return_value = mock_response

    with patch("aiofiles.open", create=True) as mock_open:
        mock_file = AsyncMock()
        mock_open.return_value.__aenter__.return_value = mock_file

        result = await adapter.download_file("file123", "/tmp/downloaded_file.jpg")

        assert result == "/tmp/downloaded_file.jpg"
        mock_file.write.assert_called()


@pytest.mark.asyncio
async def test_event_handler_registration(adapter):
    handler_called = False

    async def test_handler(update):
        nonlocal handler_called
        handler_called = True

    adapter.register_handler(TelegramUpdateType.MESSAGE, test_handler)

    update = {
        "update_id": 123,
        "message": {
            "message_id": 456,
            "from": {"id": 789},
            "chat": {"id": 789, "type": "private"},
            "date": 1234567890,
            "text": "Test",
        },
    }

    await adapter._handle_telegram_update(update)
    assert handler_called
