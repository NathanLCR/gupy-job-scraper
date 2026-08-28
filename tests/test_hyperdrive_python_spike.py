import importlib.util
from pathlib import Path

from sqlalchemy.engine import make_url


SPIKE_HELPER = (
    Path(__file__).resolve().parents[1]
    / "spikes"
    / "hyperdrive_python"
    / "src"
    / "database_url.py"
)


def test_hyperdrive_url_uses_pure_python_driver_without_sslmode():
    """Catch a pg8000-incompatible driver name or leaked Hyperdrive sslmode."""
    assert SPIKE_HELPER.exists(), "the isolated Hyperdrive Python spike is missing"

    spec = importlib.util.spec_from_file_location("hyperdrive_database_url", SPIKE_HELPER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    result = module.build_sqlalchemy_url(
        "postgres://spike-user:spike-password@hyperdrive.local:5432/spike-db"
        "?sslmode=disable&application_name=skillpulse-spike"
    )
    parsed = make_url(result)

    assert parsed.drivername == "postgresql+pg8000"
    assert parsed.username == "spike-user"
    assert parsed.password == "spike-password"
    assert parsed.host == "hyperdrive.local"
    assert parsed.port == 5432
    assert parsed.database == "spike-db"
    assert parsed.query == {"application_name": "skillpulse-spike"}
