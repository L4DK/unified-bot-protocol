# FilePath: "/DEV/orchestrator/models.py"
# Project: Unified Bot Protocol (UBP)
# Description: Pydantic models defining the data structures for Bot definitions, registration, and credentials.
# Author: "Michael Landbo"
# Date created: "2025/09/19"
# Date Modified: "2025/12/21"
# Version: "v.1.0.0"

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import uuid

class BotDefinition(BaseModel):
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
    metadata: Dict[str, str] = Field(default_factory=dict)

class BotRegistrationResponse(BaseModel):
    """
    Response model returned when a new bot is registered.
    Includes the secure One-Time-Token (OTT) for initial onboarding.
    """
    bot_id: str
    one_time_registration_token: str
    created_at: datetime

class BotCredentials(BaseModel):
    """
    Internal model for storing secure bot credentials.
    Used by the storage layer to manage authentication secrets.
    """
    bot_id: str
    api_key: str  # The permanent API key used for C2 authentication
    one_time_token: Optional[str] = None  # Used only during initial handshake
    created_at: datetime
    last_used: Optional[datetime] = None
