"""
FilePath: "/adapters/email/email_pop3.py"
Project: Unified Bot Protocol (UBP)
Component: POP3 Email Adapter (Inbound)
Version: 1.1.0 (Refactored for BaseAdapter 1.3.0)
"""

import asyncio
import poplib
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
    SimpleSendResult,
    AdapterStatus
)

class POP3EmailAdapter(PlatformAdapter):
    """
    Official UBP POP3 Adapter.
    Polls a POP3 server, downloads new emails, converts them to UBP messages,
    and deletes them from the server (standard POP3 behavior).
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.pop3_config = config.get('email_pop3', config)

        self.host = self.pop3_config.get("host")
        self.port = self.pop3_config.get("port", 995)
        self.username = self.pop3_config.get("username")
        self.password = self.pop3_config.get("password")
        self.use_ssl = self.pop3_config.get("use_ssl", True)
        self.poll_interval = self.pop3_config.get("poll_interval", 60)

        self._poll_task = None

    @property
    def platform_name(self) -> str:
        return "email_pop3"

    @property
    def capabilities(self) -> AdapterCapabilities:
        # POP3 er read-only polling
        return AdapterCapabilities(supported_capabilities=set())

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            platform="email_pop3",
            display_name="POP3 Listener",
            version="1.1.0",
            author="Michael Landbo",
            description="Polls POP3 server and processes emails"
        )

    # --- Lifecycle ---

    async def _setup_platform(self) -> None:
        """Starter polling loopet"""
        self.logger.info(f"Starting POP3 Polling on {self.host} every {self.poll_interval}s")
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
        await super().stop()

    async def send_message(self, context, message) -> SendResult:
        return SimpleSendResult(False, error_message="POP3 Adapter is read-only. Use SMTP Adapter to send.")

    async def handle_platform_event(self, event): pass
    async def handle_command(self, command): return {}

    # --- Polling Logic ---

    async def _poll_loop(self):
        while not self._shutdown_event.is_set():
            try:
                # Kør blokerende netværkskald i en executor for ikke at fryse botten
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._sync_check_mail)
            except Exception as e:
                self.logger.error(f"POP3 Polling Error: {e}")

            await asyncio.sleep(self.poll_interval)

    def _sync_check_mail(self):
        """Synkron logik der forbinder, henter og sletter mails"""
        mail = None
        try:
            # 1. Forbind
            if self.use_ssl:
                mail = poplib.POP3_SSL(self.host, self.port)
            else:
                mail = poplib.POP3(self.host, self.port)

            mail.user(self.username)
            mail.pass_(self.password)

            # 2. Tjek status
            num_messages = len(mail.list()[1])
            if num_messages == 0:
                mail.quit()
                return

            self.logger.info(f"POP3: Found {num_messages} messages")
            self.metrics["mailbox_size"] = num_messages

            # 3. Hent hver besked
            # POP3 indekserer fra 1 til N
            for i in range(1, num_messages + 1):
                try:
                    # Hent (RETR)
                    response, lines, octets = mail.retr(i)
                    raw_email = b"\r\n".join(lines)
                    msg = email.message_from_bytes(raw_email)

                    # Behandl Async (Send til Orchestrator)
                    # Vi bruger run_coroutine_threadsafe da vi er i en thread executor
                    asyncio.run_coroutine_threadsafe(
                        self._process_email(msg),
                        asyncio.get_running_loop()
                    ).result() # Vent på at den er afleveret før vi sletter

                    # Slet fra serveren (DELE) - Dette er "Mark as Read" i POP3
                    mail.dele(i)

                except Exception as e:
                    self.logger.error(f"Failed to process message {i}: {e}")
                    self.metrics["poll_errors"] = self.metrics.get("poll_errors", 0) + 1

            # 4. Luk og bekræft sletninger
            mail.quit()

        except Exception as e:
            self.logger.error(f"POP3 Connection Error: {e}")
            try:
                if mail: mail.quit()
            except: pass

    async def _process_email(self, msg):
        """Konverterer email objekt til UBP besked"""
        # Decode Subject
        subject_header = msg.get("Subject", "(No Subject)")
        decoded_list = decode_header(subject_header)
        subject = ""
        for token, encoding in decoded_list:
            if isinstance(token, bytes):
                subject += token.decode(encoding or "utf-8", errors="ignore")
            else:
                subject += token

        sender = msg.get("From", "Unknown")

        # Extract Body
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

        # Create UBP Context & Payload
        context = AdapterContext(
            tenant_id="default",
            user_id=sender,
            channel_id=sender,
            extras={"subject": subject, "protocol": "pop3"}
        )

        payload = {
            "type": "text",
            "content": body,
            "metadata": {"subject": subject, "source": "email_pop3"}
        }

        # Send til Runtime
        if self.connected:
            await self._send_to_orchestrator({
                "type": "user_message",
                "context": context.to_dict(),
                "payload": payload
            })
            self.metrics["messages_received"] += 1
