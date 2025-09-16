### **Phase 2: Management APIs and Security**

This phase builds out the administrative capabilities and hardens the system's security.

	#### **Step 5: Implement the Bot Management API**

	*   **Goal:** Add the RESTful endpoints to the Orchestrator that allow an administrator to manage bot *definitions*.
	*   **Prompt:**
			> "Extend the **Bot Orchestrator server** code. Add the RESTful Management API for bot definitions as specified in Document #7. Implement the following endpoints using FastAPI:
			> *   `POST /v1/bots`: To register a new bot definition.
			> *   `GET /v1/bots`: To list all definitions.
			> *   `GET /v1/bots/{bot_id}`: To get a specific definition.
			> *   `DELETE /v1/bots/{bot_id}`: To remove a definition.
			> Use a simple in-memory dictionary as the database for these bot definitions."

			
	#### **Step 6: Implement Secure Onboarding**

	*   **Goal:** Connect the Management API to the C2 channel by implementing the secure, one-time-token onboarding flow from Document #12.
	*   **Prompt:**
			> "Now, integrate the secure onboarding process. Modify the **Bot Orchestrator** and **Bot Agent** code to implement the full registration flow:
			> 1.  In the Orchestrator, the `POST /v1/bots` endpoint must now generate and return a unique `one_time_registration_token`.
			> 2.  In the Orchestrator's C2 handshake handler, add logic to recognize this one-time token. Upon successful validation, it must generate a new long-lived API key, invalidate the one-time token, and send the new key back to the agent in the `HandshakeResponse`.
			> 3.  In the Bot Agent, add logic to securely store the received long-lived key (simulate by writing to a local file) and use it for all subsequent connections."

---