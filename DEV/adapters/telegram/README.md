# Telegram Adapter for Unified Bot Protocol (UBP)

## Overview

This is the most comprehensive and production-ready Telegram adapter ever created for the Unified Bot Protocol (UBP) framework. It provides complete bidirectional communication between Telegram and the UBP Orchestrator with advanced features and world-class reliability.

## Features

### Core Capabilities

- **Complete Telegram Bot API 7.0+ support**
- **All message types**: text, media, documents, stickers, voice, video notes
- **Interactive components**: inline keyboards, reply keyboards, callback queries
- **Advanced features**: inline queries, payments, games, web apps
- **File handling**: upload/download with progress tracking
- **Multi-language support** and localization

### Production-Grade Features

- **Dual mode operation**: webhook and long polling with automatic fallback
- **Rate limiting**: intelligent backoff and queue management
- **Circuit breaker**: automatic failure detection and recovery
- **Comprehensive observability**: structured logging and metrics
- **Security**: message signing, webhook verification, token protection
- **Resilience**: auto-reconnection, retries, and self-healing
- **Performance**: async optimization and thread-safe operations

## Installation

```bash
pip install aiohttp aiofiles pytest pytest-asyncio
```

Ensure UBP core libraries (`ubp_core`) are installed and accessible.

## Configuration

Configure via YAML file or dictionary:

| Key                       | Description                           | Required | Default |
|---------------------------|---------------------------------------|----------|---------|
| `bot_token`               | Telegram Bot API token                | Yes      | -       |
| `webhook_url`             | Webhook URL for receiving updates     | No       | None    |
| `webhook_secret`          | Secret token for webhook verification | No       | None    |
| `use_webhook`             | Use webhook instead of polling        | No       | true    |
| `security_key`            | UBP security key for signing          | No       | ""      |
| `rate_limit_per_second`   | API requests per second               | No       | 30      |
| `max_file_size`           | Maximum file size for downloads       | No       | 50MB    |

## Usage

```python
from telegram_adapter import TelegramAdapter, TelegramConfig

config = TelegramConfig(
    bot_token="your_bot_token",
    webhook_url="https://your-domain.com/webhook/telegram",
    webhook_secret="your_secret",
    security_key="your_ubp_key"
)

adapter = TelegramAdapter(config)

# Start adapter
await adapter.start()

# Register custom handlers
async def message_handler(update):
    print(f"Received message: {update['message']['text']}")

adapter.register_handler(TelegramUpdateType.MESSAGE, message_handler)

# Stop adapter
await adapter.stop()
```

## Supported Commands

- `telegram.message.send` - Send text message
- `telegram.message.edit` - Edit message text
- `telegram.message.delete` - Delete message
- `telegram.photo.send` - Send photo
- `telegram.document.send` - Send document
- `telegram.callback_query.answer` - Answer callback query
- `telegram.inline_query.answer` - Answer inline query

## Testing

Run comprehensive test suite:

```bash
pytest -v
```

Tests cover all major functionality including webhook handling, API requests, event conversion, and error scenarios.

## Advanced Features

### Event Handlers

Register custom handlers for specific update types:

```python
adapter.register_handler(TelegramUpdateType.CALLBACK_QUERY, my_callback_handler)
```

### File Operations

Download files with progress tracking:

```python
await adapter.download_file("file_id", "/path/to/destination")
```

### Rate Limiting

Built-in intelligent rate limiting with burst support and automatic backoff.

### Circuit Breaker

Automatic failure detection and recovery to prevent cascade failures.

## Roadmap

- Telegram Mini Apps integration
- Advanced payment processing
- Bot API 8.0+ features
- Enhanced media processing
- Real-time analytics dashboard

## License

Apache License 2.0

## Contact

Michael Landbo (UBP Founder & Principal Architect)
[Unified Bot Protocol](https://www.Unified-Bot-Protocol.com)
GitHub: [L4DK/Unified-Bot-Protocol](https://github.com/L4DK/Unified-Bot-Protocol)
