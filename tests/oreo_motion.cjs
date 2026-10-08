const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function run(cut=true,reduced=false,layers=false){
 const listeners={},classes=new Set(),style={},status={},buttons=(layers?['whole','interior','layers']:['whole','interior']).map(view=>({dataset:{oreoView:view},attrs:{},disabled:!cut&&view==='interior',setAttribute(k,v){this.attrs[k]=v},addEventListener(k,fn){this[k]=fn}}));
 const photos=(layers?['whole','interior','layers']:cut?['whole','interior']:['whole']).map(view=>({dataset:{oreoPhoto:view},attrs:{},setAttribute(k,v){this.attrs[k]=v},querySelectorAll:()=>[{addEventListener(){}}]}));
 let top=700,callback,frame;
 const root={querySelectorAll:s=>s==='[data-oreo-view]'?buttons:photos,querySelector:()=>status,classList:{add:c=>classes.add(c),remove:c=>classes.delete(c)},style:{setProperty:(k,v)=>style[k]=v},getBoundingClientRect:()=>({top})};
 const motion={matches:reduced,addEventListener:(k,fn)=>listeners.motion=fn};
 const doc={hidden:false,querySelectorAll:()=>[root],addEventListener:(k,fn)=>listeners[k]=fn};
 class Observer{constructor(fn){callback=fn}observe(){}disconnect(){}}
 const ctx={document:doc,matchMedia:()=>motion,IntersectionObserver:Observer,innerHeight:800,requestAnimationFrame:fn=>{frame=fn;return 1},cancelAnimationFrame:()=>{frame=null},addEventListener:(k,fn)=>listeners[k]=fn,removeEventListener:k=>delete listeners[k]};ctx.window=ctx;
 vm.runInNewContext(fs.readFileSync('public/oreo-experience.js','utf8'),ctx);
 return {buttons,photos,classes,status,style,motion,listeners,enter(){callback([{isIntersecting:true}]);frame?.()},scroll(y){top=y;listeners.scroll?.();frame?.()}};
}
const normal=run();assert.equal(normal.buttons[0].attrs['aria-pressed'],'true');normal.buttons[1].click();assert.equal(normal.photos[0].attrs['aria-hidden'],'true');normal.buttons[0].click();assert.equal(normal.photos[0].attrs['aria-hidden'],'false');normal.enter();const start=+normal.style['--oreo-progress'];normal.scroll(300);assert.equal(+normal.style['--oreo-progress'],1);normal.scroll(700);assert.equal(+normal.style['--oreo-progress'],start);normal.motion.matches=true;normal.listeners.motion();assert.ok(!normal.classes.has('oreo-scroll'));assert.ok(!normal.listeners.scroll);const reduced=run(true,true);assert.ok(!reduced.classes.has('oreo-scroll'));reduced.buttons[1].click();assert.equal(reduced.photos[1].attrs['aria-hidden'],'false');const missing=run(false);missing.buttons[1].click();assert.equal(missing.buttons[0].attrs['aria-pressed'],'true');console.log('Oreo: reversible views, reversible scroll, reduced motion and missing-cut fallback passed.');

const layered=run(true,false,true);layered.buttons[2].click();assert.equal(layered.photos[2].attrs['aria-hidden'],'false');layered.buttons[0].click();assert.equal(layered.photos[2].attrs['aria-hidden'],'true');assert.equal(layered.buttons[0].attrs['aria-pressed'],'true');console.log('Independent-layer view reverses to whole view.');
