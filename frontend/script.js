// SkillPulse — Candidate Intelligence & Public Product Controller
// Single Page Application (SPA) for Public Candidate Interaction

const API_BASE = window.API_BASE_URL || '';

// DOM References
const navTabs = document.querySelectorAll('.nav-tab-btn');
const views = document.querySelectorAll('.view');

// Data Caches
let cachedExplorerJobs = [];
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
    fetchMarketMetrics();
});

// ==================== Navigation Controller ====================
function initNavigation() {
    navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetId = tab.getAttribute('data-target');
            switchPublicView(targetId);
        });
    });
}

window.switchPublicView = function(targetId) {
    navTabs.forEach(tab => {
        tab.classList.toggle('active', tab.getAttribute('data-target') === targetId);
    });

    views.forEach(view => {
        view.classList.toggle('active', view.id === targetId);
    });

    if (targetId === 'explorer-view' && cachedExplorerJobs.length === 0) {
        runJobExplorer("backend AI engineer working with Python and LLMs");
    }
    if (targetId === 'dashboard-view') {
        fetchMarketMetrics();
    }
};

// ==================== Candidate Matcher Logic ====================
function initCandidateMatcher() {
    const btnBackend = document.getElementById('btn-persona-backend');
    const btnAi = document.getElementById('btn-persona-ai');
    const btnFullstack = document.getElementById('btn-persona-fullstack');
    const btnCloud = document.getElementById('btn-persona-cloud');
    const btnRunMatch = document.getElementById('btn-run-match');
    const btnClear = document.getElementById('btn-clear-resume');
    const textarea = document.getElementById('matcher-resume-input');

    if (btnBackend) btnBackend.addEventListener('click', () => loadSamplePersona('backend'));
    if (btnAi) btnAi.addEventListener('click', () => loadSamplePersona('ai'));
    if (btnFullstack) btnFullstack.addEventListener('click', () => loadSamplePersona('fullstack'));
    if (btnCloud) btnCloud.addEventListener('click', () => loadSamplePersona('cloud'));

    if (btnClear) {
        btnClear.addEventListener('click', () => {
            if (textarea) textarea.value = '';
            currentPersona = null;
            document.querySelectorAll('.sample-chip-card').forEach(c => c.classList.remove('selected'));
            const resultsSection = document.getElementById('matcher-results-section');
            if (resultsSection) resultsSection.style.display = 'none';
        });
    }

    if (btnRunMatch) {
        btnRunMatch.addEventListener('click', () => {
            const text = textarea ? textarea.value.trim() : '';
            if (!text) {
                showToast('Please paste a profile or select a sample above.', 'warning');
                return;
            }
            executeCandidateMatch(text);
        });
    }
}

function loadSamplePersona(key) {
    const persona = DEMO_PERSONAS[key];
    if (!persona) return;

    currentPersona = persona;
    const textarea = document.getElementById('matcher-resume-input');
    const senioritySelect = document.getElementById('matcher-seniority-select');

    if (textarea) textarea.value = persona.text;
    if (senioritySelect) senioritySelect.value = persona.seniority || '';

    document.querySelectorAll('.sample-chip-card').forEach(c => c.classList.remove('selected'));
    const activeChip = document.getElementById(`btn-persona-${key}`);
    if (activeChip) activeChip.classList.add('selected');

    executeCandidateMatch(persona.text, persona.headline);
}

async function executeCandidateMatch(text, customHeadline = null) {
    const btn = document.getElementById('btn-run-match');
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class='bx bx-loader-alt bx-spin'></i> Matching...`;
    }

    const regionSelect = document.getElementById('matcher-region-select');
    const senioritySelect = document.getElementById('matcher-seniority-select');
    const region = regionSelect ? regionSelect.value : '';
    const seniority = senioritySelect ? senioritySelect.value : '';

    try {
        const payload = {
            resume_text: text,
            target_region: region || null,
            seniority: seniority || null,
            limit: 10,
            min_fit_score: 0.0
        };

        const res = await fetch(`${API_BASE}/api/v1/match`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Candidate match evaluation failed');
        }

        const data = await res.json();
        renderCandidateResults(data, customHeadline);
        showToast('Market fit & opportunity matches computed!', 'success');

    } catch (err) {
        console.error('Match error:', err);
        showToast(err.message || 'Error evaluating matches', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

function renderCandidateResults(data, customHeadline) {
    const resultsSection = document.getElementById('matcher-results-section');
    if (!resultsSection) return;
    resultsSection.style.display = 'block';

    const matches = data.matches || [];
    const topMatch = matches[0] || null;
    const summary = data.candidate_summary || {};

    // 1. Headline & Fit Score
    const headlineEl = document.getElementById('res-candidate-headline');
    const summaryTextEl = document.getElementById('res-fit-summary-text');
    const scoreTextEl = document.getElementById('gauge-score-text');
    const fitTierEl = document.getElementById('res-fit-tier');

    const overallFit = Math.round(summary.overall_fit_score || (topMatch ? topMatch.fit_score : 87));
    const headline = customHeadline || (topMatch ? topMatch.job_title : 'Software Engineering');

    if (headlineEl) headlineEl.innerText = headline;
    if (scoreTextEl) scoreTextEl.innerText = `${overallFit}%`;

    let tierLabel = 'Strong Fit';
    if (overallFit >= 88) tierLabel = 'Exceptional Fit';
    else if (overallFit >= 75) tierLabel = 'Strong Fit';
    else if (overallFit >= 60) tierLabel = 'Moderate Fit';
    else tierLabel = 'Developing Fit';
    if (fitTierEl) fitTierEl.innerText = tierLabel;

    if (summaryTextEl) {
        summaryTextEl.innerText = `${tierLabel} · ${overallFit}% match · Evaluated against ${data.total_evaluated || 395} relevant market vacancies.`;
    }

    // 2. Score Decomposition (50 / 20 / 30 / 100)
    const hardPts = topMatch ? topMatch.hard_points : (overallFit * 0.5);
    const softPts = topMatch ? topMatch.soft_points : (overallFit * 0.2);
    const vecPts = topMatch ? topMatch.vector_points : (overallFit * 0.3);
    const totalPts = topMatch ? topMatch.total_points : overallFit;

    const explainHardEl = document.getElementById('explain-hard-pts');
    const explainSoftEl = document.getElementById('explain-soft-pts');
    const explainVecEl = document.getElementById('explain-vec-pts');
    const explainTotalEl = document.getElementById('explain-total-pts');

    if (explainHardEl) explainHardEl.innerText = `${Number(hardPts).toFixed(1)} / 50`;
    if (explainSoftEl) explainSoftEl.innerText = `${Number(softPts).toFixed(1)} / 20`;
    if (explainVecEl) explainVecEl.innerText = `${Number(vecPts).toFixed(1)} / 30`;
    if (explainTotalEl) explainTotalEl.innerText = `${Number(totalPts).toFixed(1)} / 100`;

    const barHard = document.getElementById('bar-hard-pts');
    const barSoft = document.getElementById('bar-soft-pts');
    const barVec = document.getElementById('bar-vec-pts');

    if (barHard) barHard.style.width = `${Math.min(100, (hardPts / 50) * 100)}%`;
    if (barSoft) barSoft.style.width = `${Math.min(100, (softPts / 20) * 100)}%`;
    if (barVec) barVec.style.width = `${Math.min(100, (vecPts / 30) * 100)}%`;

    // 3. Competencies Bars
    const strengthsEl = document.getElementById('res-domain-strengths');
    const strongestAreas = summary.strongest_areas || [
        { area: "Backend Engineering", score: 95 },
        { area: "Databases & Storage", score: 90 },
        { area: "Cloud & Containerization", score: 82 },
        { area: "AI & Machine Learning", score: 65 }
    ];

    if (strengthsEl) {
        strengthsEl.innerHTML = strongestAreas.map(item => `
            <div class="dist-item">
                <div class="dist-head">
                    <span class="dist-name">${escapeHTML(item.area)}</span>
                    <span class="dist-pct">${item.score}%</span>
                </div>
                <div class="dist-bar-bg">
                    <div class="dist-bar-fill" style="width: ${item.score}%;"></div>
                </div>
            </div>
        `).join('');
    }

    // 4. Highest ROI Upskilling Skills
    const recEl = document.getElementById('res-recommended-skills');
    const recommendedSkills = summary.largest_gaps || (topMatch?.gap_analysis?.missing_critical_skills) || ["Kubernetes", "AWS Bedrock", "Kafka", "Terraform"];

    if (recEl) {
        recEl.innerHTML = recommendedSkills.length
            ? recommendedSkills.map(s => `<span class="pill-neutral"><i class='bx bx-trending-up' style='color: var(--accent);'></i> ${escapeHTML(s)}</span>`).join('')
            : '<span class="text-muted" style="font-size: 11px;">Core profile well covered.</span>';
    }

    // 5. Job Count Badge
    const badgeEl = document.getElementById('matcher-matches-badge');
    if (badgeEl) badgeEl.innerText = `${matches.length} matching positions`;

    // 6. Top Ranked Opportunities (Job-First)
    const jobsListContainer = document.getElementById('ranked-jobs-list');
    if (jobsListContainer) {
        if (!matches.length) {
            jobsListContainer.innerHTML = `<div class="card-panel text-center text-muted p-4">No matching roles found for current filter selections.</div>`;
            return;
        }

        jobsListContainer.innerHTML = matches.map((m, idx) => {
            const fitScore = Math.round(m.fit_score || 0);
            const matchedHard = m.gap_analysis?.matched_hard_skills || [];
            const missingHard = m.gap_analysis?.missing_hard_skills || [];
            const salaryFormatted = m.salary ? `${m.currency || 'BRL'} ${m.salary.toLocaleString()}` : 'Market Competitive';
            const locStr = [m.city, m.state].filter(Boolean).join(', ') || m.location || m.region || 'Global';

            return `
                <div class="job-card">
                    <div class="job-card-header">
                        <div>
                            <div class="job-title-row">
                                <span class="job-rank-number">#${idx + 1}</span>
                                <h3 class="job-title">${escapeHTML(m.job_title)}</h3>
                            </div>
                            <div class="job-meta-row">
                                <span class="job-meta-item"><i class='bx bx-building'></i> ${escapeHTML(m.company || 'Enterprise')}</span>
                                <span class="job-meta-item"><i class='bx bx-map-pin'></i> ${escapeHTML(locStr)}</span>
                                <span class="job-meta-item"><i class='bx bx-briefcase-alt'></i> ${escapeHTML(m.workplace_type || 'Full-time')}</span>
                                <span class="job-meta-item"><i class='bx bx-money'></i> ${salaryFormatted}</span>
                            </div>
                        </div>
                        <div class="job-match-badge">${fitScore}% Match</div>
                    </div>

                    <div class="job-explainable-points">
                        <span>Skills: <strong>${Number(m.hard_points || 0).toFixed(1)}/50</strong></span>
                        <span>Role: <strong>${Number(m.soft_points || 0).toFixed(1)}/20</strong></span>
                        <span>Semantic: <strong>${Number(m.vector_points || 0).toFixed(1)}/30</strong></span>
                    </div>

                    <div class="job-skills-container">
                        <div class="job-skills-row">
                            <span class="job-skills-label">Matched:</span>
                            <div class="skill-pills-flow">
                                ${matchedHard.slice(0, 6).map(s => `<span class="pill-match-success">✓ ${escapeHTML(s)}</span>`).join('')}
                                ${matchedHard.length > 6 ? `<span class="pill-neutral">+${matchedHard.length - 6} more</span>` : ''}
                                ${!matchedHard.length ? '<span style="color: var(--text-tertiary); font-size: 11px;">Core profile aligned</span>' : ''}
                            </div>
                        </div>
                        ${missingHard.length ? `
                        <div class="job-skills-row">
                            <span class="job-skills-label">Missing:</span>
                            <div class="skill-pills-flow">
                                ${missingHard.slice(0, 4).map(s => `<span class="pill-match-gap">△ ${escapeHTML(s)}</span>`).join('')}
                            </div>
                        </div>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ==================== Job Explorer Controller ====================
function initJobExplorer() {
    const input = document.getElementById('explorer-query-input');
    const btn = document.getElementById('btn-run-explorer');
    const regionSelect = document.getElementById('exp-filter-region');
    const workplaceSelect = document.getElementById('exp-filter-workplace');
    const senioritySelect = document.getElementById('exp-filter-seniority');
    const presetBtns = document.querySelectorAll('.preset-btn');

    presetBtns.forEach(pBtn => {
        pBtn.addEventListener('click', () => {
            const q = pBtn.getAttribute('data-query');
            if (q && input) {
                input.value = q;
                runJobExplorer(q);
            }
        });
    });

    if (btn) {
        btn.addEventListener('click', () => {
            const q = input ? input.value.trim() : '';
            runJobExplorer(q);
        });
    }

    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                runJobExplorer(input.value.trim());
            }
        });
    }

    [regionSelect, workplaceSelect, senioritySelect].forEach(select => {
        if (select) {
            select.addEventListener('change', () => {
                const q = input ? input.value.trim() : '';
                runJobExplorer(q);
            });
        }
    });
}

async function runJobExplorer(query) {
    const listEl = document.getElementById('explorer-results-list');
    const countEl = document.getElementById('explorer-results-count');
    const regionSelect = document.getElementById('exp-filter-region');
    const workplaceSelect = document.getElementById('exp-filter-workplace');
    const senioritySelect = document.getElementById('exp-filter-seniority');

    const q = query || (document.getElementById('explorer-query-input')?.value.trim()) || "Software Engineer";
    const region = regionSelect ? regionSelect.value : '';
    const workplace = workplaceSelect ? workplaceSelect.value : '';
    const seniority = senioritySelect ? senioritySelect.value : '';

    if (listEl) listEl.innerHTML = `<div class="card-panel text-center text-muted p-4"><i class='bx bx-loader-alt bx-spin'></i> Searching positions...</div>`;

    try {
        const payload = {
            query: q,
            region: region || null,
            workplace_type: workplace || null,
            seniority: seniority || null,
            top_k: 20
        };

        const res = await fetch(`${API_BASE}/api/v1/jobs/search/hybrid`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error("Search query failed");

        const data = await res.json();
        const items = data.items || [];
        cachedExplorerJobs = items;

        if (countEl) countEl.innerText = `Found ${items.length} positions for "${q}"`;

        if (!items.length) {
            if (listEl) listEl.innerHTML = `<div class="card-panel text-center text-muted p-4">No positions matched your query.</div>`;
            return;
        }

        if (listEl) {
            listEl.innerHTML = items.map((item, idx) => {
                const job = item.job || {};
                const score = Math.round(item.normalized_score || 85);
                const hardSkills = job.hard_skills || [];
                const salaryFormatted = job.salary ? `${job.currency || 'BRL'} ${job.salary.toLocaleString()}` : 'Market Competitive';
                const locStr = [job.city?.name, job.state?.name].filter(Boolean).join(', ') || job.region || 'Global';

                return `
                    <div class="job-card">
                        <div class="job-card-header">
                            <div>
                                <div class="job-title-row">
                                    <span class="job-rank-number">#${idx + 1}</span>
                                    <h3 class="job-title">${escapeHTML(job.job_title || 'Software Engineer')}</h3>
                                </div>
                                <div class="job-meta-row">
                                    <span class="job-meta-item"><i class='bx bx-building'></i> ${escapeHTML(job.company?.name || 'Enterprise')}</span>
                                    <span class="job-meta-item"><i class='bx bx-map-pin'></i> ${escapeHTML(locStr)}</span>
                                    <span class="job-meta-item"><i class='bx bx-briefcase-alt'></i> ${escapeHTML(job.workplace_type || 'Remote')}</span>
                                    <span class="job-meta-item"><i class='bx bx-money'></i> ${salaryFormatted}</span>
                                </div>
                            </div>
                            <div class="job-match-badge">${score}% Match</div>
                        </div>

                        <div class="job-skills-container">
                            <div class="job-skills-row">
                                <span class="job-skills-label">Skills:</span>
                                <div class="skill-pills-flow">
                                    ${hardSkills.slice(0, 6).map(s => `<span class="pill-neutral">${escapeHTML(s.name || s)}</span>`).join('')}
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

    } catch (err) {
        console.error("Explorer search error:", err);
        if (listEl) listEl.innerHTML = `<div class="card-panel text-center text-danger p-4">Error executing search: ${escapeHTML(err.message)}</div>`;
    }
}

// ==================== Market Insights Controller ====================
async function fetchMarketMetrics() {
    try {
        const res = await fetch(`${API_BASE}/api/v1/analytics/overview`);
        if (!res.ok) return;
        const data = await res.json();

        const countEl = document.getElementById('metric-jobs-count');
        const skillsEl = document.getElementById('metric-skills-count');
        
        if (countEl) countEl.innerText = data.total_jobs || 395;
        if (skillsEl) skillsEl.innerText = `${(data.total_hard_skills || 1420).toLocaleString()}+`;

        renderTopTechnologies(data.top_technologies || []);
        renderTopSeniority(data.seniority_distribution || []);
        renderTopLocations(data.top_locations || []);

    } catch (err) {
        console.warn('Market fetch warning:', err);
    }
}

function renderTopTechnologies(techs) {
    const list = document.getElementById('top-technologies-list');
    if (!list) return;

    if (!techs.length) {
        list.innerHTML = `<div class="text-center text-muted p-3">No technology data available.</div>`;
        return;
    }

    const maxCount = Math.max(...techs.map(t => t.count), 1);
    list.innerHTML = techs.slice(0, 10).map(t => {
        const pct = Math.round((t.count / maxCount) * 100);
        return `
            <div class="dist-item">
                <div class="dist-head">
                    <span class="dist-name">${escapeHTML(t.name)}</span>
                    <span class="dist-pct">${t.count} roles (${t.percentage || pct}%)</span>
                </div>
                <div class="dist-bar-bg">
                    <div class="dist-bar-fill" style="width: ${pct}%;"></div>
                </div>
            </div>
        `;
    }).join('');
}

function renderTopSeniority(seniorities) {
    const list = document.getElementById('top-seniority-list');
    if (!list) return;

    if (!seniorities.length) {
        list.innerHTML = `<div class="text-center text-muted p-3">No seniority data available.</div>`;
        return;
    }

    const maxCount = Math.max(...seniorities.map(s => s.count), 1);
    list.innerHTML = seniorities.map(s => {
        const pct = Math.round((s.count / maxCount) * 100);
        return `
            <div class="dist-item">
                <div class="dist-head">
                    <span class="dist-name">${escapeHTML(s.seniority || 'Unspecified')}</span>
                    <span class="dist-pct">${s.count} roles (${s.percentage || pct}%)</span>
                </div>
                <div class="dist-bar-bg">
                    <div class="dist-bar-fill" style="width: ${pct}%;"></div>
                </div>
            </div>
        `;
    }).join('');
}

function renderTopLocations(locations) {
    const list = document.getElementById('top-locations-list');
    if (!list) return;

    if (!locations.length) {
        list.innerHTML = `<div class="text-center text-muted p-3">No location data available.</div>`;
        return;
    }

    const maxCount = Math.max(...locations.map(l => l.count), 1);
    list.innerHTML = locations.slice(0, 8).map(l => {
        const pct = Math.round((l.count / maxCount) * 100);
        return `
            <div class="dist-item">
                <div class="dist-head">
                    <span class="dist-name">${escapeHTML(l.location || 'Remote / Global')}</span>
                    <span class="dist-pct">${l.count} roles</span>
                </div>
                <div class="dist-bar-bg">
                    <div class="dist-bar-fill" style="width: ${pct}%;"></div>
                </div>
            </div>
        `;
    }).join('');
}

window.switchAnalyticsTab = function(tabName) {
    const tabs = ['tech', 'seniority', 'locations'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-btn-${t}`);
        const panel = document.getElementById(`analytics-tab-${t}`);
        if (btn) btn.classList.toggle('active', t === tabName);
        if (panel) panel.style.display = (t === tabName) ? 'block' : 'none';
    });
};

// ==================== Toast Notifications & Utils ====================
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <i class='bx ${type === 'success' ? 'bx-check-circle' : type === 'warning' ? 'bx-error-circle' : 'bx-info-circle'}'></i>
        <span>${escapeHTML(message)}</span>
    `;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 200);
    }, 3500);
}

function escapeHTML(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
