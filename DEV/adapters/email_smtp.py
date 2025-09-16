# filepath: adapters/email_smtp.py
# project: Unified Bot Protocol (UBP)
# module: SMTP Email Adapter
# version: 0.1.0
# last_edited: 2025-09-16
# author: Michael Landbo (UBP BDFL)
# license: Apache-2.0
# description:
#   Lightweight SMTP adapter for outbound messages. Demonstrates non-chat platform integration.
#
# changelog:
# - 0.1.0: Initial creation; text-only, minimal TLS support.
#
# TODO:
# - Add HTML and attachments
# - DKIM/DMARC alignment with org policy
# - Inbound email webhook/IMAP connector

from __future__ import annotations
from typing import Dict, Any, Optional
import smtplib
import ssl
from email.message import EmailMessage

from .base import BaseAdapter, AdapterContext, AdapterCapabilities, SimpleSendResult

class SMTPEmailAdapter(BaseAdapter):
    adapter_id = "smtp_email"
    display_name = "SMTP Email"
    capabilities = AdapterCapabilities(supports_text=True, supports_media=False, supports_buttons=False, supports_threads=False)

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SimpleSendResult:
        """
        message expected fields:
          - to: List[str] | str
          - subject: str
          - content: str (plain text)
        """
        host = self.config["host"]
        port = self.config.get("port", 587)
        username = self.config.get("username")
        password = self.config.get("password")
        use_tls = self.config.get("use_tls", True)
        sender = self.config.get("from", username)

        to = message.get("to")
        if isinstance(to, str):
            to = [to]

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = ", ".join(to or [])
        msg["Subject"] = message.get("subject", "(no subject)")
        msg.set_content(message.get("content", ""))

        try:
            if use_tls:
                context_ssl = ssl.create_default_context()
                with smtplib.SMTP(host, port) as server:
                    server.starttls(context=context_ssl)
                    if username and password:
                        server.login(username, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port) as server:
                    if username and password:
                        server.login(username, password)
                    server.send_message(msg)

            return SimpleSendResult(True, platform_message_id=None, details={"platform": "smtp"})
        except Exception as e:
            self.logger.exception("SMTP send failed")
            return SimpleSendResult(False, details={"error": str(e)})