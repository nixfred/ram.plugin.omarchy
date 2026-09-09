.pragma library
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v) || 0)) }
// The headroom ramp is the one colour on screen that carries meaning rather
// than style, so it stays a traffic light — but in the active theme's own red,
// yellow and green. These constants are the ramp the plugin shipped with, and
// they stand in for any key a theme leaves out.
var RAMP_FALLBACK = {low: '#850d29', mid: '#efcc45', high: '#43f2a1'}

function rgbOf(hex, fallback) {
    var m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(hex || '').trim())
    if (!m) return fallback
    return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)]
}

// colors.toml is the theme's own palette file. Only the three keys the ramp
// needs are read; a theme that omits one keeps the shipped colour for that
// stop rather than falling back to a whole foreign ramp.
function themeRamp(text) {
    var out = {low: RAMP_FALLBACK.low, mid: RAMP_FALLBACK.mid, high: RAMP_FALLBACK.high}
    var keys = {red: 'low', yellow: 'mid', green: 'high'}
    var lines = String(text || '').split('\n')
    for (var i = 0; i < lines.length; i++) {
        var m = /^\s*([A-Za-z0-9_]+)\s*=\s*["']?(#[0-9A-Fa-f]{6})/.exec(lines[i])
        if (m && keys[m[1]] && rgbOf(m[2], null)) out[keys[m[1]]] = m[2]
    }
    return out
}

function ramp(percent, palette) {
    var p = palette || RAMP_FALLBACK
    var low = rgbOf(p.low, [133, 13, 41])
    var mid = rgbOf(p.mid, [239, 204, 69])
    var high = rgbOf(p.high, [67, 242, 161])
    var f = clamp(percent, 0, 100) / 100
    var a = f <= 0.5 ? low : mid
    var b = f <= 0.5 ? mid : high
    var t = f <= 0.5 ? f * 2 : (f - 0.5) * 2
    return Qt.rgba((a[0]+(b[0]-a[0])*t)/255, (a[1]+(b[1]-a[1])*t)/255, (a[2]+(b[2]-a[2])*t)/255, 1)
}
function gib(v) { return ((Number(v)||0)/1073741824).toFixed(1) }
function size(v) {
    var n = Number(v)||0
    return n >= 1073741824 ? gib(n)+' GiB' : (n/1048576).toFixed(1)+' MiB'
}
function readout(m, mode) {
    if (!m || !m.total) return '—'
    if (mode === 1) return Number(m.usedPct).toFixed(1)+'%'
    if (mode === 2) return gib(m.used)+' GiB'
    if (mode === 3) return gib(m.available)+' GiB'
    return Number(m.availablePct).toFixed(1)+'%'
}
function modeName(mode) { return ['% available', '% used', 'Amount used', 'Amount available'][mode] || '% available' }
function pct(v) { return (Number(v)||0).toFixed(1)+'%' }
// XDG requires an absolute path; a relative one would resolve against
// whichever working directory the recorder and the panel each happen to have.
function stateDir(home, xdg) { return (xdg && xdg.charAt(0) === '/' ? xdg : home+'/.local/state')+'/ram-pulse' }
