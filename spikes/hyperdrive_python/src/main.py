import json

from js import console
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from workers import Response, WorkerEntrypoint

from database_url import build_sqlalchemy_url


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        stage = "binding"
        engine = None

        try:
            connection_string = str(self.env.HYPERDRIVE.connectionString)
            sqlalchemy_url = build_sqlalchemy_url(connection_string)

            stage = "engine"
            engine = create_engine(sqlalchemy_url, poolclass=NullPool)

            stage = "select_1"
            with engine.connect() as connection:
                value = connection.execute(text("SELECT 1")).scalar_one()

            return Response.from_json(
                {
                    "ok": True,
                    "runtime": "python-worker",
                    "database_path": "sqlalchemy+pg8000+hyperdrive",
                    "query": "SELECT 1",
                    "value": value,
                }
            )
        except Exception as exc:
            error = {
                "ok": False,
                "runtime": "python-worker",
                "database_path": "sqlalchemy+pg8000+hyperdrive",
                "stage": stage,
                "error_type": type(exc).__name__,
            }
            console.error(json.dumps({"event": "hyperdrive_python_spike_failed", **error}))
            return Response.from_json(error, status=500)
        finally:
            if engine is not None:
                engine.dispose()
