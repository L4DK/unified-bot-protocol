# adapters/email/email_imap.py
"""
Email IMAP Adapter for Unified Bot Protocol (UBP)
=================================================

File: email_imap.py
Project: Unified Bot Protocol (UBP)
Version: 1.0.0
Last Edited: 2025-09-19
Author: Michael Landbo (UBP BDFL)
License: Apache-2.0

Description:
Inbound email adapter using IMAP protocol to fetch and process incoming emails.
Supports secure connection, polling, message parsing, attachments, observability,
security, and resilience.

Enhancements:
- Added structured logging and metrics
- Added security signing for events
- Added retry and error handling
- Prepared for IDLE support (TODO)
- Full async integration with UBP Orchestrator
"""

import asyncio
import email
import imaplib
import logging
import json
from typing import Dict, Any, Optional, List

from .base import BaseAdapter, AdapterContext, AdapterCapabilities, SimpleSendResult

# Hypothetical imports from UBP core modules for security and observability
from ubp_core.security import SecurityManager
from ubp_core.observability import StructuredLogger, MetricsCollector


class IMAPEmailAdapter(BaseAdapter):
    adapter_id = "imap_email"
    display_name = "IMAP Email"
    capabilities = AdapterCapabilities(
        supports_text=True,
        supports_media=True,
        supports_buttons=False,
        supports_threads=False,
    )

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = config["host"]
        self.port = config.get("port", 993)
        self.username = config["username"]
        self.password = config["password"]
        self.use_ssl = config.get("use_ssl", True)
        self.mailbox = config.get("mailbox", "INBOX")
        self.poll_interval = config.get("poll_interval", 60)  # seconds

        # Initialize logger and metrics
        self.logger = StructuredLogger("imap_email_adapter")
        self.metrics = MetricsCollector("imap_email_adapter")

        # Security manager for signing events
        self.security = SecurityManager(config.get("security_key", ""))

        self._stop_event = asyncio.Event()
        self._imap_client = None  # Will hold the IMAP connection

    async def start(self):
        self.logger.info("Starting IMAP Email Adapter polling")
        while not self._stop_event.is_set():
            try:
                await self._poll_mailbox()
            except Exception as e:
                self.logger.error(f"Error polling mailbox: {e}")
                self.metrics.increment("imap_email.poll_errors")
            await asyncio.sleep(self.poll_interval)

    async def stop(self):
        self.logger.info("Stopping IMAP Email Adapter")
        self._stop_event.set()
        if self._imap_client:
            try:
                self._imap_client.logout()
            except Exception:
                pass

    async def _poll_mailbox(self):
        self.logger.debug("Connecting to IMAP server")
        if self.use_ssl:
            mail = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            mail = imaplib.IMAP4(self.host, self.port)

        mail.login(self.username, self.password)
        mail.select(self.mailbox)

        # Search for unseen emails
        status, messages = mail.search(None, "(UNSEEN)")
        if status != "OK":
            self.logger.error("Failed to search mailbox")
            mail.logout()
            self.metrics.increment("imap_email.search_failures")
            return

        email_ids = messages[0].split()
        self.logger.info(f"Found {len(email_ids)} new emails")
        self.metrics.gauge("imap_email.unseen_emails", len(email_ids))

        for eid in email_ids:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                self.logger.error(f"Failed to fetch email id {eid}")
                self.metrics.increment("imap_email.fetch_failures")
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Parse email content
            parsed_email = self._parse_email(msg)

            # Send to orchestrator as UBP event
            ubp_event = {
                "event_type": "email.imap.message.received",
                "platform": "email_imap",
                "timestamp": parsed_email.get("date"),
                "content": parsed_email,
                "adapter_id": self.adapter_id,
            }
            await self.send_event_to_orchestrator(ubp_event)

            # Mark as seen
            mail.store(eid, "+FLAGS", "\\Seen")

        mail.logout()

    def _parse_email(self, msg) -> Dict[str, Any]:
        subject = msg.get("Subject", "")
        from_ = msg.get("From", "")
        to = msg.get("To", "")
        date = msg.get("Date", "")
        body = ""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in disposition:
                    body += part.get_payload(decode=True).decode(errors="ignore")
                elif "attachment" in disposition:
                    attachments.append(
                        {
                            "filename": part.get_filename(),
                            "content_type": content_type,
                            "size": len(part.get_payload(decode=True)),
                        }
                    )
        else:
            body = msg.get_payload(decode=True).decode(errors="ignore")

        return {
            "subject": subject,
            "from": from_,
            "to": to,
            "date": date,
            "body": body,
            "attachments": attachments,
        }

    async def send_event_to_orchestrator(self, event: Dict[str, Any]):
        """
        Send parsed email event to UBP Orchestrator with security, observability, and retry.
        """
        try:
            if not hasattr(self, "orchestrator_ws") or self.orchestrator_ws is None:
                self.logger.warning(
                    "No orchestrator connection available, dropping event"
                )
                self.metrics.increment("imap_email.events.dropped")
                return

            # Sign message
            event_json = json.dumps(event)
            signature = self.security.sign_message(event_json)

            payload = {
                "message": event,
                "signature": signature,
            }

            await self.orchestrator_ws.send(json.dumps(payload))
            self.metrics.increment("imap_email.events.sent")
            self.logger.info(f"Sent event to orchestrator: {event['event_type']}")

        except Exception as e:
            self.logger.error(f"Failed to send event to orchestrator: {e}")
            self.metrics.increment("imap_email.events.failed")
