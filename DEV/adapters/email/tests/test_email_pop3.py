# test_email_pop3.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from email.message import EmailMessage
from email_pop3 import POP3EmailAdapter


@pytest.fixture
def config():
    return {
        "host": "pop3.example.com",
        "username": "user@example.com",
        "password": "password",
        "security_key": "testkey",
        "poll_interval": 0.1,
        "use_ssl": True,
    }


@pytest.mark.asyncio
@patch("email_pop3.poplib.POP3_SSL")
async def test_poll_mailbox_success(mock_pop3, config):
    adapter = POP3EmailAdapter(config)
    mock_mail = MagicMock()
    mock_pop3.return_value = mock_mail
    mock_mail.list.return_value = ("OK", [b"1 2"])
    mock_mail.retr.return_value = ("OK", [b"line1", b"line2"])
    mock_mail.dele.return_value = ("OK", None)
    mock_mail.quit.return_value = None

    adapter._parse_email = MagicMock(
        return_value={"date": "Thu, 1 Jan 1970 00:00:00 +0000"}
    )
    adapter.send_event_to_orchestrator = AsyncMock()

    await adapter._poll_mailbox()

    adapter._parse_email.assert_called()
    adapter.send_event_to_orchestrator.assert_awaited()
    mock_mail.dele.assert_called()
    mock_mail.quit.assert_called()


def test_parse_email_simple_text(config):
    adapter = POP3EmailAdapter(config)
    msg = EmailMessage()
    msg.set_content("Hello POP3")
    msg["Subject"] = "Test POP3"
    msg["From"] = "sender@example.com"
    msg["To"] = "receiver@example.com"
    msg["Date"] = "Thu, 1 Jan 1970 00:00:00 +0000"

    parsed = adapter._parse_email(msg)
    assert parsed["subject"] == "Test POP3"
    assert parsed["from"] == "sender@example.com"
    assert parsed["to"] == "receiver@example.com"
    assert parsed["body"] == "Hello POP3\n"
    assert parsed["attachments"] == []


@pytest.mark.asyncio
@patch("email_pop3.POP3EmailAdapter.orchestrator_ws", new_callable=AsyncMock)
async def test_send_event_to_orchestrator_success(mock_ws, config):
    adapter = POP3EmailAdapter(config)
    adapter.orchestrator_ws = mock_ws
    adapter.security = MagicMock()
    adapter.security.sign_message.return_value = "signature"
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()

    event = {"event_type": "email.pop3.message.received"}
    await adapter.send_event_to_orchestrator(event)

    mock_ws.send.assert_awaited()
    adapter.metrics.increment.assert_called_with("pop3_email.events.sent")
    adapter.logger.info.assert_called()


@pytest.mark.asyncio
async def test_send_event_to_orchestrator_no_ws(config):
    adapter = POP3EmailAdapter(config)
    adapter.orchestrator_ws = None
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()

    event = {"event_type": "email.pop3.message.received"}
    await adapter.send_event_to_orchestrator(event)

    adapter.logger.warning.assert_called()
    adapter.metrics.increment.assert_called_with("pop3_email.events.dropped")
