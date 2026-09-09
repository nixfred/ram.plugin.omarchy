// The panel must not reintroduce a colour of its own. Every surface it paints
// comes from the active Omarchy theme, and the headroom ramp comes from that
// theme's own red / yellow / green.
const fs=require('fs'),vm=require('vm'),{test}=require('node:test'),assert=require('assert/strict');
const ctx={Qt:{rgba:(r,g,b,a)=>[r,g,b,a]}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('Model.js','utf8').replace('.pragma library',''),ctx);

const panel=fs.readFileSync('Panel.qml','utf8');
const literal=/'#[0-9a-fA-F]{3,8}'/g;

test('the panel paints no colour of its own',()=>{
  // A single hex here is a surface that will stay wrong in all 23 themes.
  assert.deepEqual(panel.match(literal)??[],[]);
});

test('the panel takes its chrome from the theme roles',()=>{
  for(const role of ['Color.popups.text','Color.popups.background','Color.accent','Color.muted','Color.urgent'])
    assert.ok(panel.includes(role),'panel no longer reads '+role);
});

test('a theme switch re-reads the palette the shell does not watch',()=>{
  // The shell loads colors.toml once and is pushed later themes over IPC, so
  // the file watcher alone would leave the ramp on the previous theme.
  assert.match(panel,/themeSignature/);
  assert.match(panel,/onThemeSignatureChanged:\s*themePalette\.reload\(\)/);
});

test('the two canvases only hold colours as overridable defaults',()=>{
  for(const name of ['HistoryGraph.qml','MemoryChip.qml']){
    for(const line of fs.readFileSync(name,'utf8').split('\n')){
      if(!literal.test(line)) continue;
      literal.lastIndex=0;
      assert.match(line.trim(),/^property color /,name+' paints a fixed colour: '+line.trim());
    }
  }
});

test('the ramp reads the theme red, yellow and green',()=>{
  const parsed=ctx.themeRamp('mode = "dark"\nred = "#ff0000"\nyellow = "#00ff00"\ngreen = "#0000ff"\n');
  // Spread out of the script realm: an object built in there has a different
  // Object prototype and would fail a strict deep-equal on that alone.
  assert.deepEqual({...parsed},{low:'#ff0000',mid:'#00ff00',high:'#0000ff'});
  assert.deepEqual(ctx.ramp(0,parsed).slice(0,3).map(v=>Math.round(v*255)),[255,0,0]);
  assert.deepEqual(ctx.ramp(50,parsed).slice(0,3).map(v=>Math.round(v*255)),[0,255,0]);
  assert.deepEqual(ctx.ramp(100,parsed).slice(0,3).map(v=>Math.round(v*255)),[0,0,255]);
});

test('a key a theme omits keeps the shipped colour for that stop alone',()=>{
  // Not a whole foreign ramp: only the missing stop falls back.
  const parsed=ctx.themeRamp('red = "#ff0000"\ngreen = "not a colour"\n');
  assert.equal(parsed.low,'#ff0000');
  assert.equal(parsed.mid,ctx.RAMP_FALLBACK.mid);
  assert.equal(parsed.high,ctx.RAMP_FALLBACK.high);
  assert.deepEqual(ctx.themeRamp(''),ctx.RAMP_FALLBACK);
  assert.deepEqual(ctx.themeRamp(undefined),ctx.RAMP_FALLBACK);
});

test('the shipped ramp is still the ramp when no theme is readable',()=>{
  for(const [pct,rgb] of [[0,[133,13,41]],[50,[239,204,69]],[100,[67,242,161]]])
    assert.deepEqual(ctx.ramp(pct).slice(0,3).map(v=>Math.round(v*255)),rgb);
});

test('every installed theme that defines the three keys parses to three colours',()=>{
  // Guards the parser against the real files rather than a synthetic one.
  const dir=process.env.HOME+'/.config/omarchy/themes';
  if(!fs.existsSync(dir)) return;
  let checked=0;
  for(const name of fs.readdirSync(dir)){
    const file=dir+'/'+name+'/colors.toml';
    if(!fs.existsSync(file)) continue;
    const parsed=ctx.themeRamp(fs.readFileSync(file,'utf8'));
    for(const stop of ['low','mid','high']) assert.match(parsed[stop],/^#[0-9a-fA-F]{6}$/,name+' '+stop);
    checked++;
  }
  assert.ok(checked>0,'no installed theme was checked');
});
