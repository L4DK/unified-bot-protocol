# orchestrator/storage.py
from typing import Dict, List, Optional
import asyncio
from datetime import datetime

from .models import BotDefinition, BotCredentials

class BotStorage:
    """
    Handles bot definition and credential storage.
    Note: This is an in-memory implementation. In production,
    use a proper database like PostgreSQL or Redis.
    """
    def __init__(self):
        self._definitions: Dict[str, BotDefinition] = {}
        self._credentials: Dict[str, BotCredentials] = {}
        self._lock = asyncio.Lock()

    async def save_bot_definition(self, bot: BotDefinition) -> None:
        async with self._lock:
            self._definitions[bot.bot_id] = bot

    async def get_bot_definition(self, bot_id: str) -> Optional[BotDefinition]:
        return self._definitions.get(bot_id)

    async def list_bot_definitions(self) -> List[BotDefinition]:
        return list(self._definitions.values())

    async def delete_bot_definition(self, bot_id: str) -> None:
        async with self._lock:
            self._definitions.pop(bot_id, None)

    async def save_bot_credentials(self, credentials: BotCredentials) -> None:
        async with self._lock:
            self._credentials[credentials.bot_id] = credentials

    async def get_bot_credentials(self, bot_id: str) -> Optional[BotCredentials]:
        return self._credentials.get(bot_id)

    async def validate_one_time_token(self, bot_id: str, token: str) -> bool:
        creds = await self.get_bot_credentials(bot_id)
        if not creds or not creds.one_time_token:
            return False
        return creds.one_time_token == token

    async def set_api_key(self, bot_id: str, api_key: str) -> None:
        async with self._lock:
            if bot_id in self._credentials:
                self._credentials[bot_id].api_key = api_key
                self._credentials[bot_id].one_time_token = None  # Invalidate token
                self._credentials[bot_id].last_used = datetime.utcnow()

    async def validate_api_key(self, bot_id: str, api_key: str) -> bool:
        creds = await self.get_bot_credentials(bot_id)
        if not creds or not creds.api_key:
            return False
        return creds.api_key == api_key