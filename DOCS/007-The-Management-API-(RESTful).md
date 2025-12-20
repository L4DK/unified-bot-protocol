### 7\. The Management API (RESTful)

The Management API is the primary interface for all administrative, configuration, and high-level operational tasks. It is the control panel used by system operators, developers, and CI/CD pipelines to manage the lifecycle of bot definitions, monitor their instances, and query historical data.

#### Design Philosophy

The choice of a **RESTful architecture** for this API is deliberate and rooted in the principles of simplicity, accessibility, and industry standardization.[1, 2, 3] While the Command & Control API prioritizes raw performance with gRPC and WebSockets, the Management API prioritizes developer experience and broad compatibility.

  * **Statelessness and Scalability:** Each request to the REST API contains all the information necessary for the server to process it. The server does not store any client session state between requests.[1, 2] This makes the API inherently scalable, as any request can be handled by any server instance behind a load balancer.[3]
  * **Resource-Oriented Design:** The API is organized around resources (like `bots`, `tasks`, `instances`), which are manipulated using standard HTTP verbs (`GET`, `POST`, `PUT`, `DELETE`).[1, 4] This creates a predictable and intuitive structure that is easy for developers to understand and use. For example, `GET /v1/bots` clearly implies retrieving a list of bots.
  * **Universal Accessibility:** REST over HTTP/S is the most widely supported and understood API paradigm in the world. It can be consumed by virtually any programming language, command-line tool (like cURL), or low-code platform without requiring special libraries or complex setup, unlike gRPC.[2, 3]
  * **Separation of Concerns:** By handling administrative tasks via REST, we keep the high-performance real-time channels clean and dedicated solely to the low-latency exchange of commands and events.

#### Technical Implementation & Features

  * **Protocol:** All communication is over HTTPS to ensure transport-layer encryption.
  * **Data Format:** All request and response bodies use the `application/json` format.
  * **Authentication:** All requests must be authenticated. This is typically done by including a secret API key in an HTTP header, such as `Authorization: Bearer <your_admin_api_key>`.
  * **Versioning:** The API is versioned in the URL path (e.g., `/v1/`) to allow for future, non-breaking changes.
  * **Standard HTTP Status Codes:** The API uses standard HTTP status codes to indicate the outcome of a request, ensuring predictable client-side error handling (e.g., `200 OK`, `201 Created`, `400 Bad Request`, `404 Not Found`, `401 Unauthorized`).[5, 6]

-----

### Detailed Endpoint Specification

#### 1\. Register a New Bot Definition

This endpoint creates the logical *definition* of a bot within the Orchestrator. This is the template from which one or more bot *instances* will later connect. This operation generates the bot's unique ID and its initial, single-use credential for onboarding.

  * **Endpoint:** `POST /v1/bots`
  * **Description:** Creates a new bot configuration record.
  * **Request Body:**
    ```json
    {
      "name": "Customer Support Chatbot",
      "description": "Handles initial customer queries via Telegram.",
      "adapter_type": "telegram",
      "capabilities": ["message.send", "faq.query"]
    }
    ```
  * **Success Response (`201 Created`):**
    ```json
    {
      "bot_id": "bot-a1b2c3d4-e5f6-7890-1234-567890abcdef",
      "name": "Customer Support Chatbot",
      "created_at": "2025-09-15T22:30:00Z",
      "one_time_registration_token": "rego-xyz789-onetime-secret-token-456"
    }
    ```

**Code Examples:**

  * **cURL:**
    ```bash
    curl -X POST "https://api.orchestrator.example.com/v1/bots" \
         -H "Authorization: Bearer <admin_api_key>" \
         -H "Content-Type: application/json" \
         -d '{
               "name": "Customer Support Chatbot",
               "description": "Handles initial customer queries via Telegram.",
               "adapter_type": "telegram",
               "capabilities": ["message.send", "faq.query"]
             }'
    ```
  * **Python (`requests`):**
    ```python
    import requests

    api_url = "https://api.orchestrator.example.com/v1/bots"
    headers = {
        "Authorization": "Bearer <admin_api_key>",
        "Content-Type": "application/json"
    }
    payload = {
        "name": "Customer Support Chatbot",
        "description": "Handles initial customer queries via Telegram.",
        "adapter_type": "telegram",
        "capabilities": ["message.send", "faq.query"]
    }

    response = requests.post(api_url, headers=headers, json=payload)

    if response.status_code == 201:
        bot_data = response.json()
        print("Bot created successfully:")
        print(f"  Bot ID: {bot_data['bot_id']}")
        print(f"  Registration Token: {bot_data['one_time_registration_token']}")
    else:
        print(f"Error: {response.status_code} - {response.text}")
    ```

-----

#### 2\. Retrieve a List of Bot Definitions

This endpoint retrieves a paginated list of all bot definitions registered with the Orchestrator.

  * **Endpoint:** `GET /v1/bots`
  * **Description:** Fetches a list of all bot configurations. Supports filtering via query parameters (e.g., `?adapter_type=telegram`).
  * **Success Response (`200 OK`):**
    ```json
    {
      "bots":,
      "pagination_token": "next_page_cursor_xyz"
    }
    ```

**Code Examples:**

  * **cURL:**
    ```bash
    curl -X GET "https://api.orchestrator.example.com/v1/bots?adapter_type=telegram" \
         -H "Authorization: Bearer <admin_api_key>"
    ```
  * **Python (`requests`):**
    ```python
    import requests

    api_url = "https://api.orchestrator.example.com/v1/bots"
    headers = {"Authorization": "Bearer <admin_api_key>"}
    params = {"adapter_type": "telegram"}

    response = requests.get(api_url, headers=headers, params=params)
    print(response.json())
    ```

-----

#### 3\. Retrieve a Specific Bot Definition

This endpoint fetches the detailed configuration for a single bot definition.

  * **Endpoint:** `GET /v1/bots/{bot_id}`
  * **Description:** Retrieves the full details of a specific bot configuration.
  * **Success Response (`200 OK`):**
    ```json
    {
      "bot_id": "bot-a1b2c3d4-e5f6-7890-1234-567890abcdef",
      "name": "Customer Support Chatbot",
      "description": "Handles initial customer queries via Telegram.",
      "adapter_type": "telegram",
      "capabilities": ["message.send", "faq.query"],
      "created_at": "2025-09-15T22:30:00Z",
      "configuration": {
        "telegram_api_token_ref": "secret_manager_key_for_token"
      }
    }
    ```

**Code Examples:**

  * **cURL:**
    ```bash
    curl -X GET "https://api.orchestrator.example.com/v1/bots/bot-a1b2c3d4-e5f6-7890-1234-567890abcdef" \
         -H "Authorization: Bearer <admin_api_key>"
    ```

-----

#### 4\. Update a Bot Definition

This endpoint updates the mutable properties of a bot definition, such as its name, description, or custom configuration.

  * **Endpoint:** `PUT /v1/bots/{bot_id}`
  * **Description:** Updates an existing bot configuration. This operation is idempotent.
  * **Request Body:**
    ```json
    {
      "name": "Customer Support Chatbot V2",
      "description": "Handles tier 1 and tier 2 customer queries via Telegram and email.",
      "configuration": {
        "telegram_api_token_ref": "secret_manager_key_for_token",
        "escalation_email": "support@example.com"
      }
    }
    ```
  * **Success Response (`200 OK`):** Returns the full, updated bot definition object.

**Code Examples:**

  * **cURL:**
    ```bash
    curl -X PUT "https://api.orchestrator.example.com/v1/bots/bot-a1b2c3d4-e5f6-7890-1234-567890abcdef" \
         -H "Authorization: Bearer <admin_api_key>" \
         -H "Content-Type: application/json" \
         -d '{
               "name": "Customer Support Chatbot V2",
               "description": "Handles tier 1 and tier 2 customer queries via Telegram and email.",
               "configuration": {
                 "telegram_api_token_ref": "secret_manager_key_for_token",
                 "escalation_email": "support@example.com"
               }
             }'
    ```

-----

#### 5\. Deregister a Bot Definition

This endpoint permanently removes a bot definition and all associated credentials from the Orchestrator.

  * **Endpoint:** `DELETE /v1/bots/{bot_id}`
  * **Description:** Deletes a bot configuration. This action will invalidate all credentials for this bot, causing any currently connected instances to be disconnected. This action is irreversible.
  * **Success Response:** `204 No Content` with an empty body.

**Code Examples:**

  * **cURL:**
    ```bash
    curl -X DELETE "https://api.orchestrator.example.com/v1/bots/bot-a1b2c3d4-e5f6-7890-1234-567890abcdef" \
         -H "Authorization: Bearer <admin_api_key>"
    ```

-----

#### 6\. List Active Instances for a Bot

This endpoint provides a real-time view of all currently connected and healthy *instances* of a specific bot definition.

  * **Endpoint:** `GET /v1/bots/{bot_id}/instances`
  * **Description:** Retrieves a list of all active, connected instances for a given bot definition.
  * **Success Response (`200 OK`):**
    ```json
    {
      "instances":
    }
    ```

**Code Examples:**

  * **cURL:**
    ```bash
    curl -X GET "https://api.orchestrator.example.com/v1/bots/bot-a1b2c3d4-e5f6-7890-1234-567890abcdef/instances" \
         -H "Authorization: Bearer <admin_api_key>"
    ```

This Management API provides a robust, predictable, and easy-to-use interface for all administrative functions, forming a critical part of the overall UBP framework.
