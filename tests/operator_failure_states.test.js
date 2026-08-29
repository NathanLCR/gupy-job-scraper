const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const OPERATOR_DIR = path.join(__dirname, '..', 'operator');

test('operator console exposes read-only dependency health and no schema mutation action', () => {
    const html = fs.readFileSync(path.join(OPERATOR_DIR, 'admin.html'), 'utf8');
    const js = fs.readFileSync(path.join(OPERATOR_DIR, 'admin.js'), 'utf8');

    assert.doesNotMatch(html, /btn-init-db|Initialize DB|Verify & Initialize DB/);
    assert.doesNotMatch(js, /database\/init|btn-init-db/);
    assert.doesNotMatch(html, />395</);
    assert.match(html, /id="database-health-status"[^>]*role="status"[^>]*aria-live="polite"/);
    assert.match(js, /\/health\/ready/);
});

test('adminFetch rejects every non-OK response', async () => {
    const source = fs.readFileSync(path.join(OPERATOR_DIR, 'admin.js'), 'utf8');
    const sandbox = {
        window: { API_BASE_URL: '', location: { replace() {} } },
        document: {
            addEventListener() {},
            getElementById() { return null; },
            querySelectorAll() { return []; },
            querySelector() { return null; },
        },
        fetch: async () => ({ ok: false, status: 500, headers: { get() { return 'application/json'; } } }),
        console: { warn() {}, error() {} },
        setTimeout,
        confirm: () => true,
    };
    const context = vm.createContext(sandbox);
    vm.runInContext(source, context);

    await assert.rejects(
        vm.runInContext("adminFetch('/api/v1/errors')", context),
        /Request failed \(500\)/,
    );
});

test('operator failure copy never claims the system is operational', () => {
    const js = fs.readFileSync(path.join(OPERATOR_DIR, 'admin.js'), 'utf8');
    assert.doesNotMatch(js, /System operational/i);
    assert.match(js, /unavailable/i);
});
