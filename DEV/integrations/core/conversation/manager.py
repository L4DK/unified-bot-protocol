# filepath: core/conversation/manager.py
# project: Unified Bot Protocol (UBP)
# component: Conversation Manager (Cross-Platform State & Context Tracking)
# license: Apache-2.0
# author: Michael Landbo (Founder & BDFL of UBP)
# description:
#   Manages conversation state machines, context tracking, and cross-platform
#   conversation continuity. Handles state transitions, entity extraction,
#   intent tracking, sentiment analysis, and conversation cleanup.
#   Core component for maintaining conversational context across bot interactions.
# version: 1.2.0
# last_edit: 2025-09-16
#
# CHANGELOG:
# - 1.2.0: Enhanced with comprehensive state machine, context management,
#          metrics tracking, and robust cleanup mechanisms
# - 1.1.0: Added entity extraction, intent tracking, sentiment analysis
# - 1.0.0: Initial conversation tracking with basic state management

from typing import Dict, List, Any, Optional, Set
import asyncio
import logging
import json
import uuid
import hashlib
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict, deque

# =========================
# Core Enums & Data Models
# =========================

class ConversationState(Enum):
    """Conversation lifecycle states following UBP conversation flow patterns"""
    INITIATED = "initiated"
    ACTIVE = "active"
    WAITING = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    ERROR = "error"

class MessageType(Enum):
    """Message types for conversation flow control"""
    USER = "user"
    BOT = "bot"
    SYSTEM = "system"
    ACTION = "action"

# ============================
# Conversation State Machine
# ============================

class ConversationStateMachine:
    """
    State machine for conversation management following UBP principles.

    Design Philosophy:
    - Interoperability: Standard state transitions work across all platforms
    - Scalability: Lightweight state processing with clear transition rules
    - Security: Validates state transitions to prevent invalid flows
    - Observability: Logs all state changes with context
    """

    def __init__(self):
        self.logger = logging.getLogger("ubp.conversation.state_machine")

        # Define valid state transitions
        self.transitions = {
            ConversationState.INITIATED: [
                ConversationState.ACTIVE,
                ConversationState.ABANDONED
            ],
            ConversationState.ACTIVE: [
                ConversationState.WAITING,
                ConversationState.PAUSED,
                ConversationState.COMPLETED,
                ConversationState.ERROR
            ],
            ConversationState.WAITING: [
                ConversationState.ACTIVE,
                ConversationState.ABANDONED,
                ConversationState.ERROR
            ],
            ConversationState.PAUSED: [
                ConversationState.ACTIVE,
                ConversationState.ABANDONED
            ],
            ConversationState.COMPLETED: [],
            ConversationState.ABANDONED: [],
            ConversationState.ERROR: [
                ConversationState.ACTIVE,
                ConversationState.ABANDONED
            ]
        }

    def can_transition(
        self,
        from_state: ConversationState,
        to_state: ConversationState
    ) -> bool:
        """Check if state transition is valid"""
        return to_state in self.transitions.get(from_state, [])

    async def process(
        self,
        conversation_id: str,
        message: Dict,
        current_state: ConversationState
    ) -> ConversationState:
        """
        Process message and determine new conversation state.

        Technical Implementation:
        - Analyzes message content and type for state transition triggers
        - Validates transitions against allowed state machine rules
        - Handles timeout detection for abandoned conversations
        - Logs state changes for observability
        """
        try:
            message_type = MessageType(message.get("type", "user"))
            new_state = current_state

            # State transition logic
            if current_state == ConversationState.INITIATED:
                if message_type == MessageType.USER:
                    new_state = ConversationState.ACTIVE
                elif self._is_timeout(message):
                    new_state = ConversationState.ABANDONED

            elif current_state == ConversationState.ACTIVE:
                if self._is_completion_message(message):
                    new_state = ConversationState.COMPLETED
                elif self._is_pause_message(message):
                    new_state = ConversationState.PAUSED
                elif self._requires_waiting(message):
                    new_state = ConversationState.WAITING
                elif self._is_error_message(message):
                    new_state = ConversationState.ERROR

            elif current_state == ConversationState.WAITING:
                if message_type == MessageType.USER:
                    new_state = ConversationState.ACTIVE
                elif self._is_timeout(message):
                    new_state = ConversationState.ABANDONED

            elif current_state == ConversationState.PAUSED:
                if self._is_resume_message(message):
                    new_state = ConversationState.ACTIVE
                elif self._is_timeout(message):
                    new_state = ConversationState.ABANDONED

            elif current_state == ConversationState.ERROR:
                if self._is_recovery_message(message):
                    new_state = ConversationState.ACTIVE
                elif self._is_timeout(message):
                    new_state = ConversationState.ABANDONED

            # Validate transition
            if new_state != current_state and not self.can_transition(current_state, new_state):
                self.logger.warning(
                    f"Invalid state transition attempted: {current_state.value} -> {new_state.value}",
                    extra={"conversation_id": conversation_id}
                )
                new_state = current_state

            # Log state changes
            if new_state != current_state:
                self.logger.info(
                    f"State transition: {current_state.value} -> {new_state.value}",
                    extra={
                        "conversation_id": conversation_id,
                        "message_type": message_type.value,
                        "trigger": self._get_transition_trigger(message)
                    }
                )

            return new_state

        except Exception as e:
            self.logger.error(
                f"Error processing state transition: {str(e)}",
                extra={"conversation_id": conversation_id}
            )
            return current_state

    def _is_completion_message(self, message: Dict) -> bool:
        """Check if message indicates conversation completion"""
        completion_keywords = ["goodbye", "bye", "thanks", "done", "complete", "finished", "end"]
        content = message.get("content", "").lower()
        return any(keyword in content for keyword in completion_keywords)

    def _is_pause_message(self, message: Dict) -> bool:
        """Check if message indicates conversation pause"""
        pause_keywords = ["pause", "wait", "hold", "later", "brb", "back later"]
        content = message.get("content", "").lower()
        return any(keyword in content for keyword in pause_keywords)

    def _is_resume_message(self, message: Dict) -> bool:
        """Check if message indicates conversation resume"""
        resume_keywords = ["resume", "continue", "back", "ready", "let's continue", "i'm back"]
        content = message.get("content", "").lower()
        return any(keyword in content for keyword in resume_keywords)

    def _requires_waiting(self, message: Dict) -> bool:
        """Check if message requires waiting for response"""
        return message.get("requires_response", False) or message.get("awaiting_input", False)

    def _is_error_message(self, message: Dict) -> bool:
        """Check if message indicates an error"""
        return message.get("type") == "error" or message.get("error", False)

    def _is_recovery_message(self, message: Dict) -> bool:
        """Check if message indicates error recovery"""
        return message.get("recovery", False) or "try again" in message.get("content", "").lower()

    def _is_timeout(self, message: Dict) -> bool:
        """Check if conversation has timed out"""
        timestamp = message.get("timestamp")
        if not timestamp:
            return False

        # Convert to datetime if needed
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                return False

        timeout_threshold = timedelta(minutes=30)  # 30 minute timeout
        return datetime.utcnow() - timestamp > timeout_threshold

    def _get_transition_trigger(self, message: Dict) -> str:
        """Get the trigger that caused the state transition"""
        content = message.get("content", "").lower()
        if any(word in content for word in ["bye", "goodbye", "done"]):
            return "completion_keyword"
        elif any(word in content for word in ["pause", "wait"]):
            return "pause_keyword"
        elif message.get("type") == "error":
            return "error_message"
        elif self._is_timeout(message):
            return "timeout"
        else:
            return "message_flow"

# ====================
# Conversation Context
# ====================

class ConversationContext:
    """
    Context tracking for conversations across platforms.

    Design Philosophy:
    - Maintains rich context including entities, intents, sentiment
    - Provides variable storage for conversation state
    - Tracks user preferences and conversation history
    - Enables context-aware response generation
    """

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.variables: Dict[str, Any] = {}
        self.entities: Dict[str, List[Dict[str, Any]]] = {}
        self.intents: List[Dict[str, Any]] = []
        self.sentiment_history: deque = deque(maxlen=10)
        self.topic_history: deque = deque(maxlen=5)
        self.user_preferences: Dict[str, Any] = {}
        self.created_at = datetime.utcnow()

    def set_variable(self, key: str, value: Any) -> None:
        """Set context variable for conversation state"""
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get context variable with optional default"""
        return self.variables.get(key, default)

    def add_entity(self, entity_type: str, entity_value: str, confidence: float = 1.0) -> None:
        """Add extracted entity to context"""
        if entity_type not in self.entities:
            self.entities[entity_type] = []

        self.entities[entity_type].append({
            "value": entity_value,
            "confidence": confidence,
            "timestamp": datetime.utcnow(),
            "source": "extraction"
        })

    def add_intent(self, intent: str, confidence: float) -> None:
        """Add detected intent to context"""
        self.intents.append({
            "intent": intent,
            "confidence": confidence,
            "timestamp": datetime.utcnow()
        })

    def update_sentiment(self, sentiment: str, score: float) -> None:
        """Update sentiment history"""
        self.sentiment_history.append({
            "sentiment": sentiment,
            "score": score,
            "timestamp": datetime.utcnow()
        })

    def update_topic(self, topic: str, confidence: float) -> None:
        """Update topic history"""
        self.topic_history.append({
            "topic": topic,
            "confidence": confidence,
            "timestamp": datetime.utcnow()
        })

    def set_user_preference(self, key: str, value: Any) -> None:
        """Set user preference"""
        self.user_preferences[key] = value

    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """Get user preference"""
        return self.user_preferences.get(key, default)

    def get_recent_entities(self, entity_type: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent entities of specified type"""
        entities = self.entities.get(entity_type, [])
        return sorted(entities, key=lambda x: x["timestamp"], reverse=True)[:limit]

    def get_dominant_sentiment(self) -> Optional[str]:
        """Get the most recent dominant sentiment"""
        if not self.sentiment_history:
            return None
        return list(self.sentiment_history)[-1]["sentiment"]

    def get_current_topics(self) -> List[str]:
        """Get current active topics"""
        return [topic["topic"] for topic in list(self.topic_history)]

# ====================
# Conversation Manager
# ====================

class ConversationManager:
    """
    Cross-platform conversation management system.

    Design Philosophy:
    - Interoperability: Works across all platform adapters uniformly
    - Scalability: Efficient memory management with automatic cleanup
    - Security: Validates conversation IDs and prevents context leakage
    - Observability: Comprehensive metrics and logging for conversation flows

    Technical Implementation:
    - State machine-driven conversation lifecycle management
    - Rich context tracking with entities, intents, and sentiment
    - Automatic cleanup of stale conversations
    - Metrics collection for conversation analytics
    """

    def __init__(self):
        self.logger = logging.getLogger("ubp.conversation.manager")
        self.state_machine = ConversationStateMachine()

        # Core data structures
        self.conversations: Dict[str, Dict[str, Any]] = {}
        self.contexts: Dict[str, ConversationContext] = {}
        self.message_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Tracking and metrics
        self.metrics: Dict[str, int] = defaultdict(int)
        self.active_conversations: Set[str] = set()

        # Configuration
        self.cleanup_interval_hours = 1
        self.conversation_timeout_hours = 24
        self.max_history_length = 100

        # Start background tasks
        asyncio.create_task(self._cleanup_conversations())

        self.logger.info("ConversationManager initialized")

    async def track_conversation(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Track and manage conversation state with comprehensive context.

        Returns conversation metadata including state, context, and history info.
        """
        try:
            conversation_id = self._get_conversation_id(message)

            # Initialize conversation if new
            if conversation_id not in self.conversations:
                await self._initialize_conversation(conversation_id, message)

            # Get current state and process through state machine
            current_state = self.conversations[conversation_id]["state"]
            new_state = await self.state_machine.process(
                conversation_id,
                message,
                current_state
            )

            # Update conversation with new state and message
            await self._update_conversation(conversation_id, message, new_state)

            # Update context with extracted information
            await self._update_context(conversation_id, message)

            # Generate response context for downstream processing
            response_context = await self._generate_response_context(conversation_id)

            # Update metrics
            self.metrics["messages_tracked"] += 1
            if new_state != current_state:
                self.metrics["state_transitions"] += 1

            return {
                "conversation_id": conversation_id,
                "state": new_state.value,
                "previous_state": current_state.value if new_state != current_state else None,
                "context": response_context,
                "history_length": len(self.message_history[conversation_id]),
                "is_active": conversation_id in self.active_conversations
            }

        except Exception as e:
            self.logger.error(f"Error tracking conversation: {str(e)}", exc_info=True)
            self.metrics["tracking_errors"] += 1
            raise

    async def _initialize_conversation(self, conversation_id: str, message: Dict[str, Any]) -> None:
        """Initialize a new conversation with metadata and context"""
        self.conversations[conversation_id] = {
            "id": conversation_id,
            "state": ConversationState.INITIATED,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "platform": message.get("platform", "unknown"),
            "user_id": message.get("user_id", "anonymous"),
            "channel_id": message.get("channel_id"),
            "metadata": {
                "initial_message_type": message.get("type", "user"),
                "language": message.get("language", "en"),
                "user_agent": message.get("user_agent")
            }
        }

        # Initialize context
        self.contexts[conversation_id] = ConversationContext(conversation_id)

        # Add to active conversations
        self.active_conversations.add(conversation_id)

        # Update metrics
        self.metrics["conversations_initialized"] += 1

        self.logger.info(
            f"Initialized conversation: {conversation_id}",
            extra={
                "conversation_id": conversation_id,
                "platform": message.get("platform"),
                "user_id": message.get("user_id")
            }
        )

    async def _update_conversation(
        self,
        conversation_id: str,
        message: Dict[str, Any],
        new_state: ConversationState
    ) -> None:
        """Update conversation with new message and state"""
        conversation = self.conversations[conversation_id]
        previous_state = conversation["state"]

        # Update state and timestamp
        conversation["state"] = new_state
        conversation["updated_at"] = datetime.utcnow()

        # Add message to history with metadata
        history_entry = {
            "message": message,
            "timestamp": datetime.utcnow(),
            "state": new_state.value,
            "previous_state": previous_state.value,
            "message_id": message.get("message_id", str(uuid.uuid4()))
        }

        self.message_history[conversation_id].append(history_entry)

        # Handle state-specific actions
        if new_state in [ConversationState.COMPLETED, ConversationState.ABANDONED]:
            self.active_conversations.discard(conversation_id)
            self.metrics["conversations_completed"] += 1

            # Calculate conversation duration
            duration = datetime.utcnow() - conversation["created_at"]
            conversation["metadata"]["duration_seconds"] = duration.total_seconds()
            conversation["metadata"]["message_count"] = len(self.message_history[conversation_id])

        elif new_state == ConversationState.ACTIVE and previous_state != ConversationState.ACTIVE:
            self.active_conversations.add(conversation_id)

    async def _update_context(self, conversation_id: str, message: Dict[str, Any]) -> None:
        """Update conversation context with extracted information"""
        context = self.contexts[conversation_id]

        try:
            # Extract and update entities
            entities = message.get("entities", {})
            for entity_type, entity_list in entities.items():
                if isinstance(entity_list, list):
                    for entity in entity_list:
                        if isinstance(entity, dict) and "value" in entity:
                            context.add_entity(
                                entity_type,
                                entity["value"],
                                entity.get("confidence", 1.0)
                            )

            # Update intents
            intent = message.get("intent")
            if intent and isinstance(intent, dict):
                context.add_intent(
                    intent.get("name", "unknown"),
                    intent.get("confidence", 1.0)
                )

            # Update sentiment
            sentiment = message.get("sentiment")
            if sentiment and isinstance(sentiment, dict):
                context.update_sentiment(
                    sentiment.get("label", "neutral"),
                    sentiment.get("score", 0.0)
                )

            # Update topic
            topic = message.get("topic")
            if topic and isinstance(topic, dict):
                context.update_topic(
                    topic.get("name", "general"),
                    topic.get("confidence", 1.0)
                )

            # Update user preferences if provided
            preferences = message.get("user_preferences", {})
            for key, value in preferences.items():
                context.set_user_preference(key, value)

        except Exception as e:
            self.logger.error(
                f"Error updating context for conversation {conversation_id}: {str(e)}",
                exc_info=True
            )

    async def _generate_response_context(self, conversation_id: str) -> Dict[str, Any]:
        """Generate comprehensive context for response generation"""
        conversation = self.conversations[conversation_id]
        context = self.contexts[conversation_id]
        history = list(self.message_history[conversation_id])

        return {
            "conversation_id": conversation_id,
            "state": conversation["state"].value,
            "platform": conversation["platform"],
            "user_id": conversation["user_id"],
            "channel_id": conversation.get("channel_id"),

            # Context variables and entities
            "variables": dict(context.variables),
            "entities": dict(context.entities),
            "recent_intents": context.intents[-3:] if context.intents else [],

            # Sentiment and topic analysis
            "sentiment_trend": list(context.sentiment_history),
            "current_sentiment": context.get_dominant_sentiment(),
            "current_topics": context.get_current_topics(),
            "topic_history": list(context.topic_history),

            # User preferences
            "user_preferences": dict(context.user_preferences),

            # Conversation metadata
            "message_count": len(history),
            "last_messages": [h["message"] for h in history[-5:]] if history else [],
            "conversation_duration": (
                datetime.utcnow() - conversation["created_at"]
            ).total_seconds(),
            "is_active": conversation_id in self.active_conversations,

            # Platform-specific metadata
            "metadata": conversation.get("metadata", {})
        }

    def _get_conversation_id(self, message: Dict[str, Any]) -> str:
        """Generate deterministic conversation ID from message components"""
        # Try to get existing conversation ID first
        conv_id = message.get("conversation_id")
        if conv_id:
            return conv_id

        # Generate based on platform, user, and channel
        platform = message.get("platform", "unknown")
        user_id = message.get("user_id", "anonymous")
        channel_id = message.get("channel_id", "default")

        # Create deterministic ID using hash
        id_components = [platform, user_id, channel_id]
        id_string = ":".join(str(comp) for comp in id_components)
        return hashlib.md5(id_string.encode()).hexdigest()

    # =================
    # Public API Methods
    # =================

    async def get_conversation_state(self, conversation_id: str) -> Optional[ConversationState]:
        """Get current conversation state"""
        conversation = self.conversations.get(conversation_id)
        return conversation["state"] if conversation else None

    async def get_conversation_context(self, conversation_id: str) -> Optional[ConversationContext]:
        """Get conversation context"""
        return self.contexts.get(conversation_id)

    async def get_conversation_history(
        self,
        conversation_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get conversation message history"""
        history = self.message_history.get(conversation_id, deque())
        return list(history)[-limit:] if history else []

    async def end_conversation(self, conversation_id: str, reason: str = "manual") -> bool:
        """Manually end a conversation"""
        if conversation_id not in self.conversations:
            return False

        self.conversations[conversation_id]["state"] = ConversationState.COMPLETED
        self.conversations[conversation_id]["metadata"]["end_reason"] = reason
        self.active_conversations.discard(conversation_id)

        self.logger.info(
            f"Manually ended conversation: {conversation_id}",
            extra={"conversation_id": conversation_id, "reason": reason}
        )
        return True

    async def pause_conversation(self, conversation_id: str) -> bool:
        """Pause an active conversation"""
        if conversation_id not in self.conversations:
            return False

        current_state = self.conversations[conversation_id]["state"]
        if current_state == ConversationState.ACTIVE:
            self.conversations[conversation_id]["state"] = ConversationState.PAUSED
            return True
        return False

    async def resume_conversation(self, conversation_id: str) -> bool:
        """Resume a paused conversation"""
        if conversation_id not in self.conversations:
            return False

        current_state = self.conversations[conversation_id]["state"]
        if current_state == ConversationState.PAUSED:
            self.conversations[conversation_id]["state"] = ConversationState.ACTIVE
            self.active_conversations.add(conversation_id)
            return True
        return False

    async def get_active_conversations(self) -> List[str]:
        """Get list of active conversation IDs"""
        return list(self.active_conversations)

    async def get_conversation_metrics(self) -> Dict[str, Any]:
        """Get conversation management metrics"""
        return {
            "total_conversations": len(self.conversations),
            "active_conversations": len(self.active_conversations),
            "messages_tracked": self.metrics["messages_tracked"],
            "state_transitions": self.metrics["state_transitions"],
            "conversations_initialized": self.metrics["conversations_initialized"],
            "conversations_completed": self.metrics["conversations_completed"],
            "tracking_errors": self.metrics["tracking_errors"],
            "cleanup_runs": self.metrics.get("cleanup_runs", 0)
        }

    # ==================
    # Background Cleanup
    # ==================

    async def _cleanup_conversations(self) -> None:
        """Background task to cleanup old conversations"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_hours * 3600)

                cutoff_time = datetime.utcnow() - timedelta(hours=self.conversation_timeout_hours)
                conversations_to_remove = []

                # Find conversations to cleanup
                for conv_id, conversation in self.conversations.items():
                    if (conversation["updated_at"] < cutoff_time and
                        conversation["state"] in [ConversationState.COMPLETED, ConversationState.ABANDONED]):
                        conversations_to_remove.append(conv_id)

                # Remove old conversations
                for conv_id in conversations_to_remove:
                    self.conversations.pop(conv_id, None)
                    self.contexts.pop(conv_id, None)
                    self.message_history.pop(conv_id, None)
                    self.active_conversations.discard(conv_id)

                if conversations_to_remove:
                    self.logger.info(f"Cleaned up {len(conversations_to_remove)} conversations")

                self.metrics["cleanup_runs"] += 1

            except Exception as e:
                self.logger.error(f"Cleanup error: {str(e)}", exc_info=True)

# =================
# Factory Functions
# =================

def create_conversation_manager() -> ConversationManager:
    """Factory function to create a ConversationManager instance"""
    return ConversationManager()

# ===============
# Module Exports
# ===============

__all__ = [
    "ConversationManager",
    "ConversationContext",
    "ConversationState",
    "ConversationStateMachine",
    "MessageType",
    "create_conversation_manager"
]