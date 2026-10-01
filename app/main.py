from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import create_api_router
from app.config import get_settings
from app.graph.nodes import NodeDependencies
from app.graph.workflow import build_support_workflow
from app.logging_config import configure_structured_logging
from app.services.customer_hint_classifier import (
    AzureOpenAICustomerHintClassifier,
    NoopCustomerHintClassifier,
)
from app.services.intent_classifier import (
    AzureOpenAIIntentClassifier,
    NoopIntentClassifier,
)
from app.services.knowledge_base import KnowledgeBaseService
from app.services.mock_actions import build_default_tool_registry
from app.services.response_generator import (
    AzureOpenAIResponseGenerator,
    NoopResponseGenerator,
)
from app.services.sales_hint_classifier import (
    AzureOpenAISalesHintClassifier,
    NoopSalesHintClassifier,
)
from app.services.tech_hint_classifier import (
    AzureOpenAITechHintClassifier,
    NoopTechHintClassifier,
)
from app.storage.conversation_store import InMemoryConversationStore

settings = get_settings()
configure_structured_logging(settings.log_level)

store = InMemoryConversationStore()
knowledge_base = KnowledgeBaseService(settings.wiki_file_path)
tools = build_default_tool_registry()
if (
    settings.model_provider == "azure_openai"
    and settings.azure_openai_base_url
    and settings.azure_openai_api_key
):
    intent_classifier = AzureOpenAIIntentClassifier(
        base_url=settings.azure_openai_base_url,
        api_key=settings.azure_openai_api_key,
        model=settings.azure_openai_model,
        deployment=settings.azure_openai_deployment,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    response_generator = AzureOpenAIResponseGenerator(
        base_url=settings.azure_openai_base_url,
        api_key=settings.azure_openai_api_key,
        model=settings.azure_openai_model,
        deployment=settings.azure_openai_deployment,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    customer_hint_classifier = AzureOpenAICustomerHintClassifier(
        base_url=settings.azure_openai_base_url,
        api_key=settings.azure_openai_api_key,
        model=settings.azure_openai_model,
        deployment=settings.azure_openai_deployment,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    tech_hint_classifier = AzureOpenAITechHintClassifier(
        base_url=settings.azure_openai_base_url,
        api_key=settings.azure_openai_api_key,
        model=settings.azure_openai_model,
        deployment=settings.azure_openai_deployment,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    sales_hint_classifier = AzureOpenAISalesHintClassifier(
        base_url=settings.azure_openai_base_url,
        api_key=settings.azure_openai_api_key,
        model=settings.azure_openai_model,
        deployment=settings.azure_openai_deployment,
        timeout_seconds=settings.llm_timeout_seconds,
    )
else:
    intent_classifier = NoopIntentClassifier()
    response_generator = NoopResponseGenerator()
    customer_hint_classifier = NoopCustomerHintClassifier()
    tech_hint_classifier = NoopTechHintClassifier()
    sales_hint_classifier = NoopSalesHintClassifier()
workflow = build_support_workflow(
    NodeDependencies(
        knowledge_base=knowledge_base,
        tools=tools,
        intent_classifier=intent_classifier,
        customer_hint_classifier=customer_hint_classifier,
        tech_hint_classifier=tech_hint_classifier,
        sales_hint_classifier=sales_hint_classifier,
    )
)

app = FastAPI(title="Support Chatbot API", version="1.0.0")
app.include_router(
    create_api_router(
        settings=settings,
        store=store,
        workflow=workflow,
        response_generator=response_generator,
    )
)

frontend_root = settings.project_root / "app" / "frontend"
static_root = frontend_root / "static"
app.mount("/static", StaticFiles(directory=static_root), name="static")


@app.middleware("http")
async def add_dev_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if settings.app_env == "development" and (
        request.url.path == "/" or request.url.path.startswith("/static/")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/", include_in_schema=False)
def storefront() -> FileResponse:
    return FileResponse(frontend_root / "index.html")


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    for error in errors:
        location = error.get("loc", ())
        if len(location) >= 2 and location[0] == "body" and location[1] == "message":
            return JSONResponse(status_code=400, content={"error": "message is required"})
    return JSONResponse(status_code=400, content={"error": "invalid request"})
