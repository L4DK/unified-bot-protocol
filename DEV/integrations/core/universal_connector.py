# FilePath: "/DEV/integrations/core/universal_connector.py"
# Projekt: Unified Bot Protocol (UBP)
# Beskrivelse: Base class for all external integrations.
#              Definerer standard interface for Capabilities, Metadata og Lifecycle.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.0.0"

from typing import Dict, List, Any, Optional, Union, Type
from enum import Enum
from abc import ABC, abstractmethod
import asyncio
import aiohttp
import json
import logging
from pydantic import BaseModel
import websockets
from datetime import datetime
import ssl
import certifi
from cryptography.fernet import Fernet
import hashlib
import hmac
import base64

logger = logging.getLogger(__name__)

class IntegrationType(Enum):
    LLM = "llm"
    IOT = "iot"
    API = "api"
    SMART_DEVICE = "smart_device"
    MEDIA = "media"
    COMMUNICATION = "communication"
    SENSOR = "sensor"
    DATABASE = "database"
    BLOCKCHAIN = "blockchain"
    SECURITY = "security"
    AI_SERVICE = "ai_service"
    AUTOMATION = "automation"

class ProtocolType(Enum):
    REST = "rest"
    WEBSOCKET = "websocket"
    MQTT = "mqtt"
    GRPC = "grpc"
    GRAPHQL = "graphql"
    SOAP = "soap"
    COAP = "coap"
    AMQP = "amqp"
    CUSTOM = "custom"

class SecurityLevel(Enum):
    NONE = "none"
    BASIC = "basic"
    TOKEN = "token"
    OAUTH = "oauth"
    CERTIFICATE = "certificate"
    CUSTOM = "custom"

class IntegrationCapability(BaseModel):
    """Defines what an integration can do"""
    name: str
    description: str
    parameters: Dict[str, Any]
    returns: Dict[str, Any]
    protocol: ProtocolType
    security: SecurityLevel
    rate_limit: Optional[int] = None
    timeout: int = 30

class IntegrationMetadata(BaseModel):
    """Metadata for an integration"""
    id: str
    name: str
    type: IntegrationType
    version: str
    capabilities: List[IntegrationCapability]
    provider: str
    documentation_url: str
    health_check_endpoint: Optional[str]
    created_at: datetime
    updated_at: datetime

class BaseIntegration(ABC):
    """
    Abstract Base Class for all integrations.
    Provides standard lifecycle management (init, shutdown) and security helpers.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connections: Dict[str, websockets.WebSocketClientProtocol] = {}

        # Internal encryption key for sensitive data in memory
        self.encryption_key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.encryption_key)

    @property
    @abstractmethod
    def metadata(self) -> IntegrationMetadata:
        """Integration metadata"""
        pass

    async def initialize(self):
        """Initialize the integration"""
        self.logger = logging.getLogger(f"ubp.integration.{self.metadata.id}")
        self.logger.info(f"Initializing integration: {self.metadata.name}")

        self.session = aiohttp.ClientSession()

        try:
            await self._setup_security()
            await self._verify_connection()
            await self._register_capabilities()
            self.logger.info("Initialization complete.")
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            await self.shutdown() # Ensure cleanup on failure
            raise

    async def shutdown(self):
        """Shutdown the integration"""
        if self.session:
            await self.session.close()

        # Close all active websockets
        for name, ws in self.ws_connections.items():
            try:
                await ws.close()
            except Exception as e:
                if self.logger: self.logger.warning(f"Error closing WS {name}: {e}")

    async def _setup_security(self):
        """Setup security credentials"""
        security = self.config.get("security", {})
        sec_type = security.get("type")

        if sec_type == SecurityLevel.OAUTH.value:
            await self._setup_oauth()
        elif sec_type == SecurityLevel.CERTIFICATE.value:
            await self._setup_certificates()

    async def _verify_connection(self):
        """Verify connection to the service"""
        endpoint = self.metadata.health_check_endpoint
        if not endpoint:
            return

        try:
            async with self.session.get(endpoint, timeout=5) as response:
                if response.status not in (200, 204):
                    raise ConnectionError(f"Health check failed: {response.status}")
        except Exception as e:
            self.logger.error(f"Connection verification failed: {str(e)}")
            raise

    async def _register_capabilities(self):
        """
        Register integration capabilities with UBP.
        (Placeholder for future capability registry logic)
        """
        pass

    # Optional overrides for specific auth flows
    async def _setup_oauth(self):
        pass

    async def _setup_certificates(self):
        pass

    @abstractmethod
    async def execute_capability(
        self,
        capability_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a specific capability (action)"""
        pass

    # Helper methods for data transformation
    async def transform_request(
        self,
        data: Dict[str, Any],
        target_format: str
    ) -> Dict[str, Any]:
        """Transform request data to target format (Default: no-op)"""
        return data

    async def transform_response(
        self,
        data: Dict[str, Any],
        target_format: str
    ) -> Dict[str, Any]:
        """Transform response data to UBP format (Default: no-op)"""
        return data
