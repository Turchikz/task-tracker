/* RaTracker v0.8.2: compact, draggable light-bulb theme control.
   Intentionally no GSAP/Draggable/MorphSVG CDN dependency. */
(() => {
  'use strict';
  const button = document.querySelector('[data-theme-toggle]');
  if (!button) return;

  const storageKey = 'task-tracker-theme';
  const bulb = button.querySelector('.theme-bulb-pull');
  const threshold = 13;
  const maxPull = 23;
  let startY = 0;
  let currentPull = 0;
  let activePointer = null;
  let suppressNextClick = false;
  let animationTimer = null;

  function currentTheme() {
    return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
  }

  function syncButton() {
    const isDark = currentTheme() === 'dark';
    button.setAttribute('aria-pressed', String(isDark));
    button.setAttribute('aria-label', isDark ? 'Включить светлую тему' : 'Включить тёмную тему');
    button.title = isDark
      ? 'Потяните шнур или нажмите, чтобы включить светлую тему'
      : 'Потяните шнур или нажмите, чтобы включить тёмную тему';
  }

  function changeTheme() {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(storageKey, next); } catch (_) { /* Private mode */ }
    syncButton();
    document.dispatchEvent(new CustomEvent('ratracker:theme-changed', { detail: { theme: next } }));

    button.classList.remove('is-pulling');
    // Restart the recoil animation for consecutive interactions.
    void button.offsetWidth;
    button.classList.add('is-pulling');
    window.clearTimeout(animationTimer);
    animationTimer = window.setTimeout(() => button.classList.remove('is-pulling'), 420);
  }

  function resetCord() {
    activePointer = null;
    currentPull = 0;
    button.classList.remove('is-dragging');
    if (bulb) bulb.style.setProperty('--cord-pull', '0px');
  }

  button.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    activePointer = event.pointerId;
    startY = event.clientY;
    currentPull = 0;
    button.classList.add('is-dragging');
    try { button.setPointerCapture(event.pointerId); } catch (_) { /* Browser fallback */ }
  });

  button.addEventListener('pointermove', (event) => {
    if (activePointer !== event.pointerId) return;
    currentPull = Math.max(0, Math.min(maxPull, event.clientY - startY));
    if (bulb) bulb.style.setProperty('--cord-pull', `${currentPull}px`);
  });

  button.addEventListener('pointerup', (event) => {
    if (activePointer !== event.pointerId) return;
    const wasPulled = currentPull >= threshold;
    resetCord();
    if (!wasPulled) return; // Normal click handler supports mouse, touch and keyboard.

    // Pointerup can emit a synthesized click; suppress that one to avoid toggling twice.
    suppressNextClick = true;
    changeTheme();
    window.setTimeout(() => { suppressNextClick = false; }, 0);
  });

  button.addEventListener('pointercancel', resetCord);
  button.addEventListener('lostpointercapture', () => {
    if (activePointer !== null) resetCord();
  });
  button.addEventListener('click', () => {
    if (suppressNextClick) {
      suppressNextClick = false;
      return;
    }
    changeTheme();
  });

  syncButton();
})();
