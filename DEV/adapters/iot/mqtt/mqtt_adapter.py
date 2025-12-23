"""
FilePath: "/adapters/iot/mqtt/mqtt_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: MQTT IoT Adapter
Description: Async MQTT client for IoT device communication and sensor monitoring.
Author: "Michael Landbo"
Date created: "22/12/2025"
Date Modified: "22/12/2025"
Version: "1.0.0"
"""

import asyncio
import logging
import json
import ssl
from typing import Dict, Any, List, Optional, Union

# We use the 'aiomqtt' library for full async support
try:
     import aiomqtt
     MQTT_AVAILABLE = True
except ImportError:
     MQTT_AVAILABLE = False

# Import Base Adapter Classes
from adapters.base_adapter import (
     PlatformAdapter,
     AdapterCapabilities,
     AdapterMetadata,
     AdapterContext,
     PlatformCapability,
     SendResult,
     SimpleSendResult,
     AdapterStatus
)

class MQTTAdapter(PlatformAdapter):
     """
     Official UBP MQTT Adapter.
     Connects to an MQTT Broker (like Mosquitto, HiveMQ, AWS IoT) to
     send commands to devices and receive telemetry data.
     """

     def __init__(self, config: Dict[str, Any]):
          super().__init__(config)

          if not MQTT_AVAILABLE:
               self.logger.error("Missing dependency: 'aiomqtt'. Install via: pip install aiomqtt")

          # Config
          self.mqtt_config = config.get('mqtt', config)

          self.broker = self.mqtt_config.get("broker_host", "localhost")
          self.port = self.mqtt_config.get("broker_port", 1883)
          self.username = self.mqtt_config.get("username")
          self.password = self.mqtt_config.get("password")
          self.client_id = self.mqtt_config.get("client_id", "ubp-mqtt-client")
          self.keepalive = self.mqtt_config.get("keepalive", 60)
          self.use_tls = self.mqtt_config.get("use_tls", False)

          # Topics to subscribe to
          self.subscriptions = self.mqtt_config.get("subscriptions", [])
          if not self.subscriptions:
               self.logger.warning("No MQTT subscriptions configured. Adapter will only be able to send.")

          # Client State
          self._client: Optional[aiomqtt.Client] = None
          self._listen_task: Optional[asyncio.Task] = None

     # --- Properties ---

     @property
     def platform_name(self) -> str:
          return "mqtt"

     @property
     def capabilities(self) -> AdapterCapabilities:
          return AdapterCapabilities(
               supported_capabilities={
                    PlatformCapability.SEND_MESSAGE, # Publish
                    PlatformCapability.REAL_TIME_EVENTS # Subscribe
               },
               max_message_length=268435456, # MQTT can handle large payloads (256MB)
               rate_limits={"message.send": 1000} # MQTT is very fast
          )

     @property
     def metadata(self) -> AdapterMetadata:
          return AdapterMetadata(
               platform="mqtt",
               display_name="IoT / MQTT Bridge",
               version="1.0.0",
               author="Michael Landbo",
               description="Control IoT devices and monitor sensors via MQTT",
               supports_webhooks=False,
               supports_real_time=True
          )

     # --- Lifecycle ---

     async def _setup_platform(self) -> None:
          """Connects to Broker and starts the listening loop"""
          if not MQTT_AVAILABLE:
               self.status = AdapterStatus.ERROR
               return

          # Setup TLS if enabled
          tls_params = None
          if self.use_tls:
               tls_params = aiomqtt.TLSParameters(
                    ca_certs=None, # System default CA
                    certfile=None,
                    keyfile=None
               )

          # Initialiser Client
          self._client = aiomqtt.Client(
               hostname=self.broker,
               port=self.port,
               username=self.username,
               password=self.password,
               identifier=self.client_id,
               keepalive=self.keepalive,
               tls_params=tls_params
          )

          # Start the background process that handles the connection
          self._listen_task = asyncio.create_task(self._mqtt_loop())
          self.logger.info(f"MQTT Adapter connecting to {self.broker}:{self.port}...")

     async def stop(self) -> None:
          """Closes the connection nicely"""
          if self._listen_task:
               self._listen_task.cancel()
               try:
                    await self._listen_task
               except asyncio.CancelledError:
                    pass

          # The aiomqtt client is automatically closed when the context manager exits the loop,
          # but we make sure here
          await super().stop()

     # --- Core Logic: Send Message (Publish) ---

     async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
          """
          Publishes a message to an MQTT topic.

          Args:
               context.channel_id: Topic navnet (f.eks. "home/livingroom/light")
               message['content']: Payload (String eller JSON dict)
          """
          if not self._client:
               return SimpleSendResult(False, error_message="MQTT Client not initialized")

          try:
               topic = context.channel_id
               if not topic:
                    return SimpleSendResult(False, error_message="Missing topic (channel_id)")

               # Payload handling
               payload = message.get("content", "")
               if isinstance(payload, (dict, list)):
                    payload = json.dumps(payload)

               qos = message.get("metadata", {}).get("qos", 1)
               retain = message.get("metadata", {}).get("retain", False)

               self.logger.debug(f"Publishing to {topic}: {str(payload)[:50]}...")

               # Publish (requires the client to be connected in the loop)
               # Note: aiomqtt publish is typically async
               await self._client.publish(topic, payload=payload, qos=qos, retain=retain)

               return SimpleSendResult(
                    success=True,
                    details={"topic": topic, "qos": qos}
               )

          except Exception as e:
               self.logger.error(f"MQTT Publish Error: {e}")
               return SimpleSendResult(False, error_message=str(e))

     # --- Listener Loop (Subscribe & Receive) ---

     async def _mqtt_loop(self):
          """The main loop that keeps the connection alive and listening"""
          while not self._shutdown_event.is_set():
               try:
                    async with self._client:
                         self.logger.info("MQTT Connected!")

                         # 1. Subscribe to topics from config
                         for topic_filter in self.subscriptions:
                              await self._client.subscribe(topic_filter)
                              self.logger.info(f"Subscribed to: {topic_filter}")

                         # 2. Listen for messages
                         async for message in self._client.messages:
                              await self._process_mqtt_message(message)

               except aiomqtt.MqttError as e:
                    self.logger.warning(f"MQTT Connection lost: {e}. Reconnecting in 5s...")
                    await asyncio.sleep(5)
               except asyncio.CancelledError:
                    break
               except Exception as e:
                    self.logger.error(f"Critical MQTT Error: {e}")
                    await asyncio.sleep(5)

     async def _process_mqtt_message(self, message):
          """"Convert MQTT message to UBP format"""
          topic = str(message.topic)
          payload_raw = message.payload

          # Forsøg at decode payload
          try:
               content = payload_raw.decode("utf-8")
               # Prøv at parse JSON hvis muligt
               try:
                    content_json = json.loads(content)
                    payload_data = {"type": "json", "content": content_json}
               except json.JSONDecodeError:
                    payload_data = {"type": "text", "content": content}
          except Exception:
               # Binær data (f.eks. billede eller firmware)
               payload_data = {"type": "binary", "content": str(payload_raw)}

          # Byg Context
          context = AdapterContext(
               tenant_id="default",
               user_id="mqtt_device", # Vi kender ikke "brugeren" bag en sensor
               channel_id=topic,      # Topic er kanalen
               extras={"qos": message.qos}
          )

          # Byg UBP Besked
          ubp_payload = {
               "type": "event" if "json" in payload_data["type"] else "user_message",
               "content": payload_data["content"],
               "metadata": {
                    "source": "mqtt",
                    "topic": topic,
                    "retain": message.retain
               }
          }

          # Send til Runtime/Orchestrator
          if self.connected:
               await self._send_to_orchestrator({
                    "type": "platform_event", # Typisk er MQTT data events, ikke chat beskeder
                    "context": context.to_dict(),
                    "payload": ubp_payload
               })
               self.metrics["messages_received"] += 1

     async def handle_platform_event(self, event): pass
     async def handle_command(self, command): return {}
