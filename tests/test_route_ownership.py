from collections import defaultdict

from fastapi.testclient import TestClient

from app import app


def test_no_duplicate_method_path_owners():
    owners = defaultdict(set)
    for route in app.routes:
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        for method in getattr(route, "methods", set()):
            if path and method not in {"HEAD", "OPTIONS"}:
                owners[(method, path)].add(endpoint)

    conflicts = {pair: endpoints for pair, endpoints in owners.items() if len(endpoints) > 1}
    assert conflicts == {}
    assert len(owners[("GET", "/jobs")]) == 1


def test_jobs_browser_and_api_routes_have_distinct_contracts():
    client = TestClient(app)
    browser = client.get("/jobs")
    api = client.get("/api/v1/jobs")

    assert browser.status_code == 200
    assert browser.headers["content-type"].startswith("text/html")
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("application/json")


def test_openapi_omits_removed_unversioned_job_aliases():
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    assert "/jobs" not in paths
    assert "/jobs/{id}" not in paths
    assert "/jobs/export" not in paths
    assert "/api/v1/jobs" in paths
