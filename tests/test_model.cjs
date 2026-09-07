const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const ctx={Qt:{rgba:(r,g,b,a)=>[r,g,b,a]}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('Model.js','utf8').replace('.pragma library',''),ctx);
const m={total:16*2**30,available:2.5*2**30,used:13.5*2**30,availablePct:15.625,usedPct:84.375};
assert.equal(ctx.readout(m,0),'15.6%');assert.equal(ctx.readout(m,1),'84.4%');
assert.equal(ctx.readout(m,2),'13.5 GiB');assert.equal(ctx.readout(m,3),'2.5 GiB');
for(const [p,c] of [[0,[133,13,41]],[50,[239,204,69]],[100,[67,242,161]]]){
  const result=ctx.ramp(p);c.forEach((v,i)=>assert.equal(Math.round(result[i]*255),v));
}
assert.equal(ctx.readout({},0),'—');
assert.equal(ctx.size(1048576),'1.0 MiB');
for(const [xdg,expected] of [[undefined,'/home/test/.local/state/ram-pulse'],['','/home/test/.local/state/ram-pulse'],
    ['relative','/home/test/.local/state/ram-pulse'],['./relative','/home/test/.local/state/ram-pulse'],
    ['/state','/state/ram-pulse']]){
  assert.equal(ctx.stateDir('/home/test',xdg),expected);
}
const panel=fs.readFileSync('Panel.qml','utf8');
const expression=panel.match(/readonly property string stateDir:\s*([^\n]+)/)[1];
for(const [xdg,expected] of [['','/home/test/.local/state/ram-pulse'],['relative','/home/test/.local/state/ram-pulse'],
    ['/state','/state/ram-pulse']]){
  assert.equal(vm.runInNewContext(expression,{Model:ctx,Quickshell:{env:n=>n==='HOME'?'/home/test':xdg}}),expected);
}
console.log('Readout formats, missing telemetry, units, red/yellow/green endpoints, and state-directory agreement pass.');
