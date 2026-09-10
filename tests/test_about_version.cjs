// The About line reads its version from the manifest, never from a
// hardcoded literal: the registry stays the first choice, and the
// manifest installed beside the panel fills in where the shell exposes
// no registry view to the widget.
const { test } = require('node:test');
const fs = require('node:fs');
const assert = require('node:assert/strict');

const panel = fs.readFileSync('Panel.qml', 'utf8');
const manifest = JSON.parse(fs.readFileSync('manifest.json', 'utf8'));

test('no hardcoded version survives a manifest bump', () => {
    assert.doesNotMatch(panel, new RegExp(manifest.version.replace(/\./g, '\\.')));
});

test('the registry stays the first choice', () => {
    assert.match(panel, /bar\.shell\.pluginRegistry/);
    assert.match(panel, /installedPlugins/);
});

test('the installed manifest fills in where the registry is unreachable', () => {
    assert.match(panel, /id:manifestFile/);
    assert.match(panel, /Qt\.resolvedUrl\('manifest\.json'\)/);
    assert.match(panel, /registryManifest \|\| .*fileManifest/);
});

test('unreadable manifests still fall back instead of blanking the About line', () => {
    assert.match(panel, /repoUrl.*nixfred\/ram\.plugin\.omarchy/);
    assert.match(panel, /homeUrl.*nixfred\.com/);
    assert.match(panel, /pluginVersion\s*\|\|\s*'unavailable'/);
});
