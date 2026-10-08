(() => {
  'use strict';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if ('IntersectionObserver' in window && !reduced) {
    document.body.classList.add('motion-ready');
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) { entry.target.classList.remove('pending'); observer.unobserve(entry.target); }
    }), {threshold: .08});
    document.querySelectorAll('.reveal').forEach(el => { el.classList.add('pending'); observer.observe(el); });
  }
  document.querySelectorAll('[data-experience]').forEach(root => {
    const tabs = [...root.querySelectorAll('[data-tab]')];
    const panels = [...root.querySelectorAll('[role="tabpanel"]')];
    let current = 0, timer;
    const select = (index, focus = false) => {
      clearTimeout(timer);
      current = (index + tabs.length) % tabs.length;
      tabs.forEach((tab, i) => { tab.setAttribute('aria-selected', i === current); tab.tabIndex = i === current ? 0 : -1; });
      panels.forEach((panel, i) => {
        panel.hidden = i !== current; panel.classList.remove('is-exploded', 'show-cut');
        panel.querySelectorAll('[aria-pressed]').forEach(button => button.setAttribute('aria-pressed', 'false'));
        const explode = panel.querySelector('[data-explode]');
        if (explode) explode.firstChild.textContent = 'Descubrí sus capas ';
        panel.querySelectorAll('.visual-layer').forEach(layer => { layer.style.transform = ''; });
      });
      root.querySelector('[data-position]').textContent = `${current + 1} / ${tabs.length}`;
      if (focus) tabs[current].focus();
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => select(index));
      tab.addEventListener('keydown', event => {
        if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
          event.preventDefault();
          select(event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : current + (event.key === 'ArrowRight' ? 1 : -1), true);
        }
      });
    });
    root.querySelector('[data-prev]').addEventListener('click', () => select(current - 1));
    root.querySelector('[data-next]').addEventListener('click', () => select(current + 1));
    let start;
    const surface = root.querySelector('[data-swipe]');
    surface.addEventListener('touchstart', event => { start = {x:event.touches[0].clientX,y:event.touches[0].clientY}; }, {passive:true});
    surface.addEventListener('touchend', event => {
      if (!start) return;
      const dx = event.changedTouches[0].clientX - start.x, dy = event.changedTouches[0].clientY - start.y;
      if (Math.abs(dx) > 65 && Math.abs(dx) > Math.abs(dy) * 1.4) select(current + (dx < 0 ? 1 : -1));
      start = null;
    }, {passive:true});
    panels.forEach(panel => {
      const layers = [...panel.querySelectorAll('.visual-layer')];
      panel.querySelector('[data-explode]')?.addEventListener('click', event => {
        clearTimeout(timer);
        const expanded = panel.classList.toggle('is-exploded');
        panel.classList.remove('show-cut');
        panel.querySelector('[data-cut]')?.setAttribute('aria-pressed', 'false');
        event.currentTarget.setAttribute('aria-pressed', expanded);
        event.currentTarget.firstChild.textContent = expanded ? 'Volvé a armarla ' : 'Descubrí sus capas ';
        layers.forEach((layer, i) => {
          const offset = expanded ? ((layers.length - 1) / 2 - i) * Math.min(70, 280 / Math.max(1, layers.length - 1)) : 0;
          layer.style.transform = `translateY(${offset}px)`;
          layer.style.zIndex = String(i + 1);
        });
        if (!expanded) timer = setTimeout(() => {
          panel.classList.add('show-cut'); panel.querySelector('[data-cut]')?.setAttribute('aria-pressed', 'true');
        }, reduced ? 0 : 850);
      });
      panel.querySelector('[data-cut]')?.addEventListener('click', event => {
        clearTimeout(timer); panel.classList.remove('is-exploded');
        const shown = panel.classList.toggle('show-cut');
        event.currentTarget.setAttribute('aria-pressed', shown);
        panel.querySelector('[data-explode]')?.setAttribute('aria-pressed', 'false');
        const explode = panel.querySelector('[data-explode]');
        if (explode) explode.firstChild.textContent = 'Descubrí sus capas ';
        layers.forEach(layer => { layer.style.transform = ''; });
      });
    });
  });
  document.querySelectorAll('[data-order]').forEach(form => {
    form.addEventListener('change', event => {
      if (event.target.name !== 'size') return;
      form.querySelector('[data-price-output]').textContent = event.target.dataset.price;
      const image = document.querySelector('.product-main-photo img');
      if (image && event.target.dataset.image) { image.removeAttribute('srcset'); image.src = event.target.dataset.image; }
    });
  });
  document.querySelectorAll('[data-back]').forEach(button => button.addEventListener('click', () => history.back()));
})();
