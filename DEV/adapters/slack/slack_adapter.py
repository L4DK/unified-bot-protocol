# filepath: adapters/slack/slack_adapter.py
from ..base import PlatformAdapter, AdapterMetadata, PlatformCapability
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.socket_mode.request import SocketModeRequest

class SlackAdapter(PlatformAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.slack_client = AsyncWebClient(token=config["bot_token"])
        self.socket_client = SocketModeClient(
            app_token=config["app_token"],
            web_client=self.slack_client
        )

    @property
    def platform_name(self) -> str:
        return "slack"

    @property
    def capabilities(self) -> List[str]:
        return [
            "slack.message.send",
            "slack.message.update",
            "slack.reaction.add",
            "slack.thread.reply",
            "slack.file.upload"
        ]

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="slack",
            version="1.0.0",
            features=["threads", "reactions", "files", "rich_text"],
            max_message_length=40000,
            supported_media_types=["image", "video", "audio", "document"],
            rate_limits={"messages_per_minute": 50}
        )

    async def _setup_platform(self):
        """Setup Slack-specific handlers"""
        self.socket_client.socket_mode_request_listeners.append(
            self._handle_slack_event
        )
        await self.socket_client.connect()

    async def _handle_slack_event(
        self,
        client: SocketModeClient,
        req: SocketModeRequest
    ):
        """Handle incoming Slack events"""
        if req.type == "events_api":
            # Acknowledge the request
            response = SocketModeResponse(envelope_id=req.envelope_id)
            await client.send_socket_mode_response(response)

            # Process the event
            event = req.payload["event"]
            await self.handle_platform_event(event)

    async def handle_platform_event(self, event: Dict):
        """Convert Slack event to UBP event"""
        if event["type"] == "message":
            ubp_event = {
                "event_type": "slack.message.received",
                "platform": "slack",
                "timestamp": event["ts"],
                "data": {
                    "channel": event["channel"],
                    "user": event["user"],
                    "text": event["text"],
                    "thread_ts": event.get("thread_ts"),
                    "raw_event": event
                }
            }
            await self.message_queue.put({"event": ubp_event})

    async def handle_command(self, command: Dict):
        """Handle UBP commands for Slack"""
        try:
            command_name = command["command_name"]
            params = command["parameters"]

            if command_name == "slack.message.send":
                response = await self.slack_client.chat_postMessage(
                    channel=params["channel"],
                    text=params["text"],
                    thread_ts=params.get("thread_ts")
                )
            elif command_name == "slack.message.update":
                response = await self.slack_client.chat_update(
                    channel=params["channel"],
                    ts=params["message_ts"],
                    text=params["text"]
                )
            elif command_name == "slack.reaction.add":
                response = await self.slack_client.reactions_add(
                    channel=params["channel"],
                    timestamp=params["message_ts"],
                    name=params["reaction"]
                )
            else:
                raise ValueError(f"Unknown command: {command_name}")

            return {
                "status": "SUCCESS",
                "result": response.data
            }

        except Exception as e:
            return {
                "status": "ERROR",
                "error_details": str(e)
            }