"""
FilePath: "/DEV/orchestrator/storage.py"
Project: Unified Bot Protocol (UBP)
Description: Database storage implementation using SQLAlchemy.
Author: "Michael Landbo"
Date created: "31/12/2025"
Version: "1.2.1"
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db_models import Bot, BotCredential
from .models import BotCredentials, BotDefinition


class BotStorage:
    """
    Handles bot definition and credential storage using PostgreSQL.
    """

    async def _get_session(self) -> AsyncSession:
        return AsyncSession()

    # --- Definition Methods ---

    async def save_bot_definition(self, bot_def: BotDefinition) -> None:
        async with AsyncSession() as session:
            async with session.begin():
                stmt = select(Bot).where(Bot.bot_id == bot_def.bot_id)
                result = await session.execute(stmt)
                existing_bot = result.scalar_one_or_none()

                if existing_bot:
                    existing_bot.name = bot_def.name
                    existing_bot.description = bot_def.description
                    existing_bot.adapter_type = bot_def.adapter_type
                    # Nu korrekt type-hinted som List
                    existing_bot.capabilities = bot_def.capabilities
                    existing_bot.metadata_fields = bot_def.metadata
                else:
                    new_bot = Bot(bot_id=bot_def.bot_id, name=bot_def.name, description=bot_def.description, adapter_type=bot_def.adapter_type, capabilities=bot_def.capabilities, metadata_fields=bot_def.metadata, created_at=bot_def.created_at)
                    session.add(new_bot)

    async def get_bot_definition(self, bot_id: str) -> Optional[BotDefinition]:
        async with AsyncSession() as session:
            stmt = select(Bot).where(Bot.bot_id == bot_id)
            result = await session.execute(stmt)
            bot_row = result.scalar_one_or_none()

            if not bot_row:
                return None

            return BotDefinition(
                bot_id=bot_row.bot_id, name=bot_row.name, description=bot_row.description, adapter_type=bot_row.adapter_type, capabilities=bot_row.capabilities, created_at=bot_row.created_at, metadata=bot_row.metadata_fields  # Nu er dette en List
            )

    async def list_bot_definitions(self) -> List[BotDefinition]:
        async with AsyncSession() as session:
            stmt = select(Bot)
            result = await session.execute(stmt)
            bots = result.scalars().all()

            return [BotDefinition(bot_id=b.bot_id, name=b.name, description=b.description, adapter_type=b.adapter_type, capabilities=b.capabilities, created_at=b.created_at, metadata=b.metadata_fields) for b in bots]

    async def delete_bot_definition(self, bot_id: str) -> None:
        async with AsyncSession() as session:
            async with session.begin():
                await session.execute(delete(BotCredential).where(BotCredential.bot_id == bot_id))
                await session.execute(delete(Bot).where(Bot.bot_id == bot_id))

    # --- Credential Methods ---

    async def save_bot_credentials(self, creds: BotCredentials) -> None:
        async with AsyncSession() as session:
            async with session.begin():
                stmt = select(BotCredential).where(BotCredential.bot_id == creds.bot_id)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.api_key = creds.api_key
                    existing.one_time_token = creds.one_time_token
                    existing.last_used = creds.last_used
                else:
                    new_creds = BotCredential(bot_id=creds.bot_id, api_key=creds.api_key, one_time_token=creds.one_time_token, created_at=creds.created_at)
                    session.add(new_creds)

    async def get_bot_credentials(self, bot_id: str) -> Optional[BotCredentials]:
        async with AsyncSession() as session:
            stmt = select(BotCredential).where(BotCredential.bot_id == bot_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if not row:
                return None

            return BotCredentials(bot_id=row.bot_id, api_key=row.api_key, one_time_token=row.one_time_token, created_at=row.created_at, last_used=row.last_used)

    async def validate_one_time_token(self, bot_id: str, token: str) -> bool:
        creds = await self.get_bot_credentials(bot_id)
        if not creds or not creds.one_time_token:
            return False
        return creds.one_time_token == token

    async def set_api_key(self, bot_id: str, api_key: str) -> None:
        async with AsyncSession() as session:
            async with session.begin():
                stmt = select(BotCredential).where(BotCredential.bot_id == bot_id)
                result = await session.execute(stmt)
                creds = result.scalar_one_or_none()

                if creds:
                    creds.api_key = api_key
                    creds.one_time_token = None
                    creds.last_used = datetime.now(timezone.utc)

    async def validate_api_key(self, bot_id: str, api_key: str) -> bool:
        async with AsyncSession() as session:
            stmt = select(BotCredential.api_key).where(BotCredential.bot_id == bot_id)
            result = await session.execute(stmt)
            stored_key = result.scalar_one_or_none()
            return stored_key == api_key
