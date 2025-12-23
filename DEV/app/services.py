# FilePath: "/DEV/app/services.py"
# Projekt: Unified Bot Protocol (UBP)
# Beskrivelse: Service Layer til initialisering af adaptere og routing af beskeder.
#              Demonstrerer "Wiring" af Core Router med Adapters.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.2.0.0"

import asyncio
import logging
import os
from typing import Dict, Any, Optional

# Korrekte imports baseret på din mappestruktur
try:
    from adapters.registry import AdapterRegistry
    from adapters.email.email_smtp import SMTPEmailAdapter
    # Vi bruger Telegram som eksempel i stedet for MQTT, da MQTT adapteren manglede i fillisten
    from adapters.telegram.telegram_adapter import TelegramAdapter

    from integrations.core.routing.policy_engine import PolicyEngine
    from integrations.core.routing.message_router import MessageRouter
except ImportError as e:
    logging.error(f"Failed to import UBP modules. Ensure you are running from /DEV root. Error: {e}")
    raise

# Setup Logging
logger = logging.getLogger("UBP.Services")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

class ServiceLayer:
    """
    Central service klasse der håndterer initialisering af adaptere
    og routing logik. Kan injiceres i FastAPI endpoints.
    """

    def __init__(self):
        self.registry = AdapterRegistry()
        self.router: Optional[MessageRouter] = None
        self.policy: Optional[PolicyEngine] = None
        self.initialized = False

    def initialize(self):
        """Loader konfiguration og registrerer adaptere."""
        if self.initialized:
            return

        logger.info("Initializing Service Layer...")

        # 1. Load Policy Engine
        # Definerer regler for hvilke platforme der må bruges og begrænsninger
        self.policy = PolicyEngine({
            "allow_platforms": ["email", "telegram", "internal_logs"],
            "max_content_length": 10000,
            "require_capabilities": ["supports_text"]
        })

        # 2. Registrer Adapters
        # VIGTIGT: Credentials hentes nu fra Environment Variables (Sikkerhed)

        # Email Adapter Setup
        if os.getenv("SMTP_ENABLED", "false").lower() == "true":
            try:
                self.registry.register("email", SMTPEmailAdapter({
                    "host": os.getenv("SMTP_HOST", "smtp.example.com"),
                    "port": int(os.getenv("SMTP_PORT", 587)),
                    "username": os.getenv("SMTP_USER", "bot@example.com"),
                    "password": os.getenv("SMTP_PASSWORD", ""), # Securely loaded
                    "from": os.getenv("SMTP_FROM", "bot@example.com"),
                    "use_tls": True
                }))
                logger.info("Adapter registered: Email")
            except Exception as e:
                logger.error(f"Failed to register Email adapter: {e}")

        # Telegram Adapter Setup (Eksempel på udskiftning af MQTT)
        if os.getenv("TELEGRAM_ENABLED", "false").lower() == "true":
            try:
                self.registry.register("telegram", TelegramAdapter({
                    "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
                    "webhook_url": os.getenv("TELEGRAM_WEBHOOK_URL", "")
                }))
                logger.info("Adapter registered: Telegram")
            except Exception as e:
                logger.error(f"Failed to register Telegram adapter: {e}")

        # 3. Initialize Router
        self.router = MessageRouter(self.registry, self.policy)
        self.initialized = True
        logger.info("Service Layer fully initialized.")

    async def route_message(self, message: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Wrapper for at route beskeder gennem systemet."""
        if not self.router:
            self.initialize()

        try:
            return await self.router.route_message(message, context)
        except Exception as e:
            logger.error(f"Routing error: {e}")
            return {"status": "error", "message": str(e)}

# Singleton instans til brug i applikationen
services = ServiceLayer()

# ==========================================
# Main entry point for manuel test / CLI kørsel
# ==========================================
async def main():
    """Test funktion til at verificere wiring."""
    # Sæt dummy env vars til test (I prod sættes disse i .env filen)
    os.environ["SMTP_ENABLED"] = "true"
    os.environ["TELEGRAM_ENABLED"] = "true"
    os.environ["SMTP_PASSWORD"] = "dummy_password"

    # Initialize
    services.initialize()

    # Test Email Routing
    logger.info("--- Testing Email Routing ---")
    email_msg = {
        "type": "text",
        "content": "Hello via UBP Service Layer!",
        "to": "user@example.com",
        "subject": "Greetings"
    }
    email_ctx = {
        "tenant_id": "acme",
        "target_platform": "email",
        "user_id": "u-123"
    }
    result_email = await services.route_message(email_msg, email_ctx)
    print(f"Email Result: {result_email}")

    # Test Telegram Routing
    logger.info("--- Testing Telegram Routing ---")
    tg_msg = {
        "type": "text",
        "content": "Hello from UBP",
        "chat_id": "123456789"
    }
    tg_ctx = {
        "tenant_id": "acme",
        "target_platform": "telegram",
        "user_id": "u-123"
    }
    result_tg = await services.route_message(tg_msg, tg_ctx)
    print(f"Telegram Result: {result_tg}")

if __name__ == "__main__":
    asyncio.run(main())
