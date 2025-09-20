# Facebook Website Adapter for Unified Bot Protocol (UBP)

## Overview

This adapter integrates Facebook Website features including Facebook Login, Social Plugins, and Customer Chat Plugin with the Unified Bot Protocol (UBP) framework.

## Features

- Secure webhook verification and signature validation
- Async processing of inbound Facebook Website events
- Outbound messaging via Facebook Messenger API
- Structured logging and metrics for observability
- Event signing for secure communication with UBP Orchestrator
- Graceful startup and shutdown of webhook HTTP server

## Installation

Install dependencies:

```bash
pip install aiohttp pytest pytest-asyncio
```

Ensure UBP core libraries (`ubp_core`) are installed and accessible.

## Configuration

Configure the adapter via a dictionary or YAML file with the following keys:

| Key                   | Description                     | Required | Example                      |
|-----------------------|---------------------------------|----------|------------------------------|
| `app_id`              | Facebook App ID                 | Yes      | `"your_app_id"`              |
| `app_secret`          | Facebook App Secret             | Yes      | `"your_app_secret"`          |
| `page_access_token`   | Facebook Page Access Token      | Yes      | `"your_page_access_token"`   |
| `verify_token`        | Webhook verification token      | Yes      | `"your_verify_token"`        |
| `security_key`        | UBP security key for signing    | No       | `"your_ubp_security_key"`    |

## Usage

```python
from facebook_website_adapter import FacebookWebsiteAdapter

config = {
    "app_id": "your_app_id",
    "app_secret": "your_app_secret",
    "page_access_token": "your_page_access_token",
    "verify_token": "your_verify_token",
    "security_key": "your_ubp_security_key",
}

adapter = FacebookWebsiteAdapter(config)

# Start webhook server (default 0.0.0.0:8081)
await adapter.start()

# On shutdown
await adapter.stop()
```

## Testing

Run tests with:

```bash
pytest
```

Tests cover webhook verification, signature validation, event processing, and command handling.

## Roadmap

- Support for advanced social plugin interactions
- Rate limiting and retry policies for Facebook API calls
- Health checks and self-healing mechanisms
- Distributed tracing integration

## License

Apache License 2.0

## Contact

Michael Landbo (UBP Founder & Principal Architect)
[Unified Bot Protocol](https://www.Unified-Bot-Protocol.com)
GitHub: [L4DK/Unified-Bot-Protocol](https://github.com/L4DK/Unified-Bot-Protocol)
