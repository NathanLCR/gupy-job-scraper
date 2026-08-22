import os
import urllib.parse
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SkillPulse"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: Optional[str] = None
    ASYNC_DATABASE_URL: Optional[str] = None
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "postgres"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_SSLMODE: Optional[str] = None

    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    # Cloud AI Router (Groq & OpenRouter Free Tiers)
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Local LLM Fallback (Ollama)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1"

    # Cloudflare Workers AI & Edge Embeddings
    CF_ACCOUNT_ID: Optional[str] = None
    CF_API_TOKEN: Optional[str] = None
    CF_EMBEDDING_MODEL: str = "@cf/baai/bge-small-en-v1.5"

    # Dense Embeddings (Cloudflare Workers AI BGE-small / SentenceTransformers)
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384

    # Batch Extraction Engine & Rate-Limit Settings
    EXTRACTION_BATCH_SIZE: int = 15
    EXTRACTION_RATE_LIMIT_DELAY: float = 2.0
    EXTRACTION_BACKOFF_SECONDS: float = 2.0

    # Public API Rate Limiting (Requests per minute per client IP)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_SEARCH_RPM: int = 60
    RATE_LIMIT_MATCH_RPM: int = 20
    RATE_LIMIT_EXPLAIN_RPM: int = 5
    RATE_LIMIT_EXTRACT_RPM: int = 10

    # Admin & Operator Console Security (Spec 08: Fail-Closed Operator Security)
    ADMIN_API_KEY: Optional[str] = None
    ADMIN_AUTH_ENABLED: bool = True
    ADMIN_SESSION_COOKIE: str = "skillpulse_admin_session"

    # App environment, CORS & port
    ENVIRONMENT: str = "development"
    PORT: int = 8080
    HOST: str = "0.0.0.0"
    DEBUG: bool = True
    CORS_ORIGINS: str = '["https://skillpulse.pages.dev", "http://localhost:8000", "http://127.0.0.1:8000"]'

    def validate_security_config(self) -> None:
        """
        Enforce fail-closed security configuration at startup per Spec 08 §4.
        In production, application startup refuses to proceed if:
        - Admin authentication is disabled;
        - ADMIN_API_KEY is unset or has insufficient entropy (< 32 characters);
        - DEBUG mode is enabled.
        """
        if self.ENVIRONMENT.lower() == "production":
            if not self.ADMIN_AUTH_ENABLED:
                raise RuntimeError("Production configuration refusal: ADMIN_AUTH_ENABLED must be True")
            if not self.ADMIN_API_KEY:
                raise RuntimeError("Production configuration refusal: ADMIN_API_KEY must be configured in production")
            if len(self.ADMIN_API_KEY) < 32:
                raise RuntimeError("Production configuration refusal: ADMIN_API_KEY must be at least 32 characters of entropy")
            if self.DEBUG:
                raise RuntimeError("Production configuration refusal: DEBUG must be False in production")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_sync_database_url(self) -> str:
        env_url = os.getenv("DATABASE_URL")
        if env_url:
            if env_url.startswith("postgres://"):
                env_url = "postgresql://" + env_url[len("postgres://") :]
            return env_url

        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = "postgresql://" + url[len("postgres://") :]
            return url

        user = urllib.parse.quote_plus(self.DB_USER)
        password = urllib.parse.quote_plus(self.DB_PASSWORD)
        url = f"postgresql://{user}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        if self.DB_SSLMODE:
            url += f"?sslmode={urllib.parse.quote_plus(self.DB_SSLMODE)}"
        return url

    def get_async_database_url(self) -> str:
        env_url = os.getenv("ASYNC_DATABASE_URL")
        if env_url:
            return env_url

        if self.ASYNC_DATABASE_URL:
            return self.ASYNC_DATABASE_URL

        sync_url = self.get_sync_database_url()
        if sync_url.startswith("postgresql://"):
            return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if sync_url.startswith("postgresql+psycopg2://"):
            return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if sync_url.startswith("sqlite://"):
            return sync_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return sync_url


settings = Settings()
