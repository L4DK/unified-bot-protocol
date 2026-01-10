"""
FilePath: "/DEV/orchestrator/models.py"
Project: Unified Bot Protocol (UBP)
Description: Pydantic models defining the data structures for Bots AND Standardized Messages.
            This acts as the "Universal Language" (Esperanto) for the system.
Author: "Michael Landbo"
Date created: "21/12/2025"
Date Modified: "31/12/2025"
Version: "1.2.0"
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

# ==========================================
# 1. BOT MANAGEMENT MODELS
# ==========================================


class UBPBotDefinition(BaseModel):
    """
    Bot definition model for registration and management.
    Defines the static properties of a bot (identity, capabilities, etc.).
    """

    bot_id: str = Field(default_factory=lambda: f"bot-{uuid.uuid4().hex[:8]}")
    name: str
    description: Optional[str] = None
    adapter_type: str  # e.g., 'telegram', 'slack', 'iot'
    capabilities: List[str]  # e.g., ['send_message', 'receive_file']
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UBPBotRegistrationResponse(BaseModel):
    """
    Response model returned when a new bot is registered.
    Includes the secure One-Time-Token (OTT) for initial onboarding.
    """

    bot_id: str
    one_time_registration_token: str
    created_at: datetime


class UBPBotCredentials(BaseModel):
    """
    Internal model for storing secure bot credentials.
    Used by the storage layer to manage authentication secrets.
    """

    bot_id: str
    api_key: str  # The permanent API key used for C2 authentication
    one_time_token: Optional[str] = None  # Used only during initial handshake
    created_at: datetime
    last_used: Optional[datetime] = None


# ==========================================
# 2. UNIFIED MESSAGE MODELS (The "Universal Language")
# ==========================================


class UBPMessageType(str, Enum):
    """Types of content a message can contain."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    COMMAND = "command"  # System commands like "/help" or internal signals
    EVENT = "event"  # IoT events, alerts, etc.


class UBPParticipant(BaseModel):
    """Represents a sender or recipient in a platform-agnostic way."""

    id: str  # Platform specific ID (e.g., Discord User ID)
    name: Optional[str] = None
    platform: str  # e.g., "discord", "slack", "console"
    role: Optional[str] = "user"  # user, bot, system, admin
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UBPMediaAttachment(BaseModel):
    """Represents a file attachment."""

    url: Optional[str] = None
    content_type: str  # e.g., "image/png"
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    base64_data: Optional[str] = None  # For small files passed inline


class UBPUnifiedMessage(BaseModel):
    """
    THE CORE STANDARD: All adapters must convert to/from this format.
    This allows routing between disparate platforms (e.g. WhatsApp -> Discord).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Content
    type: UBPMessageType = UBPMessageType.TEXT
    text: Optional[str] = None
    attachments: List[UBPMediaAttachment] = Field(default_factory=list)

    # Routing Info
    sender: UBPParticipant
    recipient: Optional[UBPParticipant] = None  # Direct Message target
    channel_id: Optional[str] = None  # Group/Channel context

    # Context
    conversation_id: Optional[str] = None  # Thread ID for context retention
    reply_to_id: Optional[str] = None  # ID of message being replied to

    # Meta
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Raw platform data (optional)

    class Config:
        use_enum_values = True
