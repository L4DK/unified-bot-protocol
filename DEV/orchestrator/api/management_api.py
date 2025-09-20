# orchestrator/api/management_api.py
from fastapi import Request, HTTPException, Security
from ..security.rate_limiter import RateLimiter
from ..security.encryption import CredentialEncryption
from ..security.audit import AuditLogger
from ..security.authenticator import verify_admin
from ..storage import BotStorage
from ..models import BotDefinition, BotCredentials, BotRegistrationResponse
from ..utils import create_one_time_token

class SecureBotManagementAPI:
    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.encryption = CredentialEncryption()
        self.audit_logger = AuditLogger()

    @router.post("/bots")
    async def register_bot(
        self,
        request: Request,
        bot: BotDefinition,
        _: bool = Security(verify_admin)
    ) -> BotRegistrationResponse:
        """Register a new bot with security measures"""

        # Check rate limits
        ip_address = request.client.host
        is_limited, retry_after = await self.rate_limiter.is_rate_limited(
            ip_address,
            "registration"
        )

        if is_limited:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds"
            )

        # Generate and encrypt one-time token
        one_time_token = create_one_time_token()
        encrypted_token = self.encryption.encrypt(one_time_token)

        # Store bot with encrypted credentials
        await self.bot_storage.save_bot_credentials(
            BotCredentials(
                bot_id=bot.bot_id,
                api_key="",
                one_time_token=encrypted_token,
                created_at=datetime.utcnow()
            )
        )

        # Log the registration event
        await self.audit_logger.log_security_event(
            event_type="BOT_REGISTRATION",
            user_id=bot.bot_id,
            ip_address=ip_address,
            details={
                "bot_name": bot.name,
                "adapter_type": bot.adapter_type,
                "capabilities": bot.capabilities
            }
        )

        return BotRegistrationResponse(
            bot_id=bot.bot_id,
            one_time_registration_token=one_time_token,
            created_at=bot.created_at
        )