"""
FILEPATH: adapters/registry.py
PROJECT: Unified Bot Protocol (UBP)
COMPONENT: Platform Adapter Registry

LICENSE: Apache-2.0
AUTHOR: Michael Landbo (Founder & BDFL of UBP)

DESCRIPTION:
  Provides a registry of available platform adapters and their capabilities.
  The registry maps adapter names to their corresponding classes and capabilities.
  It can be used to dynamically load and instantiate adapters based on user input.

VERSION: 1.0.0

CREATED: 2025-09-16
LAST EDIT: 2025-09-19

CHANGELOG:
- 1.0.0: Initial base adapter interface and registry
"""

import yaml
import os
from typing import Dict, List, Optional


class AdapterMetadata:
    def __init__(self, name: str, category: str, description: str, config_path: str):
        self.name = name
        self.category = category
        self.description = description
        self.config_path = config_path

    def load_config(self) -> dict:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, "r") as f:
            return yaml.safe_load(f)


class AdapterRegistry:
    def __init__(self):
        self.adapters: Dict[str, AdapterMetadata] = {}

    def register(self, metadata: AdapterMetadata):
        self.adapters[metadata.name] = metadata

    def get_adapter(self, name: str) -> Optional[AdapterMetadata]:
        return self.adapters.get(name)

    def list_adapters(self, category: Optional[str] = None) -> List[AdapterMetadata]:
        if category:
            return [a for a in self.adapters.values() if a.category == category]
        return list(self.adapters.values())

    def search_adapters(self, keyword: str) -> List[AdapterMetadata]:
        keyword_lower = keyword.lower()
        return [
            a
            for a in self.adapters.values()
            if keyword_lower in a.name.lower() or keyword_lower in a.description.lower()
        ]


# Initialize registry and register adapters
registry = AdapterRegistry()

registry.register(
    AdapterMetadata(
        name="discord",
        category="messaging",
        description="Discord adapter with full event handling and UBP integration",
        config_path="adapters/discord/config/discord_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="telegram",
        category="messaging",
        description="Telegram adapter using FastAPI webhook approach",
        config_path="adapters/telegram/config/telegram_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="slack",
        category="messaging",
        description="Slack adapter with SDK integration and Socket Mode",
        config_path="adapters/slack/config/slack_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="whatsapp",
        category="messaging",
        description="WhatsApp Business API adapter with template and media support",
        config_path="adapters/whatsapp/config/whatsapp_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="email",
        category="email",
        description="SMTP email sender adapter",
        config_path="adapters/email/config/email_smtp.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="webhook",
        category="integration",
        description="Universal webhook adapter with transformation rules",
        config_path="adapters/webhook/config/webhook_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="mqtt",
        category="iot",
        description="MQTT IoT adapter for device communication",
        config_path="adapters/iot/mqtt/config/mqtt_config.yaml",
    )
)


def create_adapter(name: str):
    """
    Factory method to create adapter instances by name.
    This requires actual adapter classes to be imported and mapped here.
    """
    # Example mapping (to be expanded)
    from adapters.discord.discord_adapter import DiscordAdapter
    from adapters.telegram.telegram_adapter import TelegramAdapter
    from adapters.slack.slack_adapter import SlackAdapter
    from adapters.whatsapp.whatsapp_adapter import WhatsAppAdapter
    from adapters.email.email_smtp import EmailSMTPAdapter
    from adapters.webhook.universal_webhook_adapter import UniversalWebhookAdapter
    from adapters.iot.mqtt.mqtt_adapter import MQTTAdapter

    adapter_map = {
        "discord": DiscordAdapter,
        "telegram": TelegramAdapter,
        "slack": SlackAdapter,
        "whatsapp": WhatsAppAdapter,
        "email": EmailSMTPAdapter,
        "webhook": UniversalWebhookAdapter,
        "mqtt": MQTTAdapter,
    }

    adapter_class = adapter_map.get(name)
    if not adapter_class:
        raise ValueError(f"Adapter '{name}' not found in registry.")
    metadata = registry.get_adapter(name)
    return adapter_class(config_path=metadata.config_path)
