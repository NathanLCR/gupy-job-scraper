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
            const res = await fetch(`${API_BASE}/extract`, { method: 'POST' });
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
        // Parallel fetch for metric counts
        const [jobsRes, termsRes, errorsRes] = await Promise.all([
            fetch(`${API_BASE}/job-posts?limit=1`),
            fetch(`${API_BASE}/search-terms`),
            fetch(`${API_BASE}/errors?limit=50`)
        ]);

        const jobs = await jobsRes.json();
        const terms = await termsRes.json();
        const errors = await errorsRes.json();

        // Hack for total jobs because API doesn't expose count. We show "--" or length of a full fetch if small.
        // If the user wants true count, they need a /stats endpoint, but we can just say "Tracking"
        // Since we did limit=1, we can't tell total. Let's just do a rough fetch of limit 500.
        const jResFull = await fetch(`${API_BASE}/job-posts?limit=500`);
        const jFull = await jResFull.json();
        document.getElementById('metric-jobs-count').innerText = jFull.length + (jFull.length === 500 ? '+' : '');

        document.getElementById('metric-terms-count').innerText = terms.length;
        document.getElementById('metric-errors-count').innerText = errors.length;

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
        
        if (jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No jobs found.</td></tr>';
            return;
        }

        tbody.innerHTML = jobs.map(j => `
            <tr>
                <td class="text-muted">#${j.id}</td>
                <td><strong>${escapeHTML(j.title)}</strong></td>
                <td>${escapeHTML(j.company)}</td>
                <td>${escapeHTML(j.city || '')} / ${escapeHTML(j.state || '')}</td>
                <td>${escapeHTML(j.workplace_type || '')}</td>
                <td>${new Date(j.published_date).toLocaleDateString()}</td>
                <td><span class="badge neutral">${escapeHTML(j.scraper_type)}</span></td>
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

async function fetchErrors() {
    try {
        const res = await fetch(`${API_BASE}/errors?limit=50`);
        const errors = await res.json();
        const tbody = document.querySelector('#errors-table tbody');
        
        if (errors.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">System is healthy. No recent errors.</td></tr>';
            return;
        }

        tbody.innerHTML = errors.map(e => `
            <tr>
                <td class="text-muted">${new Date(e.created_at).toLocaleString()}</td>
                <td><span class="badge ${e.context === 'App' ? 'neutral' : 'warning'}">${escapeHTML(e.context || 'System')}</span></td>
                <td class="break-word" style="color: var(--danger); font-family: monospace; font-size: 13px;">${escapeHTML(e.error_message)}</td>
            </tr>
        `).join('');
    } catch (e) {
        showToast('Failed to load errors', 'error');
    }
}

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
