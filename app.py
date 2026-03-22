import csv
from datetime import UTC, datetime
from io import StringIO
from threading import Lock, Thread

from flasgger import Swagger
from flask import Flask, Response, jsonify, redirect, request

from sqlalchemy import desc, select

from database import SessionLocal, init_db
from entities import ErrorLog, JobsPost, SearchTerm
from scraper import populate_database, scrape
from swagger_config import SWAGGER_CONFIG, SWAGGER_TEMPLATE


app = Flask(__name__)
Swagger(app, template=SWAGGER_TEMPLATE, config=SWAGGER_CONFIG)

_scrape_lock = Lock()
_scrape_status = {
    "running": False,
    "mode": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _parse_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return bool(value)


def _get_pagination_limit(default: int = 100, max_value: int = 500) -> int:
    value = request.args.get("limit", default=default, type=int)
    if value is None:
        return default
    return max(1, min(value, max_value))


def _get_pagination_offset(default: int = 0) -> int:
    value = request.args.get("offset", default=default, type=int)
    if value is None:
        return default
    return max(0, value)


def _serialize_job_post(row: JobsPost) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "name": row.name,
        "description": row.description,
        "career_page_id": row.career_page_id,
        "career_page_name": row.career_page_name,
        "career_page_logo": row.career_page_logo,
        "career_page_url": row.career_page_url,
        "job_type": row.job_type,
        "published_date": row.published_date.isoformat() if row.published_date else None,
        "application_deadline": row.application_deadline.isoformat() if row.application_deadline else None,
        "is_remote_work": row.is_remote_work,
        "city": row.city,
        "state": row.state,
        "country": row.country,
        "job_url": row.job_url,
        "workplace_type": row.workplace_type,
        "disabilities": row.disabilities,
        "skills": row.skills,
        "badges": row.badges,
    }


def _serialize_error(row: ErrorLog) -> dict:
    return {
        "id": row.id,
        "source": row.source,
        "message": row.message,
        "term": row.term,
        "page": row.page,
        "request_limit": row.request_limit,
        "payload": row.payload,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_search_term(row: SearchTerm) -> dict:
    return {"id": row.id, "term": row.term, "is_active": row.is_active}


def _job_post_to_csv_row(row: JobsPost) -> list:
    return [
        row.id,
        row.company_id,
        row.name,
        row.description or "",
        row.career_page_id,
        row.career_page_name or "",
        row.career_page_logo or "",
        row.career_page_url or "",
        row.job_type or "",
        row.published_date.isoformat() if row.published_date else "",
        row.application_deadline.isoformat() if row.application_deadline else "",
        row.is_remote_work if row.is_remote_work is not None else "",
        row.city or "",
        row.state or "",
        row.country or "",
        row.job_url or "",
        row.workplace_type or "",
        row.disabilities if row.disabilities is not None else "",
        row.skills or "",
        row.badges or "",
    ]


JOB_POSTS_CSV_HEADERS = [
    "id",
    "company_id",
    "name",
    "description",
    "career_page_id",
    "career_page_name",
    "career_page_logo",
    "career_page_url",
    "job_type",
    "published_date",
    "application_deadline",
    "is_remote_work",
    "city",
    "state",
    "country",
    "job_url",
    "workplace_type",
    "disabilities",
    "skills",
    "badges",
]


def build_job_posts_csv() -> tuple[bytes, str]:
    """Return UTF-8 CSV bytes (with BOM for Excel) and suggested filename."""
    db = SessionLocal()
    try:
        rows = db.scalars(select(JobsPost).order_by(desc(JobsPost.published_date))).all()
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(JOB_POSTS_CSV_HEADERS)
        for row in rows:
            writer.writerow(_job_post_to_csv_row(row))
        # utf-8-sig adds BOM so Excel opens UTF-8 correctly
        data = buffer.getvalue().encode("utf-8-sig")
        filename = f"job_posts_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
        return data, filename
    finally:
        db.close()


def _run_scraper(mode: str) -> None:
    with _scrape_lock:
        _scrape_status["running"] = True
        _scrape_status["mode"] = mode
        _scrape_status["started_at"] = datetime.now(UTC).isoformat()
        _scrape_status["finished_at"] = None
        _scrape_status["error"] = None

    try:
        if mode == "populate":
            populate_database()
        else:
            scrape()
    except Exception as exc:
        _scrape_status["error"] = str(exc)
    finally:
        _scrape_status["running"] = False
        _scrape_status["finished_at"] = datetime.now(UTC).isoformat()


@app.get("/health")
def health() -> tuple:
    """Service health check.
    ---
    tags:
      - Health
    responses:
      200:
        description: OK
        schema:
          type: object
          properties:
            status:
              type: string
              example: ok
    """
    return jsonify({"status": "ok"}), 200


@app.get("/docs")
def docs_redirect() -> tuple:
    """Redirect to Swagger UI.
    ---
    tags:
      - Health
    responses:
      302:
        description: Redirects to /apidocs/
    """
    return redirect("/apidocs/", code=302)


@app.post("/database/init")
def initialize_database() -> tuple:
    """Create all SQLAlchemy tables if they do not exist.
    ---
    tags:
      - Database
    responses:
      200:
        description: Tables created or already present
        schema:
          type: object
          properties:
            message:
              type: string
              example: Database initialized
    """
    init_db()
    return jsonify({"message": "Database initialized"}), 200


@app.post("/scrape/start")
def start_scrape() -> tuple:
    """Start background scrape (incremental or full populate).
    ---
    tags:
      - Scraper
    parameters:
      - name: mode
        in: query
        type: string
        enum: [incremental, populate]
        default: incremental
        description: incremental = new jobs only; populate = full historical load
    responses:
      202:
        description: Scrape job accepted
        schema:
          type: object
          properties:
            message:
              type: string
            mode:
              type: string
      400:
        description: Invalid mode
      409:
        description: A scrape is already running
    """
    mode = request.args.get("mode", "incremental").strip().lower()
    if mode not in {"incremental", "populate"}:
        return jsonify({"error": "Invalid mode. Use 'incremental' or 'populate'."}), 400

    if _scrape_status["running"]:
        return jsonify({"error": "A scrape job is already running."}), 409

    thread = Thread(target=_run_scraper, args=(mode,), daemon=True)
    thread.start()
    return jsonify({"message": "Scrape started", "mode": mode}), 202


@app.get("/scrape/status")
def scrape_status() -> tuple:
    """Current scrape job status (running, timestamps, error if any).
    ---
    tags:
      - Scraper
    responses:
      200:
        description: Status payload
        schema:
          type: object
          properties:
            running:
              type: boolean
            mode:
              type: string
              nullable: true
            started_at:
              type: string
              nullable: true
            finished_at:
              type: string
              nullable: true
            error:
              type: string
              nullable: true
    """
    return jsonify(_scrape_status), 200


@app.get("/errors")
def get_errors() -> tuple:
    """List recent error log entries (newest first).
    ---
    tags:
      - Errors
    parameters:
      - name: limit
        in: query
        type: integer
        default: 100
        description: Max rows (1–500)
    responses:
      200:
        description: Array of error log objects
    """
    limit = _get_pagination_limit()
    db = SessionLocal()
    try:
        rows = db.scalars(select(ErrorLog).order_by(desc(ErrorLog.created_at)).limit(limit)).all()
        return jsonify([_serialize_error(row) for row in rows]), 200
    finally:
        db.close()


@app.get("/job-posts")
def get_job_posts() -> tuple:
    """List job posts (newest by published_date first).
    ---
    tags:
      - Job posts
    parameters:
      - name: limit
        in: query
        type: integer
        default: 100
        description: Page size (1–500)
      - name: offset
        in: query
        type: integer
        default: 0
        description: Rows to skip
    responses:
      200:
        description: Array of job post objects
    """
    limit = _get_pagination_limit()
    offset = _get_pagination_offset()
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(JobsPost).order_by(desc(JobsPost.published_date)).limit(limit).offset(offset)
        ).all()
        return jsonify([_serialize_job_post(row) for row in rows]), 200
    finally:
        db.close()


@app.get("/job-posts/export")
def export_job_posts_csv() -> tuple:
    """Download all job posts as a CSV file (Excel-friendly UTF-8).
    ---
    tags:
      - Job posts
    produces:
      - text/csv
    responses:
      200:
        description: CSV attachment with every row from jobs_posts
    """
    data, filename = build_job_posts_csv()
    return (
        Response(
            data,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        ),
        200,
    )


@app.get("/search-terms")
def get_search_terms() -> tuple:
    """List all search terms used by the scraper.
    ---
    tags:
      - Search terms
    responses:
      200:
        description: Array of search term objects
    """
    db = SessionLocal()
    try:
        rows = db.scalars(select(SearchTerm).order_by(SearchTerm.id)).all()
        return jsonify([_serialize_search_term(row) for row in rows]), 200
    finally:
        db.close()


@app.post("/search-terms")
def create_search_term() -> tuple:
    """Create a search term.
    ---
    tags:
      - Search terms
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - term
          properties:
            term:
              type: string
            is_active:
              type: boolean
              default: true
    responses:
      201:
        description: Created
      400:
        description: Validation error
      409:
        description: Duplicate term
    """
    payload = request.get_json(silent=True) or {}
    term = (payload.get("term") or "").strip()
    is_active = _parse_bool(payload.get("is_active"), default=True)
    if not term:
        return jsonify({"error": "Field 'term' is required."}), 400

    db = SessionLocal()
    try:
        existing = db.scalar(select(SearchTerm).where(SearchTerm.term == term))
        if existing:
            return jsonify({"error": "Search term already exists."}), 409

        row = SearchTerm(term=term, is_active=is_active)
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(_serialize_search_term(row)), 201
    finally:
        db.close()


@app.put("/search-terms/<int:term_id>")
def update_search_term(term_id: int) -> tuple:
    """Update a search term by id.
    ---
    tags:
      - Search terms
    parameters:
      - name: term_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        schema:
          type: object
          properties:
            term:
              type: string
            is_active:
              type: boolean
    responses:
      200:
        description: Updated
      404:
        description: Not found
      409:
        description: Duplicate term
    """
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = db.get(SearchTerm, term_id)
        if row is None:
            return jsonify({"error": "Search term not found."}), 404

        if "term" in payload:
            new_term = (payload.get("term") or "").strip()
            if not new_term:
                return jsonify({"error": "Field 'term' cannot be empty."}), 400
            duplicate = db.scalar(
                select(SearchTerm).where(SearchTerm.term == new_term, SearchTerm.id != term_id)
            )
            if duplicate:
                return jsonify({"error": "Search term already exists."}), 409
            row.term = new_term

        if "is_active" in payload:
            row.is_active = _parse_bool(payload["is_active"], default=row.is_active)

        db.commit()
        db.refresh(row)
        return jsonify(_serialize_search_term(row)), 200
    finally:
        db.close()


@app.delete("/search-terms/<int:term_id>")
def delete_search_term(term_id: int) -> tuple:
    """Delete a search term by id.
    ---
    tags:
      - Search terms
    parameters:
      - name: term_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Deleted
      404:
        description: Not found
    """
    db = SessionLocal()
    try:
        row = db.get(SearchTerm, term_id)
        if row is None:
            return jsonify({"error": "Search term not found."}), 404
        db.delete(row)
        db.commit()
        return jsonify({"message": "Search term deleted."}), 200
    finally:
        db.close()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
