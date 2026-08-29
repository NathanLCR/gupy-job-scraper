const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { chromium } = require('playwright');

const ROOT_DIR = path.join(__dirname, '..');
const FRONTEND_DIR = path.join(ROOT_DIR, 'frontend');

// ─────────────────────────────────────────────────────────────────────────────
// Test HTTP Mock Server
// ─────────────────────────────────────────────────────────────────────────────
let server;
let serverPort;
let mockApiMode = 'unavailable'; // 'unavailable' | 'valid' | 'html_error'

const VALID_JOBS_FIXTURE = {
    items: [
        {
            id: 101,
            job_title: 'Senior Python Engineer',
            company: 'TechCorp Dublin',
            city: 'Dublin',
            state: 'Leinster',
            region: 'Europe',
            country_code: 'IE',
            currency: 'EUR',
            workplace_type: 'Remote',
            hard_skills: ['Python', 'FastAPI', 'PostgreSQL'],
            soft_skills: ['Problem Solving', 'Leadership'],
            description: 'Building high-throughput microservices in Python.',
            published_date: '2026-08-20',
            job_url: 'https://example.com/jobs/101',
        },
        {
            id: 102,
            job_title: 'Backend Platform Engineer',
            company: 'CloudScale UK',
            city: 'London',
            state: 'Greater London',
            region: 'Europe',
            country_code: 'GB',
            currency: 'GBP',
            workplace_type: 'Hybrid',
            hard_skills: ['Go', 'Kubernetes', 'Docker'],
            soft_skills: ['Collaboration'],
            description: 'Cloud infrastructure and Kubernetes orchestration.',
            published_date: '2026-08-19',
            job_url: 'https://example.com/jobs/102',
        },
    ],
    pagination: {
        page: 1,
        page_size: 25,
        total_items: 2,
        total_pages: 1,
        has_next: false,
        has_prev: false,
    },
};

const VALID_MATCH_FIXTURE = {
    total_eligible: 120,
    total_evaluated: 45,
    total_qualified: 8,
    total_matches: 1,
    extracted_skills: {
        hard_skills: ['Python', 'FastAPI', 'PostgreSQL', 'Docker'],
        soft_skills: ['Communication', 'System Design'],
    },
    matches: [
        {
            job_id: 101,
            job_title: 'Senior Python Engineer',
            company: 'TechCorp Dublin',
            location: 'Dublin, Leinster',
            region: 'Europe',
            workplace_type: 'Remote',
            currency: 'EUR',
            fit_score: 85.0,
            hard_skill_overlap: 85.0,
            soft_skill_overlap: 80.0,
            vector_similarity: 88.0,
            hard_points: 42.5,
            soft_points: 16.0,
            vector_points: 26.5,
            total_points: 85.0,
            job_url: 'https://example.com/jobs/101',
            gap_analysis: {
                matched_hard_skills: ['Python', 'FastAPI', 'PostgreSQL'],
                missing_hard_skills: ['Redis'],
                matched_soft_skills: ['Communication'],
                missing_soft_skills: [],
                recommended_skills: ['Redis'],
            },
        },
    ],
};

const VALID_ANALYTICS_FIXTURE = {
    total_jobs: 1250,
    distinct_skills: 340,
    distinct_companies: 180,
    markets_tracked: 3,
    top_skills: [
        { name: 'Python', count: 620, percentage: 49.6 },
        { name: 'Docker', count: 480, percentage: 38.4 },
        { name: 'PostgreSQL', count: 410, percentage: 32.8 },
    ],
    top_locations: [
        { name: 'Dublin', count: 320, percentage: 25.6 },
        { name: 'London', count: 290, percentage: 23.2 },
    ],
    salary_by_seniority: [
        { name: 'Senior', count: 500, percentage: 40.0 },
        { name: 'Mid-Level', count: 450, percentage: 36.0 },
    ],
    workplace_distribution: [
        { name: 'Remote', count: 750, percentage: 60.0 },
        { name: 'Hybrid', count: 350, percentage: 28.0 },
        { name: 'Onsite', count: 150, percentage: 12.0 },
    ],
};

function handleApiRequest(req, res) {
    const urlPath = req.url.split('?')[0];

    if (urlPath === '/api/v1/jobs') {
        if (mockApiMode === 'unavailable') {
            res.writeHead(503, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ detail: 'Service Unavailable' }));
            return true;
        }
        if (mockApiMode === 'html_error') {
            res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
            res.end('<!DOCTYPE html><html><body>SPA HTML Catchall</body></html>');
            return true;
        }
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(VALID_JOBS_FIXTURE));
        return true;
    }

    if (urlPath === '/api/v1/match') {
        if (mockApiMode === 'unavailable') {
            res.writeHead(503, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ detail: 'Service Unavailable' }));
            return true;
        }
        if (mockApiMode === 'html_error') {
            res.writeHead(405, { 'Content-Type': 'text/html' });
            res.end('Method Not Allowed');
            return true;
        }
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(VALID_MATCH_FIXTURE));
        return true;
    }

    if (urlPath === '/api/v1/analytics/overview') {
        if (mockApiMode === 'unavailable' || mockApiMode === 'html_error') {
            res.writeHead(503, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ detail: 'Service Unavailable' }));
            return true;
        }
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(VALID_ANALYTICS_FIXTURE));
        return true;
    }

    return false;
}

function startServer() {
    return new Promise((resolve) => {
        server = http.createServer((req, res) => {
            if (handleApiRequest(req, res)) {
                return;
            }

            const urlPath = req.url.split('?')[0];
            let cleanPath = urlPath;
            if (cleanPath.startsWith('/frontend/')) {
                cleanPath = cleanPath.replace(/^\/frontend\//, '/');
            }

            let filePath = path.join(FRONTEND_DIR, cleanPath === '/' ? 'index.html' : cleanPath);
            if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
                // SPA fallback
                filePath = path.join(FRONTEND_DIR, 'index.html');
            }

            const ext = path.extname(filePath);
            const mimeMap = {
                '.html': 'text/html; charset=utf-8',
                '.js': 'application/javascript; charset=utf-8',
                '.css': 'text/css; charset=utf-8',
                '.json': 'application/json; charset=utf-8',
            };

            const contentType = mimeMap[ext] || 'text/plain';
            res.writeHead(200, { 'Content-Type': contentType });
            fs.createReadStream(filePath).pipe(res);
        });

        server.listen(0, '127.0.0.1', () => {
            serverPort = server.address().port;
            resolve();
        });
    });
}

function stopServer() {
    return new Promise((resolve) => {
        if (server) {
            server.close(resolve);
        } else {
            resolve();
        }
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Genuine Browser Acceptance Test Suite (Playwright Chromium)
// ─────────────────────────────────────────────────────────────────────────────

test('Browser Acceptance: API Unavailable scenario across Jobs, Match, and Market', async () => {
    await startServer();
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    try {
        mockApiMode = 'unavailable';

        // 1. Jobs View with API Offline
        await page.goto(`http://127.0.0.1:${serverPort}/jobs`);
        await page.waitForLoadState('networkidle');
        await page.waitForFunction(() => {
            const count = document.getElementById('explorer-results-count');
            return count && count.textContent.includes('Unavailable');
        });

        // Check Explorer results list shows explicit unavailable state
        const jobsListText = await page.locator('#explorer-results-list').innerText();
        assert.match(jobsListText, /Live data unavailable right now\. No cached vacancies are being shown\./i);
        assert.equal(
            await page.locator('#explorer-results-list [role="alert"]').count(),
            1,
            'Jobs unavailable state uses one assertive alert',
        );

        const jobsCountText = await page.locator('#explorer-results-count').innerText();
        assert.equal(jobsCountText, 'Unavailable');

        const jobsPillText = await page.locator('#explorer-jobs-total-pill').innerText();
        assert.equal(jobsPillText, 'Unavailable');

        // 2. Candidate Match with API Offline
        await page.click('button[data-target="matcher-view"]');
        await page.waitForTimeout(100);

        // Click sample persona chip
        await page.click('#btn-persona-backend');
        const resumeText = await page.locator('#matcher-resume-input').inputValue();
        assert.ok(resumeText.length > 50, 'Persona should populate textarea');

        // Run match
        await page.click('#btn-run-match');
        await page.waitForFunction(() => {
            const emptyEl = document.getElementById('matcher-empty-state');
            return emptyEl && emptyEl.innerText.includes('Live matching is unavailable right now');
        });

        // Check match failure state
        const matchEmptyText = await page.locator('#matcher-empty-state').innerText();
        assert.match(matchEmptyText, /Live matching is unavailable right now\. Your profile was not scored\./i);
        assert.equal(
            await page.locator('#matcher-empty-state [role="alert"]').count(),
            1,
            'Match unavailable state uses one assertive alert',
        );

        const isResultsVisible = await page.locator('#matcher-results-section').isVisible();
        assert.equal(isResultsVisible, false, 'Results section must stay hidden on failure');

        // 3. Market View with API Offline
        await page.click('button[data-target="dashboard-view"]');
        await page.waitForFunction(() => {
            const statusEl = document.getElementById('market-status-text');
            return statusEl && statusEl.textContent === 'Update status unavailable';
        });

        const activeRoles = await page.locator('#metric-jobs-count').innerText();
        assert.equal(activeRoles, 'Unavailable');

        const marketsTracked = await page.locator('#metric-markets-count').innerText();
        assert.equal(marketsTracked, 'Unavailable');

        const skillsCount = await page.locator('#metric-skills-count').innerText();
        assert.equal(skillsCount, 'Unavailable');

        const topTech = await page.locator('#metric-top-tech').innerText();
        assert.equal(topTech, 'Unavailable');

        const bannerText = await page.locator('#market-status-banner').innerText();
        assert.match(bannerText, /Market aggregates could not be loaded/i);
        assert.equal(
            await page.locator('#market-status-banner [role="alert"]').count(),
            1,
            'Market unavailable state uses one assertive alert',
        );

        const statusText = await page.locator('#market-status-text').innerText();
        assert.equal(statusText, 'Update status unavailable');

        // 4. Verify initial drawer is hidden and absent from accessibility tree
        const drawer = page.locator('#job-inspector-drawer');
        const hasHidden = await drawer.getAttribute('hidden');
        assert.notEqual(hasHidden, null, 'Drawer must have hidden attribute');

        const ariaHidden = await drawer.getAttribute('aria-hidden');
        assert.equal(ariaHidden, 'true');

    } finally {
        await browser.close();
        await stopServer();
    }
});

test('Browser Acceptance: Contract-Valid Fixture Rendering across Match, Drawer, Jobs, and Market', async () => {
    await startServer();
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    try {
        mockApiMode = 'valid';

        // 1. Candidate Matcher Flow
        await page.goto(`http://127.0.0.1:${serverPort}/match`);
        await page.waitForLoadState('networkidle');

        await page.click('#btn-persona-backend');
        await page.click('#btn-run-match');
        await page.waitForFunction(() => {
            const res = document.getElementById('matcher-results-section');
            return res && res.style.display === 'block';
        });

        // Verify exact server fit score and points
        const gaugeScore = await page.locator('#gauge-score-text').innerText();
        assert.equal(gaugeScore, '85%');

        const hardPts = await page.locator('#explain-hard-pts').innerText();
        assert.equal(hardPts, '42.5 / 50');

        const softPts = await page.locator('#explain-soft-pts').innerText();
        assert.equal(softPts, '16.0 / 20');

        const vecPts = await page.locator('#explain-vec-pts').innerText();
        assert.equal(vecPts, '26.5 / 30');

        const totalPts = await page.locator('#explain-total-pts').innerText();
        assert.equal(totalPts, '85.0 / 100');

        // Verify ranked job item rendered
        const jobRow = page.locator('.job-list-row').first();
        assert.ok(await jobRow.isVisible());
        const jobRowTitle = await jobRow.locator('.job-row-title').innerText();
        assert.equal(jobRowTitle, 'Senior Python Engineer');

        // 2. Inspector Drawer Opening & Interaction
        await jobRow.click();
        const drawer = page.locator('#job-inspector-drawer');
        await page.waitForSelector('#job-inspector-drawer.active');

        assert.equal(await drawer.getAttribute('aria-hidden'), 'false');
        assert.equal(await drawer.getAttribute('hidden'), null);

        const drawerTitle = await page.locator('#drawer-job-title').innerText();
        assert.equal(drawerTitle, 'Senior Python Engineer');

        const drawerCompany = await page.locator('#drawer-company').innerText();
        assert.equal(drawerCompany, 'TechCorp Dublin');

        const drawerFitScore = await page.locator('#drawer-fit-score').innerText();
        assert.equal(drawerFitScore, '85%');

        const applyLinkHref = await page.locator('#drawer-apply-link').getAttribute('href');
        assert.equal(applyLinkHref, 'https://example.com/jobs/101');

        // Close drawer with Escape
        await page.keyboard.press('Escape');
        await page.waitForTimeout(100);
        assert.equal(await drawer.getAttribute('aria-hidden'), 'true');
        assert.notEqual(await drawer.getAttribute('hidden'), null);

        // 3. Jobs Explorer Flow
        await page.click('button[data-target="explorer-view"]');
        await page.waitForFunction(() => {
            const count = document.getElementById('explorer-results-count');
            return count && count.textContent === '2 Vacancies Found';
        });

        const expCount = await page.locator('#explorer-results-count').innerText();
        assert.equal(expCount, '2 Vacancies Found');

        const expPill = await page.locator('#explorer-jobs-total-pill').innerText();
        assert.equal(expPill, '2 roles');

        const firstExpRowTitle = await page.locator('#explorer-results-list .job-row-title').first().innerText();
        assert.equal(firstExpRowTitle, 'Senior Python Engineer');

        // 4. Market Insights Flow
        await page.click('button[data-target="dashboard-view"]');
        await page.waitForFunction(() => {
            const jobsCount = document.getElementById('metric-jobs-count');
            return jobsCount && jobsCount.textContent === '1,250';
        });

        const mJobs = await page.locator('#metric-jobs-count').innerText();
        assert.equal(mJobs, '1,250');

        const mMarkets = await page.locator('#metric-markets-count').innerText();
        assert.equal(mMarkets, '3');

        const mSkills = await page.locator('#metric-skills-count').innerText();
        assert.equal(mSkills, '340+');

        const mTopTech = await page.locator('#metric-top-tech').innerText();
        assert.equal(mTopTech, 'Python (50%)');

        const bannerHtml = await page.locator('#market-status-banner').innerHTML();
        assert.equal(bannerHtml, '', 'Status banner must be empty on success');

        const marketStatusText = await page.locator('#market-status-text').innerText();
        assert.match(marketStatusText, /Data updated recently/i);

    } finally {
        await browser.close();
        await stopServer();
    }
});
