# Microsoft Teams Adapter for Unified Bot Protocol (UBP)

## Overview

This adapter integrates Microsoft Teams with the Unified Bot Protocol (UBP) framework, enabling rich messaging, reactions, and thread replies via the Microsoft Graph API.

## Features

- OAuth2 Bearer token management with caching and refresh
- Async command handling for sending, updating messages, adding reactions, and thread replies
- Inbound webhook event processing with UBP event conversion and queueing
- Structured logging and metrics for observability
- Secure event signing for communication with UBP Orchestrator
- Resilience with retries and graceful shutdown

## Installation

Install dependencies:

```bash
pip install aiohttp pytest pytest-asyncio
```

Ensure UBP core libraries (`ubp_core`) are installed and accessible.

## Configuration

Configure the adapter via a dictionary or YAML file with the following keys:

| Key               | Description                      | Required | Example                  |
|-------------------|--------------------------------|----------|--------------------------|
| `tenant_id`       | Azure AD tenant ID              | Yes      | `"your_tenant_id"`        |
| `client_id`       | Azure AD app client ID          | Yes      | `"your_client_id"`        |
| `client_secret`   | Azure AD app client secret      | Yes      | `"your_client_secret"`    |
| `bot_app_id`      | Bot Framework app ID            | Yes      | `"your_bot_app_id"`       |
| `bot_app_password`| Bot Framework app password      | Yes      | `"your_bot_app_password"` |
| `security_key`    | UBP security key for signing    | No       | `"your_ubp_security_key"` |

## Usage

```python
from microsoft_teams_adapter import MicrosoftTeamsAdapter

config = {
    "tenant_id": "your_tenant_id",
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "bot_app_id": "your_bot_app_id",
    "bot_app_password": "your_bot_app_password",
    "security_key": "your_ubp_security_key",
}

adapter = MicrosoftTeamsAdapter(config)

# Start background tasks as needed (e.g., message queue processing)

# On shutdown
await adapter.close()
```

## Testing

Run tests with:

```bash
pytest
```

Tests cover OAuth2 token management, inbound event processing, and command handling.

## Roadmap

- Support for adaptive cards and rich media
- Rate limiting and retry policies for Microsoft Graph API calls
- Health checks and self-healing mechanisms
- Distributed tracing integration

## License

Apache License 2.0

## Contact

Michael Landbo (UBP Founder & Principal Architect)
[Unified Bot Protocol](https://www.Unified-Bot-Protocol.com)
GitHub: [L4DK/Unified-Bot-Protocol](https://github.com/L4DK/Unified-Bot-Protocol)
