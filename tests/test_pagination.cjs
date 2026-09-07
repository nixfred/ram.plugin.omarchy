// Extracts the listing-change handler from Panel.qml and evaluates it as plain
// JavaScript against a stub root. This checks the page arithmetic; it does not
// render QML.
const { test } = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const panel = fs.readFileSync('Panel.qml', 'utf8');
const handler = panel.match(/onListingChanged:\s*([^\n]+)/);
assert.ok(handler, 'A listing update must revalidate the current page');

function pageAfter(startPage, length) {
    const context = { page: startPage, listing: Array(length) };
    context.root = context;
    vm.runInNewContext(handler[1], context);
    return context.page;
}

test('a list that shrinks to one page pulls the reader back to it', () => {
    assert.equal(pageAfter(2, 2), 0);
});

test('a list that shrinks to two pages clamps to the last one', () => {
    assert.equal(pageAfter(2, 9), 1);
});

test('an empty list is page one, not a negative page', () => {
    assert.equal(pageAfter(2, 0), 0);
});

test('a list that is still long enough leaves the page alone', () => {
    assert.equal(pageAfter(2, 24), 2);
    assert.equal(pageAfter(0, 24), 0);
});

test('the last page is exactly the one holding the final row', () => {
    assert.equal(pageAfter(5, 17), 2);
    assert.equal(pageAfter(5, 16), 1);
});
