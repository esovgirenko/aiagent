import os
from dataclasses import dataclass


@dataclass
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    app_title: str = os.getenv("APP_TITLE", "Multi-LLM AI Agent")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/agent.db")
    auth_password: str = os.getenv("AUTH_PASSWORD", "")
    session_secret: str = os.getenv("SESSION_SECRET", "change-me-in-production")
    default_username: str = os.getenv("DEFAULT_USERNAME", "admin")
    default_password: str = os.getenv("DEFAULT_PASSWORD", "")
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
    autonomy_interval_sec: int = int(os.getenv("AUTONOMY_INTERVAL_SEC", "20"))
    autonomy_max_iterations: int = int(os.getenv("AUTONOMY_MAX_ITERATIONS", "20"))
    autonomy_fail_streak_limit: int = int(os.getenv("AUTONOMY_FAIL_STREAK_LIMIT", "3"))
    autonomy_idle_cycles_before_stop: int = int(os.getenv("AUTONOMY_IDLE_CYCLES_BEFORE_STOP", "2"))
    autonomy_summary_interval_sec: int = int(os.getenv("AUTONOMY_SUMMARY_INTERVAL_SEC", "3600"))
    autonomy_reviewer_provider: str = os.getenv("AUTONOMY_REVIEWER_PROVIDER", "openai")
    autonomy_reviewer_enabled: bool = os.getenv("AUTONOMY_REVIEWER_ENABLED", "true").lower() == "true"
    autonomy_self_edit_enabled: bool = os.getenv("AUTONOMY_SELF_EDIT_ENABLED", "false").lower() == "true"
    web_search_enabled: bool = os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true"
    web_search_max_results: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")

    gigachat_auth_url: str = os.getenv(
        "GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    )
    gigachat_api_url: str = os.getenv(
        "GIGACHAT_API_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    )
    gigachat_scope: str = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    gigachat_auth_key: str = os.getenv("GIGACHAT_AUTH_KEY", "")
    gigachat_client_id: str = os.getenv("GIGACHAT_CLIENT_ID", "")
    gigachat_client_secret: str = os.getenv("GIGACHAT_CLIENT_SECRET", "")
    gigachat_model: str = os.getenv("GIGACHAT_MODEL", "GigaChat")


settings = Settings()
