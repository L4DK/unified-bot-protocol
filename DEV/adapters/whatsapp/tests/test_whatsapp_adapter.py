import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from adapters.whatsapp.adapter import WhatsAppAdapter


@pytest.fixture
def sample_config():
    return {"phone_number_id": "1234567890", "access_token": "fake_access_token"}


@pytest.mark.asyncio
async def test_adapter_initialization(sample_config):
    adapter = WhatsAppAdapter(sample_config)
    assert adapter.platform_name == "whatsapp"
    assert "whatsapp.message.send" in adapter.capabilities
    assert adapter.metadata.platform == "whatsapp"
    assert adapter.metadata.version == "1.0.0"
    assert adapter.api_url.endswith(sample_config["phone_number_id"])


@pytest.mark.asyncio
async def test_handle_platform_event_puts_event_in_queue(sample_config):
    adapter = WhatsAppAdapter(sample_config)
    adapter.message_queue = asyncio.Queue()

    event = {
        "messages": [
            {
                "timestamp": "1234567890",
                "from": "12345",
                "type": "text",
                "text": {"body": "Hello WhatsApp"},
            }
        ]
    }

    await adapter.handle_platform_event(event)
    queued = await adapter.message_queue.get()
    assert queued["event"]["event_type"] == "whatsapp.message.received"
    assert queued["event"]["platform"] == "whatsapp"
    assert queued["event"]["data"]["text"] == "Hello WhatsApp"


@pytest.mark.asyncio
async def test_handle_command_send_message_success(sample_config):
    adapter = WhatsAppAdapter(sample_config)
    adapter.http_session = AsyncMock()

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"messages": ["msgid123"]})
    adapter.http_session.post.return_value.__aenter__.return_value = mock_response

    command = {
        "command_name": "whatsapp.message.send",
        "parameters": {"to": "12345", "text": "Hello"},
    }

    response = await adapter.handle_command(command)
    assert response["status"] == "SUCCESS"
    assert "messages" in response["result"]


@pytest.mark.asyncio
async def test_handle_command_template_message_success(sample_config):
    adapter = WhatsAppAdapter(sample_config)
    adapter.http_session = AsyncMock()

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"messages": ["template_msgid"]})
    adapter.http_session.post.return_value.__aenter__.return_value = mock_response

    command = {
        "command_name": "whatsapp.message.template",
        "parameters": {
            "to": "12345",
            "template": {"name": "hello_world", "language": {"code": "en_US"}},
        },
    }

    response = await adapter.handle_command(command)
    assert response["status"] == "SUCCESS"
    assert "messages" in response["result"]


@pytest.mark.asyncio
async def test_handle_command_unknown_command(sample_config):
    adapter = WhatsAppAdapter(sample_config)
    adapter.http_session = AsyncMock()

    command = {"command_name": "whatsapp.unknown.command", "parameters": {}}

    response = await adapter.handle_command(command)
    assert response["status"] == "ERROR"
    assert "Unknown command" in response["error_details"]


@pytest.mark.asyncio
async def test_handle_command_api_error(sample_config):
    adapter = WhatsAppAdapter(sample_config)
    adapter.http_session = AsyncMock()

    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.json = AsyncMock(return_value={"error": "Bad Request"})
    adapter.http_session.post.return_value.__aenter__.return_value = mock_response

    command = {
        "command_name": "whatsapp.message.send",
        "parameters": {"to": "12345", "text": "Hello"},
    }

    response = await adapter.handle_command(command)
    assert response["status"] == "ERROR"
    assert "WhatsApp API error" in response["error_details"]


@pytest.mark.asyncio
async def test_setup_platform(sample_config):
    adapter = WhatsAppAdapter(sample_config)
    adapter.http_session = AsyncMock()

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"messages": ["msgid123"]})
    adapter.http_session.post.return_value.__aenter__.return_value = mock_response

    await adapter._setup_platform()
    adapter.http_session.post.assert_called_once()

    assert adapter.api_url == "https://graph.facebook.com/v15.0/1234567890/messages"
    assert adapter.access_token == "fake_access_token"
    assert adapter.http_session is not None

    assert adapter.metadata.platform == "whatsapp"
    assert adapter.metadata.version == "1.0.0"

    assert adapter.metadata.features == ["templates", "media", "location", "interactive_buttons"]

    assert adapter.metadata.max_message_length == 4096
    assert adapter.metadata.supported_media_types == ["image", "video", "audio", "document"]
    assert adapter.metadata.rate_limits == {"messages_per_day": 1000}


if __name__ == "__main__":
    pytest.main()

    # Run FastAPI server
    uvicorn.run(adapter.app, host="0.0.0.0", port=8080)
