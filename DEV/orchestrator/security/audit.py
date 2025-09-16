# orchestrator/security/audit.py
from datetime import datetime
import json
import logging
from typing import Any, Dict, Optional
import uuid

class AuditLogger:
    """Handles audit logging for security events"""

    def __init__(self):
        self.logger = logging.getLogger("ubp.audit")
        self.logger.setLevel(logging.INFO)

        # Add specialized handler for audit logs
        handler = logging.FileHandler("audit.log")
        handler.setFormatter(
            logging.Formatter(
                json.dumps({
                    "timestamp": "%(asctime)s",
                    "level": "%(levelname)s",
                    "event_id": "%(event_id)s",
                    "event_type": "%(event_type)s",
                    "user_id": "%(user_id)s",
                    "ip_address": "%(ip_address)s",
                    "details": "%(message)s"
                })
            )
        )
        self.logger.addHandler(handler)

    async def log_security_event(
        self,
        event_type: str,
        user_id: str,
        ip_address: str,
        details: Dict[str, Any],
        success: bool = True
    ):
        """Log a security-related event"""
        event_id = str(uuid.uuid4())

        self.logger.info(
            json.dumps(details),
            extra={
                "event_id": event_id,
                "event_type": event_type,
                "user_id": user_id,
                "ip_address": ip_address,
                "success": success,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

        return event_id