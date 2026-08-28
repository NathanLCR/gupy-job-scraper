import importlib
import json

from workers import Response, WorkerEntrypoint


PACKAGES = (
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "sqlalchemy",
    "alembic",
    "psycopg2",
    "asyncpg",
    "pgvector",
    "celery",
    "redis",
    "httpx",
    "requests",
    "pandas",
    "numpy",
    "dotenv",
    "multipart",
)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        results = {}
        for package in PACKAGES:
            try:
                module = importlib.import_module(package)
                results[package] = {
                    "loaded": True,
                    "version": getattr(module, "__version__", None),
                }
            except Exception as exc:
                results[package] = {
                    "loaded": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }

        body = json.dumps({"runtime": "python-worker", "packages": results})
        return Response(body, headers={"content-type": "application/json"})
