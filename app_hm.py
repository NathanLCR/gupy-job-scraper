from services.search_terms_service_hm import get_search_terms
from services.extractor_service import regex_extractor
from flask import Flask, send_from_directory, jsonify, redirect, request
from services.scraper_service_hm import start_scrape_thread, get_scrape_status
from services.error_service import get_errors
from services.job_service_hm import get_jobs
from services.stats_service import get_stats
from services.jobs_post_service_hm import get_jobs_posts, get_job_post
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
    limit = request.args.get("limit", default=20, type=int)
    page = request.args.get("page", default=1, type=int)
    job_posts = get_jobs_posts(limit, page)
    return jsonify([job_post.to_dict() for job_post in job_posts]), 200

@app.get("/job-posts/<id>")
def job_post(id):
    job_post = get_job_post(id)
    return jsonify(job_post.to_dict()), 200

@app.get("/jobs")
def jobs():
    jobs = get_jobs()
    return jsonify([job.to_dict() for job in jobs]), 200

@app.get("/jobs/<id>")
def job(id):
    return jsonify(get_job(id)), 200

@app.get("/search-terms")
def search_terms():
    terms = get_search_terms()
    return jsonify([term.to_dict() for term in terms]), 200

@app.post("/search-terms")
def add_search_term():
    term = request.json["term"]
    term = add_search_term(term)
    return jsonify({"message": term.to_dict()}), 200

@app.put("/search-terms/<id>")
def deactive_search_term(id):
    term = remove_search_term(id)
    return jsonify({"message": f"Search term {term.to_dict()} has been deactivated"}), 200

@app.post("/regex-extract")
def extract():
    regex_extractor()
    return jsonify({"message": "Features extracted"}), 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)