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
let mockApiMode = 'valid'; // 'valid' | 'unavailable'

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
    total_evaluated: 45,
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
    distinct_companies: 420,
    markets_tracked: 5,
    top_skills: [
        { name: 'Python', count: 480, percentage: 38.4 },
        { name: 'PostgreSQL', count: 350, percentage: 28.0 },
    ],
    top_locations: [
        { location: 'Dublin, Ireland', count: 320, percentage: 25.6 },
        { location: 'London, UK', count: 280, percentage: 22.4 },
    ],
    salary_by_seniority: [
        { seniority: 'Senior', count: 620, percentage: 49.6 },
        { seniority: 'Mid', count: 380, percentage: 30.4 },
    ],
    workplace_distribution: [
        { name: 'Remote', count: 750, percentage: 60.0 },
        { name: 'Hybrid', count: 350, percentage: 28.0 },
        { name: 'On-site', count: 150, percentage: 12.0 },
    ],
};

function handleApiRequest(req, res) {
    const urlPath = req.url.split('?')[0];

    if (urlPath === '/api/v1/jobs' || (urlPath === '/jobs' && req.method === 'POST')) {
        if (mockApiMode === 'unavailable') {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ detail: 'Database connection failed' }));
            return true;
        }
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(VALID_JOBS_FIXTURE));
        return true;
    }

    if (urlPath === '/api/v1/match' || urlPath === '/api/v1/jobs/match' || (urlPath === '/match' && req.method === 'POST')) {
        if (mockApiMode === 'unavailable') {
            res.writeHead(503, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ detail: 'Match service unavailable' }));
            return true;
        }
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(VALID_MATCH_FIXTURE));
        return true;
    }

    if (urlPath === '/api/v1/analytics/skills' || urlPath === '/api/v1/analytics/overview') {
        if (mockApiMode === 'unavailable') {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ detail: 'Analytics unavailable' }));
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
// Tests
// ─────────────────────────────────────────────────────────────────────────────

test('Spec 09 Acceptance: Accessibility, Focus Management, WAI-ARIA and Viewport Matrix', async () => {
    await startServer();
    const browser = await chromium.launch({ headless: true });

    try {
        const page = await browser.newPage();

        // ─────────────────────────────────────────────────────────────────────
        // 1. Static DOM Lint & Form Accessibility
        // ─────────────────────────────────────────────────────────────────────
        await page.goto(`http://127.0.0.1:${serverPort}/match`);
        await page.waitForLoadState('domcontentloaded');

        // Verify no duplicate IDs
        const ids = await page.$$eval('[id]', elements => elements.map(el => el.id));
        const idSet = new Set();
        const duplicates = [];
        for (const id of ids) {
            if (idSet.has(id)) duplicates.push(id);
            idSet.add(id);
        }
        assert.deepEqual(duplicates, [], `Found duplicate element IDs: ${duplicates.join(', ')}`);

        // Verify form control labeling
        const unlabeledControls = await page.$$eval('input, select, textarea', controls => {
            return controls.filter(c => {
                if (c.type === 'hidden') return false;
                const id = c.id;
                const hasLabel = id && document.querySelector(`label[for="${id}"]`);
                const hasAriaLabel = c.getAttribute('aria-label') || c.getAttribute('aria-labelledby');
                return !hasLabel && !hasAriaLabel;
            }).map(c => c.tagName + (c.id ? `#${c.id}` : ''));
        });
        assert.deepEqual(unlabeledControls, [], `Unlabeled form controls found: ${unlabeledControls.join(', ')}`);

        // Verify brand link is a native anchor
        const brandLink = await page.$('#brand-link');
        assert.ok(brandLink, 'Brand link exists');
        const brandTag = await page.evaluate(el => el.tagName.toLowerCase(), brandLink);
        assert.equal(brandTag, 'a', 'Brand link is a native anchor');
        assert.equal(await brandLink.getAttribute('href'), '/match');

        // ─────────────────────────────────────────────────────────────────────
        // 2. Semantic Sample Profile Buttons & State Tracking
        // ─────────────────────────────────────────────────────────────────────
        const personaBackend = page.locator('#btn-persona-backend');
        const personaAi = page.locator('#btn-persona-ai');
        const textarea = page.locator('#matcher-resume-input');
        const clearBtn = page.locator('#btn-clear-resume');

        assert.ok(await personaBackend.evaluate(el => el.tagName.toLowerCase() === 'button'), 'Sample preset is native button');
        assert.equal(await personaBackend.getAttribute('aria-pressed'), 'false');
        assert.equal(await personaAi.getAttribute('aria-pressed'), 'false');

        // Click preset
        await personaBackend.click();
        assert.equal(await personaBackend.getAttribute('aria-pressed'), 'true');
        assert.equal(await personaAi.getAttribute('aria-pressed'), 'false');
        assert.ok((await textarea.inputValue()).length > 20, 'Textarea populated');

        // Switch preset
        await personaAi.click();
        assert.equal(await personaBackend.getAttribute('aria-pressed'), 'false');
        assert.equal(await personaAi.getAttribute('aria-pressed'), 'true');

        // Manual edit clears pressed state
        await textarea.type(' custom text');
        assert.equal(await personaBackend.getAttribute('aria-pressed'), 'false');
        assert.equal(await personaAi.getAttribute('aria-pressed'), 'false');

        // Clear button clears and focuses
        await clearBtn.click();
        assert.equal(await textarea.inputValue(), '');
        assert.ok(await textarea.evaluate(el => document.activeElement === el), 'Textarea focused after clear');

        // Empty submission exposes a field-connected assertive error.
        await page.click('#btn-run-match');
        assert.equal(await textarea.getAttribute('aria-invalid'), 'true');
        assert.equal(await textarea.getAttribute('aria-describedby'), 'matcher-resume-error');
        const profileError = page.locator('#matcher-resume-error');
        assert.equal(await profileError.getAttribute('role'), 'alert');
        assert.ok(await profileError.isVisible(), 'Profile validation error is visible');
        assert.match(await profileError.innerText(), /paste your profile text/i);

        // Correcting the field clears the validation state.
        await textarea.fill('Python backend engineer');
        assert.equal(await textarea.getAttribute('aria-invalid'), null);
        assert.equal(await profileError.isVisible(), false);

        // ─────────────────────────────────────────────────────────────────────
        // 3. Market Tabs WAI-ARIA & Arrow Key Navigation
        // ─────────────────────────────────────────────────────────────────────
        await page.goto(`http://127.0.0.1:${serverPort}/market`);
        await page.waitForLoadState('networkidle');

        const tabTech = page.locator('#tab-btn-tech');
        const tabSen = page.locator('#tab-btn-seniority');
        const tabLoc = page.locator('#tab-btn-locations');

        assert.equal(await tabTech.getAttribute('role'), 'tab');
        assert.equal(await tabTech.getAttribute('aria-selected'), 'true');
        assert.equal(await tabTech.getAttribute('tabindex'), '0');

        assert.equal(await tabSen.getAttribute('role'), 'tab');
        assert.equal(await tabSen.getAttribute('aria-selected'), 'false');
        assert.equal(await tabSen.getAttribute('tabindex'), '-1');

        // ArrowRight moves to next tab
        await tabTech.focus();
        await page.keyboard.press('ArrowRight');
        assert.equal(await tabSen.getAttribute('aria-selected'), 'true');
        assert.equal(await tabSen.getAttribute('tabindex'), '0');
        assert.equal(await tabTech.getAttribute('aria-selected'), 'false');

        // ArrowRight again -> Locations
        await page.keyboard.press('ArrowRight');
        assert.equal(await tabLoc.getAttribute('aria-selected'), 'true');

        // ArrowRight wraps to Tech
        await page.keyboard.press('ArrowRight');
        assert.equal(await tabTech.getAttribute('aria-selected'), 'true');

        // ─────────────────────────────────────────────────────────────────────
        // 4. Job Drawer Focus Trap, Inert Background & Escape Handling
        // ─────────────────────────────────────────────────────────────────────
        await page.goto(`http://127.0.0.1:${serverPort}/jobs`);
        await page.waitForLoadState('networkidle');

        const drawer = page.locator('#job-inspector-drawer');
        const header = page.locator('#public-app-header');
        const main = page.locator('#public-main-content');
        const closeBtn = page.locator('#drawer-close-btn');

        assert.ok(await drawer.evaluate(el => el.hasAttribute('hidden')), 'Drawer has hidden attribute initially');
        assert.equal(await drawer.getAttribute('aria-hidden'), 'true');
        assert.equal(await header.getAttribute('inert'), null);

        // Open drawer
        const firstRow = page.locator('.job-list-row').first();
        await firstRow.focus();
        await firstRow.click();

        assert.equal(await drawer.getAttribute('hidden'), null);
        assert.equal(await drawer.getAttribute('aria-hidden'), 'false');
        assert.equal(await drawer.getAttribute('aria-modal'), 'true');
        assert.notEqual(await header.getAttribute('inert'), null);
        assert.notEqual(await main.getAttribute('inert'), null);

        // Initial focus is on close button
        await page.waitForTimeout(50);
        assert.ok(await closeBtn.evaluate(el => document.activeElement === el), 'Close button focused on drawer open');

        // Focus wrapping
        await page.keyboard.press('Shift+Tab');
        assert.ok(await page.locator('#drawer-apply-link').evaluate(el => document.activeElement === el), 'Shift+Tab wraps focus to last focusable');

        await page.keyboard.press('Tab');
        assert.ok(await closeBtn.evaluate(el => document.activeElement === el), 'Tab wraps focus back to close button');

        // Close with Escape
        await page.keyboard.press('Escape');
        await page.waitForTimeout(50);

        assert.ok(await drawer.evaluate(el => el.hasAttribute('hidden')), 'Drawer has hidden attribute after close');
        assert.equal(await drawer.getAttribute('aria-hidden'), 'true');
        assert.equal(await header.getAttribute('inert'), null, 'Inert removed');
        assert.ok(await firstRow.evaluate(el => document.activeElement === el), 'Focus returned to trigger row');
        for (const selector of [
            '#drawer-job-title',
            '#drawer-company',
            '#drawer-location',
            '#drawer-workplace',
            '#drawer-skills',
            '#drawer-description',
            '#drawer-published',
            '#drawer-fit-score',
        ]) {
            assert.equal(await page.locator(selector).textContent(), '', selector + ' cleared on close');
        }
        assert.equal(await page.locator('#drawer-apply-link').getAttribute('href'), null);

        // ─────────────────────────────────────────────────────────────────────
        // 5. Live Region Announcements
        // ─────────────────────────────────────────────────────────────────────
        await page.goto(`http://127.0.0.1:${serverPort}/match`);
        await page.waitForLoadState('networkidle');

        const announcer = page.locator('#live-announcer');
        assert.equal(await announcer.getAttribute('role'), 'status');
        assert.equal(await announcer.getAttribute('aria-live'), 'polite');

        await page.click('#btn-persona-backend');
        await page.click('#btn-run-match');
        await page.waitForTimeout(150);

        const announcement = await announcer.textContent();
        assert.ok(announcement.includes('Matching complete') || announcement.includes('matching vacancies'), `Announcement received: ${announcement}`);

        // ─────────────────────────────────────────────────────────────────────
        // 6. Viewport Matrix & 200% Zoom Reflow
        // ─────────────────────────────────────────────────────────────────────
        const viewports = [
            { width: 390, height: 844, name: 'Mobile (390x844)' },
            { width: 768, height: 1024, name: 'Tablet (768x1024)' },
            { width: 1280, height: 800, name: 'Laptop (1280x800)' },
            { width: 1440, height: 900, name: 'Desktop (1440x900)' },
        ];

        for (const vp of viewports) {
            await page.setViewportSize({ width: vp.width, height: vp.height });
            for (const path of ['/match', '/jobs', '/market', '/how-it-works']) {
                await page.goto(`http://127.0.0.1:${serverPort}${path}`);
                await page.waitForLoadState('networkidle');
                const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
                assert.equal(hasOverflow, false, `Page horizontal overflow on ${path} at ${vp.name}`);
            }
        }

        // 200% zoom test (640x400 CSS viewport)
        await page.setViewportSize({ width: 640, height: 400 });
        await page.goto(`http://127.0.0.1:${serverPort}/match`);
        await page.waitForLoadState('networkidle');
        const zoomOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        assert.equal(zoomOverflow, false, 'Horizontal overflow under 200% zoom reflow');

        await page.close();
    } finally {
        await browser.close();
        await stopServer();
    }
});
