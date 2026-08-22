const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function loadController(fetchImpl, options = {}) {
    const elements = new Map();
    const element = (id) => {
        if (!elements.has(id)) {
            elements.set(id, {
                id,
                value: '',
                innerHTML: '',
                innerText: '',
                textContent: '',
                disabled: false,
                style: {},
                dataset: {},
                listeners: {},
                addEventListener(event, fn) {
                    this.listeners[event] = this.listeners[event] || [];
                    this.listeners[event].push(fn);
                },
                dispatchEvent(event) {
                    if (this.listeners[event]) {
                        this.listeners[event].forEach(fn => fn({ preventDefault() {} }));
                    }
                },
                appendChild() {},
                classList: {
                    _classes: new Set(),
                    add(c) { this._classes.add(c); },
                    remove(c) { this._classes.delete(c); },
                    toggle(c, force) {
                        if (force === undefined) {
                            if (this._classes.has(c)) this._classes.delete(c);
                            else this._classes.add(c);
                        } else if (force) {
                            this._classes.add(c);
                        } else {
                            this._classes.delete(c);
                        }
                    },
                    contains(c) { return this._classes.has(c); },
                },
                focus() {},
                remove() {},
                scrollIntoView() {},
                getAttribute(attr) { return this[attr] || null; },
                setAttribute(attr, val) { this[attr] = val; },
                removeAttribute(attr) { delete this[attr]; },
            });
        }
        return elements.get(id);
    };

    const logs = { log: [], warn: [], error: [] };
    const document = {
        addEventListener() {},
        createElement() { return element(`created-${elements.size}`); },
        getElementById: element,
        querySelectorAll(selector) {
            return [];
        },
    };
    const window = {
        API_BASE_URL: options.apiBaseUrl !== undefined ? options.apiBaseUrl : '',
        location: { pathname: options.pathname || '/jobs' },
        history: { pushState() {} },
        addEventListener() {},
    };
    const context = vm.createContext({
        console: {
            warn(...args) { logs.warn.push(args.join(' ')); },
            error(...args) { logs.error.push(args.join(' ')); },
            log(...args) { logs.log.push(args.join(' ')); },
        },
        document,
        window,
        fetch: fetchImpl,
        setTimeout,
        clearTimeout,
        AbortController: globalThis.AbortController,
    });
    const source = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'script.js'), 'utf8');
    vm.runInContext(source, context, { filename: 'frontend/script.js' });
    return { context, element, logs, window };
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. Jobs View Truthfulness & Contract Parity Tests
// ─────────────────────────────────────────────────────────────────────────────

test('Jobs reports live data unavailable when the API returns HTML', async () => {
    const htmlResponse = {
        ok: true,
        status: 200,
        headers: { get: (h) => (h.toLowerCase() === 'content-type' ? 'text/html; charset=utf-8' : null) },
        json: async () => ({ items: [{ company: 'silently accepted HTML' }] }),
    };
    const { context, element } = loadController(async () => htmlResponse);

    await vm.runInContext('runJobExplorer("")', context);

    assert.match(element('explorer-results-list').innerHTML, /Live data unavailable right now/i);
    assert.match(element('explorer-results-count').textContent, /Unavailable/i);
    assert.doesNotMatch(element('explorer-results-list').innerHTML, /VectorAI Labs/i);
    assert.doesNotMatch(element('explorer-results-list').innerHTML, /silently accepted HTML/i);
});

test('Jobs reports live data unavailable on HTTP 404 / 405 / 500 status', async () => {
    for (const status of [404, 405, 500]) {
        const errorResponse = {
            ok: false,
            status,
            headers: { get: () => 'application/json' },
            json: async () => ({ detail: 'Error' }),
        };
        const { context, element } = loadController(async () => errorResponse);

        await vm.runInContext('runJobExplorer("")', context);

        assert.match(element('explorer-results-list').innerHTML, /Live data unavailable right now/i);
        assert.match(element('explorer-results-count').textContent, /Unavailable/i);
    }
});

test('Jobs reports live data unavailable when response body is invalid or wrong shape', async () => {
    const invalidShapeResponse = {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({ not_items: 123 }),
    };
    const { context, element } = loadController(async () => invalidShapeResponse);

    await vm.runInContext('runJobExplorer("")', context);

    assert.match(element('explorer-results-list').innerHTML, /Live data unavailable right now/i);
    assert.match(element('explorer-results-count').textContent, /Unavailable/i);
});

test('Jobs rejects non-contract response shapes (raw array, results field, missing pagination fields)', async () => {
    // 1. Raw array
    let { context, element } = loadController(async () => ({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ([{ id: 1, job_title: 'Engineer' }]),
    }));
    await vm.runInContext('runJobExplorer("")', context);
    assert.match(element('explorer-results-count').textContent, /Unavailable/i);

    // 2. data.results instead of data.items
    ({ context, element } = loadController(async () => ({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({ results: [{ id: 1, job_title: 'Engineer' }], pagination: { page: 1, page_size: 20, total_items: 1, total_pages: 1, has_next: false, has_prev: false } }),
    })));
    await vm.runInContext('runJobExplorer("")', context);
    assert.match(element('explorer-results-count').textContent, /Unavailable/i);

    // 3. Incomplete pagination
    ({ context, element } = loadController(async () => ({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({ items: [{ id: 1, job_title: 'Engineer' }], pagination: { total_items: 1 } }),
    })));
    await vm.runInContext('runJobExplorer("")', context);
    assert.match(element('explorer-results-count').textContent, /Unavailable/i);
});

test('Jobs distinguishes valid empty response from unavailable state', async () => {
    const emptyResponse = {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
            items: [],
            pagination: {
                page: 1,
                page_size: 25,
                total_items: 0,
                total_pages: 1,
                has_next: false,
                has_prev: false,
            },
        }),
    };
    const { context, element } = loadController(async () => emptyResponse);

    await vm.runInContext('runJobExplorer("")', context);

    assert.match(element('explorer-results-list').innerHTML, /No vacancies matched these filters/i);
    assert.match(element('explorer-results-count').textContent, /0/);
    assert.doesNotMatch(element('explorer-results-list').innerHTML, /Live data unavailable/i);
});

test('Jobs clears previous data on subsequent failed fetch', async () => {
    let callCount = 0;
    const fetchImpl = async () => {
        callCount++;
        if (callCount === 1) {
            return {
                ok: true,
                status: 200,
                headers: { get: () => 'application/json' },
                json: async () => ({
                    items: [
                        { id: 1, job_title: 'Software Engineer', company: 'Valid Company', workplace_type: 'Remote' },
                    ],
                    pagination: { total_items: 1, page: 1, page_size: 25, total_pages: 1, has_next: false, has_prev: false },
                }),
            };
        }
        return {
            ok: false,
            status: 503,
            headers: { get: () => 'application/json' },
            json: async () => ({ detail: 'Unavailable' }),
        };
    };

    const { context, element } = loadController(fetchImpl);

    await vm.runInContext('runJobExplorer("")', context);
    assert.match(element('explorer-results-list').innerHTML, /Valid Company/);

    await vm.runInContext('runJobExplorer("")', context);
    assert.doesNotMatch(element('explorer-results-list').innerHTML, /Valid Company/);
    assert.match(element('explorer-results-list').innerHTML, /Live data unavailable right now/i);
    assert.match(element('explorer-results-count').textContent, /Unavailable/i);
    assert.equal(vm.runInContext('cachedExplorerJobs.length', context), 0);
});

test('Jobs preserves user query and filters upon API failure', async () => {
    const { context, element } = loadController(async () => { throw new Error('offline'); });
    element('explorer-query-input').value = 'Python engineer';
    element('exp-filter-region').value = 'Europe';

    await vm.runInContext('runJobExplorer("Python engineer")', context);

    assert.equal(element('explorer-query-input').value, 'Python engineer');
    assert.equal(element('exp-filter-region').value, 'Europe');
    assert.match(element('explorer-results-list').innerHTML, /Live data unavailable right now/i);
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. Candidate Match Truthfulness & Point Breakdown Tests
// ─────────────────────────────────────────────────────────────────────────────

test('Match reports live data unavailable on network error without generating synthetic scores', async () => {
    const { context, element } = loadController(async () => { throw new Error('offline'); });
    element('matcher-resume-input').value = 'Python FastAPI engineer with 4 years experience';

    await vm.runInContext('runCandidateMatch()', context);

    assert.match(element('matcher-empty-state').innerHTML, /Live matching is unavailable right now\. Your profile was not scored\./i);
    assert.equal(element('matcher-results-section').style.display, 'none');
    assert.equal(element('matcher-resume-input').value, 'Python FastAPI engineer with 4 years experience');
    assert.equal(vm.runInContext('cachedMatchedJobs.length', context), 0);
});

test('Match reports live data unavailable on HTTP 405 without fallback scores', async () => {
    const response405 = {
        ok: false,
        status: 405,
        headers: { get: () => 'application/json' },
        json: async () => ({ detail: 'Method Not Allowed' }),
    };
    const { context, element } = loadController(async () => response405);
    element('matcher-resume-input').value = 'Senior Rust Engineer';

    await vm.runInContext('runCandidateMatch()', context);

    assert.match(element('matcher-empty-state').innerHTML, /Live matching is unavailable right now\. Your profile was not scored\./i);
    assert.equal(element('matcher-results-section').style.display, 'none');
    assert.equal(vm.runInContext('cachedMatchedJobs.length', context), 0);
});

test('Match renders exact server points from JobMatchItem contract and does not manufacture breakdown', async () => {
    const validMatchResponse = {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
            total_evaluated: 50,
            total_matches: 1,
            extracted_skills: { hard_skills: ['Python', 'SQL'], soft_skills: ['Communication'] },
            matches: [
                {
                    job_id: 10,
                    job_title: 'Backend Engineer',
                    company: 'Acme Real',
                    location: 'Dublin',
                    region: 'Europe',
                    workplace_type: 'Remote',
                    fit_score: 75.0,
                    hard_skill_overlap: 75.0,
                    soft_skill_overlap: 70.0,
                    vector_similarity: 80.0,
                    hard_points: 37.5,
                    soft_points: 14.0,
                    vector_points: 24.0,
                    total_points: 75.5,
                    gap_analysis: {
                        matched_hard_skills: ['Python'],
                        missing_hard_skills: ['Docker'],
                        matched_soft_skills: ['Communication'],
                        missing_soft_skills: [],
                    },
                },
            ],
        }),
    };
    const { context, element } = loadController(async () => validMatchResponse);
    element('matcher-resume-input').value = 'Python engineer with SQL';

    await vm.runInContext('runCandidateMatch()', context);

    assert.equal(element('matcher-results-section').style.display, 'block');
    assert.equal(element('gauge-score-text').textContent, '75%');
    assert.equal(element('explain-hard-pts').textContent, '37.5 / 50');
    assert.equal(element('explain-soft-pts').textContent, '14.0 / 20');
    assert.equal(element('explain-vec-pts').textContent, '24.0 / 30');
    assert.equal(element('explain-total-pts').textContent, '75.5 / 100');
    assert.match(element('ranked-jobs-list').innerHTML, /Acme Real/);
    assert.equal(element('matcher-empty-state').style.display, 'none');
});

test('Match rejects incomplete match objects without real point components', async () => {
    const incompleteMatchResponse = {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
            total_evaluated: 10,
            total_matches: 1,
            extracted_skills: { hard_skills: ['Python'] },
            matches: [
                {
                    job_id: 10,
                    job_title: 'Backend Engineer',
                    fit_score: 80.0,
                    // missing hard_points, soft_points, vector_points, total_points
                },
            ],
        }),
    };
    const { context, element } = loadController(async () => incompleteMatchResponse);
    element('matcher-resume-input').value = 'Python engineer';

    await vm.runInContext('runCandidateMatch()', context);

    assert.match(element('matcher-empty-state').innerHTML, /Live matching is unavailable right now\. Your profile was not scored\./i);
    assert.equal(element('matcher-results-section').style.display, 'none');
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. Market View Truthfulness & Strict Schema Tests
// ─────────────────────────────────────────────────────────────────────────────

test('Market reports single live data unavailable banner and clears metrics on failure', async () => {
    const { context, element } = loadController(async () => { throw new Error('offline'); });

    await vm.runInContext('fetchMarketMetrics()', context);

    assert.match(element('metric-jobs-count').textContent, /Unavailable/i);
    assert.match(element('metric-markets-count').textContent, /Unavailable/i);
    assert.match(element('metric-skills-count').textContent, /Unavailable/i);
    assert.match(element('metric-top-tech').textContent, /Unavailable/i);
    assert.match(element('explorer-jobs-total-pill').textContent, /Unavailable/i);
    assert.match(element('market-status-banner').innerHTML, /Market aggregates could not be loaded/i);
    assert.equal(element('market-status-text').textContent, 'Update status unavailable');
});

test('Market rejects malformed analytics responses without fabricating percentages', async () => {
    // Missing percentage on workplace distribution item
    const malformedResponse = {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
            total_jobs: 500,
            markets_tracked: 3,
            distinct_skills: 120,
            distinct_companies: 50,
            top_skills: [{ name: 'Python', percentage: 65, count: 325 }],
            salary_by_seniority: [{ name: 'Senior', percentage: 40, count: 200 }],
            top_locations: [{ name: 'Dublin', percentage: 30, count: 150 }],
            workplace_distribution: [{ name: 'Remote' }], // missing percentage!
        }),
    };
    const { context, element } = loadController(async () => malformedResponse);

    await vm.runInContext('fetchMarketMetrics()', context);

    assert.match(element('metric-jobs-count').textContent, /Unavailable/i);
    assert.match(element('market-status-banner').innerHTML, /Market aggregates could not be loaded/i);
});

test('Market clears previously rendered metrics after a subsequent failed fetch', async () => {
    let count = 0;
    const fetchImpl = async () => {
        count++;
        if (count === 1) {
            return {
                ok: true,
                status: 200,
                headers: { get: () => 'application/json' },
                json: async () => ({
                    total_jobs: 500,
                    markets_tracked: 3,
                    distinct_skills: 120,
                    distinct_companies: 50,
                    top_skills: [{ name: 'Python', percentage: 65, count: 325 }],
                    salary_by_seniority: [{ name: 'Senior', percentage: 40, count: 200 }],
                    top_locations: [{ name: 'Dublin', percentage: 30, count: 150 }],
                    workplace_distribution: [{ name: 'Remote', percentage: 60, count: 300 }],
                }),
            };
        }
        throw new Error('API down');
    };

    const { context, element } = loadController(fetchImpl);

    await vm.runInContext('fetchMarketMetrics()', context);
    assert.match(element('metric-jobs-count').textContent, /500/);

    await vm.runInContext('fetchMarketMetrics()', context);
    assert.match(element('metric-jobs-count').textContent, /Unavailable/i);
    assert.doesNotMatch(element('metric-jobs-count').textContent, /500/);
    assert.match(element('market-status-banner').innerHTML, /Market aggregates could not be loaded/i);
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. Static Fixture Elimination & Transport Guarding Tests
// ─────────────────────────────────────────────────────────────────────────────

test('Production controller contains no automatic fixture company fallbacks in output paths', () => {
    const source = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'script.js'), 'utf8');
    const prohibitedFixtures = [
        'VectorAI Labs',
        'FinScale Technologies',
        'Scale AI Systems',
        'Cognitive Retrieval Labs',
    ];
    for (const fixture of prohibitedFixtures) {
        assert.doesNotMatch(source, new RegExp(fixture, 'i'), `Found forbidden fixture "${fixture}" in script.js`);
    }
});

test('fetchApiJson normalizes API_BASE_URL and sets redirect error', async () => {
    let capturedUrl = null;
    let capturedOptions = null;
    const fetchImpl = async (url, options) => {
        capturedUrl = url;
        capturedOptions = options;
        return {
            ok: true,
            status: 200,
            headers: { get: () => 'application/json' },
            json: async () => ({
                items: [],
                pagination: { page: 1, page_size: 20, total_items: 0, total_pages: 1, has_next: false, has_prev: false },
            }),
        };
    };

    const { context } = loadController(fetchImpl, { apiBaseUrl: 'https://api.skillpulse.test/' });

    await vm.runInContext('fetchApiJson("/api/v1/jobs")', context);

    assert.equal(capturedUrl, 'https://api.skillpulse.test/api/v1/jobs');
    assert.equal(capturedOptions.redirect, 'error');
});

test('fetchApiJson logs structured event on public API failure without leaking CV or secrets', async () => {
    const { context, logs } = loadController(async () => {
        return {
            ok: false,
            status: 500,
            headers: { get: () => 'application/json' },
            json: async () => ({ detail: 'Internal Server Error' }),
        };
    });

    try {
        await vm.runInContext('fetchApiJson("/api/v1/jobs", {}, "jobs")', context);
    } catch {
        // expected error
    }

    const allLogs = logs.warn.concat(logs.error, logs.log).join(' ');
    assert.match(allLogs, /event=public_api_failure/);
    assert.match(allLogs, /view=jobs/);
    assert.match(allLogs, /endpoint=\/api\/v1\/jobs/);
    assert.match(allLogs, /status=500/);
});

test('Initial index.html drawer has hidden attribute, aria-hidden true, no 92% placeholder, and no href="#"', () => {
    const html = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'index.html'), 'utf8');
    assert.match(html, /id="job-inspector-drawer"[^>]*hidden[^>]*aria-hidden="true"/);
    assert.match(html, /id="job-drawer-backdrop"[^>]*hidden[^>]*aria-hidden="true"/);
    assert.doesNotMatch(html, /id="drawer-fit-score">92%</);
    assert.doesNotMatch(html, /id="drawer-apply-link"[^>]*href="#"/);
});
