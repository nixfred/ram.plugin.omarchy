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
console.log('Readout formats, missing telemetry, units, and red/yellow/green endpoints pass.');
