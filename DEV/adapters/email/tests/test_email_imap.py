# test_email_imap.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from email.message import EmailMessage
from email_imap import IMAPEmailAdapter


@pytest.fixture
def config():
    return {
        "host": "imap.example.com",
        "username": "user@example.com",
        "password": "password",
        "security_key": "testkey",
        "poll_interval": 0.1,
        "use_ssl": True,
        "mailbox": "INBOX",
    }


@pytest.mark.asyncio
@patch("email_imap.imaplib.IMAP4_SSL")
async def test_poll_mailbox_success(mock_imap, config):
    adapter = IMAPEmailAdapter(config)
    mock_mail = MagicMock()
    mock_imap.return_value = mock_mail
    mock_mail.search.return_value = ("OK", [b"1 2"])
    mock_mail.fetch.return_value = ("OK", [(b"1 (RFC822 {342}", b"RawEmailBytes")])
    mock_mail.store.return_value = ("OK", None)
    mock_mail.logout.return_value = None

    # Patch _parse_email to return a dummy parsed email
    adapter._parse_email = MagicMock(
        return_value={"date": "Thu, 1 Jan 1970 00:00:00 +0000"}
    )

    # Patch send_event_to_orchestrator to async mock
    adapter.send_event_to_orchestrator = AsyncMock()

    await adapter._poll_mailbox()

    adapter._parse_email.assert_called()
    adapter.send_event_to_orchestrator.assert_awaited()
    mock_mail.store.assert_called()
    mock_mail.logout.assert_called()


@pytest.mark.asyncio
@patch("email_imap.imaplib.IMAP4_SSL")
async def test_poll_mailbox_search_fail(mock_imap, config):
    adapter = IMAPEmailAdapter(config)
    mock_mail = MagicMock()
    mock_imap.return_value = mock_mail
    mock_mail.search.return_value = ("NO", [])
    mock_mail.logout.return_value = None

    await adapter._poll_mailbox()

    mock_mail.logout.assert_called()


def test_parse_email_simple_text(config):
    adapter = IMAPEmailAdapter(config)
    msg = EmailMessage()
    msg.set_content("Hello World")
    msg["Subject"] = "Test"
    msg["From"] = "sender@example.com"
    msg["To"] = "receiver@example.com"
    msg["Date"] = "Thu, 1 Jan 1970 00:00:00 +0000"

    parsed = adapter._parse_email(msg)
    assert parsed["subject"] == "Test"
    assert parsed["from"] == "sender@example.com"
    assert parsed["to"] == "receiver@example.com"
    assert parsed["body"] == "Hello World\n"
    assert parsed["attachments"] == []


@pytest.mark.asyncio
@patch("email_imap.IMAPEmailAdapter.orchestrator_ws", new_callable=AsyncMock)
async def test_send_event_to_orchestrator_success(mock_ws, config):
    adapter = IMAPEmailAdapter(config)
    adapter.orchestrator_ws = mock_ws
    adapter.security = MagicMock()
    adapter.security.sign_message.return_value = "signature"
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()

    event = {"event_type": "email.imap.message.received"}
    await adapter.send_event_to_orchestrator(event)

    mock_ws.send.assert_awaited()
    adapter.metrics.increment.assert_called_with("imap_email.events.sent")
    adapter.logger.info.assert_called()


@pytest.mark.asyncio
async def test_send_event_to_orchestrator_no_ws(config):
    adapter = IMAPEmailAdapter(config)
    adapter.orchestrator_ws = None
    adapter.logger = MagicMock()
    adapter.metrics = MagicMock()

    event = {"event_type": "email.imap.message.received"}
    await adapter.send_event_to_orchestrator(event)

    adapter.logger.warning.assert_called()
    adapter.metrics.increment.assert_called_with("imap_email.events.dropped")
