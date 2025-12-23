"""
FilePath: "/adapters/email/email_imap.py"
Project: Unified Bot Protocol (UBP)
Component: IMAP Email Adapter (Inbound)
Version: 1.1.1 (Fixed e_id scope error)
"""

import asyncio
import imaplib
import email
from email.header import decode_header
from typing import Dict, Any

from adapters.base_adapter import (
    PlatformAdapter,
    AdapterCapabilities,
    AdapterMetadata,
    AdapterContext,
    PlatformCapability,
    SendResult,
    SimpleSendResult
)

class IMAPEmailAdapter(PlatformAdapter):
    """
    Official UBP IMAP Adapter.
    Polls an inbox and converts emails to UBP User Messages.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.imap_config = config.get('email_imap', config) # Support both keys

        self.host = self.imap_config.get("host")
        self.port = self.imap_config.get("port", 993)
        self.username = self.imap_config.get("username")
        self.password = self.imap_config.get("password")
        self.poll_interval = self.imap_config.get("poll_interval", 60)
        self.mailbox = self.imap_config.get("mailbox", "INBOX")

        self._poll_task = None

    @property
    def platform_name(self) -> str:
        return "email_imap"

    @property
    def capabilities(self) -> AdapterCapabilities:
        # Denne adapter kan kun modtage (via polling), ikke sende
        return AdapterCapabilities(supported_capabilities=set())

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="email_imap",
            display_name="IMAP Listener",
            version="1.1.1",
            author="Michael Landbo",
            description="Polls IMAP inbox for new messages"
        )

    # --- Lifecycle ---

    async def _setup_platform(self) -> None:
        """Starter polling loopet"""
        self.logger.info(f"Starting IMAP Polling on {self.host} every {self.poll_interval}s")
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
        await super().stop()

    async def send_message(self, context, message) -> SendResult:
        return SimpleSendResult(False, error_message="IMAP Adapter is read-only. Use SMTP Adapter to send.")

    async def handle_platform_event(self, event): pass
    async def handle_command(self, command): return {}

    # --- Polling Logic ---

    async def _poll_loop(self):
        while not self._shutdown_event.is_set():
            try:
                # Dette er et blokerende kald, så vi kører det i en executor for ikke at fryse async loopet
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._sync_check_mail)
            except Exception as e:
                self.logger.error(f"IMAP Polling Error: {e}")

            await asyncio.sleep(self.poll_interval)

    def _sync_check_mail(self):
        """Synkron metode der kører i en tråd. Håndterer IMAP forbindelsen."""
        try:
            mail = imaplib.IMAP4_SSL(self.host, self.port)
            mail.login(self.username, self.password)
            mail.select(self.mailbox)

            # Søg efter ulæste beskeder
            status, messages = mail.search(None, "(UNSEEN)")
            if status != "OK":
                mail.logout()
                return

            email_ids = messages[0].split()
            if not email_ids:
                mail.logout()
                return

            self.logger.info(f"IMAP: Found {len(email_ids)} new emails")

            for e_id in email_ids:
                _, msg_data = mail.fetch(e_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])

                        # Kør async processering thread-safe og VENT på resultatet
                        future = asyncio.run_coroutine_threadsafe(
                            self._process_email(msg),
                            asyncio.get_running_loop()
                        )

                        try:
                            # Vent på at beskeden er afleveret til systemet før vi markerer som læst
                            future.result(timeout=10)

                            # Mark as read (når vi er her, gik processeringen godt)
                            mail.store(e_id, "+FLAGS", "\\Seen")
                        except Exception as e:
                            self.logger.error(f"Failed to process email {e_id}: {e}")

            mail.logout()
        except Exception as e:
            self.logger.error(f"Sync IMAP Error: {e}")

    async def _process_email(self, msg):
        """Konverter og send til UBP"""
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8")

        sender = msg.get("From")

        # Simpel body extraction (kun text/plain)
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="ignore")
                    break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(errors="ignore")

        # Context
        context = AdapterContext(
            tenant_id="default",
            user_id=sender,
            channel_id=sender, # For email er kanal og bruger ofte det samme (afsender)
            extras={"subject": subject}
        )

        # Payload
        payload = {
            "type": "text",
            "content": body,
            "metadata": {"subject": subject, "source": "email_imap"}
        }

        # Send til systemet
        if self.connected:
            await self._send_to_orchestrator({
                "type": "user_message",
                "context": context.to_dict(),
                "payload": payload
            })
            self.metrics["messages_received"] += 1
