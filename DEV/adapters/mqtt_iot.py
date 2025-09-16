# filepath: adapters/mqtt_iot.py
# project: Unified Bot Protocol (UBP)
# module: MQTT IoT Adapter (outbound publish)
# version: 0.1.0
# last_edited: 2025-09-16
# author: Michael Landbo (UBP BDFL)
# license: Apache-2.0
# description:
#   Minimal MQTT publisher to demonstrate smart device/IoT integration via UBP.
#
# changelog:
# - 0.1.0: Initial creation; simple JSON publish.
#
# TODO:
# - Add QoS control, retained messages, LWT, and TLS mTLS support
# - Add inbound subscription mapping to UBP messages

from __future__ import annotations
from typing import Dict, Any
import json
import asyncio

try:
    import asyncio_mqtt
except ImportError:
    asyncio_mqtt = None

from .base import BaseAdapter, AdapterContext, AdapterCapabilities, SimpleSendResult, AdapterError

class MQTTAdapter(BaseAdapter):
    adapter_id = "mqtt_iot"
    display_name = "MQTT IoT"
    capabilities = AdapterCapabilities(supports_text=True)

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SimpleSendResult:
        if asyncio_mqtt is None:
            raise AdapterError("asyncio_mqtt not installed. Install with: pip install asyncio-mqtt")

        broker = self.config["broker"]
        port = self.config.get("port", 1883)
        topic = message.get("topic")
        payload = message.get("payload", {})
        qos = int(self.config.get("qos", 0))

        if not topic:
            return SimpleSendResult(False, details={"error": "missing topic"})

        try:
            async with asyncio_mqtt.Client(broker, port) as client:
                await client.publish(topic, json.dumps(payload), qos=qos)
            return SimpleSendResult(True, details={"topic": topic, "broker": broker})
        except Exception as e:
            self.logger.exception("MQTT publish failed")
            return SimpleSendResult(False, details={"error": str(e)})