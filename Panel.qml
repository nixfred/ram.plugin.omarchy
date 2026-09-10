import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
    id: root
    moduleName: 'nixfred.ram-pulse'
    ipcTarget: 'nixfred.ram-pulse'
    manageIpc: false
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    readonly property string stateDir: Model.stateDir(Quickshell.env('HOME'), Quickshell.env('XDG_STATE_HOME'))
    // Theme surface. Every colour the panel paints derives from the active
    // Omarchy theme: the popup roles for chrome, and the theme's own red,
    // yellow and green for the headroom ramp. Card fills and strokes are the
    // foreground laid over the popup background at low alpha, so they follow a
    // light theme as readily as a dark one instead of assuming either.
    readonly property color themeText: Color.popups.text
    readonly property color themeBg: Color.popups.background
    readonly property color themeAccent: Color.accent
    readonly property color themeMuted: Color.muted
    readonly property color themeUrgent: Color.urgent
    readonly property color themeSoft: Qt.alpha(themeText,0.78)
    readonly property color surfaceIdle: Qt.tint(themeBg,Qt.alpha(themeText,0.03))
    readonly property color surface: Qt.tint(themeBg,Qt.alpha(themeText,0.05))
    readonly property color surfaceHover: Qt.tint(themeBg,Qt.alpha(themeText,0.11))
    readonly property color stroke: Qt.tint(themeBg,Qt.alpha(themeText,0.18))
    readonly property color strokeStrong: Qt.tint(themeBg,Qt.alpha(themeText,0.34))
    readonly property string themeFont: bar ? bar.fontFamily : Style.font.family
    // The three ramp stops, read from the theme's own palette file.
    property var rampPalette: Model.RAMP_FALLBACK
    readonly property color rampWarn: rampPalette.mid
    readonly property color rampGood: rampPalette.high
    readonly property string helper: String(Qt.resolvedUrl('ram_pulse.py')).replace(/^file:\/\//,'')
    // Identity for the About line. The manifest is the single source of truth
    // for all three, so bumping a version or moving the repo is one edit there.
    // The constants are the fallback for when the registry is not reachable.
    readonly property var pluginManifest: {
        var reg = bar && bar.shell ? bar.shell.pluginRegistry : null
        return reg && reg.installedPlugins ? (reg.installedPlugins[root.moduleName] || null) : null
    }
    readonly property string pluginVersion: pluginManifest && pluginManifest.version ? String(pluginManifest.version) : ''
    readonly property string repoUrl: pluginManifest && pluginManifest.repository ? String(pluginManifest.repository) : 'https://github.com/nixfred/ram.plugin.omarchy'
    readonly property string homeUrl: pluginManifest && pluginManifest.homepage ? String(pluginManifest.homepage) : 'https://nixfred.com'
    property var mem: ({})
    property var histories: ({})
    property int tab: 0
    property int page: 0
    property int range: Model.RANGES[0].seconds
    property bool chooseMode: false
    property string actionStatus: ''
    property real now: Date.now()/1000
    readonly property bool stale: !mem.ts || now-mem.ts > 15
    readonly property int mode: Model.clamp(setting('displayMode',0),0,3)
    readonly property color tint: stale ? themeMuted : Model.ramp(mem.availablePct,rampPalette)
    readonly property real pressure: mem.psi && mem.psi.some ? mem.psi.some.avg10 : 0
    readonly property var rows: mem.hoarders || []
    readonly property var groups: mem.groups || []
    readonly property bool grouped: setting('groupByApp',true) !== false
    readonly property bool showReadout: setting('showReadout',true) !== false
    readonly property var listing: grouped ? groups : rows
    readonly property var tabs: ['Overview', 'RAM hoarders', 'Memory lab', 'About']
    readonly property int lastTab: tabs.length - 1
    // Telemetry can shorten the list under a reader who is already paging.
    onListingChanged: page=Model.clampPage(page, listing.length, Model.PAGE_SIZE)
    readonly property var chart: histories[String(range)] || {points:[],seconds:range,now:now,bucket:15,count:0,peak:0}
    readonly property string health: stale ? 'WAITING FOR TELEMETRY' : pressure >= 10 ? 'MEMORY IS STALLING' : mem.availablePct < 20 ? 'LOW HEADROOM' : 'ROOM TO BREATHE'

    function setGrouped(value) {
        root.page=0
        root.settings=Object.assign({}, root.settings, {groupByApp:!!value})
        if(root.bar && root.bar.shell) root.bar.shell.updateEntryInline(root.moduleName,root.settings)
    }
    function setMode(value) {
        root.settings=Object.assign({}, root.settings, {displayMode:Model.clamp(value,0,3)})
        if(root.bar && root.bar.shell) root.bar.shell.updateEntryInline(root.moduleName,root.settings)
    }
    function runAction(action, row) {
        if(actionProc.running) return
        actionStatus=action==='flush'?'Writing pending data to disk…':'Finding the existing window…'
        actionProc.command=['python3',helper,action].concat(row?[String(row.pid),String(row.start)]:[])
        actionProc.running=true
    }
    // The panel closes first, so the page is never opened behind a popup the
    // same click dismissed. xdg-open is detached: a cold browser start must not
    // block the shell's event loop.
    function openUrl(url) {
        if(!url) return
        root.close()
        Quickshell.execDetached(['xdg-open',url])
    }
    function status() {
        return JSON.stringify({opened:opened,version:pluginVersion,mode:mode,readout:Model.readout(mem,mode),tint:String(tint),stale:stale,samples:chart.count || 0,tab:tab,chooseMode:chooseMode,total:mem.total,available:mem.available,hoarders:rows.length,groups:groups.length,grouped:grouped,action:actionStatus})
    }
    onOpenedChanged: if(opened) { snapshotFile.reload(); historyFile.reload() }
    FileView {
        id:snapshotFile; path:root.stateDir+'/snapshot.json'; watchChanges:true; printErrors:false
        onFileChanged:reload()
        onLoaded:{try{var m=JSON.parse(text());if(m.total>0)root.mem=m}catch(e){}}
    }
    FileView {
        id:historyFile; path:root.stateDir+'/history.json'; watchChanges:true; printErrors:false
        onFileChanged:reload()
        onLoaded:{try{root.histories=JSON.parse(text())}catch(e){}}
    }
    FileView {
        // The theme's own palette, for the three ramp stops the shell does not
        // expose. watchChanges covers a theme edited in place.
        id:themePalette
        path:Quickshell.env('HOME')+'/.local/state/omarchy/current/theme/colors.toml'
        watchChanges:true; printErrors:false
        onFileChanged:reload()
        onLoaded:root.rampPalette=Model.themeRamp(text())
    }
    // A runtime theme switch does not touch colors.toml in a way the watcher
    // can see: the shell loads it once at startup and has the new palette
    // pushed to Color over IPC instead. So re-read the file whenever the
    // shell's own colours move, which is exactly when that push lands.
    readonly property string themeSignature: String(Color.background)+String(Color.foreground)+String(Color.accent)+String(Color.urgent)
    onThemeSignatureChanged: themePalette.reload()
    Timer { interval:3000; running:true; repeat:true; onTriggered:{root.now=Date.now()/1000; if(root.stale)snapshotFile.reload()} }
    Process {
        id:actionProc
        stdout:StdioCollector { onStreamFinished:{try{var r=JSON.parse(text);root.actionStatus=r.error || r.message || 'Done';if(!r.error && r.message && r.message.indexOf('Focused ')===0)root.close()}catch(e){root.actionStatus='Action could not complete.'}} }
        onExited:function(code){if(code!==0 && root.actionStatus.indexOf('…')>=0)root.actionStatus='Action could not complete.'}
    }
    IpcHandler {
        target:'nixfred.ram-pulse'
        function open():void {root.chooseMode=false;root.open()}
        function close():void {root.close()}
        function toggle():void {root.chooseMode=false;root.toggle()}
        function status():string {return root.status()}
        function modes():void {root.chooseMode=true;root.open()}
        function display(value:int):void {root.setMode(value)}
        function showTab(value:int):void {root.tab=Model.clamp(value,0,root.lastTab);root.chooseMode=false;root.open()}
        function historyRange(value:int):void {if(Model.validRange(value))root.range=value}
        function grouping(value:bool):void {root.setGrouped(value)}
    }
    WidgetButton {
        id:button; anchors.fill:parent;bar:root.bar;labelVisible:false;hasVisualContent:true
        fixedWidth:vertical?-1:barRow.implicitWidth+12
        tooltipText:'RAM Pulse · '+(root.stale?'Telemetry offline':Model.size(root.mem.available)+' available of '+Model.size(root.mem.total))+'\nLeft-click: dashboard · Right-click: readout'
        onPressed:function(b){if(b===Qt.RightButton){root.chooseMode=true;root.open()}else{root.chooseMode=false;root.toggle()}}
        Row {
            id:barRow;anchors.centerIn:parent;spacing:4
            MemoryChip {compact:true;body:root.themeBg;available:root.mem.availablePct || 0;tint:root.tint;animate:!root.stale && root.setting('animated',true)}
            Column {
                visible:root.showReadout
                anchors.verticalCenter:parent.verticalCenter
                Text {text:root.stale?'—':Model.readout(root.mem,root.mode);color:root.barForeground;font.family:Style.font.family;font.pixelSize:12;font.bold:true}
                Text {text:root.mode===1||root.mode===2?'USED':'AVAILABLE';color:root.tint;font.pixelSize:7;font.letterSpacing:0.8}
            }
        }
    }
    component Label: Text {
        color:root.themeMuted;font.pixelSize:12;font.family:root.themeFont;textFormat:Text.PlainText
    }
    component Heading: Text {
        color:root.themeText;font.pixelSize:15;font.bold:true;font.family:root.themeFont;textFormat:Text.PlainText
    }
    component Action: Rectangle {
        id:act
        property string text:''
        property bool selected:false
        property color accent:root.tint
        signal clicked()
        implicitWidth:caption.implicitWidth+26;implicitHeight:34
        radius:9;color:act.selected?Qt.alpha(accent,0.18):area.containsMouse?root.surfaceHover:root.surfaceIdle
        border.color:act.selected?accent:area.containsMouse?root.strokeStrong:root.stroke
        Behavior on color {ColorAnimation{duration:120}}
        Text{id:caption;anchors.centerIn:parent;text:act.text;color:act.selected?root.themeText:root.themeSoft;font.pixelSize:12;font.family:root.themeFont;font.bold:act.selected;textFormat:Text.PlainText}
        MouseArea{id:area;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;onClicked:act.clicked()}
    }
    component Stat: Rectangle {
        property string label:''
        property string value:''
        property string hint:''
        radius:12;color:root.surface;border.color:root.stroke
        Column {anchors.fill:parent;anchors.margins:12;spacing:5
            Label{text:label;font.pixelSize:10;font.letterSpacing:1}
            Heading{text:value;font.pixelSize:20}
            Label{text:hint;font.pixelSize:10}
        }
    }
    KeyboardPanel {
        id:panel;anchorItem:button;owner:root;bar:root.bar;open:root.opened;focusTarget:body
        contentWidth:panel.fittedContentWidth(root.chooseMode?370:740)
        contentHeight:panel.fittedContentHeight(root.chooseMode?modeColumn.implicitHeight:mainColumn.implicitHeight)
        Item {
            id:body;anchors.fill:parent;focus:true
            Keys.onEscapePressed:root.close()
            Keys.onPressed:function(event){
                if(event.key===Qt.Key_Left && !root.chooseMode){root.tab=Math.max(0,root.tab-1);event.accepted=true}
                if(event.key===Qt.Key_Right && !root.chooseMode){root.tab=Math.min(root.lastTab,root.tab+1);event.accepted=true}
                if(root.chooseMode && event.key>=Qt.Key_1 && event.key<=Qt.Key_4){root.setMode(event.key-Qt.Key_1);event.accepted=true}
            }
            Rectangle {anchors.fill:parent;anchors.margins:-10;radius:14;color:root.themeBg}
            Column {
                id:modeColumn;width:parent.width;spacing:12;visible:root.chooseMode
                Heading{text:'BAR READOUT';font.letterSpacing:1.5}
                Label{text:'Choose what lives beside the chip. One decimal.'}
                Repeater {
                    model:4
                    Action {
                        required property int index
                        width:modeColumn.width;height:44;selected:root.mode===index
                        text:(index+1)+'.  '+Model.modeName(index)+'   ·   '+Model.readout(root.mem,index)
                        onClicked:root.setMode(index)
                    }
                }
                Action{text:'Open memory dashboard →';width:parent.width;onClicked:root.chooseMode=false}
            }
            Column {
                id:mainColumn;width:parent.width;spacing:14;visible:!root.chooseMode
                Row {
                    width:parent.width;spacing:10
                    Column {width:parent.width-220;spacing:3
                        Heading{text:'RAM PULSE';font.pixelSize:19;font.letterSpacing:3}
                        Label{text:'Your memory, in motion.';font.pixelSize:11}
                    }
                    Rectangle {width:190;height:32;radius:16;color:Qt.alpha(root.tint,0.14);border.color:Qt.alpha(root.tint,0.5)
                        Row {anchors.centerIn:parent;spacing:7
                            Rectangle {width:6;height:6;radius:3;color:root.tint;anchors.verticalCenter:parent.verticalCenter
                                SequentialAnimation on opacity {running:root.opened&&!root.stale;loops:Animation.Infinite;NumberAnimation{to:0.3;duration:900}NumberAnimation{to:1;duration:900}}
                            }
                            Label{text:root.health;color:root.themeText;font.pixelSize:9;font.bold:true}
                        }
                    }
                }
                Row {spacing:8
                    Repeater {model:root.tabs
                        Action {required property int index;required property string modelData;text:modelData;selected:root.tab===index;onClicked:root.tab=index}
                    }
                }
                Column {
                    width:parent.width;spacing:14;visible:root.tab===0
                    height:visible?implicitHeight:0
                    Rectangle {
                        width:parent.width;height:170;radius:16;border.color:Qt.alpha(root.tint,0.45)
                        gradient:Gradient {GradientStop{position:0;color:Qt.alpha(root.tint,0.13)}GradientStop{position:1;color:root.surface}}
                        MemoryChip {id:heroChip;body:root.themeBg;x:12;y:5;width:160;height:160;available:root.mem.availablePct || 0;tint:root.tint;animate:root.opened&&root.tab===0&&!root.stale&&root.setting('animated',true)}
                        Column {x:188;y:20;spacing:6
                            Label{text:'AVAILABLE HEADROOM';font.pixelSize:11;font.letterSpacing:2}
                            Row {spacing:10
                                Text {text:root.stale?'—':Model.gib(root.mem.available);color:root.themeText;font.pixelSize:52;font.family:root.themeFont;font.weight:Font.Light}
                                Label{text:'GiB';font.pixelSize:18;anchors.bottom:parent.bottom;anchors.bottomMargin:10}
                            }
                            Label{text:Model.pct(root.mem.availablePct)+' available  /  '+Model.size(root.mem.total)+' usable physical RAM';color:root.themeSoft}
                            Label{text:'Used = total − available, including kernel reservations.';font.pixelSize:10}
                        }
                        Text {anchors.right:parent.right;anchors.rightMargin:20;anchors.top:parent.top;anchors.topMargin:22;text:Model.pct(root.mem.usedPct)+'\nused';color:Qt.alpha(root.themeText,0.5);font.pixelSize:15;horizontalAlignment:Text.AlignRight}
                    }
                    Row {width:parent.width;spacing:10
                        Stat{width:(parent.width-20)/3;height:96;label:'IN USE';value:Model.size(root.mem.used);hint:Model.pct(root.mem.usedPct)+' of physical RAM'}
                        Stat{width:(parent.width-20)/3;height:96;label:'REUSABLE CACHE';value:Model.size(root.mem.cache);hint:'Kernel reclaims it as needed'}
                        Stat{width:(parent.width-20)/3;height:96;label:'MEMORY PRESSURE';value:Model.pct(root.pressure);hint:'Time tasks stalled · last 10s'}
                    }
                    Rectangle {width:parent.width;height:242;radius:14;color:root.surface;border.color:root.stroke
                        Column {anchors.fill:parent;anchors.margins:14;spacing:9
                            Row {width:parent.width;spacing:7
                                Heading{text:'CONTINUOUS HISTORY';font.pixelSize:12;width:parent.width-222;anchors.verticalCenter:parent.verticalCenter}
                                Repeater{model:Model.RANGES
                                    Action{required property var modelData;text:modelData.text;selected:root.range===modelData.seconds;implicitWidth:68;implicitHeight:28;onClicked:root.range=modelData.seconds}
                                }
                            }
                            HistoryGraph{width:parent.width;height:139;historyData:root.chart;tint:root.tint
                                swapTint:root.themeAccent;grid:root.stroke;axisText:root.themeMuted
                                crosshair:root.strokeStrong;hoverBackground:root.surfaceHover
                                hoverBorder:root.stroke;hoverForeground:root.themeText;fontFamily:root.themeFont}
                            Row{spacing:14
                                Label{text:'━ RAM used';color:root.tint;font.pixelSize:10}
                                Label{text:'━ Swap used';color:root.themeAccent;font.pixelSize:10}
                                Label{text:'Peak '+Model.pct(root.chart.peak)+'  ·  '+(root.chart.count||0)+' samples';font.pixelSize:10}
                            }
                            Label{text:(root.chart.count||0)<2?'History is starting. Samples accumulate every 15 seconds.':'Recording while closed · 7-day retention · hover to inspect · faint line = RAM peaks';font.pixelSize:10}
                        }
                    }
                    Rectangle {width:parent.width;height:105;radius:14;color:root.surface;border.color:root.stroke
                        Column{anchors.fill:parent;anchors.margins:14;spacing:9
                            Row{width:parent.width
                                Heading{text:'SWAP + ZRAM';font.pixelSize:12;width:parent.width/2}
                                Label{text:Model.size(root.mem.swapUsed)+' / '+Model.size(root.mem.swapTotal);width:parent.width/2;horizontalAlignment:Text.AlignRight;color:root.themeSoft}
                            }
                            Rectangle{width:parent.width;height:5;radius:3;color:root.stroke
                                Rectangle{width:parent.width*Model.clamp(root.mem.swapTotal?root.mem.swapUsed/root.mem.swapTotal:0,0,1);height:parent.height;radius:3;color:root.themeAccent;Behavior on width{NumberAnimation{duration:800}}}
                            }
                            Label{text:root.mem.zram?'zram stores '+Model.size(root.mem.zram.original)+' in '+Model.size(root.mem.zram.physical)+' of real RAM  ·  '+(root.mem.zram.physical?root.mem.zram.original/root.mem.zram.physical:0).toFixed(1)+'× effective ratio':'Reading compressed swap…';font.pixelSize:11}
                            Label{text:'In '+Model.size(root.mem.rates?root.mem.rates.pswpin*root.mem.pageSize:0)+'/s  ·  Out '+Model.size(root.mem.rates?root.mem.rates.pswpout*root.mem.pageSize:0)+'/s  ·  swap allocation alone does not mean active thrashing';font.pixelSize:10}
                        }
                    }
                }
                Column {
                    width:parent.width;spacing:10;visible:root.tab===1;height:visible?implicitHeight:0
                    Row{width:parent.width;spacing:8
                        Heading{text:'TOP RAM HOARDERS';width:parent.width-300;font.pixelSize:13;anchors.verticalCenter:parent.verticalCenter}
                        Action{text:'By app';selected:root.grouped;implicitWidth:76;implicitHeight:28;onClicked:root.setGrouped(true)}
                        Action{text:'By process';selected:!root.grouped;implicitWidth:98;implicitHeight:28;onClicked:root.setGrouped(false)}
                        Label{text:'refresh 9s';font.pixelSize:10;anchors.verticalCenter:parent.verticalCenter}
                    }
                    Label{text:root.grouped?'One row per window or service. Click a row to visit it. Ranked by proportional RAM.':'One row per process, ranked by resident RAM. Click a row to visit its app or attached session.';font.pixelSize:11}
                    Repeater {
                        model:root.listing.slice(root.page*Model.PAGE_SIZE,root.page*Model.PAGE_SIZE+Model.PAGE_SIZE)
                        Rectangle {
                            id:procRow
                            required property var modelData
                            required property int index
                            width:mainColumn.width;height:65;radius:10
                            color:hoarderMouse.containsMouse?root.surfaceHover:root.surface;border.color:hoarderMouse.containsMouse?root.tint:root.stroke
                            Rectangle{anchors.left:parent.left;anchors.bottom:parent.bottom;anchors.leftMargin:12;anchors.bottomMargin:5;width:(parent.width-24)*Model.clamp(Model.totalOf(procRow.modelData)/(root.mem.total||1),0,1);height:2;radius:1;color:root.tint}
                            Label{x:12;y:22;text:String(root.page*Model.PAGE_SIZE+procRow.index+1).padStart(2,'0');font.pixelSize:12;color:root.tint}
                            Column{x:44;y:10;spacing:5;width:parent.width-222
                                Heading{text:procRow.modelData.name+'  ·  '+(procRow.modelData.count>1?procRow.modelData.count+' processes':procRow.modelData.pid);font.pixelSize:13;width:parent.width;elide:Text.ElideRight}
                                Label{text:Model.targetLabel(procRow.modelData);width:parent.width;elide:Text.ElideRight;font.pixelSize:10}
                            }
                            Column{anchors.right:parent.right;anchors.rightMargin:35;y:10;spacing:5
                                Heading{text:Model.size(Model.totalOf(procRow.modelData));font.pixelSize:15;anchors.right:parent.right}
                                Label{text:Model.kindOf(procRow.modelData)+'  ·  swap '+Model.size(procRow.modelData.swap);font.pixelSize:10;anchors.right:parent.right}
                            }
                            Label{anchors.right:parent.right;anchors.rightMargin:13;y:22;text:procRow.modelData.target.address?'↗':'ⓘ';color:root.tint;font.pixelSize:16}
                            MouseArea{id:hoarderMouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor
                                onClicked: {if(procRow.modelData.target.address)root.runAction('focus',procRow.modelData);else root.actionStatus=procRow.modelData.name+' · '+(procRow.modelData.count>1?procRow.modelData.count+' processes':'PID '+procRow.modelData.pid)+' · proportional RAM '+(procRow.modelData.pss===null||procRow.modelData.pss===undefined?'unavailable, a member could not be read':Model.size(procRow.modelData.pss))+'. No existing window to focus.'}
                            }
                        }
                    }
                    Row{spacing:10
                        Action{text:'← Previous';opacity:root.page>0?1:0.4;onClicked:root.page=Math.max(0,root.page-1)}
                        Label{text:(root.page+1)+' / '+Model.pageCount(root.listing.length,Model.PAGE_SIZE);anchors.verticalCenter:parent.verticalCenter}
                        Action{text:'Next →';opacity:(root.page+1)*Model.PAGE_SIZE<root.listing.length?1:0.4;onClicked:root.page=Model.clampPage(root.page+1,root.listing.length,Model.PAGE_SIZE)}
                    }
                    Label{width:parent.width;wrapMode:Text.WordWrap;text:root.grouped?'A group total is proportional RAM: every shared page is divided between the processes mapping it, so these totals may be added together. A group whose members cannot all be read shows its largest resident process instead, marked resident. Windows group with the processes behind them; a service groups with its own helpers.':'RSS includes shared pages, so process totals must not be added together. Swap is per-process anonymous swap; shared swap may be omitted. Browser subprocesses lead to their browser window.';font.pixelSize:10}
                }
                Column {
                    width:parent.width;spacing:12;visible:root.tab===2;height:visible?implicitHeight:0
                    Heading{text:'UNDER THE HOOD';font.pixelSize:13}
                    Grid{width:parent.width;columns:3;spacing:10
                        Repeater{model:[
                            {l:'TRULY FREE',v:Model.size(root.mem.free),h:'Completely unused physical pages'},
                            {l:'DIRTY PAGES',v:Model.size(root.mem.dirty),h:'Changed data waiting for disk'},
                            {l:'WRITEBACK',v:Model.size(root.mem.writeback),h:'Data currently being written'},
                            {l:'ANONYMOUS',v:Model.size((root.mem.details||{}).AnonPages),h:'Heaps, stacks and private pages'},
                            {l:'SHARED / TMPFS',v:Model.size((root.mem.details||{}).Shmem),h:'Shared-memory objects and tmpfs'},
                            {l:'KERNEL SLAB',v:Model.size((root.mem.details||{}).Slab),h:'Includes reclaimable kernel caches'},
                            {l:'PAGE TABLES',v:Model.size((root.mem.details||{}).PageTables),h:'Virtual-memory mapping overhead'},
                            {l:'LOCKED / UNEVICTABLE',v:Model.size((root.mem.details||{}).Unevictable),h:'Pages the kernel cannot reclaim'},
                            {l:'ALL TASKS STALLED',v:Model.pct(root.mem.psi&&root.mem.psi.full?root.mem.psi.full.avg10:0),h:'Full memory pressure · last 10s'},
                            {l:'MAJOR PAGE FAULTS',v:((root.mem.rates||{}).pgmajfault||0).toFixed(1)+'/s',h:'Page faults requiring storage I/O'},
                            {l:'ZRAM PHYSICAL COST',v:Model.size((root.mem.zram||{}).physical),h:'Already part of used physical RAM'},
                            {l:'COMMITTED VIRTUAL',v:Model.size((root.mem.details||{}).Committed_AS),h:'Promised address space, not RSS'}
                        ]
                            Stat{required property var modelData;width:(mainColumn.width-20)/3;height:91;label:modelData.l;value:modelData.v;hint:modelData.h}
                        }
                    }
                    Column{width:parent.width;spacing:7
                        Repeater{model:root.mem.swaps||[]
                            Label{required property var modelData;width:parent.width;text:modelData.name+'  ·  '+Model.size(modelData.used)+' / '+Model.size(modelData.total)+'  ·  priority '+modelData.priority;color:root.themeAccent;font.pixelSize:11}
                        }
                    }
                    Rectangle{width:parent.width;height:152;radius:12;color:Qt.tint(root.themeBg,Qt.alpha(root.rampGood,0.08));border.color:Qt.alpha(root.rampGood,0.42)
                        Column{anchors.fill:parent;anchors.margins:14;spacing:9
                            Heading{text:'LET LINUX RECLAIM CACHE';font.pixelSize:12}
                            Label{width:parent.width;wrapMode:Text.WordWrap;text:'Available RAM already includes memory Linux can reuse. Dirty pages contain pending writes. Flushing writes safely saves that data; it does not guarantee more available RAM. Repeated flushing can briefly increase disk activity.';font.pixelSize:11;color:root.themeSoft}
                            Action{text:actionProc.running?'Working…':'Flush pending writes';accent:root.rampGood;onClicked:root.runAction('flush')}
                        }
                    }
                    Label{width:parent.width;wrapMode:Text.WordWrap;text:'Readouts overlap and are not a pie chart. No process termination, cache purge, swap reset or privileged tuning is exposed.';font.pixelSize:10}
                }
                Column {
                    width:parent.width;spacing:12;visible:root.tab===root.lastTab;height:visible?implicitHeight:0
                    Rectangle {
                        width:parent.width;height:132;radius:16;border.color:Qt.alpha(root.tint,0.45)
                        gradient:Gradient {GradientStop{position:0;color:Qt.alpha(root.tint,0.13)}GradientStop{position:1;color:root.surface}}
                        // Still, not animated: an About tab should not be the
                        // most expensive thing the panel draws.
                        MemoryChip {x:14;y:6;body:root.themeBg;width:120;height:120;available:root.mem.availablePct || 0;tint:root.tint;animate:false}
                        Column {x:152;y:26;spacing:6
                            Label{text:'VERSION';font.pixelSize:11;font.letterSpacing:2}
                            Heading{text:root.pluginVersion || 'unavailable';font.pixelSize:34;font.letterSpacing:1}
                            Label{text:'RAM Pulse for Omarchy  ·  MIT  ·  Fred Nix';font.pixelSize:11}
                        }
                    }
                    Row {spacing:8
                        Action{text:'Source code on GitHub  →';onClicked:root.openUrl(root.repoUrl)}
                        Action{text:'nixfred.com  →';onClicked:root.openUrl(root.homeUrl)}
                    }
                    PanelSeparator{}
                    // Where this plugin's moving parts live. An About in a
                    // diagnostic tool is the natural place to answer "what is
                    // running and where does it keep things" without a manual.
                    Flow {
                        width:parent.width;spacing:10
                        Stat{width:(mainColumn.width-20)/3;height:91;label:'RECORDER';value:root.stale?'offline':'running';hint:'ram-pulse.service, user unit'}
                        Stat{width:(mainColumn.width-20)/3;height:91;label:'RETENTION';value:'7 days';hint:'aggregate metrics, this machine only'}
                        Stat{width:(mainColumn.width-20)/3;height:91;label:'SAMPLES HELD';value:String(root.chart.count||0);hint:'in the range on screen'}
                    }
                    Label{width:parent.width;wrapMode:Text.WordWrap;font.pixelSize:11;text:'State lives in '+root.stateDir+' and never leaves this machine. RAM Pulse reads unprivileged kernel counters only: it never terminates a process, purges cache, resets swap or writes a tunable.'}
                }
                PanelSeparator{}
                Label{width:parent.width;wrapMode:Text.WordWrap;font.pixelSize:10;color:root.stale?root.rampWarn:root.themeSoft;text:Model.recorderStatus(root.actionStatus,root.stale,root.mem.collectorErrors && Object.keys(root.mem.collectorErrors).length,Qt.formatTime(new Date(root.mem.ts*1000),'h:mm:ss AP'))}
            }
        }
    }
}
