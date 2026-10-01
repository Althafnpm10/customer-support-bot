from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    project_root: Path
    app_env: str
    log_level: str
    wiki_file_path: Path
    enable_debug_endpoints: bool
    model_provider: str
    azure_openai_base_url: str
    azure_openai_api_key: str
    azure_openai_model: str
    azure_openai_deployment: str
    llm_timeout_seconds: float


def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    app_env = os.getenv("APP_ENV", "development").strip().lower()
    log_level = os.getenv("LOG_LEVEL", "info").strip().lower()
    model_provider = os.getenv("MODEL_PROVIDER", "none").strip().lower()
    azure_openai_base_url = os.getenv("AZURE_OPENAI_BASE_URL", "").strip()
    azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    azure_openai_model = os.getenv("AZURE_OPENAI_MODEL", "gpt-4.1-mini").strip()
    azure_openai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
    try:
        llm_timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "20").strip())
    except ValueError:
        llm_timeout_seconds = 20.0

    wiki_config = Path(os.getenv("WIKI_FILE_PATH", "data/wiki.txt"))
    wiki_file_path = wiki_config if wiki_config.is_absolute() else project_root / wiki_config

    enable_debug = _to_bool(os.getenv("ENABLE_DEBUG_ENDPOINTS"), default=True)
    if app_env == "production":
        enable_debug = False

    return Settings(
        project_root=project_root,
        app_env=app_env,
        log_level=log_level,
        wiki_file_path=wiki_file_path,
        enable_debug_endpoints=enable_debug,
        model_provider=model_provider,
        azure_openai_base_url=azure_openai_base_url,
        azure_openai_api_key=azure_openai_api_key,
        azure_openai_model=azure_openai_model,
        azure_openai_deployment=azure_openai_deployment,
        llm_timeout_seconds=llm_timeout_seconds,
    )
