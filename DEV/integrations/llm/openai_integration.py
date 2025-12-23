# FilePath: "/DEV/integrations/llm/openai_integration.py"
# Project: Unified Bot Protocol (UBP)
# Description: Integration implementation for OpenAI (GPT, DALL-E, Whisper, TTS).
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.0.0"

from typing import Dict, Any, List, Optional
import base64
import os
from datetime import datetime
import logging

# Ensure 'openai' and 'tiktoken' are installed
try:
    import openai
    from openai import AsyncOpenAI
    import tiktoken
except ImportError:
    AsyncOpenAI = None
    tiktoken = None

# Relative imports from base
try:
    from .base import (
        BaseLLMIntegration,
        IntegrationMetadata,
        IntegrationType,
        ProtocolType,
        SecurityLevel,
        IntegrationCapability,
        LLMCapability,
        LLMProvider
    )
except ImportError:
    # Fallback for testing
    from integrations.llm.base import (
        BaseLLMIntegration,
        IntegrationMetadata,
        IntegrationType,
        ProtocolType,
        SecurityLevel,
        IntegrationCapability,
        LLMCapability,
        LLMProvider
    )

class OpenAIIntegration(BaseLLMIntegration):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if AsyncOpenAI is None:
            raise ImportError("OpenAI library not found. Install with `pip install openai tiktoken`.")

        self.client = AsyncOpenAI(api_key=config["api_key"])
        self.default_model = config.get("default_model", "gpt-4-turbo")

    @property
    def metadata(self) -> IntegrationMetadata:
        return IntegrationMetadata(
            id="openai",
            name="OpenAI Integration",
            type=IntegrationType.LLM,
            version="1.0.0",
            capabilities=[
                IntegrationCapability(
                    name=LLMCapability.TEXT_GENERATION.value,
                    description="Generate text using OpenAI models",
                    parameters={
                        "model": "str",
                        "temperature": "float",
                        "max_tokens": "int"
                    },
                    returns={"text": "str"},
                    protocol=ProtocolType.REST,
                    security=SecurityLevel.TOKEN
                ),
                IntegrationCapability(
                    name=LLMCapability.IMAGE_GENERATION.value,
                    description="Generate images using DALL-E",
                    parameters={
                        "model": "str",
                        "size": "str",
                        "quality": "str"
                    },
                    returns={"images": "List[str]"},
                    protocol=ProtocolType.REST,
                    security=SecurityLevel.TOKEN
                ),
                IntegrationCapability(
                    name=LLMCapability.AUDIO_TRANSCRIPTION.value,
                    description="Transcribe audio using Whisper",
                    parameters={"file": "bytes"},
                    returns={"text": "str"},
                    protocol=ProtocolType.REST,
                    security=SecurityLevel.TOKEN
                )
            ],
            provider=LLMProvider.OPENAI.value,
            documentation_url="https://platform.openai.com/docs",
            health_check_endpoint="https://api.openai.com/v1/models",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    async def generate_text(
        self,
        prompt: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate text using OpenAI"""
        params = parameters or {}
        try:
            response = await self.client.chat.completions.create(
                model=params.get("model", self.default_model),
                messages=[{"role": "user", "content": prompt}],
                temperature=params.get("temperature", 0.7),
                max_tokens=params.get("max_tokens", 1000),
                tools=self._get_available_tools() if self._get_available_tools() else None,
                tool_choice=params.get("tool_choice", "auto") if self._get_available_tools() else None
            )

            return {
                "text": response.choices[0].message.content,
                "usage": dict(response.usage) if response.usage else {},
                "model": response.model
            }

        except Exception as e:
            self.logger.error(f"Text generation error: {str(e)}")
            raise

    async def generate_image(
        self,
        prompt: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate image using DALL-E"""
        params = parameters or {}
        try:
            response = await self.client.images.generate(
                model=params.get("model", "dall-e-3"),
                prompt=prompt,
                size=params.get("size", "1024x1024"),
                quality=params.get("quality", "standard"),
                n=params.get("n", 1)
            )

            return {
                "images": [img.url for img in response.data],
                "model": "dall-e-3"
            }

        except Exception as e:
            self.logger.error(f"Image generation error: {str(e)}")
            raise

    async def analyze_image(
        self,
        image_data: bytes,
        prompt: str = None,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze image using GPT-4 Vision"""
        params = parameters or {}
        try:
            # Convert image to base64
            base64_image = base64.b64encode(image_data).decode('utf-8')

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or "Analyze this image"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]

            response = await self.client.chat.completions.create(
                model="gpt-4-turbo", # or gpt-4-vision-preview
                messages=messages,
                max_tokens=params.get("max_tokens", 300)
            )

            return {
                "analysis": response.choices[0].message.content,
                "usage": dict(response.usage) if response.usage else {},
                "model": response.model
            }

        except Exception as e:
            self.logger.error(f"Image analysis error: {str(e)}")
            raise

    async def transcribe_audio(
        self,
        audio_data: bytes,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Transcribe audio using Whisper"""
        params = parameters or {}
        temp_file = "temp_audio.mp3"
        try:
            # Save audio data to temporary file (OpenAI library needs a file-like object with name)
            with open(temp_file, "wb") as f:
                f.write(audio_data)

            with open(temp_file, "rb") as audio_file:
                response = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=params.get("language"),
                    prompt=params.get("prompt")
                )

            return {
                "text": response.text,
                "model": "whisper-1"
            }

        except Exception as e:
            self.logger.error(f"Audio transcription error: {str(e)}")
            raise
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    async def generate_audio(
        self,
        text: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate audio using TTS"""
        params = parameters or {}
        try:
            response = await self.client.audio.speech.create(
                model=params.get("model", "tts-1"),
                voice=params.get("voice", "alloy"),
                input=text
            )

            # Get audio data
            # OpenAI returns a binary response content
            audio_data = response.content

            return {
                "audio_data": audio_data,
                "model": "tts-1",
                "format": "mp3"
            }

        except Exception as e:
            self.logger.error(f"Audio generation error: {str(e)}")
            raise

    # -- Unsupported Capabilities --

    async def generate_video(self, prompt: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """OpenAI (public API) doesn't support video generation directly yet (Sora is closed beta)"""
        raise NotImplementedError("OpenAI doesn't support video generation yet")

    async def analyze_video(self, video_data: bytes, prompt: str = None, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """OpenAI (public API) doesn't support video analysis directly yet"""
        raise NotImplementedError("OpenAI doesn't support video analysis yet")

    # -- Helpers --

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """Get available tools for the model"""
        tools = []

        # Add registered functions as tools
        for name, func_def in self.function_registry.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": func_def.get("description", ""),
                    "parameters": func_def.get("parameters", {})
                }
            })

        # Add registered tools
        tools.extend(self.tool_registry.values())

        return tools

    async def _count_tokens(
        self,
        text: str,
        model: str = None
    ) -> int:
        """Count tokens in text"""
        if tiktoken is None:
            return len(text.split()) * 1.3 # Fallback

        try:
            encoding = tiktoken.encoding_for_model(
                model or self.default_model
            )
            return len(encoding.encode(text))
        except Exception:
            # Fallback to approximate count
            return int(len(text.split()) * 1.3)

    # -- Main Executor --

    async def execute_capability(
        self,
        capability_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a specific capability"""
        if capability_name == LLMCapability.TEXT_GENERATION.value:
            return await self.generate_text(
                parameters["prompt"],
                parameters.get("parameters", {})
            )
        elif capability_name == LLMCapability.IMAGE_GENERATION.value:
            return await self.generate_image(
                parameters["prompt"],
                parameters.get("parameters", {})
            )
        elif capability_name == LLMCapability.AUDIO_TRANSCRIPTION.value:
            return await self.transcribe_audio(
                parameters["audio_data"],
                parameters.get("parameters", {})
            )
        else:
            raise ValueError(f"Unsupported capability: {capability_name}")
