"""
FilePath: "/adapters/email/email_smtp.py"
Project: Unified Bot Protocol (UBP)
Component: SMTP Email Adapter (Outbound)
Version: 1.1.0 (Refactored for BaseAdapter 1.3.0)
"""

import ssl
import aiosmtplib
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Dict, Any, List, Optional

# Import Base Adapter Classes
from adapters.base_adapter import (
    PlatformAdapter,
    AdapterCapabilities,
    AdapterMetadata,
    AdapterContext,
    PlatformCapability,
    SendResult,
    SimpleSendResult,
    AdapterStatus
)

class EmailSMTPAdapter(PlatformAdapter):
    """
    Official UBP SMTP Adapter for sending emails.
    Supports TLS, HTML content, and attachments via aiosmtplib.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Håndter både flad config og nested 'email' config
        self.email_config = config.get('email', config)

        self.host = self.email_config.get("host")
        self.port = self.email_config.get("port", 587)
        self.username = self.email_config.get("username")
        self.password = self.email_config.get("password")
        self.use_tls = self.email_config.get("use_tls", True)
        self.default_sender = self.email_config.get("from", self.username)

        if not self.host or not self.username:
            self.logger.error("SMTP config missing 'host' or 'username'")

    # --- Properties ---

    @property
    def platform_name(self) -> str:
        return "email"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supported_capabilities={
                PlatformCapability.SEND_MESSAGE,
                PlatformCapability.SEND_DOCUMENT,
                PlatformCapability.SEND_IMAGE
            },
            max_message_length=10485760, # 10MB default limit
            supported_media_types=["text/plain", "text/html", "application/pdf", "image/jpeg"],
            rate_limits={"message.send": 5} # 5 mails/sec (forsigtig default)
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="email",
            display_name="SMTP Email Sender",
            version="1.1.0",
            author="Michael Landbo",
            description="Async SMTP adapter for UBP",
            supports_webhooks=False,
            supports_real_time=False
        )

    # --- Lifecycle ---

    async def _setup_platform(self) -> None:
        """SMTP kræver normalt ikke en vedvarende forbindelse ved start, vi tester bare config."""
        try:
            # Vi laver en hurtig connection test
            test_conn = aiosmtplib.SMTP(hostname=self.host, port=self.port, use_tls=False)
            await test_conn.connect()
            if self.use_tls:
                await test_conn.starttls()
            await test_conn.quit()
            self.logger.info(f"SMTP Connection verified to {self.host}:{self.port}")
        except Exception as e:
            self.logger.warning(f"Could not verify SMTP connection at startup: {e}")
            # Vi crasher ikke, da det kan være netværket er nede midlertidigt

    async def handle_platform_event(self, event: Dict[str, Any]) -> None:
        pass # SMTP modtager ikke events

    async def handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "not_implemented"}

    # --- Core Logic: Send Message ---

    async def send_message(self, context: AdapterContext, message: Dict[str, Any]) -> SendResult:
        """Sender en email via SMTP"""
        try:
            # Modtager kan være user_id (email) eller channel_id (email)
            recipient = context.channel_id or context.user_id

            # Fallback: Check om recipient ligger i message payload
            if not recipient and "to" in message:
                recipient = message["to"]

            if not recipient:
                return SimpleSendResult(False, error_message="Missing recipient email address")

            # Byg Email Objekt
            msg = EmailMessage()
            msg["From"] = self.default_sender
            msg["To"] = recipient
            msg["Subject"] = message.get("subject", "Message from UBP Bot")
            msg["Message-ID"] = make_msgid()

            content = message.get("content", "")
            html_content = message.get("html_content")

            # Set Body
            msg.set_content(content)
            if html_content:
                msg.add_alternative(html_content, subtype="html")

            # Håndter Attachments (hvis defineret i message dict)
            attachments = message.get("attachments", [])
            for att in attachments:
                fname = att.get("filename", "attachment")
                fdata = att.get("content") # Forventer bytes
                ctype = att.get("mime_type", "application/octet-stream")

                if fdata:
                    maintype, subtype = ctype.split("/", 1)
                    msg.add_attachment(fdata, maintype=maintype, subtype=subtype, filename=fname)

            # Send Async
            self.logger.info(f"Sending email to {recipient} via {self.host}")

            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                start_tls=self.use_tls,
                username=self.username,
                password=self.password
            )

            return SimpleSendResult(
                success=True,
                platform_message_id=msg["Message-ID"],
                details={"recipient": recipient}
            )

        except Exception as e:
            self.logger.error(f"SMTP Send Error: {e}")
            return SimpleSendResult(success=False, error_message=str(e))
