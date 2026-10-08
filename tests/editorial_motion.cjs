const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('public/editorial.js','utf8');
function run(kind='float', intensity='35', reduced=false) {
  const calls=[], listeners={}, animations=[];
  const preference={matches:reduced,addEventListener:(name,fn)=>listeners.motion=fn};
  const element={dataset:{animation:kind,intensity,delay:'100'},style:{},parentElement:{getBoundingClientRect:()=>({top:500,height:200})},animate:(frames,options)=>{
    calls.push({frames,options});
    const result={played:0,paused:0,canceled:0,play(){this.played++},pause(){this.paused++},cancel(){this.canceled++}};
    animations.push(result);return result;
  }};
  const document={hidden:false,querySelectorAll:()=>[element],addEventListener:(name,fn)=>listeners[name]=fn};
  let callback;
  class IntersectionObserver {constructor(fn){callback=fn}observe(){}disconnect(){}}
  const context={document,matchMedia:()=>preference,IntersectionObserver,innerHeight:800,requestAnimationFrame:fn=>{listeners.frame=fn;return 1;},addEventListener:(name,fn)=>listeners[name]=fn};
  context.window=context;
  vm.runInNewContext(code,context);
  return {calls,element,animations,preference,listeners,document,enter:()=>callback?.([{target:element,isIntersecting:true}]),exit:()=>callback?.([{target:element,isIntersecting:false}])};
}
const float=run();float.enter();
assert.equal(float.calls.length,1);
assert.equal(float.calls[0].frames[1].transform,'translateY(-6.3px)');
assert.equal(float.calls[0].options.duration*2,6020);
float.exit();assert.equal(float.animations[0].paused,1);
float.enter();assert.equal(float.calls.length,1);assert.equal(float.animations[0].played,1);
float.preference.matches=true;float.listeners.motion();assert.equal(float.animations[0].canceled,1);
assert.equal(float.element.style.transform,'');
const reduced=run('float','35',true);reduced.enter();assert.equal(reduced.calls.length,0);
for (const kind of ['tilt','fade','scroll-reveal']) {const effect=run(kind);effect.enter();assert.equal(effect.calls.length,1);}
for (const kind of ['none','unknown']) {const effect=run(kind);effect.enter();assert.equal(effect.calls.length,0);}
const zero=run('float','0');zero.enter();assert.equal(zero.calls.length,0);
const parallax=run('parallax','100');parallax.enter();parallax.listeners.frame();
assert.equal(parallax.element.style.transform,'translateY(-8px)');
const hidden=run();hidden.enter();hidden.document.hidden=true;hidden.listeners.visibilitychange();assert.equal(hidden.animations[0].paused,1);
console.log('Editorial animation checks passed: effects, float range, zero, reduced motion, offscreen/hidden pause, shared scroll.');
