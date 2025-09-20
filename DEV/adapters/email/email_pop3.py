# adapters/email/email_pop3.py
"""
Email POP3 Adapter for Unified Bot Protocol (UBP)
=================================================

File: email_pop3.py
Project: Unified Bot Protocol (UBP)
Version: 1.0.0
Last Edited: 2025-09-19
Author: Michael Landbo (UBP BDFL)
License: Apache-2.0

Description:
Inbound email adapter using POP3 protocol to fetch and process incoming emails.
Supports secure connection, polling, message parsing, attachments, observability,
security, and resilience.

Enhancements:
- Structured logging and metrics
- Security signing for events
- Retry and error handling
- Full async integration with UBP Orchestrator
"""

import asyncio
import email
import poplib
import logging
import json
from typing import Dict, Any, Optional, List

from .base import BaseAdapter, AdapterContext, AdapterCapabilities, SimpleSendResult

from ubp_core.security import SecurityManager
from ubp_core.observability import StructuredLogger, MetricsCollector


class POP3EmailAdapter(BaseAdapter):
    adapter_id = "pop3_email"
    display_name = "POP3 Email"
    capabilities = AdapterCapabilities(
        supports_text=True,
        supports_media=True,
        supports_buttons=False,
        supports_threads=False,
    )

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = config["host"]
        self.port = config.get("port", 995)
        self.username = config["username"]
        self.password = config["password"]
        self.use_ssl = config.get("use_ssl", True)
        self.poll_interval = config.get("poll_interval", 60)  # seconds

        self.logger = StructuredLogger("pop3_email_adapter")
        self.metrics = MetricsCollector("pop3_email_adapter")
        self.security = SecurityManager(config.get("security_key", ""))

        self._stop_event = asyncio.Event()

    async def start(self):
        self.logger.info("Starting POP3 Email Adapter polling")
        while not self._stop_event.is_set():
            try:
                await self._poll_mailbox()
            except Exception as e:
                self.logger.error(f"Error polling mailbox: {e}")
                self.metrics.increment("pop3_email.poll_errors")
            await asyncio.sleep(self.poll_interval)

    async def stop(self):
        self.logger.info("Stopping POP3 Email Adapter")
        self._stop_event.set()

    async def _poll_mailbox(self):
        self.logger.debug("Connecting to POP3 server")
        if self.use_ssl:
            mail = poplib.POP3_SSL(self.host, self.port)
        else:
            mail = poplib.POP3(self.host, self.port)

        mail.user(self.username)
        mail.pass_(self.password)

        num_messages = len(mail.list()[1])
        self.logger.info(f"Found {num_messages} messages in mailbox")
        self.metrics.gauge("pop3_email.mailbox_size", num_messages)

        for i in range(num_messages):
            try:
                response, lines, octets = mail.retr(i + 1)
                raw_email = b"\r\n".join(lines)
                msg = email.message_from_bytes(raw_email)

                parsed_email = self._parse_email(msg)

                ubp_event = {
                    "event_type": "email.pop3.message.received",
                    "platform": "email_pop3",
                    "timestamp": parsed_email.get("date"),
                    "content": parsed_email,
                    "adapter_id": self.adapter_id,
                }
                await self.send_event_to_orchestrator(ubp_event)

                # Delete message after processing
                mail.dele(i + 1)
            except Exception as e:
                self.logger.error(f"Failed to process message {i + 1}: {e}")
                self.metrics.increment("pop3_email.message_processing_failures")

        mail.quit()

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
        try:
            if not hasattr(self, "orchestrator_ws") or self.orchestrator_ws is None:
                self.logger.warning(
                    "No orchestrator connection available, dropping event"
                )
                self.metrics.increment("pop3_email.events.dropped")
                return

            event_json = json.dumps(event)
            signature = self.security.sign_message(event_json)

            payload = {
                "message": event,
                "signature": signature,
            }

            await self.orchestrator_ws.send(json.dumps(payload))
            self.metrics.increment("pop3_email.events.sent")
            self.logger.info(f"Sent event to orchestrator: {event['event_type']}")

        except Exception as e:
            self.logger.error(f"Failed to send event to orchestrator: {e}")
            self.metrics.increment("pop3_email.events.failed")
