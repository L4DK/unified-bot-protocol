# FilePath: "/DEV/integrations/llm/google_gemini.py"
# Project: Unified Bot Protocol (UBP)
# Description: Integration implementation for Google Gemini (Text & Vision).
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.0.0"

from typing import Dict, Any, List, Optional
import base64
from datetime import datetime
import logging
import io

# Ensure 'google-generativeai' and 'Pillow' are installed
try:
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
    from PIL import Image
except ImportError:
    genai = None
    Image = None

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

class GoogleGeminiIntegration(BaseLLMIntegration):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if genai is None or Image is None:
            raise ImportError("Google Generative AI library or Pillow not found. Install with `pip install google-generativeai pillow`.")

        genai.configure(api_key=config["api_key"])
        self.default_model = config.get("default_model", "gemini-pro")
        self.vision_model = config.get("vision_model", "gemini-pro-vision")

        # Initialize models
        self.text_model = genai.GenerativeModel(self.default_model)
        self.vision_model_instance = genai.GenerativeModel(self.vision_model)

        # Safety settings (default: block medium and above)
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }

    @property
    def metadata(self) -> IntegrationMetadata:
        return IntegrationMetadata(
            id="google_gemini",
            name="Google Gemini Integration",
            type=IntegrationType.LLM,
            version="1.0.0",
            capabilities=[
                IntegrationCapability(
                    name=LLMCapability.TEXT_GENERATION.value,
                    description="Generate text using Gemini models",
                    parameters={
                        "model": "str",
                        "temperature": "float",
                        "max_output_tokens": "int"
                    },
                    returns={"text": "str"},
                    protocol=ProtocolType.REST,
                    security=SecurityLevel.TOKEN
                ),
                IntegrationCapability(
                    name=LLMCapability.IMAGE_ANALYSIS.value,
                    description="Analyze images using Gemini Vision",
                    parameters={
                        "model": "str",
                        "temperature": "float"
                    },
                    returns={"analysis": "str"},
                    protocol=ProtocolType.REST,
                    security=SecurityLevel.TOKEN
                ),
            ],
            provider=LLMProvider.GOOGLE.value,
            documentation_url="https://ai.google.dev/docs",
            health_check_endpoint=None, # Gemini doesn't have a simple public health endpoint without auth
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    async def generate_text(
        self,
        prompt: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate text using Gemini"""
        params = parameters or {}
        try:
            generation_config = genai.types.GenerationConfig(
                temperature=params.get("temperature", 0.7),
                max_output_tokens=params.get("max_output_tokens", 1000),
                top_p=params.get("top_p", 0.8),
                top_k=params.get("top_k", 40)
            )

            # Gemini-pro runs synchronously in the python SDK usually, but has an async method
            response = await self.text_model.generate_content_async(
                prompt,
                generation_config=generation_config,
                safety_settings=self.safety_settings
            )

            # Extract token counts if available (Gemini usage metadata structure varies by version)
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

            if hasattr(response, 'usage_metadata'):
                prompt_tokens = response.usage_metadata.prompt_token_count
                completion_tokens = response.usage_metadata.candidates_token_count
                total_tokens = response.usage_metadata.total_token_count

            return {
                "text": response.text,
                "model": self.default_model,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                }
            }

        except Exception as e:
            self.logger.error(f"Text generation error: {str(e)}")
            raise

    async def analyze_image(
        self,
        image_data: bytes,
        prompt: str = None,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze image using Gemini Vision"""
        params = parameters or {}
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))

            generation_config = genai.types.GenerationConfig(
                temperature=params.get("temperature", 0.4),
                max_output_tokens=params.get("max_output_tokens", 500)
            )

            content = [prompt or "Analyze this image", image]

            response = await self.vision_model_instance.generate_content_async(
                content,
                generation_config=generation_config,
                safety_settings=self.safety_settings
            )

            # Extract usage
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            if hasattr(response, 'usage_metadata'):
                prompt_tokens = response.usage_metadata.prompt_token_count
                completion_tokens = response.usage_metadata.candidates_token_count
                total_tokens = response.usage_metadata.total_token_count

            return {
                "analysis": response.text,
                "model": self.vision_model,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                }
            }

        except Exception as e:
            self.logger.error(f"Image analysis error: {str(e)}")
            raise

    # -- Unsupported Capabilities --

    async def generate_image(self, prompt: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Gemini doesn't support image generation directly (Imagen is separate API)"""
        raise NotImplementedError("Gemini doesn't support image generation")

    async def transcribe_audio(self, audio_data: bytes, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Gemini doesn't support audio transcription directly"""
        raise NotImplementedError("Gemini doesn't support audio transcription")

    async def generate_audio(self, text: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Gemini doesn't support audio generation directly"""
        raise NotImplementedError("Gemini doesn't support audio generation")

    async def generate_video(self, prompt: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Gemini doesn't support video generation directly"""
        raise NotImplementedError("Gemini doesn't support video generation")

    async def analyze_video(self, video_data: bytes, prompt: str = None, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Analyze video using Gemini (Not implemented in this basic integration)"""
        # Gemini 1.5 Pro supports video, but requires File API upload for large files
        raise NotImplementedError("Video analysis not yet supported in this integration")

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
        elif capability_name == LLMCapability.IMAGE_ANALYSIS.value:
            return await self.analyze_image(
                parameters["image_data"],
                parameters.get("prompt"),
                parameters.get("parameters", {})
            )
        else:
            raise ValueError(f"Unsupported capability: {capability_name}")
