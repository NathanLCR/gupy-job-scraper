import json
import pytest
from config import Settings


def production_settings(**overrides) -> Settings:
    """Helper to create a Settings object configured for production testing."""
    base = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "DATABASE_URL": "postgresql://skillpulse:secret@db.internal:5432/skillpulse",
        "ADMIN_AUTH_ENABLED": True,
        "ADMIN_API_KEY": "a" * 32,
        "RATE_LIMIT_ENABLED": True,
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "RATE_LIMIT_KEY_SALT": "secure-random-salt-for-testing-must-be-32-chars",
        "TRUSTED_PROXY_CIDRS": "[]",
        "TRUST_CLOUDFLARE_CONNECTING_IP": False,
        "CORS_ORIGINS": '["https://jobs.example.com"]',
        "CF_ACCOUNT_ID": "test-account",
        "CF_API_TOKEN": "test-token-with-enough-entropy",
        "RATE_LIMIT_SEARCH_RPM": 60,
        "RATE_LIMIT_MATCH_RPM": 20,
        "RATE_LIMIT_EXPLAIN_RPM": 5,
        "RATE_LIMIT_EXTRACT_RPM": 10,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_trusted_proxy_defaults_to_empty():
    settings = Settings(_env_file=None)
    assert settings.get_trusted_proxy_networks() == ()


@pytest.mark.parametrize("cidr", ["0.0.0.0/0", "::/0", "not-a-cidr", "10.0.0.999/32", "2001:db8:::1"])
def test_production_rejects_unsafe_or_invalid_proxy_cidrs(cidr):
    settings = production_settings(TRUSTED_PROXY_CIDRS=json.dumps([cidr]))
    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_CIDRS"):
        settings.validate_runtime_config()


def test_production_accepts_valid_trusted_proxy_cidrs():
    settings = production_settings(
        TRUSTED_PROXY_CIDRS=json.dumps(["10.0.0.0/8", "192.168.1.0/24", "2001:db8::/32"])
    )
    settings.validate_runtime_config()
    networks = settings.get_trusted_proxy_networks()
    assert len(networks) == 3
    assert str(networks[0]) == "10.0.0.0/8"


def test_production_rejects_missing_or_empty_salt():
    settings = production_settings(RATE_LIMIT_KEY_SALT=None)
    with pytest.raises(RuntimeError, match="RATE_LIMIT_KEY_SALT"):
        settings.validate_runtime_config()

    settings_empty = production_settings(RATE_LIMIT_KEY_SALT="")
    with pytest.raises(RuntimeError, match="RATE_LIMIT_KEY_SALT"):
        settings_empty.validate_runtime_config()


def test_production_rejects_short_salt():
    settings = production_settings(RATE_LIMIT_KEY_SALT="short-salt-less-than-32-chars")
    with pytest.raises(RuntimeError, match="RATE_LIMIT_KEY_SALT"):
        settings.validate_runtime_config()


@pytest.mark.parametrize(
    "placeholder",
    [
        "replace-with-at-least-32-random-characters",
        "replace_with_at_least_32_characters_here",
        "your-secret-salt-goes-here-32-chars-long",
        "your_secret_salt_goes_here_32_chars",
    ],
)
def test_production_rejects_placeholder_salt(placeholder):
    settings = production_settings(RATE_LIMIT_KEY_SALT=placeholder)
    with pytest.raises(RuntimeError, match="RATE_LIMIT_KEY_SALT"):
        settings.validate_runtime_config()


def test_production_rejects_enabled_limiter_without_redis():
    settings = production_settings(RATE_LIMIT_ENABLED=True, REDIS_URL=None)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        settings.validate_runtime_config()


def test_production_rejects_placeholder_redis_url():
    settings = production_settings(REDIS_URL="redis://replace-with-redis-host:6379/0")
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        settings.validate_runtime_config()


def test_production_rejects_cloudflare_trust_without_trusted_cidrs():
    settings = production_settings(TRUST_CLOUDFLARE_CONNECTING_IP=True, TRUSTED_PROXY_CIDRS="[]")
    with pytest.raises(RuntimeError, match="TRUST_CLOUDFLARE_CONNECTING_IP"):
        settings.validate_runtime_config()


def test_production_accepts_cloudflare_trust_with_trusted_cidrs():
    settings = production_settings(
        TRUST_CLOUDFLARE_CONNECTING_IP=True,
        TRUSTED_PROXY_CIDRS=json.dumps(["173.245.48.0/20", "103.21.244.0/22"]),
    )
    settings.validate_runtime_config()


@pytest.mark.parametrize(
    "field,value",
    [
        ("RATE_LIMIT_SEARCH_RPM", 0),
        ("RATE_LIMIT_SEARCH_RPM", -10),
        ("RATE_LIMIT_MATCH_RPM", 0),
        ("RATE_LIMIT_EXPLAIN_RPM", -1),
        ("RATE_LIMIT_EXTRACT_RPM", 0),
    ],
)
def test_production_rejects_nonpositive_rate_limits(field, value):
    settings = production_settings(**{field: value})
    with pytest.raises(RuntimeError, match="rate limits"):
        settings.validate_runtime_config()


def test_development_allows_disabled_rate_limit_and_missing_redis():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="development",
        DEBUG=True,
        RATE_LIMIT_ENABLED=False,
        REDIS_URL=None,
    )
    settings.validate_runtime_config()
    assert settings.RATE_LIMIT_ENABLED is False


def test_validation_errors_never_expose_salt_or_redis_url():
    secret_salt = "replace-salt-secret-value-not-exposed"
    secret_url = "redis://user:super_secret_pw@internal.redis.host:6379/0"
    settings = production_settings(
        RATE_LIMIT_KEY_SALT=secret_salt,
        REDIS_URL="redis://replace-with-redis-host:6379/0",
    )
    try:
        settings.validate_runtime_config()
    except RuntimeError as exc:
        msg = str(exc)
        assert secret_salt not in msg
        assert "replace-salt-secret-value-not-exposed" not in msg
        assert "super_secret_pw" not in msg
