import csv
import io
from database import SessionLocal
from entities import JobPost, Job

# Student: Created the initial structure with JobPostCSV() and JobCSV() functions
#          that queried the database and wrote CSV rows with column mappings.
# AI:      Refactored to use io.StringIO (in-memory buffer) instead of writing
#          to disk files, so Flask can stream the CSV directly as a download
#          response. Also fixed the Job CSV columns to resolve relationship names
#          (company, city, skills) instead of exporting raw foreign key IDs.

def export_job_posts_csv():
    # Student: Wrote the query, column headers, and row mapping logic.
    # AI:      Wrapped output in io.StringIO and added null-safe formatting
    #          (e.g. `or ""`, `.isoformat()` guards) to prevent CSV errors.
    db = SessionLocal()
    try:
        job_posts = db.query(JobPost).order_by(JobPost.published_date.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "company_id", "name", "description",
            "career_page_name", "career_page_url", "job_type",
            "published_date", "application_deadline",
            "is_remote_work", "city", "state", "country",
            "job_url", "workplace_type", "disabilities",
            "skills", "badges"
        ])
        for jp in job_posts:
            writer.writerow([
                jp.id, jp.company_id, jp.name, jp.description or "",
                jp.career_page_name or "", jp.career_page_url or "",
                jp.job_type or "",
                jp.published_date.isoformat() if jp.published_date else "",
                jp.application_deadline.isoformat() if jp.application_deadline else "",
                jp.is_remote_work if jp.is_remote_work is not None else "",
                jp.city or "", jp.state or "", jp.country or "",
                jp.job_url or "", jp.workplace_type or "",
                jp.disabilities if jp.disabilities is not None else "",
                jp.skills or "", jp.badges or "",
            ])

        output.seek(0)
        return output
    finally:
        db.close()


def export_jobs_csv():
    # Student: Created the initial function structure and database query.
    # AI:      Rewrote the column mapping to resolve ORM relationships
    #          (company.name, contract_type.name, city.name, etc.) and
    #          join skill lists into comma-separated strings for readability.
    db = SessionLocal()
    try:
        jobs = db.query(Job).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "job_title", "salary", "extractor_type",
            "company", "contract_type",
            "state", "city",
            "hard_skills", "soft_skills", "nice_to_have_skills",
            "tech_stack"
        ])
        for job in jobs:
            writer.writerow([
                job.id,
                job.job_title,
                job.salary or "",
                job.extractor_type,
                job.company.name if job.company else "",
                job.contract_type.name if job.contract_type else "",
                job.state.name if job.state else "",
                job.city.name if job.city else "",
                ", ".join(s.name for s in job.hard_skills),
                ", ".join(s.name for s in job.soft_skills),
                ", ".join(s.name for s in job.nice_to_have_skills),
                ", ".join(job.tech_stack) if job.tech_stack else "",
            ])

        output.seek(0)
        return output
    finally:
        db.close()

