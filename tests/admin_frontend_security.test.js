const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const FRONTEND_DIR = path.join(__dirname, '..', 'frontend');
const OPERATOR_DIR = path.join(__dirname, '..', 'operator');

test('Frontend static directory: does not contain the operator console (Spec 08 §3.1)', () => {
    // admin.html/js/css must live outside frontend/, which is mounted as a
    // public StaticFiles directory in app.py. If they were ever placed back
    // inside frontend/, they would be reachable unauthenticated regardless
    // of any auth check on the /nathan-eh-foda route.
    assert.equal(fs.existsSync(path.join(FRONTEND_DIR, 'admin.html')), false, 'frontend/admin.html must not exist');
    assert.equal(fs.existsSync(path.join(FRONTEND_DIR, 'admin.js')), false, 'frontend/admin.js must not exist');
    assert.equal(fs.existsSync(path.join(FRONTEND_DIR, 'admin.css')), false, 'frontend/admin.css must not exist');
});

test('Operator documents: login is distinct and workspace starts verification-locked', () => {
    const loginHtml = fs.readFileSync(path.join(OPERATOR_DIR, 'login.html'), 'utf-8');
    const html = fs.readFileSync(path.join(OPERATOR_DIR, 'admin.html'), 'utf-8');

    assert.match(loginHtml, /id="admin-key-input"/, 'Login document contains the credential form');
    assert.doesNotMatch(loginHtml, /id="admin-app-layout"/, 'Login document must not contain the workspace');
    assert.doesNotMatch(html, /id="admin-key-input"/, 'Workspace document must not contain the login credential form');
    assert.match(html, /id="admin-app-layout"[^>]*\bhidden\b/, 'Admin layout must have hidden attribute');
    assert.match(html, /id="admin-app-layout"[^>]*aria-hidden="true"/, 'Admin layout must have aria-hidden="true"');
});

test('Admin JS: Contains no default secrets, no X-Admin-Key headers, and no storage reads/writes of secrets', () => {
    const js = fs.readFileSync(path.join(OPERATOR_DIR, 'admin.js'), 'utf-8');

    // 1. No fallback secret
    assert.doesNotMatch(js, /skillpulse-admin-secret/, 'Admin controller must not contain hardcoded secret fallback');

    // 2. No storage reads/writes for admin secret
    assert.doesNotMatch(js, /sessionStorage\.(get|set)Item\(['"]skillpulse_admin/i, 'Admin controller must not persist secrets in sessionStorage');
    assert.doesNotMatch(js, /localStorage\.(get|set)Item\(['"]skillpulse_admin/i, 'Admin controller must not persist secrets in localStorage');

    // 3. No X-Admin-Key header construction
    assert.doesNotMatch(js, /['"]X-Admin-Key['"]/i, 'Admin controller must not send legacy X-Admin-Key header');
});

test('Admin JS: checkAdminAuth strictly verifies 200 JSON contract and fails closed on HTML or invalid responses', async () => {
    const js = fs.readFileSync(path.join(OPERATOR_DIR, 'admin.js'), 'utf-8');

    // Mock DOM elements
    const elements = {
        'admin-auth-overlay': { style: { display: 'flex' } },
        'admin-app-layout': {
            hidden: true,
            attributes: { hidden: 'true', 'aria-hidden': 'true' },
            setAttribute(k, v) { this.attributes[k] = String(v); if (k === 'hidden') this.hidden = true; },
            removeAttribute(k) { delete this.attributes[k]; if (k === 'hidden') this.hidden = false; },
            getAttribute(k) { return this.attributes[k] || null; },
        },
    };

    const mockDocument = {
        getElementById(id) { return elements[id] || null; },
        querySelectorAll() { return []; },
        querySelector() { return null; },
        addEventListener(event, handler) {
            if (event === 'DOMContentLoaded') this.domReadyHandler = handler;
        },
        domReadyHandler: null,
    };

    // Helper to evaluate checkAdminAuth in controlled sandbox
    function runCheckAdminAuth(fetchResponseMock) {
        // Reset DOM state
        elements['admin-auth-overlay'].style.display = 'flex';
        elements['admin-app-layout'].setAttribute('hidden', 'true');
        elements['admin-app-layout'].setAttribute('aria-hidden', 'true');

        let initialDataLoaded = 0;
        let navigationInitialized = 0;
        let actionsInitialized = 0;
        let redirectedTo = null;

        const sandbox = {
            window: {
                API_BASE_URL: '',
                location: { replace(url) { redirectedTo = url; } },
            },
            document: mockDocument,
            fetch: async () => fetchResponseMock,
            loadInitialAdminData: () => { initialDataLoaded += 1; },
            initAdminNavigation: () => { navigationInitialized += 1; },
            initAdminActions: () => { actionsInitialized += 1; },
            console: { warn: () => {}, error: () => {} },
        };

        const vm = require('node:vm');
        const context = vm.createContext(sandbox);
        vm.runInContext(js, context);
        context.initAdminNavigation = () => { navigationInitialized += 1; };
        context.initAdminActions = () => { actionsInitialized += 1; };
        context.loadInitialAdminData = () => { initialDataLoaded += 1; };

        return {
            checkAuth: () => vm.runInContext('checkAdminAuth()', context),
            initialize: () => mockDocument.domReadyHandler(),
            logout: () => vm.runInContext('window.handleAdminLogout()', context),
            isUnlocked: () => elements['admin-app-layout'].getAttribute('hidden') === null && elements['admin-app-layout'].getAttribute('aria-hidden') === 'false',
            isInitialDataLoaded: () => initialDataLoaded,
            navigationCount: () => navigationInitialized,
            actionsCount: () => actionsInitialized,
            redirectedTo: () => redirectedTo,
        };
    }

    // 1. HTML 200 SPA Catchall (Common Pages failure mode) -> Must fail closed
    const htmlResponse = {
        ok: true,
        status: 200,
        headers: { get: (h) => h.toLowerCase() === 'content-type' ? 'text/html; charset=utf-8' : null },
        text: async () => '<!DOCTYPE html><html><body>SPA Root</body></html>',
        json: async () => { throw new Error('Unexpected token < in JSON'); },
    };
    const htmlRunner = runCheckAdminAuth(htmlResponse);
    const htmlAuthResult = await htmlRunner.checkAuth();
    assert.equal(htmlAuthResult, false, 'HTML response must not authenticate');
    assert.equal(htmlRunner.isUnlocked(), false, 'Workspace must remain locked on HTML response');
    assert.equal(htmlRunner.navigationCount(), 0, 'Navigation must not initialize before authentication');
    assert.equal(htmlRunner.actionsCount(), 0, 'Mutation handlers must not initialize before authentication');

    // 2. HTTP 401 Unauthorized -> Must fail closed
    const unauthResponse = {
        ok: false,
        status: 401,
        headers: { get: (h) => h.toLowerCase() === 'content-type' ? 'application/json' : null },
        json: async () => ({ detail: 'Unauthorized' }),
    };
    const unauthRunner = runCheckAdminAuth(unauthResponse);
    const unauthResult = await unauthRunner.checkAuth();
    assert.equal(unauthResult, false);
    assert.equal(unauthRunner.isUnlocked(), false);

    // 3. Wrong JSON shape (e.g. { status: "ok" } without authenticated: true) -> Must fail closed
    const wrongShapeResponse = {
        ok: true,
        status: 200,
        headers: { get: (h) => h.toLowerCase() === 'content-type' ? 'application/json' : null },
        json: async () => ({ status: 'ok' }),
    };
    const wrongShapeRunner = runCheckAdminAuth(wrongShapeResponse);
    const wrongShapeResult = await wrongShapeRunner.checkAuth();
    assert.equal(wrongShapeResult, false);
    assert.equal(wrongShapeRunner.isUnlocked(), false);

    // 4. Exact valid JSON response -> Unlocks workspace
    const validAuthResponse = {
        ok: true,
        status: 200,
        headers: { get: (h) => h.toLowerCase() === 'content-type' ? 'application/json; charset=utf-8' : null },
        json: async () => ({ status: 'authenticated', authenticated: true, role: 'operator' }),
    };
    const validRunner = runCheckAdminAuth(validAuthResponse);
    const validResult = await validRunner.checkAuth();
    assert.equal(validResult, true);
    assert.equal(validRunner.isUnlocked(), true, 'Workspace must unlock on valid contract');
    assert.equal(elements['admin-auth-overlay'].style.display, 'none');
    assert.equal(validRunner.navigationCount(), 0, 'Direct verification alone must not initialize handlers');
    assert.equal(validRunner.actionsCount(), 0, 'Direct verification alone must not initialize mutation handlers');

    const initializedRunner = runCheckAdminAuth(validAuthResponse);
    await initializedRunner.initialize();
    assert.equal(initializedRunner.navigationCount(), 1);
    assert.equal(initializedRunner.actionsCount(), 1);
    assert.equal(initializedRunner.isInitialDataLoaded(), 1);

    // 5. Logout immediately locks workspace
    await validRunner.logout();
    assert.equal(validRunner.isUnlocked(), false, 'Workspace must lock immediately on logout');
    assert.equal(elements['admin-auth-overlay'].style.display, 'flex');
});
