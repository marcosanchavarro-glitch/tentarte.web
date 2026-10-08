(() => {
  'use strict';
  // Each layer is a distinct, inspected RGBA resource; never a clone of the whole photo.
  const layerSlots = Object.freeze(['chocolate-base', 'chocolate-filling', 'oreo-cream', 'decoration']);
  class OreoExperience {
    static layerSlots = layerSlots;
    constructor(root) {
      this.root = root;
      this.buttons = [...root.querySelectorAll('[data-oreo-view]')];
      this.photos = [...root.querySelectorAll('[data-oreo-photo]')];
      this.motion = matchMedia('(prefers-reduced-motion: reduce)');
      this.frame = 0;
      this.active = false;
      const wholeStatus = root.querySelector('[data-oreo-status]').textContent || 'Tarta completa';
      this.select = view => {
        if (!this.photos.some(photo => photo.dataset.oreoPhoto === view)) return;
        this.buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.oreoView === view)));
        this.photos.forEach(photo => photo.setAttribute('aria-hidden', String(photo.dataset.oreoPhoto !== view)));
        root.querySelector('[data-oreo-status]').textContent = view === 'whole' ? wholeStatus : view === 'layers' ? 'Cuatro capas ilustrativas. Volvé a Tarta completa para reconstruir la vista.' : root.dataset?.illustrative === 'true' ? 'Interior ilustrativo de Oreo' : 'Corte real de Oreo';
      };
      this.buttons.forEach(button => button.addEventListener('click', () => this.select(button.dataset.oreoView)));
      this.photos.forEach(photo => photo.querySelectorAll('img').forEach(image => image.addEventListener('error', () => {
        if (image.dataset.fallback) {
          const fallback = image.dataset.fallback;
          delete image.dataset.fallback;
          image.removeAttribute('srcset'); image.src = fallback; return;
        }
        const button = this.buttons.find(item => item.dataset.oreoView === photo.dataset.oreoPhoto);
        button.disabled = true;
        if (photo.dataset.oreoPhoto !== 'whole') this.select('whole');
        root.querySelector('[data-oreo-status]').textContent = 'No pudimos cargar esta fotografía. Podés volver a intentarlo recargando la página.';
      })));
      this.select('whole');
      root.classList.add('oreo-ready');
      this.update = () => {
        this.frame = 0;
        if (!this.active || this.motion.matches || document.hidden) return;
        const rect = root.getBoundingClientRect();
        const progress = Math.max(0, Math.min(1, (innerHeight - rect.top) / (innerHeight * .6)));
        root.style.setProperty('--oreo-progress', String(progress));
      };
      this.schedule = () => { if (!this.frame) this.frame = requestAnimationFrame(this.update); };
      this.configure = () => {
        this.observer?.disconnect();
        window.removeEventListener('scroll', this.schedule);
        window.removeEventListener('resize', this.schedule);
        cancelAnimationFrame(this.frame); this.frame = 0;
        root.classList.remove('oreo-scroll');
        if (this.motion.matches || !('IntersectionObserver' in window)) return;
        root.classList.add('oreo-scroll');
        this.observer = new IntersectionObserver(entries => {
          this.active = entries[0].isIntersecting;
          if (this.active) this.schedule();
        });
        this.observer.observe(root);
        window.addEventListener('scroll', this.schedule, {passive:true});
        window.addEventListener('resize', this.schedule, {passive:true});
      };
      this.motion.addEventListener('change', this.configure);
      document.addEventListener('visibilitychange', this.schedule);
      this.configure();
    }
  }
  document.querySelectorAll('[data-oreo-experience]').forEach(root => new OreoExperience(root));
})();
