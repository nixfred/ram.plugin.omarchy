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

// Half the themes on a typical box define a red, yellow and green too muted to
// work as a warning: 2-haxorz's three stops sit at 0.23, 0.13 and 0.11
// saturation, and vantablack's are pure greyscale. The ramp keeps each theme's
// hue and raises only what it must to stay tellable apart at a glance. A stop
// with almost no chroma has no hue worth preserving, so the shipped hue stands
// in rather than tinting grey at random.
var RAMP_MIN_SAT = 0.55
var RAMP_MIN_LIGHT = 0.42
var RAMP_MAX_LIGHT = 0.66
var RAMP_HUE_FLOOR = 0.12

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

// colors.toml is the theme's own palette file. Only the three keys the ramp
// needs are read; a theme that omits one keeps the shipped colour for that
// stop rather than falling back to a whole foreign ramp. The shipped colours
// are deliberate and are never put through the floor.
function themeRamp(text) {
    var out = {low: RAMP_FALLBACK.low, mid: RAMP_FALLBACK.mid, high: RAMP_FALLBACK.high}
    var keys = {red: 'low', yellow: 'mid', green: 'high'}
    var lines = String(text || '').split('\n')
    for (var i = 0; i < lines.length; i++) {
        var m = /^\s*([A-Za-z0-9_]+)\s*=\s*["']?(#[0-9A-Fa-f]{6})/.exec(lines[i])
        if (m && keys[m[1]] && rgbOf(m[2], null)) {
            var slot = keys[m[1]]
            out[slot] = readableStop(m[2], RAMP_FALLBACK[slot])
        }
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
