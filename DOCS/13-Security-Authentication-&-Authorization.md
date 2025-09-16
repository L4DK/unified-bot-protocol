### 13\. Security: Authentication & Authorization

Once a bot has been securely onboarded and has its identity, the framework must rigorously control what that bot is allowed to do. A critical aspect of the security model is the explicit distinction between a bot's identity and a user's identity. A bot may need to act as an autonomous system agent, or it may need to act on behalf of a specific human user. These two operational contexts require fundamentally different authentication and authorization models.

#### Design Philosophy

The philosophy is to enforce a **dual-mode, zero-trust security model** that separates **Authentication** (who you are) from **Authorization** (what you are allowed to do). We never assume that just because a bot is a valid, authenticated member of the system, it has the right to access any data or perform any action.

  * **System Identity vs. User Identity:** The framework must always be able to answer two distinct questions:
    1.  "Is this a valid, known bot instance?" (Authentication of the bot itself).
    2.  "Is this bot authorized to perform this specific action on behalf of this specific user?" (Authorization delegated by a user).
  * **Principle of Least Privilege:** By default, a bot has no permissions to access user-specific data. It must explicitly be granted those permissions by the user through a secure, auditable consent process.
  * **Standardization:** We rely on industry-standard protocols for both modes. This avoids reinventing the wheel and allows for integration with existing identity providers and security infrastructure. We use simple API Keys or mTLS for system identity and the robust OAuth 2.0 framework for user-delegated identity.[2, 3, 4]

#### Mode 1: System-to-System Authentication

This mode is used to authenticate the bot *itself*. It verifies the identity of the machine or process making the request.

  * **Purpose:** To confirm that a request is coming from a legitimate, registered bot instance. This is used for background tasks, internal system operations, or any action not tied to a specific user context.
  * **Mechanisms:**
      * **API Key:** This is the most common method. The long-lived API Key issued during the onboarding process is included in every request. For REST calls, this is typically in an HTTP header (e.g., `Authorization: Bearer <bot_api_key>`). For the C2 channel, it's in the `auth_token` field of the `HandshakeRequest`. This method is simple and efficient for trusted server-to-server communication.[2]
      * **Mutual TLS (mTLS):** For higher-security environments, mTLS provides stronger, cryptographic proof of identity. Both the Bot Agent (client) and the Orchestrator (server) present X.509 certificates to each other. The connection is only established if both parties can validate the other's certificate against a trusted Certificate Authority. This ensures that not only is the bot legitimate, but it's also talking to the legitimate Orchestrator, preventing man-in-the-middle attacks.[5]
  * **Scope:** This authentication grants the bot access to system-level resources and confirms its right to be on the network, but it grants **zero** access to user-specific data.

**Code Example: API Key Validation Middleware (Python/FastAPI)**

```python
from fastapi import Request, HTTPException, status

# A simple in-memory database of valid bot API keys
VALID_API_KEYS = {
    "prod-key-abc-123": {"bot_id": "bot-data-processor-01"},
    "prod-key-def-456": {"bot_id": "bot-slack-adapter-01"}
}

async def verify_bot_api_key(request: Request):
    """
    This dependency checks the 'Authorization' header for a valid bot API key.
    """
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bot authentication credentials"
        )
    
    api_key = auth_header.split(" ")[1]
    
    bot_identity = VALID_API_KEYS.get(api_key)
    if not bot_identity:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bot API key"
        )
    
    # Attach the verified bot identity to the request state for later use
    request.state.bot = bot_identity
    return bot_identity
```

-----

#### Mode 2: User-Delegated Authorization

This mode is used when a bot needs to access protected resources or perform actions on behalf of a human user (e.g., reading a user's emails, posting to their calendar).

  * **Purpose:** To confirm that a human user has explicitly granted the bot permission to perform a specific action on their behalf.
  * **Mechanism: OAuth 2.0 Authorization Code Flow**
    The architecture mandates the use of the OAuth 2.0 framework, which is the industry standard for delegated authorization.[2, 3, 6] The flow works as follows:
    1.  **Redirection:** The bot, via its user interface, redirects the user to a trusted Authorization Server (e.g., Microsoft Entra ID, Google Identity Platform, Auth0).
    2.  **User Consent:** The user authenticates with the Authorization Server and is presented with a consent screen that clearly lists the permissions (called **scopes**) the bot is requesting (e.g., `calendar.read`, `mail.send`).
    3.  **Authorization Grant:** If the user approves, the Authorization Server redirects them back to the bot with a temporary, single-use **authorization code**.
    4.  **Token Exchange:** The bot's backend securely exchanges this authorization code with the Authorization Server for an **access token** and a **refresh token**.
    5.  **API Call:** The short-lived access token is then included in all subsequent API calls to protected resources. For UBP, this token is placed in the `user_context_token` field of the `CommandRequest`.
  * **Scope:** The access token contains the specific scopes the user consented to. The Orchestrator **MUST** validate that the token contains the required scope for the requested operation. For example, a command to read a calendar must be accompanied by a token with the `calendar.read` scope.[3, 7]

**Code Example: User-Delegated Token Validation (Conceptual Python)**

```python
import jwt # PyJWT library for decoding JWTs

# A fictional public key from the Authorization Server to verify the token's signature
AUTH_SERVER_PUBLIC_KEY = "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"

def verify_user_token_and_scopes(token: str, required_scope: str):
    """
    Validates a JWT access token and checks for a required scope.
    """
    if not token:
        raise HTTPException(status_code=401, detail="User authorization token is missing.")
        
    try:
        # Decode the JWT. In a real app, this also verifies the signature,
        # expiration time (exp), and issuer (iss).
        decoded_token = jwt.decode(
            token, AUTH_SERVER_PUBLIC_KEY, algorithms=, audience="my-api"
        )
        
        # The scopes are typically in a 'scp' or 'scope' claim.
        scopes = decoded_token.get("scp", "").split(" ")
        
        if required_scope not in scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Missing required scope: {required_scope}"
            )
            
        # Return the user's identity (e.g., from the 'sub' claim)
        return {"user_id": decoded_token.get("sub")}

    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid user token: {e}")

# --- Example usage in an Orchestrator command handler ---
def handle_read_calendar_command(command: ubp_v1.CommandRequest):
    # This command requires user-delegated permission.
    user_context_token = command.user_context_token
    
    # Verify the token and ensure it has the 'calendar.read' scope.
    user_identity = verify_user_token_and_scopes(user_context_token, "calendar.read")
    
    # If verification passes, proceed with the operation.
    print(f"Executing read_calendar for user {user_identity['user_id']}")
    #... logic to read the user's calendar...
```

-----

### The Dual-Validation Model in Practice

A robust request within the UBP must therefore carry and validate both identities when necessary.

**Scenario:** A bot needs to read a user's calendar.

1.  **Connection Authentication (System Identity):** The Bot Agent establishes its gRPC/WebSocket connection. The Orchestrator validates its long-lived API key during the handshake. The connection is now trusted as coming from a legitimate bot.
2.  **Command Authorization (User Identity):** The bot sends a `CommandRequest` with `command_name: "calendar.read"`. This command **must** include the user's OAuth 2.0 access token in the `user_context_token` field.
3.  **Orchestrator's Dual Validation:**
      * The Orchestrator's application logic receives the command over the already-authenticated connection.
      * It inspects the command and sees it requires user context.
      * It calls a function like `verify_user_token_and_scopes` to validate the `user_context_token`.
      * This function confirms the token is valid, unexpired, and contains the `calendar.read` scope.
4.  **Execution:** Only after both the bot's system identity and the user's delegated authorization are confirmed does the Orchestrator proceed to execute the command.

This dual-validation model provides a comprehensive, zero-trust security posture that rigorously enforces both system and user-level permissions, ensuring that bots can act powerfully but only within the strict boundaries defined by user consent.
