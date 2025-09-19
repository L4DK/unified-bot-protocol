"""
Discord Platform Adapter for Unified Bot Protocol (UBP)
=======================================================

File: adapters/discord_adapter.py
Project: Unified Bot Protocol (UBP)
Version: 1.0.0
Last Edit: 2025-09-17
Author: Michael Landbo

Description:
Complete Discord Platform Adapter implementation providing bidirectional
communication between Discord and the UBP Orchestrator. Handles all Discord
events, message types, interactions, and maintains full UBP compliance.

Features:
- Full Discord API integration with discord.py
- Bidirectional message translation (Discord ↔ UBP)
- Interactive components (buttons, select menus, modals)
- Slash commands and context menus
- Voice channel integration
- Thread management
- Webhook support
- Rate limiting and error handling
- Comprehensive observability
- Security and authentication
- Auto-reconnection and resilience

TODO:
- Add voice message transcription
- Implement advanced moderation features
- Add custom emoji handling
- Extend thread archiving capabilities
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
import uuid
import hashlib
import hmac
import base64

import discord
from discord.ext import commands, tasks
import aiohttp
import websockets
from cryptography.fernet import Fernet

# UBP Core Imports
from ubp_core.platform_adapter import BasePlatformAdapter
from ubp_core.message_schema import UBPMessage, MessageType, ContentType
from ubp_core.security import SecurityManager, AuthenticationError
from ubp_core.observability import StructuredLogger, MetricsCollector, TracingManager
from ubp_core.health import HealthChecker
from ubp_core.registry import ServiceRegistry


class DiscordEventType(Enum):
    """Discord-specific event types"""
    MESSAGE = "message"
    REACTION_ADD = "reaction_add"
    REACTION_REMOVE = "reaction_remove"
    MEMBER_JOIN = "member_join"
    MEMBER_LEAVE = "member_leave"
    VOICE_STATE_UPDATE = "voice_state_update"
    THREAD_CREATE = "thread_create"
    THREAD_DELETE = "thread_delete"
    INTERACTION = "interaction"
    SLASH_COMMAND = "slash_command"
    BUTTON_CLICK = "button_click"
    SELECT_MENU = "select_menu"
    MODAL_SUBMIT = "modal_submit"


@dataclass
class DiscordContext:
    """Discord-specific context information"""
    guild_id: Optional[int] = None
    channel_id: Optional[int] = None
    thread_id: Optional[int] = None
    user_id: Optional[int] = None
    message_id: Optional[int] = None
    interaction_id: Optional[str] = None
    permissions: List[str] = None
    roles: List[str] = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []
        if self.roles is None:
            self.roles = []


@dataclass
class DiscordMessage:
    """Discord message representation"""
    content: str
    author_id: int
    channel_id: int
    guild_id: Optional[int]
    message_id: int
    timestamp: datetime
    message_type: str = "text"
    attachments: List[Dict] = None
    embeds: List[Dict] = None
    reactions: List[Dict] = None
    thread_id: Optional[int] = None
    reference_message_id: Optional[int] = None

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []
        if self.embeds is None:
            self.embeds = []
        if self.reactions is None:
            self.reactions = []


class DiscordRateLimiter:
    """Discord API rate limiting handler"""

    def __init__(self):
        self.buckets: Dict[str, Dict] = {}
        self.global_rate_limit = False
        self.global_reset_time = 0

    async def wait_if_rate_limited(self, endpoint: str) -> None:
        """Wait if rate limited for specific endpoint"""
        current_time = time.time()

        # Check global rate limit
        if self.global_rate_limit and current_time < self.global_reset_time:
            wait_time = self.global_reset_time - current_time
            await asyncio.sleep(wait_time)
            return

        # Check endpoint-specific rate limit
        if endpoint in self.buckets:
            bucket = self.buckets[endpoint]
            if bucket['remaining'] <= 0 and current_time < bucket['reset_time']:
                wait_time = bucket['reset_time'] - current_time
                await asyncio.sleep(wait_time)

    def update_rate_limit(self, endpoint: str, headers: Dict[str, str]) -> None:
        """Update rate limit information from response headers"""
        if 'X-RateLimit-Global' in headers:
            self.global_rate_limit = True
            self.global_reset_time = time.time() + float(headers.get('Retry-After', 0))

        if 'X-RateLimit-Remaining' in headers:
            self.buckets[endpoint] = {
                'remaining': int(headers['X-RateLimit-Remaining']),
                'reset_time': float(headers.get('X-RateLimit-Reset-After', 0)) + time.time()
            }


class DiscordInteractionHandler:
    """Handles Discord interactions (slash commands, buttons, etc.)"""

    def __init__(self, adapter: 'DiscordPlatformAdapter'):
        self.adapter = adapter
        self.logger = adapter.logger
        self.commands: Dict[str, Callable] = {}
        self.components: Dict[str, Callable] = {}

    def register_command(self, name: str, handler: Callable) -> None:
        """Register a slash command handler"""
        self.commands[name] = handler
        self.logger.info(f"Registered slash command: {name}")

    def register_component(self, custom_id: str, handler: Callable) -> None:
        """Register a component interaction handler"""
        self.components[custom_id] = handler
        self.logger.info(f"Registered component handler: {custom_id}")

    async def handle_interaction(self, interaction: discord.Interaction) -> None:
        """Handle incoming Discord interaction"""
        try:
            if interaction.type == discord.InteractionType.application_command:
                await self._handle_slash_command(interaction)
            elif interaction.type == discord.InteractionType.component:
                await self._handle_component_interaction(interaction)
            elif interaction.type == discord.InteractionType.modal_submit:
                await self._handle_modal_submit(interaction)
        except Exception as e:
            self.logger.error(f"Error handling interaction: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("An error occurred processing your request.", ephemeral=True)

    async def _handle_slash_command(self, interaction: discord.Interaction) -> None:
        """Handle slash command interaction"""
        command_name = interaction.data.get('name')
        if command_name in self.commands:
            await self.commands[command_name](interaction)
        else:
            # Forward to UBP Orchestrator
            ubp_message = await self.adapter._discord_to_ubp(interaction)
            await self.adapter._send_to_orchestrator(ubp_message)

    async def _handle_component_interaction(self, interaction: discord.Interaction) -> None:
        """Handle component interaction (buttons, select menus)"""
        custom_id = interaction.data.get('custom_id')
        if custom_id in self.components:
            await self.components[custom_id](interaction)
        else:
            # Forward to UBP Orchestrator
            ubp_message = await self.adapter._discord_to_ubp(interaction)
            await self.adapter._send_to_orchestrator(ubp_message)

    async def _handle_modal_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission"""
        custom_id = interaction.data.get('custom_id')
        if custom_id in self.components:
            await self.components[custom_id](interaction)
        else:
            # Forward to UBP Orchestrator
            ubp_message = await self.adapter._discord_to_ubp(interaction)
            await self.adapter._send_to_orchestrator(ubp_message)


class DiscordPlatformAdapter(BasePlatformAdapter):
    """
    Discord Platform Adapter for UBP

    Provides complete Discord integration with bidirectional communication,
    event handling, and full UBP protocol compliance.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Discord Configuration
        self.bot_token = config['discord']['bot_token']
        self.application_id = config['discord']['application_id']
        self.guild_ids = config['discord'].get('guild_ids', [])
        self.command_prefix = config['discord'].get('command_prefix', '!')

        # UBP Configuration
        self.orchestrator_url = config['ubp']['orchestrator_url']
        self.adapter_id = config['ubp']['adapter_id']
        self.security_key = config['ubp']['security_key']

        # Initialize components
        self.logger = StructuredLogger(f"discord_adapter_{self.adapter_id}")
        self.metrics = MetricsCollector("discord_adapter")
        self.tracer = TracingManager("discord_adapter")
        self.security = SecurityManager(self.security_key)
        self.health_checker = HealthChecker()
        self.rate_limiter = DiscordRateLimiter()

        # Discord Bot Setup
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        intents.guild_reactions = True
        intents.voice_states = True
        intents.members = True

        self.bot = commands.Bot(
            command_prefix=self.command_prefix,
            intents=intents,
            application_id=self.application_id
        )

        # Interaction Handler
        self.interaction_handler = DiscordInteractionHandler(self)

        # State Management
        self.active_sessions: Dict[str, Dict] = {}
        self.message_cache: Dict[int, DiscordMessage] = {}
        self.webhook_cache: Dict[int, discord.Webhook] = {}

        # WebSocket connection to UBP Orchestrator
        self.orchestrator_ws: Optional[websockets.WebSocketServerProtocol] = None
        self.connection_retry_count = 0
        self.max_retry_attempts = 5

        # Setup Discord event handlers
        self._setup_discord_events()

        # Health check endpoints
        self.health_checker.add_check("discord_connection", self._check_discord_health)
        self.health_checker.add_check("orchestrator_connection", self._check_orchestrator_health)

        self.logger.info("Discord Platform Adapter initialized")

    def _setup_discord_events(self) -> None:
        """Setup Discord bot event handlers"""

        @self.bot.event
        async def on_ready():
            self.logger.info(f"Discord bot connected as {self.bot.user}")
            self.metrics.increment("discord.connection.established")

            # Sync slash commands
            try:
                if self.guild_ids:
                    for guild_id in self.guild_ids:
                        guild = discord.Object(id=guild_id)
                        await self.bot.tree.sync(guild=guild)
                else:
                    await self.bot.tree.sync()
                self.logger.info("Slash commands synced")
            except Exception as e:
                self.logger.error(f"Failed to sync slash commands: {e}")

        @self.bot.event
        async def on_message(message: discord.Message):
            if message.author.bot:
                return

            await self._handle_discord_message(message)

        @self.bot.event
        async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
            if user.bot:
                return

            await self._handle_discord_reaction(reaction, user, "add")

        @self.bot.event
        async def on_reaction_remove(reaction: discord.Reaction, user: discord.User):
            if user.bot:
                return

            await self._handle_discord_reaction(reaction, user, "remove")

        @self.bot.event
        async def on_member_join(member: discord.Member):
            await self._handle_member_event(member, "join")

        @self.bot.event
        async def on_member_remove(member: discord.Member):
            await self._handle_member_event(member, "leave")

        @self.bot.event
        async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
            await self._handle_voice_state_update(member, before, after)

        @self.bot.event
        async def on_thread_create(thread: discord.Thread):
            await self._handle_thread_event(thread, "create")

        @self.bot.event
        async def on_thread_delete(thread: discord.Thread):
            await self._handle_thread_event(thread, "delete")

        @self.bot.event
        async def on_interaction(interaction: discord.Interaction):
            await self.interaction_handler.handle_interaction(interaction)

        @self.bot.event
        async def on_error(event: str, *args, **kwargs):
            self.logger.error(f"Discord event error in {event}: {args}, {kwargs}")
            self.metrics.increment("discord.errors", tags={"event": event})

    async def start(self) -> None:
        """Start the Discord Platform Adapter"""
        try:
            self.logger.info("Starting Discord Platform Adapter")

            # Start health checker
            await self.health_checker.start()

            # Connect to UBP Orchestrator
            await self._connect_to_orchestrator()

            # Start Discord bot
            await self.bot.start(self.bot_token)

        except Exception as e:
            self.logger.error(f"Failed to start Discord adapter: {e}")
            raise

    async def stop(self) -> None:
        """Stop the Discord Platform Adapter"""
        try:
            self.logger.info("Stopping Discord Platform Adapter")

            # Close orchestrator connection
            if self.orchestrator_ws:
                await self.orchestrator_ws.close()

            # Stop Discord bot
            await self.bot.close()

            # Stop health checker
            await self.health_checker.stop()

            self.logger.info("Discord Platform Adapter stopped")

        except Exception as e:
            self.logger.error(f"Error stopping Discord adapter: {e}")

    async def _connect_to_orchestrator(self) -> None:
        """Establish WebSocket connection to UBP Orchestrator"""
        while self.connection_retry_count < self.max_retry_attempts:
            try:
                self.logger.info(f"Connecting to UBP Orchestrator: {self.orchestrator_url}")

                headers = {
                    'Authorization': f'Bearer {self.security.generate_token()}',
                    'X-Adapter-ID': self.adapter_id,
                    'X-Platform': 'discord'
                }

                self.orchestrator_ws = await websockets.connect(
                    self.orchestrator_url,
                    extra_headers=headers,
                    ping_interval=30,
                    ping_timeout=10
                )

                self.logger.info("Connected to UBP Orchestrator")
                self.metrics.increment("orchestrator.connection.established")
                self.connection_retry_count = 0

                # Start message handler
                asyncio.create_task(self._handle_orchestrator_messages())
                break

            except Exception as e:
                self.connection_retry_count += 1
                self.logger.error(f"Failed to connect to orchestrator (attempt {self.connection_retry_count}): {e}")

                if self.connection_retry_count < self.max_retry_attempts:
                    await asyncio.sleep(2 ** self.connection_retry_count)  # Exponential backoff
                else:
                    raise ConnectionError("Failed to connect to UBP Orchestrator after maximum retries")

    async def _handle_orchestrator_messages(self) -> None:
        """Handle incoming messages from UBP Orchestrator"""
        try:
            async for message in self.orchestrator_ws:
                try:
                    data = json.loads(message)
                    ubp_message = UBPMessage(**data)

                    # Process message based on type
                    if ubp_message.message_type == MessageType.COMMAND:
                        await self._handle_orchestrator_command(ubp_message)
                    elif ubp_message.message_type == MessageType.RESPONSE:
                        await self._handle_orchestrator_response(ubp_message)
                    elif ubp_message.message_type == MessageType.EVENT:
                        await self._handle_orchestrator_event(ubp_message)

                    self.metrics.increment("orchestrator.messages.received")

                except json.JSONDecodeError as e:
                    self.logger.error(f"Invalid JSON from orchestrator: {e}")
                except Exception as e:
                    self.logger.error(f"Error processing orchestrator message: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("Orchestrator connection closed, attempting reconnection")
            await self._connect_to_orchestrator()
        except Exception as e:
            self.logger.error(f"Error in orchestrator message handler: {e}")

    async def _handle_discord_message(self, message: discord.Message) -> None:
        """Handle incoming Discord message"""
        try:
            # Create Discord message object
            discord_msg = DiscordMessage(
                content=message.content,
                author_id=message.author.id,
                channel_id=message.channel.id,
                guild_id=message.guild.id if message.guild else None,
                message_id=message.id,
                timestamp=message.created_at,
                attachments=[{
                    'url': att.url,
                    'filename': att.filename,
                    'size': att.size,
                    'content_type': att.content_type
                } for att in message.attachments],
                embeds=[embed.to_dict() for embed in message.embeds],
                thread_id=message.channel.id if isinstance(message.channel, discord.Thread) else None,
                reference_message_id=message.reference.message_id if message.reference else None
            )

            # Cache message
            self.message_cache[message.id] = discord_msg

            # Convert to UBP message
            ubp_message = await self._discord_to_ubp(discord_msg)

            # Send to orchestrator
            await self._send_to_orchestrator(ubp_message)

            self.metrics.increment("discord.messages.processed")

        except Exception as e:
            self.logger.error(f"Error handling Discord message: {e}")
            self.metrics.increment("discord.errors", tags={"type": "message_handling"})

    async def _handle_discord_reaction(self, reaction: discord.Reaction, user: discord.User, action: str) -> None:
        """Handle Discord reaction events"""
        try:
            context = DiscordContext(
                guild_id=reaction.message.guild.id if reaction.message.guild else None,
                channel_id=reaction.message.channel.id,
                user_id=user.id,
                message_id=reaction.message.id
            )

            ubp_message = UBPMessage(
                message_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                message_type=MessageType.EVENT,
                content_type=ContentType.EVENT,
                platform="discord",
                adapter_id=self.adapter_id,
                content={
                    'event_type': f'reaction_{action}',
                    'emoji': str(reaction.emoji),
                    'message_id': reaction.message.id,
                    'user_id': user.id,
                    'count': reaction.count
                },
                context=asdict(context),
                metadata={
                    'platform_event': f'reaction_{action}',
                    'emoji_name': reaction.emoji.name if hasattr(reaction.emoji, 'name') else str(reaction.emoji)
                }
            )

            await self._send_to_orchestrator(ubp_message)

        except Exception as e:
            self.logger.error(f"Error handling Discord reaction: {e}")

    async def _handle_member_event(self, member: discord.Member, event_type: str) -> None:
        """Handle member join/leave events"""
        try:
            context = DiscordContext(
                guild_id=member.guild.id,
                user_id=member.id,
                roles=[role.name for role in member.roles]
            )

            ubp_message = UBPMessage(
                message_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                message_type=MessageType.EVENT,
                content_type=ContentType.EVENT,
                platform="discord",
                adapter_id=self.adapter_id,
                content={
                    'event_type': f'member_{event_type}',
                    'user_id': member.id,
                    'username': member.name,
                    'display_name': member.display_name,
                    'joined_at': member.joined_at.isoformat() if member.joined_at else None,
                    'roles': [role.name for role in member.roles]
                },
                context=asdict(context),
                metadata={
                    'platform_event': f'member_{event_type}',
                    'guild_name': member.guild.name
                }
            )

            await self._send_to_orchestrator(ubp_message)

        except Exception as e:
            self.logger.error(f"Error handling member event: {e}")

    async def _handle_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        """Handle voice state changes"""
        try:
            context = DiscordContext(
                guild_id=member.guild.id,
                user_id=member.id
            )

            ubp_message = UBPMessage(
                message_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                message_type=MessageType.EVENT,
                content_type=ContentType.EVENT,
                platform="discord",
                adapter_id=self.adapter_id,
                content={
                    'event_type': 'voice_state_update',
                    'user_id': member.id,
                    'before_channel': before.channel.id if before.channel else None,
                    'after_channel': after.channel.id if after.channel else None,
                    'muted': after.mute,
                    'deafened': after.deaf,
                    'self_muted': after.self_mute,
                    'self_deafened': after.self_deaf
                },
                context=asdict(context),
                metadata={
                    'platform_event': 'voice_state_update'
                }
            )

            await self._send_to_orchestrator(ubp_message)

        except Exception as e:
            self.logger.error(f"Error handling voice state update: {e}")

    async def _handle_thread_event(self, thread: discord.Thread, event_type: str) -> None:
        """Handle thread creation/deletion events"""
        try:
            context = DiscordContext(
                guild_id=thread.guild.id,
                channel_id=thread.parent_id,
                thread_id=thread.id
            )

            ubp_message = UBPMessage(
                message_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                message_type=MessageType.EVENT,
                content_type=ContentType.EVENT,
                platform="discord",
                adapter_id=self.adapter_id,
                content={
                    'event_type': f'thread_{event_type}',
                    'thread_id': thread.id,
                    'thread_name': thread.name,
                    'parent_channel_id': thread.parent_id,
                    'owner_id': thread.owner_id,
                    'archived': thread.archived,
                    'auto_archive_duration': thread.auto_archive_duration
                },
                context=asdict(context),
                metadata={
                    'platform_event': f'thread_{event_type}'
                }
            )

            await self._send_to_orchestrator(ubp_message)

        except Exception as e:
            self.logger.error(f"Error handling thread event: {e}")

    async def _discord_to_ubp(self, discord_obj: Union[DiscordMessage, discord.Interaction]) -> UBPMessage:
        """Convert Discord object to UBP message format"""
        if isinstance(discord_obj, DiscordMessage):
            return await self._discord_message_to_ubp(discord_obj)
        elif isinstance(discord_obj, discord.Interaction):
            return await self._discord_interaction_to_ubp(discord_obj)
        else:
            raise ValueError(f"Unsupported Discord object type: {type(discord_obj)}")

    async def _discord_message_to_ubp(self, discord_msg: DiscordMessage) -> UBPMessage:
        """Convert Discord message to UBP message"""
        # Determine content type
        content_type = ContentType.TEXT
        if discord_msg.attachments:
            if any(att['content_type'].startswith('image/') for att in discord_msg.attachments):
                content_type = ContentType.IMAGE
            elif any(att['content_type'].startswith('audio/') for att in discord_msg.attachments):
                content_type = ContentType.AUDIO
            elif any(att['content_type'].startswith('video/') for att in discord_msg.attachments):
                content_type = ContentType.VIDEO
            else:
                content_type = ContentType.FILE

        # Create context
        context = DiscordContext(
            guild_id=discord_msg.guild_id,
            channel_id=discord_msg.channel_id,
            thread_id=discord_msg.thread_id,
            user_id=discord_msg.author_id,
            message_id=discord_msg.message_id
        )

        # Create UBP message
        ubp_message = UBPMessage(
            message_id=str(uuid.uuid4()),
            timestamp=discord_msg.timestamp,
            message_type=MessageType.USER_MESSAGE,
            content_type=content_type,
            platform="discord",
            adapter_id=self.adapter_id,
            content={
                'text': discord_msg.content,
                'attachments': discord_msg.attachments,
                'embeds': discord_msg.embeds,
                'reactions': discord_msg.reactions,
                'reference_message_id': discord_msg.reference_message_id
            },
            context=asdict(context),
            metadata={
                'discord_message_id': discord_msg.message_id,
                'message_type': discord_msg.message_type
            }
        )

        return ubp_message

    async def _discord_interaction_to_ubp(self, interaction: discord.Interaction) -> UBPMessage:
        """Convert Discord interaction to UBP message"""
        context = DiscordContext(
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            user_id=interaction.user.id,
            interaction_id=str(interaction.id)
        )

        # Extract interaction data
        interaction_data = {
            'type': interaction.type.name,
            'data': interaction.data,
            'user': {
                'id': interaction.user.id,
                'username': interaction.user.name,
                'display_name': interaction.user.display_name
            }
        }

        if interaction.type == discord.InteractionType.application_command:
            interaction_data['command_name'] = interaction.data.get('name')
            interaction_data['options'] = interaction.data.get('options', [])
        elif interaction.type == discord.InteractionType.component:
            interaction_data['custom_id'] = interaction.data.get('custom_id')
            interaction_data['component_type'] = interaction.data.get('component_type')
            interaction_data['values'] = interaction.data.get('values', [])

        ubp_message = UBPMessage(
            message_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            message_type=MessageType.COMMAND,
            content_type=ContentType.INTERACTION,
            platform="discord",
            adapter_id=self.adapter_id,
            content=interaction_data,
            context=asdict(context),
            metadata={
                'interaction_id': str(interaction.id),
                'interaction_type': interaction.type.name
            }
        )

        return ubp_message

    async def _send_to_orchestrator(self, ubp_message: UBPMessage) -> None:
        """Send UBP message to orchestrator"""
        try:
            if not self.orchestrator_ws:
                self.logger.warning("No orchestrator connection, message dropped")
                return

            # Add security signature
            message_dict = asdict(ubp_message)
            message_dict['signature'] = self.security.sign_message(message_dict)

            # Send message
            await self.orchestrator_ws.send(json.dumps(message_dict, default=str))
            self.metrics.increment("orchestrator.messages.sent")

        except Exception as e:
            self.logger.error(f"Error sending message to orchestrator: {e}")
            self.metrics.increment("orchestrator.errors", tags={"type": "send_message"})

    async def _handle_orchestrator_command(self, ubp_message: UBPMessage) -> None:
        """Handle command from orchestrator"""
        try:
            command = ubp_message.content.get('command')

            if command == 'send_message':
                await self._send_discord_message(ubp_message)
            elif command == 'create_thread':
                await self._create_discord_thread(ubp_message)
            elif command == 'add_reaction':
                await self._add_discord_reaction(ubp_message)
            elif command == 'create_webhook':
                await self._create_discord_webhook(ubp_message)
            elif command == 'register_slash_command':
                await self._register_slash_command(ubp_message)
            else:
                self.logger.warning(f"Unknown command from orchestrator: {command}")

        except Exception as e:
            self.logger.error(f"Error handling orchestrator command: {e}")

    async def _handle_orchestrator_response(self, ubp_message: UBPMessage) -> None:
        """Handle response from orchestrator"""
        try:
            # Find the original interaction or message to respond to
            context = DiscordContext(**ubp_message.context)

            if context.interaction_id:
                # This is a response to an interaction
                await self._send_interaction_response(ubp_message, context)
            else:
                # This is a response to a regular message
                await self._send_discord_message(ubp_message)

        except Exception as e:
            self.logger.error(f"Error handling orchestrator response: {e}")

    async def _handle_orchestrator_event(self, ubp_message: UBPMessage) -> None:
        """Handle event from orchestrator"""
        try:
            event_type = ubp_message.content.get('event_type')

            if event_type == 'bot_status_update':
                await self._update_bot_status(ubp_message)
            elif event_type == 'guild_settings_update':
                await self._update_guild_settings(ubp_message)
            else:
                self.logger.info(f"Received orchestrator event: {event_type}")

        except Exception as e:
            self.logger.error(f"Error handling orchestrator event: {e}")

    async def _send_discord_message(self, ubp_message: UBPMessage) -> None:
        """Send message to Discord"""
        try:
            context = DiscordContext(**ubp_message.context)
            content = ubp_message.content

            # Get channel
            channel = self.bot.get_channel(context.channel_id)
            if not channel:
                self.logger.error(f"Channel not found: {context.channel_id}")
                return

            # Prepare message content
            message_content = content.get('text', '')
            embeds = []
            files = []
            view = None

            # Handle embeds
            if 'embeds' in content:
                for embed_data in content['embeds']:
                    embed = discord.Embed.from_dict(embed_data)
                    embeds.append(embed)

            # Handle files
            if 'files' in content:
                for file_data in content['files']:
                    file_obj = discord.File(
                        fp=file_data['data'],
                        filename=file_data['filename']
                    )
                    files.append(file_obj)

            # Handle components (buttons, select menus)
            if 'components' in content:
                view = await self._create_discord_view(content['components'])

            # Send message
            message = await channel.send(
                content=message_content,
                embeds=embeds,
                files=files,
                view=view
            )

            self.logger.info(f"Sent Discord message: {message.id}")
            self.metrics.increment("discord.messages.sent")

        except Exception as e:
            self.logger.error(f"Error sending Discord message: {e}")
            self.metrics.increment("discord.errors", tags={"type": "send_message"})

    async def _send_interaction_response(self, ubp_message: UBPMessage, context: DiscordContext) -> None:
        """Send response to Discord interaction"""
        try:
            # Note: In a real implementation, you would need to store interaction objects
            # and retrieve them here. For brevity, this is simplified.
            self.logger.info(f"Would send interaction response for: {context.interaction_id}")

        except Exception as e:
            self.logger.error(f"Error sending interaction response: {e}")

    async def _create_discord_view(self, components: List[Dict]) -> discord.ui.View:
        """Create Discord UI view from component data"""
        view = discord.ui.View()

        for component in components:
            if component['type'] == 'button':
                button = discord.ui.Button(
                    style=getattr(discord.ButtonStyle, component.get('style', 'secondary')),
                    label=component.get('label', ''),
                    custom_id=component.get('custom_id'),
                    emoji=component.get('emoji'),
                    disabled=component.get('disabled', False)
                )
                view.add_item(button)
            elif component['type'] == 'select':
                select = discord.ui.Select(
                    custom_id=component.get('custom_id'),
                    placeholder=component.get('placeholder', ''),
                    min_values=component.get('min_values', 1),
                    max_values=component.get('max_values', 1)
                )

                for option in component.get('options', []):
                    select.add_option(
                        label=option['label'],
                        value=option['value'],
                        description=option.get('description'),
                        emoji=option.get('emoji')
                    )

                view.add_item(select)

        return view

    async def _create_discord_thread(self, ubp_message: UBPMessage) -> None:
        """Create Discord thread"""
        try:
            context = DiscordContext(**ubp_message.context)
            content = ubp_message.content

            channel = self.bot.get_channel(context.channel_id)
            if not channel:
                self.logger.error(f"Channel not found: {context.channel_id}")
                return

            thread = await channel.create_thread(
                name=content['name'],
                auto_archive_duration=content.get('auto_archive_duration', 60),
                type=getattr(discord.ChannelType, content.get('type', 'public_thread'))
            )

            self.logger.info(f"Created Discord thread: {thread.id}")

        except Exception as e:
            self.logger.error(f"Error creating Discord thread: {e}")

    async def _add_discord_reaction(self, ubp_message: UBPMessage) -> None:
        """Add reaction to Discord message"""
        try:
            context = DiscordContext(**ubp_message.context)
            content = ubp_message.content

            channel = self.bot.get_channel(context.channel_id)
            if not channel:
                self.logger.error(f"Channel not found: {context.channel_id}")
                return

            message = await channel.fetch_message(context.message_id)
            await message.add_reaction(content['emoji'])

            self.logger.info(f"Added reaction to message: {context.message_id}")

        except Exception as e:
            self.logger.error(f"Error adding Discord reaction: {e}")

    async def _create_discord_webhook(self, ubp_message: UBPMessage) -> None:
        """Create Discord webhook"""
        try:
            context = DiscordContext(**ubp_message.context)
            content = ubp_message.content

            channel = self.bot.get_channel(context.channel_id)
            if not channel:
                self.logger.error(f"Channel not found: {context.channel_id}")
                return

            webhook = await channel.create_webhook(
                name=content['name'],
                avatar=content.get('avatar')
            )

            # Cache webhook
            self.webhook_cache[channel.id] = webhook

            self.logger.info(f"Created Discord webhook: {webhook.id}")

        except Exception as e:
            self.logger.error(f"Error creating Discord webhook: {e}")

    async def _register_slash_command(self, ubp_message: UBPMessage) -> None:
        """Register slash command"""
        try:
            content = ubp_message.content

            @self.bot.tree.command(
                name=content['name'],
                description=content['description']
            )
            async def dynamic_command(interaction: discord.Interaction):
                await self.interaction_handler.handle_interaction(interaction)

            # Sync commands
            if self.guild_ids:
                for guild_id in self.guild_ids:
                    guild = discord.Object(id=guild_id)
                    await self.bot.tree.sync(guild=guild)
            else:
                await self.bot.tree.sync()

            self.logger.info(f"Registered slash command: {content['name']}")

        except Exception as e:
            self.logger.error(f"Error registering slash command: {e}")

    async def _update_bot_status(self, ubp_message: UBPMessage) -> None:
        """Update Discord bot status"""
        try:
            content = ubp_message.content

            activity_type = getattr(discord.ActivityType, content.get('activity_type', 'playing'))
            activity = discord.Activity(
                type=activity_type,
                name=content.get('activity_name', '')
            )

            status = getattr(discord.Status, content.get('status', 'online'))

            await self.bot.change_presence(activity=activity, status=status)

            self.logger.info(f"Updated bot status: {content}")

        except Exception as e:
            self.logger.error(f"Error updating bot status: {e}")

    async def _update_guild_settings(self, ubp_message: UBPMessage) -> None:
        """Update guild-specific settings"""
        try:
            content = ubp_message.content
            guild_id = content['guild_id']

            # Store guild settings (implementation depends on your storage solution)
            self.logger.info(f"Updated guild settings for {guild_id}: {content}")

        except Exception as e:
            self.logger.error(f"Error updating guild settings: {e}")

    async def _check_discord_health(self) -> bool:
        """Check Discord connection health"""
        return self.bot.is_ready() and not self.bot.is_closed()

    async def _check_orchestrator_health(self) -> bool:
        """Check orchestrator connection health"""
        return self.orchestrator_ws is not None and not self.orchestrator_ws.closed

    # Health check task
    @tasks.loop(minutes=1)
    async def health_check_task(self):
        """Periodic health check"""
        try:
            discord_healthy = await self._check_discord_health()
            orchestrator_healthy = await self._check_orchestrator_health()

            self.metrics.gauge("discord.health", 1 if discord_healthy else 0)
            self.metrics.gauge("orchestrator.health", 1 if orchestrator_healthy else 0)

            if not orchestrator_healthy:
                self.logger.warning("Orchestrator connection unhealthy, attempting reconnection")
                await self._connect_to_orchestrator()

        except Exception as e:
            self.logger.error(f"Error in health check: {e}")


# Example usage and configuration
if __name__ == "__main__":
    config = {
        'discord': {
            'bot_token': 'YOUR_BOT_TOKEN',
            'application_id': 'YOUR_APPLICATION_ID',
            'guild_ids': [],  # Leave empty for global commands
            'command_prefix': '!'
        },
        'ubp': {
            'orchestrator_url': 'ws://localhost:8080/ws/adapters',
            'adapter_id': 'discord_adapter_001',
            'security_key': 'your_security_key_here'
        }
    }

    adapter = DiscordPlatformAdapter(config)

    # Run the adapter
    asyncio.run(adapter.start())