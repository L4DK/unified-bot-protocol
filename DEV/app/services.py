# filepath: app/services.py
# project: Unified Bot Protocol (UBP)
# module: Wiring example for Router + Adapters
# version: 0.1.0
# last_edited: 2025-09-16
# author: Michael Landbo (UBP BDFL)
# license: Apache-2.0
# description:
#   Demonstrates how to register adapters and route messages.
#
# TODO:
# - Replace hard-coded config with Management API/Secrets backends
# - Add FastAPI endpoints to expose Management & C2 APIs per UBP spec

import asyncio
import logging

from adapters.base import AdapterRegistry
from adapters.email_smtp import SMTPEmailAdapter
from adapters.mqtt_iot import MQTTAdapter
from core.routing.policy_engine import PolicyEngine
from core.routing.message_router import MessageRouter

logging.basicConfig(level=logging.INFO)

registry = AdapterRegistry()
registry.register("email", SMTPEmailAdapter({
    "host": "smtp.example.com",
    "port": 587,
    "username": "bot@example.com",
    "password": "REDACTED",
    "from": "bot@example.com",
    "use_tls": True
}))
registry.register("mqtt_iot", MQTTAdapter({
    "broker": "mqtt-broker.local",
    "port": 1883,
    "qos": 0
}))

policy = PolicyEngine({
    "allow_platforms": ["email", "mqtt_iot"],
    "max_content_length": 5000,
    "require_capabilities": ["supports_text"]
})

router = MessageRouter(registry, policy)

async def main():
    # Email example
    email_msg = {"type": "text", "content": "Hello via Email!", "to": "user@example.com", "subject": "Greetings"}
    email_ctx = {"tenant_id": "acme", "target_platform": "email", "user_id": "u-123"}
    print(await router.route_message(email_msg, email_ctx))

    # MQTT example
    mqtt_msg = {"type": "command", "payload": {"device": "lamp", "action": "on"}, "topic": "home/livingroom/lamp"}
    mqtt_ctx = {"tenant_id": "acme", "target_platform": "mqtt_iot", "user_id": "u-123"}
    print(await router.route_message(mqtt_msg, mqtt_ctx))

if __name__ == "__main__":
    asyncio.run(main())