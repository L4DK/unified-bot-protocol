# adapters/whatsapp/adapter.py
from ..base import PlatformAdapter, AdapterMetadata
import aiohttp

class WhatsAppAdapter(PlatformAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = f"https://graph.facebook.com/v12.0/{config['phone_number_id']}"
        self.access_token = config["access_token"]

    @property
    def platform_name(self) -> str:
        return "whatsapp"

    @property
    def capabilities(self) -> List[str]:
        return [
            "whatsapp.message.send",
            "whatsapp.message.template",
            "whatsapp.media.send",
            "whatsapp.location.send"
        ]

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="whatsapp",
            version="1.0.0",
            features=["templates", "media", "location", "interactive_buttons"],
            max_message_length=4096,
            supported_media_types=["image", "video", "audio", "document"],
            rate_limits={"messages_per_day": 1000}
        )

    async def _setup_platform(self):
        """Setup WhatsApp webhook"""
        # Webhook setup would be handled by your web framework
        pass

    async def handle_platform_event(self, event: Dict):
        """Handle WhatsApp webhook events"""
        if "messages" in event:
            message = event["messages"][0]
            ubp_event = {
                "event_type": "whatsapp.message.received",
                "platform": "whatsapp",
                "timestamp": message["timestamp"],
                "data": {
                    "from": message["from"],
                    "type": message["type"],
                    "text": message.get("text", {}).get("body", ""),
                    "raw_message": message
                }
            }
            await self.message_queue.put({"event": ubp_event})

    async def handle_command(self, command: Dict):
        """Handle UBP commands for WhatsApp"""
        try:
            command_name = command["command_name"]
            params = command["parameters"]

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            if command_name == "whatsapp.message.send":
                payload = {
                    "messaging_product": "whatsapp",
                    "to": params["to"],
                    "type": "text",
                    "text": {"body": params["text"]}
                }
            elif command_name == "whatsapp.message.template":
                payload = {
                    "messaging_product": "whatsapp",
                    "to": params["to"],
                    "type": "template",
                    "template": params["template"]
                }
            else:
                raise ValueError(f"Unknown command: {command_name}")

            async with self.http_session.post(
                f"{self.api_url}/messages",
                headers=headers,
                json=payload
            ) as response:
                result = await response.json()

                if response.status != 200:
                    raise Exception(f"WhatsApp API error: {result}")

                return {
                    "status": "SUCCESS",
                    "result": result
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "error_details": str(e)
            }