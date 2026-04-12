from services.search_terms_service_hm import (
    get_search_terms,
    add_search_term,
    remove_search_term,
    update_search_term,
)
from services.extractor_service import start_extractor_thread, get_extractor_status
from flask import Flask, Response, send_from_directory, jsonify, redirect, request
from services.scraper_service_hm import start_scrape_thread, get_scrape_status
from services.error_service import get_errors
from services.job_service_hm import get_jobs, get_job
from services.stats_service import get_stats
from services.jobs_post_service_hm import get_jobs_posts, get_job_post
from services.features_service_hm import get_average_job_post_daily, get_top_locations, get_top_technologies, get_average_salary, get_jobs_by_contract_type, get_jobs_by_seniority
from services.csv_service import export_job_posts_csv, export_jobs_csv
app = Flask(__name__)

@app.route("/")
def index():
    return redirect("/dashboard")

@app.route("/dashboard")
def dashboard():
    return send_from_directory('frontend', 'index.html')

@app.route("/frontend/<path:path>")
def frontend_static(path):
    return send_from_directory('frontend', path)

@app.post("/scrape/start")
def start_scrape():
    start_scrape_thread()
    return jsonify({"message": "Scrape started", "mode": "incremental"}), 202

@app.get("/health")
def health() -> tuple:
    return jsonify({"status": "ok"}), 200

@app.get("/scrape/status")
def scrape_status():
    return jsonify(get_scrape_status()), 200

@app.get("/errors")
def errors():
    return jsonify(get_errors()), 200

@app.get("/stats")
def stats():
    return jsonify(get_stats()), 200

@app.get("/job-posts")
def jobs_posts():
    job_posts = get_jobs_posts()
    return jsonify([job_post.to_dict() for job_post in job_posts]), 200

@app.get("/job-posts/<id>")
def job_post(id):
    try:
        job_post = get_job_post(id)
        return jsonify(job_post.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.get("/jobs")
def jobs():
    jobs = get_jobs()
    return jsonify([job.to_dict() for job in jobs]), 200

@app.get("/jobs/<id>")
def job(id):
    try:
        job = get_job(id)
        return jsonify(job.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.get("/search-terms")
def search_terms():
    terms = get_search_terms(include_inactive=include_inactive)
    return jsonify([term.to_dict() for term in terms]), 200

@app.post("/search-terms")
def create_search_term_route():
    term_str = request.json["term"]
    new_term = add_search_term(term_str)
    return jsonify(new_term.to_dict()), 201

@app.put("/search-terms/<id>")
def deactive_search_term(id):
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
    try:
        remove_search_term(id)
        return jsonify({"message": f"Search term {id} deleted"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.post("/regex-extract")
def extract():
    start_extractor_thread()
    return jsonify({"message": "Features extraction started"}), 202

@app.get("/regex-extract/status")
def extract_status():
    return jsonify(get_extractor_status()), 200


@app.get("/features/average-job-post-daily")
def average_job_post_daily():
    return jsonify(get_average_job_post_daily()), 200

@app.get("/features/top-technologies")
@app.get("/features/top-5-technologies")
def top_technologies():
    technologies = get_top_technologies()
    return jsonify(technologies), 200

@app.get("/features/top-locations")
@app.get("/features/top-5-locations")
def top_locations():
    locations = get_top_locations()
    return jsonify(locations), 200

@app.get("/features/average-salary")
def average_salary():
    return jsonify(get_average_salary()), 200

@app.get("/features/jobs-by-contract-type")
def jobs_by_contract_type():
    return jsonify(get_jobs_by_contract_type()), 200

@app.get("/features/jobs-by-seniority")
def jobs_by_seniority():
    return jsonify(get_jobs_by_seniority()), 200

@app.get("/job-posts/export")
def export_job_posts():
    csv_data = export_job_posts_csv()
    return Response(csv_data.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=job_posts.csv"})

@app.get("/jobs/export")
def export_jobs():
    csv_data = export_jobs_csv()
    return Response(csv_data.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=jobs.csv"})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
