import ipaddress
import json
import os
import urllib.parse
from typing import Optional, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


_PLACEHOLDER_PARTS = ("replace_", "replace-", "your_", "your-")


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return any(part in lowered for part in _PLACEHOLDER_PARTS)


def _ping_redis(redis_url: str, timeout_seconds: float = 1.0) -> None:
    import redis

    client = redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=timeout_seconds,
        socket_timeout=timeout_seconds,
    )
    client.ping()


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
    REDIS_URL: Optional[str] = None
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
    EMBEDDING_PROVIDER: str = "cloudflare"
    ACTIVE_EMBEDDING_MODEL: str = "@cf/baai/bge-small-en-v1.5"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    POSTGRES_INDEXED_RETRIEVAL_ENABLED: bool = False
    EMBEDDING_REEMBED_INTERVAL_SECONDS: int = 900

    # Batch Extraction Engine & Rate-Limit Settings
    EXTRACTION_BATCH_SIZE: int = 15
    EXTRACTION_RATE_LIMIT_DELAY: float = 2.0
    EXTRACTION_BACKOFF_SECONDS: float = 2.0

    # Public API Rate Limiting & Distributed Limiter Settings
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_SHADOW: bool = False
    RATE_LIMIT_KEY_SALT: Optional[str] = None
    TRUSTED_PROXY_CIDRS: str = "[]"
    TRUST_CLOUDFLARE_CONNECTING_IP: bool = False
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

    def get_cors_origins(self) -> tuple[str, ...]:
        raw = self.CORS_ORIGINS
        try:
            values = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "Production configuration refusal: CORS_ORIGINS must be a valid JSON array"
            ) from exc
        if not isinstance(values, list) or not values:
            raise RuntimeError(
                "Production configuration refusal: CORS_ORIGINS must be a non-empty JSON array"
            )

        origins: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip() or value.strip() == "*":
                raise RuntimeError(
                    "Production configuration refusal: CORS_ORIGINS contains an invalid origin"
                )
            parsed = urllib.parse.urlsplit(value.strip())
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise RuntimeError(
                    "Production configuration refusal: CORS_ORIGINS contains an invalid origin"
                )
            origins.append(value.strip().rstrip("/"))
        return tuple(origins)

    def get_trusted_proxy_networks(self) -> tuple[Union[ipaddress.IPv4Network, ipaddress.IPv6Network], ...]:
        raw = self.TRUSTED_PROXY_CIDRS
        if isinstance(raw, str):
            try:
                values = json.loads(raw)
            except Exception as exc:
                raise RuntimeError("Production configuration refusal: TRUSTED_PROXY_CIDRS must be a valid JSON list of CIDR strings") from exc
        elif isinstance(raw, (list, tuple)):
            values = list(raw)
        else:
            raise RuntimeError("Production configuration refusal: TRUSTED_PROXY_CIDRS must be a valid JSON list of CIDR strings")

        if not isinstance(values, list):
            raise RuntimeError("Production configuration refusal: TRUSTED_PROXY_CIDRS must be a JSON array of CIDR strings")

        networks = []
        for value in values:
            if not isinstance(value, str):
                raise RuntimeError("Production configuration refusal: TRUSTED_PROXY_CIDRS entries must be strings")
            try:
                net = ipaddress.ip_network(value, strict=False)
            except Exception as exc:
                raise RuntimeError("Production configuration refusal: TRUSTED_PROXY_CIDRS contains invalid CIDR") from exc
            networks.append(net)
        return tuple(networks)

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
            stripped_key = self.ADMIN_API_KEY.strip().lower()
            if any(stripped_key.startswith(prefix) for prefix in ("replace_", "replace-", "your_", "your-")):
                raise RuntimeError("Production configuration refusal: ADMIN_API_KEY must not be a placeholder")
            if self.DEBUG:
                raise RuntimeError("Production configuration refusal: DEBUG must be False in production")

    def validate_runtime_config(self) -> None:
        """
        Validate full runtime configuration at startup.
        In production, enforces security settings, rate limiting, Redis settings,
        trusted proxy CIDRs, and positive rate limits.
        """
        self.validate_security_config()

        if self.ENVIRONMENT.lower() == "production":
            database_url = (self.DATABASE_URL or "").strip()
            try:
                parsed_database = make_url(database_url)
            except (ArgumentError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    "Production configuration refusal: DATABASE_URL is malformed"
                ) from exc
            if (
                parsed_database.get_backend_name() != "postgresql"
                or not parsed_database.host
                or not parsed_database.database
                or _is_placeholder(database_url)
            ):
                raise RuntimeError(
                    "Production configuration refusal: DATABASE_URL must be a non-placeholder PostgreSQL URL"
                )

            self.get_cors_origins()

            if self.EMBEDDING_PROVIDER != "cloudflare":
                raise RuntimeError(
                    "Production configuration refusal: EMBEDDING_PROVIDER must select the configured production provider"
                )
            if self.ACTIVE_EMBEDDING_MODEL != self.CF_EMBEDDING_MODEL:
                raise RuntimeError(
                    "Production configuration refusal: ACTIVE_EMBEDDING_MODEL must match CF_EMBEDDING_MODEL"
                )
            if not self.CF_ACCOUNT_ID or _is_placeholder(self.CF_ACCOUNT_ID):
                raise RuntimeError(
                    "Production configuration refusal: CF_ACCOUNT_ID must be configured"
                )
            if not self.CF_API_TOKEN or _is_placeholder(self.CF_API_TOKEN):
                raise RuntimeError(
                    "Production configuration refusal: CF_API_TOKEN must be configured"
                )

            if not self.RATE_LIMIT_ENABLED:
                raise RuntimeError("Production configuration refusal: RATE_LIMIT_ENABLED must be True in production")
            if self.RATE_LIMIT_SHADOW:
                raise RuntimeError("Production configuration refusal: RATE_LIMIT_SHADOW must be False in production")

            if not self.REDIS_URL or not self.REDIS_URL.strip():
                raise RuntimeError("Production configuration refusal: REDIS_URL must be configured when RATE_LIMIT_ENABLED is True")

            stripped_redis = self.REDIS_URL.strip()
            parsed_redis = urllib.parse.urlsplit(stripped_redis)
            if (
                parsed_redis.scheme not in {"redis", "rediss"}
                or not parsed_redis.hostname
                or _is_placeholder(stripped_redis)
            ):
                raise RuntimeError("Production configuration refusal: REDIS_URL must not be a placeholder")

            if not self.RATE_LIMIT_KEY_SALT or not self.RATE_LIMIT_KEY_SALT.strip():
                raise RuntimeError("Production configuration refusal: RATE_LIMIT_KEY_SALT must be configured when RATE_LIMIT_ENABLED is True")
            if len(self.RATE_LIMIT_KEY_SALT) < 32:
                raise RuntimeError("Production configuration refusal: RATE_LIMIT_KEY_SALT must be at least 32 characters")

            stripped_salt = self.RATE_LIMIT_KEY_SALT.strip().lower()
            if any(stripped_salt.startswith(p) for p in ("replace-", "replace_", "your-", "your_")) or "replace-with-at-least-32-random-characters" in stripped_salt:
                raise RuntimeError("Production configuration refusal: RATE_LIMIT_KEY_SALT must not be a placeholder")

            networks = self.get_trusted_proxy_networks()
            for net in networks:
                if net.prefixlen == 0:
                    raise RuntimeError("Production configuration refusal: TRUSTED_PROXY_CIDRS must not contain universal CIDRs (0.0.0.0/0 or ::/0)")

            if self.TRUST_CLOUDFLARE_CONNECTING_IP:
                if len(networks) == 0:
                    raise RuntimeError("Production configuration refusal: TRUST_CLOUDFLARE_CONNECTING_IP requires at least one CIDR in TRUSTED_PROXY_CIDRS")

            if (
                self.RATE_LIMIT_SEARCH_RPM <= 0
                or self.RATE_LIMIT_MATCH_RPM <= 0
                or self.RATE_LIMIT_EXPLAIN_RPM <= 0
                or self.RATE_LIMIT_EXTRACT_RPM <= 0
            ):
                raise RuntimeError("Production configuration refusal: rate limits must be positive integers")

    def validate_runtime_dependencies(self) -> None:
        """Validate bounded external dependencies before a production listener starts."""
        self.validate_runtime_config()
        if not self.RATE_LIMIT_ENABLED:
            return
        if not self.REDIS_URL:
            raise RuntimeError("Production configuration refusal: REDIS_URL must be configured")
        try:
            _ping_redis(self.REDIS_URL, timeout_seconds=1.0)
        except Exception as exc:
            raise RuntimeError(
                "Production configuration refusal: REDIS_URL is unreachable"
            ) from exc


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
