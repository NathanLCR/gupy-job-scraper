import json

from js import console
from workers import Response, WorkerEntrypoint


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        stage = "binding"
        try:
            stage = "prepare"
            stmt = self.env.DB.prepare(
                "SELECT id, name FROM companies ORDER BY id"
            )

            stage = "run"
            result = await stmt.run()

            return Response.from_json(
                {
                    "ok": True,
                    "runtime": "python-worker",
                    "database_path": "d1-ffi-binding",
                    "results": result.results,
                }
            )
        except Exception as exc:
            error = {
                "ok": False,
                "runtime": "python-worker",
                "database_path": "d1-ffi-binding",
                "stage": stage,
                "error_type": type(exc).__name__,
            }
            console.error(
                json.dumps({"event": "d1_python_read_spike_failed", **error})
            )
            return Response.from_json(error, status=500)
