"""
FilePath: "/DEV/orchestrator/security/audit.py"
Project: Unified Bot Protocol (UBP)
Component: Security Audit Logger
Description: Handles specialized audit logging for security events (JSON format).
Author: "Michael Landbo"
Date created: "21/12/2025"
Date Modified: "27/12/2025"
Version: "1.1.0"
"""

import json
import logging
import os
import uuid
from typing import Any, Dict

# Define the log directory relative to the project root (DEV/logs)
# This file is in DEV/orchestrator/security/, so we go up 3 levels.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(BASE_DIR, "logs")


class AuditLogger:
    """
    Handles audit logging for security events.
    Writes structured JSON logs to 'DEV/logs/audit.log'.
    """

    def __init__(self):
        self.logger = logging.getLogger("ubp.audit")
        self.logger.setLevel(logging.INFO)
        # Prevent audit logs from propagating to the root logger (console)
        self.logger.propagate = False

        # Ensure duplicate handlers aren't added if instantiated multiple times
        if not self.logger.handlers:
            # Ensure logs directory exists
            os.makedirs(LOG_DIR, exist_ok=True)

            # Add specialized handler for audit logs
            log_file = os.path.join(LOG_DIR, "audit.log")
            handler = logging.FileHandler(log_file)

            # We define a custom formatter that outputs valid JSON.
            # We rely on the log_security_event method to pass the extra fields.
            # The %(message)s will contain the JSON dumped details object.
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
        success: bool = True,
    ) -> str:
        """
        Log a security-related event.
        Returns the generated event_id.
        """
        event_id = str(uuid.uuid4())

        # Add success status to details for the message body
        log_details = details.copy()
        log_details["success"] = success

        # Log with extra fields required by the Formatter
        # json.dumps ensures that 'details' is a valid JSON value inside our formatter string
        self.logger.info(
            json.dumps(log_details),
            extra={
                "event_id": event_id,
                "event_type": event_type,
                "user_id": user_id,
                "ip_address": ip_address,
            },
        )

        return event_id
