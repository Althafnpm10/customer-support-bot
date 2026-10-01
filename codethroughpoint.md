# CodeThroughPoint: Updated Runtime Flow (Including Recent Changes)

This file documents the current chatbot runtime after your latest architecture updates.
It follows the same 4 phases:

1. before user enters,
2. when user enters (session start),
3. when user sends a message and how intent/agent behavior is decided,
4. when user receives the final response.

## Recent Changes Integrated In This Version

The document now reflects these recent code changes:

1. LLM-based intent routing was introduced via [app/services/intent_classifier.py:71](/home/azureuser/customsupport/app/services/intent_classifier.py:71), wired in [app/main.py:45](/home/azureuser/customsupport/app/main.py:45) through [app/main.py:90](/home/azureuser/customsupport/app/main.py:90).
2. New per-domain hint classifiers were added and wired:
   - customer hints: [app/services/customer_hint_classifier.py:45](/home/azureuser/customsupport/app/services/customer_hint_classifier.py:45)
   - tech hints: [app/services/tech_hint_classifier.py:45](/home/azureuser/customsupport/app/services/tech_hint_classifier.py:45)
   - sales hints: [app/services/sales_hint_classifier.py:66](/home/azureuser/customsupport/app/services/sales_hint_classifier.py:66)
3. Graph node dependencies now inject all classifiers at [app/graph/nodes.py:23](/home/azureuser/customsupport/app/graph/nodes.py:23) through [app/graph/nodes.py:30](/home/azureuser/customsupport/app/graph/nodes.py:30).
4. Router behavior now delegates route+intent decision to classifier-backed `decide_route()` at [app/graph/nodes.py:39](/home/azureuser/customsupport/app/graph/nodes.py:39) and [app/graph/router.py:21](/home/azureuser/customsupport/app/graph/router.py:21).
5. Agents now produce structured `llm_hints` and mostly return empty response text (`"response": ""`) for the generator to convert into final user-facing text:
   - customer: [app/agents/customer_support.py:55](/home/azureuser/customsupport/app/agents/customer_support.py:55), [app/agents/customer_support.py:215](/home/azureuser/customsupport/app/agents/customer_support.py:215)
   - tech: [app/agents/tech_support.py:43](/home/azureuser/customsupport/app/agents/tech_support.py:43), [app/agents/tech_support.py:148](/home/azureuser/customsupport/app/agents/tech_support.py:148)
   - sales: [app/agents/sales_support.py:41](/home/azureuser/customsupport/app/agents/sales_support.py:41), [app/agents/sales_support.py:191](/home/azureuser/customsupport/app/agents/sales_support.py:191)
6. `/chat` now always calls response generation and returns 503 on generation failure/empty output at [app/api/routes.py:93](/home/azureuser/customsupport/app/api/routes.py:93) through [app/api/routes.py:125](/home/azureuser/customsupport/app/api/routes.py:125).

## 1) Before User Enters (Boot + Dependency Wiring)

### 1.1 Backend startup objects

At import/startup time in [app/main.py:39](/home/azureuser/customsupport/app/main.py:39):

1. settings load from `.env` via [app/config.py:31](/home/azureuser/customsupport/app/config.py:31).
2. structured logging is configured at [app/main.py:40](/home/azureuser/customsupport/app/main.py:40).
3. shared services are created:
   - conversation store [app/main.py:42](/home/azureuser/customsupport/app/main.py:42)
   - knowledge base [app/main.py:43](/home/azureuser/customsupport/app/main.py:43)
   - tool registry [app/main.py:44](/home/azureuser/customsupport/app/main.py:44)

### 1.2 Model provider switch

At [app/main.py:45](/home/azureuser/customsupport/app/main.py:45):

1. if `MODEL_PROVIDER=azure_openai` and key/base URL exist, app wires Azure classifiers + Azure response generator ([app/main.py:50](/home/azureuser/customsupport/app/main.py:50) through [app/main.py:84](/home/azureuser/customsupport/app/main.py:84)).
2. otherwise app wires Noop fallbacks ([app/main.py:85](/home/azureuser/customsupport/app/main.py:85) through [app/main.py:90](/home/azureuser/customsupport/app/main.py:90)).

### 1.3 Workflow and API app

1. workflow is compiled with injected dependencies at [app/main.py:91](/home/azureuser/customsupport/app/main.py:91) through [app/main.py:100](/home/azureuser/customsupport/app/main.py:100).
2. FastAPI app and router are registered at [app/main.py:102](/home/azureuser/customsupport/app/main.py:102) through [app/main.py:110](/home/azureuser/customsupport/app/main.py:110).
3. static frontend and root HTML are served via [app/main.py:114](/home/azureuser/customsupport/app/main.py:114) and [app/main.py:129](/home/azureuser/customsupport/app/main.py:129).

## 2) When User Enters (Session Start / “Login Attempt”)

This codebase does not implement username/password login.
"Enter" means first chat message in a new conversation.

In `/chat` ([app/api/routes.py:33](/home/azureuser/customsupport/app/api/routes.py:33)):

1. `payload_conversation_id` is parsed at [app/api/routes.py:36](/home/azureuser/customsupport/app/api/routes.py:36).
2. `is_login_attempt` is derived from missing `conversation_id` at [app/api/routes.py:37](/home/azureuser/customsupport/app/api/routes.py:37).
3. backend creates conversation ID if missing at [app/api/routes.py:53](/home/azureuser/customsupport/app/api/routes.py:53) using [app/api/routes.py:189](/home/azureuser/customsupport/app/api/routes.py:189).
4. state is loaded/created at [app/api/routes.py:54](/home/azureuser/customsupport/app/api/routes.py:54), store implementation at [app/storage/conversation_store.py:42](/home/azureuser/customsupport/app/storage/conversation_store.py:42).

Frontend ownership:

1. `user_id` is created and persisted in browser localStorage at [app/frontend/static/js/chatbot-plugin.js:20](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:20).
2. backend-issued `conversation_id` is persisted on frontend at [app/frontend/static/js/chatbot-plugin.js:81](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:81).

## 3) When User Sends Message: Understanding + Agent Behavior

### 3.1 Frontend send path

1. submit handler triggers in [app/frontend/static/js/app.js:60](/home/azureuser/customsupport/app/frontend/static/js/app.js:60).
2. plugin sends POST `/chat` at [app/frontend/static/js/chatbot-plugin.js:59](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:59).

### 3.2 API pre-workflow state preparation

1. message/user/conversation normalization at [app/api/routes.py:35](/home/azureuser/customsupport/app/api/routes.py:35) through [app/api/routes.py:39](/home/azureuser/customsupport/app/api/routes.py:39).
2. empty message check at [app/api/routes.py:39](/home/azureuser/customsupport/app/api/routes.py:39) through [app/api/routes.py:52](/home/azureuser/customsupport/app/api/routes.py:52).
3. message added to state at [app/api/routes.py:73](/home/azureuser/customsupport/app/api/routes.py:73) and [app/api/routes.py:74](/home/azureuser/customsupport/app/api/routes.py:74).
4. graph execution starts at [app/api/routes.py:77](/home/azureuser/customsupport/app/api/routes.py:77).

### 3.3 Workflow order

Defined in [app/graph/workflow.py:18](/home/azureuser/customsupport/app/graph/workflow.py:18):

1. `START -> greeting` at [app/graph/workflow.py:40](/home/azureuser/customsupport/app/graph/workflow.py:40).
2. `greeting -> router` at [app/graph/workflow.py:41](/home/azureuser/customsupport/app/graph/workflow.py:41).
3. router conditionally dispatches customer/tech/sales/fallback at [app/graph/workflow.py:42](/home/azureuser/customsupport/app/graph/workflow.py:42).
4. selected node ends the graph at [app/graph/workflow.py:52](/home/azureuser/customsupport/app/graph/workflow.py:52) through [app/graph/workflow.py:55](/home/azureuser/customsupport/app/graph/workflow.py:55).

### 3.4 Route + intent decision (new architecture)

1. router node uses injected intent classifier at [app/graph/nodes.py:39](/home/azureuser/customsupport/app/graph/nodes.py:39) through [app/graph/nodes.py:46](/home/azureuser/customsupport/app/graph/nodes.py:46).
2. `decide_route()` simply calls classifier and returns route/intent/confidence at [app/graph/router.py:21](/home/azureuser/customsupport/app/graph/router.py:21) through [app/graph/router.py:34](/home/azureuser/customsupport/app/graph/router.py:34).
3. intent classifier contract is in [app/services/intent_classifier.py:59](/home/azureuser/customsupport/app/services/intent_classifier.py:59).
4. Azure classifier builds context and calls model endpoint at [app/services/intent_classifier.py:78](/home/azureuser/customsupport/app/services/intent_classifier.py:78) through [app/services/intent_classifier.py:121](/home/azureuser/customsupport/app/services/intent_classifier.py:121).
5. route+intent are sanitized against allowed values at [app/services/intent_classifier.py:170](/home/azureuser/customsupport/app/services/intent_classifier.py:170).

### 3.5 Agent-level understanding

#### Customer support

Entry: [app/graph/nodes.py:71](/home/azureuser/customsupport/app/graph/nodes.py:71), handler at [app/agents/customer_support.py:36](/home/azureuser/customsupport/app/agents/customer_support.py:36).

Current behavior uses:

1. entity extraction from latest message at [app/agents/customer_support.py:43](/home/azureuser/customsupport/app/agents/customer_support.py:43) and [app/agents/customer_support.py:284](/home/azureuser/customsupport/app/agents/customer_support.py:284).
2. customer hint classifier output at [app/agents/customer_support.py:49](/home/azureuser/customsupport/app/agents/customer_support.py:49).
3. warranty memory lookup/cancel/non-eligible flows at [app/agents/customer_support.py:68](/home/azureuser/customsupport/app/agents/customer_support.py:68), [app/agents/customer_support.py:79](/home/azureuser/customsupport/app/agents/customer_support.py:79), [app/agents/customer_support.py:97](/home/azureuser/customsupport/app/agents/customer_support.py:97).
4. warranty validation + outcome paths at [app/agents/customer_support.py:119](/home/azureuser/customsupport/app/agents/customer_support.py:119) through [app/agents/customer_support.py:181](/home/azureuser/customsupport/app/agents/customer_support.py:181).
5. service request tool invocation at [app/agents/customer_support.py:190](/home/azureuser/customsupport/app/agents/customer_support.py:190) through [app/agents/customer_support.py:205](/home/azureuser/customsupport/app/agents/customer_support.py:205).

#### Tech support

Entry: [app/graph/nodes.py:109](/home/azureuser/customsupport/app/graph/nodes.py:109), handler at [app/agents/tech_support.py:30](/home/azureuser/customsupport/app/agents/tech_support.py:30).

Current behavior uses:

1. tech hint classifier decision at [app/agents/tech_support.py:38](/home/azureuser/customsupport/app/agents/tech_support.py:38).
2. follow-up attempt flow at [app/agents/tech_support.py:49](/home/azureuser/customsupport/app/agents/tech_support.py:49).
3. unsupported/non-resolvable handling at [app/agents/tech_support.py:86](/home/azureuser/customsupport/app/agents/tech_support.py:86) and [app/agents/tech_support.py:94](/home/azureuser/customsupport/app/agents/tech_support.py:94).
4. KB search + section-aware hints at [app/agents/tech_support.py:111](/home/azureuser/customsupport/app/agents/tech_support.py:111) through [app/agents/tech_support.py:148](/home/azureuser/customsupport/app/agents/tech_support.py:148).

#### Sales support

Entry: [app/graph/nodes.py:113](/home/azureuser/customsupport/app/graph/nodes.py:113), handler at [app/agents/sales_support.py:23](/home/azureuser/customsupport/app/agents/sales_support.py:23).

Current behavior uses:

1. sales hint classifier decision at [app/agents/sales_support.py:35](/home/azureuser/customsupport/app/agents/sales_support.py:35).
2. pending checkout/address/order placement paths at [app/agents/sales_support.py:55](/home/azureuser/customsupport/app/agents/sales_support.py:55) through [app/agents/sales_support.py:145](/home/azureuser/customsupport/app/agents/sales_support.py:145).
3. cancellation/comparison/order resolution paths at [app/agents/sales_support.py:92](/home/azureuser/customsupport/app/agents/sales_support.py:92), [app/agents/sales_support.py:106](/home/azureuser/customsupport/app/agents/sales_support.py:106), [app/agents/sales_support.py:114](/home/azureuser/customsupport/app/agents/sales_support.py:114).

#### Mixed customer + tech

If intent router marks mixed support request, customer node additionally runs tech handler and merges both hint payloads at [app/graph/nodes.py:78](/home/azureuser/customsupport/app/graph/nodes.py:78) through [app/graph/nodes.py:106](/home/azureuser/customsupport/app/graph/nodes.py:106).

#### Fallback

Fallback handler writes minimal `llm_hints` and returns empty response text at [app/agents/fallback.py:8](/home/azureuser/customsupport/app/agents/fallback.py:8) through [app/agents/fallback.py:26](/home/azureuser/customsupport/app/agents/fallback.py:26).

## 4) When User Receives Response (Generator + Persist + UI Render)

### 4.1 Final response generation step

After workflow returns:

1. `/chat` derives route+intent at [app/api/routes.py:90](/home/azureuser/customsupport/app/api/routes.py:90) and [app/api/routes.py:91](/home/azureuser/customsupport/app/api/routes.py:91).
2. response generator is called at [app/api/routes.py:93](/home/azureuser/customsupport/app/api/routes.py:93).
3. generator context packs `llm_hints`, metadata, tool calls, memory in [app/services/response_generator.py:198](/home/azureuser/customsupport/app/services/response_generator.py:198) through [app/services/response_generator.py:231](/home/azureuser/customsupport/app/services/response_generator.py:231).
4. model instructions are defined in [app/services/response_generator.py:234](/home/azureuser/customsupport/app/services/response_generator.py:234).
5. failures return `503` in API at [app/api/routes.py:99](/home/azureuser/customsupport/app/api/routes.py:99) through [app/api/routes.py:125](/home/azureuser/customsupport/app/api/routes.py:125).

### 4.2 Persistence and response payload

1. final text is inserted into state at [app/api/routes.py:127](/home/azureuser/customsupport/app/api/routes.py:127).
2. assistant message is appended at [app/api/routes.py:128](/home/azureuser/customsupport/app/api/routes.py:128).
3. state is saved at [app/api/routes.py:129](/home/azureuser/customsupport/app/api/routes.py:129), store write at [app/storage/conversation_store.py:54](/home/azureuser/customsupport/app/storage/conversation_store.py:54).
4. handoff label is computed by `_handoff_target_for` at [app/api/routes.py:193](/home/azureuser/customsupport/app/api/routes.py:193).
5. API returns final `ChatResponse` at [app/api/routes.py:147](/home/azureuser/customsupport/app/api/routes.py:147).

### 4.3 Frontend rendering

1. plugin parses backend JSON at [app/frontend/static/js/chatbot-plugin.js:80](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:80).
2. frontend updates stored conversation id at [app/frontend/static/js/chatbot-plugin.js:81](/home/azureuser/customsupport/app/frontend/static/js/chatbot-plugin.js:81).
3. UI removes `Typing...` and appends final bot text at [app/frontend/static/js/app.js:37](/home/azureuser/customsupport/app/frontend/static/js/app.js:37) through [app/frontend/static/js/app.js:40](/home/azureuser/customsupport/app/frontend/static/js/app.js:40).
4. on API error it renders failure text at [app/frontend/static/js/app.js:41](/home/azureuser/customsupport/app/frontend/static/js/app.js:41) through [app/frontend/static/js/app.js:46](/home/azureuser/customsupport/app/frontend/static/js/app.js:46).

## Quick Current Mental Model

1. Agents are now state/hint producers.
2. LLM classifiers decide route and follow-up semantics.
3. Response generator turns structured hints into final natural text.
4. API enforces non-empty generated response before returning to UI.
