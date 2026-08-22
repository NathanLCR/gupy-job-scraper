// SkillPulse — Public Client Controller
// Single Page Application (SPA) for Candidate Intelligence & Market Explorer

function getApiBaseUrl() {
    const raw = (window.API_BASE_URL || '').trim();
    return raw.replace(/\/+$/, '');
}

function buildApiUrl(endpoint) {
    const base = getApiBaseUrl();
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    return base ? `${base}${cleanEndpoint}` : cleanEndpoint;
}

function logPublicApiFailure(view, endpoint, category, status) {
    console.warn(`event=public_api_failure view=${view} endpoint=${endpoint} category=${category} status=${status !== null && status !== undefined ? status : 'null'}`);
}

async function fetchApiJson(endpoint, options = {}, view = 'general') {
    const url = buildApiUrl(endpoint);
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeoutMs = options.timeoutMs || 10000;
    let timeoutId = null;
    if (controller) {
        timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    }

    const fetchOptions = {
        ...options,
        redirect: 'error',
        signal: options.signal || (controller ? controller.signal : undefined),
    };

    let response;
    try {
        response = await fetch(url, fetchOptions);
    } catch (err) {
        if (timeoutId) clearTimeout(timeoutId);
        const category = err.name === 'AbortError' ? 'timeout' : 'network';
        logPublicApiFailure(view, endpoint, category, null);
        throw err;
    }
    if (timeoutId) clearTimeout(timeoutId);

    if (!response.ok) {
        logPublicApiFailure(view, endpoint, 'http', response.status);
        throw new Error(`Server returned HTTP ${response.status}`);
    }

    const contentType = response.headers?.get?.('content-type')?.toLowerCase() || '';
    if (!contentType.includes('application/json')) {
        logPublicApiFailure(view, endpoint, 'content_type', response.status);
        throw new Error(`Expected JSON from the API, received ${contentType || 'an unknown content type'}`);
    }

    let data;
    try {
        data = await response.json();
    } catch (err) {
        logPublicApiFailure(view, endpoint, 'schema', response.status);
        throw err;
    }

    return data;
}

function liveDataUnavailableMarkup(detail) {
    return `
        <div class="data-unavailable-state" role="alert">
            <strong>⚠ Live data unavailable right now.</strong>
            <span>${escapeHtml(detail)}</span>
            <a href="/match">Try a sample profile instead →</a>
        </div>
    `;
}

// DOM References
const navTabs = document.querySelectorAll('.nav-tab-btn');
const views = document.querySelectorAll('.view');

// Data Caches
let cachedExplorerJobs = [];
let cachedMatchedJobs = [];
let currentPersona = null;

// Benchmark Candidate Profiles for 1-Click Demos
const DEMO_PERSONAS = {
    backend: {
        name: "Backend Software Engineer",
        headline: "Backend / Platform Engineering",
        seniority: "Pleno",
        region: "Europe",
        text: "Backend Software Engineer with 4+ years developing scalable Python and FastAPI services. Experienced with PostgreSQL database optimization, Redis caching, Docker containerization, Celery asynchronous background tasks, and RESTful API architecture. Familiar with microservices, CI/CD pipelines, and relational schema design."
    },
    ai: {
        name: "Junior AI / ML Engineer",
        headline: "AI & Machine Learning Engineering",
        seniority: "Júnior",
        region: "Europe",
        text: "Machine Learning & AI Engineer with 2 years of practical experience building LLM applications, RAG pipelines, and semantic search workflows. Proficient in Python, PyTorch, Hugging Face Transformers, LangChain, pgvector, and FastAPI. Strong foundation in data preprocessing with Pandas and NumPy."
    },
    fullstack: {
        name: "Full-stack Developer",
        headline: "Full-stack Web Engineering",
        seniority: "Pleno",
        region: "Europe",
        text: "Full-stack Developer with 3+ years building responsive web applications with TypeScript, React, Next.js, Node.js, and PostgreSQL. Experienced in designing REST and GraphQL APIs, writing clean modular CSS with Tailwind, and deploying containerized applications with Docker."
    },
    cloud: {
        name: "Senior Cloud Architect",
        headline: "Cloud & Infrastructure Architecture",
        seniority: "Sênior",
        region: "Europe",
        text: "Senior Cloud & Infrastructure Architect with 6+ years building distributed cloud platforms using Kubernetes, AWS (EKS, RDS, S3, IAM), Terraform infrastructure-as-code, Docker, Go, and Linux systems. Deep background in CI/CD pipeline automation, observability with Prometheus/Grafana, and microservices security."
    }
};

// ==================== Initialization ====================
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initCandidateMatcher();
    initJobExplorer();
    initDrawerKeyboardListener();

    // Resolve initial route from URL pathname
    handleInitialRoute();
    fetchMarketMetrics();
});

// ==================== Navigation & Router ====================
function initNavigation() {
    const brandLink = document.getElementById('brand-link');
    if (brandLink) {
        brandLink.addEventListener('click', (e) => {
            e.preventDefault();
            switchPublicView('matcher-view', '/match');
        });
    }

    navTabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = tab.getAttribute('data-target');
            const targetPath = tab.getAttribute('data-path') || '/';
            switchPublicView(targetId, targetPath);
        });
    });

    window.addEventListener('popstate', () => {
        handleInitialRoute();
    });
}

function handleInitialRoute() {
    const path = window.location.pathname.toLowerCase();
    if (path.startsWith('/jobs')) {
        switchPublicView('explorer-view', '/jobs', false);
    } else if (path.startsWith('/market')) {
        switchPublicView('dashboard-view', '/market', false);
    } else if (path.startsWith('/how-it-works')) {
        switchPublicView('architecture-view', '/how-it-works', false);
    } else {
        switchPublicView('matcher-view', '/match', false);
    }
}

window.switchPublicView = function(targetId, targetPath = null, updateHistory = true) {
    navTabs.forEach(tab => {
        const isMatch = tab.getAttribute('data-target') === targetId;
        tab.classList.toggle('active', isMatch);
        if (isMatch) {
            tab.setAttribute('aria-current', 'page');
        } else {
            tab.removeAttribute('aria-current');
        }
    });

    views.forEach(view => {
        view.classList.toggle('active', view.id === targetId);
    });

    if (updateHistory && targetPath && window.location.pathname !== targetPath) {
        window.history.pushState({ targetId }, '', targetPath);
    }

    if (targetId === 'explorer-view' && cachedExplorerJobs.length === 0) {
        runJobExplorer();
    }
    if (targetId === 'dashboard-view') {
        fetchMarketMetrics();
    }
};

function announceLive(message) {
    const announcer = document.getElementById('live-announcer');
    if (announcer) {
        announcer.textContent = '';
        setTimeout(() => {
            announcer.textContent = message;
        }, 50);
    }
}

// ==================== Contract Validation Helpers ====================
function validateJobListResponse(data) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return false;
    if (!Array.isArray(data.items)) return false;
    const p = data.pagination;
    if (!p || typeof p !== 'object') return false;
    if (typeof p.page !== 'number' || typeof p.page_size !== 'number') return false;
    if (typeof p.total_items !== 'number' || typeof p.total_pages !== 'number') return false;
    if (typeof p.has_next !== 'boolean' || typeof p.has_prev !== 'boolean') return false;
    return true;
}

function validateCandidateMatchResponse(data) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return false;
    if (!Array.isArray(data.matches)) return false;
    if (typeof data.total_evaluated !== 'number' || typeof data.total_matches !== 'number') return false;
    if (!data.extracted_skills || typeof data.extracted_skills !== 'object') return false;
    for (const m of data.matches) {
        if (!m || typeof m !== 'object') return false;
        if (typeof m.job_id !== 'number' || typeof m.job_title !== 'string') return false;
        if (typeof m.fit_score !== 'number') return false;
        if (typeof m.hard_points !== 'number' || typeof m.soft_points !== 'number') return false;
        if (typeof m.vector_points !== 'number' || typeof m.total_points !== 'number') return false;
        if (!m.gap_analysis || typeof m.gap_analysis !== 'object') return false;
    }
    return true;
}

function validateSkillAnalyticsResponse(data) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return false;
    if (typeof data.total_jobs !== 'number' || typeof data.distinct_skills !== 'number') return false;
    if (typeof data.distinct_companies !== 'number' || typeof data.markets_tracked !== 'number') return false;
    if (!Array.isArray(data.top_skills) || !Array.isArray(data.top_locations)) return false;
    if (!Array.isArray(data.salary_by_seniority) || !Array.isArray(data.workplace_distribution)) return false;
    for (const s of data.top_skills) {
        if (!s || typeof s !== 'object' || typeof s.name !== 'string' || typeof s.percentage !== 'number') return false;
    }
    for (const l of data.top_locations) {
        if (!l || typeof l !== 'object' || typeof (l.name || l.location) !== 'string' || typeof l.percentage !== 'number') return false;
    }
    for (const sen of data.salary_by_seniority) {
        if (!sen || typeof sen !== 'object' || typeof (sen.name || sen.seniority) !== 'string' || typeof sen.percentage !== 'number') return false;
    }
    for (const w of data.workplace_distribution) {
        if (!w || typeof w !== 'object' || typeof w.name !== 'string' || typeof w.percentage !== 'number') return false;
    }
    return true;
}

// ==================== 1. Candidate Matcher ====================
function clearProfileValidation(textarea) {
    const error = document.getElementById('matcher-resume-error');
    if (textarea) {
        textarea.removeAttribute('aria-invalid');
        textarea.removeAttribute('aria-describedby');
    }
    if (error) {
        error.textContent = '';
        error.setAttribute('hidden', 'true');
    }
}

function showProfileValidation(textarea) {
    const error = document.getElementById('matcher-resume-error');
    if (!textarea || !error) return;
    error.textContent = 'Please paste your profile text or choose a sample profile.';
    error.removeAttribute('hidden');
    textarea.setAttribute('aria-invalid', 'true');
    textarea.setAttribute('aria-describedby', 'matcher-resume-error');
    textarea.focus();
}

function initCandidateMatcher() {
    const btnRun = document.getElementById('btn-run-match');
    const btnClear = document.getElementById('btn-clear-resume');
    const textarea = document.getElementById('matcher-resume-input');

    // Preset Chip Click Handlers (Input-only affordance: populates form without claiming match result)
    const personaMap = {
        'btn-persona-backend': 'backend',
        'btn-persona-ai': 'ai',
        'btn-persona-fullstack': 'fullstack',
        'btn-persona-cloud': 'cloud'
    };

    const presetButtons = Object.keys(personaMap).map(id => document.getElementById(id)).filter(Boolean);

    function resetPresetStates() {
        presetButtons.forEach(btn => {
            btn.classList.remove('active');
            btn.setAttribute('aria-pressed', 'false');
        });
    }

    Object.entries(personaMap).forEach(([btnId, key]) => {
        const el = document.getElementById(btnId);
        if (el) {
            el.addEventListener('click', () => {
                resetPresetStates();
                el.classList.add('active');
                el.setAttribute('aria-pressed', 'true');

                const p = DEMO_PERSONAS[key];
                if (textarea) {
                    textarea.value = p.text;
                    clearProfileValidation(textarea);
                }
                currentPersona = p;

                const regSelect = document.getElementById('matcher-region-select');
                const senSelect = document.getElementById('matcher-seniority-select');
                if (regSelect && p.region) regSelect.value = p.region;
                if (senSelect && p.seniority) senSelect.value = p.seniority;
            });
        }
    });

    if (textarea) {
        textarea.addEventListener('input', () => {
            resetPresetStates();
            currentPersona = null;
            clearProfileValidation(textarea);
        });
    }

    if (btnRun) {
        btnRun.addEventListener('click', () => runCandidateMatch());
    }

    if (btnClear) {
        btnClear.addEventListener('click', () => {
            if (textarea) {
                textarea.value = '';
                clearProfileValidation(textarea);
                textarea.focus();
            }
            resetPresetStates();
            currentPersona = null;
            cachedMatchedJobs = [];
            const resSection = document.getElementById('matcher-results-section');
            const emptyEl = document.getElementById('matcher-empty-state');
            if (resSection) resSection.style.display = 'none';
            if (emptyEl) {
                emptyEl.style.display = 'block';
                emptyEl.innerHTML = `
                    <div class="empty-state-icon" aria-hidden="true"><i class='bx bx-user-pin'></i></div>
                    <div class="empty-state-title">No candidate profile loaded</div>
                    <div class="empty-state-subtitle">Paste a CV / profile text or click a sample profile above to see explainable matches.</div>
                `;
            }
        });
    }
}

async function runCandidateMatch() {
    const textarea = document.getElementById('matcher-resume-input');
    const text = textarea ? textarea.value.trim() : '';

    if (!text) {
        showProfileValidation(textarea);
        return;
    }
    clearProfileValidation(textarea);

    const btnRun = document.getElementById('btn-run-match');
    if (btnRun) {
        btnRun.disabled = true;
        btnRun.innerHTML = `<span>Matching...</span> <i class='bx bx-loader-alt bx-spin'></i>`;
    }

    const region = document.getElementById('matcher-region-select')?.value || null;
    const seniority = document.getElementById('matcher-seniority-select')?.value || null;

    try {
        const data = await fetchApiJson('/api/v1/match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                resume_text: text,
                target_region: region,
                seniority: seniority,
                limit: 8,
                min_fit_score: 0.0
            })
        }, 'match');

        if (!validateCandidateMatchResponse(data)) {
            logPublicApiFailure('match', '/api/v1/match', 'schema', 200);
            renderMatchUnavailable();
            return;
        }

        renderMatchResults(data);

    } catch (err) {
        renderMatchUnavailable();
    } finally {
        if (btnRun) {
            btnRun.disabled = false;
            btnRun.innerHTML = `<span>Find my matches</span> <i class='bx bx-right-arrow-alt'></i>`;
        }
    }
}

function renderMatchResults(data) {
    const emptyEl = document.getElementById('matcher-empty-state');
    if (emptyEl) emptyEl.style.display = 'none';
    const resultsSection = document.getElementById('matcher-results-section');
    if (!resultsSection) return;
    resultsSection.style.display = 'block';

    // 1. Overall Score & Headline
    const headline = currentPersona ? currentPersona.headline : "Candidate Profile";
    const headlineEl = document.getElementById('res-candidate-headline');
    if (headlineEl) headlineEl.textContent = headline;

    const matches = data.matches || [];
    cachedMatchedJobs = matches;

    if (matches.length === 0) {
        const scoreEl = document.getElementById('gauge-score-text');
        if (scoreEl) scoreEl.textContent = "0%";
        const badge = document.getElementById('matcher-matches-badge');
        if (badge) badge.textContent = "0 roles matched";
        const tierBadge = document.getElementById('res-fit-tier');
        if (tierBadge) {
            tierBadge.textContent = "No Matches";
            tierBadge.style.color = "var(--text-muted)";
            tierBadge.style.backgroundColor = "var(--surface-raised)";
            tierBadge.style.borderColor = "var(--border)";
        }
        renderRankedJobs([]);
        return;
    }

    const firstMatch = matches[0];
    const rawTopScore = typeof firstMatch.fit_score === 'number' ? firstMatch.fit_score : 0;
    const topScore = rawTopScore <= 1.0 ? Math.round(rawTopScore * 100) : Math.round(rawTopScore);
    const scoreEl = document.getElementById('gauge-score-text');
    if (scoreEl) scoreEl.textContent = `${topScore}%`;

    const tierBadge = document.getElementById('res-fit-tier');
    if (tierBadge) {
        if (topScore >= 80) {
            tierBadge.textContent = "Strong Fit";
            tierBadge.style.color = "var(--success)";
            tierBadge.style.backgroundColor = "var(--success-subtle)";
            tierBadge.style.borderColor = "var(--success-border)";
        } else if (topScore >= 60) {
            tierBadge.textContent = "Moderate Fit";
            tierBadge.style.color = "var(--accent-hover)";
            tierBadge.style.backgroundColor = "var(--accent-subtle)";
            tierBadge.style.borderColor = "var(--accent-border)";
        } else {
            tierBadge.textContent = "Emerging Fit";
            tierBadge.style.color = "var(--warning)";
            tierBadge.style.backgroundColor = "var(--warning-subtle)";
            tierBadge.style.borderColor = "var(--warning-border)";
        }
    }

    const badge = document.getElementById('matcher-matches-badge');
    if (badge) badge.textContent = `${matches.length} target roles matched`;

    const summaryEl = document.getElementById('res-fit-summary-text');
    if (summaryEl) {
        summaryEl.textContent = `Top alignment · ${topScore}% match · Evaluated against active market vacancies.`;
    }

    // 2. Score Decomposition (Exact server points from JobMatchItem)
    const hardPts = typeof firstMatch.hard_points === 'number' ? firstMatch.hard_points : 0;
    const expPts = typeof firstMatch.soft_points === 'number' ? firstMatch.soft_points : 0;
    const vecPts = typeof firstMatch.vector_points === 'number' ? firstMatch.vector_points : 0;
    const totalPts = typeof firstMatch.total_points === 'number' ? firstMatch.total_points : topScore;

    const explainHard = document.getElementById('explain-hard-pts');
    if (explainHard) explainHard.textContent = `${hardPts.toFixed(1)} / 50`;
    const barHard = document.getElementById('bar-hard-pts');
    if (barHard) barHard.style.width = `${Math.min(100, Math.max(0, (hardPts / 50) * 100))}%`;

    const explainSoft = document.getElementById('explain-soft-pts');
    if (explainSoft) explainSoft.textContent = `${expPts.toFixed(1)} / 20`;
    const barSoft = document.getElementById('bar-soft-pts');
    if (barSoft) barSoft.style.width = `${Math.min(100, Math.max(0, (expPts / 20) * 100))}%`;

    const explainVec = document.getElementById('explain-vec-pts');
    if (explainVec) explainVec.textContent = `${vecPts.toFixed(1)} / 30`;
    const barVec = document.getElementById('bar-vec-pts');
    if (barVec) barVec.style.width = `${Math.min(100, Math.max(0, (vecPts / 30) * 100))}%`;

    const explainTotal = document.getElementById('explain-total-pts');
    if (explainTotal) explainTotal.textContent = `${totalPts.toFixed(1)} / 100`;

    // 3. Candidate Competencies
    const extractedHard = (data.extracted_skills && data.extracted_skills.hard_skills) || [];
    const compContainer = document.getElementById('res-domain-strengths');
    if (compContainer) {
        compContainer.innerHTML = extractedHard.length ? extractedHard.slice(0, 5).map(skill => `
            <div class="dist-item">
                <div class="dist-head">
                    <span class="dist-name">${escapeHtml(skill)}</span>
                    <span class="dist-pct" style="color: var(--success); font-weight: 600;">Verified</span>
                </div>
                <div class="point-bar-bg"><div class="point-bar-fill" style="width: 100%;"></div></div>
            </div>
        `).join('') : '<span class="text-muted">No hard skills were extracted from this profile.</span>';
    }

    // 4. Highest ROI Upskilling Skills
    const recContainer = document.getElementById('res-recommended-skills');
    const missingSkills = firstMatch.gap_analysis?.missing_hard_skills || [];
    if (recContainer) {
        recContainer.innerHTML = missingSkills.length ? missingSkills.map(s => `
            <span class="skill-roi-pill"><i class='bx bx-trending-up'></i> ${escapeHtml(s)}</span>
        `).join('') : '<span class="text-muted">No missing hard skills reported.</span>';
    }

    // 5. Render Ranked Matching Opportunities
    renderRankedJobs(matches);
    announceLive(`Matching complete. ${matches.length} matching vacancies found.`);
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderMatchUnavailable() {
    const resultsSection = document.getElementById('matcher-results-section');
    const emptyEl = document.getElementById('matcher-empty-state');
    cachedMatchedJobs = [];
    if (resultsSection) resultsSection.style.display = 'none';
    if (emptyEl) {
        emptyEl.style.display = 'block';
        emptyEl.innerHTML = liveDataUnavailableMarkup('Live matching is unavailable right now. Your profile was not scored.');
    }
}

function renderRankedJobs(jobs) {
    const listEl = document.getElementById('ranked-jobs-list');
    if (!listEl) return;

    if (!jobs || jobs.length === 0) {
        listEl.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-muted);">No matching opportunities found for this query.</div>`;
        return;
    }

    listEl.innerHTML = jobs.map((job, idx) => {
        const rawScore = typeof job.fit_score === 'number' ? job.fit_score : 0;
        const score = rawScore <= 1.0 ? Math.round(rawScore * 100) : Math.round(rawScore);
        const scoreClass = score >= 85 ? 'high' : (score >= 70 ? 'med' : '');
        const title = job.job_title || job.title || "Software Engineer";
        const company = job.company || job.company_name || "Company";
        const location = job.location || (job.city ? `${job.city}, ${job.state || ''}` : job.region) || "Europe";
        const skills = (job.gap_analysis?.matched_hard_skills || job.hard_skills || job.required_hard_skills || []).slice(0, 4);

        return `
            <div class="job-list-row" role="button" tabindex="0" aria-label="View job details for ${escapeHtml(title)} at ${escapeHtml(company)}" onclick="openJobDrawerFromData(${idx}, 'match')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openJobDrawerFromData(${idx}, 'match');}">
                <div class="job-row-main">
                    <div class="job-row-title-line">
                        <span class="job-row-title">${escapeHtml(title)}</span>
                        <span class="job-tag">${escapeHtml(job.workplace_type || "Remote")}</span>
                    </div>
                    <div class="job-row-meta">
                        <span>${escapeHtml(company)}</span>
                        <span>·</span>
                        <span>${escapeHtml(location)}</span>
                    </div>
                    <div class="job-row-skills">
                        ${skills.map(s => `<span class="skill-tag">${escapeHtml(s)}</span>`).join('')}
                    </div>
                </div>
                <div class="job-row-right">
                    <span class="job-match-pill ${scoreClass}">${score}% match</span>
                </div>
            </div>
        `;
    }).join('');
}

// ==================== 2. Job Explorer ====================
function initJobExplorer() {
    const btnSearch = document.getElementById('btn-run-explorer');
    const input = document.getElementById('explorer-query-input');
    const presetBtns = document.querySelectorAll('.preset-btn[data-query]');

    if (btnSearch) {
        btnSearch.addEventListener('click', () => runJobExplorer(input ? input.value : ''));
    }

    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                runJobExplorer(input.value);
            }
        });
    }

    presetBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            presetBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const q = btn.getAttribute('data-query');
            if (input) input.value = q;
            runJobExplorer(q);
        });
    });
}

async function runJobExplorer(query = "") {
    const listEl = document.getElementById('explorer-results-list');
    if (listEl) {
        listEl.innerHTML = `<div style="padding: 32px; text-align: center; color: var(--text-muted);"><i class='bx bx-loader-alt bx-spin' style="font-size: 20px;"></i><br>Retrieving matching vacancies...</div>`;
    }

    const region = document.getElementById('exp-filter-region')?.value || '';
    const workplace = document.getElementById('exp-filter-workplace')?.value || '';
    const seniority = document.getElementById('exp-filter-seniority')?.value || '';

    try {
        let endpoint = `/api/v1/jobs?page=1&page_size=25`;
        if (query && query.trim()) {
            endpoint += `&search=${encodeURIComponent(query.trim())}`;
        }
        if (region) {
            endpoint += `&region=${encodeURIComponent(region)}`;
        }
        if (workplace) {
            endpoint += `&workplace_type=${encodeURIComponent(workplace)}`;
        }
        if (seniority) {
            endpoint += `&seniority=${encodeURIComponent(seniority)}`;
        }

        const data = await fetchApiJson(endpoint, {}, 'jobs');

        // Spec 07: Validate exact JobListResponse contract
        if (!validateJobListResponse(data)) {
            logPublicApiFailure('jobs', endpoint, 'schema', 200);
            renderExplorerUnavailable();
            return;
        }

        const jobs = data.items;
        cachedExplorerJobs = jobs;

        const countEl = document.getElementById('explorer-results-count');
        const pillEl = document.getElementById('explorer-jobs-total-pill');

        if (jobs.length === 0) {
            if (countEl) countEl.textContent = '0 Vacancies Found';
            if (pillEl) pillEl.textContent = '0 roles';
            if (listEl) {
                listEl.innerHTML = `<div style="padding: 32px; text-align: center; color: var(--text-muted);">No vacancies matched these filters.</div>`;
            }
            return;
        }

        const totalItems = data.pagination.total_items;
        if (countEl) countEl.textContent = `${totalItems} Vacancies Found`;
        if (pillEl) pillEl.textContent = `${Number(totalItems).toLocaleString()} roles`;

        renderExplorerJobs(jobs);
        announceLive(`Loaded ${jobs.length} vacancies.`);

    } catch (err) {
        renderExplorerUnavailable();
    }
}

function renderExplorerJobs(jobs) {
    const listEl = document.getElementById('explorer-results-list');
    if (!listEl) return;

    if (!jobs || jobs.length === 0) {
        listEl.innerHTML = `<div style="padding: 32px; text-align: center; color: var(--text-muted);">No vacancies matched these filters.</div>`;
        return;
    }

    listEl.innerHTML = jobs.map((job, idx) => {
        const title = job.job_title || job.title || "Software Engineer";
        const company = job.company || job.company_name || "Company";
        const location = job.city ? (job.state ? `${job.city}, ${job.state}` : job.city) : (job.location || job.region || "Global");
        const skills = (job.hard_skills || job.required_hard_skills || job.tech_stack || []).slice(0, 4);
        const workplace = job.workplace_type || "Remote";

        return `
            <div class="job-list-row" role="button" tabindex="0" aria-label="View job details for ${escapeHtml(title)} at ${escapeHtml(company)}" onclick="openJobDrawerFromData(${idx}, 'explorer')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openJobDrawerFromData(${idx}, 'explorer');}">
                <div class="job-row-main">
                    <div class="job-row-title-line">
                        <span class="job-row-title">${escapeHtml(title)}</span>
                        <span class="job-tag">${escapeHtml(workplace)}</span>
                    </div>
                    <div class="job-row-meta">
                        <span>${escapeHtml(company)}</span>
                        <span>·</span>
                        <span>${escapeHtml(location)}</span>
                    </div>
                    <div class="job-row-skills">
                        ${skills.map(s => `<span class="skill-tag">${escapeHtml(s)}</span>`).join('')}
                    </div>
                </div>
                <div class="job-row-right">
                    <i class='bx bx-chevron-right' aria-hidden="true" style="font-size: 18px; color: var(--text-muted);"></i>
                </div>
            </div>
        `;
    }).join('');
}

function renderExplorerUnavailable() {
    cachedExplorerJobs = [];
    const listEl = document.getElementById('explorer-results-list');
    if (listEl) {
        listEl.innerHTML = liveDataUnavailableMarkup('Live data unavailable right now. No cached vacancies are being shown.');
    }
    const countEl = document.getElementById('explorer-results-count');
    if (countEl) countEl.textContent = 'Unavailable';
    const pillEl = document.getElementById('explorer-jobs-total-pill');
    if (pillEl) pillEl.textContent = 'Unavailable';
}

// ==================== 3. Market Insights ====================
async function fetchMarketMetrics() {
    try {
        const data = await fetchApiJson('/api/v1/analytics/overview', {}, 'market');
        if (!validateSkillAnalyticsResponse(data)) {
            logPublicApiFailure('market', '/api/v1/analytics/overview', 'schema', 200);
            renderMarketUnavailable();
            return;
        }
        renderSkillAnalytics(data);
    } catch (e) {
        renderMarketUnavailable();
    }
}

function renderSkillAnalytics(data) {
    const totalJobs = data.total_jobs;
    const marketsCount = data.markets_tracked;
    const skillsCount = data.distinct_skills;
    const topSkills = data.top_skills || [];

    const bannerEl = document.getElementById('market-status-banner');
    if (bannerEl) bannerEl.innerHTML = '';

    const countEl = document.getElementById('metric-jobs-count');
    if (countEl) countEl.textContent = Number(totalJobs).toLocaleString();

    const pillEl = document.getElementById('explorer-jobs-total-pill');
    if (pillEl && (pillEl.textContent === 'Unavailable' || pillEl.textContent.includes('--'))) {
        pillEl.textContent = `${Number(totalJobs).toLocaleString()} roles`;
    }

    const marketsEl = document.getElementById('metric-markets-count');
    if (marketsEl) marketsEl.textContent = String(marketsCount);

    const skillsEl = document.getElementById('metric-skills-count');
    if (skillsEl) skillsEl.textContent = `${Number(skillsCount).toLocaleString()}+`;

    const topTechEl = document.getElementById('metric-top-tech');
    if (topTechEl && topSkills.length > 0) {
        topTechEl.textContent = `${topSkills[0].name} (${Math.round(topSkills[0].percentage)}%)`;
    } else if (topTechEl) {
        topTechEl.textContent = 'None';
    }

    const statusEl = document.getElementById('market-status-text');
    if (statusEl) {
        statusEl.textContent = 'Data updated recently · ESCO & O*NET taxonomy';
    }

    // 1. Technologies distribution list
    const listEl = document.getElementById('top-technologies-list');
    if (listEl) {
        listEl.innerHTML = topSkills.length > 0 ? topSkills.slice(0, 6).map((item, idx) => {
            const isTop = idx === 0;
            const skillName = item.name;
            const barFillClass = isTop ? 'point-bar-fill accent' : 'point-bar-fill';
            const pct = Math.round(item.percentage);
            return `
                <div class="dist-item">
                    <div class="dist-head">
                        <span class="dist-name">${escapeHtml(skillName)}</span>
                        <span class="dist-pct">${pct}%</span>
                    </div>
                    <div class="point-bar-bg"><div class="${barFillClass}" style="width: ${pct}%;"></div></div>
                </div>
            `;
        }).join('') : '<div class="text-center text-muted" style="padding: 20px;">No skill metrics recorded.</div>';
    }

    // 2. Seniority distribution list
    const senEl = document.getElementById('top-seniority-list');
    if (senEl) {
        const seniorityItems = (data.salary_by_seniority || []).slice(0, 5);
        const maxSenCount = Math.max(...seniorityItems.map(s => s.count || 1), 1);
        senEl.innerHTML = seniorityItems.length > 0 ? seniorityItems.map((item, idx) => {
            const pct = Math.round(item.percentage);
            const count = item.count || 1;
            const widthPct = Math.round((count / maxSenCount) * 100);
            const isTop = idx === 0;
            return `
                <div class="dist-item">
                    <div class="dist-head">
                        <span class="dist-name">${escapeHtml(item.name || item.seniority || "Level")}</span>
                        <span class="dist-pct">${pct}%</span>
                    </div>
                    <div class="point-bar-bg"><div class="${isTop ? 'point-bar-fill accent' : 'point-bar-fill'}" style="width: ${widthPct}%;"></div></div>
                </div>
            `;
        }).join('') : '<div class="text-center text-muted" style="padding: 20px;">No seniority metrics recorded.</div>';
    }

    // 3. Locations distribution list
    const locEl = document.getElementById('top-locations-list');
    if (locEl) {
        const locItems = (data.top_locations || []).slice(0, 5);
        const maxLocCount = Math.max(...locItems.map(l => l.count || 1), 1);
        locEl.innerHTML = locItems.length > 0 ? locItems.map((item, idx) => {
            const pct = Math.round(item.percentage);
            const count = item.count || 1;
            const widthPct = Math.round((count / maxLocCount) * 100);
            const isTop = idx === 0;
            return `
                <div class="dist-item">
                    <div class="dist-head">
                        <span class="dist-name">${escapeHtml(item.name || item.location || "Location")}</span>
                        <span class="dist-pct">${pct}%</span>
                    </div>
                    <div class="point-bar-bg"><div class="${isTop ? 'point-bar-fill accent' : 'point-bar-fill'}" style="width: ${widthPct}%;"></div></div>
                </div>
            `;
        }).join('') : '<div class="text-center text-muted" style="padding: 20px;">No location metrics recorded.</div>';
    }

    // 4. Workplace distribution list
    const wpEl = document.getElementById('workplace-distribution-list');
    if (wpEl) {
        const wpItems = data.workplace_distribution || [];
        wpEl.innerHTML = wpItems.length > 0 ? wpItems.map((item, idx) => {
            const isTop = idx === 0;
            const pct = Math.round(item.percentage);
            return `
                <div class="dist-item">
                    <div class="dist-head">
                        <span class="dist-name">${escapeHtml(item.name)}</span>
                        <span class="dist-pct" style="color: ${isTop ? 'var(--success)' : 'var(--text-secondary)'}; font-weight: 600;">${pct}%</span>
                    </div>
                    <div class="point-bar-bg"><div class="${isTop ? 'point-bar-fill accent' : 'point-bar-fill'}" style="width: ${pct}%;"></div></div>
                    <div class="metric-sub" style="margin-top: 2px;">${item.count ? `${item.count} vacancies` : ''}</div>
                </div>
            `;
        }).join('') : '<div class="text-center text-muted" style="padding: 20px;">No workplace mix recorded.</div>';
    }
}

function renderMarketUnavailable() {
    ['metric-jobs-count', 'metric-markets-count', 'metric-skills-count', 'metric-top-tech'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = 'Unavailable';
    });

    const pillEl = document.getElementById('explorer-jobs-total-pill');
    if (pillEl) pillEl.textContent = 'Unavailable';

    const bannerEl = document.getElementById('market-status-banner');
    if (bannerEl) {
        bannerEl.innerHTML = liveDataUnavailableMarkup('Market aggregates could not be loaded from the live API.');
    }

    ['top-technologies-list', 'top-seniority-list', 'top-locations-list', 'workplace-distribution-list'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="text-center text-muted" style="padding: 24px;">Market data unavailable</div>';
    });

    const statusEl = document.getElementById('market-status-text');
    if (statusEl) {
        statusEl.textContent = 'Update status unavailable';
    }
}

let lastDrawerOpener = null;

function clearJobDrawerContent() {
    [
        'drawer-job-title',
        'drawer-company',
        'drawer-location',
        'drawer-skills',
        'drawer-description',
        'drawer-published',
        'drawer-fit-score',
    ].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '';
    });

    const divider = document.getElementById('drawer-meta-divider');
    if (divider) divider.style.display = 'none';

    const workplace = document.getElementById('drawer-workplace');
    if (workplace) {
        workplace.textContent = '';
        workplace.style.display = 'none';
    }

    const fitSection = document.getElementById('drawer-fit-section');
    if (fitSection) fitSection.style.display = 'none';
    const fitBar = document.getElementById('drawer-fit-bar');
    if (fitBar) fitBar.style.width = '0%';
    const progressbar = document.getElementById('drawer-fit-progressbar');
    if (progressbar) progressbar.setAttribute('aria-valuenow', '0');

    const link = document.getElementById('drawer-apply-link');
    if (link) {
        link.removeAttribute('href');
        link.style.display = 'none';
        link.setAttribute('hidden', 'true');
    }
}

window.switchAnalyticsTab = function(tabName) {
    const tabs = ['tech', 'seniority', 'locations'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-btn-${t}`);
        const panel = document.getElementById(`analytics-tab-${t}`);
        const isSelected = t === tabName;
        if (btn) {
            btn.classList.toggle('active', isSelected);
            btn.setAttribute('aria-selected', isSelected ? 'true' : 'false');
            btn.setAttribute('tabindex', isSelected ? '0' : '-1');
            if (isSelected) btn.focus();
        }
        if (panel) {
            panel.style.display = isSelected ? 'block' : 'none';
        }
    });
};

function initAnalyticsTabsKeyboard() {
    const tablist = document.querySelector('[role="tablist"][aria-label="Market distribution categories"]');
    if (!tablist) return;

    const tabs = ['tech', 'seniority', 'locations'];
    tablist.addEventListener('keydown', (e) => {
        const activeTab = document.activeElement;
        if (!activeTab || !activeTab.id || !activeTab.id.startsWith('tab-btn-')) return;
        const currentKey = activeTab.id.replace('tab-btn-', '');
        let currentIndex = tabs.indexOf(currentKey);
        if (currentIndex === -1) return;

        let targetIndex = -1;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
            e.preventDefault();
            targetIndex = (currentIndex + 1) % tabs.length;
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
            e.preventDefault();
            targetIndex = (currentIndex - 1 + tabs.length) % tabs.length;
        } else if (e.key === 'Home') {
            e.preventDefault();
            targetIndex = 0;
        } else if (e.key === 'End') {
            e.preventDefault();
            targetIndex = tabs.length - 1;
        }

        if (targetIndex !== -1) {
            switchAnalyticsTab(tabs[targetIndex]);
        }
    });
}

// ==================== 4. Job Inspector Drawer ====================
window.openJobDrawerFromData = function(idx, source) {
    const list = source === 'match' ? cachedMatchedJobs : cachedExplorerJobs;
    if (!list || !list[idx]) return;
    const job = list[idx];

    // Store element that triggered the modal for focus restoration
    lastDrawerOpener = document.activeElement;
    clearJobDrawerContent();

    const title = job.job_title || job.title || "";
    const company = job.company || job.company_name || "";
    const location = job.city ? (job.state ? `${job.city}, ${job.state}` : job.city) : (job.location || job.region || "");
    const workplace = job.workplace_type || "";

    const titleEl = document.getElementById('drawer-job-title');
    if (titleEl) titleEl.textContent = title || "Job Details";

    const companyEl = document.getElementById('drawer-company');
    if (companyEl) companyEl.textContent = company;

    const locEl = document.getElementById('drawer-location');
    if (locEl) locEl.textContent = location;

    const dividerEl = document.getElementById('drawer-meta-divider');
    if (dividerEl) dividerEl.style.display = (company && location) ? 'inline' : 'none';

    const wpEl = document.getElementById('drawer-workplace');
    if (wpEl) {
        if (workplace) {
            wpEl.textContent = workplace;
            wpEl.style.display = 'inline-block';
        } else {
            wpEl.style.display = 'none';
        }
    }

    // Fit Section
    const fitSec = document.getElementById('drawer-fit-section');
    if (job.fit_score !== undefined && job.fit_score !== null && fitSec) {
        fitSec.style.display = 'block';
        const rawScore = job.fit_score;
        const pct = rawScore <= 1.0 ? Math.round(rawScore * 100) : Math.round(rawScore);
        const scoreVal = document.getElementById('drawer-fit-score');
        if (scoreVal) scoreVal.textContent = `${pct}%`;
        const scoreBar = document.getElementById('drawer-fit-bar');
        if (scoreBar) scoreBar.style.width = `${pct}%`;
        const progressbar = document.getElementById('drawer-fit-progressbar');
        if (progressbar) progressbar.setAttribute('aria-valuenow', String(pct));
    } else if (fitSec) {
        fitSec.style.display = 'none';
    }

    // Skills
    const skillsContainer = document.getElementById('drawer-skills');
    const skills = job.hard_skills || job.required_hard_skills || job.gap_analysis?.matched_hard_skills || job.tech_stack || [];
    if (skillsContainer) {
        skillsContainer.innerHTML = skills.length > 0
            ? skills.map(s => `<span class="skill-tag">${escapeHtml(s)}</span>`).join('')
            : `<span style="font-size: 12px; color: var(--text-muted);">No specific skills provided</span>`;
    }

    // Description
    const descEl = document.getElementById('drawer-description');
    if (descEl) {
        descEl.textContent = job.description || job.job_description || "No description provided for this vacancy.";
    }

    // Published date
    const pubEl = document.getElementById('drawer-published');
    if (pubEl) {
        pubEl.textContent = job.published_date ? `Posted ${job.published_date}` : "";
    }

    // Apply Link
    const linkEl = document.getElementById('drawer-apply-link');
    const rawUrl = job.job_url || job.career_page_url || job.url;
    if (linkEl) {
        if (rawUrl && typeof rawUrl === 'string' && rawUrl.startsWith('https://')) {
            linkEl.href = rawUrl;
            linkEl.style.display = 'inline-flex';
            linkEl.removeAttribute('hidden');
        } else {
            linkEl.removeAttribute('href');
            linkEl.style.display = 'none';
            linkEl.setAttribute('hidden', 'true');
        }
    }

    // Reveal Drawer
    const backdrop = document.getElementById('job-drawer-backdrop');
    const drawerEl = document.getElementById('job-inspector-drawer');
    if (backdrop) {
        backdrop.removeAttribute('hidden');
        backdrop.setAttribute('aria-hidden', 'false');
        backdrop.classList.add('active');
    }
    if (drawerEl) {
        drawerEl.removeAttribute('hidden');
        drawerEl.setAttribute('aria-hidden', 'false');
        drawerEl.setAttribute('aria-modal', 'true');
        drawerEl.classList.add('active');
    }

    // Set background content as inert
    const header = document.getElementById('public-app-header');
    const main = document.getElementById('public-main-content');
    if (header) header.setAttribute('inert', '');
    if (main) main.setAttribute('inert', '');

    document.body.style.overflow = 'hidden';

    // Move initial focus to close button
    setTimeout(() => {
        const closeBtn = document.getElementById('drawer-close-btn');
        if (closeBtn) closeBtn.focus();
    }, 20);
};

window.closeJobDrawer = function() {
    const backdrop = document.getElementById('job-drawer-backdrop');
    const drawer = document.getElementById('job-inspector-drawer');

    // If drawer is already closed, do nothing
    if (!drawer || drawer.hasAttribute('hidden')) return;

    if (backdrop) {
        backdrop.classList.remove('active');
        backdrop.setAttribute('hidden', 'true');
        backdrop.setAttribute('aria-hidden', 'true');
    }
    if (drawer) {
        drawer.classList.remove('active');
        drawer.setAttribute('hidden', 'true');
        drawer.setAttribute('aria-hidden', 'true');
        drawer.removeAttribute('aria-modal');
    }

    // Remove background inert attribute
    const header = document.getElementById('public-app-header');
    const main = document.getElementById('public-main-content');
    if (header) header.removeAttribute('inert');
    if (main) main.removeAttribute('inert');

    clearJobDrawerContent();
    document.body.style.overflow = '';

    // Restore focus to opener element
    if (lastDrawerOpener && typeof lastDrawerOpener.focus === 'function' && document.body.contains(lastDrawerOpener)) {
        lastDrawerOpener.focus();
    }
    lastDrawerOpener = null;
};

function initDrawerKeyboardListener() {
    initAnalyticsTabsKeyboard();

    window.addEventListener('keydown', (e) => {
        const drawer = document.getElementById('job-inspector-drawer');
        const isDrawerOpen = drawer && !drawer.hasAttribute('hidden');

        if (e.key === 'Escape') {
            if (isDrawerOpen) {
                e.preventDefault();
                closeJobDrawer();
            }
            return;
        }

        // Focus trap inside drawer
        if (e.key === 'Tab' && isDrawerOpen) {
            const focusables = Array.from(
                drawer.querySelectorAll('button:not([disabled]):not([hidden]), a[href]:not([hidden]), [tabindex]:not([tabindex="-1"])')
            ).filter(el => el.offsetParent !== null || el === document.getElementById('drawer-close-btn'));

            if (!focusables.length) return;

            const firstEl = focusables[0];
            const lastEl = focusables[focusables.length - 1];

            if (e.shiftKey) {
                if (document.activeElement === firstEl || !drawer.contains(document.activeElement)) {
                    e.preventDefault();
                    lastEl.focus();
                }
            } else {
                if (document.activeElement === lastEl || !drawer.contains(document.activeElement)) {
                    e.preventDefault();
                    firstEl.focus();
                }
            }
        }
    });
}

// ==================== Utilities ====================
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast-msg';

    let icon = 'bx-info-circle';
    if (type === 'success') icon = 'bx-check-circle';
    if (type === 'warning') icon = 'bx-error-circle';

    toast.innerHTML = `<i class='bx ${icon}'></i> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(4px)';
        toast.style.transition = 'all 0.2s ease';
        setTimeout(() => toast.remove(), 200);
    }, 3200);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
