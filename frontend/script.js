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
let cachedTerms = [];
let lastErrors = [];
let selectedTrendSkill = '';
const jobsTableState = { page: 1, pageSize: 100, search: '', workplace: '', sort: 'date-desc' };
const processedJobsTableState = { page: 1, pageSize: 100, search: '', location: '', sort: 'id-desc' };
const termsTableState = { page: 1, pageSize: 20, search: '', status: 'all' };
const errorsTableState = { page: 1, pageSize: 20, search: '', source: '' };

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
    document.getElementById('jobs-search').addEventListener('input', debounce((event) => {
        jobsTableState.search = event.target.value.trim();
        jobsTableState.page = 1;
        fetchJobs();
    }, 250));
    document.getElementById('jobs-filter-workplace').addEventListener('change', (event) => {
        jobsTableState.workplace = event.target.value;
        jobsTableState.page = 1;
        fetchJobs();
    });
    document.getElementById('jobs-sort').addEventListener('change', (event) => {
        jobsTableState.sort = event.target.value;
        jobsTableState.page = 1;
        fetchJobs();
    });
    document.getElementById('jobs-page-size').addEventListener('change', (event) => {
        jobsTableState.pageSize = parseInt(event.target.value, 10);
        jobsTableState.page = 1;
        fetchJobs();
    });

    // Processed Jobs View
    document.getElementById('pj-search').addEventListener('input', debounce((event) => {
        processedJobsTableState.search = event.target.value.trim();
        processedJobsTableState.page = 1;
        fetchProcessedJobs();
    }, 250));
    document.getElementById('pj-filter-location').addEventListener('input', debounce((event) => {
        processedJobsTableState.location = event.target.value.trim();
        processedJobsTableState.page = 1;
        fetchProcessedJobs();
    }, 250));
    document.getElementById('pj-sort').addEventListener('change', (event) => {
        processedJobsTableState.sort = event.target.value;
        processedJobsTableState.page = 1;
        fetchProcessedJobs();
    });
    document.getElementById('pj-page-size').addEventListener('change', (event) => {
        processedJobsTableState.pageSize = parseInt(event.target.value, 10);
        processedJobsTableState.page = 1;
        fetchProcessedJobs();
    });

    // Terms View
    document.getElementById('terms-search').addEventListener('input', debounce((event) => {
        termsTableState.search = event.target.value.trim();
        termsTableState.page = 1;
        fetchSearchTerms();
    }, 250));
    document.getElementById('terms-filter-status').addEventListener('change', (event) => {
        termsTableState.status = event.target.value;
        termsTableState.page = 1;
        fetchSearchTerms();
    });
    document.getElementById('terms-page-size').addEventListener('change', (event) => {
        termsTableState.pageSize = parseInt(event.target.value, 10);
        termsTableState.page = 1;
        fetchSearchTerms();
    });

    // Errors View
    document.getElementById('errors-search').addEventListener('input', debounce((event) => {
        errorsTableState.search = event.target.value.trim();
        errorsTableState.page = 1;
        fetchErrors();
    }, 250));
    document.getElementById('errors-filter-source').addEventListener('change', (event) => {
        errorsTableState.source = event.target.value;
        errorsTableState.page = 1;
        fetchErrors();
    });
    document.getElementById('errors-page-size').addEventListener('change', (event) => {
        errorsTableState.pageSize = parseInt(event.target.value, 10);
        errorsTableState.page = 1;
        fetchErrors();
    });

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
                showToast(`Started scrape successfully!`, 'success');
                fetchScrapeStatus();
            } else {
                showToast(data.error || 'Failed to start scrape.', 'error');
            }
        } catch (e) {
            showToast('Connection error.', 'error');
        }
    };

    document.getElementById('dash-btn-scrape').addEventListener('click', () => triggerScrape());
    
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
    if (document.getElementById('trend-search-btn')) {
        document.getElementById('trend-search-btn').addEventListener('click', applyTrendSearch);
    }
    if (document.getElementById('trend-clear-btn')) {
        document.getElementById('trend-clear-btn').addEventListener('click', clearTrendSearch);
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

    document.getElementById('sys-started').innerText = data.started_at ? new Date(data.started_at).toLocaleString() : '--';
    
    if (data.running) {
        statusEl.innerText = 'RUNNING';
        statusEl.className = 'badge success';
        pillText.innerText = `Scraping...`;
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
    const maxValue = Math.max(
        ...series.flatMap(item => item.counts || []),
        1
    );
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

    const totalsByPeriod = periods.map((period, index) => ({
        period,
        total: series.reduce((sum, item) => sum + ((item.counts || [])[index] || 0), 0)
    }));
    const busiestDay = totalsByPeriod.reduce((best, current) => current.total > best.total ? current : best, totalsByPeriod[0]);
    const overallTotal = series.reduce((sum, item) => sum + (item.total || 0), 0);

    const summaryHtml = `
        <div class="trend-summary-grid">
            <div class="trend-summary-card">
                <span class="trend-summary-label">Window</span>
                <strong class="trend-summary-value">${periods[0]} to ${periods[periods.length - 1]}</strong>
            </div>
            <div class="trend-summary-card">
                <span class="trend-summary-label">${selectedSkill ? 'Selected technology' : 'Tracked technologies'}</span>
                <strong class="trend-summary-value">${selectedSkill ? escapeHTML(selectedSkill) : series.length}</strong>
            </div>
            <div class="trend-summary-card">
                <span class="trend-summary-label">Busiest day</span>
                <strong class="trend-summary-value">${busiestDay.period}</strong>
                <span class="trend-summary-meta">${busiestDay.total} mentions</span>
            </div>
            <div class="trend-summary-card">
                <span class="trend-summary-label">Total mentions</span>
                <strong class="trend-summary-value">${overallTotal}</strong>
            </div>
        </div>
    `;

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

    const seriesStatsHtml = series.map((item, index) => {
        const counts = item.counts || [];
        const activeDays = counts.filter(count => count > 0).length;
        const latest = counts[counts.length - 1] || 0;
        const peak = Math.max(...counts, 0);
        const avg = item.total / Math.max(periods.length, 1);
        const latestIndex = counts.lastIndexOf(latest);
        const latestDate = latest > 0 && latestIndex >= 0 ? periods[latestIndex] : 'No recent hits';

        return `
            <div class="trend-series-card">
                <div class="trend-series-head">
                    <span class="trend-legend-item">
                        <span class="trend-legend-swatch" style="background:${colors[index % colors.length]}"></span>
                        ${escapeHTML(item.name)}
                    </span>
                    <strong class="trend-series-total">${item.total}</strong>
                </div>
                <div class="trend-series-metrics">
                    <span>Total: ${item.total}</span>
                    <span>Avg/day: ${avg.toFixed(2)}</span>
                    <span>Peak/day: ${peak}</span>
                    <span>Active days: ${activeDays}</span>
                    <span>Latest count: ${latest}</span>
                    <span>Latest hit: ${latestDate}</span>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = `
        ${summaryHtml}
        <div class="trend-legend">${legendHtml}</div>
        <svg class="trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Technology trend line chart">
            ${yAxisLabelsHtml}
            <line class="trend-axis" x1="${padding.left}" y1="${padding.top + chartHeight}" x2="${width - padding.right}" y2="${padding.top + chartHeight}"></line>
            ${linesHtml}
            ${circlesHtml}
            ${xAxisLabelsHtml}
        </svg>
        <div class="trend-footer">
            <span>${selectedSkill ? `Tracking ${escapeHTML(selectedSkill)} over ${trendData.days || periods.length} days` : `Tracking top ${series.length} technologies over ${trendData.days || periods.length} days`}</span>
            <span>Peak daily count: ${maxValue}</span>
        </div>
        <div class="trend-series-grid">${seriesStatsHtml}</div>
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

// ==================== Dashboard Metrics ====================
async function fetchDashboardMetrics() {
    try {
        const trendQuery = new URLSearchParams({ days: '30', limit: selectedTrendSkill ? '1' : '5' });
        if (selectedTrendSkill) {
            trendQuery.set('skill', selectedTrendSkill);
        }

        const [statsRes, errorsRes, avgRes, salaryRes, techRes, locRes, contractRes, seniorityRes, trendRes] = await Promise.all([
            fetch(`${API_BASE}/stats`),
            fetch(`${API_BASE}/errors?page=1&page_size=50`),
            fetch(`${API_BASE}/features/average-job-post-daily`),
            fetch(`${API_BASE}/features/average-salary`),
            fetch(`${API_BASE}/features/top-technologies`),
            fetch(`${API_BASE}/features/top-locations`),
            fetch(`${API_BASE}/features/jobs-by-contract-type`),
            fetch(`${API_BASE}/features/jobs-by-seniority`),
            fetch(`${API_BASE}/features/technology-trends?${trendQuery.toString()}`)
        ]);

        const stats = await statsRes.json();
        const errorsPayload = await errorsRes.json();
        const avgDaily = await avgRes.json();
        const avgSalary = await salaryRes.json();
        const technologies = await techRes.json();
        const locations = await locRes.json();
        const contracts = await contractRes.json();
        const seniority = await seniorityRes.json();
        const trends = await trendRes.json();

        const errors = errorsPayload.items || [];
        const updateEl = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.innerText = val;
        };

        updateEl('metric-jobs-count', stats.total_jobs || 0);
        updateEl('metric-processed-count', stats.total_processed || 0);
        updateEl('metric-terms-count', stats.total_terms || 0);
        updateEl('metric-errors-count', stats.total_errors || 0);
        
        // Display average formatted to 2 decimals
        const avgVal = parseFloat(avgDaily);
        updateEl('metric-avg-daily', isNaN(avgVal) ? '0.00' : avgVal.toFixed(2));
        
        // Display average salary
        const salaryVal = parseFloat(avgSalary);
        updateEl('metric-avg-salary', isNaN(salaryVal) ? 'N/A' : `R$${salaryVal.toFixed(0)}`);
        
        renderBarChart('top-technologies-list', technologies, 'No data available', 'primary');
        renderBarChart('top-locations-list', locations, 'No data available', 'info');
        renderBarChart('top-contracts-list', contracts, 'No data available', 'warning');
        renderBarChart('top-seniority-list', seniority, 'No data available', 'success');
        renderTrendChart('technology-trends-chart', trends, 'Trend data will appear after processed jobs are available.');

    } catch (e) {
        console.error('Metrics fetch error', e);
    }
}


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

        const res = await fetch(`${API_BASE}/job-posts?${query.toString()}`);
        const payload = await res.json();
        cachedJobs = payload.items || [];
        renderJobsTable(payload.pagination || emptyPagination(jobsTableState.page, jobsTableState.pageSize));
    } catch (e) {
        showToast('Failed to load jobs', 'error');
    }
}

function renderJobsTable(pagination) {
    const tbody = document.querySelector('#jobs-table tbody');
    if (cachedJobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No jobs found.</td></tr>';
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

        const res = await fetch(`${API_BASE}/jobs?${query.toString()}`);
        const payload = await res.json();
        cachedProcessedJobs = payload.items || [];
        renderProcessedJobsTable(payload.pagination || emptyPagination(processedJobsTableState.page, processedJobsTableState.pageSize));
    } catch (e) {
        showToast('Failed to load structured jobs', 'error');
    }
}

function renderProcessedJobsTable(pagination) {
    const tbody = document.querySelector('#processed-jobs-table tbody');
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
        showToast('Failed to load errors', 'error');
    }
}

function renderErrorsTable(pagination) {
    const tbody = document.querySelector('#errors-table tbody');
    if (cachedErrors.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">System is healthy. No recent errors.</td></tr>';
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
    html += `<button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} data-page="${totalPages}"><i class='bx bx-chevrons-right'></i></button>`;

    // Info
    html += `<span class="page-summary">${formatPaginationRange(pagination)}</span>`;
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
function emptyPagination(page = 1, pageSize = 20) {
    return {
        page,
        page_size: pageSize,
        total_items: 0,
        total_pages: 1,
        has_next: false,
        has_prev: false
    };
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
    if (totalBadge) {
        totalBadge.innerText = `${pagination.total_items || 0} result${pagination.total_items === 1 ? '' : 's'}`;
    }
    if (rangeBadge) {
        rangeBadge.innerText = `Page ${pagination.page || 1} of ${pagination.total_pages || 1}`;
    }
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
