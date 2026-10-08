/* One registry, one visibility observer and one scroll frame for all posters. */
(() => {
  'use strict';
  const elements = [...document.querySelectorAll('[data-poster]')];
  if (!elements.length) return;
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  const effects = {
    float: (el,n,delay) => el.animate([{transform:'translateY(0)'},{transform:`translateY(${-18*n}px)`}], {duration:3500-1400*n,direction:'alternate',iterations:Infinity,easing:'ease-in-out',delay}),
    tilt: (el,n,delay) => el.animate([{transform:`rotate(${-3*n}deg)`},{transform:`rotate(${3*n}deg)`}], {duration:4000,direction:'alternate',iterations:Infinity,easing:'ease-in-out',delay}),
    fade: (el,n,delay) => el.animate([{opacity:1-n},{opacity:1}], {duration:500+500*n,fill:'both',easing:'ease-out',delay}),
    'scroll-reveal': (el,n,delay) => el.animate([{opacity:0,transform:`translateY(${32*n}px)`},{opacity:1,transform:'translateY(0)'}], {duration:500+500*n,fill:'both',easing:'ease-out',delay})
  };
  const active = new Set(), animations = new Map(), entered = new Set();
  let observer, frame=0;
  const intensity = el => Math.max(0,Math.min(100,Number(el.dataset.intensity)||0))/100;
  const isParallax = el => el.dataset.animation === 'parallax';
  function scrollFrame() {
    frame=0;
    if (preference.matches || document.hidden) return;
    active.forEach(el => {
      if (!isParallax(el)) return;
      const rect=el.parentElement.getBoundingClientRect();
      const ratio=Math.max(-1,Math.min(1,((rect.top+rect.height/2)-innerHeight/2)/innerHeight));
      el.style.transform=`translateY(${-ratio*32*intensity(el)}px)`;
    });
  }
  function requestFrame() {if (!frame && !preference.matches) frame=requestAnimationFrame(scrollFrame);}
  function show(el) {
    active.add(el);
    const old=animations.get(el);
    if (old) {if (!document.hidden) old.play();return;}
    const n=intensity(el), kind=el.dataset.animation;
    if (!n || preference.matches || kind==='none') return;
    if (isParallax(el)) {requestFrame();return;}
    if (entered.has(el)) return;
    const effect=effects[kind];
    if (!effect || typeof el.animate !== 'function') return;
    entered.add(el);
    const animation=effect(el,n,Math.max(0,Math.min(3000,Number(el.dataset.delay)||0)));
    animations.set(el,animation);
    if (document.hidden) animation.pause();
  }
  function setup() {
    observer?.disconnect();
    animations.forEach(animation=>animation.cancel());animations.clear();active.clear();entered.clear();
    elements.forEach(el=>{el.style.transform='';el.style.opacity='';});
    if (preference.matches) return;
    if (!('IntersectionObserver' in window)) return; // Static and readable fallback.
    observer=new IntersectionObserver(entries=>entries.forEach(entry=>{
      if (entry.isIntersecting) show(entry.target);
      else {active.delete(entry.target);animations.get(entry.target)?.pause();}
    }),{threshold:0.02});
    elements.forEach(el=>observer.observe(el));
  }
  addEventListener('scroll',requestFrame,{passive:true});
  addEventListener('resize',requestFrame,{passive:true});
  document.addEventListener('visibilitychange',()=>{
    animations.forEach((animation,el)=>{if(document.hidden||!active.has(el))animation.pause();else animation.play();});
    requestFrame();
  });
  preference.addEventListener('change',setup);
  setup();
})();
