// Extracts the inline accounting functions from Panel.qml and evaluates them as
// plain JavaScript. This checks the value and label chosen for a row; it does
// not render QML.
const { test } = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const panel = fs.readFileSync('Panel.qml', 'utf8');
const ctx = {};
vm.createContext(ctx);
for (const name of ['totalOf', 'kindOf']) {
    const source = panel.match(new RegExp('function ' + name + '\\(row\\) \\{[^\\n]*\\}'));
    assert.ok(source, 'Expected inline accounting function: ' + name);
    vm.runInContext(source[0], ctx);
}

test('a one-process app is shown with the value it was ranked by', () => {
    assert.equal(ctx.totalOf({ count: 1, pss: 100, rss: 900 }), 100);
    assert.equal(ctx.kindOf({ count: 1, pss: 100, rss: 900 }), 'proportional');
});

test('a multi-process app stays proportional', () => {
    assert.equal(ctx.totalOf({ count: 2, pss: 100, rss: 900 }), 100);
    assert.equal(ctx.kindOf({ count: 2, pss: 100, rss: 900 }), 'proportional');
});

test('a flat process row stays resident', () => {
    assert.equal(ctx.totalOf({ pss: 100, rss: 900 }), 900);
    assert.equal(ctx.kindOf({ pss: 100, rss: 900 }), 'resident');
});

test('an incomplete group still falls back to resident', () => {
    assert.equal(ctx.totalOf({ count: 2, pss: null, rss: 900 }), 900);
    assert.equal(ctx.kindOf({ count: 2, pss: null, rss: 900 }), 'resident');
    assert.equal(ctx.totalOf({ count: 1, pss: undefined, rss: 900 }), 900);
});

test('a valid zero proportional total is not treated as missing', () => {
    assert.equal(ctx.totalOf({ count: 1, pss: 0, rss: 900 }), 0);
    assert.equal(ctx.kindOf({ count: 1, pss: 0, rss: 900 }), 'proportional');
});
