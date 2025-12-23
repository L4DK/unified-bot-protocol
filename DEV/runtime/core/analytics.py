"""
FilePath: "/runtime/core/analytics.py"
Project: Unified Bot Protocol (UBP)
Component: Analytics Engine
Description: Tracks usage metrics and interactions.
Author: "Michael Landbo"
Version: "1.0.0"
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("UBP-Analytics")

class AnalyticsEngine:
     def __init__(self):
          self.metrics = {
               "messages_processed": 0,
               "tokens_used": 0,
               "errors": 0
          }

     async def track_interaction(self, adapter: str, user_id: str, message_type: str, metadata: Dict[str, Any] = None):
          """Logger en interaktion"""
          self.metrics["messages_processed"] += 1

          log_msg = f"[Analytics] {adapter} | User: {user_id} | Type: {message_type}"
          if metadata:
               log_msg += f" | Meta: {metadata}"

          logger.info(log_msg)

          # Her kunne vi sende data til Prometheus, Grafana eller en SQL database
          # TODO: Implement persistent storage

     def track_error(self, source: str, error_msg: str):
          self.metrics["errors"] += 1
          logger.error(f"[Analytics] ERROR in {source}: {error_msg}")

     def get_stats(self) -> Dict[str, int]:
          return self.metrics

# Global instans
analytics = AnalyticsEngine()
