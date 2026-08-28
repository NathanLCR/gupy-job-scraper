import asyncio
import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace


SPIKE_ROOT = (
    Path(__file__).resolve().parents[1] / "spikes" / "d1_python_read"
)
WORKER_MAIN = SPIKE_ROOT / "src" / "main.py"
SCHEMA = SPIKE_ROOT / "schema.sql"


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    @classmethod
    def from_json(cls, payload, status=200):
        return cls(payload, status)


class FakeWorkerEntrypoint:
    pass


def load_worker(monkeypatch, console):
    monkeypatch.setitem(sys.modules, "js", SimpleNamespace(console=console))
    monkeypatch.setitem(
        sys.modules,
        "workers",
        SimpleNamespace(
            Response=FakeResponse,
            WorkerEntrypoint=FakeWorkerEntrypoint,
        ),
    )

    assert WORKER_MAIN.exists(), "the isolated D1 Python read spike is missing"
    spec = importlib.util.spec_from_file_location("d1_python_read_main", WORKER_MAIN)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_schema_creates_project_shaped_companies_with_expected_seed_rows():
    """Catch a schema that cannot recreate the intended D1 fixture."""
    assert SCHEMA.exists(), "the D1 spike schema is missing"

    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(SCHEMA.read_text())
        rows = connection.execute(
            "SELECT id, name FROM companies ORDER BY id"
        ).fetchall()
    finally:
        connection.close()

    assert rows == [(1, "Ambev"), (2, "Eurofarma"), (3, "Nubank")]


def test_worker_reads_companies_through_the_d1_binding(monkeypatch):
    """Catch a Worker that bypasses the DB binding or changes the response contract."""
    console = SimpleNamespace(error=lambda _message: None)
    module = load_worker(monkeypatch, console)
    expected_rows = [
        {"id": 1, "name": "Ambev"},
        {"id": 2, "name": "Eurofarma"},
        {"id": 3, "name": "Nubank"},
    ]

    class Statement:
        async def run(self):
            return SimpleNamespace(results=expected_rows)

    class Database:
        def __init__(self):
            self.queries = []

        def prepare(self, query):
            self.queries.append(query)
            return Statement()

    database = Database()
    worker = module.Default()
    worker.env = SimpleNamespace(DB=database)

    response = asyncio.run(worker.fetch(SimpleNamespace()))

    assert database.queries == ["SELECT id, name FROM companies ORDER BY id"]
    assert response.status == 200
    assert response.payload == {
        "ok": True,
        "runtime": "python-worker",
        "database_path": "d1-ffi-binding",
        "results": expected_rows,
    }


def test_worker_reports_the_exact_failure_stage_without_leaking_details(monkeypatch):
    """Catch an opaque 500 or a response that exposes the database exception text."""
    logged = []
    console = SimpleNamespace(error=logged.append)
    module = load_worker(monkeypatch, console)

    class Database:
        def prepare(self, _query):
            raise RuntimeError("sensitive database detail")

    worker = module.Default()
    worker.env = SimpleNamespace(DB=Database())

    response = asyncio.run(worker.fetch(SimpleNamespace()))

    assert response.status == 500
    assert response.payload == {
        "ok": False,
        "runtime": "python-worker",
        "database_path": "d1-ffi-binding",
        "stage": "prepare",
        "error_type": "RuntimeError",
    }
    assert len(logged) == 1
    assert "d1_python_read_spike_failed" in logged[0]
    assert "sensitive database detail" not in logged[0]
