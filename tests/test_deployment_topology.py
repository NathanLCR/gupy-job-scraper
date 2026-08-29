from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _command_text(service):
    command = service.get("command", "")
    return " ".join(command) if isinstance(command, list) else str(command)


def test_compose_assigns_alembic_to_exactly_one_migration_owner():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]
    owners = [name for name, service in services.items() if "alembic upgrade head" in _command_text(service)]

    assert owners == ["migrate"]
    assert services["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert services["worker"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"


def test_api_and_worker_do_not_mutate_schema_and_worker_verifies_before_beat():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]
    entrypoint = (ROOT / "docker" / "entrypoint.sh").read_text()

    assert "alembic" not in entrypoint.lower()
    assert "alembic" not in _command_text(services["api"]).lower()
    worker_command = _command_text(services["worker"])
    assert "scripts.verify_schema" in worker_command
    assert "--beat" in worker_command


def test_api_healthcheck_uses_database_gated_readiness_endpoint():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    healthcheck = " ".join(compose["services"]["api"]["healthcheck"]["test"])
    assert "/health/ready" in healthcheck
