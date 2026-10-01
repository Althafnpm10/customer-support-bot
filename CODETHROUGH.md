# CU Electronics Support Bot: Deep End-to-End CodeThrough

This is a complete walkthrough of how the project works from startup to final response.
The focus is practical traceability: every major step includes a direct file+line reference so you can jump into code while reading.

---

## 0) How to Read This Document

This guide is intentionally detailed. Read it in this order:

1. Sections 1-4 explain runtime architecture and request boundaries (browser, proxy, API).
2. Sections 5-9 explain state machine behavior, routing, and each agent.
3. Section 10 explains how final human-readable text is generated.
4. Section 11 gives full turn-by-turn scenario traces.
5. Section 12 is a quick click-to-code navigation map.

If you are presenting this to someone else, keep code open side-by-side and jump through the links as you narrate.

---

## 1) Runtime Architecture and True Entry Points

The same business logic is used in both run modes. What changes is how `/chat` is reached over HTTP.

### 1.1 Direct FastAPI mode

In direct mode, one uvicorn process serves both UI and API.
The app object is created at [app/main.py:45](/home/azureuser/customsupport/app/main.py:45).

From there:

1. API router is attached at [app/main.py:46](/home/azureuser/customsupport/app/main.py:46).
2. Static files are mounted at [app/main.py:57](/home/azureuser/customsupport/app/main.py:57).
3. Storefront HTML is served by `/` at [app/main.py:72](/home/azureuser/customsupport/app/main.py:72).

### 1.2 Docker two-container mode

In Docker mode, frontend and backend are separate services.

1. Backend service is defined at [docker-compose.yml:2](/home/azureuser/customsupport/docker-compose.yml:2).
2. Frontend service is defined at [docker-compose.yml:12](/home/azureuser/customsupport/docker-compose.yml:12).
3. Backend process command is uvicorn at [Dockerfile.backend:16](/home/azureuser/customsupport/Dockerfile.backend:16).
4. Frontend container uses nginx from [Dockerfile.frontend:1](/home/azureuser/customsupport/Dockerfile.frontend:1).

In this mode, browser requests do not hit backend directly for `/chat`.
Nginx proxies `/chat` to backend using [docker/nginx/default.conf:17](/home/azureuser/customsupport/docker/nginx/default.conf:17) and [docker/nginx/default.conf:18](/home/azureuser/customsupport/docker/nginx/default.conf:18).

---

## 2) Startup Wiring: What Exists Before the First User Message

Startup initialization is in [app/main.py:23](/home/azureuser/customsupport/app/main.py:23).
This section is important because almost every request depends on these shared objects.

### 2.1 Settings loading and logging

1. Settings are loaded by `get_settings()` at [app/main.py:23](/home/azureuser/customsupport/app/main.py:23), implemented in [app/config.py:31](/home/azureuser/customsupport/app/config.py:31).
2. Logging is configured once in [app/main.py:24](/home/azureuser/customsupport/app/main.py:24), implemented by [app/logging_config.py:114](/home/azureuser/customsupport/app/logging_config.py:114).
3. Sensitive keys are redacted by logging formatter rules at [app/logging_config.py:11](/home/azureuser/customsupport/app/logging_config.py:11), [app/logging_config.py:59](/home/azureuser/customsupport/app/logging_config.py:59), and [app/logging_config.py:72](/home/azureuser/customsupport/app/logging_config.py:72).

### 2.2 Core shared services

These are all process-level singletons in current design:

1. conversation store at [app/main.py:26](/home/azureuser/customsupport/app/main.py:26)
2. knowledge base service at [app/main.py:27](/home/azureuser/customsupport/app/main.py:27)
3. mock tool registry at [app/main.py:28](/home/azureuser/customsupport/app/main.py:28)
4. compiled LangGraph workflow at [app/main.py:29](/home/azureuser/customsupport/app/main.py:29)

### 2.3 Response generator selection logic

This is selected once at boot:

1. Azure generator path begins at [app/main.py:30](/home/azureuser/customsupport/app/main.py:30).
2. Noop fallback is selected at [app/main.py:43](/home/azureuser/customsupport/app/main.py:43).

Relevant settings fields are defined in [app/config.py:16](/home/azureuser/customsupport/app/config.py:16) and populated in [app/config.py:35](/home/azureuser/customsupport/app/config.py:35).

---

## 3) Frontend Flow: From Page Load to Calling `/chat`

### 3.1 HTML entry and chat controls

Main page is [app/frontend/index.html:1](/home/azureuser/customsupport/app/frontend/index.html:1).
Chat-related DOM elements include:

1. chat toggle button: [app/frontend/index.html:95](/home/azureuser/customsupport/app/frontend/index.html:95)
2. chat panel: [app/frontend/index.html:99](/home/azureuser/customsupport/app/frontend/index.html:99)
3. messages container: [app/frontend/index.html:107](/home/azureuser/customsupport/app/frontend/index.html:107)
4. send form and input: [app/frontend/index.html:113](/home/azureuser/customsupport/app/frontend/index.html:113), [app/frontend/index.html:114](/home/azureuser/customsupport/app/frontend/index.html:114)
5. reset session button: [app/frontend/index.html:117](/home/azureuser/customsupport/app/frontend/index.html:117)

### 3.2 Script order and why it matters

Scripts load in this order:

1. [app/frontend/index.html:120](/home/azureuser/customsupport/app/frontend/index.html:120) (`chatbot-plugin.js`)
2. [app/frontend/index.html:121](/home/azureuser/customsupport/app/frontend/index.html:121) (`app.js`)

`app.js` constructs `window.FrontendBackendChatPlugin` at [app/frontend/static/js/app.js:12](/home/azureuser/customsupport/app/frontend/static/js/app.js:12), so plugin must exist before `app.js` runs.

### 3.3 Message send path

User action path is:

1. submit handler in [app/frontend/static/js/app.js:60](/home/azureuser/customsupport/app/frontend/static/js/app.js:60)
2. `sendToBackend` wrapper at [app/frontend/static/js/app.js:30](/home/azureuser/customsupport/app/frontend/static/js/app.js:30)
3. plugin `sendMessage` at [app/frontend/static/js/chatbot-plugin.js:50](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:50)
4. network call `fetch(.../chat)` at [app/frontend/static/js/chatbot-plugin.js:59](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:59)
5. UI render of backend response at [app/frontend/static/js/app.js:40](/home/azureuser/customsupport/app/frontend/static/js/app.js:40)

### 3.4 Session reset path

There are two reset triggers:

1. automatic reset on full page load at [app/frontend/static/js/app.js:20](/home/azureuser/customsupport/app/frontend/static/js/app.js:20)
2. manual reset button at [app/frontend/static/js/app.js:70](/home/azureuser/customsupport/app/frontend/static/js/app.js:70)

Both call `resetConversation()` in [app/frontend/static/js/chatbot-plugin.js:34](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:34), which clears local conversation ID and calls backend delete endpoint when an old conversation exists.

---

## 4) Who Provides `user_id` and `conversation_id`

This is one of the most important flow questions.

### 4.1 `user_id` provider

`user_id` is created and persisted on frontend (browser localStorage), not generated by backend.

Code path:

1. constructor creates key names and loads IDs at [app/frontend/static/js/chatbot-plugin.js:14](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:14) to [app/frontend/static/js/chatbot-plugin.js:17](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:17)
2. `getOrCreateUserId()` at [app/frontend/static/js/chatbot-plugin.js:20](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:20)
3. random ID generator at [app/frontend/static/js/chatbot-plugin.js:2](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:2)
4. payload attach as `user_id` at [app/frontend/static/js/chatbot-plugin.js:53](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:53)

### 4.2 `conversation_id` provider

`conversation_id` is created by backend when missing.

Code path:

1. route handler checks payload and creates ID when absent at [app/api/routes.py:54](/home/azureuser/customsupport/app/api/routes.py:54)
2. ID format function `_new_conversation_id` at [app/api/routes.py:190](/home/azureuser/customsupport/app/api/routes.py:190)
3. response includes `conversation_id` at [app/api/routes.py:149](/home/azureuser/customsupport/app/api/routes.py:149)
4. frontend persists it at [app/frontend/static/js/chatbot-plugin.js:83](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:83)
5. later requests include it at [app/frontend/static/js/chatbot-plugin.js:55](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:55)

So the ownership split is:

1. frontend owns `user_id`
2. backend owns generation of `conversation_id`
3. frontend stores and reuses the backend-generated conversation ID

---

## 5) `/chat` Route: Full Request Lifecycle

Route starts at [app/api/routes.py:33](/home/azureuser/customsupport/app/api/routes.py:33).
Request model is [app/api/schemas.py:10](/home/azureuser/customsupport/app/api/schemas.py:10).

### 5.1 Input normalization and validation

At route start, handler normalizes input values:

1. `payload_user_id` extraction and trim at [app/api/routes.py:36](/home/azureuser/customsupport/app/api/routes.py:36)
2. `payload_conversation_id` extraction and trim at [app/api/routes.py:37](/home/azureuser/customsupport/app/api/routes.py:37)
3. `message` extraction and trim at [app/api/routes.py:39](/home/azureuser/customsupport/app/api/routes.py:39)

If message is empty, API returns an error at [app/api/routes.py:52](/home/azureuser/customsupport/app/api/routes.py:52).

### 5.2 Conversation state retrieval

1. conversation ID is created or reused at [app/api/routes.py:54](/home/azureuser/customsupport/app/api/routes.py:54)
2. state load/create call is [app/api/routes.py:55](/home/azureuser/customsupport/app/api/routes.py:55)
3. store method is [app/storage/conversation_store.py:42](/home/azureuser/customsupport/app/storage/conversation_store.py:42)
4. default state shape is [app/storage/conversation_store.py:9](/home/azureuser/customsupport/app/storage/conversation_store.py:9)

### 5.3 State mutation before graph execution

Handler updates conversational state before invoking graph:

1. sets `latest_user_message` [app/api/routes.py:74](/home/azureuser/customsupport/app/api/routes.py:74)
2. appends user message into `messages` list [app/api/routes.py:75](/home/azureuser/customsupport/app/api/routes.py:75)

### 5.4 Graph invocation and post-processing

1. invokes workflow with deep-copied state [app/api/routes.py:78](/home/azureuser/customsupport/app/api/routes.py:78)
2. ensures `shared_memory` exists after workflow [app/api/routes.py:90](/home/azureuser/customsupport/app/api/routes.py:90)
3. derives `route` and `intent` [app/api/routes.py:91](/home/azureuser/customsupport/app/api/routes.py:91)
4. generates final response text [app/api/routes.py:94](/home/azureuser/customsupport/app/api/routes.py:94)
5. appends assistant message to history [app/api/routes.py:129](/home/azureuser/customsupport/app/api/routes.py:129)
6. saves final state [app/api/routes.py:130](/home/azureuser/customsupport/app/api/routes.py:130)
7. returns `ChatResponse` object [app/api/routes.py:148](/home/azureuser/customsupport/app/api/routes.py:148)

---

## 6) Conversation Store and State Model Details

Store implementation is [app/storage/conversation_store.py:27](/home/azureuser/customsupport/app/storage/conversation_store.py:27).
State type is [app/graph/state.py:9](/home/azureuser/customsupport/app/graph/state.py:9).

### 6.1 State fields and purpose

The state fields are not random. Each one exists for a specific stage:

1. `conversation_id`: map key in store and response correlation key.
2. `user_id`: user identity from frontend.
3. `messages`: complete conversation transcript for current session.
4. `latest_user_message`: current-turn input used by router and agents.
5. `greeted`: one-time behavior flag for first interaction handling.
6. `route`: selected lane (`customer_support`, `tech_support`, `sales_support`, `fallback`).
7. `intent`: lane-specific sub-intent (e.g., `router_disconnect_issue`, `warranty_claim`, `order_placement`).
8. `confidence`: routing confidence score.
9. `response`: final assistant text generated after workflow stage.
10. `tool_calls`: mock tool invocation outputs.
11. `metadata`: dynamic per-agent state including `llm_hints` and follow-up flags.
12. `extracted_entities`: customer support extraction output (model/serial/purchase date etc.).
13. `shared_memory`: persistent per-lane memory across turns.

### 6.2 Store behavior characteristics

Important implementation details:

1. in-memory only, not durable across process restarts [app/storage/conversation_store.py:29](/home/azureuser/customsupport/app/storage/conversation_store.py:29)
2. lock-protected operations for thread safety [app/storage/conversation_store.py:35](/home/azureuser/customsupport/app/storage/conversation_store.py:35)
3. deep-copy on read and write to avoid accidental mutation leaks [app/storage/conversation_store.py:40](/home/azureuser/customsupport/app/storage/conversation_store.py:40), [app/storage/conversation_store.py:56](/home/azureuser/customsupport/app/storage/conversation_store.py:56)

---

## 7) LangGraph Workflow: Precise Node and Edge Behavior

Workflow is defined in [app/graph/workflow.py:18](/home/azureuser/customsupport/app/graph/workflow.py:18).

### 7.1 Nodes and responsibilities

1. `greeting` node at [app/graph/workflow.py:21](/home/azureuser/customsupport/app/graph/workflow.py:21)
   - implementation at [app/graph/nodes.py:26](/home/azureuser/customsupport/app/graph/nodes.py:26)
   - sets `greeted=True` once
2. `router` node at [app/graph/workflow.py:22](/home/azureuser/customsupport/app/graph/workflow.py:22)
   - implementation at [app/graph/nodes.py:33](/home/azureuser/customsupport/app/graph/nodes.py:33)
3. specialist/fallback nodes
   - customer [app/graph/workflow.py:23](/home/azureuser/customsupport/app/graph/workflow.py:23)
   - tech [app/graph/workflow.py:27](/home/azureuser/customsupport/app/graph/workflow.py:27)
   - sales [app/graph/workflow.py:31](/home/azureuser/customsupport/app/graph/workflow.py:31)
   - fallback [app/graph/workflow.py:35](/home/azureuser/customsupport/app/graph/workflow.py:35)

### 7.2 Edge graph

1. `START -> greeting` [app/graph/workflow.py:37](/home/azureuser/customsupport/app/graph/workflow.py:37)
2. `greeting -> router` [app/graph/workflow.py:38](/home/azureuser/customsupport/app/graph/workflow.py:38)
3. conditional router dispatch [app/graph/workflow.py:39](/home/azureuser/customsupport/app/graph/workflow.py:39)
4. all branches terminate to `END` [app/graph/workflow.py:49](/home/azureuser/customsupport/app/graph/workflow.py:49)

### 7.3 Dispatch selector

`route_from_state` at [app/graph/nodes.py:65](/home/azureuser/customsupport/app/graph/nodes.py:65) maps route value to node ID.
If no recognized route exists, it falls back to `fallback_node`.

---

## 8) Router Logic and Follow-up Protection

### 8.1 Primary route engine

Core route decision function is [app/graph/router.py:187](/home/azureuser/customsupport/app/graph/router.py:187).
It normalizes input and checks term sets for customer, tech, sales, greeting, and unsupported-item paths.

The most important behavior in order:

1. detect sales-style requests first [app/graph/router.py:189](/home/azureuser/customsupport/app/graph/router.py:189)
2. detect unsupported items [app/graph/router.py:195](/home/azureuser/customsupport/app/graph/router.py:195)
3. explicit lane phrases [app/graph/router.py:198](/home/azureuser/customsupport/app/graph/router.py:198)
4. score-based customer-vs-tech decision [app/graph/router.py:207](/home/azureuser/customsupport/app/graph/router.py:207)
5. greeting/unknown fallback [app/graph/router.py:216](/home/azureuser/customsupport/app/graph/router.py:216)

### 8.2 Intent classification

Intent helpers define sub-type behavior:

1. customer intent at [app/graph/router.py:233](/home/azureuser/customsupport/app/graph/router.py:233)
2. tech intent at [app/graph/router.py:250](/home/azureuser/customsupport/app/graph/router.py:250)
3. sales intent at [app/graph/router.py:273](/home/azureuser/customsupport/app/graph/router.py:273)

### 8.3 Why follow-up protection exists

Without follow-up logic, multi-turn conversations commonly misroute.
Example: after user sends only serial number, keyword-only routing might classify as unknown.

This project adds pre-routing follow-up checks in `router_node`:

1. customer follow-up guard [app/graph/nodes.py:126](/home/azureuser/customsupport/app/graph/nodes.py:126)
2. tech follow-up guard [app/graph/nodes.py:181](/home/azureuser/customsupport/app/graph/nodes.py:181)
3. sales follow-up guard [app/graph/nodes.py:188](/home/azureuser/customsupport/app/graph/nodes.py:188)

These checks run before generic `decide_route(...)` call [app/graph/nodes.py:61](/home/azureuser/customsupport/app/graph/nodes.py:61).

### 8.4 Mixed-support path

Mixed customer+tech detection helper: [app/graph/router.py:341](/home/azureuser/customsupport/app/graph/router.py:341).
When detected inside customer node, tech handler is called and both hint payloads are merged [app/graph/nodes.py:85](/home/azureuser/customsupport/app/graph/nodes.py:85), [app/graph/nodes.py:103](/home/azureuser/customsupport/app/graph/nodes.py:103).

---

## 9) Agent-by-Agent Internal Behavior

### 9.1 Customer support agent internals

Entry function: [app/agents/customer_support.py:31](/home/azureuser/customsupport/app/agents/customer_support.py:31).

The handler does these stages:

1. parse message and current intent [app/agents/customer_support.py:32](/home/azureuser/customsupport/app/agents/customer_support.py:32)
2. extract entities [app/agents/customer_support.py:34](/home/azureuser/customsupport/app/agents/customer_support.py:34)
3. load and mutate shared memory [app/agents/customer_support.py:37](/home/azureuser/customsupport/app/agents/customer_support.py:37)
4. set structured `llm_hints` [app/agents/customer_support.py:40](/home/azureuser/customsupport/app/agents/customer_support.py:40)

#### 9.1.1 Entity extraction details

Extraction method is [app/agents/customer_support.py:330](/home/azureuser/customsupport/app/agents/customer_support.py:330).
It supports:

1. product type detection
2. labeled model/serial fields
3. comma separated and space separated compact formats
4. ISO date parsing and US date parsing fallback
5. issue description extraction for service requests

#### 9.1.2 Warranty behavior details

Warranty branch starts around [app/agents/customer_support.py:100](/home/azureuser/customsupport/app/agents/customer_support.py:100).
Key logic:

1. required fields by intent from [app/agents/customer_support.py:11](/home/azureuser/customsupport/app/agents/customer_support.py:11)
2. serial validity check [app/agents/customer_support.py:105](/home/azureuser/customsupport/app/agents/customer_support.py:105)
3. missing field request generation via `llm_hints` [app/agents/customer_support.py:116](/home/azureuser/customsupport/app/agents/customer_support.py:116)
4. warranty age calculation in [app/agents/customer_support.py:482](/home/azureuser/customsupport/app/agents/customer_support.py:482)
5. active request memory update in [app/agents/customer_support.py:287](/home/azureuser/customsupport/app/agents/customer_support.py:287)

#### 9.1.3 Memory recall/cancel details

1. memory query detector [app/agents/customer_support.py:218](/home/azureuser/customsupport/app/agents/customer_support.py:218)
2. cancellation detector [app/agents/customer_support.py:273](/home/azureuser/customsupport/app/agents/customer_support.py:273)
3. cancel operation [app/agents/customer_support.py:299](/home/azureuser/customsupport/app/agents/customer_support.py:299)

#### 9.1.4 Tool invocation details

Service request tool path:

1. safe invoke wrapper [app/agents/customer_support.py:314](/home/azureuser/customsupport/app/agents/customer_support.py:314)
2. registry call [app/services/tool_registry.py:27](/home/azureuser/customsupport/app/services/tool_registry.py:27)
3. mock service tool implementation [app/services/mock_actions.py:9](/home/azureuser/customsupport/app/services/mock_actions.py:9)

### 9.2 Technical support agent internals

Entry function: [app/agents/tech_support.py:36](/home/azureuser/customsupport/app/agents/tech_support.py:36).

The agent behavior revolves around `llm_hints.status` variants:

1. `kb_match` when knowledge section found [app/agents/tech_support.py:137](/home/azureuser/customsupport/app/agents/tech_support.py:137)
2. `kb_miss` when no adequate match [app/agents/tech_support.py:114](/home/azureuser/customsupport/app/agents/tech_support.py:114)
3. `follow_up` when user reports attempted steps [app/agents/tech_support.py:72](/home/azureuser/customsupport/app/agents/tech_support.py:72)
4. `troubleshooting_exhausted` when all standard steps tried [app/agents/tech_support.py:58](/home/azureuser/customsupport/app/agents/tech_support.py:58)

Knowledge base implementation:

1. service class [app/services/knowledge_base.py:67](/home/azureuser/customsupport/app/services/knowledge_base.py:67)
2. chunk reload/parser [app/services/knowledge_base.py:74](/home/azureuser/customsupport/app/services/knowledge_base.py:74)
3. search scoring [app/services/knowledge_base.py:81](/home/azureuser/customsupport/app/services/knowledge_base.py:81)
4. source data file [data/wiki.txt:1](/home/azureuser/customsupport/data/wiki.txt:1)

### 9.3 Sales support agent internals

Entry function: [app/agents/sales_support.py:67](/home/azureuser/customsupport/app/agents/sales_support.py:67).

The sales lane supports recommendation, comparison, checkout, and cancellation in one stateful flow.

#### 9.3.1 Recommendation and selection

1. recommendation fallback branch [app/agents/sales_support.py:177](/home/azureuser/customsupport/app/agents/sales_support.py:177)
2. recommendation algorithm [app/services/product_catalog.py:185](/home/azureuser/customsupport/app/services/product_catalog.py:185)
3. product catalog definitions [app/services/product_catalog.py:23](/home/azureuser/customsupport/app/services/product_catalog.py:23)

#### 9.3.2 Order placement lifecycle

1. intent branch for order placement [app/agents/sales_support.py:144](/home/azureuser/customsupport/app/agents/sales_support.py:144)
2. if address missing, mark pending order [app/agents/sales_support.py:170](/home/azureuser/customsupport/app/agents/sales_support.py:170)
3. parse shipping address [app/agents/sales_support.py:366](/home/azureuser/customsupport/app/agents/sales_support.py:366)
4. place order via mock tool [app/agents/sales_support.py:290](/home/azureuser/customsupport/app/agents/sales_support.py:290), [app/services/mock_actions.py:49](/home/azureuser/customsupport/app/services/mock_actions.py:49)

#### 9.3.3 Cancellation lifecycle

1. cancellation intent branch [app/agents/sales_support.py:126](/home/azureuser/customsupport/app/agents/sales_support.py:126)
2. reference extraction fallback from memory [app/agents/sales_support.py:321](/home/azureuser/customsupport/app/agents/sales_support.py:321)
3. cancel mock tool [app/services/mock_actions.py:62](/home/azureuser/customsupport/app/services/mock_actions.py:62)
4. memory update to mark order cancelled [app/agents/sales_support.py:472](/home/azureuser/customsupport/app/agents/sales_support.py:472)

### 9.4 Fallback agent internals

Fallback handler: [app/agents/fallback.py:8](/home/azureuser/customsupport/app/agents/fallback.py:8).

It detects unsupported items via [app/services/product_scope.py:98](/home/azureuser/customsupport/app/services/product_scope.py:98), then sets `metadata.llm_hints` to drive response generation.

---

## 10) Response Generation and Final API Payload

After specialist node returns, route handler turns structured output into final text.

### 10.1 Generation call and failures

1. response generation call [app/api/routes.py:94](/home/azureuser/customsupport/app/api/routes.py:94)
2. exception path -> `llm_response_generation_failed` [app/api/routes.py:101](/home/azureuser/customsupport/app/api/routes.py:101)
3. empty response path -> `llm_response_generation_empty` [app/api/routes.py:114](/home/azureuser/customsupport/app/api/routes.py:114)

### 10.2 Azure response generator mechanics

Implementation class starts at [app/services/response_generator.py:38](/home/azureuser/customsupport/app/services/response_generator.py:38).

It performs:

1. context payload build [app/services/response_generator.py:53](/home/azureuser/customsupport/app/services/response_generator.py:53)
2. request message build [app/services/response_generator.py:60](/home/azureuser/customsupport/app/services/response_generator.py:60)
3. API selection logic (`/responses` vs chat completions) [app/services/response_generator.py:98](/home/azureuser/customsupport/app/services/response_generator.py:98)
4. response text extraction helpers [app/services/response_generator.py:154](/home/azureuser/customsupport/app/services/response_generator.py:154), [app/services/response_generator.py:175](/home/azureuser/customsupport/app/services/response_generator.py:175)

### 10.3 LLM prompt contract

System prompt is defined at [app/services/response_generator.py:234](/home/azureuser/customsupport/app/services/response_generator.py:234).
It explicitly instructs route-based speaker prefixes and behavior based on `llm_hints.status`.

### 10.4 Persist and return

After generating text:

1. API writes `result["response"]` [app/api/routes.py:128](/home/azureuser/customsupport/app/api/routes.py:128)
2. appends assistant message into transcript [app/api/routes.py:129](/home/azureuser/customsupport/app/api/routes.py:129)
3. saves state [app/api/routes.py:130](/home/azureuser/customsupport/app/api/routes.py:130)
4. returns typed `ChatResponse` [app/api/routes.py:148](/home/azureuser/customsupport/app/api/routes.py:148)

---

## 11) Full Scenario Traces (Turn-by-Turn)

### 11.1 Scenario A: First technical support message

Example user message: `My router keeps disconnecting`

Trace:

1. user types in [app/frontend/index.html:114](/home/azureuser/customsupport/app/frontend/index.html:114)
2. submit fires [app/frontend/static/js/app.js:60](/home/azureuser/customsupport/app/frontend/static/js/app.js:60)
3. plugin sends POST `/chat` [app/frontend/static/js/chatbot-plugin.js:59](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:59)
4. backend creates conversation ID [app/api/routes.py:54](/home/azureuser/customsupport/app/api/routes.py:54)
5. workflow runs [app/api/routes.py:78](/home/azureuser/customsupport/app/api/routes.py:78)
6. router chooses `tech_support` + `router_disconnect_issue` [app/graph/router.py:256](/home/azureuser/customsupport/app/graph/router.py:256)
7. tech agent fetches KB hints [app/agents/tech_support.py:112](/home/azureuser/customsupport/app/agents/tech_support.py:112)
8. final text generated and returned [app/api/routes.py:94](/home/azureuser/customsupport/app/api/routes.py:94), [app/api/routes.py:148](/home/azureuser/customsupport/app/api/routes.py:148)

### 11.2 Scenario B: Warranty claim with serial-only follow-up

Turn sequence:

1. user starts warranty claim
2. system asks for missing fields
3. user sends only serial value
4. route still stays in customer support due follow-up guard
5. user sends purchase date
6. warranty request becomes initialized or expired depending on date

Key lines responsible:

1. follow-up lock in router [app/graph/nodes.py:126](/home/azureuser/customsupport/app/graph/nodes.py:126)
2. serial-only check [app/graph/nodes.py:202](/home/azureuser/customsupport/app/graph/nodes.py:202)
3. entity extraction for serial-only values [app/agents/customer_support.py:366](/home/azureuser/customsupport/app/agents/customer_support.py:366)
4. warranty outcome [app/agents/customer_support.py:482](/home/azureuser/customsupport/app/agents/customer_support.py:482)

### 11.3 Scenario C: Product recommendation to order placement to cancellation

Turn sequence:

1. recommendation request enters sales lane
2. user selects product for order
3. agent requests shipping address if absent
4. user supplies address
5. `place_mock_order` tool called
6. user asks cancel order
7. `cancel_mock_order` tool called using known or extracted reference

Key lines responsible:

1. sales route selection [app/graph/router.py:293](/home/azureuser/customsupport/app/graph/router.py:293)
2. order placement branch [app/agents/sales_support.py:144](/home/azureuser/customsupport/app/agents/sales_support.py:144)
3. address parsing [app/agents/sales_support.py:366](/home/azureuser/customsupport/app/agents/sales_support.py:366)
4. place tool [app/services/mock_actions.py:45](/home/azureuser/customsupport/app/services/mock_actions.py:45)
5. cancellation branch [app/agents/sales_support.py:126](/home/azureuser/customsupport/app/agents/sales_support.py:126)
6. cancel tool [app/services/mock_actions.py:58](/home/azureuser/customsupport/app/services/mock_actions.py:58)

### 11.4 Scenario D: Mixed customer + technical message in one turn

Example: `I want to claim warranty for my camera and my router keeps disconnecting`

What happens:

1. router chooses customer-support-first behavior
2. customer node computes customer hints
3. customer node also calls tech handler
4. node merges both hint payloads
5. response generator can create a single combined response

Key code:

1. mixed detection helper [app/graph/router.py:341](/home/azureuser/customsupport/app/graph/router.py:341)
2. mixed handling in customer node [app/graph/nodes.py:82](/home/azureuser/customsupport/app/graph/nodes.py:82)
3. merge payload [app/graph/nodes.py:103](/home/azureuser/customsupport/app/graph/nodes.py:103)

---

## 12) Click-to-Code Quick Map (If You Click This, It Goes There)

### 12.1 Click chat icon

1. HTML element [app/frontend/index.html:95](/home/azureuser/customsupport/app/frontend/index.html:95)
2. click handler [app/frontend/static/js/app.js:49](/home/azureuser/customsupport/app/frontend/static/js/app.js:49)
3. panel visibility toggle [app/frontend/static/js/app.js:50](/home/azureuser/customsupport/app/frontend/static/js/app.js:50)

### 12.2 Click send

1. form submit [app/frontend/static/js/app.js:60](/home/azureuser/customsupport/app/frontend/static/js/app.js:60)
2. `sendToBackend` [app/frontend/static/js/app.js:30](/home/azureuser/customsupport/app/frontend/static/js/app.js:30)
3. plugin payload build [app/frontend/static/js/chatbot-plugin.js:51](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:51)
4. POST `/chat` [app/frontend/static/js/chatbot-plugin.js:59](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:59)
5. backend chat route [app/api/routes.py:33](/home/azureuser/customsupport/app/api/routes.py:33)
6. workflow invoke [app/api/routes.py:78](/home/azureuser/customsupport/app/api/routes.py:78)
7. node dispatch [app/graph/workflow.py:39](/home/azureuser/customsupport/app/graph/workflow.py:39)
8. response generation [app/api/routes.py:94](/home/azureuser/customsupport/app/api/routes.py:94)
9. state save and return [app/api/routes.py:130](/home/azureuser/customsupport/app/api/routes.py:130), [app/api/routes.py:148](/home/azureuser/customsupport/app/api/routes.py:148)
10. UI append response [app/frontend/static/js/app.js:40](/home/azureuser/customsupport/app/frontend/static/js/app.js:40)

### 12.3 Click Start New Session

1. reset button [app/frontend/index.html:117](/home/azureuser/customsupport/app/frontend/index.html:117)
2. reset listener [app/frontend/static/js/app.js:70](/home/azureuser/customsupport/app/frontend/static/js/app.js:70)
3. plugin reset and backend delete call [app/frontend/static/js/chatbot-plugin.js:34](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:34), [app/frontend/static/js/chatbot-plugin.js:41](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:41)
4. delete endpoint [app/api/routes.py:160](/home/azureuser/customsupport/app/api/routes.py:160)

---

## 13) Tests You Can Use as Executable Documentation

These tests are useful when validating that the walkthrough still matches behavior.

1. new conversation flow [tests/test_chat_api.py:37](/home/azureuser/customsupport/tests/test_chat_api.py:37)
2. reuse same conversation id [tests/test_chat_api.py:50](/home/azureuser/customsupport/tests/test_chat_api.py:50)
3. independent sessions per user [tests/test_chat_api.py:72](/home/azureuser/customsupport/tests/test_chat_api.py:72)
4. order placement flow [tests/test_chat_api.py:305](/home/azureuser/customsupport/tests/test_chat_api.py:305)
5. order cancellation flow [tests/test_chat_api.py:336](/home/azureuser/customsupport/tests/test_chat_api.py:336)
6. mixed support handling [tests/test_chat_api.py:956](/home/azureuser/customsupport/tests/test_chat_api.py:956)
7. router decision checks [tests/test_router.py:7](/home/azureuser/customsupport/tests/test_router.py:7)

---

## 14) Final Mental Model

The entire system loop can be summarized as a repeatable cycle:

1. frontend sends message with identity/session context
2. backend loads and updates state
3. state machine routes to correct lane with follow-up awareness
4. specialist agent writes structured hints and memory/tool outputs
5. response generator converts structured context into user-facing text
6. backend persists updated state and returns API payload
7. frontend renders text and stores conversation id for next turn

When debugging, always ask where in this loop the mismatch appears:

1. request construction issue
2. route/intent issue
3. specialist lane issue
4. response generation issue
5. state persistence issue

That ordering prevents random guessing and keeps debugging deterministic.

---

## 15) Mentor Presentation Script (Project Starts Here -> Click -> Function -> Next File)

Use this section when you explain live to your mentor. This is written as a direct narration flow.

### 15.1 Opening line you can use

"This project is a support chatbot for CU Electronics. The frontend captures user chat messages, sends them to `/chat`, the backend runs a LangGraph state machine, one specialist agent prepares structured output, and then the response generator builds the final user-facing reply."

### 15.2 Start of project execution (backend startup)

Say:

"The backend starts from `app/main.py`. At startup it builds all shared services first, then mounts routes."

Then show:

1. `app` creation in [app/main.py:45](/home/azureuser/customsupport/app/main.py:45)
2. conversation store created in [app/main.py:26](/home/azureuser/customsupport/app/main.py:26)
3. knowledge base service created in [app/main.py:27](/home/azureuser/customsupport/app/main.py:27)
4. tools registry created in [app/main.py:28](/home/azureuser/customsupport/app/main.py:28)
5. workflow compiled in [app/main.py:29](/home/azureuser/customsupport/app/main.py:29)
6. API router mounted in [app/main.py:46](/home/azureuser/customsupport/app/main.py:46)

Tell your mentor:

"This is the base wiring. Without this wiring, `/chat` cannot run because it needs store + workflow + response generator."

### 15.3 Where frontend starts and what user clicks first

Say:

"The user sees the storefront from `index.html`. The chat button and chat form are in this file."

Then show:

1. page root in [app/frontend/index.html:1](/home/azureuser/customsupport/app/frontend/index.html:1)
2. chat toggle button in [app/frontend/index.html:95](/home/azureuser/customsupport/app/frontend/index.html:95)
3. chat form in [app/frontend/index.html:113](/home/azureuser/customsupport/app/frontend/index.html:113)
4. input box in [app/frontend/index.html:114](/home/azureuser/customsupport/app/frontend/index.html:114)

Say:

"If user clicks chat icon, `app.js` toggles panel visibility. If user types and presses send, submit handler runs."

Then show:

1. chat toggle handler in [app/frontend/static/js/app.js:49](/home/azureuser/customsupport/app/frontend/static/js/app.js:49)
2. submit handler in [app/frontend/static/js/app.js:60](/home/azureuser/customsupport/app/frontend/static/js/app.js:60)

### 15.4 Explain user ID and conversation ID in mentor-friendly way

Say:

"`user_id` is generated in browser localStorage by plugin. `conversation_id` is generated by backend on first chat request and then reused."

Then show `user_id` source:

1. plugin constructor in [app/frontend/static/js/chatbot-plugin.js:10](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:10)
2. `getOrCreateUserId()` in [app/frontend/static/js/chatbot-plugin.js:20](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:20)
3. payload attach `user_id` in [app/frontend/static/js/chatbot-plugin.js:53](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:53)

Then show `conversation_id` source:

1. backend generates ID when missing in [app/api/routes.py:54](/home/azureuser/customsupport/app/api/routes.py:54)
2. ID generator function in [app/api/routes.py:190](/home/azureuser/customsupport/app/api/routes.py:190)
3. frontend stores returned ID in [app/frontend/static/js/chatbot-plugin.js:81](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:81)
4. frontend reuses it in [app/frontend/static/js/chatbot-plugin.js:55](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:55)

### 15.5 Exact click-to-backend function flow (what to say step-by-step)

Say this exactly in sequence:

1. "User clicks Send."
2. "Browser runs submit handler in `app.js`."
3. "Submit handler calls plugin `sendMessage`."
4. "Plugin sends POST request to `/chat`."
5. "Backend `/chat` route receives payload."
6. "Backend loads or creates conversation state."
7. "Backend writes latest user message into state."
8. "Backend invokes workflow state machine."
9. "Router node decides which specialist lane to use."
10. "Selected agent prepares metadata, memory, and tool outputs."
11. "Response generator converts structured output to final sentence."
12. "Backend saves updated state and returns JSON."
13. "Frontend renders assistant response in chat window."

Show lines while narrating:

1. submit handler [app/frontend/static/js/app.js:60](/home/azureuser/customsupport/app/frontend/static/js/app.js:60)
2. plugin send [app/frontend/static/js/chatbot-plugin.js:50](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:50)
3. POST `/chat` [app/frontend/static/js/chatbot-plugin.js:59](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:59)
4. backend route entry [app/api/routes.py:33](/home/azureuser/customsupport/app/api/routes.py:33)
5. state load/create [app/api/routes.py:55](/home/azureuser/customsupport/app/api/routes.py:55)
6. append user message [app/api/routes.py:75](/home/azureuser/customsupport/app/api/routes.py:75)
7. workflow invoke [app/api/routes.py:78](/home/azureuser/customsupport/app/api/routes.py:78)
8. graph definition [app/graph/workflow.py:18](/home/azureuser/customsupport/app/graph/workflow.py:18)
9. router node [app/graph/nodes.py:33](/home/azureuser/customsupport/app/graph/nodes.py:33)
10. route decision [app/graph/router.py:187](/home/azureuser/customsupport/app/graph/router.py:187)
11. response generation call [app/api/routes.py:94](/home/azureuser/customsupport/app/api/routes.py:94)
12. save + return [app/api/routes.py:130](/home/azureuser/customsupport/app/api/routes.py:130), [app/api/routes.py:148](/home/azureuser/customsupport/app/api/routes.py:148)
13. frontend render [app/frontend/static/js/app.js:40](/home/azureuser/customsupport/app/frontend/static/js/app.js:40)

### 15.6 How to explain state machine in simple mentor language

Say:

"Inside the state machine, flow is fixed: `START -> greeting -> router -> one specialist -> END`."

Then show:

1. start and first edge [app/graph/workflow.py:37](/home/azureuser/customsupport/app/graph/workflow.py:37)
2. router branch map [app/graph/workflow.py:39](/home/azureuser/customsupport/app/graph/workflow.py:39)
3. end edges [app/graph/workflow.py:49](/home/azureuser/customsupport/app/graph/workflow.py:49)

Then explain specialist lanes:

1. customer lane entry [app/graph/nodes.py:78](/home/azureuser/customsupport/app/graph/nodes.py:78), handler [app/agents/customer_support.py:31](/home/azureuser/customsupport/app/agents/customer_support.py:31)
2. tech lane entry [app/graph/nodes.py:114](/home/azureuser/customsupport/app/graph/nodes.py:114), handler [app/agents/tech_support.py:36](/home/azureuser/customsupport/app/agents/tech_support.py:36)
3. sales lane entry [app/graph/nodes.py:118](/home/azureuser/customsupport/app/graph/nodes.py:118), handler [app/agents/sales_support.py:67](/home/azureuser/customsupport/app/agents/sales_support.py:67)
4. fallback lane entry [app/graph/nodes.py:122](/home/azureuser/customsupport/app/graph/nodes.py:122), handler [app/agents/fallback.py:8](/home/azureuser/customsupport/app/agents/fallback.py:8)

### 15.7 What to say for each lane in one clear paragraph

Customer lane explanation:

"Customer lane handles warranty, replacement, return, and service request style input. It extracts entities like model, serial number, and purchase date, checks missing fields, updates shared memory for follow-ups, and can invoke mock service tools when needed."

Reference lines:

1. entity extraction [app/agents/customer_support.py:330](/home/azureuser/customsupport/app/agents/customer_support.py:330)
2. required fields logic [app/agents/customer_support.py:100](/home/azureuser/customsupport/app/agents/customer_support.py:100)
3. memory update [app/agents/customer_support.py:211](/home/azureuser/customsupport/app/agents/customer_support.py:211)
4. tool invoke wrapper [app/agents/customer_support.py:314](/home/azureuser/customsupport/app/agents/customer_support.py:314)

Tech lane explanation:

"Tech lane tries to find troubleshooting guidance from local wiki content. It keeps section context across turns, checks if user already tried steps, and escalates toward replacement suggestions when issue is not resolvable."

Reference lines:

1. tech handler start [app/agents/tech_support.py:36](/home/azureuser/customsupport/app/agents/tech_support.py:36)
2. KB search [app/agents/tech_support.py:112](/home/azureuser/customsupport/app/agents/tech_support.py:112)
3. follow-up attempt logic [app/agents/tech_support.py:155](/home/azureuser/customsupport/app/agents/tech_support.py:155)
4. KB file [data/wiki.txt:1](/home/azureuser/customsupport/data/wiki.txt:1)

Sales lane explanation:

"Sales lane handles recommendation, product comparison, order placement, shipping address capture, and cancellation. It maintains order memory so later cancellation can use previous order context."

Reference lines:

1. sales handler start [app/agents/sales_support.py:67](/home/azureuser/customsupport/app/agents/sales_support.py:67)
2. order branch [app/agents/sales_support.py:144](/home/azureuser/customsupport/app/agents/sales_support.py:144)
3. address parse [app/agents/sales_support.py:366](/home/azureuser/customsupport/app/agents/sales_support.py:366)
4. order/cancel tools [app/services/mock_actions.py:45](/home/azureuser/customsupport/app/services/mock_actions.py:45), [app/services/mock_actions.py:58](/home/azureuser/customsupport/app/services/mock_actions.py:58)

Fallback lane explanation:

"Fallback lane handles greetings, unknown requests, and unsupported products. It sets hint status so response generator can return correct triage message."

Reference lines:

1. fallback handler [app/agents/fallback.py:8](/home/azureuser/customsupport/app/agents/fallback.py:8)
2. unsupported detection [app/services/product_scope.py:98](/home/azureuser/customsupport/app/services/product_scope.py:98)

### 15.8 How to explain final response generation clearly

Say:

"Agents mostly produce structured hints, not final natural-language text. The API then calls response generator, which reads route + intent + llm_hints + memory + tool calls, then writes final human response."

Then show:

1. generation call in route [app/api/routes.py:94](/home/azureuser/customsupport/app/api/routes.py:94)
2. context payload builder [app/services/response_generator.py:198](/home/azureuser/customsupport/app/services/response_generator.py:198)
3. system prompt rules [app/services/response_generator.py:234](/home/azureuser/customsupport/app/services/response_generator.py:234)
4. final save and response return [app/api/routes.py:128](/home/azureuser/customsupport/app/api/routes.py:128), [app/api/routes.py:130](/home/azureuser/customsupport/app/api/routes.py:130), [app/api/routes.py:148](/home/azureuser/customsupport/app/api/routes.py:148)

### 15.9 90-second mentor demo script (ready to speak)

You can read this directly:

"Project starts in `app/main.py`, where store, tools, knowledge base, and state machine are wired.  
User opens storefront page from `index.html`, clicks chat, types message, and hits send.  
`app.js` submit handler calls plugin `sendMessage`, and plugin posts payload to `/chat` with browser `user_id` and optional `conversation_id`.  
Backend `/chat` route validates message, creates conversation ID if this is first turn, loads state, appends message, and invokes LangGraph workflow.  
Workflow runs greeting node, router node, then dispatches to customer, tech, sales, or fallback lane.  
Selected agent updates structured output: `llm_hints`, memory, and optional tool calls.  
Route then calls response generator to convert structured state into final user-facing text.  
Finally backend saves conversation state and returns JSON, and frontend appends that response to chat UI."
