(() => {
  'use strict';
  const form = document.querySelector('[data-poster-editor]');
  if (form) {
    const intensity = form.elements.animation_intensity;
    intensity.addEventListener('input', () => {form.querySelector('[data-intensity-output]').textContent = intensity.value + ' %';});
    const type = form.elements.link_type, target = form.elements.link_target;
    const product = form.querySelector('[data-product-picker]'), section = form.querySelector('[data-section-picker]');
    function linkFields(changed = false) {
      form.querySelector('[data-product-choice]').hidden = type.value !== 'product';
      form.querySelector('[data-section-choice]').hidden = type.value !== 'section';
      form.querySelector('[data-target-field]').hidden = ['none','catalog','product','section'].includes(type.value);
      if (type.value === 'product') target.value = product.value;
      if (type.value === 'section') target.value = section.value;
      if (changed && ['none','catalog'].includes(type.value)) target.value = '';
      form.elements.open_in_new_tab.disabled = type.value !== 'external_url';
    }
    type.addEventListener('change', () => linkFields(true));
    product.addEventListener('change', () => {target.value = product.value;});
    section.addEventListener('change', () => {target.value = section.value;});
    linkFields();
    document.querySelectorAll('[data-preview-size]').forEach(button => button.addEventListener('click', () => {
      document.querySelector('.preview-frame').className = 'preview-frame preview-' + button.dataset.previewSize;
      document.querySelectorAll('[data-preview-size]').forEach(b => b.setAttribute('aria-pressed',String(b === button)));
    }));
    let dirty = false;
    form.addEventListener('input', () => {dirty = true;});
    form.addEventListener('submit', event => {if (!event.submitter?.hasAttribute('data-preview')) dirty = false;});
    window.addEventListener('beforeunload', event => {if (dirty) {event.preventDefault(); event.returnValue = '';}});
  }
  const composition = document.querySelector('[data-composition]');
  if (composition) {
    const rows = composition.querySelector('[data-blocks]');
    composition.addEventListener('click', event => {
      if (event.target.closest('[data-add-block]')) {
        if (rows.children.length >= 40) return;
        rows.append(document.querySelector('#new-block').content.cloneNode(true));
        rows.lastElementChild.querySelector('select').focus();
      }
      const row = event.target.closest('[data-block-row]');
      if (!row) return;
      if (event.target.closest('[data-block-up]') && row.previousElementSibling) {rows.insertBefore(row,row.previousElementSibling);event.target.focus();}
      if (event.target.closest('[data-block-down]') && row.nextElementSibling) {rows.insertBefore(row.nextElementSibling,row);event.target.focus();}
      if (event.target.closest('[data-block-remove]')) {row.remove();}
      composition.querySelector('[data-block-status]').textContent = 'Orden actualizado. Guardá la composición para publicarlo.';
    });
  }
})();
