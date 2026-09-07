// Extracts the dashboard footer expression from Panel.qml and evaluates it as
// plain JavaScript. This checks the status text only; it does not render QML.
const { test } = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const panel = fs.readFileSync('Panel.qml', 'utf8');
const match = panel.match(/text:(root\.actionStatus \|\| \(.*\))\}\s*$/m);
assert.ok(match, 'Expected a dashboard footer status expression in Panel.qml');
const footer = match[1];

function statusFor(root) {
    const context = {
        root: Object.assign({ actionStatus: '', stale: false, mem: {} }, root),
        Qt: { formatTime: () => '1:00:00 PM' },
    };
    return vm.runInNewContext(footer, context);
}

test('a healthy recorder still reports live telemetry', () => {
    assert.match(statusFor({ mem: { ts: 1, collectorErrors: {} } }), /^LIVE/);
});

test('an offline recorder keeps its own message', () => {
    assert.equal(statusFor({ stale: true, mem: { ts: 1, collectorErrors: { history: 'x' } } }),
        'Telemetry is offline. Check the ram-pulse user service.');
});

test('a degraded recorder is reported instead of a false LIVE line', () => {
    const text = statusFor({ mem: { ts: 1, collectorErrors: { history: 'database is locked' } } });
    assert.doesNotMatch(text, /^LIVE/);
    assert.match(text, /degraded/);
});

test('a process-scan failure is reported the same way', () => {
    assert.match(statusFor({ mem: { ts: 1, collectorErrors: { processes: 'unavailable' } } }), /degraded/);
});

test('a snapshot without the field predates this change and stays live', () => {
    assert.match(statusFor({ mem: { ts: 1 } }), /^LIVE/);
});

test('an explicit action status still wins', () => {
    assert.equal(statusFor({ actionStatus: 'Flushed', mem: { ts: 1, collectorErrors: { history: 'x' } } }), 'Flushed');
});
