# Prompt: run the Phase 1a / Phase 3 gating spike — read `companies` from real D1 via a Python Worker

**Use this prompt to kick off a fresh Claude Code session (or hand to any engineer) to execute the next concrete step in [`docs/05_api_routing_fix_spec.md`](../05_api_routing_fix_spec.md).** It's self-contained — the session doesn't need this conversation's history, only this file and the repo.

---

## Context (read before starting)

`docs/05_api_routing_fix_spec.md` — Phase 1a — records that the Hyperdrive-from-Python spike (`spikes/hyperdrive_python/`) failed: `pg8000`, the only packageable pure-Python Postgres driver, needs a real blocking OS socket, and the Python Workers (Pyodide) sandbox doesn't expose one. Two prior spikes already proved the *unrelated* parts work fine:

- `spikes/python_worker_dependencies/` — Pyodide can resolve and inject Cloudflare bindings correctly; only the Postgres **driver** failed, not bindings in general.
- `spikes/python_worker_fastapi_baseline/` — FastAPI runs on a Python Worker at all (cold start ~29s, warm ~176ms).

The chosen resolution (Phase 1a, option A) is to stop trying to reach Postgres from a Python Worker and instead run D1's officially documented, driver-free access pattern — `self.env.DB.prepare(query).bind(...).run()` from a Python `WorkerEntrypoint` — against a **real D1 database**, not a toy. This is also, verbatim, the gating spike Phase 3 requires before any relational-data migration can be scheduled. One spike closes both.

Cloudflare's own tutorial for this exact pattern: `developers.cloudflare.com/d1/examples/query-d1-from-python-workers/`. Prepared-statement API: `developers.cloudflare.com/d1/worker-api/prepared-statements/`.

## Objective

Prove — with a real deployed Worker, a real D1 database, and a real HTTP response, not a docs citation — that a Python Worker can read a table shaped like this project's schema and return rows as JSON. Nothing more. Do not wire this into `app.py` or any production route; this is an isolated proof, scoped exactly like `spikes/hyperdrive_python/` before it.

## Steps

1. **Create the spike directory** `spikes/d1_python_read/`, mirroring the structure of `spikes/hyperdrive_python/` (`pyproject.toml`, `wrangler.jsonc`, `src/main.py`). Use the same toolchain the prior spikes used (`uv` + `workers-py` + `workers-runtime-sdk` dev dependencies — see `spikes/hyperdrive_python/pyproject.toml` for the exact pattern).

2. **Create a real D1 database.** Either:
   - `npx wrangler d1 create skillpulse-d1-read-spike`, or
   - the Cloudflare MCP tool `d1_database_create` if available in your session (`ToolSearch` for `mcp__*__d1_database_create` if it's deferred).

   Record the database name and ID — they go in `wrangler.jsonc` and in the spike result you write up afterward.

3. **Seed it with a schema shaped like this project's simplest real table**, `companies` (see [`entities/company.py`](../../entities/company.py) — just `id` (PK) and `name` (unique, not null), no relationships to worry about for this spike):

   ```sql
   -- spikes/d1_python_read/schema.sql
   CREATE TABLE IF NOT EXISTS companies (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     name TEXT NOT NULL UNIQUE
   );
   INSERT INTO companies (name) VALUES ('Ambev'), ('Eurofarma'), ('Nubank');
   ```

   Apply it to the **remote** database, not just local — a local-only D1 instance doesn't exercise the real network/binding path this spike exists to prove:
   ```bash
   npx wrangler d1 execute skillpulse-d1-read-spike --remote --file=spikes/d1_python_read/schema.sql
   ```

4. **`wrangler.jsonc`** — bind it:
   ```jsonc
   {
     "$schema": "../../node_modules/wrangler/config-schema.json",
     "name": "skillpulse-python-d1-read-spike-<TODAY'S DATE, e.g. 20260821>",
     "main": "src/main.py",
     "compatibility_date": "<TODAY>",
     "compatibility_flags": ["python_workers"],
     "d1_databases": [
       {
         "binding": "DB",
         "database_name": "skillpulse-d1-read-spike",
         "database_id": "<ID FROM STEP 2>"
       }
     ],
     "observability": { "enabled": true }
   }
   ```

5. **`src/main.py`** — follow Cloudflare's documented pattern exactly, don't improvise a different one; the point is to prove the documented path works for this project, not to find a novel one:
   ```python
   import json

   from js import console
   from workers import Response, WorkerEntrypoint


   class Default(WorkerEntrypoint):
       async def fetch(self, request):
           stage = "binding"
           try:
               stage = "prepare"
               stmt = self.env.DB.prepare("SELECT id, name FROM companies ORDER BY id")

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
               console.error(json.dumps({"event": "d1_python_read_spike_failed", **error}))
               return Response.from_json(error, status=500)
   ```

6. **Deploy for real** (this must be a live deployed Worker hitting the real D1 database over the network — the same bar the two prior spikes held themselves to, not `wrangler dev` alone):
   ```bash
   cd spikes/d1_python_read
   npx wrangler deploy
   ```

7. **Hit it twice** and capture both raw responses (status code + JSON body) — the prior spikes reported two consecutive live requests, match that:
   ```bash
   curl -s -w '\nHTTP %{http_code}\n' https://<worker-name>.<your-subdomain>.workers.dev/
   curl -s -w '\nHTTP %{http_code}\n' https://<worker-name>.<your-subdomain>.workers.dev/
   ```

## Recording the result

Whichever way it goes, **write the result into `docs/05_api_routing_fix_spec.md` yourself, in the same voice and level of evidence as the two existing spike write-ups** (Phase 1's dependency-spike and Hyperdrive-spike paragraphs) — deployed Worker name + version ID, the exact HTTP status and JSON body(ies), and which stage failed if it did. Then:

- Check off the four unchecked boxes under **Phase 1a** in the acceptance-criteria section (§4).
- Check off the matching box under **Phase 3** (`The read-one-table-from-D1 spike is confirmed working...`) — don't write the result twice, just cross-reference Phase 1a from there, the way the spec already sets up.
- If it **worked**: note explicitly that Phase 1 and Phase 3 now collapse into one migration per the Phase 1a decision, and that Phase 1's remaining Postgres/Hyperdrive-specific work (§3, Phase 1 item 3) is superseded — don't leave both an open Postgres path and a working D1 path in the doc without saying which one the project is actually taking.
- If it **failed**: capture the exact stage and error type (same shape as the Hyperdrive failure — `stage` + `error_type` in the response body already gives you this), and fall back to documenting option (B) — the RPC-bridge-to-a-JS-Worker path already written up under Phase 1a — as the path forward instead.

## Guardrails

- This is a proof, not a feature. Do not touch `app.py`, `database.py`, `entities/`, or any `api/v1/*` route.
- Don't reuse this spike's D1 database for anything beyond this proof — it's disposable, same as the Hyperdrive spike's throwaway config.
- If `wrangler d1 create` / deploy requires Cloudflare credentials you don't have in this session, say so plainly in the spec update rather than fabricating a result — the two existing spike write-ups are trusted precisely because they cite real deployed Worker versions and real response bodies.
