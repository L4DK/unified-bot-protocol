### 10\. The Conversational Context API (RESTful)

Stateful conversational agents, particularly those based on LLMs, require a mechanism to persist and retrieve context across multiple turns of a conversation. A single user interaction is often part of a larger dialogue. For a bot to be effective, it must remember previous parts of the conversation, such as user preferences, items in a shopping cart, or the last question asked. The Conversational Context API provides a simple, scalable, and session-scoped key-value store for this purpose.

#### Design Philosophy

The core philosophy is to **externalize conversational state**. The bots themselves are designed to be stateless, which makes them highly scalable and resilient. However, conversations are inherently stateful. This API provides a dedicated, centralized service to manage that state, acting as the bot's "short-term memory".[1]

  * **Simplicity and Accessibility:** The API is designed as a simple RESTful document store. This makes it incredibly easy for any bot, written in any language, to use standard HTTP clients to save and retrieve context without needing complex database connectors or state management libraries.[2]
  * **Session-Scoped:** Context is strictly partitioned by a `session_id`. This ensures that the context from one user's conversation is completely isolated from another's.
  * **Namespace-Driven:** Within a single session, context is further partitioned by a `namespace`. This is a crucial feature for multi-bot orchestration. It allows different bots (e.g., a "user profile bot" and a "shopping cart bot") to participate in the same user session and store their own data without overwriting or interfering with each other's context.[2]
  * **Ephemeral by Design:** Conversational context is typically transient. To prevent the indefinite storage of stale data, the API mandates a **Time-To-Live (TTL)** on all stored data. This ensures that context automatically expires after a defined period of inactivity, which is critical for data hygiene, resource management, and compliance with data privacy principles.[2]

#### Technical Implementation & Features

  * **Protocol:** All communication is over HTTPS.
  * **Data Format:** All request and response bodies use `application/json`.
  * **Authentication:** Requests are authenticated using the bot's system-level API key.
  * **Key Resources:** The primary resource is a `document` identified by a composite key of `session_id` and `namespace`.

-----

### Detailed Endpoint Specification

#### 1\. Save or Update Properties (Upsert)

This endpoint is used to add new properties or update existing ones for a given session and namespace. It performs an "upsert" operation: existing keys in the JSON payload are overwritten, and new keys are created.

  * **Endpoint:** `POST /v1/context/{session_id}/{namespace}`
  * **Description:** Creates or updates the context document for a specific session and namespace. This operation is idempotent for a given payload.
  * **Request Body:**
    ```json
    {
      "ttlSeconds": 3600,
      "payload": {
        "user_name": "Alex",
        "preferred_language": "en-US"
      }
    }
    ```
      * `ttlSeconds` (integer, **required**): The number of seconds from now that this context document should live. Each `POST` request resets the timer.[2]
      * `payload` (object, **required**): The JSON object containing the key-value pairs to be stored.
  * **Success Response (`201 Created`):**
    ```json
    {
      "documentKey": "session-xyz-123:user_profile",
      "success": true
    }
    ```

**Code Examples:**

  * **cURL:**
    ```bash
    curl -X POST "https://api.orchestrator.example.com/v1/context/session-xyz-123/user_profile" \
         -H "Authorization: Bearer <bot_api_key>" \
         -H "Content-Type: application/json" \
         -d '{
               "ttlSeconds": 3600,
               "payload": {
                 "user_name": "Alex",
                 "preferred_language": "en-US"
               }
             }'
    ```
  * **Python (`requests`):**
    ```python
    import requests

    def save_user_profile(session_id: str, name: str, language: str):
        api_url = f"https://api.orchestrator.example.com/v1/context/{session_id}/user_profile"
        headers = {
            "Authorization": "Bearer <bot_api_key>",
            "Content-Type": "application/json"
        }
        data = {
            "ttlSeconds": 3600, # Context will expire in 1 hour
            "payload": {
                "user_name": name,
                "preferred_language": language
            }
        }
        response = requests.post(api_url, headers=headers, json=data)
        response.raise_for_status()
        print("User profile context saved successfully.")

    save_user_profile("session-xyz-123", "Alex", "en-US")
    ```

-----

#### 2\. Retrieve Properties

This endpoint retrieves the entire JSON document of properties stored for a given session and namespace.

  * **Endpoint:** `GET /v1/context/{session_id}/{namespace}`
  * **Description:** Fetches the context document for a specific session and namespace.
  * **Success Response (`200 OK`):**
    ```json
    {
      "user_name": "Alex",
      "preferred_language": "en-US"
    }
    ```
  * **Not Found Response (`404 Not Found`):** If the context does not exist or has expired, the API returns a 404.

**Code Examples:**

  * **cURL:**
    ```bash
    curl -X GET "https://api.orchestrator.example.com/v1/context/session-xyz-123/user_profile" \
         -H "Authorization: Bearer <bot_api_key>"
    ```
  * **Python (`requests`):**
    ```python
    import requests

    def get_user_profile(session_id: str) -> dict | None:
        api_url = f"https://api.orchestrator.example.com/v1/context/{session_id}/user_profile"
        headers = {"Authorization": "Bearer <bot_api_key>"}
        
        response = requests.get(api_url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print("No context found for this session.")
            return None
        else:
            response.raise_for_status()

    profile = get_user_profile("session-xyz-123")
    if profile:
        print(f"Retrieved user profile: {profile}")
    ```

-----

### Interaction Flow: A Multi-Bot Scenario

**Scenario:** A user interacts with a retail bot.

**Turn 1: User provides their name.**

  * **User:** "Hi, my name is Jane."
  * **Bot A (Profile Bot):** Makes a `POST` to `/v1/context/session-abc-456/profile` with `{"payload": {"name": "Jane"}, "ttlSeconds": 1800}`.

**Turn 2: User adds an item to their cart.**

  * **User:** "Add a blue shirt to my cart."
  * **Bot B (Shopping Bot):** Makes a `POST` to `/v1/context/session-abc-456/cart` with `{"payload": {"items":, "last_updated": "..."}}, "ttlSeconds": 1800}`. Note that this does not affect the `/profile` namespace.

**Turn 3: User asks for a personalized greeting.**

  * **User:** "Can you greet me by my name?"
  * **Bot A (Profile Bot):** Makes a `GET` to `/v1/context/session-abc-456/profile`.
  * **API Response:** `{"name": "Jane"}`
  * **Bot A (Profile Bot):** "Of course, hello Jane\!"

This API provides a simple yet powerful mechanism for managing conversational state, enabling the creation of more intelligent, context-aware, and personalized bot experiences.
