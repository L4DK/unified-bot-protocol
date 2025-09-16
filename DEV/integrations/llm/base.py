# integrations/llm/base.py
from typing import Dict, List, Any, Optional, Union
from ..core.universal_connector import (
    BaseIntegration,
    IntegrationMetadata,
    IntegrationType,
    ProtocolType,
    SecurityLevel,
    IntegrationCapability
)
from abc import abstractmethod
from enum import Enum
import json
import asyncio
from datetime import datetime

class LLMCapability(Enum):
    TEXT_GENERATION = "text.generate"
    TEXT_COMPLETION = "text.complete"
    TEXT_EMBEDDING = "text.embed"
    TEXT_CLASSIFICATION = "text.classify"
    IMAGE_GENERATION = "image.generate"
    IMAGE_EDITING = "image.edit"
    IMAGE_ANALYSIS = "image.analyze"
    AUDIO_TRANSCRIPTION = "audio.transcribe"
    AUDIO_GENERATION = "audio.generate"
    VIDEO_GENERATION = "video.generate"
    VIDEO_ANALYSIS = "video.analyze"
    FUNCTION_CALLING = "function.call"
    TOOL_USE = "tool.use"

class LLMProvider(Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    META = "meta"
    MICROSOFT = "microsoft"
    HUGGINGFACE = "huggingface"
    OPENROUTER = "openrouter"
    CUSTOM = "custom"

class BaseLLMIntegration(BaseIntegration):
    """Base class for LLM integrations"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_configs = {}
        self.active_conversations = {}
        self.function_registry = {}
        self.tool_registry = {}

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate text using the LLM"""
        pass

    @abstractmethod
    async def Image Generation(
        self,
        prompt: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate image using the LLM"""
        pass

    @abstractmethod
    async def analyze_image(
        self,
        image_data: bytes,
        prompt: str = None,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze image using the LLM"""
        pass

    @abstractmethod
    async def transcribe_audio(
        self,
        audio_data: bytes,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Transcribe audio using the LLM"""
        pass

    @abstractmethod
    async def generate_audio(
        self,
        text: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate audio using the LLM"""
        pass

    @abstractmethod
    async def Video Generation(
        self,
        prompt: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate video using the LLM"""
        pass

    @abstractmethod
    async def analyze_video(
        self,
        video_data: bytes,
        prompt: str = None,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze video using the LLM"""
        pass

    async def register_function(
        self,
        function_name: str,
        function_def: Dict[str, Any]
    ):
        """Register a function for LLM to call"""
        self.function_registry[function_name] = function_def

    async def register_tool(
        self,
        tool_name: str,
        tool_def: Dict[str, Any]
    ):
        """Register a tool for LLM to use"""
        self.tool_registry[tool_name] = tool_def

    async def start_conversation(
        self,
        conversation_id: str,
        parameters: Dict[str, Any] = None
    ):
        """Start a new conversation"""
        self.active_conversations[conversation_id] = {
            "messages": [],
            "parameters": parameters or {},
            "created_at": datetime.utcnow()
        }

    async def add_message(
        self,
        conversation_id: str,
        message: Dict[str, Any]
    ):
        """Add message to conversation"""
        if conversation_id not in self.active_conversations:
            await self.start_conversation(conversation_id)

        self.active_conversations[conversation_id]["messages"].append(message)

    async def get_conversation_history(
        self,
        conversation_id: str
    ) -> List[Dict[str, Any]]:
        """Get conversation history"""
        return self.active_conversations.get(
            conversation_id,
            {"messages": []}
        )["messages"]