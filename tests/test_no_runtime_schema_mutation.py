import ast
from pathlib import Path


PRODUCTION_PATHS = (
    Path("app.py"),
    Path("app_hm.py"),
    Path("services/ingestion/ingestion_manager.py"),
    Path("services/scraper_service.py"),
    Path("services/celery_app.py"),
)


def test_production_paths_do_not_import_or_call_schema_creation():
    violations = []
    for path in PRODUCTION_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "database":
                if any(alias.name == "init_db" for alias in node.names):
                    violations.append(f"{path}: imports init_db")
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in {"init_db", "create_all"}:
                    violations.append(f"{path}: calls {name}")

    assert violations == []


def test_alternate_app_has_no_database_initialization_route():
    source = Path("app_hm.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="app_hm.py")
    route_paths = []
    for node in ast.walk(tree):
        for decorator in getattr(node, "decorator_list", []):
            if isinstance(decorator, ast.Call) and decorator.args:
                value = getattr(decorator.args[0], "value", None)
                if isinstance(value, str):
                    route_paths.append(value)
    assert "/database/init" not in route_paths
