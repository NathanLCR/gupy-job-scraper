try:
    from flasgger import Swagger
except ModuleNotFoundError:  # pragma: no cover - local environments may skip optional docs dependency
    class Swagger:  # type: ignore[override]
        def __init__(self, app, template=None, config=None):
            self.app = app
            self.template = template
            self.config = config
from database import init_db
from services.search_terms_service_hm import (
    get_search_terms,
    add_search_term,
    remove_search_term,
    update_search_term,
)
from services.extractor_service import (
    start_extractor_thread,
    start_llm_extractor_thread,
    get_extractor_status,
)
from flask import Flask, Response, send_from_directory, jsonify, redirect, request
from services.scraper_service_hm import start_scrape_thread, get_scrape_status
from services.error_service import get_errors
from services.job_service_hm import get_jobs, get_job
from services.stats_service import get_stats
from services.jobs_post_service_hm import get_jobs_posts, get_job_post
from services.features_service_hm import get_average_job_post_daily, get_top_locations, get_top_technologies, get_average_salary, get_jobs_by_contract_type, get_jobs_by_seniority, get_technology_trends
from services.csv_service import export_job_posts_csv, export_jobs_csv
from swagger_config import SWAGGER_CONFIG, SWAGGER_TEMPLATE

app = Flask(__name__)
Swagger(app, template=SWAGGER_TEMPLATE, config=SWAGGER_CONFIG)


def _get_positive_int_arg(name: str, default: int, *, minimum: int = 1, maximum: int = 100) -> int:
    value = request.args.get(name, default=default, type=int)
    if value is None:
        return default
    return max(minimum, min(value, maximum))


def _get_sort_direction(default: str = "desc") -> str:
    value = (request.args.get("order", default) or default).lower()
    return "asc" if value == "asc" else "desc"

@app.route("/")
def index():
    return redirect("/dashboard")

@app.route("/dashboard")
def dashboard():
    return send_from_directory('frontend', 'index.html')

@app.get("/docs")
def docs_redirect():
    """
    ---
    tags:
      - Health
    responses:
      302:
        description: Redirects to /apidocs/
    """
    return redirect("/apidocs/", code=302)

@app.route("/frontend/<path:path>")
def frontend_static(path):
    return send_from_directory('frontend', path)

@app.post("/database/init")
def initialize_database():
    """
    ---
    tags:
      - Database
    responses:
      200:
        description: Tables created or already present
    """
    init_db()
    return jsonify({"message": "Database initialized"}), 200

@app.post("/scrape/start")
def start_scrape():
    """
    ---
    tags:
      - Scraper
    responses:
      202:
        description: Scrape started in the background
    """
    start_scrape_thread()
    return jsonify({"message": "Scrape started", "mode": "incremental"}), 202

@app.get("/health")
def health() -> tuple:
    """
    ---
    tags:
      - Health
    responses:
      200:
        description: Service is reachable
    """
    return jsonify({"status": "ok"}), 200

@app.get("/scrape/status")
def scrape_status():
    """
    ---
    tags:
      - Scraper
    responses:
      200:
        description: Scraper status payload
    """
    return jsonify(get_scrape_status()), 200

@app.get("/errors")
def errors():
    """
    ---
    tags:
      - Errors
    parameters:
      - name: page
        in: query
        type: integer
      - name: page_size
        in: query
        type: integer
      - name: search
        in: query
        type: string
      - name: source
        in: query
        type: string
    responses:
      200:
        description: Paginated error log results
    """
    payload = get_errors(
        search=request.args.get("search", type=str),
        source=request.args.get("source", type=str),
        page=_get_positive_int_arg("page", 1),
        page_size=_get_positive_int_arg("page_size", 20),
        paginated=True,
    )
    return jsonify(payload), 200

@app.get("/stats")
def stats():
    """
    ---
    tags:
      - Health
    responses:
      200:
        description: Dashboard metric counts
    """
    return jsonify(get_stats()), 200

@app.get("/job-posts")
def jobs_posts():
    """
    ---
    tags:
      - Job posts
    parameters:
      - name: page
        in: query
        type: integer
      - name: page_size
        in: query
        type: integer
      - name: search
        in: query
        type: string
      - name: workplace_type
        in: query
        type: string
      - name: sort
        in: query
        type: string
      - name: order
        in: query
        type: string
    responses:
      200:
        description: Paginated job posts
    """
    payload = get_jobs_posts(
        search=request.args.get("search", type=str),
        workplace_type=request.args.get("workplace_type", type=str),
        sort=request.args.get("sort", default="published_date", type=str),
        order=_get_sort_direction(),
        page=_get_positive_int_arg("page", 1),
        page_size=_get_positive_int_arg("page_size", 20),
        paginated=True,
    )
    return jsonify(payload), 200

@app.get("/job-posts/<id>")
def job_post(id):
    """
    ---
    tags:
      - Job posts
    parameters:
      - name: id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Single job post
      404:
        description: Not found
    """
    try:
        job_post = get_job_post(id)
        return jsonify(job_post.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.get("/jobs")
def jobs():
    """
    ---
    tags:
      - Jobs
    parameters:
      - name: page
        in: query
        type: integer
      - name: page_size
        in: query
        type: integer
      - name: search
        in: query
        type: string
      - name: location
        in: query
        type: string
      - name: sort
        in: query
        type: string
      - name: order
        in: query
        type: string
    responses:
      200:
        description: Paginated processed jobs
    """
    payload = get_jobs(
        search=request.args.get("search", type=str),
        location=request.args.get("location", type=str),
        sort=request.args.get("sort", default="id", type=str),
        order=_get_sort_direction(),
        page=_get_positive_int_arg("page", 1),
        page_size=_get_positive_int_arg("page_size", 20),
        paginated=True,
    )
    return jsonify(payload), 200

@app.get("/jobs/<id>")
def job(id):
    """
    ---
    tags:
      - Jobs
    parameters:
      - name: id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Single processed job
      404:
        description: Not found
    """
    try:
        job = get_job(id)
        return jsonify(job.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.get("/search-terms")
def search_terms():
    """
    ---
    tags:
      - Search terms
    parameters:
      - name: page
        in: query
        type: integer
      - name: page_size
        in: query
        type: integer
      - name: search
        in: query
        type: string
      - name: status
        in: query
        type: string
      - name: include_inactive
        in: query
        type: boolean
    responses:
      200:
        description: Paginated search terms
    """
    include_inactive = request.args.get("include_inactive", "").lower() in {"1", "true", "yes"}
    payload = get_search_terms(
        include_inactive=include_inactive,
        search=request.args.get("search", type=str),
        status=request.args.get("status", type=str),
        page=_get_positive_int_arg("page", 1),
        page_size=_get_positive_int_arg("page_size", 20),
        paginated=True,
    )
    return jsonify(payload), 200

@app.post("/search-terms")
def create_search_term_route():
    """
    ---
    tags:
      - Search terms
    responses:
      201:
        description: Search term created
    """
    term_str = request.json["term"]
    new_term = add_search_term(term_str)
    return jsonify(new_term.to_dict()), 201

@app.put("/search-terms/<id>")
def deactive_search_term(id):
    """
    ---
    tags:
      - Search terms
    responses:
      200:
        description: Search term updated
      400:
        description: Invalid request
      404:
        description: Search term not found
    """
    try:
        payload = request.get_json(silent=True) or {}
        if "is_active" not in payload:
            return jsonify({"error": "is_active is required"}), 400
        term = update_search_term(id, is_active=bool(payload["is_active"]))
        return jsonify(term.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.delete("/search-terms/<id>")
def delete_search_term_route(id):
    """
    ---
    tags:
      - Search terms
    responses:
      200:
        description: Search term deleted
      404:
        description: Search term not found
    """
    try:
        remove_search_term(id)
        return jsonify({"message": f"Search term {id} deleted"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.post("/regex-extract")
def extract():
    """
    ---
    tags:
      - Jobs
    responses:
      202:
        description: Feature extraction started
    """
    start_extractor_thread()
    return jsonify({"message": "Features extraction started"}), 202

@app.get("/regex-extract/status")
def extract_status():
    """
    ---
    tags:
      - Jobs
    responses:
      200:
        description: Feature extraction status
    """
    return jsonify(get_extractor_status()), 200


@app.post("/llm-extract")
def llm_extract():
    """
    ---
    tags:
      - Jobs
    responses:
      202:
        description: LLM extraction started
    """
    start_llm_extractor_thread()
    return jsonify({"message": "LLM extraction started"}), 202


@app.get("/llm-extract/status")
def llm_extract_status():
    """
    ---
    tags:
      - Jobs
    responses:
      200:
        description: LLM extraction status
    """
    return jsonify(get_extractor_status("llm")), 200


@app.get("/features/average-job-post-daily")
def average_job_post_daily():
    """
    ---
    tags:
      - Jobs
    responses:
      200:
        description: Average number of job posts per day
    """
    return jsonify(get_average_job_post_daily()), 200

@app.get("/features/top-technologies")
@app.get("/features/top-5-technologies")
def top_technologies():
    """
    ---
    tags:
      - Jobs
    responses:
      200:
        description: Top extracted technologies
    """
    technologies = get_top_technologies()
    return jsonify(technologies), 200

@app.get("/features/top-locations")
@app.get("/features/top-5-locations")
def top_locations():
    """
    ---
    tags:
      - Jobs
    responses:
      200:
        description: Top extracted locations
    """
    locations = get_top_locations()
    return jsonify(locations), 200

@app.get("/features/average-salary")
def average_salary():
    """
    ---
    tags:
      - Jobs
    responses:
      200:
        description: Average salary across processed jobs
    """
    return jsonify(get_average_salary()), 200

@app.get("/features/jobs-by-contract-type")
def jobs_by_contract_type():
    """
    ---
    tags:
      - Jobs
    responses:
      200:
        description: Jobs grouped by contract type
    """
    return jsonify(get_jobs_by_contract_type()), 200

@app.get("/features/jobs-by-seniority")
def jobs_by_seniority():
    """
    ---
    tags:
      - Jobs
    responses:
      200:
        description: Jobs grouped by seniority
    """
    return jsonify(get_jobs_by_seniority()), 200

@app.get("/features/technology-trends")
def technology_trends():
    """
    ---
    tags:
      - Jobs
    responses:
      200:
        description: Technology trend series
    """
    days = request.args.get("days", default=30, type=int)
    limit = request.args.get("limit", default=5, type=int)
    skill = request.args.get("skill", default="", type=str)
    return jsonify(get_technology_trends(days=days, limit=limit, skill=skill)), 200

@app.get("/job-posts/export")
def export_job_posts():
    """
    ---
    tags:
      - Job posts
    produces:
      - text/csv
    responses:
      200:
        description: CSV export for raw job posts
    """
    csv_data = export_job_posts_csv()
    return Response(csv_data.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=job_posts.csv"})

@app.get("/jobs/export")
def export_jobs():
    """
    ---
    tags:
      - Jobs
    produces:
      - text/csv
    responses:
      200:
        description: CSV export for processed jobs
    """
    csv_data = export_jobs_csv()
    return Response(csv_data.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=jobs.csv"})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
