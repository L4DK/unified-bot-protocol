# Tasklist

## 🔍 1. Arkitektonisk Analyse & "Missing Links"

### A. Data Persistens (Kritisk)

* **Status:** Lige nu kører store dele af systemet "In-Memory".
  * `TaskManager` bruger interne dictionaries (`self.tasks`).
  * `RateLimiter` bruger in-memory lister.
  * `ActiveAdapterManager` gemmer instanser i hukommelsen.
* **Problemet:** Hvis serveren genstarter, mister du **alle** tasks, **alle** rate-limit data, audit logs (hvis de ikke flushes hurtigt nok) og flow-tilstande.
* **Mangler:**
  * [ ] **Database:** Der mangler en PostgreSQL eller MongoDB integration til at gemme brugere, bots, tasks og historik.
  * [ ] **Redis:** Til distributed rate-limiting og pub/sub mellem services (hvis du vil skalere ud over én server).
  * [ ] **Identity Mapping:** For at "alt kan snakke med alt", skal vi vide, at "Discord User 123" er den samme person som "Slack User ABC". Denne mapping mangler.

#### B. gRPC vs. WebSocket

* **Dokumentation:** `DOCS/008...` nævner gRPC og WebSocket side om side.
* **Kode:** Jeg ser **ingen** gRPC implementation i `DEV`. Kun FastAPI (REST) og WebSockets.
* **Dom:** Enten skal gRPC fjernes fra dokumentationen for at undgå forvirring, eller også skal `.proto` filer og en gRPC server implementeres (anbefales kun til meget høj performance internt mellem services).

#### C. Message Transformation (The "Translation" Layer)

* **Status:** `MessageRouter` kan route beskeder.
* **Problemet:** Hvis en besked kommer fra **WhatsApp** (som rå JSON) og sendes til  **Discord** , vil Discord adapteren sandsynligvis fejle, hvis den bare modtager WhatsApp-JSON'en.
* **Mangler:** En **Transformer / Normalizer** i hver adapter.
  * [ ] *Input:* Adapter skal konvertere platforms-specifik JSON -> **UBP Standard Message** (defineret i `DOCS/006`).
  * [ ] *Output:* Adapter skal konvertere **UBP Standard Message** -> Platforms-specifik JSON (f.eks. Discord Embeds).

#### D. Automation Engine Integration

* **Status:** `DEV/automation` indeholder `engine.py` og `flow_builder.py`.
* **Mangler:** Jeg ser ikke, hvor denne motor bliver  *kaldt* .
  * [ ] Når en besked kommer ind via `SecureC2Handler`, sendes den til `MessageRouter`. Men hvornår tjekker vi, om beskeden trigger et automatiseret flow?
  * [ ] Der mangler en "Hook" eller "Interceptor" i `MessageRouter`, der sender beskeder forbi `AutomationEngine` før de routes videre.

---

### 🛠️ 2. Adapter Analyse: Hvad mangler?

For at opnå målet om "Alt skal tale med alt", er her dommen over adapterne:

| **Adapter**         | **Status**  | **Mangler / Kritik**                                                                                                                                    |
| :------------------ | :---------- | :------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Discord**         | 🟡 Middel   | Mangler sandsynligvis håndtering af **Slash Commands** og **voice channels**. Implementerer den `send_message` med fuld understøttelse af embeds/files? |
| **Slack**           | 🟡 Middel   | Understøtter den "**Block Kit**" (knapper, inputs)? Det er essentielt for interaktive bots.                                                             |
| **Telegram**        | 🟢 God      | **Telegram API** er simpelt, men tjek om **Webhook** vs. **Polling** er håndteret korrekt (**UBP** bør foretrække **Webhook**).                         |
| **WhatsApp**        | 🔴 Kritisk  | Kræver ofte **Meta Graph API** verifikation og en offentlig **URL**. Er handshake implementeret?                                                        |
| **Microsoft Teams** | 🟡 Middel   | **Teams Graph API** er notorisk bøvlet. Kræver **Azure AD auth flow**, som jeg ikke har set fuldt implementeret.                                        |
| **Email**           | 🟢 God      | **SMTP**/**IMAP** ser fint ud, men parsing af **HTML** emails til ren tekst (til LLM'er) kan være tricky.                                               |
| **IoT (MQTT)**      | 🟢 God      | Ser fin ud, men mangler definition af "**Devices**". Hvordan ved vi, at en **MQTT** besked er "tekst"?                                                  |
| **Zabbix**          | 🟡 Speciel  | Dette er en "indgående" adapter (alarmer). Kan den modtage kommandoer tilbage? (F.eks. "**Acknowledge alert**").                                        |
| **Facebook**        | 🔴 Kritisk  | Opdelt i "**Website**" og "**Messenger**". "**Website**" lyder som scraping (skrøbeligt). Messenger kræver webhook verifikation.                        |

**Nye Adaptere der bør overvejes:**

1. [ ] **Twilio SMS:** For simpel 2-vejs SMS (lettere end WhatsApp).
2. [ ] **Generic REST Poller:** Til systemer der ikke har webhooks, men hvor vi skal hente data hvert X minut.
3. [ ] **OpenAI Realtime API (Audio):** Hvis du vil have tale-til-tale support i fremtiden.

---

### 📝 3. DevOps & Environment Analyse

* **Docker:** Jeg mangler en `Dockerfile` og `docker-compose.yml`. Uden disse er det svært at spinne hele orkesteret op med en database.
* **Tests:** Mappen `tests/` findes sporadisk i adaptere, men der mangler  **Integration Tests** . En test der sender en besked ind i API'et og bekræfter den kommer ud i "Console" adapteren.
* **Libs:**
  * Du bruger `aiohttp` mange steder. Det er godt.
  * Overvej `pydantic-settings` til `settings.py` for stærkere type-sikkerhed af `.env`.
  * Du mangler en database driver (f.eks. `asyncpg` for PostgreSQL eller `motor` for MongoDB).

---

### ✅ Detaljeret Tasklist (Roadmap)

Her er planen for at få systemet fra "Kodebase" til "Produktionsplatform".

#### Fase 1: Fundament & Persistens (Prio 1)

1. [ ] **Docker Setup:** Opret `docker-compose.yml` der starter:
    * UBP Orchestrator
    * PostgreSQL (Database)
    * Redis (Cache/Queue)
2. [ ] **Database Layer:**
    * Implementer `DEV/orchestrator/storage.py` med rigtig database logik (f.eks. **SQLAlchemy Async** eller **Tortoise** **ORM**).
    * Opret modeller for: `BotRegistration`, `UserIdentity`, `Task`, `AuditLog`.
3. [ ] **Refactor Managers:**
    * Opdater `TaskManager` til at gemme/hente tasks fra DB i stedet for memory.
    * Opdater `AuditLogger` til også at skrive til DB (eller en log-shipper).

#### Fase 2: Routing Intelligence (Prio 2)

1. [ ] **Standardized Message Model:**
    * Gennemgå `DEV/orchestrator/models.py`. Sørg for at `UnifiedMessage` klassen dækker alt: Text, Image, Audio, Buttons, Sender, Recipient.
2. [ ] **Adapter Transformers:**
    * Gå igennem hver adapter (`discord`, `slack`, etc.) og implementer:
      * `to_unified(platform_msg) -> UnifiedMessage`
      * `to_platform(unified_msg) -> dict`
3. [ ] **Identity Mapping Service:**
    * Lav en service der mapper: `discord_id:123` <-> `internal_uuid:abc` <-> `slack_id:xyz`. Dette er nøglen til cross-platform chat.

#### Fase 3: Automation & AI Integration (Prio 3)

1. [ ] **Wiring Automation Engine:**
    * Forbind `AutomationEngine` til `MessageRouter`.
    * Logik: *Besked modtaget -> Tjek triggers i Engine -> Hvis match: Kør flow -> Ellers: Route standard.*
2. [ ] **LLM Loop:**
    * Implementer en "Co-pilot" integration. Hvis en besked tagger botten (f.eks. "@bot"), skal den routes til `integrations/llm/openai_integration.py` og svaret routes tilbage.

#### Fase 4: Dokumentation & Cleanup (Prio 4)

1. [ ] **Opdater README:** Lav en "Quickstart" guide til udviklere.
1. [ ] **Cleanup:** Slet den gamle `main.py` og ubrugte filer.
1. [ ] **Consistency Check:** Sørg for at gRPC referencer i DOCS markeres som "Planned" eller fjernes, hvis det ikke implementeres nu.

#### Fase 5: Nye Adaptere (Nice to have)

1. [ ] **Twilio SMS Adapter.**
1. [ ] **Generic Webhook Ingestor** (En adapter der bare tager imod JSON og mapper det via en config template).
