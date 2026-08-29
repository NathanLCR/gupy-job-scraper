import json

import pytest

import config
from config import Settings


def production_settings(**overrides) -> Settings:
    values = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "DATABASE_URL": "postgresql://skillpulse:secret@db.internal:5432/skillpulse",
        "REDIS_URL": "redis://redis.internal:6379/0",
        "ADMIN_AUTH_ENABLED": True,
        "ADMIN_API_KEY": "a" * 32,
        "RATE_LIMIT_ENABLED": True,
        "RATE_LIMIT_SHADOW": False,
        "RATE_LIMIT_KEY_SALT": "b" * 32,
        "TRUSTED_PROXY_CIDRS": "[]",
        "CORS_ORIGINS": json.dumps(["https://jobs.example.com"]),
        "CF_ACCOUNT_ID": "test-account",
        "CF_API_TOKEN": "test-token-with-enough-entropy",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///production.db",
        "not-a-database-url",
        "postgresql://missing-host",
        "postgresql://replace_user:replace_password@replace_host:5432/replace_database",
    ],
)
def test_production_rejects_unsafe_database_urls(database_url):
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        production_settings(DATABASE_URL=database_url).validate_runtime_config()


@pytest.mark.parametrize(
    "redis_url",
    ["not-a-url", "http://redis.internal:6379/0", "redis://", "redis://replace_host:6379/0"],
)
def test_production_rejects_malformed_or_placeholder_redis_urls(redis_url):
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        production_settings(REDIS_URL=redis_url).validate_runtime_config()


@pytest.mark.parametrize(
    "origins",
    [
        "*",
        '["*"]',
        '["https://jobs.example.com", "*"]',
        '["javascript:alert(1)"]',
        '["https://jobs.example.com/path"]',
        '["https://jobs.example.com", 7]',
        "https://jobs.example.com",
        "{bad-json",
    ],
)
def test_production_rejects_wildcard_or_malformed_cors(origins):
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        production_settings(CORS_ORIGINS=origins).validate_runtime_config()


def test_production_rejects_shadow_rate_limiting():
    with pytest.raises(RuntimeError, match="RATE_LIMIT_SHADOW"):
        production_settings(RATE_LIMIT_SHADOW=True).validate_runtime_config()


def test_startup_dependency_validation_rejects_unreachable_redis(monkeypatch):
    settings = production_settings()

    def unavailable(*args, **kwargs):
        raise OSError("redis://user:password@redis.internal is unavailable")

    monkeypatch.setattr(config, "_ping_redis", unavailable, raising=False)
    with pytest.raises(RuntimeError, match="REDIS_URL") as exc_info:
        settings.validate_runtime_dependencies()
    assert "password" not in str(exc_info.value)
    assert "redis.internal" not in str(exc_info.value)


def test_development_example_keeps_operator_routes_fail_closed():
    settings = Settings(_env_file=".env.example")
    assert settings.ADMIN_AUTH_ENABLED is True
    assert settings.ADMIN_API_KEY in (None, "")
