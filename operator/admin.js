// SkillPulse — Operator Admin Console Controller
// Fail-Closed Operator Interface (Spec 08)

const API_BASE = window.API_BASE_URL || '';

function apiFetch(url, options = {}) {
    return fetch(url, { ...options, credentials: 'same-origin' });
}

// ==================== Initialization & Fail-Closed Auth ====================
document.addEventListener('DOMContentLoaded', async () => {
    const authenticated = await checkAdminAuth();
    if (!authenticated) {
        window.location.replace('/operator/login');
        return;
    }
    initAdminNavigation();
    initAdminActions();
    loadInitialAdminData();
});

async function checkAdminAuth() {
    try {
        const res = await apiFetch(`${API_BASE}/api/v1/admin/verify`);
        const contentType = res.headers.get('content-type') || '';

        // Strict contract: must be 200 JSON with exact status and authenticated flag
        if (res.ok && contentType.includes('application/json')) {
            const data = await res.json();
            if (data && data.status === 'authenticated' && data.authenticated === true) {
                unlockWorkspace();
                return true;
            }
        }
    } catch {
        // Network errors or offline states fail closed
    }

    lockWorkspace();
    return false;
}

function unlockWorkspace() {
    const overlay = document.getElementById('admin-auth-overlay');
    const layout = document.getElementById('admin-app-layout');
    if (overlay) overlay.style.display = 'none';
    if (layout) {
        layout.removeAttribute('hidden');
        layout.setAttribute('aria-hidden', 'false');
    }
}

function lockWorkspace() {
    const overlay = document.getElementById('admin-auth-overlay');
    const layout = document.getElementById('admin-app-layout');
    if (layout) {
        layout.setAttribute('hidden', 'true');
        layout.setAttribute('aria-hidden', 'true');
    }
    if (overlay) {
        overlay.style.display = 'flex';
    }
}

function showAuthModal() {
    lockWorkspace();
}

window.handleAdminLogout = async function() {
    lockWorkspace();
    try {
        await apiFetch(`${API_BASE}/api/v1/admin/logout`, { method: 'POST' });
    } catch {}
    window.location.replace('/operator/login');
};

async function adminFetch(url, options = {}) {
    const res = await apiFetch(url, options);
    if (res.status === 401 || res.status === 403) {
        lockWorkspace();
        throw new Error('Unauthorized');
    }
    if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
    }
    return res;
}

// ==================== Navigation ====================
function initAdminNavigation() {
    const items = document.querySelectorAll('.admin-nav-item[data-target]');
    const views = document.querySelectorAll('.admin-view');
    const title = document.getElementById('admin-view-title');

    items.forEach(item => {
        item.addEventListener('click', () => {
            items.forEach(i => i.classList.remove('active'));
            item.classList.add('active');

            const targetId = item.getAttribute('data-target');
            views.forEach(v => v.classList.toggle('active', v.id === targetId));

            if (title) title.innerText = item.innerText.trim();

            if (targetId === 'admin-terms-view') fetchSearchTerms();
            if (targetId === 'admin-processed-jobs-view') fetchProcessedJobs();
            if (targetId === 'admin-raw-jobs-view') fetchRawJobs();
            if (targetId === 'admin-logs-view') fetchLogs();
            if (targetId === 'admin-overview-view') fetchAdminOverview();
            if (targetId === 'admin-health-view') fetchReadiness();
        });
    });
}

function loadInitialAdminData() {
    fetchAdminOverview();
    fetchSearchTerms();
    fetchProcessedJobs();
    fetchRawJobs();
    fetchReadiness();
}

// ==================== Action Buttons ====================
function initAdminActions() {
    const btnScrape = document.getElementById('btn-trigger-scrape');
    const btnExtract = document.getElementById('btn-trigger-extract');
    const btnAddTerm = document.getElementById('btn-add-term');
    const btnCancelTerm = document.getElementById('btn-cancel-term');
    const btnSaveTerm = document.getElementById('btn-save-term');
    const btnRunExtract = document.getElementById('btn-run-batch-extract');
    const btnRefreshProcessed = document.getElementById('btn-refresh-processed');
    const btnRefreshRaw = document.getElementById('btn-refresh-raw');
    const btnRefreshLogs = document.getElementById('btn-refresh-logs');
    const btnExportCsv = document.getElementById('btn-export-csv');

    if (btnScrape) {
        btnScrape.addEventListener('click', async () => {
            if (!confirm('Run background multi-source scraper pass across configured search feeds?')) return;
            btnScrape.disabled = true;
            try {
                await adminFetch(`${API_BASE}/scrape/start`, { method: 'POST' });
                showAdminToast('Ingestion scraper triggered in background', 'success');
                const box = document.getElementById('ingest-status-box');
                if (box) box.innerText = 'Worker status: Running scrape passes across multi-source target feeds...';
            } catch {
                showAdminToast('Failed to trigger scraper', 'error');
            } finally {
                btnScrape.disabled = false;
            }
        });
    }

    const runExtractionHandler = async () => {
        if (!confirm('Execute batch NLP extraction cascade on unextracted job postings?')) return;
        const targetBtn = btnExtract || btnRunExtract;
        if (targetBtn) targetBtn.disabled = true;
        try {
            await adminFetch(`${API_BASE}/api/v1/extract/batch?engine=cascade&limit=50`, { method: 'POST' });
            showAdminToast('Batch extraction cascade started', 'success');
            const box = document.getElementById('extract-status-box');
            if (box) box.innerText = 'Extraction status: Processing unextracted jobs with Tier 1 (Aho-Corasick), Tier 2 (NER), and Tier 3 (Groq/OpenRouter)...';
        } catch {
            showAdminToast('Failed to start batch extraction', 'error');
        } finally {
            if (targetBtn) targetBtn.disabled = false;
        }
    };

    if (btnExtract) btnExtract.addEventListener('click', runExtractionHandler);
    if (btnRunExtract) btnRunExtract.addEventListener('click', runExtractionHandler);

    if (btnAddTerm) {
        btnAddTerm.addEventListener('click', () => {
            const box = document.getElementById('add-term-box');
            if (box) box.style.display = 'block';
        });
    }

    if (btnCancelTerm) {
        btnCancelTerm.addEventListener('click', () => {
            const box = document.getElementById('add-term-box');
            if (box) box.style.display = 'none';
        });
    }

    if (btnSaveTerm) {
        btnSaveTerm.addEventListener('click', async () => {
            const input = document.getElementById('new-term-input');
            const term = input ? input.value.trim() : '';
            if (!term) return;

            btnSaveTerm.disabled = true;
            try {
                await adminFetch(`${API_BASE}/api/v1/search-terms`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ term, is_active: true })
                });
                showAdminToast(`Search target "${term}" added`, 'success');
                if (input) input.value = '';
                document.getElementById('add-term-box').style.display = 'none';
                fetchSearchTerms();
            } catch {
                showAdminToast('Failed to add search target', 'error');
            } finally {
                btnSaveTerm.disabled = false;
            }
        });
    }

    if (btnRefreshProcessed) btnRefreshProcessed.addEventListener('click', fetchProcessedJobs);
    if (btnRefreshRaw) btnRefreshRaw.addEventListener('click', fetchRawJobs);
    if (btnRefreshLogs) btnRefreshLogs.addEventListener('click', fetchLogs);

    if (btnExportCsv) {
        btnExportCsv.addEventListener('click', async () => {
            try {
                const res = await adminFetch(`${API_BASE}/job-posts/export`);
                const blob = await res.blob();
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = 'job_posts.csv';
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(downloadUrl);
            } catch {
                showAdminToast('Failed to export CSV', 'error');
            }
        });
    }
}

// ==================== Data Fetchers ====================
async function fetchAdminOverview() {
    const countEl = document.getElementById('count-structured');
    const ingEl = document.getElementById('status-ingestion');
    try {
        const statsRes = await adminFetch(`${API_BASE}/api/v1/stats`);
        const stats = await statsRes.json();
        if (countEl) countEl.innerText = Number.isFinite(stats.jobs_count) ? String(stats.jobs_count) : 'Unavailable';
    } catch {
        if (countEl) countEl.innerText = 'Unavailable';
    }
    try {
        const scrapeRes = await adminFetch(`${API_BASE}/scrape/status`);
        const sData = await scrapeRes.json();
        if (ingEl) ingEl.innerText = sData.running ? 'Running' : 'Idle';
    } catch {
        if (ingEl) ingEl.innerText = 'Unavailable';
    }
}

async function fetchReadiness() {
    const statusEl = document.getElementById('database-health-status');
    const sidebarEl = document.getElementById('sidebar-health-status');
    try {
        const response = await adminFetch(`${API_BASE}/health/ready`);
        const data = await response.json();
        const dependencies = data.dependencies || {};
        const message = `Database: ${data.database}; schema: ${data.schema}; Redis: ${dependencies.redis || 'unavailable'}.`;
        if (statusEl) statusEl.innerText = message;
        if (sidebarEl) sidebarEl.innerText = data.status === 'ready' ? 'Database ready' : 'Database unavailable';
    } catch {
        if (statusEl) statusEl.innerText = 'Readiness status unavailable.';
        if (sidebarEl) sidebarEl.innerText = 'Status unavailable';
    }
}

async function fetchSearchTerms() {
    const tbody = document.getElementById('terms-table-body') || document.querySelector('#terms-table tbody');
    if (!tbody) return;

    try {
        const res = await adminFetch(`${API_BASE}/api/v1/search-terms?include_inactive=true&page=1&page_size=50`);

        const data = await res.json();
        const items = data.items || [];

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No configured search target feeds.</td></tr>`;
            return;
        }

        tbody.innerHTML = items.map(item => `
            <tr>
                <td>#${item.id}</td>
                <td><strong>${escapeHTML(item.term)}</strong></td>
                <td>
                    <span style="color: ${item.is_active ? 'var(--success)' : 'var(--text-muted)'}; font-weight: 500;">
                        ${item.is_active ? 'Active' : 'Inactive'}
                    </span>
                </td>
                <td>${item.created_at ? String(item.created_at).slice(0, 10) : '—'}</td>
                <td>
                    <button class="btn-admin" style="padding: 2px 6px; font-size: 11px;" onclick="deleteSearchTerm(${item.id})">
                        Delete
                    </button>
                </td>
            </tr>
        `).join('');

    } catch {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--danger);">Failed to load search terms.</td></tr>`;
    }
}

window.deleteSearchTerm = async function(id) {
    if (!confirm('Remove this search term query target?')) return;
    try {
        await adminFetch(`${API_BASE}/api/v1/search-terms/${id}`, { method: 'DELETE' });
        showAdminToast('Search target removed', 'success');
        fetchSearchTerms();
    } catch {
        showAdminToast('Failed to delete target', 'error');
    }
};

async function fetchProcessedJobs() {
    const tbody = document.getElementById('processed-jobs-table-body') || document.querySelector('#processed-jobs-table tbody');
    if (!tbody) return;

    try {
        const res = await adminFetch(`${API_BASE}/api/v1/jobs?page=1&page_size=25`);

        const data = await res.json();
        const items = data.items || [];

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No structured jobs found.</td></tr>`;
            return;
        }

        tbody.innerHTML = items.map(j => {
            const skills = (j.hard_skills || j.required_hard_skills || j.tech_stack || []).slice(0, 4).join(', ');
            return `
                <tr>
                    <td>#${j.id}</td>
                    <td><strong>${escapeHTML(j.job_title || j.title || '—')}</strong></td>
                    <td>${escapeHTML(skills || '—')}</td>
                    <td>${escapeHTML(j.seniority || '—')}</td>
                    <td><span style="font-family: var(--font-mono); font-size: 10px; color: var(--accent);">${j.embedding_model ? escapeHTML(j.embedding_model) : 'Unavailable'}</span></td>
                </tr>
            `;
        }).join('');

    } catch {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--danger);">Failed to load structured jobs.</td></tr>`;
    }
}

async function fetchRawJobs() {
    const tbody = document.getElementById('raw-jobs-table-body') || document.querySelector('#raw-jobs-table tbody');
    if (!tbody) return;

    try {
        const res = await adminFetch(`${API_BASE}/job-posts?page=1&page_size=25`);

        const data = await res.json();
        const items = data.items || [];

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No raw postings found.</td></tr>`;
            return;
        }

        tbody.innerHTML = items.map(j => {
            const company = j.career_page_name || j.company_name || j.company || '—';
            return `
                <tr>
                    <td>#${j.id}</td>
                    <td><strong>${escapeHTML(j.title || j.name || '—')}</strong></td>
                    <td>${escapeHTML(j.source || '—')}</td>
                    <td>${escapeHTML(company)}</td>
                    <td>${j.published_date ? String(j.published_date).slice(0, 10) : '—'}</td>
                </tr>
            `;
        }).join('');

    } catch {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--danger);">Failed to load raw jobs.</td></tr>`;
    }
}

async function fetchLogs() {
    const container = document.getElementById('logs-container');
    if (!container) return;

    try {
        const res = await adminFetch(`${API_BASE}/api/v1/errors?page=1&page_size=30`);

        const data = await res.json();
        const items = data.items || [];

        if (!items.length) {
            container.innerText = 'No error events recorded.';
            return;
        }

        container.innerHTML = items.map(e => `
            <div style="margin-bottom: 6px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 4px;">
                <span style="color: var(--text-muted);">[${e.created_at || 'LOG'}]</span>
                <span style="color: var(--danger); font-weight: 600;">[${escapeHTML(e.source || 'SYS')}]</span>
                <span>${escapeHTML(e.message || e.error_message || 'Event')}</span>
            </div>
        `).join('');

    } catch {
        container.innerText = 'Logs unavailable. Retry after checking service readiness.';
    }
}

// ==================== Utilities ====================
function showAdminToast(message, type = 'info') {
    const container = document.getElementById('admin-toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.style.cssText = `
        background-color: var(--surface-raised);
        border: 1px solid var(--border);
        color: var(--text);
        font-size: 12px;
        padding: 8px 12px;
        border-radius: var(--radius-sm);
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    `;

    toast.innerText = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.2s ease';
        setTimeout(() => toast.remove(), 200);
    }, 2800);
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
