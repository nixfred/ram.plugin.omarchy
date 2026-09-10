.pragma library
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v) || 0)) }
// Headroom ramp carries meaning, so it stays a traffic light in the theme's
// own red, yellow and green. Fallbacks stand in for missing keys.
var RAMP_FALLBACK = {low: '#850d29', mid: '#efcc45', high: '#43f2a1'}

function rgbOf(hex, fallback) {
    var m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(hex || '').trim())
    if (!m) return fallback
    return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)]
}

function hexOf(rgb) {
    var out = '#'
    for (var i = 0; i < 3; i++) {
        var v = Math.round(Math.min(Math.max(rgb[i], 0), 1) * 255).toString(16)
        out += v.length < 2 ? '0' + v : v
    }
    return out
}

function rgbToHsl(r, g, b) {
    var mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, h = 0, s = 0
    if (mx !== mn) {
        var d = mx - mn
        s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn)
        if (mx === r) h = (g - b) / d + (g < b ? 6 : 0)
        else if (mx === g) h = (b - r) / d + 2
        else h = (r - g) / d + 4
        h /= 6
    }
    return [h, s, l]
}

function hslToRgb(h, s, l) {
    if (s === 0) return [l, l, l]
    var hi = l < 0.5 ? l * (1 + s) : l + s - l * s
    var lo = 2 * l - hi
    function stop(t) {
        if (t < 0) t += 1
        if (t > 1) t -= 1
        if (t < 1/6) return lo + (hi - lo) * 6 * t
        if (t < 1/2) return hi
        if (t < 2/3) return lo + (hi - lo) * (2/3 - t) * 6
        return lo
    }
    return [stop(h + 1/3), stop(h), stop(h - 1/3)]
}

// Near-achromatic stops borrow the shipped hue; lifted stops need minimum
// saturation, lightness bounds and separation to stay tellable apart.
var RAMP_MIN_SAT = 0.55
var RAMP_MIN_LIGHT = 0.30
var RAMP_MAX_LIGHT = 0.78
var RAMP_HUE_FLOOR = 0.02

// Named keys win over terminal slots where both exist.
var PALETTE_ALIASES = {red: ['red', 'color1'], yellow: ['yellow', 'color3'],
                       green: ['green', 'color2']}

// Minimum weighted RGB distance between stops, measured after lifting.
var RAMP_SEPARATION_MIN = 80

// Cheap redmean distance: enough to tell three hues from one mud.
function separation(a, b) {
    var mean = (a[0] + b[0]) / 2, dr = a[0] - b[0], dg = a[1] - b[1], db = a[2] - b[2]
    return Math.sqrt((2 + mean / 256) * dr * dr + 4 * dg * dg + (2 + (255 - mean) / 256) * db * db)
}

function readableStop(themeHex, shippedHex) {
    var t = rgbOf(themeHex, null)
    if (!t) return shippedHex
    var shipped = rgbOf(shippedHex, [128, 128, 128])
    var a = rgbToHsl(t[0]/255, t[1]/255, t[2]/255)
    var b = rgbToHsl(shipped[0]/255, shipped[1]/255, shipped[2]/255)
    var hue = a[1] < RAMP_HUE_FLOOR ? b[0] : a[0]
    var sat = Math.max(a[1], RAMP_MIN_SAT)
    var light = Math.min(Math.max(a[2], RAMP_MIN_LIGHT), RAMP_MAX_LIGHT)
    return hexOf(hslToRgb(hue, sat, light))
}

// Only the three ramp keys are read. Partial palettes and indistinguishable
// triples fall back as a set, never mixed.
function themeRamp(text) {
    var found = {}, lines = String(text || '').split('\n')
    for (var i = 0; i < lines.length; i++) {
        var m = /^\s*([A-Za-z0-9_]+)\s*=\s*["']?(#[0-9A-Fa-f]{6})/.exec(lines[i])
        if (m) found[m[1].toLowerCase()] = m[2]
    }
    var slots = {red: 'low', yellow: 'mid', green: 'high'}
    var out = {low: RAMP_FALLBACK.low, mid: RAMP_FALLBACK.mid, high: RAMP_FALLBACK.high}
    var complete = true
    for (var role in slots) {
        var slot = slots[role], keys = PALETTE_ALIASES[role], picked = null
        for (var k = 0; k < keys.length; k++) {
            if (found[keys[k]] && rgbOf(found[keys[k]], null)) { picked = found[keys[k]]; break }
        }
        if (picked === null) { complete = false; continue }
        out[slot] = readableStop(picked, RAMP_FALLBACK[slot])
    }
    if (!complete) return {low: RAMP_FALLBACK.low, mid: RAMP_FALLBACK.mid, high: RAMP_FALLBACK.high}
    var low = rgbOf(out.low, null), mid = rgbOf(out.mid, null), high = rgbOf(out.high, null)
    if (separation(low, mid) < RAMP_SEPARATION_MIN || separation(mid, high) < RAMP_SEPARATION_MIN)
        return {low: RAMP_FALLBACK.low, mid: RAMP_FALLBACK.mid, high: RAMP_FALLBACK.high}
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
// Single sources for list paging and history ranges; QML passes them explicitly.
var PAGE_SIZE = 8
var RANGES = [{text: '1 hour', seconds: 3600}, {text: '24 hours', seconds: 86400}, {text: '7 days', seconds: 604800}]
function validRange(v) { for (var i = 0; i < RANGES.length; i++) if (RANGES[i].seconds === v) return true; return false }
// Group totals are PSS and may be added; incomplete groups fall back to RSS.
function totalOf(row) { return row && row.count >= 1 && row.pss !== null && row.pss !== undefined ? row.pss : row.rss }
function kindOf(row) { return row && row.count >= 1 && row.pss !== null && row.pss !== undefined ? 'proportional' : 'resident' }
function pageCount(count, pageSize) { return Math.max(1, Math.ceil((Number(count) || 0) / pageSize)) }
function clampPage(page, count, pageSize) { return Math.min(Math.max(0, Number(page) || 0), pageCount(count, pageSize) - 1) }
function targetLabel(row) {
    if (!row) return ''
    var t = row.target
    if (t && t.address) {
        var prefix = t.host && t.host.kind === 'herdr' ? 'Herdr ' + (t.host.pane || '') + ' · ' : t.host && t.host.kind === 'tmux' ? 'tmux ' + (t.host.pane || '') + ' · ' : ''
        return prefix + (t.title || '')
    }
    if (row.count > 1) return (row.names || []).join(', ') + ' · no attached window'
    return 'Background process · no attached window'
}
function recorderStatus(actionStatus, stale, hasErrors, timeText) {
    if (actionStatus) return actionStatus
    if (stale) return 'Telemetry is offline. Check the ram-pulse user service.'
    if (hasErrors) return 'Live memory is available; recorder details are degraded. Check the ram-pulse user service.'
    return 'LIVE · updated ' + timeText + '  ·  History stays on this machine  ·  Esc closes'
}
