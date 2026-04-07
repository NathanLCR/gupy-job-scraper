// DOM Elements
const views = document.querySelectorAll('.view');
const navItems = document.querySelectorAll('.nav-item');
const pageTitle = document.getElementById('page-title');

// Base URL
const API_BASE = '';

// Chart Instance
let pollTimeout = null;
let extractorPollTimeout = null;

// ==================== Data Caches ====================
let cachedJobs = [];
let cachedProcessedJobs = [];
let cachedErrors = [];
let lastErrors = [];

// ==================== Initialization ====================
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initActionButtons();
    initToolbars();
    
    // Initial Data Fetches
    fetchDashboardMetrics();
    fetchScrapeStatus();
    fetchExtractorStatus();
    
    // Setup long polling
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
            document.getElementById(targetId).classList.add('active');
            
            pageTitle.innerText = item.innerText.trim();
            if (targetId === 'jobs-view') fetchJobs();
            if (targetId === 'processed-jobs-view') fetchProcessedJobs();
            if (targetId === 'terms-view') fetchSearchTerms();
            if (targetId === 'errors-view') fetchErrors();
            if (targetId === 'dashboard-view') fetchDashboardMetrics();
        });
    });
}

// ==================== Toolbar Initialization ====================
function initToolbars() {
    // Jobs View
    document.getElementById('jobs-search').addEventListener('input', debounce(() => renderJobsTable(), 250));
    document.getElementById('jobs-filter-workplace').addEventListener('change', () => renderJobsTable());
    document.getElementById('jobs-sort').addEventListener('change', () => renderJobsTable());
    document.getElementById('jobs-page-size').addEventListener('change', () => { jobsCurrentPage = 1; renderJobsTable(); });

    // Processed Jobs View
    document.getElementById('pj-search').addEventListener('input', debounce(() => renderProcessedJobsTable(), 250));
    document.getElementById('pj-sort').addEventListener('change', () => renderProcessedJobsTable());
    document.getElementById('pj-page-size').addEventListener('change', () => { pjCurrentPage = 1; renderProcessedJobsTable(); });

    // Errors View
    document.getElementById('errors-search').addEventListener('input', debounce(() => renderErrorsTable(), 250));
    document.getElementById('errors-filter-source').addEventListener('change', () => renderErrorsTable());
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
    const triggerScrape = async (mode) => {
        try {
            const res = await fetch(`${API_BASE}/scrape/start?mode=${mode}`, { method: 'POST' });
            const data = await res.json();
            if (res.ok || res.status === 202) {
                showToast(`Started ${mode} scrape successfully!`, 'success');
                fetchScrapeStatus();
            } else {
                showToast(data.error || 'Failed to start scrape.', 'error');
            }
        } catch (e) {
            showToast('Connection error.', 'error');
        }
    };

    document.getElementById('btn-scrape-incremental').addEventListener('click', () => triggerScrape('incremental'));
    document.getElementById('dash-btn-scrape').addEventListener('click', () => triggerScrape('incremental'));
    document.getElementById('dash-btn-populate').addEventListener('click', () => triggerScrape('populate'));
    
    // Extractor
    document.getElementById('btn-extract').addEventListener('click', async () => {
        try {
            const res = await fetch(`${API_BASE}/regex-extract`, { method: 'POST' });
            const data = await res.json();
            if (res.ok || res.status === 202) {
                showToast(data.message || 'Feature extraction started.', 'success');
                fetchExtractorStatus();
            } else {
                showToast(data.error || 'Failed to extract features.', 'error');
            }
        } catch (e) {
            showToast('Connection error.', 'error');
        }
    });

    // CSV Export
    document.getElementById('btn-export-csv').addEventListener('click', () => {
        window.location.href = `${API_BASE}/job-posts/export`;
    });

    // Term Add View Toggle
    document.getElementById('btn-add-term').addEventListener('click', () => {
        document.getElementById('add-term-form').style.display = 'flex';
        document.getElementById('new-term-input').focus();
    });
    document.getElementById('btn-cancel-term').addEventListener('click', () => {
        document.getElementById('add-term-form').style.display = 'none';
        document.getElementById('new-term-input').value = '';
    });
    
    // Add Term Submit
    document.getElementById('btn-submit-term').addEventListener('click', async () => {
        const input = document.getElementById('new-term-input');
        const term = input.value.trim();
        if (!term) return showToast('Please enter a term', 'warning');
        
        try {
            const res = await fetch(`${API_BASE}/search-terms`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ term, is_active: true })
            });
            const data = await res.json();
            if (res.ok || res.status === 201) {
                showToast('Term added', 'success');
                input.value = '';
                document.getElementById('add-term-form').style.display = 'none';
                fetchSearchTerms();
                fetchDashboardMetrics();
            } else {
                showToast(data.error || 'Failed to add term', 'error');
            }
        } catch(e) { showToast('Connection error', 'error'); }
    });

    // Refresh buttons
    document.getElementById('btn-refresh-errors').addEventListener('click', fetchErrors);
    if (document.getElementById('btn-refresh-processed')) {
        document.getElementById('btn-refresh-processed').addEventListener('click', fetchProcessedJobs);
    }
}

// ==================== Scraper Status ====================
async function fetchScrapeStatus() {
    try {
        const res = await fetch(`${API_BASE}/scrape/status`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        updateScrapeStatusUI(data);
    } catch (e) {
        document.getElementById('sys-status').innerText = 'Backend Unreachable';
        document.getElementById('sys-status').className = 'badge danger';
    }
}

function pollScrapeStatus() {
    if (pollTimeout) clearTimeout(pollTimeout);
    fetchScrapeStatus();
    pollTimeout = setTimeout(pollScrapeStatus, 5000);
}

function updateScrapeStatusUI(data) {
    const statusEl = document.getElementById('sys-status');
    const pillText = document.getElementById('global-status-text');
    const pillInd = document.querySelector('#global-status-pill .status-indicator');

    document.getElementById('sys-mode').innerText = data.mode || '--';
    document.getElementById('sys-started').innerText = data.started_at ? new Date(data.started_at).toLocaleString() : '--';
    
    if (data.running) {
        statusEl.innerText = 'RUNNING';
        statusEl.className = 'badge success';
        pillText.innerText = `Scraping (${data.mode})...`;
        pillInd.className = 'status-indicator running';
        document.getElementById('sys-finished').innerText = 'In Progress...';
    } else {
        if (data.error) {
            statusEl.innerText = 'ERROR';
            statusEl.className = 'badge danger';
            pillText.innerText = 'System Fault';
            pillInd.className = 'status-indicator error';
        } else {
            statusEl.innerText = 'IDLE';
            statusEl.className = 'badge neutral';
            pillText.innerText = 'System Idle';
            pillInd.className = 'status-indicator';
        }
        document.getElementById('sys-finished').innerText = data.finished_at ? new Date(data.finished_at).toLocaleString() : '--';
    }
}

// ==================== Extractor Status ====================
async function fetchExtractorStatus() {
    try {
        const res = await fetch(`${API_BASE}/regex-extract/status`);
        if (!res.ok) return;
        const data = await res.json();
        updateExtractorStatusUI(data);
    } catch (e) {
        // Silently fail - endpoint may not exist
    }
}

function pollExtractorStatus() {
    if (extractorPollTimeout) clearTimeout(extractorPollTimeout);
    fetchExtractorStatus();
    extractorPollTimeout = setTimeout(pollExtractorStatus, 5000);
}

function updateExtractorStatusUI(data) {
    const pillText = document.getElementById('extractor-status-text');
    const pillInd = document.getElementById('extractor-indicator');
    const extStatus = document.getElementById('ext-status');
    const extStarted = document.getElementById('ext-started');
    const extFinished = document.getElementById('ext-finished');

    if (data.running) {
        pillText.innerText = 'Extracting...';
        pillInd.className = 'status-indicator running';
        if (extStatus) { extStatus.innerText = 'RUNNING'; extStatus.className = 'badge success'; }
        if (extStarted) extStarted.innerText = data.started_at ? new Date(data.started_at).toLocaleString() : '--';
        if (extFinished) extFinished.innerText = 'In Progress...';
    } else {
        if (data.error) {
            pillText.innerText = 'Extractor Error';
            pillInd.className = 'status-indicator error';
            if (extStatus) { extStatus.innerText = 'ERROR'; extStatus.className = 'badge danger'; }
        } else {
            pillText.innerText = 'Extractor Idle';
            pillInd.className = 'status-indicator';
            if (extStatus) { extStatus.innerText = 'IDLE'; extStatus.className = 'badge neutral'; }
        }
        if (extStarted) extStarted.innerText = data.started_at ? new Date(data.started_at).toLocaleString() : '--';
        if (extFinished) extFinished.innerText = data.finished_at ? new Date(data.finished_at).toLocaleString() : '--';
    }
}

// ==================== Dashboard Metrics ====================
async function fetchDashboardMetrics() {
    try {
        const [statsRes, errorsRes, avgRes, salaryRes, techRes, locRes] = await Promise.all([
            fetch(`${API_BASE}/stats`),
            fetch(`${API_BASE}/errors?limit=50`),
            fetch(`${API_BASE}/features/average-job-post-daily`),
            fetch(`${API_BASE}/features/average-salary`),
            fetch(`${API_BASE}/features/top-5-technologies`),
            fetch(`${API_BASE}/features/top-5-locations`)
        ]);

        const stats = await statsRes.json();
        const errors = await errorsRes.json();
        const avgDaily = await avgRes.json();
        const avgSalary = await salaryRes.json();
        const technologies = await techRes.json();
        const locations = await locRes.json();

        document.getElementById('metric-jobs-count').innerText = stats.total_jobs || 0;
        document.getElementById('metric-processed-count').innerText = stats.total_processed || 0;
        document.getElementById('metric-terms-count').innerText = stats.total_terms || 0;
        document.getElementById('metric-errors-count').innerText = stats.total_errors || 0;
        
        // Display average formatted to 2 decimals
        const avgVal = parseFloat(avgDaily);
        document.getElementById('metric-avg-daily').innerText = isNaN(avgVal) ? '0.00' : avgVal.toFixed(2);
        
        // Display average salary
        const salaryVal = parseFloat(avgSalary);
        document.getElementById('metric-avg-salary').innerText = isNaN(salaryVal) ? 'N/A' : `R$${salaryVal.toFixed(0)}`;
        
        // Display Top 5 Technologies
        const techList = document.getElementById('top-technologies-list');
        if (technologies.length === 0) {
            techList.innerHTML = '<div class="text-center text-muted">No data available</div>';
        } else {
            techList.innerHTML = technologies.map(tech => `
                <div class="list-item">
                    <span class="list-item-name">${escapeHTML(tech.name)}</span>
                    <span class="list-item-count">${tech.count}</span>
                </div>
            `).join('');
        }
        
        // Display Top 5 Locations
        const locList = document.getElementById('top-locations-list');
        if (locations.length === 0) {
            locList.innerHTML = '<div class="text-center text-muted">No data available</div>';
        } else {
            locList.innerHTML = locations.map(loc => `
                <div class="list-item">
                    <span class="list-item-name">${escapeHTML(loc.name)}</span>
                    <span class="list-item-count">${loc.count}</span>
                </div>
            `).join('');
        }

    } catch (e) {
        console.error('Metrics fetch error', e);
    }
}


// ==================== Job Posts (with client-side pagination, search, sort, filter) ====================
let jobsCurrentPage = 1;

async function fetchJobs() {
    try {
        const res = await fetch(`${API_BASE}/job-posts?limit=500`);
        cachedJobs = await res.json();
        jobsCurrentPage = 1;
        renderJobsTable();
    } catch (e) {
        showToast('Failed to load jobs', 'error');
    }
}

function renderJobsTable() {
    const tbody = document.querySelector('#jobs-table tbody');
    const search = (document.getElementById('jobs-search').value || '').toLowerCase();
    const workplaceFilter = document.getElementById('jobs-filter-workplace').value.toLowerCase();
    const sortKey = document.getElementById('jobs-sort').value;
    const pageSize = parseInt(document.getElementById('jobs-page-size').value);

    // Filter
    let filtered = cachedJobs.filter(j => {
        const matchSearch = !search || 
            (j.name || '').toLowerCase().includes(search) ||
            (j.career_page_name || '').toLowerCase().includes(search) ||
            (j.city || '').toLowerCase().includes(search) ||
            (j.state || '').toLowerCase().includes(search);
        const matchWorkplace = !workplaceFilter || (j.workplace_type || '').toLowerCase().includes(workplaceFilter);
        return matchSearch && matchWorkplace;
    });

    // Sort
    filtered = sortArray(filtered, sortKey, {
        'date-desc': (a, b) => new Date(b.published_date || 0) - new Date(a.published_date || 0),
        'date-asc': (a, b) => new Date(a.published_date || 0) - new Date(b.published_date || 0),
        'name-asc': (a, b) => (a.name || '').localeCompare(b.name || ''),
        'name-desc': (a, b) => (b.name || '').localeCompare(a.name || ''),
    });

    // Paginate
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    if (jobsCurrentPage > totalPages) jobsCurrentPage = totalPages;
    const start = (jobsCurrentPage - 1) * pageSize;
    const paged = filtered.slice(start, start + pageSize);

    if (paged.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No jobs found.</td></tr>';
    } else {
        tbody.innerHTML = paged.map(j => `
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

    renderPagination('jobs-pagination', jobsCurrentPage, totalPages, filtered.length, (p) => { jobsCurrentPage = p; renderJobsTable(); });
}

// ==================== Processed Jobs (with client-side pagination, search, sort) ====================
let pjCurrentPage = 1;

async function fetchProcessedJobs() {
    try {
        const res = await fetch(`${API_BASE}/jobs?limit=500`);
        cachedProcessedJobs = await res.json();
        pjCurrentPage = 1;
        renderProcessedJobsTable();
    } catch (e) {
        showToast('Failed to load structured jobs', 'error');
    }
}

function renderProcessedJobsTable() {
    const tbody = document.querySelector('#processed-jobs-table tbody');
    const search = (document.getElementById('pj-search').value || '').toLowerCase();
    const sortKey = document.getElementById('pj-sort').value;
    const pageSize = parseInt(document.getElementById('pj-page-size').value);

    // Filter
    let filtered = cachedProcessedJobs.filter(j => {
        return !search || 
            (j.job_title || '').toLowerCase().includes(search) ||
            (j.company || '').toLowerCase().includes(search) ||
            (j.city || '').toLowerCase().includes(search) ||
            (j.state || '').toLowerCase().includes(search);
    });

    // Sort
    filtered = sortArray(filtered, sortKey, {
        'id-desc': (a, b) => b.id - a.id,
        'id-asc': (a, b) => a.id - b.id,
        'title-asc': (a, b) => (a.job_title || '').localeCompare(b.job_title || ''),
        'title-desc': (a, b) => (b.job_title || '').localeCompare(a.job_title || ''),
        'salary-desc': (a, b) => (b.salary || 0) - (a.salary || 0),
        'salary-asc': (a, b) => (a.salary || 0) - (b.salary || 0),
    });

    // Paginate
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    if (pjCurrentPage > totalPages) pjCurrentPage = totalPages;
    const start = (pjCurrentPage - 1) * pageSize;
    const paged = filtered.slice(start, start + pageSize);

    if (paged.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No structured jobs found.</td></tr>';
    } else {
        tbody.innerHTML = paged.map(j => `
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

    renderPagination('pj-pagination', pjCurrentPage, totalPages, filtered.length, (p) => { pjCurrentPage = p; renderProcessedJobsTable(); });
}

// ==================== Search Terms ====================
async function fetchSearchTerms() {
    try {
        const res = await fetch(`${API_BASE}/search-terms`);
        const terms = await res.json();
        const tbody = document.querySelector('#terms-table tbody');
        
        if (terms.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No search terms configured.</td></tr>';
            return;
        }

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
    } catch(e) {
        showToast('Failed to load terms', 'error');
    }
}

window.toggleTerm = async (id, isActive) => {
    try {
        await fetch(`${API_BASE}/search-terms/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: isActive })
        });
        showToast('Term updated', 'success');
        fetchDashboardMetrics();
    } catch(e) {
        showToast('Update failed', 'error');
        fetchSearchTerms();
    }
};

window.deleteTerm = async (id) => {
    if (!confirm('Are you sure you want to delete this term?')) return;
    try {
        await fetch(`${API_BASE}/search-terms/${id}`, { method: 'DELETE' });
        showToast('Term deleted', 'success');
        fetchSearchTerms();
        fetchDashboardMetrics();
    } catch(e) {
        showToast('Delete failed', 'error');
    }
};

// ==================== Errors (with client-side search, filter, pagination) ====================
let errorsCurrentPage = 1;

async function fetchErrors() {
    try {
        const res = await fetch(`${API_BASE}/errors?limit=200`);
        cachedErrors = await res.json();
        lastErrors = cachedErrors;
        errorsCurrentPage = 1;
        renderErrorsTable();
    } catch (e) {
        showToast('Failed to load errors', 'error');
    }
}

function renderErrorsTable() {
    const tbody = document.querySelector('#errors-table tbody');
    const search = (document.getElementById('errors-search').value || '').toLowerCase();
    const sourceFilter = document.getElementById('errors-filter-source').value;
    const pageSize = 20;

    let filtered = cachedErrors.filter(e => {
        const matchSearch = !search || 
            (e.message || '').toLowerCase().includes(search) ||
            (e.source || '').toLowerCase().includes(search) ||
            (e.term || '').toLowerCase().includes(search);
        const matchSource = !sourceFilter || (e.source || '') === sourceFilter;
        return matchSearch && matchSource;
    });

    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    if (errorsCurrentPage > totalPages) errorsCurrentPage = totalPages;
    const start = (errorsCurrentPage - 1) * pageSize;
    const paged = filtered.slice(start, start + pageSize);

    if (paged.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">System is healthy. No recent errors.</td></tr>';
    } else {
        tbody.innerHTML = paged.map(e => `
            <tr>
                <td class="text-muted">${new Date(e.created_at).toLocaleString()}</td>
                <td><span class="badge ${e.source === 'scraper' ? 'neutral' : 'warning'}">${escapeHTML(e.source || 'System')}</span></td>
                <td class="break-word" style="color: var(--danger); font-family: monospace; font-size: 13px;">${escapeHTML(e.message)}</td>
                <td><button class="btn small outline" onclick="openErrorModal(${e.id})">Inspect</button></td>
            </tr>
        `).join('');
    }

    renderPagination('errors-pagination', errorsCurrentPage, totalPages, filtered.length, (p) => { errorsCurrentPage = p; renderErrorsTable(); });
}

// ==================== Modals ====================
async function openJobModal(id) {
    try {
        const res = await fetch(`${API_BASE}/job-posts/${id}`);
        if (!res.ok) throw new Error('Not found');
        const job = await res.json();
        
        document.getElementById('modal-job-title').innerText = job.name || 'Unknown Role';
        document.getElementById('modal-job-company').innerText = job.career_page_name || 'Unknown Company';
        document.getElementById('modal-job-location').innerText = `${job.city || ''} ${job.state || ''} ${job.country || ''}`.trim() || 'Remote / Unknown';
        
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
        
        document.getElementById('modal-job-disabilities').innerText = job.disabilities ? "Yes" : (job.disabilities === false ? "No" : "Not specified");

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
    document.getElementById('modal-err-term').innerText = error.term || 'N/A';
    document.getElementById('modal-err-page').innerText = error.page || 'N/A';
    
    document.getElementById('modal-err-msg').innerText = error.message || 'No message';
    
    try {
        const formattedPayload = error.payload ? JSON.stringify(JSON.parse(error.payload), null, 2) : 'No payload';
        document.getElementById('modal-err-payload').innerText = formattedPayload;
    } catch(e) {
        document.getElementById('modal-err-payload').innerText = error.payload || 'No payload';
    }
    
    document.getElementById('error-modal').style.display = 'flex';
}

async function openProcessedModal(id) {
    try {
        const res = await fetch(`${API_BASE}/jobs/${id}`);
        if (!res.ok) throw new Error('Not found');
        const pj = await res.json();
        
        document.getElementById('pj-title').innerText = pj.job_title || 'Processed Job';
        document.getElementById('pj-company').innerText = pj.company || 'Unknown Company';
        document.getElementById('pj-location').innerText = `${pj.city || ''} ${pj.state || ''}`.trim() || 'Location TBD';
        document.getElementById('pj-contract').innerText = pj.contract_type || 'Full Time';
        document.getElementById('pj-salary').innerText = pj.salary ? `R$${pj.salary.toLocaleString()}` : 'Salary Undisclosed';
        
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
    document.getElementById(modalId).style.display = 'none';
}

// Close modals when clicking overlay
document.querySelectorAll('.modal-overlay').forEach(el => {
    el.addEventListener('click', (e) => {
        if(e.target === el) el.style.display = 'none';
    });
});

// ==================== Pagination Renderer ====================
function renderPagination(containerId, currentPage, totalPages, totalItems, onPageChange) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (totalPages <= 1) {
        container.innerHTML = `<span class="page-info">${totalItems} item${totalItems !== 1 ? 's' : ''}</span>`;
        return;
    }

    let html = '';

    // Prev button
    html += `<button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} data-page="${currentPage - 1}"><i class='bx bx-chevron-left'></i></button>`;

    // Page numbers with smart ellipsis
    const pages = getPageRange(currentPage, totalPages);
    let lastPage = 0;
    for (const p of pages) {
        if (p - lastPage > 1) {
            html += `<span class="page-info" style="margin: 0 2px;">…</span>`;
        }
        html += `<button class="page-btn ${p === currentPage ? 'active' : ''}" data-page="${p}">${p}</button>`;
        lastPage = p;
    }

    // Next button
    html += `<button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} data-page="${currentPage + 1}"><i class='bx bx-chevron-right'></i></button>`;

    // Info
    html += `<span class="page-info">${totalItems} items</span>`;

    container.innerHTML = html;

    // Bind click events
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
function sortArray(arr, key, sorters) {
    const fn = sorters[key];
    if (fn) return [...arr].sort(fn);
    return arr;
}

function safeHostname(url) {
    try { return new URL(url).hostname; } catch { return 'Direct'; }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
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
    }, 3000);
}

function escapeHTML(str) {
    if(!str) return '';
    return str.toString().replace(/[&<>'"]/g, 
        tag => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
        }[tag] || tag)
    );
}
