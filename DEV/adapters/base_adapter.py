# FILEPATH: adapters/base_adapter.py
# PROJECT: Unified Bot Protocol (UBP)
# COMPONENT: Platform Adapter Base Classes & Registry
#
# LICENSE: Apache-2.0
# AUTHOR: Michael Landbo (Founder & BDFL of UBP)
#
# DESCRIPTION:
#   Defines the standard Platform Adapter interface and base implementation
#   for all UBP platform integrations. Includes adapter registry, capability
#   management, connection handling, and metrics collection.
#   Core foundation for Telegram, Slack, WhatsApp, and other platform adapters.
#
# VERSION: 1.3.1
# CREATED: 2025-09-16
# LAST EDIT: 2025-09-19
#
# CHANGELOG:
# - 1.3.0: Complete merger of robust connection handling, metrics, queue processing
#          with enhanced capability system and adapter registry
# - 1.2.0: Added comprehensive error handling and reconnection logic
# - 1.1.0: Added capability descriptors and adapter metadata
# - 1.0.0: Initial base adapter interface and registry

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Protocol, runtime_checkable, Set
from enum import Enum
from datetime import datetime, timedelta
import asyncio
import json
import logging
import uuid
import websockets
import aiohttp
from pydantic import BaseModel, Field
from dataclasses import dataclass

# =========================
# Core Enums & Data Models
# =========================

class PlatformCapability(Enum):
    """Standard capabilities across all UBP platform adapters"""
    # Message Operations
    SEND_MESSAGE = "message.send"
    EDIT_MESSAGE = "message.edit"
    DELETE_MESSAGE = "message.delete"
    FORWARD_MESSAGE = "message.forward"
    REPLY_MESSAGE = "message.reply"

    # Media Operations
    SEND_MEDIA = "media.send"
    SEND_DOCUMENT = "media.document"
    SEND_AUDIO = "media.audio"
    SEND_VIDEO = "media.video"
    SEND_IMAGE = "media.image"

    # Interactive Elements
    SEND_REACTION = "reaction.send"
    SEND_BUTTONS = "buttons.send"
    SEND_KEYBOARD = "keyboard.send"
    SEND_CAROUSEL = "carousel.send"

    # Thread & Channel Operations
    CREATE_THREAD = "thread.create"
    JOIN_CHANNEL = "channel.join"
    LEAVE_CHANNEL = "channel.leave"
    MANAGE_CHANNEL = "channel.manage"

    # User Operations
    USER_PROFILE = "user.profile"
    USER_PRESENCE = "user.presence"
    USER_TYPING = "user.typing"

    # Moderation & Control
    MODERATE_CONTENT = "content.moderate"
    BAN_USER = "user.ban"
    MUTE_USER = "user.mute"

    # Advanced Features
    STREAM_CONTROL = "stream.control"
    ANALYTICS = "analytics.fetch"
    WEBHOOK_SUPPORT = "webhook.support"
    REAL_TIME_EVENTS = "events.realtime"

class AdapterStatus(Enum):
    """Adapter lifecycle states"""
    INITIALIZING = "initializing"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    STOPPING = "stopping"
    STOPPED = "stopped"

class MessagePriority(Enum):
    """Message priority levels for queue processing"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

# =================
# Exception Classes
# =================

class AdapterError(Exception):
    """Base exception for adapter errors"""
    def __init__(self, message: str, error_code: str = "ADAPTER_ERROR", details: Optional[Dict] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}

class ConnectionError(AdapterError):
    """Connection-related adapter errors"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "CONNECTION_ERROR", details)

class AuthenticationError(AdapterError):
    """Authentication-related adapter errors"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "AUTH_ERROR", details)

class RateLimitError(AdapterError):
    """Rate limiting errors"""
    def __init__(self, message: str, retry_after: Optional[int] = None, details: Optional[Dict] = None):
        super().__init__(message, "RATE_LIMIT_ERROR", details)
        self.retry_after = retry_after

# ==================
# Protocol Interfaces
# ==================

@runtime_checkable
class SendResult(Protocol):
    """Result of a message send operation"""
    success: bool
    platform_message_id: Optional[str]
    error_message: Optional[str]
    details: Dict[str, Any]
    timestamp: datetime

@dataclass
class SimpleSendResult:
    """Simple implementation of SendResult"""
    success: bool
    platform_message_id: Optional[str] = None
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

# =================
# Context & Metadata
# =================

class AdapterContext:
    """
    Context object carrying platform/session scoped metadata.

    Design Philosophy:
    - Provides correlation IDs for distributed tracing
    - Carries tenant/user context for multi-tenant deployments
    - Enables platform-specific customization through extras
    """

    def __init__(
        self,
        tenant_id: str,
        correlation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        tracing_ctx: Optional[Any] = None,
        extras: Optional[Dict[str, Any]] = None
    ):
        self.tenant_id = tenant_id
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.user_id = user_id
        self.channel_id = channel_id
        self.tracing_ctx = tracing_ctx
        self.extras = extras or {}
        self.created_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for serialization"""
        return {
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "created_at": self.created_at.isoformat(),
            "extras": self.extras
        }

class AdapterCapabilities:
    """
    Declarative capability set for adapter discovery and routing.

    Technical Implementation:
    - Helps PolicyEngine determine valid message targets
    - Enables MessageRouter to select appropriate adapters
    - Supports capability-based load balancing
    """

    def __init__(
        self,
        supported_capabilities: Set[PlatformCapability],
        max_message_length: int = 4096,
        supported_media_types: Optional[List[str]] = None,
        rate_limits: Optional[Dict[str, int]] = None,
        custom_features: Optional[Dict[str, Any]] = None
    ):
        self.supported_capabilities = supported_capabilities
        self.max_message_length = max_message_length
        self.supported_media_types = supported_media_types or []
        self.rate_limits = rate_limits or {}
        self.custom_features = custom_features or {}

    def supports(self, capability: PlatformCapability) -> bool:
        """Check if adapter supports a specific capability"""
        return capability in self.supported_capabilities

    def supports_media_type(self, media_type: str) -> bool:
        """Check if adapter supports a specific media type"""
        return media_type in self.supported_media_types

    def get_rate_limit(self, operation: str) -> Optional[int]:
        """Get rate limit for a specific operation"""
        return self.rate_limits.get(operation)

    def to_dict(self) -> Dict[str, Any]:
        """Convert capabilities to dictionary"""
        return {
            "supported_capabilities": [cap.value for cap in self.supported_capabilities],
            "max_message_length": self.max_message_length,
            "supported_media_types": self.supported_media_types,
            "rate_limits": self.rate_limits,
            "custom_features": self.custom_features
        }

class AdapterMetadata(BaseModel):
    """Comprehensive metadata for platform adapters"""
    platform: str = Field(..., description="Platform identifier (e.g., 'telegram', 'slack')")
    version: str = Field(..., description="Adapter version")
    display_name: str = Field(..., description="Human-readable platform name")
    description: Optional[str] = Field(None, description="Adapter description")
    author: Optional[str] = Field(None, description="Adapter author")
    homepage: Optional[str] = Field(None, description="Platform homepage URL")
    api_version: Optional[str] = Field(None, description="Platform API version")

    # Technical specifications
    max_message_length: int = Field(4096, description="Maximum message length")
    supported_media_types: List[str] = Field(default_factory=list)
    rate_limits: Dict[str, int] = Field(default_factory=dict)

    # Feature flags
    supports_webhooks: bool = Field(False, description="Supports webhook delivery")
    supports_real_time: bool = Field(False, description="Supports real-time events")
    supports_threading: bool = Field(False, description="Supports message threading")
    supports_reactions: bool = Field(False, description="Supports message reactions")

    # Configuration
    required_config: List[str] = Field(default_factory=list, description="Required config keys")
    optional_config: List[str] = Field(default_factory=list, description="Optional config keys")

# ===================
# Message Queue Item
# ===================

@dataclass
class QueuedMessage:
    """Message item for adapter queue processing"""
    message: Dict[str, Any]
    context: AdapterContext
    priority: MessagePriority = MessagePriority.NORMAL
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = None
    scheduled_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

# ==================
# Base Adapter Class
# ==================

class PlatformAdapter(ABC):
    """
    Base class for all UBP platform adapters.

    Design Philosophy:
    - Interoperability: Standard interface works across all platforms
    - Scalability: Async processing with message queuing and connection pooling
    - Security: Secure credential management and error isolation
    - Observability: Comprehensive metrics, logging, and health monitoring

    Technical Implementation:
    - WebSocket connection to UBP Orchestrator with automatic reconnection
    - HTTP session management for platform API calls
    - Message queue with priority handling and retry logic
    - Metrics collection and periodic reporting
    - Health monitoring and status reporting
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.adapter_id = f"{self.platform_name}-{str(uuid.uuid4())[:8]}"
        self.logger = logging.getLogger(f"ubp.adapter.{self.platform_name}")

        # Connection management
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.status = AdapterStatus.INITIALIZING
        self.connected = False
        self.last_heartbeat = None

        # Reconnection configuration
        self.reconnect_delay = config.get("reconnect_delay", 5)
        self.max_reconnect_delay = config.get("max_reconnect_delay", 300)
        self.reconnect_backoff = config.get("reconnect_backoff", 2.0)
        self.current_reconnect_delay = self.reconnect_delay

        # Message processing
        self.message_queue: asyncio.Queue[QueuedMessage] = asyncio.Queue(
            maxsize=config.get("queue_size", 1000)
        )
        self.processing_messages = False

        # Metrics and monitoring
        self.metrics = {
            "messages_sent": 0,
            "messages_received": 0,
            "messages_queued": 0,
            "messages_failed": 0,
            "connection_attempts": 0,
            "reconnects": 0,
            "errors": 0,
            "uptime_start": datetime.utcnow()
        }

        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()

        self.logger.info(f"Initialized {self.platform_name} adapter: {self.adapter_id}")

    # ==================
    # Abstract Properties
    # ==================

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Platform identifier (e.g., 'telegram', 'slack', 'whatsapp')"""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        """Adapter capabilities and feature set"""
        pass

    @property
    @abstractmethod
    def metadata(self) -> AdapterMetadata:
        """Comprehensive adapter metadata"""
        pass

    # =================
    # Abstract Methods
    # =================

    @abstractmethod
    async def _setup_platform(self) -> None:
        """Platform-specific initialization (API clients, webhooks, etc.)"""
        pass

    @abstractmethod
    async def handle_platform_event(self, event: Dict[str, Any]) -> None:
        """Handle incoming platform-specific events"""
        pass

    @abstractmethod
    async def handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle UBP command from Orchestrator"""
        pass

    @abstractmethod
    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """Send message to platform (core adapter functionality)"""
        pass

    # ==================
    # Lifecycle Management
    # ==================

    async def start(self) -> None:
        """Start the adapter with full initialization"""
        try:
            self.logger.info(f"Starting {self.platform_name} adapter...")
            self.status = AdapterStatus.CONNECTING

            # Initialize HTTP session
            connector = aiohttp.TCPConnector(
                limit=self.config.get("http_pool_size", 100),
                ttl_dns_cache=300,
                use_dns_cache=True
            )
            self.http_session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30)
            )

            # Platform-specific setup
            await self._setup_platform()

            # Connect to Orchestrator
            await self._connect_to_orchestrator()

            # Start background tasks
            await self._start_background_tasks()

            self.status = AdapterStatus.CONNECTED
            self.logger.info(f"{self.platform_name} adapter started successfully")

        except Exception as e:
            self.status = AdapterStatus.ERROR
            self.logger.error(f"Failed to start adapter: {str(e)}", exc_info=True)
            raise AdapterError(f"Adapter startup failed: {str(e)}")

    async def stop(self) -> None:
        """Gracefully stop the adapter"""
        try:
            self.logger.info(f"Stopping {self.platform_name} adapter...")
            self.status = AdapterStatus.STOPPING

            # Signal shutdown
            self._shutdown_event.set()

            # Stop background tasks
            await self._stop_background_tasks()

            # Close connections
            self.connected = False
            if self.websocket:
                await self.websocket.close()
            if self.http_session:
                await self.http_session.close()

            self.status = AdapterStatus.STOPPED
            self.logger.info(f"{self.platform_name} adapter stopped")

        except Exception as e:
            self.logger.error(f"Error stopping adapter: {str(e)}", exc_info=True)

    # ====================
    # Connection Management
    # ====================

    async def _connect_to_orchestrator(self) -> None:
        """Establish WebSocket connection to UBP Orchestrator"""
        try:
            orchestrator_url = self.config.get("orchestrator_url", "ws://localhost:8765")
            self.logger.info(f"Connecting to Orchestrator: {orchestrator_url}")

            # Connect with heartbeat
            self.websocket = await websockets.connect(
                orchestrator_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10
            )

            # Perform handshake
            await self._perform_handshake()

            self.connected = True
            self.last_heartbeat = datetime.utcnow()
            self.current_reconnect_delay = self.reconnect_delay  # Reset backoff
            self.metrics["connection_attempts"] += 1

            self.logger.info(f"{self.platform_name} adapter connected to Orchestrator")

        except Exception as e:
            self.logger.error(f"Connection to Orchestrator failed: {str(e)}")
            self.metrics["errors"] += 1
            raise ConnectionError(f"Failed to connect to Orchestrator: {str(e)}")

    async def _perform_handshake(self) -> None:
        """Perform UBP handshake with Orchestrator"""
        handshake_request = {
            "handshake": {
                "bot_id": self.adapter_id,
                "instance_id": self.adapter_id,
                "auth": {
                    "api_key": self.config.get("ubp_api_key", "")
                },
                "capabilities": [cap.value for cap in self.capabilities.supported_capabilities],
                "metadata": {
                    "adapter_type": "platform_adapter",
                    "platform": self.platform_name,
                    "version": self.metadata.version,
                    "capabilities": self.capabilities.to_dict(),
                    "metadata": self.metadata.dict()
                }
            }
        }

        await self.websocket.send(json.dumps(handshake_request))
        response = await self.websocket.recv()
        handshake_response = json.loads(response)

        if handshake_response.get("handshake_response", {}).get("status") != "SUCCESS":
            error_msg = handshake_response.get("handshake_response", {}).get("error_message", "Unknown error")
            raise AuthenticationError(f"Handshake failed: {error_msg}")

        self.logger.info("Handshake with Orchestrator successful")

    async def _maintain_connection(self) -> None:
        """Maintain connection to Orchestrator with automatic reconnection"""
        while not self._shutdown_event.is_set():
            try:
                if not self.connected:
                    self.logger.info("Attempting to reconnect to Orchestrator...")
                    await self._connect_to_orchestrator()
                    self.metrics["reconnects"] += 1

                # Listen for messages
                if self.websocket:
                    try:
                        message = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                        await self._handle_orchestrator_message(message)
                        self.last_heartbeat = datetime.utcnow()
                    except asyncio.TimeoutError:
                        # Normal timeout, continue loop
                        pass
                    except websockets.exceptions.ConnectionClosed:
                        self.logger.warning("Connection to Orchestrator lost")
                        self.connected = False
                        self.status = AdapterStatus.DISCONNECTED

            except Exception as e:
                self.logger.error(f"Connection maintenance error: {str(e)}")
                self.connected = False
                self.status = AdapterStatus.ERROR
                self.metrics["errors"] += 1

                # Exponential backoff
                await asyncio.sleep(self.current_reconnect_delay)
                self.current_reconnect_delay = min(
                    self.max_reconnect_delay,
                    self.current_reconnect_delay * self.reconnect_backoff
                )

    async def _handle_orchestrator_message(self, message: str) -> None:
        """Handle incoming messages from Orchestrator"""
        try:
            msg = json.loads(message)
            self.metrics["messages_received"] += 1

            if "command_request" in msg:
                # Handle command from Orchestrator
                command_response = await self.handle_command(msg["command_request"])
                if command_response:
                    await self._send_to_orchestrator({"command_response": command_response})

            elif "policy_update" in msg:
                # Handle policy updates
                await self._handle_policy_update(msg["policy_update"])

            else:
                self.logger.warning(f"Unknown message type from Orchestrator: {list(msg.keys())}")

        except json.JSONDecodeError:
            self.logger.error("Received invalid JSON from Orchestrator")
        except Exception as e:
            self.logger.error(f"Error handling Orchestrator message: {str(e)}", exc_info=True)
            self.metrics["errors"] += 1

    async def _handle_policy_update(self, policy: Dict[str, Any]) -> None:
        """Handle policy updates from Orchestrator"""
        try:
            # Update configuration based on policy
            if "rate_limits" in policy:
                self.capabilities.rate_limits.update(policy["rate_limits"])

            if "reconnect_delay" in policy:
                self.reconnect_delay = policy["reconnect_delay"]

            self.logger.info("Policy update applied", extra={"policy": policy})

        except Exception as e:
            self.logger.error(f"Error applying policy update: {str(e)}")

    # ===================
    # Message Processing
    # ===================

    async def queue_message(
        self,
        message: Dict[str, Any],
        context: AdapterContext,
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> None:
        """Queue message for processing"""
        try:
            queued_msg = QueuedMessage(
                message=message,
                context=context,
                priority=priority
            )

            await self.message_queue.put(queued_msg)
            self.metrics["messages_queued"] += 1

        except asyncio.QueueFull:
            self.logger.error("Message queue is full, dropping message")
            self.metrics["messages_failed"] += 1
            raise AdapterError("Message queue is full")

    async def _process_message_queue(self) -> None:
        """Process queued messages with priority handling"""
        self.processing_messages = True

        while not self._shutdown_event.is_set():
            try:
                # Get message from queue with timeout
                queued_msg = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=1.0
                )

                # Process message
                await self._process_queued_message(queued_msg)

            except asyncio.TimeoutError:
                # Normal timeout, continue processing
                continue
            except Exception as e:
                self.logger.error(f"Error in message queue processing: {str(e)}", exc_info=True)
                self.metrics["errors"] += 1
                await asyncio.sleep(1)  # Brief pause on error

    async def _process_queued_message(self, queued_msg: QueuedMessage) -> None:
        """Process a single queued message"""
        try:
            # Check if message is scheduled for future delivery
            if queued_msg.scheduled_at and datetime.utcnow() < queued_msg.scheduled_at:
                # Re-queue for later
                await asyncio.sleep(1)
                await self.message_queue.put(queued_msg)
                return

            # Send message to platform
            result = await self.send_message(queued_msg.context, queued_msg.message)

            if result.success:
                self.metrics["messages_sent"] += 1

                # Send confirmation to Orchestrator
                confirmation = {
                    "message_sent": {
                        "correlation_id": queued_msg.context.correlation_id,
                        "platform_message_id": result.platform_message_id,
                        "timestamp": result.timestamp.isoformat(),
                        "platform": self.platform_name
                    }
                }
                await self._send_to_orchestrator(confirmation)

            else:
                # Handle failure with retry logic
                await self._handle_message_failure(queued_msg, result.error_message)

        except Exception as e:
            self.logger.error(f"Error processing queued message: {str(e)}", exc_info=True)
            await self._handle_message_failure(queued_msg, str(e))

    async def _handle_message_failure(self, queued_msg: QueuedMessage, error: str) -> None:
        """Handle message processing failure with retry logic"""
        queued_msg.retry_count += 1

        if queued_msg.retry_count <= queued_msg.max_retries:
            # Calculate retry delay with exponential backoff
            retry_delay = min(300, 2 ** queued_msg.retry_count)  # Max 5 minutes
            queued_msg.scheduled_at = datetime.utcnow() + timedelta(seconds=retry_delay)

            self.logger.warning(
                f"Message failed, retrying in {retry_delay}s (attempt {queued_msg.retry_count}/{queued_msg.max_retries})"
            )

            # Re-queue for retry
            await self.message_queue.put(queued_msg)
        else:
            # Max retries exceeded
            self.metrics["messages_failed"] += 1
            self.logger.error(f"Message failed permanently after {queued_msg.max_retries} retries: {error}")

            # Send failure notification to Orchestrator
            failure_notification = {
                "message_failed": {
                    "correlation_id": queued_msg.context.correlation_id,
                    "error": error,
                    "retry_count": queued_msg.retry_count,
                    "platform": self.platform_name
                }
            }
            await self._send_to_orchestrator(failure_notification)

    async def _send_to_orchestrator(self, message: Dict[str, Any]) -> None:
        """Send message to Orchestrator"""
        try:
            if self.connected and self.websocket:
                await self.websocket.send(json.dumps(message))
            else:
                self.logger.warning("Cannot send to Orchestrator: not connected")
        except Exception as e:
            self.logger.error(f"Error sending to Orchestrator: {str(e)}")

    # ===================
    # Background Tasks
    # ===================

    async def _start_background_tasks(self) -> None:
        """Start all background tasks"""
        tasks = [
            self._maintain_connection(),
            self._process_message_queue(),
            self._report_metrics(),
            self._health_monitor()
        ]

        for task_coro in tasks:
            task = asyncio.create_task(task_coro)
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _stop_background_tasks(self) -> None:
        """Stop all background tasks"""
        for task in self._background_tasks:
            task.cancel()

        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

    async def _report_metrics(self) -> None:
        """Periodically report adapter metrics"""
        while not self._shutdown_event.is_set():
            try:
                # Calculate uptime
                uptime = datetime.utcnow() - self.metrics["uptime_start"]

                metrics_report = {
                    "adapter_metrics": {
                        "adapter_id": self.adapter_id,
                        "platform": self.platform_name,
                        "status": self.status.value,
                        "uptime_seconds": uptime.total_seconds(),
                        "metrics": dict(self.metrics),
                        "queue_size": self.message_queue.qsize(),
                        "connected": self.connected,
                        "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None
                    }
                }

                await self._send_to_orchestrator(metrics_report)
                self.logger.debug(f"Reported metrics: {self.metrics}")

                # Wait for next report interval
                await asyncio.sleep(self.config.get("metrics_interval", 300))  # 5 minutes default

            except Exception as e:
                self.logger.error(f"Error reporting metrics: {str(e)}")
                await asyncio.sleep(60)  # Retry in 1 minute

    async def _health_monitor(self) -> None:
        """Monitor adapter health and status"""
        while not self._shutdown_event.is_set():
            try:
                # Check connection health
                if self.connected and self.last_heartbeat:
                    time_since_heartbeat = datetime.utcnow() - self.last_heartbeat
                    if time_since_heartbeat > timedelta(minutes=2):
                        self.logger.warning("No heartbeat received for 2 minutes")
                        self.connected = False
                        self.status = AdapterStatus.DISCONNECTED

                # Check queue health
                queue_size = self.message_queue.qsize()
                max_queue_size = self.config.get("queue_size", 1000)
                if queue_size > max_queue_size * 0.8:
                    self.logger.warning(f"Message queue is {queue_size}/{max_queue_size} (80%+ full)")

                await asyncio.sleep(30)  # Check every 30 seconds

            except Exception as e:
                self.logger.error(f"Health monitor error: {str(e)}")
                await asyncio.sleep(60)

    # ===============
    # Public API
    # ===============

    async def health(self) -> Dict[str, Any]:
        """Get adapter health status"""
        uptime = datetime.utcnow() - self.metrics["uptime_start"]

        return {
            "status": self.status.value,
            "platform": self.platform_name,
            "adapter_id": self.adapter_id,
            "connected": self.connected,
            "uptime_seconds": uptime.total_seconds(),
            "queue_size": self.message_queue.qsize(),
            "metrics": dict(self.metrics),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "capabilities": self.capabilities.to_dict()
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Get current adapter metrics"""
        return dict(self.metrics)

    def get_status(self) -> AdapterStatus:
        """Get current adapter status"""
        return self.status

# ==================
# Adapter Registry
# ==================

class AdapterRegistry:
    """
    Registry for managing platform adapters.

    Design Philosophy:
    - Centralized adapter discovery and management
    - Support for multiple adapters per platform
    - Health monitoring and load balancing
    - Integration with Service Discovery
    """

    def __init__(self):
        self.logger = logging.getLogger("ubp.adapter.registry")
        self._adapters: Dict[str, PlatformAdapter] = {}
        self._by_platform: Dict[str, List[str]] = {}
        self._health_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 60  # 1 minute cache TTL

    def register(self, adapter: PlatformAdapter) -> None:
        """Register a platform adapter"""
        self._adapters[adapter.adapter_id] = adapter
        platform_adapters = self._by_platform.setdefault(adapter.platform_name, [])
        platform_adapters.append(adapter.adapter_id)

        self.logger.info(f"Registered adapter: {adapter.adapter_id} for platform: {adapter.platform_name}")

    def unregister(self, adapter_id: str) -> bool:
        """Unregister an adapter"""
        adapter = self._adapters.pop(adapter_id, None)
        if adapter:
            platform_adapters = self._by_platform.get(adapter.platform_name, [])
            if adapter_id in platform_adapters:
                platform_adapters.remove(adapter_id)

            self._health_cache.pop(adapter_id, None)
            self.logger.info(f"Unregistered adapter: {adapter_id}")
            return True
        return False

    def get(self, adapter_id: str) -> Optional[PlatformAdapter]:
        """Get adapter by ID"""
        return self._adapters.get(adapter_id)

    def list_by_platform(self, platform: str) -> List[PlatformAdapter]:
        """Get all adapters for a specific platform"""
        adapter_ids = self._by_platform.get(platform, [])
        return [self._adapters[aid] for aid in adapter_ids if aid in self._adapters]

    def get_healthy_adapters(self, platform: str) -> List[PlatformAdapter]:
        """Get healthy adapters for a platform"""
        adapters = self.list_by_platform(platform)
        healthy_adapters = []

        for adapter in adapters:
            if adapter.status == AdapterStatus.CONNECTED and adapter.connected:
                healthy_adapters.append(adapter)

        return healthy_adapters

    def all(self) -> List[PlatformAdapter]:
        """Get all registered adapters"""
        return list(self._adapters.values())

    def get_platforms(self) -> List[str]:
        """Get list of all registered platforms"""
        return list(self._by_platform.keys())

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """Perform health check on all adapters"""
        health_results = {}

        for adapter_id, adapter in self._adapters.items():
            try:
                health = await adapter.health()
                health_results[adapter_id] = health
                self._health_cache[adapter_id] = {
                    "health": health,
                    "timestamp": datetime.utcnow()
                }
            except Exception as e:
                health_results[adapter_id] = {
                    "status": "error",
                    "error": str(e)
                }

        return health_results

# =================
# Factory Functions
# =================

def create_adapter_registry() -> AdapterRegistry:
    """Factory function to create an AdapterRegistry"""
    return AdapterRegistry()

# ===============
# Module Exports
# ===============

__all__ = [
    # Base classes
    "PlatformAdapter",
    "AdapterRegistry",

    # Data models
    "AdapterContext",
    "AdapterCapabilities",
    "AdapterMetadata",
    "QueuedMessage",
    "SendResult",
    "SimpleSendResult",

    # Enums
    "PlatformCapability",
    "AdapterStatus",
    "MessagePriority",

    # Exceptions
    "AdapterError",
    "ConnectionError",
    "AuthenticationError",
    "RateLimitError",

    # Factory functions
    "create_adapter_registry"
]