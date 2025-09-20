import pytest
import json
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from universal_webhook_adapter import (
    app,
    send_to_orchestrator,
    ip_allowed,
    verify_slack_signature,
)

client = TestClient(app)


@pytest.mark.asyncio
async def test_ip_allowed():
    allowed = ["192.168.1.0/24", "10.0.0.0/8"]
    assert ip_allowed("192.168.1.5", allowed)
    assert not ip_allowed("8.8.8.8", allowed)


def test_verify_slack_signature_valid():
    secret = "test_secret"
    timestamp = "1234567890"
    body = b"payload"
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    import hmac, hashlib

    valid_sig = (
        "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    )
    assert verify_slack_signature(secret, body, timestamp, valid_sig)


def test_verify_slack_signature_invalid():
    secret = "test_secret"
    timestamp = "1234567890"
    body = b"payload"
    invalid_sig = "v0=invalidsignature"
    assert not verify_slack_signature(secret, body, timestamp, invalid_sig)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)


@patch("universal_webhook_adapter.send_to_orchestrator", new_callable=AsyncMock)
def test_slack_webhook_valid_signature(mock_send):
    secret = "your_slack_signing_secret"
    payload = {"type": "event_callback", "event": {"type": "message"}}
    body = json.dumps(payload).encode("utf-8")
    timestamp = "1234567890"
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    import hmac, hashlib

    signature = (
        "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    )

    headers = {"X-Slack-Signature": signature, "X-Slack-Request-Timestamp": timestamp}

    with patch.dict(
        "universal_webhook_adapter.CONFIG",
        {
            "platforms": {"slack": {"signing_secret": secret}},
            "webhook": {"allowed_ips": ["127.0.0.1/32"]},
        },
    ):
        response = client.post("/webhook/slack", data=body, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_send.assert_awaited_once()


@patch("universal_webhook_adapter.send_to_orchestrator", new_callable=AsyncMock)
def test_github_webhook_valid_signature(mock_send):
    secret = "your_github_webhook_secret"
    payload = {"action": "push"}
    body = json.dumps(payload).encode("utf-8")
    import hmac, hashlib

    signature = "sha1=" + hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()

    headers = {"X-Hub-Signature": signature}

    with patch.dict(
        "universal_webhook_adapter.CONFIG",
        {
            "platforms": {"github": {"webhook_secret": secret}},
            "webhook": {"allowed_ips": ["127.0.0.1/32"]},
        },
    ):
        response = client.post("/webhook/github", data=body, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@patch("universal_webhook_adapter.send_to_orchestrator", new_callable=AsyncMock)
def test_telegram_webhook(mock_send):
    payload = {"update_id": 123456, "message": {"text": "hello"}}
    body = json.dumps(payload).encode("utf-8")

    with patch.dict(
        "universal_webhook_adapter.CONFIG",
        {"webhook": {"allowed_ips": ["127.0.0.1/32"]}},
    ):
        response = client.post("/webhook/telegram", data=body)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_send.assert_awaited_once()


@patch("universal_webhook_adapter.send_to_orchestrator", new_callable=AsyncMock)
def test_generic_webhook(mock_send):
    payload = {"foo": "bar"}
    body = json.dumps(payload).encode("utf-8")

    with patch.dict(
        "universal_webhook_adapter.CONFIG",
        {"webhook": {"allowed_ips": ["127.0.0.1/32"]}},
    ):
        response = client.post("/webhook/customplatform", data=body)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_send.assert_awaited_once()


if __name__ == "__main__":
    pytest.main()
