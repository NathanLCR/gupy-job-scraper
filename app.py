from datetime import UTC, datetime
from threading import Lock, Thread

from flask import Flask, jsonify, request
from sqlalchemy import desc, select

from database import SessionLocal, init_db
from entities import ErrorLog, JobsPost, SearchTerm
from scraper import populate_database, scrape


app = Flask(__name__)

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
    return jsonify({"status": "ok"}), 200


@app.post("/database/init")
def initialize_database() -> tuple:
    init_db()
    return jsonify({"message": "Database initialized"}), 200


@app.post("/scrape/start")
def start_scrape() -> tuple:
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
    return jsonify(_scrape_status), 200


@app.get("/errors")
def get_errors() -> tuple:
    limit = _get_pagination_limit()
    db = SessionLocal()
    try:
        rows = db.scalars(select(ErrorLog).order_by(desc(ErrorLog.created_at)).limit(limit)).all()
        return jsonify([_serialize_error(row) for row in rows]), 200
    finally:
        db.close()


@app.get("/job-posts")
def get_job_posts() -> tuple:
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


@app.get("/search-terms")
def get_search_terms() -> tuple:
    db = SessionLocal()
    try:
        rows = db.scalars(select(SearchTerm).order_by(SearchTerm.id)).all()
        return jsonify([_serialize_search_term(row) for row in rows]), 200
    finally:
        db.close()


@app.post("/search-terms")
def create_search_term() -> tuple:
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
