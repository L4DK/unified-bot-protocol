### 14\. Security: Command Integrity and Encryption

Beyond authenticating the bot and authorizing its actions, the framework must protect the data in transit, ensuring both its **integrity** (the message has not been tampered with) and its **confidentiality** (the message content is secret). While the transport layer (TLS/WSS) provides essential point-to-point encryption, certain use cases demand an even higher level of message-level security. This is the principle of **defense in depth**.

#### Design Philosophy

The philosophy is to provide **proportional, message-level security**. Not all commands require the same level of protection. A request for a public document is low-risk, but a command to execute a financial transaction is high-risk. The framework provides *optional but standardized* mechanisms for higher security, avoiding unnecessary performance overhead for routine operations while ensuring maximum protection for critical ones.

  * **Integrity and Non-Repudiation:** For high-stakes operations, it must be possible to cryptographically prove that a specific bot sent a specific command and that the command was not altered in transit. This prevents message tampering and provides a strong, auditable trail, a concept known as non-repudiation.[1]
  * **Confidentiality (End-to-End Encryption):** For commands containing highly sensitive data (e.g., personally identifiable information, financial details), the content must be protected even from intermediary components within the UBP framework itself (like load balancers or even the Orchestrator's logging system). The data should only be readable by the final intended recipient. This is the core principle of End-to-End Encryption (E2EE).[2]

#### 1\. Command Signing (Integrity)

This mechanism is used to guarantee that a command has not been altered and to verify its origin.

  * **Purpose:** To prevent message tampering and provide non-repudiation.
  * **How it Works (Asymmetric Cryptography):**
    1.  **Key Provisioning:** During the secure onboarding process, each Bot Agent is provisioned with a unique public/private key pair (e.g., RSA or ECDSA). The agent securely stores its private key, while its public key is registered with the Orchestrator.
    2.  **Signing (Sender):** When a Bot Agent needs to send a signed command, it performs the following steps:
        a. It takes the complete, serialized `CommandRequest` payload.
        b. It calculates a cryptographic hash of this payload (e.g., SHA-256).
        c. It encrypts this hash using its own **private key**. This encrypted hash is the **digital signature**.[3]
        d. The signature is attached to the UBP message metadata.
    3.  **Verification (Receiver):** When the Orchestrator receives the signed command, it performs these steps:
        a. It independently calculates the SHA-256 hash of the received `CommandRequest` payload.
        b. It retrieves the sender's **public key** from its bot registry.
        c. It uses the public key to decrypt the signature received in the message metadata.
        d. It compares its calculated hash with the decrypted hash. If they match, the signature is valid.[1]
  * **Guarantees:** A valid signature proves two things:
      * **Authenticity:** Only the holder of the private key could have created the signature.
      * **Integrity:** If even a single bit of the command payload had been altered in transit, the hashes would not match, and verification would fail.

**Protobuf Schema Extension for Signing:**
The `UbpMessage` is extended with an optional field for the signature.

```protobuf
// In ubp/v1/core.proto

message UbpMessage {
  string message_id = 1;
  string trace_id = 2;
  
  // Optional digital signature of the 'payload' bytes.
  bytes signature = 9;
  // The algorithm used for the signature, e.g., "rsa-sha256".
  string signature_algorithm = 10;

  oneof payload {
    //... other payload types
  }
}
```

**Code Example: Signing and Verifying (Python with `cryptography` library)**

```python
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature
import ubp.v1.core_pb2 as ubp_v1
import uuid

# --- Key Generation (done once during onboarding) ---
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()

# --- On the Bot Agent (Sender) ---
def sign_command(command_req: ubp_v1.CommandRequest) -> ubp_v1.UbpMessage:
    wrapper = ubp_v1.UbpMessage(
        message_id=str(uuid.uuid4()),
        command_request=command_req
    )
    
    # We sign the serialized payload bytes
    payload_bytes = wrapper.payload.SerializeToString()
    
    signature = private_key.sign(
        payload_bytes,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    
    wrapper.signature = signature
    wrapper.signature_algorithm = "rsa-sha256"
    return wrapper

# --- On the Orchestrator (Receiver) ---
def verify_signature(message: ubp_v1.UbpMessage) -> bool:
    if not message.HasField("signature"):
        print("Message is not signed.")
        return True # Or False, depending on policy

    payload_bytes = message.payload.SerializeToString()
    
    try:
        public_key.verify(
            message.signature,
            payload_bytes,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        print("Signature is VALID.")
        return True
    except InvalidSignature:
        print("Signature is INVALID. Message may have been tampered with!")
        return False

# --- Demo ---
my_command = ubp_v1.CommandRequest(command_name="execute_trade", command_id="cmd-1")
signed_message = sign_command(my_command)
is_valid = verify_signature(signed_message)
```

-----

#### 2\. End-to-End Encryption (E2EE)

This mechanism is used to protect the confidentiality of the command's content from all intermediaries.

  * **Purpose:** To ensure that only the final recipient can read the sensitive data within a command's payload.
  * **Why it's needed (beyond TLS):** TLS encrypts the communication channel between two points (e.g., Agent -\> Orchestrator). However, the message is in plaintext inside the Orchestrator's memory. This means the Orchestrator's logic, and potentially its logging systems, could access the sensitive data. E2EE encrypts the data *inside* the message, so that even the Orchestrator cannot read it if it is not the final destination.[2]
  * **How it Works:**
    1.  **Key Provisioning:** As with signing, both the Orchestrator and the agents have public/private key pairs.
    2.  **Encryption (Sender):** The Orchestrator needs to send a command with a sensitive payload (e.g., user credentials) to a specific Bot Agent.
        a. It retrieves the target Bot Agent's **public key** from the service registry.
        b. It uses this public key to encrypt the sensitive part of the message (e.g., the `arguments` payload).
        c. The encrypted payload is placed in the `CommandRequest`.
    3.  **Decryption (Receiver):** The Bot Agent receives the command.
        a. It uses its own **private key** to decrypt the encrypted payload.
        b. Only this agent, which possesses the corresponding private key, can decrypt and read the data.

**Protobuf Schema Extension for E2EE:**
We can add a field to the `CommandRequest` to indicate that its payload is encrypted.

```protobuf
// In ubp/v1/core.proto

message CommandRequest {
  string command_id = 1;
  string command_name = 2;
  
  // The arguments payload. If is_encrypted is true, this contains
  // the ciphertext. Otherwise, it contains the plaintext Any object.
  google.protobuf.Any arguments = 3;
  
  string user_context_token = 4;
  
  // Flag indicating if the 'arguments' payload is encrypted.
  bool is_encrypted = 5;
  // The algorithm used for encryption, e.g., "rsa-oaep-mgf1-sha256".
  string encryption_algorithm = 6;
}
```

**Code Example: E2EE for Command Arguments (Python)**

```python
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from google.protobuf.any_pb2 import Any
import ubp.v1.core_pb2 as ubp_v1

# Assume agent_private_key and agent_public_key are pre-shared
agent_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
agent_public_key = agent_private_key.public_key()

# --- On the Orchestrator (Sender) ---
def create_encrypted_command(sensitive_payload: bytes) -> ubp_v1.CommandRequest:
    ciphertext = agent_public_key.encrypt(
        sensitive_payload,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    # The encrypted bytes are wrapped in a generic Any proto for transport
    encrypted_args = Any()
    encrypted_args.value = ciphertext
    
    command_req = ubp_v1.CommandRequest(
        command_name="process_sensitive_data",
        arguments=encrypted_args,
        is_encrypted=True,
        encryption_algorithm="rsa-oaep-mgf1-sha256"
    )
    return command_req

# --- On the Bot Agent (Receiver) ---
def decrypt_command_args(command_req: ubp_v1.CommandRequest) -> bytes | None:
    if not command_req.is_encrypted:
        print("Arguments are not encrypted.")
        return command_req.arguments.value

    try:
        plaintext = agent_private_key.decrypt(
            command_req.arguments.value,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        print("Successfully decrypted arguments.")
        return plaintext
    except Exception as e:
        print(f"Decryption failed: {e}")
        return None

# --- Demo ---
sensitive_data = b'{"user_ssn": "000-00-0000"}'
encrypted_command = create_encrypted_command(sensitive_data)
decrypted_data = decrypt_command_args(encrypted_command)

if decrypted_data:
    print(f"Decrypted Data: {decrypted_data.decode()}")
```

By providing these optional, message-level security features, the UBP framework allows developers to apply the appropriate level of protection for each specific operation, creating a system that is secure by design and capable of handling even the most sensitive workloads.
