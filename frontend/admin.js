// SkillPulse — Operator Console Controller
// Dedicated protected administrator interface for pipeline operations

const API_BASE = window.API_BASE_URL || '';
let adminToken = sessionStorage.getItem('skillpulse_admin_key') || 'skillpulse-admin-secret';

// ==================== Initialization & Auth ====================
document.addEventListener('DOMContentLoaded', async () => {
    initAdminNavigation();
    initAdminActions();

    const isAuthed = await checkAdminAuth();
    if (isAuthed) {
        hideAuthModal();
        loadInitialAdminData();
    } else {
        showAuthModal();
    }
});

async function checkAdminAuth() {
    if (!adminToken) return false;
    try {
        const res = await fetch(`${API_BASE}/api/v1/admin/verify`, {
            headers: { 'X-Admin-Key': adminToken }
        });
        return res.ok;
    } catch {
        return false;
    }
}

function showAuthModal() {
    const overlay = document.getElementById('admin-auth-overlay');
    if (overlay) overlay.style.display = 'flex';
}

function hideAuthModal() {
    const overlay = document.getElementById('admin-auth-overlay');
    if (overlay) overlay.style.display = 'none';
}

window.handleAdminLogin = async function(event) {
    event.preventDefault();
    const input = document.getElementById('admin-key-input');
    const errBox = document.getElementById('auth-error-msg');
    const key = input ? input.value.trim() : '';

    if (!key) return;

    try {
        const res = await fetch(`${API_BASE}/api/v1/admin/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key })
        });

        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || 'Invalid admin secret key');
        }

        const data = await res.json();
        adminToken = data.token || key;
        sessionStorage.setItem('skillpulse_admin_key', adminToken);
        hideAuthModal();
        loadInitialAdminData();
        showAdminToast('Operator session established', 'success');

    } catch (err) {
        if (errBox) {
            errBox.innerText = err.message;
            errBox.style.display = 'block';
        }
    }
};

window.handleAdminLogout = async function() {
    try {
        await fetch(`${API_BASE}/api/v1/admin/logout`, { method: 'POST' });
    } catch {}
    sessionStorage.removeItem('skillpulse_admin_key');
    adminToken = '';
    showAuthModal();
};

async function adminFetch(url, options = {}) {
    const headers = options.headers || {};
    if (adminToken) {
        headers['X-Admin-Key'] = adminToken;
    }
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
        showAuthModal();
        throw new Error('Unauthorized');
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
        });
    });
}

function loadInitialAdminData() {
    fetchAdminOverview();
    fetchSearchTerms();
    fetchProcessedJobs();
}

// ==================== Action Buttons ====================
function initAdminActions() {
    const btnScrape = document.getElementById('btn-trigger-scrape');
    const btnExtract = document.getElementById('btn-trigger-extract');
    const btnInitDb = document.getElementById('btn-init-db');
    const btnAddTerm = document.getElementById('btn-add-term');
    const btnCancelTerm = document.getElementById('btn-cancel-term');
    const btnSaveTerm = document.getElementById('btn-save-term');
    const btnRunExtract = document.getElementById('btn-run-batch-extract');
    const btnRefreshProcessed = document.getElementById('btn-refresh-processed');
    const btnRefreshLogs = document.getElementById('btn-refresh-logs');
    const btnExportCsv = document.getElementById('btn-export-csv');

    if (btnScrape) {
        btnScrape.addEventListener('click', async () => {
            try {
                const res = await adminFetch(`${API_BASE}/scrape/start`, { method: 'POST' });
                if (res.ok) showAdminToast('Ingestion scraper triggered in background', 'success');
            } catch (err) {
                showAdminToast('Failed to trigger scraper', 'error');
            }
        });
    }

    if (btnExtract || btnRunExtract) {
        const handler = async () => {
            const engine = document.getElementById('extract-engine-select')?.value || 'cascade';
            try {
                const res = await adminFetch(`${API_BASE}/api/v1/extract/batch?engine=${engine}&limit=50`, { method: 'POST' });
                if (res.ok) showAdminToast(`Batch extraction (${engine}) started`, 'success');
            } catch (err) {
                showAdminToast('Failed to start batch extraction', 'error');
            }
        };
        if (btnExtract) btnExtract.addEventListener('click', handler);
        if (btnRunExtract) btnRunExtract.addEventListener('click', handler);
    }

    if (btnInitDb) {
        btnInitDb.addEventListener('click', async () => {
            try {
                const res = await adminFetch(`${API_BASE}/database/init`, { method: 'POST' });
                if (res.ok) showAdminToast('Database initialized successfully', 'success');
            } catch (err) {
                showAdminToast('Failed to initialize database', 'error');
            }
        });
    }

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

            try {
                const res = await adminFetch(`${API_BASE}/api/v1/search-terms`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ term, is_active: true })
                });
                if (res.ok) {
                    showAdminToast(`Search term "${term}" added`, 'success');
                    if (input) input.value = '';
                    document.getElementById('add-term-box').style.display = 'none';
                    fetchSearchTerms();
                }
            } catch (err) {
                showAdminToast('Failed to add search term', 'error');
            }
        });
    }

    if (btnRefreshProcessed) btnRefreshProcessed.addEventListener('click', fetchProcessedJobs);
    if (btnRefreshLogs) btnRefreshLogs.addEventListener('click', fetchLogs);

    if (btnExportCsv) {
        btnExportCsv.addEventListener('click', () => {
            window.open(`${API_BASE}/job-posts/export?admin_key=${encodeURIComponent(adminToken)}`, '_blank');
        });
    }
}

// ==================== Data Fetchers ====================
async function fetchAdminOverview() {
    try {
        const statsRes = await fetch(`${API_BASE}/api/v1/stats`);
        if (statsRes.ok) {
            const stats = await statsRes.json();
            const countEl = document.getElementById('count-structured');
            if (countEl) countEl.innerText = stats.jobs_count || 395;
        }

        const scrapeRes = await adminFetch(`${API_BASE}/scrape/status`).catch(() => null);
        if (scrapeRes && scrapeRes.ok) {
            const sData = await scrapeRes.json();
            const ingEl = document.getElementById('status-ingestion');
            if (ingEl) ingEl.innerText = sData.running ? 'Running' : 'Idle';
        }
    } catch (err) {
        console.warn('Overview fetch error:', err);
    }
}

async function fetchSearchTerms() {
    const tbody = document.querySelector('#terms-table tbody');
    if (!tbody) return;

    try {
        const res = await adminFetch(`${API_BASE}/api/v1/search-terms?include_inactive=true&page=1&page_size=50`);
        if (!res.ok) return;

        const data = await res.json();
        const items = data.items || [];

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No configured search terms.</td></tr>`;
            return;
        }

        tbody.innerHTML = items.map(item => `
            <tr>
                <td>#${item.id}</td>
                <td><strong>${escapeHTML(item.term)}</strong></td>
                <td>
                    <span style="color: ${item.is_active ? 'var(--success)' : 'var(--text-muted)'};">
                        ${item.is_active ? 'Active' : 'Inactive'}
                    </span>
                </td>
                <td style="text-align: right;">
                    <button class="btn-admin" style="padding: 2px 6px; font-size: 11px;" onclick="deleteSearchTerm(${item.id})">
                        Delete
                    </button>
                </td>
            </tr>
        `).join('');

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--danger);">Failed to load search terms.</td></tr>`;
    }
}

window.deleteSearchTerm = async function(id) {
    if (!confirm('Remove this search term query?')) return;
    try {
        const res = await adminFetch(`${API_BASE}/api/v1/search-terms/${id}`, { method: 'DELETE' });
        if (res.ok) {
            showAdminToast('Search term removed', 'success');
            fetchSearchTerms();
        }
    } catch {
        showAdminToast('Failed to delete term', 'error');
    }
};

async function fetchProcessedJobs() {
    const tbody = document.querySelector('#processed-jobs-table tbody');
    if (!tbody) return;

    try {
        const res = await fetch(`${API_BASE}/api/v1/jobs?page=1&page_size=25`);
        if (!res.ok) return;

        const data = await res.json();
        const items = data.items || [];

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No structured jobs found.</td></tr>`;
            return;
        }

        tbody.innerHTML = items.map(j => `
            <tr>
                <td>#${j.id}</td>
                <td><strong>${escapeHTML(j.job_title)}</strong></td>
                <td>${escapeHTML(j.company?.name || 'Enterprise')}</td>
                <td>${escapeHTML(j.region || 'Global')}</td>
                <td>${j.salary ? `${j.currency || 'BRL'} ${j.salary.toLocaleString()}` : '—'}</td>
            </tr>
        `).join('');

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--danger);">Failed to load structured jobs.</td></tr>`;
    }
}

async function fetchRawJobs() {
    const tbody = document.querySelector('#raw-jobs-table tbody');
    if (!tbody) return;

    try {
        const res = await fetch(`${API_BASE}/job-posts?page=1&page_size=25`);
        if (!res.ok) return;

        const data = await res.json();
        const items = data.items || [];

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No raw posts found.</td></tr>`;
            return;
        }

        tbody.innerHTML = items.map(j => `
            <tr>
                <td>#${j.id}</td>
                <td>${escapeHTML(j.source || 'Scraper')}</td>
                <td><strong>${escapeHTML(j.title || j.name || 'Position')}</strong></td>
                <td>${escapeHTML(j.company_name || 'Enterprise')}</td>
                <td>${escapeHTML(j.workplace_type || 'Remote')}</td>
                <td>${j.published_date ? String(j.published_date).slice(0, 10) : '—'}</td>
            </tr>
        `).join('');

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--danger);">Failed to load raw jobs.</td></tr>`;
    }
}

async function fetchLogs() {
    const tbody = document.querySelector('#logs-table tbody');
    if (!tbody) return;

    try {
        const res = await adminFetch(`${API_BASE}/api/v1/errors?page=1&page_size=25`);
        if (!res.ok) return;

        const data = await res.json();
        const items = data.items || [];

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">No error logs reported.</td></tr>`;
            return;
        }

        tbody.innerHTML = items.map(l => `
            <tr>
                <td style="font-family: var(--font-mono); font-size: 11px;">${l.created_at || 'Recent'}</td>
                <td><span style="color: var(--warning);">${escapeHTML(l.context || l.source || 'System')}</span></td>
                <td>${escapeHTML(l.error_message || l.message || 'Log event')}</td>
            </tr>
        `).join('');

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--danger);">Failed to load logs.</td></tr>`;
    }
}

// ==================== Utilities ====================
function showAdminToast(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.style.cssText = `
        background-color: var(--bg-surface-raised);
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        padding: 8px 14px;
        font-size: 12px;
        color: var(--text-primary);
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    `;
    if (type === 'success') toast.style.borderColor = 'var(--success)';
    if (type === 'error') toast.style.borderColor = 'var(--danger)';

    toast.innerText = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function escapeHTML(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
