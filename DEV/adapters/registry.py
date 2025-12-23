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

VERSION: 1.0.1

CREATED: 2025-09-16
LAST EDIT: 2025-12-22

CHANGELOG:
- 1.0.1: Added dynamic absolute path resolution to fix execution from subdirectories.
- 1.0.0: Initial base adapter interface and registry
"""

import yaml
import os
from typing import Dict, List, Optional, Any

# --- PATH CORRECTION ---
# Finder den absolutte sti til mappen, hvor denne fil (registry.py) ligger.
# F.eks: F:\WEBSERVER\www\unified-bot-protocol-main\DEV\adapters
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class AdapterMetadata:
    def __init__(self, name: str, category: str, description: str, relative_config_path: str):
        self.name = name
        self.category = category
        self.description = description
        # Bygger den absolutte sti ved at sammensætte BASE_DIR med den relative sti
        # Vi fjerner 'adapters/' fra starten af stien hvis den er der, for at undgå dubletter,
        # da BASE_DIR allerede er nede i 'adapters' mappen.
        clean_rel_path = relative_config_path.replace("adapters/", "").replace("adapters\\", "")
        self.config_path = os.path.join(BASE_DIR, clean_rel_path)

    def load_config(self) -> dict:
        if not os.path.exists(self.config_path):
            # Fallback logging eller fejlbesked kunne være her
            raise FileNotFoundError(f"Config file not found at: {self.config_path}")

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

# Note: Vi beholder stierne som du kender dem, men klassen rydder selv op i dem.
registry.register(
    AdapterMetadata(
        name="discord",
        category="messaging",
        description="Discord adapter with full event handling and UBP integration",
        relative_config_path="discord/config/discord_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="telegram",
        category="messaging",
        description="Telegram adapter using FastAPI webhook approach",
        relative_config_path="telegram/config/telegram_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="slack",
        category="messaging",
        description="Slack adapter with SDK integration and Socket Mode",
        relative_config_path="slack/config/slack_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="whatsapp",
        category="messaging",
        description="WhatsApp Business API adapter with template and media support",
        relative_config_path="whatsapp/config/whatsapp_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="email",
        category="email",
        description="SMTP email sender adapter",
        relative_config_path="email/config/email_smtp.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="webhook",
        category="integration",
        description="Universal webhook adapter with transformation rules",
        relative_config_path="webhook/config/webhook_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="mqtt",
        category="iot",
        description="MQTT IoT adapter for device communication",
        relative_config_path="iot/mqtt/config/mqtt_config.yaml",
    )
)

registry.register(
    AdapterMetadata(
        name="console",
        category="cli",
        description="Local Terminal Chat",
        relative_config_path="console/config/console_config.yaml", # Keep in mind: relative_config_path
    )
)


def create_adapter(name: str):
    """
    Factory method to create adapter instances by name.
    """
    metadata = registry.get_adapter(name)
    if not metadata:
        raise ValueError(f"Adapter '{name}' is not registered.")

    # 1. Load basis config fra YAML
    config = metadata.load_config()

    # 2. ENVIRONMENT OVERRIDE (Inject secrets fra .env)
    # Dette gør at vi ikke behøver skrive passwords i YAML filer
    import os

    if name == "discord":
        if os.getenv("DISCORD_BOT_TOKEN"):
            # Sørg for at strukturen matcher det adapteren forventer (nested eller flad)
            if "discord" not in config: config["discord"] = {}
            config["discord"]["bot_token"] = os.getenv("DISCORD_BOT_TOKEN")

    elif name == "telegram":
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            if "telegram" not in config: config["telegram"] = {}
            config["telegram"]["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")

    elif name == "slack":
        if "slack" not in config: config["slack"] = {}
        if os.getenv("SLACK_BOT_TOKEN"): config["slack"]["bot_token"] = os.getenv("SLACK_BOT_TOKEN")
        if os.getenv("SLACK_APP_TOKEN"): config["slack"]["app_token"] = os.getenv("SLACK_APP_TOKEN")

    elif name == "whatsapp":
        if "whatsapp" not in config: config["whatsapp"] = {}
        if os.getenv("WHATSAPP_ACCESS_TOKEN"): config["whatsapp"]["access_token"] = os.getenv("WHATSAPP_ACCESS_TOKEN")

    elif name == "email":
        if "email" not in config: config["email"] = {}
        if os.getenv("EMAIL_SMTP_PASS"): config["email"]["password"] = os.getenv("EMAIL_SMTP_PASS")
        if os.getenv("EMAIL_SMTP_USER"): config["email"]["username"] = os.getenv("EMAIL_SMTP_USER")

    elif name == "mqtt":
        if "mqtt" not in config: config["mqtt"] = {}
        if os.getenv("MQTT_BROKER"): config["mqtt"]["broker_host"] = os.getenv("MQTT_BROKER")
        if os.getenv("MQTT_PASS"): config["mqtt"]["password"] = os.getenv("MQTT_PASS")

    # 3. Import og Instantiér (Som før)
    try:
        if name == "discord":
            from adapters.discord.discord_adapter import DiscordAdapter
            return DiscordAdapter(config=config) # Vi sender den opdaterede config med env vars

        elif name == "telegram":
            from adapters.telegram.telegram_adapter import TelegramAdapter
            return TelegramAdapter(config=config)

        elif name == "slack":
            from adapters.slack.slack_adapter import SlackAdapter
            return SlackAdapter(config=config)

        elif name == "whatsapp":
            from adapters.whatsapp.whatsapp_adapter import WhatsAppAdapter
            return WhatsAppAdapter(config=config)

        elif name == "email":
            from adapters.email.email_smtp import EmailSMTPAdapter
            return EmailSMTPAdapter(config=config)

        elif name == "webhook":
            from adapters.webhook.universal_webhook_adapter import UniversalWebhookAdapter
            return UniversalWebhookAdapter(config=config)

        elif name == "mqtt":
            try:
                from adapters.iot.mqtt.mqtt_adapter import MQTTAdapter
                return MQTTAdapter(config=config)
            except ImportError:
                # Fallback hvis filen ikke er oprettet endnu, så crasher registry ikke
                raise ImportError("MQTT Adapter code missing")

        elif name == "console":
            from adapters.console.console_adapter import ConsoleAdapter
            return ConsoleAdapter(config=config)

        elif name == "zabbix":
                from adapters.zabbix.zabbix_adapter import ZabbixAdapter
                # Inject Zabbix secrets
                if "zabbix" not in config: config["zabbix"] = {}
                if os.getenv("ZABBIX_URL"): config["zabbix"]["zabbix_url"] = os.getenv("ZABBIX_URL")
                if os.getenv("ZABBIX_API_TOKEN"): config["zabbix"]["api_token"] = os.getenv("ZABBIX_API_TOKEN")
                return ZabbixAdapter(config=config)

        else:
            raise ValueError(f"No factory implementation for adapter: {name}")

    except ImportError as e:
        raise ImportError(f"Could not import adapter class for {name}. Error: {str(e)}")
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Configuration file missing for {name}: {str(e)}")
