# Discord Platform Adapter (UBP)

**File:** `discord_platform_adapter.py`
**Project:** Unified Bot Protocol (UBP)
**Version:** 1.0.0
**Last Updated:** 2025-09-17
**Author:** Michael Landbo (Founder of UBP)

---

## 📌 Overview

The **Discord Platform Adapter** provides **bidirectional integration** between Discord and the **Unified Bot Protocol (UBP) Orchestrator**, enabling bots and AI agents to seamlessly interact with Discord communities while maintaining **full UBP compliance**.

This adapter translates **Discord events/messages** into standardized **UBP messages** and vice versa, providing interoperability, observability, scalability, and security.

---

## ✨ Features

- ✅ Full **Discord API integration** (via `discord.py`)
- ✅ **Bidirectional message translation** (Discord ↔ UBP)
- ✅ Support for **slash commands, buttons, modals, select menus**
- ✅ **Voice channels & thread management** supported
- ✅ **Message attachments, embeds, reactions** included
- ✅ **Webhook support** with caching
- ✅ **Rate limiting**, **error handling**, **resilience**
- ✅ **Security**: Token authentication, message signing, encryption
- ✅ **Observability**: Structured logs, metrics, distributed tracing
- ✅ **Health checks** for Discord + Orchestrator connectivity

---

## ⚙️ Installation

### 1. Install Python dependencies

```bash
pip install discord.py aiohttp websockets cryptography
```

### 2. Clone UBP Repository

```bash
git clone https://github.com/L4DK/Unified-Bot-Protocol.git
cd Unified-Bot-Protocol/adapters/discord/
```

---

## 🚀 Usage

### 1. Configure the Adapter

Edit `config` in `discord_platform_adapter.py`:

```python
config = {
    'discord': {
        'bot_token': 'YOUR_DISCORD_BOT_TOKEN',
        'application_id': 'YOUR_DISCORD_APP_ID',
        'guild_ids': [123456789],  # Optional, for guild-specific commands
        'command_prefix': '!'
    },
    'ubp': {
        'orchestrator_url': 'ws://localhost:8080/ws/adapters',
        'adapter_id': 'discord_adapter_001',
        'security_key': 'your_security_key_here'
    }
}
```

### 2. Run the Adapter

```bash
python discord_platform_adapter.py
```

The adapter will connect to **Discord** and the **UBP Orchestrator**.

---

## 📚 Example Bot Workflow

1. A Discord user sends `/weather Paris`.
2. The adapter converts it into a **UBP Command** message.
3. The Orchestrator forwards it to the designated **Bot Agent**.
4. The agent responds with structured data.
5. The adapter translates it back to **Discord embeds + text reply**.

---

## 🧪 Health & Observability

- `StructuredLogger` → JSON logs for ingestion into ELK/Grafana
- `MetricsCollector` → Tracks Discord API calls, errors, throughput
- `TracingManager` → Distributed tracing via correlation IDs
- Health check runs every **60s** (Discord + Orchestrator connections)

---

## 🔒 Security

- **Authentication** → Adapter signs all outbound requests to Orchestrator
- **Encryption** → Messages secured with Fernet (symmetric encryption)
- **Rate limiting** → Prevents hitting Discord API limits
- **Auto-reconnection** → Exponential backoff on disconnects

---

## 🛠️ Development Guide

### Run locally with hot reload

```bash
python -m discord_platform_adapter
```

### Useful links

- [Discord Developer Portal](https://discord.com/developers/applications)
- [Unified Bot Protocol - Official Docs](https://www.unified-bot-protocol.com)
- [UBP GitHub Repo](https://github.com/L4DK/Unified-Bot-Protocol)

---

## 📜 Changelog

### v1.0.0 (2025-09-17)

- Initial implementation of Discord Adapter
- Bidirectional event translation fully implemented
- Added **slash commands, buttons, select menus**
- Added **health checks + reconnect logic**
- Enabled **security signing + observability**

---

## 👥 Contributing

This project follows the **UBP Open Source Model (Apache 2.0 License)**.
All **protocol code** must remain **free and open**.
Commercial extensions are allowed, but must not compromise interoperability.

Fork → PR → Code Review → Merge (Founder-led BDFL governance).

---

## 📝 License

Apache 2.0 License. See [LICENSE](../../LICENSE) for details.
