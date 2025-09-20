# orchestrator/models.py
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import uuid

class BotDefinition(BaseModel):
    """Bot definition model for registration and management"""
    bot_id: str = Field(default_factory=lambda: f"bot-{uuid.uuid4().hex[:8]}")
    name: str
    description: Optional[str] = None
    adapter_type: str
    capabilities: List[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, str] = Field(default_factory=dict)

class BotRegistrationResponse(BaseModel):
    """Response model for bot registration"""
    bot_id: str
    one_time_registration_token: str
    created_at: datetime

class BotCredentials(BaseModel):
    """Internal model for bot credentials"""
    bot_id: str
    api_key: str
    one_time_token: Optional[str] = None
    created_at: datetime
    last_used: Optional[datetime] = None
