# FILEPATH: adapters/slack/slack_adapter.py
# PROJECT: Unified Bot Protocol (UBP)
# COMPONENT: Platform Adapter Base Classes & Registry
#
# LICENSE: Apache-2.0
# AUTHOR: Michael Landbo (Founder & BDFL of UBP)
#
# DESCRIPTION:
#   Defines the standard Platform Adapter interface and base implementation
#   for all UBP platform integrations. Includes adapter registry, capability
#   management, connection handling, and metrics collection.
#   Core foundation for Slack platform adapter.
#
# VERSION: 1.0.1
# CREATED: 2025-09-16
# LAST EDIT: 2025-09-19
#
# CHANGELOG:
# - 1.0.1: Added file upload capability
# - 1.0.0: Initial base adapter interface and registry

from ..base import PlatformAdapter, AdapterMetadata, PlatformCapability
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.socket_mode.request import SocketModeRequest

class SlackAdapter(PlatformAdapter):
    def __init__(self, config: Dict[str, Any]):
        """
        Initializes a SlackAdapter instance with configuration.

        Args:
            config (Dict[str, Any]): Configuration dictionary containing:
                - bot_token (str): Slack bot token for the adapter
                - app_token (str): Slack app token for the adapter
        """
        super().__init__(config)
        self.slack_client = AsyncWebClient(token=config["bot_token"])
        self.socket_client = SocketModeClient(
            app_token=config["app_token"],
            web_client=self.slack_client
        )

    @property
    def platform_name(self) -> str:
        """Returns the name of the platform this adapter is for.

        Returns:
            str: The name of the platform, which is "slack".
        """
        return "slack"

    @property
    def capabilities(self) -> List[str]:

        """
        Returns a list of capabilities that this adapter supports.

        The supported capabilities are:

        - slack.message.send: Send a message to a Slack channel.
        - slack.message.update: Update a message in a Slack channel.
        - slack.reaction.add: Add a reaction to a message in a Slack channel.
        - slack.thread.reply: Reply to a thread in a Slack channel.
        - slack.file.upload: Upload a file to a Slack channel.

        Returns:
            List[str]: A list of capabilities supported by this adapter.
        """
        return [
            "slack.message.send",
            "slack.message.update",
            "slack.reaction.add",
            "slack.thread.reply",
            "slack.file.upload"
        ]

    @property
    def metadata(self) -> AdapterMetadata:
        """
        Returns metadata for the Slack adapter.

        Returns an instance of AdapterMetadata containing information about
        the Slack adapter, such as its version, features, maximum message
        length, supported media types, and rate limits.

        Returns:
            AdapterMetadata: Metadata for the Slack adapter.
        """
        return AdapterMetadata(
            platform="slack",
            version="1.0.0",
            features=["threads", "reactions", "files", "rich_text"],
            max_message_length=40000,
            supported_media_types=["image", "video", "audio", "document"],
            rate_limits={"messages_per_minute": 50}
        )

    async def _setup_platform(self):
        """Setup Slack-specific handlers and connect to the Slack Socket Mode API.

        This function sets up the Slack adapter by adding the event handler for
        incoming Slack events and connecting to the Slack Socket Mode API.
        """
        self.socket_client.socket_mode_request_listeners.append(
            self._handle_slack_event
        )
        await self.socket_client.connect()

    async def _handle_slack_event(
        self,
        client: SocketModeClient,
        req: SocketModeRequest
    ):
        """Handle incoming Slack events

        Acknowledges the incoming Slack event request, processes the event
        payload, and passes the event to the handle_platform_event method
        for further processing.

        Parameters:
            client (SocketModeClient): The SocketModeClient instance
            req (SocketModeRequest): The incoming Slack event request
        """
        if req.type == "events_api":
            # Acknowledge the request
            response = SocketModeResponse(envelope_id=req.envelope_id)
            await client.send_socket_mode_response(response)

            # Process the event
            event = req.payload["event"]
            await self.handle_platform_event(event)

    async def handle_platform_event(self, event: Dict):
        """
        Handle incoming Slack events.

        This method is responsible for converting Slack events into UBP events.

        The events are received through the Slack Socket Mode API and are processed
        accordingly. Currently, only message events are supported.

        Args:
            event (Dict): The Slack event to be processed.

        Returns:
            None
        """
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
        """
        Handle UBP commands for Slack

        Parameters:
            command (Dict): UBP command to be handled

        Returns:
            Dict: UBP command response
        """
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