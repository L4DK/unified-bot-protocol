# test_email_smtp.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from email_smtp import SMTPEmailAdapter
from adapters.email.base import SimpleSendResult


@pytest.fixture
def config():
    return {
        "host": "smtp.example.com",
        "username": "user@example.com",
        "password": "password",
        "security_key": "testkey",
        "use_tls": True,
        "from": "sender@example.com",
    }


@pytest.mark.asyncio
@patch("email_smtp.aiosmtplib.send", new_callable=AsyncMock)
async def test_send_message_plain_text(mock_send, config):
    adapter = SMTPEmailAdapter(config)
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()
    adapter.security = MagicMock()
    adapter.security.sign_message.return_value = "signature"

    message = {
        "to": "receiver@example.com",
        "subject": "Test Email",
        "content": "Hello SMTP",
    }

    result = await adapter.send_message(None, message)

    mock_send.assert_awaited()
    adapter.metrics.increment.assert_called_with("smtp_email.messages.sent")
    assert result.success is True


@pytest.mark.asyncio
@patch("email_smtp.aiosmtplib.send", new_callable=AsyncMock)
async def test_send_message_html_and_attachments(mock_send, config):
    adapter = SMTPEmailAdapter(config)
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()
    adapter.security = MagicMock()
    adapter.security.sign_message.return_value = "signature"

    message = {
        "to": ["receiver@example.com"],
        "subject": "Test Email HTML",
        "content": "Hello SMTP",
        "html_content": "<p>Hello <b>SMTP</b></p>",
        "attachments": [
            {
                "filename": "test.txt",
                "content": b"Test content",
                "mime_type": "text/plain",
            }
        ],
    }

    result = await adapter.send_message(None, message)

    mock_send.assert_awaited()
    adapter.metrics.increment.assert_called_with("smtp_email.messages.sent")
    assert result.success is True


@pytest.mark.asyncio
@patch("email_smtp.aiosmtplib.send", new_callable=AsyncMock)
async def test_send_message_failure(mock_send, config):
    adapter = SMTPEmailAdapter(config)
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()
    adapter.security = MagicMock()
    adapter.security.sign_message.return_value = "signature"

    mock_send.side_effect = Exception("SMTP failure")

    message = {
        "to": "receiver@example.com",
        "subject": "Test Email",
        "content": "Hello SMTP",
    }

    result = await adapter.send_message(None, message)

    mock_send.assert_awaited()
    adapter.metrics.increment.assert_called_with("smtp_email.send_failures")
    assert result.success is False


@pytest.mark.asyncio
async def test_send_message_no_recipient(config):
    adapter = SMTPEmailAdapter(config)
    adapter.logger = MagicMock()

    message = {"subject": "No recipient", "content": "Hello"}

    result = await adapter.send_message(None, message)
    assert result.success is False
    adapter.logger.error.assert_called()
