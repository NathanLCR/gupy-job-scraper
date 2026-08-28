import pytest
from config import Settings


def test_development_example_is_startable():
    settings = Settings(_env_file=".env.example")
    settings.validate_runtime_config()
    assert settings.ENVIRONMENT == "development"
    assert settings.DEBUG is True


def test_production_example_rejects_placeholders():
    settings = Settings(_env_file=".env.production.example")
    with pytest.raises(RuntimeError, match="placeholder|must be configured|entropy|characters"):
        settings.validate_runtime_config()
