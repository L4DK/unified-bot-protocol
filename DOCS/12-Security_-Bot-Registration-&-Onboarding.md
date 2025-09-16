### 12\. Security: Bot Registration and Onboarding

The initial registration of a bot is the front door to the entire ecosystem. If this process is weak, the security of the entire framework is compromised. The onboarding workflow is designed to establish a verifiable and unique identity for each bot agent *before* it is permitted to join the network. No bot is trusted by default.

#### Design Philosophy

The philosophy is directly analogous to the **"secure boot"** process in modern computing.[1] Just as a computer's firmware cryptographically verifies the integrity of the operating system before loading it, our Orchestrator must verify the authenticity of a new bot agent before accepting its connection. The core principles are:

  * **Trust Must Be Explicitly Established:** A new bot instance is considered untrusted until it proves its legitimacy through a secure, out-of-band process.
  * **Initial Credentials Must Be Single-Use:** The credential used for the very first connection must be ephemeral and immediately invalidated upon use. This prevents replay attacks where a stolen initial token could be used to register multiple rogue agents.
  * **Separation of Concerns:** The administrative act of *defining* a bot (done by a human operator via the Management API) is completely separate from the technical act of a bot instance *connecting* for the first time. This separation ensures that only intentionally configured bots can join the network.
  * **Progressive Trust:** The system progresses from a temporary, single-use token to a persistent, long-lived credential, establishing a chain of trust from the initial administrative action to the bot's ongoing operations.

#### Technical Implementation & Step-by-Step Flow

The process involves a secure token exchange that transitions a bot from an unknown entity to a trusted, identified member of the fleet.

1.  **Step 1: Administrative Bot Definition (via Management API)**
    An administrator with proper credentials makes a `POST` request to the `/v1/bots` endpoint of the Management API. This is a trusted, authenticated action that tells the Orchestrator, "A new, legitimate bot of this type is expected to exist."

2.  **Step 2: Orchestrator Generates Credentials**
    In response to the successful API call, the Orchestrator generates two crucial pieces of data:

      * A unique, immutable `bot_id`.
      * A cryptographically secure, **`one_time_registration_token`**. This token is associated with the `bot_id` and is marked as "unused".

3.  **Step 3: Secure Configuration of the Bot Agent**
    The administrator receives the `bot_id` and the `one_time_registration_token` from the API response. They must now securely provide these values to the bot agent's runtime environment. This is typically done via:

      * Environment variables in a Docker container or Kubernetes deployment.
      * A secret management service (e.g., HashiCorp Vault, AWS Secrets Manager).
      * **Crucially, this token should never be hardcoded in the bot's source code.**

4.  **Step 4: The First Handshake**
    On its very first startup, the Bot Agent initiates a connection to the Orchestrator's C2 endpoint (gRPC/WebSocket). In its initial `HandshakeRequest`, it includes the `bot_id` and the `one_time_registration_token` in the `auth_token` field.

5.  **Step 5: Orchestrator Validation and Credential Issuance**
    The Orchestrator receives the handshake. Its logic proceeds as follows:

      * It looks up the `bot_id`.
      * It checks if the provided `auth_token` matches the stored, unused `one_time_registration_token`.
      * If they match, the Orchestrator performs three actions in a single atomic transaction:
        1.  Generates a new, persistent, long-lived credential (e.g., a high-entropy API Key).
        2.  Stores this new API Key, associating it with the `bot_id`.
        3.  **Permanently invalidates or deletes the `one_time_registration_token`**.
      * The Orchestrator then sends a `HandshakeResponse` to the agent. This response includes the newly generated long-lived API Key.

6.  **Step 6: Agent Persists the Long-Lived Credential**
    The Bot Agent receives the successful `HandshakeResponse` containing the new API Key. It **MUST** securely persist this key for all future restarts. This could involve writing it to a file on a persistent volume or storing it in a local secure wallet.

7.  **Step 7: Subsequent Connections**
    On any subsequent startup, the agent's logic will detect the persisted long-lived API Key. It will now use *this* key in the `auth_token` field of its `HandshakeRequest`. If an attacker tries to reuse the original `one_time_registration_token`, the Orchestrator will reject the handshake because the token has already been invalidated.

-----

### Real-Life Code Examples

#### 1\. Orchestrator Handshake Logic (Conceptual Python)

This example shows the server-side logic for handling the token exchange.

```python
# A simplified representation of a bot record in the database
bot_registry_db = {
    "bot-abc-123": {
        "one_time_token": "rego-xyz789-onetime-secret-token-456",
        "one_time_token_used": False,
        "long_lived_api_key": None
    }
}

def generate_long_lived_key():
    # In a real system, use a cryptographically secure random generator
    return "prod-key-" + str(uuid.uuid4())

def handle_handshake(request: ubp_v1.HandshakeRequest):
    bot_id = request.bot_id
    auth_token = request.auth_token

    bot_record = bot_registry_db.get(bot_id)

    if not bot_record:
        return build_handshake_failure("Invalid Bot ID")

    # --- Onboarding Logic for First-Time Connection ---
    if auth_token == bot_record["one_time_token"] and not bot_record["one_time_token_used"]:
        print(f"Orchestrator: First-time registration for bot {bot_id}.")
        
        # 1. Generate and store the new long-lived key
        new_api_key = generate_long_lived_key()
        bot_record["long_lived_api_key"] = new_api_key
        
        # 2. Invalidate the one-time token
        bot_record["one_time_token_used"] = True
        
        print(f"Orchestrator: Issued new long-lived key for {bot_id}.")
        
        # 3. Send the new key back to the agent in the response
        return build_handshake_success(issued_api_key=new_api_key)

    # --- Standard Logic for Subsequent Connections ---
    elif auth_token == bot_record["long_lived_api_key"]:
        print(f"Orchestrator: Bot {bot_id} authenticated with long-lived key.")
        return build_handshake_success()

    else:
        print(f"Orchestrator: Authentication failed for bot {bot_id}.")
        return build_handshake_failure("Authentication Failed")

```

#### 2\. Bot Agent Startup and Credential Management (Conceptual Python)

This example shows the agent's logic for handling its credentials across restarts.

```python
import os
import uuid

# Path to where the persistent key will be stored
PERSISTENT_KEY_FILE = "/var/data/bot/persistent_key.txt"

class BotAgent:
    def __init__(self):
        self.bot_id = os.getenv("BOT_ID")
        self.one_time_token = os.getenv("ONE_TIME_REGISTRATION_TOKEN")
        self.persistent_key = self._load_persistent_key()
        self.connection = None

    def _load_persistent_key(self):
        """Tries to load the long-lived key from a file."""
        if os.path.exists(PERSISTENT_KEY_FILE):
            with open(PERSISTENT_KEY_FILE, 'r') as f:
                return f.read().strip()
        return None

    def _save_persistent_key(self, key: str):
        """Saves the long-lived key to a file."""
        os.makedirs(os.path.dirname(PERSISTENT_KEY_FILE), exist_ok=True)
        with open(PERSISTENT_KEY_FILE, 'w') as f:
            f.write(key)
        self.persistent_key = key
        print("Agent: Successfully saved new persistent API key.")

    def get_auth_token(self):
        """Determines which token to use for the handshake."""
        if self.persistent_key:
            print("Agent: Using persistent API key for authentication.")
            return self.persistent_key
        elif self.one_time_token:
            print("Agent: Using one-time registration token for first-time authentication.")
            return self.one_time_token
        else:
            raise ValueError("No authentication credentials found.")

    def connect_and_handshake(self):
        #... connection logic...
        
        handshake_req = ubp_v1.HandshakeRequest(
            bot_id=self.bot_id,
            instance_id=f"instance-{uuid.uuid4()}",
            auth_token=self.get_auth_token()
        )
        
        # Send handshake and wait for response
        handshake_response = self.connection.send_and_wait(handshake_req)

        if handshake_response.status == "SUCCESS":
            # Check if a new key was issued (only happens on first registration)
            if handshake_response.HasField("issued_api_key") and not self.persistent_key:
                self._save_persistent_key(handshake_response.issued_api_key)
        else:
            raise ConnectionError("Handshake failed!")

```

#### 3\. Protobuf Schema Extension

To support this flow, the `HandshakeResponse` message can be extended with an optional field to carry the new key.

File: `ubp/v1/core.proto` (addition to `HandshakeResponse`)

```protobuf
message HandshakeResponse {
  enum Status {
    SUCCESS = 0;
    AUTH_FAILED = 1;
    INVALID_BOT_ID = 2;
  }
  Status status = 1;
  string error_message = 2;
  int32 heartbeat_interval_sec = 3;
  
  // This field is ONLY populated in the response to a successful
  // handshake that used a one-time registration token.
  // It contains the new long-lived key the agent must use going forward.
  optional string issued_api_key = 4;
}
```

This secure onboarding process ensures that only authorized and properly configured bots can gain access to the UBP network, forming the first and most important layer of the framework's zero-trust security model.
