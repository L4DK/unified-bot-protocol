"""
FilePath: "/adapters/discord/discord_adapter.py"
Project: Unified Bot Protocol (UBP)
Component: Discord Adapter Implementation
Version: 1.1.0 (Refactored for BaseAdapter 1.3.0)
"""

import discord
import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from discord.ext import commands

# Vi importerer fra din nye struktur
from adapters.base_adapter import (
    PlatformAdapter,
    AdapterCapabilities,
    AdapterMetadata,
    AdapterContext,
    PlatformCapability,
    SendResult,
    SimpleSendResult,
    AdapterStatus,
    MessagePriority
)

class DiscordAdapter(PlatformAdapter):
    """
    Official UBP Discord Adapter.
    Inherits from PlatformAdapter to ensure 100% compatibility with UBP Runtime.
    """

    def __init__(self, config: Dict[str, Any]):
        # Initialiser base class først (håndterer køer, metrics, connection loop)
        super().__init__(config)

        # Discord Specifik Config
        self.discord_config = config.get('discord', {})
        self.bot_token = self.discord_config.get('bot_token')
        self.cmd_prefix = self.discord_config.get('command_prefix', '!')

        # Setup Discord Bot Client
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True

        self.client = commands.Bot(command_prefix=self.cmd_prefix, intents=intents)

        # Intern state
        self._discord_task: Optional[asyncio.Task] = None

    # --- Implementering af Abstrakte Egenskaber ---

    @property
    def platform_name(self) -> str:
        return "discord"

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Definerer hvad denne adapter kan"""
        return AdapterCapabilities(
            supported_capabilities={
                PlatformCapability.SEND_MESSAGE,
                PlatformCapability.SEND_IMAGE,
                PlatformCapability.SEND_REACTION,
                PlatformCapability.USER_PRESENCE,
                PlatformCapability.REPLY_MESSAGE
            },
            max_message_length=2000,
            supported_media_types=["image/png", "image/jpeg", "image/gif", "application/pdf"],
            rate_limits={"message.send": 50} # 50 requests per second (discord limit varriarer)
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="discord",
            display_name="Discord Integration",
            version="1.1.0",
            author="Michael Landbo",
            description="Full implementation of Discord for UBP",
            supports_real_time=True,
            supports_reactions=True
        )

    # --- Lifecycle Methods ---

    async def _setup_platform(self) -> None:
        """Klargør Discord klienten. Kaldes automatisk af base.start()"""

        @self.client.event
        async def on_ready():
            self.logger.info(f"Discord connected as {self.client.user} (ID: {self.client.user.id})")
            # Vi sætter ikke self.status = CONNECTED her, det styrer base-klassen når WS er klar.

        @self.client.event
        async def on_message(message):
            # Ignorer egne beskeder
            if message.author == self.client.user:
                return

            await self._handle_discord_message(message)

        # Vi starter selve discord-loopet som en baggrunds-task, så det ikke blokerer UBP
        self._discord_task = asyncio.create_task(self.client.start(self.bot_token))

    async def stop(self) -> None:
        """Overrider stop for at lukke Discord forbindelsen pænt"""
        if self._discord_task:
            await self.client.close()
            self._discord_task.cancel()
        await super().stop()

    # --- Core Logic: Send Message (UBP -> Discord) ---

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """Implementerer den faktiske afsendelse til Discord"""
        try:
            target_channel_id = context.channel_id

            # Hvis vi ikke har et kanal-ID, kan vi ikke sende (medmindre vi slår bruger op)
            if not target_channel_id:
                 return SimpleSendResult(
                    success=False,
                    error_message="Missing 'channel_id' in context"
                )

            channel = self.client.get_channel(int(target_channel_id))
            if not channel:
                # Prøv at fetch hvis den ikke er i cache
                try:
                    channel = await self.client.fetch_channel(int(target_channel_id))
                except Exception:
                    return SimpleSendResult(
                        success=False,
                        error_message=f"Channel {target_channel_id} not found on Discord"
                    )

            # Send selve beskeden
            content = message.get("content", "")
            # Her kan vi udvide med embeds, filer osv. baseret på message dict

            discord_msg = await channel.send(content)

            return SimpleSendResult(
                success=True,
                platform_message_id=str(discord_msg.id),
                details={"guild_id": getattr(channel, "guild", None) and str(channel.guild.id)}
            )

        except Exception as e:
            self.logger.error(f"Failed to send to Discord: {e}")
            return SimpleSendResult(
                success=False,
                error_message=str(e)
            )

    # --- Core Logic: Handle Events (Discord -> UBP) ---

    async def _handle_discord_message(self, message: discord.Message):
        """Konverterer Discord besked til UBP format og sender til Runtime"""

        # Byg Context
        context = AdapterContext(
            tenant_id="default", # I multi-tenant setup ville dette komme fra config/db
            user_id=str(message.author.id),
            channel_id=str(message.channel.id),
            extras={
                "username": message.author.name,
                "guild_id": str(message.guild.id) if message.guild else None
            }
        )

        # Byg Payload
        payload = {
            "type": "text", # Kunne være 'image' hvis attachments
            "content": message.content,
            "metadata": {
                "source": "discord",
                "ts": message.created_at.isoformat()
            }
        }

        # Brug base-klassens metode til at sende til Orchestrator/Runtime
        # Bemærk: I denne arkitektur sender adapteren normalt til en kø eller via WS til orchestrator.
        # Hvis vi kører "standalone" med runtime.py som vi lavede før, kan vi injicere beskeden der.
        # Men for nu, lad os antage standard UBP flow:

        # Vi lægger den i indgående kø (hvis implementeret) eller sender via WS
        # Her bruger vi base-klassens _send_to_orchestrator hvis den er forbundet.
        if self.connected:
            await self._send_to_orchestrator({
                "type": "user_message",
                "context": context.to_dict(),
                "payload": payload
            })
            self.metrics["messages_received"] += 1

    async def handle_platform_event(self, event: Dict[str, Any]) -> None:
        # Placeholder for Webhook events hvis nødvendigt
        pass

    async def handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Håndterer specifikke kommandoer fra Orchestrator (udover send_message)"""
        cmd_type = command.get("command")

        if cmd_type == "get_user_info":
            user_id = command.get("user_id")
            user = self.client.get_user(int(user_id))
            if user:
                return {"username": user.name, "bot": user.bot}

        return {"error": "Unknown command"}
