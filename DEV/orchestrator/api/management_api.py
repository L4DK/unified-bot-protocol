# FilePath: "/DEV/orchestrator/api/management_api.py"
# Projekt: Unified Bot Protocol (UBP)
# Beskrivelse: Management API til registrering og styring af bots.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.0.0"

from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader

from ..security.rate_limiter import RateLimiter
from ..security.encryption import CredentialEncryption
from ..security.audit import AuditLogger
from ..storage import BotStorage
from ..models import BotDefinition, BotCredentials, BotRegistrationResponse
from ..utils import create_one_time_token

# Opret router
router = APIRouter(tags=["Bot Management"])

# Services Initialization
rate_limiter = RateLimiter()
encryption = CredentialEncryption()
audit_logger = AuditLogger()
bot_storage = BotStorage()

# Dummy Admin Verification (Erstat med rigtig logik senere)
api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

async def verify_admin(key: str = Security(api_key_header)):
    """Simpel check for admin rettigheder."""
    # TODO: Flyt til settings og brug rigtig auth
    if key != "admin-secret-123":
        raise HTTPException(status_code=403, detail="Invalid Admin Key")
    return True

@router.post("/bots/register", response_model=BotRegistrationResponse)
async def register_bot(
    request: Request,
    bot: BotDefinition,
    authorized: bool = Security(verify_admin)
):
    """
    Register a new bot with security measures.
    Requires X-Admin-Key header.
    """

    # 1. Check Rate Limits
    ip_address = request.client.host if request.client else "unknown"
    is_limited, retry_after = await rate_limiter.is_rate_limited(
        ip_address,
        "registration"
    )

    if is_limited:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds"
        )

    # 2. Check if bot already exists
    existing = await bot_storage.get_bot_definition(bot.bot_id)
    if existing:
         raise HTTPException(status_code=409, detail=f"Bot with ID {bot.bot_id} already exists")

    # 3. Generate and encrypt one-time token (OTT)
    one_time_token = create_one_time_token()
    encrypted_token = encryption.encrypt(one_time_token)

    # 4. Save Definition
    await bot_storage.save_bot_definition(bot)

    # 5. Store Encrypted Credentials
    await bot_storage.save_bot_credentials(
        BotCredentials(
            bot_id=bot.bot_id,
            api_key="", # Sættes først efter handshake rotation
            one_time_token=encrypted_token,
            created_at=datetime.utcnow()
        )
    )

    # 6. Log the registration event
    await audit_logger.log_security_event(
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
