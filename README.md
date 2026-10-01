# Support Chatbot Backend (v1)

FastAPI + LangGraph backend for customer support and technical support.

## Features

- Amazon-style electronics storefront UI at `/` (cameras, CPUs, routers, WiFi modems)
- Floating chatbot icon that opens a support panel
- Frontend-backend chat plugin (`app/frontend/static/js/chatbot-plugin.js`)
- `GET /health` -> `{"status":"ok"}`
- `POST /chat` with in-memory conversation state
- Mixed customer+technical requests are handled automatically: customer support result first, then technical guidance
- `DELETE /conversations/{conversation_id}` to clear an old chat session
- Optional `GET /debug/conversations/{conversation_id}` (disabled in production)
- LLM-based routing and intent classification:
  - `customer_support`
  - `tech_support`
  - `sales_support`
  - `fallback`
- Mock-only actions (no real external operations)
- Wiki-grounded tech support from `data/wiki.txt`

## Project Structure

```text
support_chatbot_backend/
  app/
    main.py
    frontend/
      index.html
      static/
        css/styles.css
        js/chatbot-plugin.js
        js/app.js
    api/
      routes.py
      schemas.py
    graph/
      state.py
      workflow.py
      nodes.py
      router.py
    agents/
      customer_support.py
      tech_support.py
      fallback.py
    services/
      knowledge_base.py
      tool_registry.py
      mock_warranty.py
      mock_actions.py
    storage/
      conversation_store.py
    config.py
  data/
    wiki.txt
  tests/
    test_router.py
    test_tech_support.py
    test_customer_support.py
    test_chat_api.py
  pyproject.toml
  requirements.txt
```

## Environment

Copy `.env.example` to `.env`:

```env
APP_ENV=development
LOG_LEVEL=info
WIKI_FILE_PATH=data/wiki.txt
ENABLE_DEBUG_ENDPOINTS=true
MODEL_PROVIDER=none
AZURE_OPENAI_BASE_URL=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_MODEL=gpt-4.1-mini
AZURE_OPENAI_DEPLOYMENT=
LLM_TIMEOUT_SECONDS=20
```

To enable LLM-based routing/intent classification and final response generation through Azure OpenAI-compatible endpoint:

```env
MODEL_PROVIDER=azure_openai
AZURE_OPENAI_BASE_URL=https://<your-resource>.services.ai.azure.com/openai/v1
AZURE_OPENAI_API_KEY=<your-api-key>
AZURE_OPENAI_MODEL=gpt-4.1-mini
AZURE_OPENAI_DEPLOYMENT=<optional-deployment-name>
```

## Run

```powershell
cd C:\Users\altha\support_chatbot_backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/` for the UI.

## Run With Docker (2 Containers)

This project includes:

- `frontend` container (Nginx + UI) on port `8090`
- `backend` container (FastAPI) on port `8081`

From the project root:

```bash
docker compose up --build -d
```

Open:

- UI: `http://127.0.0.1:8090/`
- Backend health: `http://127.0.0.1:8081/health`

Stop:

```bash
docker compose down
```

## API

### Health

```http
GET /health
```

Response:

```json
{"status":"ok"}
```

### Chat

```http
POST /chat
```

Request:

```json
{
  "conversation_id": "optional-string",
  "user_id": "optional-string",
  "message": "My router keeps disconnecting"
}
```

Response:

```json
{
  "conversation_id": "conv_123",
  "route": "tech_support",
  "intent": "router_disconnect_issue",
  "response": "Hello! I can help with that...",
  "tool_calls": [],
  "metadata": {
    "greeted": true
  }
}
```

## Tests

```powershell
pytest -q
```

## Deployment Note

Set request-size limits at the API gateway / reverse proxy level (for example Nginx or cloud load balancer) for production deployments.
