# FilePath: "/DEV/orchestrator/security/audit.py"
# Project: Unified Bot Protocol (UBP)
# Description: Handles specialized audit logging for security events (JSON format).
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.1.0.0"

from datetime import datetime
import json
import logging
import os
from typing import Any, Dict
import uuid

class AuditLogger:
    """
    Handles audit logging for security events.
    Writes structured JSON logs to 'logs/audit.log'.
    """

    def __init__(self):
        self.logger = logging.getLogger("ubp.audit")
        self.logger.setLevel(logging.INFO)

        # Ensure duplicate handlers aren't added if instantiated multiple times
        if not self.logger.handlers:
            # Ensure logs directory exists
            if not os.path.exists("logs"):
                try:
                    os.makedirs("logs")
                except OSError:
                    pass # Handle potential race conditions

            # Add specialized handler for audit logs
            handler = logging.FileHandler("logs/audit.log")

            # We define a custom formatter that outputs valid JSON.
            # Note: We rely on the log_security_event method to pass the extra fields.
            formatter = logging.Formatter(
                '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
                '"event_id": "%(event_id)s", "event_type": "%(event_type)s", '
                '"user_id": "%(user_id)s", "ip_address": "%(ip_address)s", '
                '"details": %(message)s}'
            )

            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    async def log_security_event(
        self,
        event_type: str,
        user_id: str,
        ip_address: str,
        details: Dict[str, Any],
        success: bool = True
    ) -> str:
        """
        Log a security-related event.
        Returns the generated event_id.
        """
        event_id = str(uuid.uuid4())

        # Add success status to details for the message body
        log_details = details.copy()
        log_details['success'] = success

        # Log with extra fields required by the Formatter
        self.logger.info(
            json.dumps(log_details),
            extra={
                "event_id": event_id,
                "event_type": event_type,
                "user_id": user_id,
                "ip_address": ip_address
            }
        )

        return event_id
