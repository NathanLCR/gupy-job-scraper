// DOM Elements
const views = document.querySelectorAll('.view');
const navItems = document.querySelectorAll('.nav-item');
const pageTitle = document.getElementById('page-title');

// Base URL (Assuming frontend is served from the same host, use relative paths)
const API_BASE = '';

// Chart Instance
let errorChartInstance = null;
let pollTimeout = null;

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initActionButtons();
    
    // Initial Data Fetches
    fetchDashboardMetrics();
    fetchScrapeStatus();
    
    // Setup long polling for scraper status
    pollScrapeStatus();
});

// --- Navigation ---
function initNavigation() {
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Update active states
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            // Switch view
            const targetId = item.getAttribute('data-target');
            views.forEach(view => view.classList.remove('active'));
            document.getElementById(targetId).classList.add('active');
            
            // Trigger specific view loads
            pageTitle.innerText = item.innerText.trim();
            if (targetId === 'jobs-view') fetchJobs();
            if (targetId === 'processed-jobs-view') fetchProcessedJobs();
            if (targetId === 'terms-view') fetchSearchTerms();
            if (targetId === 'errors-view') fetchErrors();
            if (targetId === 'dashboard-view') fetchDashboardMetrics();
        });
    });
}

function initActionButtons() {
    // Scraper triggers
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
            if (res.ok) {
                showToast(data.message || 'Features extracted.', 'success');
            } else {
                showToast('Failed to extract features.', 'error');
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

    // Refresh Errors
    document.getElementById('btn-refresh-errors').addEventListener('click', fetchErrors);
    
    // Refresh Processed Jobs
    if (document.getElementById('btn-refresh-processed')) {
        document.getElementById('btn-refresh-processed').addEventListener('click', fetchProcessedJobs);
    }
}

// --- API Fetches & Renders ---

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
    const pillInd = document.querySelector('.status-indicator');

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

async function fetchDashboardMetrics() {
    try {
        const [statsRes, errorsRes] = await Promise.all([
            fetch(`${API_BASE}/stats`),
            fetch(`${API_BASE}/errors?limit=50`)
        ]);

        const stats = await statsRes.json();
        const errors = await errorsRes.json();

        document.getElementById('metric-jobs-count').innerText = stats.total_jobs || 0;
        document.getElementById('metric-processed-count').innerText = stats.total_processed || 0;
        document.getElementById('metric-terms-count').innerText = stats.total_terms || 0;
        document.getElementById('metric-errors-count').innerText = stats.total_errors || 0;

        renderErrorChart(errors);

    } catch (e) {
        console.error('Metrics fetch error', e);
    }
}

async function fetchJobs() {
    try {
        const res = await fetch(`${API_BASE}/job-posts?limit=100`);
        const jobs = await res.json();
        const tbody = document.querySelector('#jobs-table tbody');
        
        if (!jobs || jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No jobs found.</td></tr>';
            return;
        }

        tbody.innerHTML = jobs.map(j => `
            <tr>
                <td class="text-muted">#${j.id}</td>
                <td><strong>${escapeHTML(j.name)}</strong></td>
                <td>${escapeHTML(j.career_page_name || 'N/A')}</td>
                <td>${escapeHTML(j.city || '')} / ${escapeHTML(j.state || '')}</td>
                <td>${escapeHTML(j.workplace_type || '')}</td>
                <td>${j.published_date ? new Date(j.published_date).toLocaleDateString() : 'N/A'}</td>
                <td><span class="badge neutral">${escapeHTML(j.career_page_url ? new URL(j.career_page_url).hostname : 'Direct')}</span></td>
                <td><button class="btn small outline" onclick="openJobModal(${j.id})">Details</button></td>
            </tr>
        `).join('');
    } catch (e) {
        showToast('Failed to load jobs', 'error');
    }
}

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
        fetchSearchTerms(); // revert row
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

// store global errors to avoid refetching on click
let lastErrors = [];

async function fetchErrors() {
    try {
        const res = await fetch(`${API_BASE}/errors?limit=50`);
        const errors = await res.json();
        lastErrors = errors;
        const tbody = document.querySelector('#errors-table tbody');
        
        if (!errors || errors.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">System is healthy. No recent errors.</td></tr>';
            return;
        }

        tbody.innerHTML = errors.map(e => `
            <tr>
                <td class="text-muted">${new Date(e.created_at).toLocaleString()}</td>
                <td><span class="badge ${e.source === 'scraper' ? 'neutral' : 'warning'}">${escapeHTML(e.source || 'System')}</span></td>
                <td class="break-word" style="color: var(--danger); font-family: monospace; font-size: 13px;">${escapeHTML(e.message)}</td>
                <td><button class="btn small outline" onclick="openErrorModal(${e.id})">Inspect</button></td>
            </tr>
        `).join('');
    } catch (e) {
        showToast('Failed to load errors', 'error');
    }
}

async function fetchProcessedJobs() {
    try {
        const res = await fetch(`${API_BASE}/jobs?limit=100`);
        const jobs = await res.json();
        const tbody = document.querySelector('#processed-jobs-table tbody');
        
        if (!jobs || jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No structured jobs found.</td></tr>';
            return;
        }

        tbody.innerHTML = jobs.map(j => `
            <tr>
                <td class="text-muted">#${j.id}</td>
                <td><strong>${escapeHTML(j.job_title)}</strong></td>
                <td>${escapeHTML(j.company || 'N/A')}</td>
                <td>${escapeHTML(j.city || '')} ${escapeHTML(j.state || '')}</td>
                <td><span class="badge success">${j.salary ? '$' + j.salary : 'N/A'}</span></td>
                <td><button class="btn small outline" onclick="openProcessedModal(${j.id})">Inspect</button></td>
            </tr>
        `).join('');
    } catch (e) {
        showToast('Failed to load structured jobs', 'error');
    }
}

// --- Modals Logic ---
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
        document.getElementById('pj-salary').innerText = pj.salary ? `$${pj.salary}` : 'Salary Undisclosed';
        
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

function renderErrorChart(errors) {
    const ctx = document.getElementById('errorChart');
    if (errorChartInstance) errorChartInstance.destroy();
    
    if (errors.length === 0) {
        // Show empty state chart
        errorChartInstance = new Chart(ctx, {
            type: 'bar',
            data: { labels: ['No Errors'], datasets: [{ data: [0] }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
        });
        return;
    }

    // Group by date
    const countsByDate = {};
    errors.forEach(e => {
        const d = new Date(e.created_at).toLocaleDateString();
        countsByDate[d] = (countsByDate[d] || 0) + 1;
    });

    const labels = Object.keys(countsByDate).reverse().slice(-7); // Last 7 days with errors
    const data = labels.map(l => countsByDate[l]);

    errorChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Error Count',
                data: data,
                borderColor: '#ef4444',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                borderWidth: 2,
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#ef4444',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { stepSize: 1 } },
                x: { grid: { display: false } }
            }
        }
    });
}


// --- Utilities ---
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
