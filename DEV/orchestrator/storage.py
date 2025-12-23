# FilePath: "/DEV/orchestrator/storage.py"
# Project: Unified Bot Protocol (UBP)
# Description: In-memory storage implementation for bot definitions and credentials.
#              Designed to be replaced by Redis/PostgreSQL in production.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.1.0.0"

from typing import Dict, List, Optional
import asyncio
from datetime import datetime

from .models import BotDefinition, BotCredentials

class BotStorage:
    """
    Handles bot definition and credential storage.

    Current Implementation: In-Memory (Dict)
    Future Roadmap: Migrate to Redis or PostgreSQL for persistence.
    """

    def __init__(self):
        # In-memory stores
        self._definitions: Dict[str, BotDefinition] = {}
        self._credentials: Dict[str, BotCredentials] = {}

        # Concurrency lock to ensure thread/task safety during writes
        self._lock = asyncio.Lock()

    async def save_bot_definition(self, bot: BotDefinition) -> None:
        """Stores or updates a bot definition."""
        async with self._lock:
            self._definitions[bot.bot_id] = bot

    async def get_bot_definition(self, bot_id: str) -> Optional[BotDefinition]:
        """Retrieves a bot definition by ID."""
        return self._definitions.get(bot_id)

    async def list_bot_definitions(self) -> List[BotDefinition]:
        """Lists all registered bots."""
        return list(self._definitions.values())

    async def delete_bot_definition(self, bot_id: str) -> None:
        """Removes a bot definition."""
        async with self._lock:
            self._definitions.pop(bot_id, None)

    async def save_bot_credentials(self, credentials: BotCredentials) -> None:
        """Securely stores bot credentials."""
        async with self._lock:
            self._credentials[credentials.bot_id] = credentials

    async def get_bot_credentials(self, bot_id: str) -> Optional[BotCredentials]:
        """Retrieves credentials for a specific bot."""
        return self._credentials.get(bot_id)

    async def validate_one_time_token(self, bot_id: str, token: str) -> bool:
        """
        Validates a One-Time-Token (OTT) for initial bot onboarding.
        Returns True if the token matches.
        """
        creds = await self.get_bot_credentials(bot_id)
        if not creds or not creds.one_time_token:
            return False
        return creds.one_time_token == token

    async def set_api_key(self, bot_id: str, api_key: str) -> None:
        """
        Rotates or sets the permanent API Key for a bot.
        Invalidates the One-Time-Token upon successful key generation.
        """
        async with self._lock:
            if bot_id in self._credentials:
                creds = self._credentials[bot_id]
                creds.api_key = api_key
                creds.one_time_token = None  # Security: Invalidate OTT immediately
                creds.last_used = datetime.utcnow()

    async def validate_api_key(self, bot_id: str, api_key: str) -> bool:
        """Validates the permanent API Key for authentication."""
        creds = await self.get_bot_credentials(bot_id)
        if not creds or not creds.api_key:
            return False
        return creds.api_key == api_key
