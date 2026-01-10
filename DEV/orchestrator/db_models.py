"""
FilePath: "/DEV/orchestrator/db_models.py"
Project: Unified Bot Protocol (UBP)
Description: SQLAlchemy Database Models (Tables).
Author: "Michael Landbo"
Date created: "31/12/2025"
Version: "1.1.1"
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .database import BaseSettings

# pylint: disable=not-callable


# --- BOT MODELS ---
class Bot(BaseSettings):
    __tablename__ = "bots"
    bot_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    adapter_type: Mapped[str] = mapped_column(String(50))
    # Rettet: Mapped[List[str]] i stedet for dict, da capabilities typisk er en liste
    capabilities: Mapped[List[str]] = mapped_column(JSON, default=list)
    metadata_fields: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class BotCredential(BaseSettings):
    __tablename__ = "bot_credentials"
    bot_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    api_key: Mapped[str] = mapped_column(String(255), index=True)
    one_time_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# --- AUDIT MODEL ---
class AuditLogEntry(BaseSettings):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean, default=True)


# --- TASK MODEL ---
class TaskModel(BaseSettings):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    progress: Mapped[int] = mapped_column(default=0)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_fields: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
