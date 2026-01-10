"""
FilePath: "/DEV/orchestrator/security/audit.py"
Project: Unified Bot Protocol (UBP)
Component: Security Audit Logger
Description: Handles specialized audit logging to Database AND File.
Author: "Michael Landbo"
Date created: "21/12/2025"
Date Modified: "31/12/2025"
Version: "1.2.0"
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

# DB Imports
from sqlalchemy.ext.asyncio import AsyncSession

from ..db_models import AuditLogEntry

# Log directory setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(BASE_DIR, "logs")


class AuditLogger:
    """
    Handles audit logging.
    1. Writes structured JSON logs to 'DEV/logs/audit.log' (File Backup).
    2. Writes structured rows to 'audit_logs' table (Database Primary).
    """

    def __init__(self):
        # --- File Logging Setup ---
        self.file_logger = logging.getLogger("ubp.audit")
        self.file_logger.setLevel(logging.INFO)
        self.file_logger.propagate = False

        if not self.file_logger.handlers:
            os.makedirs(LOG_DIR, exist_ok=True)
            log_file = os.path.join(LOG_DIR, "audit.log")
            handler = logging.FileHandler(log_file)
            # Custom formatter for JSON content in 'message'
            formatter = logging.Formatter('{"timestamp": "%(asctime)s", "event_id": "%(event_id)s", ' '"event_type": "%(event_type)s", "details": %(message)s}')
            handler.setFormatter(formatter)
            self.file_logger.addHandler(handler)

    async def log_security_event(
        self,
        event_type: str,
        user_id: str,
        ip_address: str,
        details: Dict[str, Any],
        success: bool = True,
    ) -> str:
        """
        Log a security-related event to DB and File.
        Returns the generated event_id.
        """
        event_id = str(uuid.uuid4())

        # 1. Write to Database (Primary)
        try:
            async with AsyncSession() as session:
                async with session.begin():
                    entry = AuditLogEntry(
                        event_id=event_id,
                        event_type=event_type,
                        user_id=user_id,
                        ip_address=ip_address,
                        details=details,
                        success=success,
                        timestamp=datetime.now(timezone.utc),
                    )
                    session.add(entry)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Fallback: Log to file if DB fails
            self.file_logger.error("FAILED TO WRITE AUDIT TO DB: %s", e)

        # 2. Write to File (Backup / SIEM ingestion)
        log_details = details.copy()
        log_details["success"] = success

        self.file_logger.info(
            json.dumps(log_details),
            extra={
                "event_id": event_id,
                "event_type": event_type,
                "user_id": user_id,
                "ip_address": ip_address,
            },
        )

        return event_id
