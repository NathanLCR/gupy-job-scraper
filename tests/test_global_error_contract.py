import logging

from fastapi.testclient import TestClient

from app import app


def test_unexpected_api_failure_returns_stable_json_and_request_id(monkeypatch, caplog):
    secret = "postgresql://operator:db-password@private-db.internal:5432/skillpulse"

    def explode(*args, **kwargs):
        raise RuntimeError(f"query failed against {secret}")

    monkeypatch.setattr("api.v1.jobs.get_jobs", explode)
    client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR):
        response = client.get("/api/v1/jobs", headers={"X-Request-ID": "req-contract-123"})

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"] == "req-contract-123"
    assert response.json() == {
        "detail": "Internal server error.",
        "request_id": "req-contract-123",
    }
    assert secret not in response.text
    assert "db-password" not in caplog.text
    assert "private-db.internal" not in caplog.text
    assert "Traceback" not in caplog.text


def test_generated_request_id_is_shared_by_error_body_and_header(monkeypatch):
    monkeypatch.setattr(
        "api.v1.jobs.get_jobs",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    response = TestClient(app, raise_server_exceptions=False).get("/api/v1/jobs")

    assert response.status_code == 500
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert len(response.json()["request_id"]) >= 16
