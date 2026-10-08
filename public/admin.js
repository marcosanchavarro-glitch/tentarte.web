(() => {
  const editor = document.querySelector('[data-editor]');
  if (!editor) return;
  let dirty = false;
  editor.addEventListener('input', () => { dirty = true; });
  editor.addEventListener('click', event => {
    const add = event.target.closest('[data-add]');
    if (add) {
      const section = editor.querySelector(`[data-repeat="${add.dataset.add}"]`);
      if (section.children.length >= 40) return;
      section.append(document.querySelector(`#row-${add.dataset.add}`).content.cloneNode(true));
      section.lastElementChild.querySelector('input:not([type=hidden])')?.focus(); dirty = true;
    }
    const row = event.target.closest('[data-row]');
    if (!row) return;
    if (event.target.closest('[data-remove]')) { row.remove(); dirty = true; }
    if (event.target.closest('[data-up]') && row.previousElementSibling) { row.parentNode.insertBefore(row, row.previousElementSibling); dirty = true; }
    if (event.target.closest('[data-down]') && row.nextElementSibling) { row.parentNode.insertBefore(row.nextElementSibling, row); dirty = true; }
  });
  editor.addEventListener('submit', () => { dirty = false; });
  window.addEventListener('beforeunload', event => { if (dirty) {event.preventDefault(); event.returnValue = '';} });
})();
