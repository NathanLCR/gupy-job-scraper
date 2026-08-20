import os
import urllib.parse
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SkillPulse AI"
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

    # Dense Embeddings (In-Memory CPU SentenceTransformers)
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384

    # Batch Extraction Engine & Rate-Limit Settings
    EXTRACTION_BATCH_SIZE: int = 15
    EXTRACTION_RATE_LIMIT_DELAY: float = 2.0
    EXTRACTION_BACKOFF_SECONDS: float = 2.0

    # App environment, CORS & port
    ENVIRONMENT: str = "development"
    PORT: int = 8080
    HOST: str = "0.0.0.0"
    DEBUG: bool = True
    CORS_ORIGINS: str = '["https://skillpulse.pages.dev", "http://localhost:8000", "http://127.0.0.1:8000"]'

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
