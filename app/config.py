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
