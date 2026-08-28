from fastapi import FastAPI
import sqlalchemy

import asgi
from workers import WorkerEntrypoint


app = FastAPI()


@app.get("/")
def read_root():
    return {
        "runtime": "python-worker",
        "fastapi": "loaded",
        "sqlalchemy": sqlalchemy.__version__,
    }


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await asgi.fetch(app, request, self.env)
