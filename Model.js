.pragma library
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v) || 0)) }
function ramp(percent) {
    var f = clamp(percent, 0, 100) / 100
    var a = f <= 0.5 ? [133, 13, 41] : [239, 204, 69]
    var b = f <= 0.5 ? [239, 204, 69] : [67, 242, 161]
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
