// The panel must not reintroduce a colour of its own. Every surface it paints
// comes from the active Omarchy theme, and the headroom ramp comes from that
// theme's own red / yellow / green.
const fs=require('fs'),vm=require('vm'),{test}=require('node:test'),assert=require('assert/strict');
const ctx={Qt:{rgba:(r,g,b,a)=>[r,g,b,a]}};

// Themes ship in two places: the user's own and the ones Omarchy installs.
// Checking only the first misses more than half of them, including the theme
// that was active when the muted-ramp problem was found.
function installedThemes(){
  const out=[];
  for(const dir of [process.env.HOME+'/.config/omarchy/themes','/usr/share/omarchy/themes']){
    if(!fs.existsSync(dir)) continue;
    for(const name of fs.readdirSync(dir)){
      const file=dir+'/'+name+'/colors.toml';
      if(fs.existsSync(file)) out.push([name,fs.readFileSync(file,'utf8')]);
    }
  }
  return out;
}
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

// The floor is 0.55, but a stop is rounded to 8 bits per channel on its way
// back to a hex string, which can land a hair under. Assert against the floor
// less one quantisation step rather than loosening the floor itself.
const READABLE=0.54;

// Saturation of an "#rrggbb", 0..1, for asserting a ramp can still be read.
function saturation(hex){
  const [r,g,b]=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
  const mx=Math.max(r,g,b),mn=Math.min(r,g,b),l=(mx+mn)/2;
  if(mx===mn) return 0;
  return l>0.5?(mx-mn)/(2-mx-mn):(mx-mn)/(mx+mn);
}

test('a muted theme is lifted to a ramp that can still warn',()=>{
  // 2-haxorz sits at 0.23 / 0.13 / 0.11 saturation: dusty rose, olive and grey
  // teal. Read verbatim it produced a chip that could no longer warn at all.
  const r=ctx.themeRamp('red = "#b9968f"\nyellow = "#7b8768"\ngreen = "#708c8b"');
  assert.deepEqual({...r},{low:'#d68372',mid:'#86b936',high:'#39c383'});
  for(const stop of [r.low,r.mid,r.high]) assert.ok(saturation(stop)>=READABLE,stop);
});

test('a ramp that is already vivid is left alone',()=>{
  // Only what must move, moves: ethereal's red and yellow are untouched and
  // just its sage green lifts.
  const r=ctx.themeRamp('red = "#ED5B5A"\nyellow = "#E9BB4F"\ngreen = "#92a593"');
  assert.equal(r.low,'#ed5b5a');
  assert.equal(r.mid,'#e9bb4f');
  assert.notEqual(r.high,'#92a593');
});

test('a greyscale theme borrows the shipped hues rather than tinting at random',()=>{
  // vantablack and white define all three stops as pure grey, so there is no
  // hue to preserve.
  const r=ctx.themeRamp('red = "#8a8a8a"\nyellow = "#a0a0a0"\ngreen = "#b4b4b4"');
  assert.deepEqual({...r},{low:'#ca4a68',mid:'#d4bf6c',high:'#79d8ac'});
});

test('the shipped ramp is never put through the floor',()=>{
  // #850d29 is a deliberate dark crimson; the floor would lighten it.
  assert.deepEqual({...ctx.themeRamp('')},{...ctx.RAMP_FALLBACK});
});

test('no installed theme yields a ramp that cannot warn',()=>{
  const themes=installedThemes();
  for(const [name,raw] of themes){
    const r=ctx.themeRamp(raw);
    for(const [stop,hex] of Object.entries(r))
      assert.ok(saturation(hex)>=READABLE,name+' '+stop+' is '+hex+' at saturation '+saturation(hex).toFixed(2));
  }
  assert.ok(themes.length>0,'no installed theme was checked');
});

test('every installed theme parses to three colours',()=>{
  // Guards the parser against the real files rather than a synthetic one.
  const themes=installedThemes();
  for(const [name,raw] of themes){
    const parsed=ctx.themeRamp(raw);
    for(const stop of ['low','mid','high']) assert.match(parsed[stop],/^#[0-9a-fA-F]{6}$/,name+' '+stop);
  }
  assert.ok(themes.length>0,'no installed theme was checked');
});
