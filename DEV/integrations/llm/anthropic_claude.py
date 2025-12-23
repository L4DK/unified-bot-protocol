# FilePath: "/DEV/integrations/llm/anthropic_claude.py"
# Project: Unified Bot Protocol (UBP)
# Description: Integration implementation for Anthropic Claude (Text & Vision).
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.0.0"

from typing import Dict, Any, List, Optional
import base64
from datetime import datetime
import logging

# Ensure 'anthropic' is installed in your environment
try:
    import anthropic
    from anthropic import AsyncAnthropic
except ImportError:
    # This prevents the whole app from crashing if the optional dependency is missing
    AsyncAnthropic = None

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

class AnthropicClaudeIntegration(BaseLLMIntegration):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if AsyncAnthropic is None:
            raise ImportError("Anthropic library not found. Install with `pip install anthropic`.")

        self.client = AsyncAnthropic(api_key=config["api_key"])
        self.default_model = config.get("default_model", "claude-3-5-sonnet-20240620")

    @property
    def metadata(self) -> IntegrationMetadata:
        return IntegrationMetadata(
            id="anthropic_claude",
            name="Anthropic Claude Integration",
            type=IntegrationType.LLM,
            version="1.0.0",
            capabilities=[
                IntegrationCapability(
                    name=LLMCapability.TEXT_GENERATION.value,
                    description="Generate text using Claude models",
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
                    name=LLMCapability.IMAGE_ANALYSIS.value,
                    description="Analyze images using Claude Vision",
                    parameters={
                        "model": "str",
                        "temperature": "float"
                    },
                    returns={"analysis": "str"},
                    protocol=ProtocolType.REST,
                    security=SecurityLevel.TOKEN
                ),
                IntegrationCapability(
                    name=LLMCapability.FUNCTION_CALLING.value,
                    description="Use tools with Claude",
                    parameters={
                        "tools": "List[Dict]",
                        "tool_choice": "str"
                    },
                    returns={"result": "Dict"},
                    protocol=ProtocolType.REST,
                    security=SecurityLevel.TOKEN
                ),
            ],
            provider=LLMProvider.ANTHROPIC.value,
            documentation_url="https://docs.anthropic.com/",
            health_check_endpoint=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    async def generate_text(
        self,
        prompt: str,
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate text using Claude"""
        params = parameters or {}
        try:
            messages = [{"role": "user", "content": prompt}]

            # Add conversation history if available
            conversation_id = params.get("conversation_id")
            if conversation_id and conversation_id in self.active_conversations:
                history = await self.get_conversation_history(conversation_id)
                messages = self._format_conversation_history(history) + messages

            response = await self.client.messages.create(
                model=params.get("model", self.default_model),
                messages=messages,
                max_tokens=params.get("max_tokens", 1000),
                temperature=params.get("temperature", 0.7),
                # If tools are provided in params, pass them along (Claude 3 specific)
                tools=params.get("tools") if params.get("use_tools") else anthropic.NOT_GIVEN,
                tool_choice=params.get("tool_choice", "auto") if params.get("use_tools") else anthropic.NOT_GIVEN
            )

            # Handle tool use
            if response.stop_reason == "tool_use":
                tool_results = await self._handle_tool_use(response.content)
                return {
                    "text": response.content[0].text if response.content else "",
                    "tool_results": tool_results,
                    "model": response.model,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens
                    }
                }

            return {
                "text": response.content[0].text if response.content else "",
                "model": response.model,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens
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
        """Analyze image using Claude Vision"""
        params = parameters or {}
        try:
            # Convert image to base64
            base64_image = base64.b64encode(image_data).decode('utf-8')

            # Determine image type
            image_type = self._detect_image_type(image_data)

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": f"image/{image_type}",
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt or "Analyze this image in detail"
                        }
                    ]
                }
            ]

            response = await self.client.messages.create(
                model=params.get("model", self.default_model),
                messages=messages,
                max_tokens=params.get("max_tokens", 1000),
                temperature=params.get("temperature", 0.4)
            )

            return {
                "analysis": response.content[0].text if response.content else "",
                "model": response.model,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens
                }
            }

        except Exception as e:
            self.logger.error(f"Image analysis error: {str(e)}")
            raise

    async def _handle_tool_use(self, content: List) -> List[Dict]:
        """Handle tool use in Claude response"""
        tool_results = []

        for item in content:
            if item.type == "tool_use":
                tool_name = item.name
                tool_input = item.input

                # Execute the tool
                if tool_name in self.function_registry:
                    try:
                        # Placeholder for actual execution logic
                        # result = await self._execute_function(tool_name, tool_input)
                        result = {"status": "executed", "mock_output": "Tool executed successfully"}

                        tool_results.append({
                            "tool_use_id": item.id,
                            "tool_name": tool_name,
                            "result": result
                        })
                    except Exception as e:
                        tool_results.append({
                            "tool_use_id": item.id,
                            "tool_name": tool_name,
                            "error": str(e)
                        })

        return tool_results

    def _format_conversation_history(self, history: List[Dict]) -> List[Dict]:
        """Format conversation history for Claude"""
        formatted_messages = []

        for msg in history:
            message = msg.get("message", {})
            role = "user" if message.get("type") == "user" else "assistant"

            formatted_messages.append({
                "role": role,
                "content": message.get("content", "")
            })

        return formatted_messages

    def _detect_image_type(self, image_data: bytes) -> str:
        """Detect image type from binary data headers"""
        if image_data.startswith(b'\xff\xd8\xff'):
            return "jpeg"
        elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return "png"
        elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
            return "gif"
        elif image_data.startswith(b'RIFF') and b'WEBP' in image_data[:12]:
            return "webp"
        else:
            return "jpeg"  # Default fallback

    # -- Unsupported Capabilities --

    async def generate_image(self, prompt: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Claude doesn't support image generation directly"""
        raise NotImplementedError("Claude doesn't support image generation")

    async def transcribe_audio(self, audio_data: bytes, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Claude doesn't support audio transcription directly"""
        raise NotImplementedError("Claude doesn't support audio transcription")

    async def generate_audio(self, text: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Claude doesn't support audio generation directly"""
        raise NotImplementedError("Claude doesn't support audio generation")

    async def generate_video(self, prompt: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Claude doesn't support video generation directly"""
        raise NotImplementedError("Claude doesn't support video generation")

    async def analyze_video(self, video_data: bytes, prompt: str = None, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Claude doesn't support video analysis directly"""
        raise NotImplementedError("Claude doesn't support video analysis")

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
        elif capability_name == LLMCapability.FUNCTION_CALLING.value:
            return await self.generate_text(
                parameters["prompt"],
                {**parameters.get("parameters", {}), "use_tools": True}
            )
        else:
            raise ValueError(f"Unsupported capability: {capability_name}")
