# Scraper Service Pagination & Overlap Bug Fix

**Date:** April 12, 2026
**Target Files:**
- `services/scraper_service_hm.py`
- `services/jobs_post_service_hm.py`

## Issue 1: Bypassed Timestamp Update
In `scraper_service_hm.py`, a bug was causing the `last_scraped_at` timestamp to go un-updated for a specific search term if fewer than 20 new jobs were inserted on the first page of results.

```python
# Old Buggy Code
inserted += save_new_job_post(response['data'], last_scraped)
if check_if_all_save(inserted):
    continue # <-- This jumped to the next term instantly
```

This `continue` completely bypassed the `update_last_scraped_at(search_term.id)` call at the bottom of the structure. Consequently, on the next scraper run, the same old timestamp was used, leading to redundant queries. 

**Fix Applied:** Removed the `continue` statement and restructured the conditional block so that `update_last_scraped_at(search_term.id)` is always reached after exploring the relevant pages.

## Issue 2: Cross-term Pagination Abort
When the scraper retrieved jobs, it looped through multiple search terms. If it encountered a job for "Term B" that had already been successfully scraped by "Term A", `jobs_post_service_hm.py` correctly skipped it to prevent SQL duplication via an ID check. 

However, because the duplicate was ignored, the total `inserted` count for that batch dropped below the `LIMIT` of 20. The `scraper_service_hm.py` interpreted any batch with fewer than 20 inserted records as "we hit the end of the new jobs." This caused the scraper to prematurely abort pagination, missing any older (but entirely valid) jobs on subsequent pages for Term B.

**Fix Applied:**
1. Modified `save_new_job_post` inside `jobs_post_service_hm.py` to decouple "skipped due to duplicate existence" from "skipped due to reaching chronological limit." 
2. The function now returns a tuple `(inserted, reached_old)`. The `reached_old` flag only flips to `True` when a job's `publishedDate <= last_scraped_at`.
3. Erased the flawed `check_if_all_save` method from `scraper_service_hm.py`.
4. The scraper now strictly relies on `if reached_old: break` to cleanly halt pagination, completely sidestepping cross-term duplication pitfalls.
