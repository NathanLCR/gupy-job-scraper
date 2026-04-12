# Student: Created the original Flask app with Swagger documentation and inline DB queries.
# AI:      Refactored to use the modular service layer (matching app_hm.py), while
#          preserving the Swagger annotations for API documentation.

from flasgger import Swagger
from flask import Flask, Response, send_from_directory, jsonify, redirect, request
from database import init_db
from services.search_terms_service_hm import get_search_terms, add_search_term, remove_search_term
from services.extractor_service import start_extractor_thread, get_extractor_status
from services.scraper_service_hm import start_scrape_thread, get_scrape_status
from services.error_service import get_errors
from services.job_service_hm import get_jobs, get_job
from services.stats_service import get_stats
from services.jobs_post_service_hm import get_jobs_posts, get_job_post
from services.features_service_hm import get_average_job_post_daily, get_top_locations, get_top_technologies, get_average_salary, get_jobs_by_contract_type, get_jobs_by_seniority
from services.csv_service import export_job_posts_csv, export_jobs_csv
from swagger_config import SWAGGER_CONFIG, SWAGGER_TEMPLATE

app = Flask(__name__)
Swagger(app, template=SWAGGER_TEMPLATE, config=SWAGGER_CONFIG)

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
    """
    init_db()
    return jsonify({"message": "Database initialized"}), 200

@app.post("/scrape/start")
def start_scrape() -> tuple:
    """
    ---
    tags:
      - Scraper
    responses:
      202:
        description: Scrape job accepted
    """
    start_scrape_thread()
    return jsonify({"message": "Scrape started", "mode": "incremental"}), 202

@app.get("/scrape/status")
def scrape_status() -> tuple:
    """
    ---
    tags:
      - Scraper
    responses:
      200:
        description: Status payload
    """
    return jsonify(get_scrape_status()), 200

@app.get("/errors")
def errors() -> tuple:
    """
    ---
    tags:
      - Errors
    responses:
      200:
        description: Array of error log objects
    """
    return jsonify(get_errors()), 200

@app.get("/stats")
def stats() -> tuple:
    """
    ---
    tags:
      - Health
    responses:
      200:
        description: Metric counts
    """
    return jsonify(get_stats()), 200

@app.get("/job-posts")
def jobs_posts() -> tuple:
    """
    ---
    tags:
      - Job posts
    responses:
      200:
        description: Array of job post objects
    """
    job_posts = get_jobs_posts()
    return jsonify([job_post.to_dict() for job_post in job_posts]), 200

@app.get("/job-posts/<id>")
def job_post(id) -> tuple:
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
        description: Single job post object
      404:
        description: Not found
    """
    try:
        post = get_job_post(id)
        return jsonify(post.to_dict()), 200
    except ValueError:
        return jsonify({"error": "Job post not found"}), 404

@app.get("/job-posts/export")
def export_job_posts() -> tuple:
    """
    ---
    tags:
      - Job posts
    produces:
      - text/csv
    responses:
      200:
        description: CSV with all raw job posts
    """
    csv_data = export_job_posts_csv()
    return Response(csv_data.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=job_posts.csv"})

@app.get("/jobs")
def jobs() -> tuple:
    """
    ---
    tags:
      - Jobs
    responses:
      200:
        description: Array of processed job objects
    """
    jobs_list = get_jobs()
    return jsonify([job.to_dict() for job in jobs_list]), 200

@app.get("/jobs/<id>")
def job(id) -> tuple:
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
        description: Single processed job object
      404:
        description: Not found
    """
    try:
        job_obj = get_job(id)
        return jsonify(job_obj.to_dict()), 200
    except ValueError:
        return jsonify({"error": "Job not found"}), 404

@app.get("/jobs/export")
def export_jobs() -> tuple:
    """
    ---
    tags:
      - Jobs
    produces:
      - text/csv
    responses:
      200:
        description: CSV with all processed jobs
    """
    csv_data = export_jobs_csv()
    return Response(csv_data.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=jobs.csv"})

@app.get("/search-terms")
def search_terms() -> tuple:
    """
    ---
    tags:
      - Search terms
    responses:
      200:
        description: Array of search term objects
    """
    terms = get_search_terms()
    return jsonify([term.to_dict() for term in terms]), 200

@app.post("/search-terms")
def create_search_term_route() -> tuple:
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
    """
    term_str = request.json["term"]
    new_term = add_search_term(term_str)
    return jsonify(new_term.to_dict()), 201

@app.put("/search-terms/<id>")
def deactive_search_term(id) -> tuple:
    """
    ---
    tags:
      - Search terms
    parameters:
      - name: id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Term deactivated
    """
    term = remove_search_term(id)
    return jsonify({"message": f"Search term {term.to_dict()} has been deactivated"}), 200

@app.post("/regex-extract")
def extract_features() -> tuple:
    """
    ---
    tags:
      - Extractor
    responses:
      202:
        description: Feature extraction started in background
    """
    start_extractor_thread()
    return jsonify({"message": "Features extraction started"}), 202

@app.get("/regex-extract/status")
def extract_status() -> tuple:
    """
    ---
    tags:
      - Extractor
    responses:
      200:
        description: Extractor status
    """
    return jsonify(get_extractor_status()), 200

@app.get("/features/average-job-post-daily")
def average_job_post_daily() -> tuple:
    """
    ---
    tags:
      - Features
    responses:
      200:
        description: Average daily job posts count
    """
    return jsonify(get_average_job_post_daily()), 200

@app.get("/features/top-5-technologies")
def top_5_technologies() -> tuple:
    """
    ---
    tags:
      - Features
    responses:
      200:
        description: Top technologies by job count
    """
    return jsonify(get_top_technologies()), 200

@app.get("/features/top-5-locations")
def top_5_locations() -> tuple:
    """
    ---
    tags:
      - Features
    responses:
      200:
        description: Top locations by job count
    """
    return jsonify(get_top_locations()), 200

@app.get("/features/average-salary")
def average_salary() -> tuple:
    """
    ---
    tags:
      - Features
    responses:
      200:
        description: Average salary across all jobs
    """
    return jsonify(get_average_salary()), 200

@app.get("/features/jobs-by-contract-type")
def jobs_by_contract_type() -> tuple:
    """
    ---
    tags:
      - Features
    responses:
      200:
        description: Job count grouped by contract type
    """
    return jsonify(get_jobs_by_contract_type()), 200

@app.get("/features/jobs-by-seniority")
def jobs_by_seniority() -> tuple:
    """
    ---
    tags:
      - Features
    responses:
      200:
        description: Job count grouped by seniority
    """
    return jsonify(get_jobs_by_seniority()), 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
