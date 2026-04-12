# Codex Keyword Trend Chat Log

## 2026-04-12

### User

`how could we do a technology trend analysis`

### Assistant

The cleanest way in your project is to use the data you already have: `jobs_posts.published_date` for time, and `hard_skills` linked to each processed `job`.

Idea:

- Track how often a technology appears over time, like Python jobs per week, React jobs per week, or AWS jobs per week.
- This gives you a trend chart instead of only a static top-technologies snapshot.

Implementation approach:

- Add a service function in `services/features_service_hm.py`.
- Join `Job`, `job_hard_skills`, `HardSkill`, and `JobPost`.
- Group by date bucket plus skill name.
- Return JSON shaped for a frontend chart.

Good first version:

- Limit to the last 30 days.
- Start with the top 5 technologies.
- Group by day.

Suggested endpoint:

- `GET /features/technology-trends?days=30&limit=5`
- Optional filtered version:
  - `GET /features/technology-trends?days=30&limit=1&skill=Python`

Frontend idea:

- Add a line chart in the dashboard.
- Optionally add a search box so the user can request a time series for one specific technology.

Why it is valuable:

- It adds temporal analysis.
- It is more analytical than a simple count table.
- It gives you a strong talking point for the report and presentation.

### User

`can you dump the chat in codex_keyword_trend`

### Assistant

I’m logging the keyword-trend discussion in this file from this prompt onward. I’m assuming `codex_keyword_trend` means a markdown file named `codex_keyword_trend.md` in the project root.
