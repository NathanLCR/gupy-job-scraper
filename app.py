from services.extractor_service import regex_extractor
import csv
from datetime import UTC, datetime
from io import StringIO
from threading import Lock, Thread
from flasgger import Swagger
from flask import Flask, Response, jsonify, redirect, request, send_from_directory
from sqlalchemy import desc, select, func
from database import SessionLocal, init_db
from entities import ErrorLog, JobsPost, SearchTerm, Job
from services.scraper_service import populate_database, scrape
from swagger_config import SWAGGER_CONFIG, SWAGGER_TEMPLATE
from utils import (
    JOB_POSTS_CSV_HEADERS,
    _get_pagination_limit,
    _get_pagination_offset,
    _job_post_to_csv_row,
    _parse_bool,
    _serialize_error,
    _serialize_job_post,
    _serialize_search_term,
    _serialize_job,
)

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

def build_job_posts_csv() -> tuple[bytes, str]:
    db = SessionLocal()
    try:
        rows = db.scalars(select(JobsPost).order_by(desc(JobsPost.published_date))).all()
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(JOB_POSTS_CSV_HEADERS)
        for row in rows:
            writer.writerow(_job_post_to_csv_row(row))
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

@app.route("/")
def index():
    return redirect("/dashboard")

@app.route("/dashboard")
def dashboard():
    return send_from_directory('frontend', 'index.html')

@app.route("/frontend/<path:path>")
def frontend_static(path):
    return send_from_directory('frontend', path)

@app.get("/health")
def health() -> tuple:
    """
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
    """
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
    """
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
    """
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
    """
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
    """
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
    """
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

@app.get("/job-posts/<int:job_id>")
def get_job_post(job_id: int) -> tuple:
    """
    ---
    tags:
      - Job posts
    parameters:
      - name: job_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Job object with full features
      404:
        description: Not found
    """
    db = SessionLocal()
    try:
        row = db.get(JobsPost, job_id)
        if row is None:
            return jsonify({"error": "Job not found."}), 404
        return jsonify(_serialize_job_post(row)), 200
    finally:
        db.close()

@app.get("/jobs")
def get_jobs_list() -> tuple:
    """
    ---
    tags:
      - Jobs
    parameters:
      - name: limit
        in: query
        type: integer
        default: 100
      - name: offset
        in: query
        type: integer
        default: 0
    responses:
      200:
        description: Array of processed job objects
    """
    limit = _get_pagination_limit()
    offset = _get_pagination_offset()
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(Job).order_by(desc(Job.id)).limit(limit).offset(offset)
        ).all()
        return jsonify([_serialize_job(row) for row in rows]), 200
    finally:
        db.close()

@app.get("/jobs/<int:job_id>")
def get_job_structured(job_id: int) -> tuple:
    """
    ---
    tags:
      - Jobs
    parameters:
      - name: job_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Job object with full relational structures
      404:
        description: Not found
    """
    db = SessionLocal()
    try:
        row = db.get(Job, job_id)
        if row is None:
            return jsonify({"error": "Job not found."}), 404
        return jsonify(_serialize_job(row)), 200
    finally:
        db.close()

@app.get("/stats")
def get_stats() -> tuple:
    """
    ---
    tags:
      - Health
    responses:
      200:
        description: Metric counts
    """
    db = SessionLocal()
    try:
        jobs_count = db.scalar(select(func.count(JobsPost.id))) or 0
        processed_jobs_count = db.scalar(select(func.count(Job.id))) or 0
        terms_count = db.scalar(select(func.count(SearchTerm.id))) or 0
        errors_count = db.scalar(select(func.count(ErrorLog.id))) or 0
        return jsonify({
            "total_jobs": jobs_count,
            "total_processed": processed_jobs_count,
            "total_terms": terms_count,
            "total_errors": errors_count
        }), 200
    finally:
        db.close()

@app.get("/job-posts/export")
def export_job_posts_csv() -> tuple:
    """
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
    """
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
    """
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
    """
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
    """
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

@app.post("/extract")
def extract_endpoint():
    """
    ---
    tags:
      - Extractor
    responses:
      200:
        description: Features extracted
    """
    regex_extractor()
    return jsonify({"message": "Features extracted."}), 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
