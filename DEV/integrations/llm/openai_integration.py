# integrations/llm/openai_integration.py
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
import openai
from openai import AsyncOpenAI
import base64
import tiktoken

class OpenAIIntegration(BaseLLMIntegration):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client = AsyncOpenAI(api_key=config["api_key"])
        self.default_model = config.get("default_model", "gpt-4")

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
                # Add other capabilities...
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
                tools=self._get_available_tools(),
                tool_choice=params.get("tool_choice", "auto")
            )

            return {
                "text": response.choices[0].message.content,
                "usage": response.usage.dict(),
                "model": response.model
            }

        except Exception as e:
            self.logger.error(f"Text generation error: {str(e)}")
            raise

    async def Image Generation(
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
                model="gpt-4-vision-preview",
                messages=messages,
                max_tokens=params.get("max_tokens", 300)
            )

            return {
                "analysis": response.choices[0].message.content,
                "usage": response.usage.dict(),
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
        try:
            # Save audio data to temporary file
            temp_file = "temp_audio.mp3"
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
            # Cleanup
            import os
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
            audio_data = await response.read()

            return {
                "audio_data": audio_data,
                "model": "tts-1",
                "format": "mp3"
            }

        except Exception as e:
            self.logger.error(f"Audio generation error: {str(e)}")
            raise

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """Get available tools for the model"""
        tools = []

        # Add registered functions as tools
        for name, func_def in self.function_registry.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    **func_def
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
        try:
            encoding = tiktoken.encoding_for_model(
                model or self.default_model
            )
            return len(encoding.encode(text))
        except Exception:
            # Fallback to approximate count
            return len(text.split()) * 1.3