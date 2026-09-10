const { test } = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const ctx = { Qt: { rgba: (r, g, b, a) => [r, g, b, a] } };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('Model.js', 'utf8').replace('.pragma library', ''), ctx);

test('readout formats and missing telemetry', () => {
  const m = { total: 16 * 2 ** 30, available: 2.5 * 2 ** 30, used: 13.5 * 2 ** 30, availablePct: 15.625, usedPct: 84.375 };
  assert.equal(ctx.readout(m, 0), '15.6%');
  assert.equal(ctx.readout(m, 1), '84.4%');
  assert.equal(ctx.readout(m, 2), '13.5 GiB');
  assert.equal(ctx.readout(m, 3), '2.5 GiB');
  assert.equal(ctx.readout({}, 0), '—');
  assert.equal(ctx.size(1048576), '1.0 MiB');
});

test('ramp endpoints use the shipped stops', () => {
  for (const [p, c] of [[0, [133, 13, 41]], [50, [239, 204, 69]], [100, [67, 242, 161]]]) {
    const r = ctx.ramp(p);
    c.forEach((v, i) => assert.equal(Math.round(r[i] * 255), v));
  }
});

test('state directory prefers an absolute XDG path', () => {
  for (const [xdg, expected] of [[undefined, '/home/test/.local/state/ram-pulse'], ['', '/home/test/.local/state/ram-pulse'],
      ['relative', '/home/test/.local/state/ram-pulse'], ['/state', '/state/ram-pulse']])
    assert.equal(ctx.stateDir('/home/test', xdg), expected);
});

test('accounting totals PSS and never sums RSS', () => {
  assert.equal(ctx.totalOf({ count: 1, pss: 100, rss: 900 }), 100);
  assert.equal(ctx.kindOf({ count: 1, pss: 100, rss: 900 }), 'proportional');
  assert.equal(ctx.totalOf({ count: 2, pss: 100, rss: 900 }), 100);
  assert.equal(ctx.totalOf({ pss: 100, rss: 900 }), 900);
  assert.equal(ctx.kindOf({ pss: 100, rss: 900 }), 'resident');
  assert.equal(ctx.totalOf({ count: 2, pss: null, rss: 900 }), 900);
  assert.equal(ctx.totalOf({ count: 1, pss: undefined, rss: 900 }), 900);
  assert.equal(ctx.totalOf({ count: 1, pss: 0, rss: 900 }), 0);
  assert.equal(ctx.kindOf({ count: 1, pss: 0, rss: 900 }), 'proportional');
});

test('pagination clamps to the page holding the final row', () => {
  assert.equal(ctx.pageCount(0, 8), 1);
  assert.equal(ctx.pageCount(9, 8), 2);
  assert.equal(ctx.pageCount(16, 8), 2);
  assert.equal(ctx.clampPage(2, 2, 8), 0);
  assert.equal(ctx.clampPage(2, 9, 8), 1);
  assert.equal(ctx.clampPage(2, 0, 8), 0);
  assert.equal(ctx.clampPage(5, 17, 8), 2);
  assert.equal(ctx.clampPage(5, 16, 8), 1);
  assert.equal(ctx.clampPage(2, 24, 8), 2);
  assert.equal(ctx.clampPage(0, 24, 8), 0);
  assert.equal(ctx.PAGE_SIZE, 8);
});

test('footer reports live, offline and degraded recorders', () => {
  assert.match(ctx.recorderStatus('', false, 0, '1:00 PM'), /^LIVE/);
  assert.equal(ctx.recorderStatus('', true, 1, '1:00 PM'), 'Telemetry is offline. Check the ram-pulse user service.');
  assert.match(ctx.recorderStatus('', false, 1, '1:00 PM'), /degraded/);
  assert.doesNotMatch(ctx.recorderStatus('', false, 1, '1:00 PM'), /^LIVE/);
  assert.match(ctx.recorderStatus('', false, undefined, '1:00 PM'), /^LIVE/);
  assert.equal(ctx.recorderStatus('Flushed', false, 1, '1:00 PM'), 'Flushed');
});

test('destination labels name the window or its absence', () => {
  assert.equal(ctx.targetLabel({ target: { address: '0x', title: 't', host: { kind: 'herdr', pane: 'p' } } }), 'Herdr p · t');
  assert.equal(ctx.targetLabel({ target: { address: '0x', title: 't', host: { kind: 'tmux', pane: '%3' } } }), 'tmux %3 · t');
  assert.equal(ctx.targetLabel({ target: { address: '0x', title: 't', host: {} } }), 't');
  assert.equal(ctx.targetLabel({ count: 2, names: ['a', 'b'] }), 'a, b · no attached window');
  assert.equal(ctx.targetLabel({}), 'Background process · no attached window');
});

test('history ranges are single-sourced', () => {
  assert.equal([...ctx.RANGES.map(r => r.seconds)].join(','), '3600,86400,604800');
  assert.ok(ctx.validRange(3600) && ctx.validRange(86400) && ctx.validRange(604800));
  assert.ok(!ctx.validRange(123));
});

test('panel wires its pure logic through the model', () => {
  const panel = fs.readFileSync('Panel.qml', 'utf8');
  for (const name of ['Model.PAGE_SIZE', 'Model.RANGES', 'Model.totalOf', 'Model.targetLabel', 'Model.recorderStatus', 'Model.clampPage', 'root.tabs', 'root.lastTab'])
    assert.ok(panel.includes(name), 'Panel no longer wires ' + name);
});
