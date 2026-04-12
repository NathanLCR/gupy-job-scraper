# LLM Extractor Codex Handoff

## User Request

The user asked:

> Can you finish my LLM extractor?

Follow-up request:

> Dump this chat and the changes you have done into a LLM_extractor_codex.md inside ai-assistance

## What Was Found

The project already had an LLM-related file at `features_extractors/llm_extractor.py`, but it was only a standalone script that:

- queried Ollama directly
- read `JobPost` rows from the database
- exported extracted data to `extracted_jobs_llm.csv`
- did not persist structured results into the normalized `jobs` tables
- did not integrate with `services/extractor_service.py`
- did not expose any LLM extraction endpoint in the Flask apps
- did not have dedicated tests for the LLM path

At the same time, the regex extractor was already integrated end-to-end through:

- `services/extractor_service.py`
- `POST /regex-extract`
- `GET /regex-extract/status`
- normalized DB persistence into `Job`, `Company`, `ContractType`, `State`, `City`, and skill relations

## Work Completed

### 1. Reworked the LLM extractor into a reusable feature extractor

Updated `features_extractors/llm_extractor.py` so it now:

- keeps the Ollama request logic in `call_ollama(...)`
- exposes `extract(description, *, model=DEFAULT_MODEL)`
- normalizes raw LLM JSON into the same feature shape used by the service layer
- coerces list-like fields safely
- coerces numeric fields such as years of experience and confidence score
- removes the CSV-export-only workflow

Normalized output keys now include:

- `job_title`
- `salary`
- `seniority`
- `contract_type`
- `hard_skills`
- `soft_skills`
- `nice_to_have`
- `years_experience`
- `confidence_score`

### 2. Integrated LLM extraction into the main extractor service

Updated `services/extractor_service.py` so it now supports both extractor types:

- `regex`
- `llm`

Changes made:

- introduced per-extractor status tracking via `extractor_statuses`
- kept `get_extractor_status()` backward-compatible, defaulting to `regex`
- added a shared `_run_extractor(...)` pipeline for DB persistence
- added `llm_extractor(limit=None)`
- added `start_llm_extractor_thread(...)`
- extended `start_extractor_thread(...)` to optionally run the `llm` flow

The shared persistence flow now:

- pulls only `JobPost` records that do not yet exist in `Job`
- creates missing `Company`, `State`, `City`, `ContractType`
- creates or reuses `HardSkill`, `SoftSkill`, `NiceToHaveSkill`
- writes a normalized `Job` row with `extractor_type="llm"` for the LLM path
- logs extractor-specific errors through `log_error(...)`

### 3. Added API endpoints for the LLM extractor

Updated both Flask entrypoints:

- `app.py`
- `app_hm.py`

New endpoints:

- `POST /llm-extract`
- `GET /llm-extract/status`

These mirror the existing regex extractor behavior and allow the LLM extractor to be triggered in the same way from the backend/API.

## Files Changed

- `features_extractors/llm_extractor.py`
- `services/extractor_service.py`
- `app.py`
- `app_hm.py`
- `tests/llm_extractor_test.py`

## Tests Added

Created `tests/llm_extractor_test.py` with coverage for:

- the LLM extractor DB persistence path
- the new `/llm-extract` endpoint
- the new `/llm-extract/status` endpoint

The DB persistence test stubs the model call so tests remain deterministic and do not depend on a live Ollama service.

## Verification Performed

Ran targeted tests:

```bash
pytest -q tests/llm_extractor_test.py tests/extractor_service_test.py
```

Result:

- `9 passed`

Ran a syntax/compile check on touched backend files:

```bash
python3 -m compileall services/extractor_service.py features_extractors/llm_extractor.py app.py app_hm.py
```

Then ran the full test suite:

```bash
pytest -q
```

Result:

- `14 passed`

## Important Note

The backend/API work is complete, but the dashboard UI was not updated to trigger the new LLM extractor. The existing frontend button still points to:

- `POST /regex-extract`

So the LLM extractor is ready on the backend, but not yet wired into the frontend controls.

## Brief Chat Summary

Summary of the collaboration in this chat:

1. Inspected the repository structure and confirmed the extractor-related files.
2. Detected that the repo already had unrelated local modifications and avoided touching them unnecessarily.
3. Reviewed the standalone LLM extractor, the regex extractor service, the Flask entrypoints, and the tests.
4. Determined that the main missing piece was service/API integration rather than just model prompting.
5. Reworked the LLM extractor into a reusable module.
6. Added a full LLM extraction persistence path to the service layer.
7. Added `/llm-extract` and `/llm-extract/status`.
8. Added tests and verified everything passed.
9. Reported that the frontend button still targets regex extraction.

## Suggested Next Step

If needed, the next logical step is to update the dashboard so users can:

- choose between regex and LLM extraction
- see separate extractor statuses in the UI
- filter errors for `llm_extractor` alongside `regex_extractor`
