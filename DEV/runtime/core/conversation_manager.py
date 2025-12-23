"""
FilePath: "/runtime/core/conversation_manager.py"
Project: Unified Bot Protocol (UBP)
Component: Conversation Manager
Description: Manages conversation history, context, and state across different adapters.
Author: "Michael Landbo"
Version: "1.2.1"
"""

import time
import uuid
import logging
from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger("UBP-ConversationManager")

class ConversationState(Enum):
     ACTIVE = "active"
     WAITING = "waiting"
     COMPLETED = "completed"

@dataclass
class ConversationContext:
     conversation_id: str
     user_id: str
     channel_id: str
     adapter_name: str
     started_at: float = field(default_factory=time.time)
     last_updated: float = field(default_factory=time.time)
     metadata: Dict[str, Any] = field(default_factory=dict)
     state: ConversationState = ConversationState.ACTIVE

class ConversationManager:
     """
     Styrer hukommelsen for botten.
     Gemmer beskeder i RAM (i produktion ville man bruge Redis/Database).
     """
     def __init__(self, history_limit: int = 20):
          self.history_limit = history_limit
          # Key: conversation_id (eller user_id i simple cases)
          self.contexts: Dict[str, ConversationContext] = {}
          # Key: conversation_id -> List of message dicts
          self.histories: Dict[str, List[Dict[str, str]]] = {}

     def get_conversation_id(self, user_id: str, channel_id: str, adapter_name: str) -> str:
          """
          Finder eller opretter et unikt ID for denne samtale.
          For simpelthedens skyld bruger vi f.eks. 'adapter:user_id' som nøgle.
          """
          # I en avanceret bot ville vi håndtere sessions-timeout her.
          return f"{adapter_name}:{user_id}"

     def get_history(self, conversation_id: str) -> List[Dict[str, str]]:
          """Henter chat-historik formateret til LLM (OpenAI format)"""
          return self.histories.get(conversation_id, [])

     def add_message(self, conversation_id: str, role: str, content: str, name: str = None):
          """Tilføjer en besked til historikken"""
          if conversation_id not in self.histories:
               self.histories[conversation_id] = []

          msg = {"role": role, "content": content}
          # Nogle LLMs understøtter 'name' feltet for at skelne brugere
          if name:
               msg["name"] = name

          self.histories[conversation_id].append(msg)

          # Trim historik hvis den bliver for lang (sparer tokens)
          if len(self.histories[conversation_id]) > self.history_limit:
               self.histories[conversation_id] = self.histories[conversation_id][-self.history_limit:]

          # Opdater timestamp
          if conversation_id in self.contexts:
               self.contexts[conversation_id].last_updated = time.time()

     def get_or_create_context(self, user_id: str, channel_id: str, adapter_name: str) -> ConversationContext:
          """Henter kontekst objektet eller opretter nyt"""
          conv_id = self.get_conversation_id(user_id, channel_id, adapter_name)

          if conv_id not in self.contexts:
               logger.info(f"New conversation started: {conv_id}")
               self.contexts[conv_id] = ConversationContext(
                    conversation_id=conv_id,
                    user_id=user_id,
                    channel_id=channel_id,
                    adapter_name=adapter_name
               )
          return self.contexts[conv_id]

     def clear_history(self, conversation_id: str):
          """Glemmer historikken (f.eks. ved 'reset' kommando)"""
          if conversation_id in self.histories:
               self.histories[conversation_id] = []
               logger.info(f"History cleared for {conversation_id}")

# Global instans
conversation_manager = ConversationManager()
