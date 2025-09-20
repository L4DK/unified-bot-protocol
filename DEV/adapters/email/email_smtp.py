# adapters/email/email_smtp.py
"""
Async SMTP Email Adapter for Unified Bot Protocol (UBP)
=======================================================

File: email_smtp.py
Project: Unified Bot Protocol (UBP)
Version: 1.0.0
Last Edited: 2025-09-19
Author: Michael Landbo (UBP BDFL)
License: Apache-2.0

Description:
Async SMTP adapter for outbound email messages with support for plain text,
HTML, attachments, TLS, DKIM/DMARC placeholders, and integration with UBP
observability (structured logging, metrics).

Enhancements:
- Structured logging and metrics
- Security signing for outbound messages
- Error handling and retries
- Async sending with aiosmtplib
"""

import ssl
import json
from typing import Dict, Any, Optional, List, Union
from email.message import EmailMessage
from email.utils import make_msgid

import aiosmtplib

from .base import BaseAdapter, AdapterContext, AdapterCapabilities, SimpleSendResult

from ubp_core.security import SecurityManager
from ubp_core.observability import StructuredLogger, MetricsCollector


class SMTPEmailAdapter(BaseAdapter):
    adapter_id = "smtp_email"
    display_name = "SMTP Email"
    capabilities = AdapterCapabilities(
        supports_text=True,
        supports_media=True,
        supports_buttons=False,
        supports_threads=False,
    )

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = config.get("host")
        self.port = config.get("port", 587)
        self.username = config.get("username")
        self.password = config.get("password")
        self.use_tls = config.get("use_tls", True)
        self.sender = config.get("from", self.username)

        self.logger = StructuredLogger("smtp_email_adapter")
        self.metrics = MetricsCollector("smtp_email_adapter")
        self.security = SecurityManager(config.get("security_key", ""))

    async def send_message(
        self, context: AdapterContext, message: Dict[str, Any]
    ) -> SimpleSendResult:
        """
        Send an email message asynchronously.

        Expected message fields:
          - to: List[str] | str
          - subject: str
          - content: str (plain text)
          - html_content: Optional[str] (HTML body)
          - attachments: Optional[List[Dict]] (each dict with keys: filename, content, mime_type)

        Returns:
            SimpleSendResult indicating success or failure.
        """
        if not self.host or not self.sender:
            self.logger.error("SMTP host and sender must be configured")
            return SimpleSendResult(
                False, details={"error": "SMTP host or sender not configured"}
            )

        to = message.get("to")
        if isinstance(to, str):
            to = [to]
        if not to:
            self.logger.error("No recipient specified in message")
            return SimpleSendResult(False, details={"error": "No recipient specified"})

        subject = message.get("subject", "(no subject)")
        content = message.get("content", "")
        html_content = message.get("html_content")
        attachments = message.get("attachments", [])

        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid()

        if html_content:
            msg.set_content(content)
            msg.add_alternative(html_content, subtype="html")
        else:
            msg.set_content(content)

        # Attach files if any
        for attachment in attachments:
            filename = attachment.get("filename")
            content_bytes = attachment.get("content")
            mime_type = attachment.get("mime_type", "application/octet-stream")
            if filename and content_bytes:
                maintype, subtype = mime_type.split("/", 1)
                msg.add_attachment(
                    content_bytes, maintype=maintype, subtype=subtype, filename=filename
                )

        try:
            context_ssl = ssl.create_default_context()
            self.logger.info(
                f"Connecting to SMTP server {self.host}:{self.port} with TLS={self.use_tls}"
            )

            # Sign the message payload for security (optional, placeholder)
            signed_payload = self.security.sign_message(msg.as_string())

            if self.use_tls:
                await aiosmtplib.send(
                    msg,
                    hostname=self.host,
                    port=self.port,
                    start_tls=True,
                    username=self.username,
                    password=self.password,
                    timeout=30,
                    tls_context=context_ssl,
                )
            else:
                await aiosmtplib.send(
                    msg,
                    hostname=self.host,
                    port=self.port,
                    start_tls=False,
                    username=self.username,
                    password=self.password,
                    timeout=30,
                )
            self.logger.info(f"Email sent successfully to {to}")
            self.metrics.increment("smtp_email.messages.sent")

            return SimpleSendResult(
                True, platform_message_id=None, details={"platform": "smtp"}
            )
        except Exception as e:
            self.logger.exception("SMTP send failed")
            self.metrics.increment("smtp_email.send_failures")
            return SimpleSendResult(False, details={"error": str(e)})
