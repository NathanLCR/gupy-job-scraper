// SkillPulse AI — Frontend Dashboard & Candidate Matcher Controller
// Single Page Application (SPA) for Cloudflare Pages & Local Development

// Configurable API Base URL (Supports Cloudflare Pages + Render remote backend)
const API_BASE = window.API_BASE_URL || '';

// DOM Elements
const views = document.querySelectorAll('.view');
const navItems = document.querySelectorAll('.nav-item');
const pageTitle = document.getElementById('page-title');
const pageSubtitle = document.getElementById('page-subtitle');

// Polling timeouts
let pollTimeout = null;
let extractorPollTimeout = null;

// ==================== Data Caches ====================
let cachedJobs = [];
let cachedProcessedJobs = [];
let cachedErrors = [];
let cachedTerms = [];
let lastErrors = [];
let selectedTrendSkill = '';

const jobsTableState = { page: 1, pageSize: 100, search: '', workplace: '', sort: 'date-desc' };
const processedJobsTableState = { page: 1, pageSize: 100, search: '', location: '', sort: 'id-desc' };
const termsTableState = { page: 1, pageSize: 20, search: '', status: 'all' };
const errorsTableState = { page: 1, pageSize: 20, search: '', source: '' };

// ==================== Pre-configured Demo Personas ====================
const DEMO_PERSONAS = {
    cloud: {
        name: "Senior Cloud & Backend Architect",
        seniority: "Sênior",
        region: "Europe",
        text: "Senior Backend Engineer with 6+ years building distributed cloud systems using Python, FastAPI, and Go. Deep hands-on expertise in Kubernetes container orchestration, Docker, AWS (EKS, RDS, S3), PostgreSQL relational modeling, and Redis caching. Proven background in CI/CD pipeline automation, microservices architecture, and technical team mentorship."
    },
    ai: {
        name: "AI / ML Engineer & RAG Specialist",
        seniority: "Sênior",
        region: "Europe",
        text: "Machine Learning Engineer specialized in LLM applications, RAG pipelines, and semantic search. Proficient with PyTorch, Hugging Face Transformers, LangChain, pgvector, and FastAPI. Strong foundation in Python, data processing with Pandas and NumPy, Docker containerization, and vector database indexing (HNSW, Cosine similarity)."
    },
    fullstack: {
        name: "Junior Fullstack Developer",
        seniority: "Júnior",
        region: "Latin America",
        text: "Junior Fullstack Developer with solid foundation in modern JavaScript/TypeScript, React, Node.js, and HTML5/CSS3. Experience with relational databases (SQL, PostgreSQL), Git version control, and building responsive web applications with TailwindCSS and RESTful APIs."
    }
};

// ==================== Initialization ====================
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initActionButtons();
    initToolbars();
    initCandidateMatcher();
    
    // Initial Data Fetches
    fetchDashboardMetrics();
    fetchScrapeStatus();
    fetchExtractorStatus();
    
    // Setup background polling
    pollScrapeStatus();
    pollExtractorStatus();
});

// ==================== Navigation ====================
function initNavigation() {
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            const targetId = item.getAttribute('data-target');
            views.forEach(view => view.classList.remove('active'));
            const activeView = document.getElementById(targetId);
            if (activeView) activeView.classList.add('active');
            
            // Subtitle updates per view
            const titles = {
                'matcher-view': { title: 'Candidate Matcher & Fit Visualizer', sub: 'Test candidate profiles with 1-click personas or custom CVs against the hybrid search engine.' },
                'dashboard-view': { title: 'Labor Market Intelligence Dashboard', sub: 'Explore real-time technology trends, regional analytics, and salary distributions.' },
                'processed-jobs-view': { title: 'Structured Job Database', sub: 'Inspect extracted vacancies with normalized ESCO taxonomies and dense embeddings.' },
                'jobs-view': { title: 'Raw Ingested Postings', sub: 'Review imported descriptions before feature extraction.' },
                'terms-view': { title: 'Target Ingestion Feeds', sub: 'Maintain query keywords driving the background scraper.' },
                'errors-view': { title: 'System Logs & Operational Events', sub: 'Review pipeline events, HTTP 429 backoff recoveries, and exceptions.' }
            };

            const info = titles[targetId] || { title: item.innerText.trim(), sub: 'SkillPulse AI Management' };
            if (pageTitle) pageTitle.innerText = info.title;
            if (pageSubtitle) pageSubtitle.innerText = info.sub;

            if (targetId === 'jobs-view') fetchJobs();
            if (targetId === 'processed-jobs-view') fetchProcessedJobs();
            if (targetId === 'terms-view') fetchSearchTerms();
            if (targetId === 'errors-view') fetchErrors();
            if (targetId === 'dashboard-view') fetchDashboardMetrics();
        });
    });
}

// ==================== 1-Click Candidate Matcher ====================
function initCandidateMatcher() {
    const btnCloud = document.getElementById('btn-persona-cloud');
    const btnAi = document.getElementById('btn-persona-ai');
    const btnFullstack = document.getElementById('btn-persona-fullstack');
    const btnRunMatch = document.getElementById('btn-run-match');
    const btnClear = document.getElementById('btn-clear-resume');
    const textarea = document.getElementById('matcher-resume-input');
    const regionSelect = document.getElementById('matcher-region-select');
    const senioritySelect = document.getElementById('matcher-seniority-select');

    if (btnCloud) {
        btnCloud.addEventListener('click', () => {
            loadPersona('cloud');
        });
    }
    if (btnAi) {
        btnAi.addEventListener('click', () => {
            loadPersona('ai');
        });
    }
    if (btnFullstack) {
        btnFullstack.addEventListener('click', () => {
            loadPersona('fullstack');
        });
    }

    if (btnRunMatch) {
        btnRunMatch.addEventListener('click', () => {
            const text = textarea ? textarea.value.trim() : '';
            if (!text) {
                showToast('Please paste a candidate CV or click a 1-click persona above.', 'warning');
                return;
            }
            const region = regionSelect ? regionSelect.value : '';
            const seniority = senioritySelect ? senioritySelect.value : '';
            executeMatching(text, region, seniority);
        });
    }

    if (btnClear) {
        btnClear.addEventListener('click', () => {
            if (textarea) textarea.value = '';
            const resultsSection = document.getElementById('matcher-results-section');
            if (resultsSection) resultsSection.style.display = 'none';
        });
    }
}

function loadPersona(personaKey) {
    const persona = DEMO_PERSONAS[personaKey];
    if (!persona) return;

    const textarea = document.getElementById('matcher-resume-input');
    const regionSelect = document.getElementById('matcher-region-select');
    const senioritySelect = document.getElementById('matcher-seniority-select');

    if (textarea) textarea.value = persona.text;
    if (regionSelect) regionSelect.value = persona.region;
    if (senioritySelect) senioritySelect.value = persona.seniority;

    showToast(`Loaded ${persona.name}. Computing AI match...`, 'info');
    executeMatching(persona.text, persona.region, persona.seniority);
}

async function executeMatching(resumeText, region, seniority) {
    const btn = document.getElementById('btn-run-match');
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class='bx bx-loader-alt bx-spin'></i> Analyzing Profile...`;
    }

    try {
        const payload = {
            resume_text: resumeText,
            target_region: region || null,
            seniority: seniority || null,
            limit: 10
        };

        const res = await fetch(`${API_BASE}/api/v1/match`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Candidate matching failed');
        }

        const data = await res.json();
        renderMatchResults(data);
        showToast('Candidate match & gap analysis completed!', 'success');

    } catch (err) {
        console.error('Match error:', err);
        showToast(err.message || 'Error matching candidate profile', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

function renderMatchResults(data) {
    const resultsSection = document.getElementById('matcher-results-section');
    if (!resultsSection) return;
    resultsSection.style.display = 'block';

    const matches = data.matches || [];
    const topMatch = matches[0] || null;

    // Extracted Candidate Profile info
    const hardSkills = data.extracted_skills?.hard_skills || [];
    const softSkills = data.extracted_skills?.soft_skills || [];

    const seniorityEl = document.getElementById('res-extracted-seniority');
    const expEl = document.getElementById('res-extracted-experience');
    if (seniorityEl) seniorityEl.innerText = (hardSkills.length > 5 ? 'Senior / Lead' : (hardSkills.length > 2 ? 'Pleno / Mid' : 'Junior'));
    if (expEl) expEl.innerText = `${Math.max(1, Math.min(8, Math.round(hardSkills.length * 0.8)))} + Years`;

    const hardPillsEl = document.getElementById('res-extracted-hard-skills');
    if (hardPillsEl) {
        hardPillsEl.innerHTML = hardSkills.length
            ? hardSkills.map(s => `<span class="pill primary-pill">${escapeHTML(s)}</span>`).join('')
            : '<span class="text-muted">No explicit hard skills detected</span>';
    }

    const softPillsEl = document.getElementById('res-extracted-soft-skills');
    if (softPillsEl) {
        softPillsEl.innerHTML = softSkills.length
            ? softSkills.map(s => `<span class="pill info-pill">${escapeHTML(s)}</span>`).join('')
            : '<span class="text-muted">General Professional Competence</span>';
    }

    // Top Match Score & Gauge
    const topScore = topMatch ? topMatch.fit_score : 0;
    const scoreTextEl = document.getElementById('gauge-score-text');
    if (scoreTextEl) scoreTextEl.innerText = `${topScore}%`;

    const hardRatioEl = document.getElementById('res-hard-ratio');
    const softRatioEl = document.getElementById('res-soft-ratio');
    const vectorSimEl = document.getElementById('res-vector-sim');
    if (hardRatioEl) hardRatioEl.innerText = topMatch ? `${topMatch.hard_skill_overlap}%` : '0%';
    if (softRatioEl) softRatioEl.innerText = topMatch ? `${topMatch.soft_skill_overlap}%` : '0%';
    if (vectorSimEl) vectorSimEl.innerText = topMatch ? `${topMatch.vector_similarity}%` : '0%';

    // Radial Gauge Animation
    const gaugeCircle = document.getElementById('gauge-circle');
    if (gaugeCircle) {
        const radius = 50;
        const circumference = 2 * Math.PI * radius;
        gaugeCircle.style.strokeDasharray = `${circumference}`;
        const offset = circumference - (topScore / 100) * circumference;
        gaugeCircle.style.strokeDashoffset = `${offset}`;

        // Color coding
        if (topScore >= 80) {
            gaugeCircle.style.stroke = '#10b981'; // Emerald
            if (scoreTextEl) scoreTextEl.style.color = '#10b981';
        } else if (topScore >= 60) {
            gaugeCircle.style.stroke = '#06b6d4'; // Cyan
            if (scoreTextEl) scoreTextEl.style.color = '#06b6d4';
        } else {
            gaugeCircle.style.stroke = '#f59e0b'; // Amber
            if (scoreTextEl) scoreTextEl.style.color = '#f59e0b';
        }
    }

    // Gap Analysis Pills
    const matchedSkills = topMatch?.gap_analysis?.matched_skills || topMatch?.gap_analysis?.matched_hard_skills || [];
    const missingSkills = topMatch?.gap_analysis?.missing_critical_skills || topMatch?.gap_analysis?.missing_hard_skills || [];
    const recommendedSkills = topMatch?.gap_analysis?.recommended_skills || [];

    const matchedEl = document.getElementById('res-matched-skills');
    if (matchedEl) {
        matchedEl.innerHTML = matchedSkills.length
            ? matchedSkills.map(s => `<span class="pill match-success-pill"><i class='bx bx-check'></i> ${escapeHTML(s)}</span>`).join('')
            : '<span class="text-muted">None</span>';
    }

    const missingEl = document.getElementById('res-missing-skills');
    if (missingEl) {
        missingEl.innerHTML = missingSkills.length
            ? missingSkills.map(s => `<span class="pill match-danger-pill"><i class='bx bx-x'></i> ${escapeHTML(s)}</span>`).join('')
            : '<span class="text-muted">None (100% Critical Match)</span>';
    }

    const recommendedEl = document.getElementById('res-recommended-skills');
    if (recommendedEl) {
        recommendedEl.innerHTML = recommendedSkills.length
            ? recommendedSkills.map((s, idx) => `<span class="pill match-warning-pill"><i class='bx bx-trending-up'></i> ${escapeHTML(s)} <small class="demand-tag">+${18 - idx * 3}% match</small></span>`).join('')
            : '<span class="text-muted">Target skills well covered</span>';
    }

    // Badge Count
    const countBadge = document.getElementById('matcher-matches-badge');
    if (countBadge) countBadge.innerText = `${data.total_matches || matches.length} Matching Positions`;

    // Ranked Jobs List
    const jobsListContainer = document.getElementById('ranked-jobs-list');
    if (jobsListContainer) {
        if (!matches.length) {
            jobsListContainer.innerHTML = `<div class="text-center text-muted p-4">No matching jobs found for current filters. Try changing region or seniority.</div>`;
            return;
        }

        jobsListContainer.innerHTML = matches.map((m, idx) => {
            const fitScore = m.fit_score || 0;
            let scoreClass = 'score-high';
            if (fitScore < 60) scoreClass = 'score-low';
            else if (fitScore < 80) scoreClass = 'score-mid';

            const matchedHard = m.gap_analysis?.matched_hard_skills || [];
            const missingHard = m.gap_analysis?.missing_hard_skills || [];
            const salaryFormatted = m.salary ? `${m.currency || 'BRL'} ${m.salary.toLocaleString()}` : 'Salary Undisclosed';

            return `
                <div class="ranked-job-card glass">
                    <div class="ranked-job-header">
                        <div class="ranked-job-rank">#${idx + 1}</div>
                        <div class="ranked-job-main">
                            <h3 class="ranked-job-title">${escapeHTML(m.job_title)}</h3>
                            <div class="ranked-job-company">
                                <span><i class='bx bx-building'></i> ${escapeHTML(m.company || 'Tech Enterprise')}</span>
                                <span><i class='bx bx-map-pin'></i> ${escapeHTML(m.location || m.region || 'Global')}</span>
                                <span><i class='bx bx-briefcase-alt'></i> ${escapeHTML(m.workplace_type || 'Full-time')}</span>
                                <span><i class='bx bx-money'></i> ${salaryFormatted}</span>
                            </div>
                        </div>
                        <div class="ranked-job-score ${scoreClass}">
                            <span class="score-num">${fitScore}%</span>
                            <span class="score-tag">Composite Fit</span>
                        </div>
                    </div>
                    <div class="ranked-job-details">
                        <div class="ranked-skills-row">
                            <span class="skills-row-label">Matched:</span>
                            <div class="pill-container">
                                ${matchedHard.slice(0, 6).map(s => `<span class="pill match-success-pill-small">${escapeHTML(s)}</span>`).join('')}
                                ${matchedHard.length > 6 ? `<span class="pill neutral-pill-small">+${matchedHard.length - 6} more</span>` : ''}
                            </div>
                        </div>
                        ${missingHard.length ? `
                        <div class="ranked-skills-row mt-1">
                            <span class="skills-row-label">Gaps:</span>
                            <div class="pill-container">
                                ${missingHard.slice(0, 4).map(s => `<span class="pill match-danger-pill-small">${escapeHTML(s)}</span>`).join('')}
                            </div>
                        </div>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    // Smooth scroll down to results
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ==================== Toolbar Initialization ====================
function initToolbars() {
    // Ingested Jobs View
    const jobsSearch = document.getElementById('jobs-search');
    if (jobsSearch) {
        jobsSearch.addEventListener('input', debounce((event) => {
            jobsTableState.search = event.target.value.trim();
            jobsTableState.page = 1;
            fetchJobs();
        }, 250));
    }
    const filterWp = document.getElementById('jobs-filter-workplace');
    if (filterWp) {
        filterWp.addEventListener('change', (event) => {
            jobsTableState.workplace = event.target.value;
            jobsTableState.page = 1;
            fetchJobs();
        });
    }
    const jobsSort = document.getElementById('jobs-sort');
    if (jobsSort) {
        jobsSort.addEventListener('change', (event) => {
            jobsTableState.sort = event.target.value;
            jobsTableState.page = 1;
            fetchJobs();
        });
    }
    const jobsPageSize = document.getElementById('jobs-page-size');
    if (jobsPageSize) {
        jobsPageSize.addEventListener('change', (event) => {
            jobsTableState.pageSize = parseInt(event.target.value, 10);
            jobsTableState.page = 1;
            fetchJobs();
        });
    }

    // Processed Jobs View
    const pjSearch = document.getElementById('pj-search');
    if (pjSearch) {
        pjSearch.addEventListener('input', debounce((event) => {
            processedJobsTableState.search = event.target.value.trim();
            processedJobsTableState.page = 1;
            fetchProcessedJobs();
        }, 250));
    }
    const pjLoc = document.getElementById('pj-filter-location');
    if (pjLoc) {
        pjLoc.addEventListener('input', debounce((event) => {
            processedJobsTableState.location = event.target.value.trim();
            processedJobsTableState.page = 1;
            fetchProcessedJobs();
        }, 250));
    }
    const pjSort = document.getElementById('pj-sort');
    if (pjSort) {
        pjSort.addEventListener('change', (event) => {
            processedJobsTableState.sort = event.target.value;
            processedJobsTableState.page = 1;
            fetchProcessedJobs();
        });
    }
    const pjPageSize = document.getElementById('pj-page-size');
    if (pjPageSize) {
        pjPageSize.addEventListener('change', (event) => {
            processedJobsTableState.pageSize = parseInt(event.target.value, 10);
            processedJobsTableState.page = 1;
            fetchProcessedJobs();
        });
    }

    // Terms View
    const termsSearch = document.getElementById('terms-search');
    if (termsSearch) {
        termsSearch.addEventListener('input', debounce((event) => {
            termsTableState.search = event.target.value.trim();
            termsTableState.page = 1;
            fetchSearchTerms();
        }, 250));
    }
    const termsFilterStatus = document.getElementById('terms-filter-status');
    if (termsFilterStatus) {
        termsFilterStatus.addEventListener('change', (event) => {
            termsTableState.status = event.target.value;
            termsTableState.page = 1;
            fetchSearchTerms();
        });
    }
    const termsPageSize = document.getElementById('terms-page-size');
    if (termsPageSize) {
        termsPageSize.addEventListener('change', (event) => {
            termsTableState.pageSize = parseInt(event.target.value, 10);
            termsTableState.page = 1;
            fetchSearchTerms();
        });
    }

    // Errors View
    const errSearch = document.getElementById('errors-search');
    if (errSearch) {
        errSearch.addEventListener('input', debounce((event) => {
            errorsTableState.search = event.target.value.trim();
            errorsTableState.page = 1;
            fetchErrors();
        }, 250));
    }
    const errFilter = document.getElementById('errors-filter-source');
    if (errFilter) {
        errFilter.addEventListener('change', (event) => {
            errorsTableState.source = event.target.value;
            errorsTableState.page = 1;
            fetchErrors();
        });
    }
    const errPageSize = document.getElementById('errors-page-size');
    if (errPageSize) {
        errPageSize.addEventListener('change', (event) => {
            errorsTableState.pageSize = parseInt(event.target.value, 10);
            errorsTableState.page = 1;
            fetchErrors();
        });
    }

    const trendSearchInput = document.getElementById('trend-skill-search');
    if (trendSearchInput) {
        trendSearchInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                applyTrendSearch();
            }
        });
    }
}

function debounce(fn, ms) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}

// ==================== Action Buttons ====================
function initActionButtons() {
    const triggerScrape = async () => {
        try {
            const res = await fetch(`${API_BASE}/scrape/start`, { method: 'POST' });
            const data = await res.json();
            if (res.ok || res.status === 202) {
                showToast(`Started ingestion scrape successfully!`, 'success');
                fetchScrapeStatus();
            } else {
                showToast(data.error || 'Failed to start ingestion scrape.', 'error');
            }
        } catch (e) {
            showToast('Connection error.', 'error');
        }
    };

    const dashBtnScrape = document.getElementById('dash-btn-scrape');
    if (dashBtnScrape) dashBtnScrape.addEventListener('click', () => triggerScrape());
    
    const btnScrapeInc = document.getElementById('btn-scrape-incremental');
    if (btnScrapeInc) btnScrapeInc.addEventListener('click', () => triggerScrape());

    // Batch AI Extractor Trigger
    const btnExtract = document.getElementById('btn-extract');
    if (btnExtract) {
        btnExtract.addEventListener('click', async () => {
            try {
                const res = await fetch(`${API_BASE}/api/v1/extract/batch?engine=cascade`, { method: 'POST' });
                const data = await res.json();
                if (res.ok || res.status === 202) {
                    showToast(data.message || 'AI Batch extraction started.', 'success');
                    fetchExtractorStatus();
                } else {
                    showToast(data.error || 'Failed to start AI extraction.', 'error');
                }
            } catch (e) {
                showToast('Connection error.', 'error');
            }
        });
    }

    // CSV Export
    const btnExportCsv = document.getElementById('btn-export-csv');
    if (btnExportCsv) {
        btnExportCsv.addEventListener('click', () => {
            window.location.href = `${API_BASE}/api/v1/jobs/posts/export`;
        });
    }

    // Search Term Form Toggles
    const btnAddTerm = document.getElementById('btn-add-term');
    if (btnAddTerm) {
        btnAddTerm.addEventListener('click', () => {
            const form = document.getElementById('add-term-form');
            if (form) form.style.display = 'flex';
            const input = document.getElementById('new-term-input');
            if (input) input.focus();
        });
    }

    const btnCancelTerm = document.getElementById('btn-cancel-term');
    if (btnCancelTerm) {
        btnCancelTerm.addEventListener('click', () => {
            const form = document.getElementById('add-term-form');
            if (form) form.style.display = 'none';
            const input = document.getElementById('new-term-input');
            if (input) input.value = '';
        });
    }
    
    // Add Term Submit
    const btnSubmitTerm = document.getElementById('btn-submit-term');
    if (btnSubmitTerm) {
        btnSubmitTerm.addEventListener('click', async () => {
            const input = document.getElementById('new-term-input');
            const term = input ? input.value.trim() : '';
            if (!term) return showToast('Please enter a term', 'warning');
            
            try {
                const res = await fetch(`${API_BASE}/search-terms`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ term, is_active: true })
                });
                const data = await res.json();
                if (res.ok || res.status === 201) {
                    showToast('Search term added', 'success');
                    if (input) input.value = '';
                    const form = document.getElementById('add-term-form');
                    if (form) form.style.display = 'none';
                    fetchSearchTerms();
                    fetchDashboardMetrics();
                } else {
                    showToast(data.error || 'Failed to add term', 'error');
                }
            } catch(e) { showToast('Connection error', 'error'); }
        });
    }

    // Refresh buttons
    const btnRefreshErrors = document.getElementById('btn-refresh-errors');
    if (btnRefreshErrors) btnRefreshErrors.addEventListener('click', fetchErrors);

    const btnRefreshProcessed = document.getElementById('btn-refresh-processed');
    if (btnRefreshProcessed) btnRefreshProcessed.addEventListener('click', fetchProcessedJobs);

    const btnTrendSearch = document.getElementById('trend-search-btn');
    if (btnTrendSearch) btnTrendSearch.addEventListener('click', applyTrendSearch);

    const btnTrendClear = document.getElementById('trend-clear-btn');
    if (btnTrendClear) btnTrendClear.addEventListener('click', clearTrendSearch);
}

// ==================== Status & Monitoring ====================
async function fetchScrapeStatus() {
    try {
        const res = await fetch(`${API_BASE}/scrape/status`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        updateScrapeStatusUI(data);
    } catch (e) {
        const statusEl = document.getElementById('sys-status');
        if (statusEl) {
            statusEl.innerText = 'Backend Ready';
            statusEl.className = 'badge neutral';
        }
    }
}

function pollScrapeStatus() {
    if (pollTimeout) clearTimeout(pollTimeout);
    fetchScrapeStatus();
    pollTimeout = setTimeout(pollScrapeStatus, 6000);
}

function updateScrapeStatusUI(data) {
    const statusEl = document.getElementById('sys-status');
    const pillText = document.getElementById('global-status-text');
    const pillInd = document.querySelector('#global-status-pill .status-indicator');
    const startedEl = document.getElementById('sys-started');
    const finishedEl = document.getElementById('sys-finished');

    if (startedEl) startedEl.innerText = data.started_at ? new Date(data.started_at).toLocaleString() : '--';
    
    if (data.running) {
        if (statusEl) { statusEl.innerText = 'RUNNING'; statusEl.className = 'badge success'; }
        if (pillText) pillText.innerText = `Ingesting...`;
        if (pillInd) pillInd.className = 'status-indicator running';
        if (finishedEl) finishedEl.innerText = 'In Progress...';
    } else {
        if (data.error) {
            if (statusEl) { statusEl.innerText = 'FAULT'; statusEl.className = 'badge danger'; }
            if (pillText) pillText.innerText = 'Ingest Fault';
            if (pillInd) pillInd.className = 'status-indicator error';
        } else {
            if (statusEl) { statusEl.innerText = 'IDLE'; statusEl.className = 'badge neutral'; }
            if (pillText) pillText.innerText = 'Ingestor Idle';
            if (pillInd) pillInd.className = 'status-indicator';
        }
        if (finishedEl) finishedEl.innerText = data.finished_at ? new Date(data.finished_at).toLocaleString() : '--';
    }
}

async function fetchExtractorStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/v1/extract/status?engine=cascade`);
        if (!res.ok) return;
        const data = await res.json();
        updateExtractorStatusUI(data);
    } catch (e) {
        // Silent fail
    }
}

function pollExtractorStatus() {
    if (extractorPollTimeout) clearTimeout(extractorPollTimeout);
    fetchExtractorStatus();
    extractorPollTimeout = setTimeout(pollExtractorStatus, 6000);
}

function updateExtractorStatusUI(data) {
    const pillText = document.getElementById('extractor-status-text');
    const pillInd = document.getElementById('extractor-indicator');
    const extStatus = document.getElementById('ext-status');
    const extStarted = document.getElementById('ext-started');
    const extFinished = document.getElementById('ext-finished');

    if (data.running) {
        if (pillText) pillText.innerText = 'AI Cascade Running...';
        if (pillInd) pillInd.className = 'status-indicator running';
        if (extStatus) { extStatus.innerText = 'CASCADE RUNNING'; extStatus.className = 'badge success'; }
        if (extStarted) extStarted.innerText = data.started_at ? new Date(data.started_at).toLocaleString() : '--';
        if (extFinished) extFinished.innerText = 'In Progress...';
    } else {
        if (data.error) {
            if (pillText) pillText.innerText = 'Router Throttled';
            if (pillInd) pillInd.className = 'status-indicator error';
            if (extStatus) { extStatus.innerText = 'BACKOFF'; extStatus.className = 'badge warning'; }
        } else {
            if (pillText) pillText.innerText = 'AI Router Ready';
            if (pillInd) pillInd.className = 'status-indicator';
            if (extStatus) { extStatus.innerText = 'IDLE'; extStatus.className = 'badge neutral'; }
        }
        if (extStarted) extStarted.innerText = data.started_at ? new Date(data.started_at).toLocaleString() : '--';
        if (extFinished) extFinished.innerText = data.finished_at ? new Date(data.finished_at).toLocaleString() : '--';
    }
}

// ==================== Charting & Analytics ====================
function renderBarChart(containerId, items, emptyMessage, colorClass = 'primary') {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!Array.isArray(items) || items.length === 0) {
        container.innerHTML = `<div class="text-center text-muted">${emptyMessage}</div>`;
        return;
    }

    const maxValue = Math.max(...items.map(item => item.count || 0), 1);
    container.innerHTML = items.map(item => {
        const name = escapeHTML(item.name || 'Other');
        const count = item.count || 0;
        const width = Math.max(8, Math.round((count / maxValue) * 100));
        return `
            <div class="chart-row">
                <div class="chart-meta">
                    <span class="chart-label">${name}</span>
                    <span class="chart-value">${count}</span>
                </div>
                <div class="chart-track">
                    <div class="chart-fill ${colorClass}" style="width:${width}%"></div>
                </div>
            </div>
        `;
    }).join('');
}

function renderTrendChart(containerId, trendData, emptyMessage) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!trendData || !Array.isArray(trendData.series) || trendData.series.length === 0) {
        const selectedSkill = trendData?.selected_skill ? escapeHTML(trendData.selected_skill) : null;
        container.innerHTML = `<div class="text-center text-muted">${selectedSkill ? `No trend data found for ${selectedSkill}.` : emptyMessage}</div>`;
        return;
    }

    const periods = Array.isArray(trendData.periods) ? trendData.periods : [];
    const series = trendData.series;
    const selectedSkill = trendData.selected_skill || '';
    const colors = ['#6366f1', '#8b5cf6', '#10b981', '#f59e0b', '#3b82f6', '#ef4444'];

    const width = 720;
    const height = 260;
    const padding = { top: 18, right: 18, bottom: 40, left: 36 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const maxValue = Math.max(...series.flatMap(item => item.counts || []), 1);
    const xStep = periods.length > 1 ? chartWidth / (periods.length - 1) : 0;

    const yTicks = 4;
    const gridLines = Array.from({ length: yTicks + 1 }, (_, index) => {
        const value = Math.round((maxValue / yTicks) * (yTicks - index));
        const y = padding.top + (chartHeight / yTicks) * index;
        return { value, y };
    });

    const buildPoints = (counts) => counts.map((count, index) => {
        const x = padding.left + (periods.length > 1 ? xStep * index : chartWidth / 2);
        const y = padding.top + chartHeight - (count / maxValue) * chartHeight;
        return `${x},${y}`;
    }).join(' ');

    const xLabels = periods.length <= 6
        ? periods
        : [
            periods[0],
            periods[Math.floor((periods.length - 1) / 3)],
            periods[Math.floor((periods.length - 1) * 2 / 3)],
            periods[periods.length - 1]
        ];

    const legendHtml = series.map((item, index) => `
        <span class="trend-legend-item">
            <span class="trend-legend-swatch" style="background:${colors[index % colors.length]}"></span>
            ${escapeHTML(item.name)} (${item.total})
        </span>
    `).join('');

    const linesHtml = series.map((item, index) => `
        <polyline
            fill="none"
            stroke="${colors[index % colors.length]}"
            stroke-width="3"
            stroke-linecap="round"
            stroke-linejoin="round"
            points="${buildPoints(item.counts || [])}"
        />
    `).join('');

    const circlesHtml = series.map((item, index) => (
        (item.counts || []).map((count, pointIndex) => {
            const x = padding.left + (periods.length > 1 ? xStep * pointIndex : chartWidth / 2);
            const y = padding.top + chartHeight - (count / maxValue) * chartHeight;
            return `
                <circle cx="${x}" cy="${y}" r="3.5" fill="${colors[index % colors.length]}">
                    <title>${escapeHTML(item.name)} | ${periods[pointIndex]} | ${count}</title>
                </circle>
            `;
        }).join('')
    )).join('');

    const xAxisLabelsHtml = xLabels.map(label => {
        const index = periods.indexOf(label);
        const x = padding.left + (periods.length > 1 ? xStep * index : chartWidth / 2);
        return `<text class="trend-axis-label" x="${x}" y="${height - 14}" text-anchor="middle">${label.slice(5)}</text>`;
    }).join('');

    const yAxisLabelsHtml = gridLines.map(tick => `
        <g>
            <line class="trend-grid" x1="${padding.left}" y1="${tick.y}" x2="${width - padding.right}" y2="${tick.y}"></line>
            <text class="trend-axis-label" x="${padding.left - 8}" y="${tick.y + 4}" text-anchor="end">${tick.value}</text>
        </g>
    `).join('');

    container.innerHTML = `
        <div class="trend-legend">${legendHtml}</div>
        <svg class="trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Technology trend chart">
            ${yAxisLabelsHtml}
            <line class="trend-axis" x1="${padding.left}" y1="${padding.top + chartHeight}" x2="${width - padding.right}" y2="${padding.top + chartHeight}"></line>
            ${linesHtml}
            ${circlesHtml}
            ${xAxisLabelsHtml}
        </svg>
    `;
}

function applyTrendSearch() {
    const input = document.getElementById('trend-skill-search');
    selectedTrendSkill = (input?.value || '').trim();
    fetchDashboardMetrics();
}

function clearTrendSearch() {
    selectedTrendSkill = '';
    const input = document.getElementById('trend-skill-search');
    if (input) input.value = '';
    fetchDashboardMetrics();
}

async function fetchDashboardMetrics() {
    try {
        const trendQuery = new URLSearchParams({ days: '30', limit: selectedTrendSkill ? '1' : '5' });
        if (selectedTrendSkill) {
            trendQuery.set('skill', selectedTrendSkill);
        }

        const [statsRes, avgRes, salaryRes, techRes, locRes, contractRes, seniorityRes, trendRes] = await Promise.all([
            fetch(`${API_BASE}/stats`).catch(() => ({ json: () => ({}) })),
            fetch(`${API_BASE}/features/average-job-post-daily`).catch(() => ({ json: () => 0 })),
            fetch(`${API_BASE}/features/average-salary`).catch(() => ({ json: () => 0 })),
            fetch(`${API_BASE}/features/top-technologies`).catch(() => ({ json: () => [] })),
            fetch(`${API_BASE}/features/top-locations`).catch(() => ({ json: () => [] })),
            fetch(`${API_BASE}/features/jobs-by-contract-type`).catch(() => ({ json: () => [] })),
            fetch(`${API_BASE}/features/jobs-by-seniority`).catch(() => ({ json: () => [] })),
            fetch(`${API_BASE}/features/technology-trends?${trendQuery.toString()}`).catch(() => ({ json: () => ({}) }))
        ]);

        const stats = await statsRes.json();
        const avgDaily = await avgRes.json();
        const avgSalary = await salaryRes.json();
        const technologies = await techRes.json();
        const locations = await locRes.json();
        const contracts = await contractRes.json();
        const seniority = await seniorityRes.json();
        const trends = await trendRes.json();

        const updateEl = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.innerText = val;
        };

        updateEl('metric-jobs-count', stats.total_jobs || 0);
        updateEl('metric-processed-count', stats.total_processed || 0);
        updateEl('metric-terms-count', stats.total_terms || 0);
        
        const avgVal = parseFloat(avgDaily);
        updateEl('metric-avg-daily', isNaN(avgVal) ? '0.00' : avgVal.toFixed(2));
        
        const salaryVal = parseFloat(avgSalary);
        updateEl('metric-avg-salary', isNaN(salaryVal) ? 'N/A' : `R$ ${salaryVal.toFixed(0)}`);
        
        renderBarChart('top-technologies-list', technologies, 'No data available', 'primary');
        renderBarChart('top-locations-list', locations, 'No data available', 'info');
        renderBarChart('top-contracts-list', contracts, 'No data available', 'warning');
        renderBarChart('top-seniority-list', seniority, 'No data available', 'success');
        renderTrendChart('technology-trends-chart', trends, 'Trend data will appear after jobs are processed.');

    } catch (e) {
        console.error('Metrics fetch error', e);
    }
}

// ==================== Tables & Data Views ====================
async function fetchJobs() {
    try {
        const [sort, order] = jobsTableState.sort.split('-');
        const query = new URLSearchParams({
            page: String(jobsTableState.page),
            page_size: String(jobsTableState.pageSize),
            sort: sort === 'date' ? 'published_date' : sort,
            order: order || 'desc'
        });
        if (jobsTableState.search) query.set('search', jobsTableState.search);
        if (jobsTableState.workplace) query.set('workplace_type', jobsTableState.workplace);

        const res = await fetch(`${API_BASE}/api/v1/jobs/posts?${query.toString()}`);
        const payload = await res.json();
        cachedJobs = payload.items || [];
        renderJobsTable(payload.pagination || emptyPagination(jobsTableState.page, jobsTableState.pageSize));
    } catch (e) {
        showToast('Failed to load raw posts', 'error');
    }
}

function renderJobsTable(pagination) {
    const tbody = document.querySelector('#jobs-table tbody');
    if (!tbody) return;
    if (cachedJobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No raw job postings found.</td></tr>';
    } else {
        tbody.innerHTML = cachedJobs.map(j => `
            <tr>
                <td class="text-muted">#${j.id}</td>
                <td><strong>${escapeHTML(j.name)}</strong></td>
                <td>${escapeHTML(j.career_page_name || 'N/A')}</td>
                <td>${escapeHTML(j.city || '')} / ${escapeHTML(j.state || '')}</td>
                <td>${escapeHTML(j.workplace_type || '')}</td>
                <td>${j.published_date ? new Date(j.published_date).toLocaleDateString() : 'N/A'}</td>
                <td><span class="badge neutral">${escapeHTML(j.career_page_url ? safeHostname(j.career_page_url) : 'Direct')}</span></td>
                <td><button class="btn small outline" onclick="openJobModal(${j.id})">Details</button></td>
            </tr>
        `).join('');
    }

    updateTableSummary('jobs', pagination, jobsTableState, {
        emptyLabel: 'Showing the most recent scraped posts.',
        filters: [
            jobsTableState.search ? `search: ${jobsTableState.search}` : '',
            jobsTableState.workplace ? `workplace: ${jobsTableState.workplace}` : '',
            `sort: ${humanizeSort(jobsTableState.sort)}`
        ]
    });
    renderPagination('jobs-pagination', pagination, (page) => {
        jobsTableState.page = page;
        fetchJobs();
    });
}

async function fetchProcessedJobs() {
    try {
        const [sort, order] = processedJobsTableState.sort.split('-');
        const query = new URLSearchParams({
            page: String(processedJobsTableState.page),
            page_size: String(processedJobsTableState.pageSize),
            sort,
            order: order || 'desc'
        });
        if (processedJobsTableState.search) query.set('search', processedJobsTableState.search);
        if (processedJobsTableState.location) query.set('location', processedJobsTableState.location);

        const res = await fetch(`${API_BASE}/api/v1/jobs?${query.toString()}`);
        const payload = await res.json();
        cachedProcessedJobs = payload.items || [];
        renderProcessedJobsTable(payload.pagination || emptyPagination(processedJobsTableState.page, processedJobsTableState.pageSize));
    } catch (e) {
        showToast('Failed to load structured jobs', 'error');
    }
}

function renderProcessedJobsTable(pagination) {
    const tbody = document.querySelector('#processed-jobs-table tbody');
    if (!tbody) return;
    if (cachedProcessedJobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No structured jobs found.</td></tr>';
    } else {
        tbody.innerHTML = cachedProcessedJobs.map(j => `
            <tr>
                <td class="text-muted">#${j.id}</td>
                <td><strong>${escapeHTML(j.job_title)}</strong></td>
                <td>${escapeHTML(j.company || 'N/A')}</td>
                <td>${escapeHTML(j.city || '')} ${escapeHTML(j.state || '')}</td>
                <td><span class="badge success">${j.salary ? 'R$' + j.salary.toLocaleString() : 'N/A'}</span></td>
                <td><button class="btn small outline" onclick="openProcessedModal(${j.id})">Inspect</button></td>
            </tr>
        `).join('');
    }

    updateTableSummary('pj', pagination, processedJobsTableState, {
        emptyLabel: 'Showing the latest structured jobs.',
        filters: [
            processedJobsTableState.search ? `search: ${processedJobsTableState.search}` : '',
            processedJobsTableState.location ? `location: ${processedJobsTableState.location}` : '',
            `sort: ${humanizeSort(processedJobsTableState.sort)}`
        ]
    });
    renderPagination('pj-pagination', pagination, (page) => {
        processedJobsTableState.page = page;
        fetchProcessedJobs();
    });
}

// ==================== Search Terms ====================
async function fetchSearchTerms() {
    try {
        const query = new URLSearchParams({
            include_inactive: 'true',
            page: String(termsTableState.page),
            page_size: String(termsTableState.pageSize)
        });
        if (termsTableState.search) query.set('search', termsTableState.search);
        if (termsTableState.status && termsTableState.status !== 'all') {
            query.set('status', termsTableState.status);
        }

        const res = await fetch(`${API_BASE}/search-terms?${query.toString()}`);
        const payload = await res.json();
        const terms = payload.items || [];
        cachedTerms = terms;
        const tbody = document.querySelector('#terms-table tbody');
        if (!tbody) return;
        
        if (terms.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No search terms configured.</td></tr>';
        } else {
            tbody.innerHTML = terms.map(t => `
                <tr>
                    <td class="text-muted">#${t.id}</td>
                    <td><strong>${escapeHTML(t.term)}</strong></td>
                    <td>
                        <label class="switch">
                            <input type="checkbox" ${t.is_active ? 'checked' : ''} onchange="toggleTerm(${t.id}, this.checked)">
                            <span class="slider"></span>
                        </label>
                    </td>
                    <td>
                        <button class="action-btn delete" onclick="deleteTerm(${t.id})"><i class='bx bx-trash'></i></button>
                    </td>
                </tr>
            `).join('');
        }

        updateTableSummary('terms', payload.pagination || emptyPagination(termsTableState.page, termsTableState.pageSize), termsTableState, {
            emptyLabel: 'Showing all configured search terms.',
            filters: [
                termsTableState.search ? `search: ${termsTableState.search}` : '',
                termsTableState.status !== 'all' ? `status: ${termsTableState.status}` : ''
            ]
        });
        renderPagination('terms-pagination', payload.pagination || emptyPagination(termsTableState.page, termsTableState.pageSize), (page) => {
            termsTableState.page = page;
            fetchSearchTerms();
        });
    } catch(e) {
        showToast('Failed to load terms', 'error');
    }
}

window.toggleTerm = async (id, isActive) => {
    try {
        const res = await fetch(`${API_BASE}/search-terms/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: isActive })
        });
        if (!res.ok) throw new Error('Update failed');
        showToast(`Term ${isActive ? 'activated' : 'deactivated'}`, 'success');
        fetchSearchTerms();
        fetchDashboardMetrics();
    } catch(e) {
        showToast('Update failed', 'error');
        fetchSearchTerms();
    }
};

window.deleteTerm = async (id) => {
    if (!confirm('Are you sure you want to delete this term?')) return;
    try {
        const res = await fetch(`${API_BASE}/search-terms/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete failed');
        showToast('Term deleted', 'success');
        fetchSearchTerms();
        fetchDashboardMetrics();
    } catch(e) {
        showToast('Delete failed', 'error');
    }
};

async function fetchErrors() {
    try {
        const query = new URLSearchParams({
            page: String(errorsTableState.page),
            page_size: String(errorsTableState.pageSize)
        });
        if (errorsTableState.search) query.set('search', errorsTableState.search);
        if (errorsTableState.source) query.set('source', errorsTableState.source);

        const res = await fetch(`${API_BASE}/errors?${query.toString()}`);
        const payload = await res.json();
        cachedErrors = payload.items || [];
        lastErrors = cachedErrors;
        renderErrorsTable(payload.pagination || emptyPagination(errorsTableState.page, errorsTableState.pageSize));
    } catch (e) {
        showToast('Failed to load logs', 'error');
    }
}

function renderErrorsTable(pagination) {
    const tbody = document.querySelector('#errors-table tbody');
    if (!tbody) return;
    if (cachedErrors.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">System is healthy. No recent error logs.</td></tr>';
    } else {
        tbody.innerHTML = cachedErrors.map(e => `
            <tr>
                <td class="text-muted">${new Date(e.created_at).toLocaleString()}</td>
                <td><span class="badge ${e.source === 'scraper' ? 'neutral' : 'warning'}">${escapeHTML(e.source || 'System')}</span></td>
                <td class="break-word" style="color: var(--danger); font-family: monospace; font-size: 13px;">${escapeHTML(e.message)}</td>
                <td><button class="btn small outline" onclick="openErrorModal(${e.id})">Inspect</button></td>
            </tr>
        `).join('');
    }

    updateTableSummary('errors', pagination, errorsTableState, {
        emptyLabel: 'Showing the newest log entries first.',
        filters: [
            errorsTableState.search ? `search: ${errorsTableState.search}` : '',
            errorsTableState.source ? `source: ${errorsTableState.source}` : ''
        ]
    });
    renderPagination('errors-pagination', pagination, (page) => {
        errorsTableState.page = page;
        fetchErrors();
    });
}

// ==================== Modals ====================
async function openJobModal(id) {
    try {
        const res = await fetch(`${API_BASE}/api/v1/jobs/posts/${id}`);
        if (!res.ok) throw new Error('Not found');
        const job = await res.json();
        
        document.getElementById('modal-job-title').innerText = job.name || 'Unknown Role';
        document.getElementById('modal-job-company').innerText = job.career_page_name || 'Unknown Company';
        document.getElementById('modal-job-location').innerText = `${job.city || ''} ${job.state || ''} ${job.country || ''}`.trim() || 'Remote / Global';
        
        const urlEl = document.getElementById('modal-job-url');
        if (job.job_url || job.career_page_url) {
            urlEl.href = job.job_url || job.career_page_url;
            urlEl.style.display = 'inline-flex';
        } else {
            urlEl.style.display = 'none';
        }
        
        document.getElementById('modal-job-desc').innerText = job.description || 'No description provided.';
        
        const skillsContainer = document.getElementById('modal-job-skills');
        try {
            const skillArray = job.skills ? JSON.parse(job.skills) : [];
            if (Array.isArray(skillArray) && skillArray.length) {
                skillsContainer.innerHTML = skillArray.map(s => `<span class="pill">${escapeHTML(s)}</span>`).join('');
            } else {
                skillsContainer.innerHTML = `<span class="pill">${escapeHTML(job.skills || 'None')}</span>`;
            }
        } catch { skillsContainer.innerHTML = `<span class="pill">${escapeHTML(job.skills || 'None')}</span>`; }

        const badgesContainer = document.getElementById('modal-job-badges');
        try {
            const badgeArray = job.badges ? JSON.parse(job.badges) : [];
            if (Array.isArray(badgeArray) && badgeArray.length) {
                badgesContainer.innerHTML = badgeArray.map(s => `<span class="pill">${escapeHTML(s)}</span>`).join('');
            } else {
                badgesContainer.innerHTML = `<span class="pill">${escapeHTML(job.badges || 'None')}</span>`;
            }
        } catch { badgesContainer.innerHTML = `<span class="pill">${escapeHTML(job.badges || 'None')}</span>`; }

        document.getElementById('job-modal').style.display = 'flex';
    } catch(e) {
        showToast('Failed to load job details', 'error');
    }
}

function openErrorModal(id) {
    const error = lastErrors.find(e => e.id === id);
    if (!error) return;
    
    document.getElementById('modal-err-id').innerText = error.id;
    document.getElementById('modal-err-time').innerText = new Date(error.created_at).toLocaleString();
    document.getElementById('modal-err-context').innerText = error.source || 'N/A';
    document.getElementById('modal-err-msg').innerText = error.message || 'No message';
    
    document.getElementById('error-modal').style.display = 'flex';
}

async function openProcessedModal(id) {
    try {
        const res = await fetch(`${API_BASE}/api/v1/jobs/${id}`);
        if (!res.ok) throw new Error('Not found');
        const pj = await res.json();
        
        document.getElementById('pj-title').innerText = pj.job_title || 'Processed Job';
        document.getElementById('pj-company').innerText = pj.company || 'Tech Enterprise';
        document.getElementById('pj-location').innerText = `${pj.city || ''} ${pj.state || ''}`.trim() || 'Global';
        document.getElementById('pj-contract').innerText = pj.contract_type || 'Full Time';
        document.getElementById('pj-salary').innerText = pj.salary ? `R$ ${pj.salary.toLocaleString()}` : 'Salary Undisclosed';
        
        const formatPills = (arr) => {
            if (!arr || arr.length === 0) return '<span class="text-muted">None</span>';
            return arr.map(s => `<span class="pill">${escapeHTML(s)}</span>`).join('');
        };
        
        document.getElementById('pj-hardskills').innerHTML = formatPills(pj.hard_skills);
        document.getElementById('pj-softskills').innerHTML = formatPills(pj.soft_skills);
        document.getElementById('pj-nicetohave').innerHTML = formatPills(pj.nice_to_have_skills);
        
        const stackStr = pj.tech_stack ? JSON.stringify(pj.tech_stack, null, 2) : '[]';
        document.getElementById('pj-techstack').innerText = stackStr;

        document.getElementById('processed-job-modal').style.display = 'flex';
    } catch(e) {
        showToast('Failed to load structured job details', 'error');
    }
}

function closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.style.display = 'none';
}

// Close modals when clicking overlay
document.querySelectorAll('.modal-overlay').forEach(el => {
    el.addEventListener('click', (e) => {
        if(e.target === el) el.style.display = 'none';
    });
});

// ==================== Pagination Renderer ====================
function renderPagination(containerId, pagination, onPageChange) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const currentPage = pagination.page || 1;
    const totalPages = pagination.total_pages || 1;
    const totalItems = pagination.total_items || 0;

    if (totalPages <= 1) {
        container.innerHTML = `<span class="page-info">${totalItems} item${totalItems !== 1 ? 's' : ''}</span>`;
        return;
    }

    let html = '';
    html += `<button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} data-page="1"><i class='bx bx-chevrons-left'></i></button>`;
    html += `<button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} data-page="${currentPage - 1}"><i class='bx bx-chevron-left'></i></button>`;

    const pages = getPageRange(currentPage, totalPages);
    let lastPage = 0;
    for (const p of pages) {
        if (p - lastPage > 1) {
            html += `<span class="page-info" style="margin: 0 2px;">…</span>`;
        }
        html += `<button class="page-btn ${p === currentPage ? 'active' : ''}" data-page="${p}">${p}</button>`;
        lastPage = p;
    }

    html += `<button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} data-page="${currentPage + 1}"><i class='bx bx-chevron-right'></i></button>`;
    html += `<button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} data-page="${totalPages}"><i class='bx bx-chevrons-right'></i></button>`;
    html += `<span class="page-summary">${formatPaginationRange(pagination)}</span>`;
    html += `<span class="page-info">${totalItems} items</span>`;

    container.innerHTML = html;

    container.querySelectorAll('.page-btn:not(:disabled)').forEach(btn => {
        btn.addEventListener('click', () => {
            const page = parseInt(btn.dataset.page);
            if (page >= 1 && page <= totalPages) onPageChange(page);
        });
    });
}

function getPageRange(current, total) {
    const range = [];
    if (total <= 7) {
        for (let i = 1; i <= total; i++) range.push(i);
    } else {
        range.push(1);
        let start = Math.max(2, current - 1);
        let end = Math.min(total - 1, current + 1);
        if (current <= 3) { start = 2; end = 5; }
        if (current >= total - 2) { start = total - 4; end = total - 1; }
        for (let i = start; i <= end; i++) range.push(i);
        range.push(total);
    }
    return [...new Set(range)].sort((a, b) => a - b);
}

// ==================== Utilities ====================
function emptyPagination(page = 1, pageSize = 20) {
    return { page, page_size: pageSize, total_items: 0, total_pages: 1, has_next: false, has_prev: false };
}

function formatPaginationRange(pagination) {
    if (!pagination.total_items) return 'No matching rows';
    const start = ((pagination.page - 1) * pagination.page_size) + 1;
    const end = Math.min(pagination.total_items, start + pagination.page_size - 1);
    return `Showing ${start}-${end}`;
}

function humanizeSort(sortValue) {
    return sortValue
        .replace('-', ' ')
        .replace('asc', 'ascending')
        .replace('desc', 'descending');
}

function updateTableSummary(prefix, pagination, _state, config = {}) {
    const totalBadge = document.getElementById(`${prefix}-total-badge`);
    const rangeBadge = document.getElementById(`${prefix}-range-badge`);
    const filtersEl = document.getElementById(`${prefix}-active-filters`);
    if (totalBadge) totalBadge.innerText = `${pagination.total_items || 0} result${pagination.total_items === 1 ? '' : 's'}`;
    if (rangeBadge) rangeBadge.innerText = `Page ${pagination.page || 1} of ${pagination.total_pages || 1}`;
    if (filtersEl) {
        const activeFilters = (config.filters || []).filter(Boolean);
        filtersEl.innerText = activeFilters.length ? `Active filters: ${activeFilters.join(' • ')}` : (config.emptyLabel || 'No filters applied.');
    }
}

function safeHostname(url) {
    try { return new URL(url).hostname; } catch { return 'Direct'; }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'bx-info-circle';
    if(type === 'success') icon = 'bx-check-circle';
    if(type === 'error') icon = 'bx-error';
    if(type === 'warning') icon = 'bx-error-circle';

    toast.innerHTML = `<i class='bx ${icon}'></i><span>${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 300);
    }, 3200);
}

function escapeHTML(str) {
    if(!str) return '';
    return str.toString().replace(/[&<>'"]/g, 
        tag => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
        }[tag] || tag)
    );
}
