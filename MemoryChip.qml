import QtQuick
import "Model.js" as Model

Item {
    id: root
    property real available: 50
    property bool animate: true
    property bool compact: false
    property color tint: Model.ramp(available)
    // The chip's own body. The panel passes the theme's popup background so the
    // silicon reads as a cut-out of the panel rather than a fixed dark square.
    property color body: '#0b141b'
    property real phase: 0
    property real level: available / 100
    implicitWidth: compact ? 28 : 160
    implicitHeight: compact ? 25 : 160
    // One phase revolution every 5.8s, advanced by the repaint tick itself.
    readonly property real phaseStep: tick.interval / 5800
    // Painting is coalesced onto one 10Hz tick and stops while invisible.
    // Do not drive phase from an animation: it repaints at display rate.
    Timer {
        id: tick
        interval: 100; repeat: true
        running: root.animate && root.visible
        onTriggered: { root.phase = (root.phase + root.phaseStep) % 1; canvas.requestPaint() }
    }
    function repaint() { if (root.visible) canvas.requestPaint() }
    onTintChanged: repaint()
    onBodyChanged: repaint()
    onLevelChanged: repaint()
    onVisibleChanged: repaint()
    Canvas {
        id: canvas
        anchors.fill: parent
        onWidthChanged: root.repaint()
        onHeightChanged: root.repaint()
        onPaint: {
            var c = getContext('2d'), w = width, h = height
            c.reset(); c.clearRect(0,0,w,h)
            var cx=w/2, cy=h/2, size=Math.min(w,h), body=size*(root.compact?0.58:0.47)
            var x=cx-body/2, y=cy-body/2, t=root.phase*Math.PI*2
            var aura=c.createRadialGradient(cx,cy,body*0.1,cx,cy,size*0.5)
            aura.addColorStop(0,Qt.alpha(root.tint,0.45)); aura.addColorStop(0.6,Qt.alpha(root.tint,0.20+0.07*Math.sin(t))); aura.addColorStop(1,'transparent')
            c.fillStyle=aura; c.fillRect(0,0,w,h)
            if (!root.compact) {
                for(var ring=0;ring<3;ring++) {
                    c.beginPath(); c.strokeStyle=Qt.alpha(root.tint,0.11+ring*0.04); c.lineWidth=1
                    c.arc(cx,cy,body*(0.78+ring*0.12),0,Math.PI*2); c.stroke()
                    c.beginPath(); c.strokeStyle=Qt.alpha(root.tint,0.65); c.lineWidth=2
                    var ang=t*(ring%2===0?1:-1)+ring*2
                    c.arc(cx,cy,body*(0.78+ring*0.12),ang,ang+0.42);c.stroke()
                }
            }
            c.fillStyle=root.body; c.strokeStyle=root.tint; c.lineWidth=root.compact?1.2:2
            c.fillRect(x,y,body,body)
            c.shadowColor=root.tint; c.shadowBlur=root.compact?5:12
            c.strokeRect(x,y,body,body); c.shadowBlur=0
            c.save();c.beginPath();c.rect(x+2,y+2,body-4,body-4);c.clip()
            var fillY=y+body*(1-root.level)
            var liquid=c.createLinearGradient(0,y,0,y+body)
            liquid.addColorStop(0,Qt.alpha(root.tint,0.65)); liquid.addColorStop(1,Qt.alpha(root.tint,0.16))
            c.beginPath();c.moveTo(x,y+body);c.lineTo(x,fillY)
            for(var px=0;px<=body;px+=2) c.lineTo(x+px,fillY+Math.sin(px/body*Math.PI*3+t)*(root.compact?1:3))
            c.lineTo(x+body,y+body);c.closePath();c.fillStyle=liquid;c.fill()
            c.strokeStyle=Qt.alpha(root.tint,0.35);c.lineWidth=0.8
            for(var row=1;row<4;row++){ c.beginPath();c.moveTo(x,y+body*row/4);c.lineTo(x+body,y+body*row/4);c.stroke() }
            c.restore()
            c.strokeStyle=root.tint;c.lineWidth=root.compact?1:2
            for(var pin=0;pin<4;pin++) {
                var p=body*(pin+1)/5, len=body*0.17
                c.beginPath();c.moveTo(x+p,y-len);c.lineTo(x+p,y);c.moveTo(x+p,y+body);c.lineTo(x+p,y+body+len)
                c.moveTo(x-len,y+p);c.lineTo(x,y+p);c.moveTo(x+body,y+p);c.lineTo(x+body+len,y+p);c.stroke()
                if(!root.compact){
                    var progress=(root.phase+pin/4)%1
                    c.fillStyle=Qt.alpha(root.tint,1-progress*0.5)
                    c.beginPath();c.arc(x+p,y-len-progress*body*0.3,1.7,0,Math.PI*2);c.fill()
                    c.beginPath();c.arc(x+body+len+progress*body*0.3,y+p,1.7,0,Math.PI*2);c.fill()
                }
            }
        }
    }
}
