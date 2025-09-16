# integrations/llm/google_gemini.py
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
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import base64
from datetime import datetime

class GoogleGeminiIntegration(BaseLLMIntegration):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        genai.configure(api_key=config["api_key"])
        self.default_model = config.get("default_model", "gemini-pro")
        self.vision_model = config.get("vision_model", "gemini-pro-vision")

        # Initialize models
        self.text_model = genai.GenerativeModel(self.default_model)
        self.vision_model_instance = genai.GenerativeModel(self.vision_model)

        # Safety settings
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
                # Add other capabilities...
            ],
            provider=LLMProvider.GOOGLE.value,
            documentation_url="https://ai.google.dev/docs",
            health_check_endpoint=None,
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

            response = await self.text_model.generate_content_async(
                prompt,
                generation_config=generation_config,
                safety_settings=self.safety_settings
            )

            return {
                "text": response.text,
                "model": self.default_model,
                "usage": {
                    "prompt_tokens": response.usage_metadata.prompt_token_count,
                    "completion_tokens": response.usage_metadata.candidates_token_count,
                    "total_tokens": response.usage_metadata.total_token_count
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
            # Convert image to PIL Image
            from PIL import Image
            import io

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

            return {
                "analysis": response.text,
                "model": self.vision_model,
                "usage": {
                    "prompt_tokens": response.usage_metadata.prompt_token_count,
                    "completion_tokens": response.usage_metadata.candidates_token_count,
                    "total_tokens": response.usage_metadata.total_token_count
                }
            }

        except Exception as e:
            self.logger.error(f"Image analysis error: {str(e)}")
            raise

    async def Image Generation(
        self,
        prompt: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Gemini doesn't support image generation directly"""
        raise NotImplementedError("Gemini doesn't support image generation")

    async def transcribe_audio(
        self,
        audio_data: bytes,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Gemini doesn't support audio transcription directly"""
        raise NotImplementedError("Gemini doesn't support audio transcription")

    async def generate_audio(
        self,
        text: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Gemini doesn't support audio generation directly"""
        raise NotImplementedError("Gemini doesn't support audio generation")

    async def Video Generation(
        self,
        prompt: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Gemini doesn't support video generation directly"""
        raise NotImplementedError("Gemini doesn't support video generation")

    async def analyze_video(
        self,
        video_data: bytes,
        prompt: str = None,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze video using Gemini (if supported)"""
        # This would need to be implemented when Gemini supports video analysis
        raise NotImplementedError("Video analysis not yet supported")

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