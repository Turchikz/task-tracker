(() => {
  'use strict';
  const openButton = document.querySelector('[data-notice-open]');
  const panel = document.querySelector('#notification-drawer');
  const closeButton = document.querySelector('[data-notice-close]');
  const backdrop = document.querySelector('[data-notice-backdrop]');
  if (!openButton || !panel || !closeButton || !backdrop) return;
  let previousFocus = null;
  function setOpen(open) {
    if (open) previousFocus = document.activeElement;
    panel.hidden = !open;
    backdrop.hidden = !open;
    panel.setAttribute('aria-hidden', String(!open));
    openButton.setAttribute('aria-expanded', String(open));
    document.body.classList.toggle('notice-drawer-open', open);
    if (open) closeButton.focus();
    else if (previousFocus && document.contains(previousFocus)) previousFocus.focus();
  }
  openButton.addEventListener('click', () => setOpen(panel.hidden));
  closeButton.addEventListener('click', () => setOpen(false));
  backdrop.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', (event) => {
    if (panel.hidden) return;
    if (event.key === 'Escape') { event.preventDefault(); setOpen(false); }
    if (event.key === 'Tab') {
      const controls = [...panel.querySelectorAll('a,button,input,select,textarea,[tabindex]')]
        .filter(el => !el.disabled && el.getAttribute('tabindex') !== '-1');
      if (!controls.length) return;
      const first = controls[0], last = controls[controls.length-1];
      if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last.focus();}
      else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
    }
  });
})();