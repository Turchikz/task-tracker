/* RaTracker v0.8.0: progressively enhanced UI. Native HTML remains usable without JS. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));
  const safeGet = (key) => { try { return localStorage.getItem(key); } catch { return null; } };
  const safeSet = (key, value) => { try { localStorage.setItem(key, value); } catch {} };

  // Keep menus keyboard accessible and mutually exclusive.
  const menus = $$('[data-menu]');
  menus.forEach((menu) => {
    menu.addEventListener('toggle', () => {
      if (menu.open) menus.forEach((item) => { if (item !== menu) item.open = false; });
    });
  });
  document.addEventListener('click', (event) => {
    menus.forEach((menu) => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      menus.forEach((menu) => { menu.open = false; });
      document.activeElement?.blur?.();
    }
    const target = event.target;
    const inEditable = target?.matches?.('input, textarea, select, [contenteditable]');
    if (((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') ||
        (!inEditable && !event.altKey && !event.ctrlKey && !event.metaKey && event.key === '/')) {
      const search = $('[data-global-search]');
      if (search) {
        event.preventDefault();
        search.focus();
        search.select();
      }
    }
  });
  $('[data-theme-menu-toggle]')?.addEventListener('click', () => {
    $('[data-theme-toggle]')?.click();
    menus.forEach((m) => { m.open = false; });
  });

  // Bulk toolbar only after selecting editable tasks; disabled buttons cannot submit.
  const bulk = $('[data-bulk-form]');
  if (bulk) {
    const checks = $$('[data-task-select]');
    const selectAll = $('[data-select-all]');
    const count = $('[data-selected-count]', bulk);
    const submit = $('[data-bulk-submit]', bulk);
    const update = () => {
      const n = checks.filter((c) => c.checked).length;
      bulk.hidden = n === 0;
      if (count) count.textContent = `${n} выбрано`;
      if (submit) submit.disabled = n === 0;
      if (selectAll) {
        selectAll.checked = n > 0 && n === checks.length;
        selectAll.indeterminate = n > 0 && n < checks.length;
      }
    };
    const sync = () => {
      const action = $('[name="action"]', bulk)?.value;
      $$('[data-bulk-field]', bulk).forEach((control) => {
        control.hidden = control.dataset.bulkField !== action;
        control.querySelectorAll('input,select').forEach((input) => { input.disabled = control.hidden; });
      });
    };
    checks.forEach((c) => c.addEventListener('change', update));
    selectAll?.addEventListener('change', () => { checks.forEach((c) => { c.checked = selectAll.checked; }); update(); });
    $('[data-bulk-cancel]', bulk)?.addEventListener('click', () => {
      checks.forEach((c) => { c.checked = false; }); update();
    });
    $('[name="action"]', bulk)?.addEventListener('change', sync);
    bulk.addEventListener('submit', (event) => {
      if (!checks.some((c) => c.checked)) { event.preventDefault(); update(); }
    });
    sync(); update();
  }

  // Per-user browser column visibility (does not alter saved server filters).
  const colPanel = $('[data-columns-menu]');
  const table = $('[data-task-table]');
  if (colPanel && table) {
    const key = colPanel.dataset.columnStorageKey;
    const hiddenDefault = new Set((colPanel.dataset.defaultHidden || '').split(',').filter(Boolean));
    let hidden;
    try { const value = safeGet(key); hidden = value === null ? hiddenDefault : new Set(JSON.parse(value)); }
    catch { hidden = hiddenDefault; }
    const update = () => {
      $$('[data-column]', table).forEach((cell) => { cell.hidden = hidden.has(cell.dataset.column); });
      $$('[data-toggle-column]', colPanel).forEach((input) => { input.checked = !hidden.has(input.value); });
      safeSet(key, JSON.stringify([...hidden]));
    };
    $$('[data-toggle-column]', colPanel).forEach((input) => input.addEventListener('change', () => {
      if (input.checked) hidden.delete(input.value); else hidden.add(input.value);
      update();
    }));
    update();
  }

  // Make the main task action first in DOM tab order, not merely visually first.
  const actionBar = $('.task-action-priority');
  if (actionBar) {
    const primary = $('.btn.primary, .btn.success', actionBar);
    if (primary) {
      const item = primary.closest('form') || primary;
      actionBar.insertBefore(item, actionBar.firstElementChild);
    }
  }

  // Expand long histories only on demand.
  const history = $('.history-section');
  if (history && $$('.history-extra', history).length) {
    history.classList.add('is-collapsed');
    const button = $('[data-history-toggle]', history);
    if (button) {
      button.hidden = false;
      button.addEventListener('click', () => {
        const expanded = history.classList.toggle('history-expanded');
        history.classList.toggle('is-collapsed', !expanded);
        button.textContent = expanded ? 'Свернуть историю' : 'Показать всю историю';
        button.setAttribute('aria-expanded', String(expanded));
      });
      button.setAttribute('aria-expanded', 'false');
    }
  }

  // Calendar: agenda on mobile, month on desktop; user may override manually.
  const agenda = $('[data-calendar-agenda]');
  const calendar = $('.calendar-wrap-production');
  const switches = $$('[data-calendar-mode]');
  if (agenda && calendar && switches.length) {
    let selected = null;
    const apply = (mode) => {
      selected = mode === 'agenda' ? 'agenda' : 'month';
      agenda.hidden = selected !== 'agenda';
      calendar.classList.toggle('calendar-is-hidden', selected === 'agenda');
      switches.forEach((b) => {
        b.classList.toggle('is-selected', b.dataset.calendarMode === selected);
        b.setAttribute('aria-pressed', String(b.dataset.calendarMode === selected));
      });
    };
    apply(window.matchMedia('(max-width: 760px)').matches ? 'agenda' : 'month');
    switches.forEach((button) => button.addEventListener('click', () => apply(button.dataset.calendarMode)));
  }

  // Kanban: reducing empty column clutter is opt-in.
  const board = $('[data-kanban-board]');
  const emptyToggle = $('[data-hide-empty-kanban]');
  if (board && emptyToggle) {
    emptyToggle.addEventListener('change', () => board.classList.toggle('hide-empty-columns', emptyToggle.checked));
  }

  // Notifications unread/all; hide orphaned date dividers as well.
  const noticeButtons = $$('[data-notify-filter]');
  if (noticeButtons.length) {
    const filterNotices = (mode) => {
      $$('[data-notification]').forEach((notice) => {
        notice.hidden = mode === 'unread' && !notice.classList.contains('unread');
      });
      $$('.notification-date-heading').forEach((heading) => {
        let next = heading.nextElementSibling;
        let visible = false;
        while (next && !next.classList.contains('notification-date-heading')) {
          if (next.matches('[data-notification]') && !next.hidden) visible = true;
          next = next.nextElementSibling;
        }
        heading.hidden = !visible;
      });
      noticeButtons.forEach((button) => {
        const active = button.dataset.notifyFilter === mode;
        button.classList.toggle('is-selected', active);
        button.setAttribute('aria-pressed', String(active));
      });
    };
    noticeButtons.forEach((button) => button.addEventListener('click', () => filterNotices(button.dataset.notifyFilter)));
  }

  // Workload hover tooltip. Full title and metadata, without disturbing column sizing.
  const workload = $('.workload-page');
  if (workload) {
    const tooltip = document.createElement('div');
    tooltip.className = 'workload-tooltip';
    tooltip.hidden = true;
    tooltip.setAttribute('role', 'tooltip');
    document.body.appendChild(tooltip);
    const position = (event) => {
      if (tooltip.hidden) return;
      let x = event.clientX + 14, y = event.clientY + 14;
      const rect = tooltip.getBoundingClientRect();
      if (x + rect.width > window.innerWidth - 10) x = Math.max(8, event.clientX - rect.width - 12);
      if (y + rect.height > window.innerHeight - 10) y = Math.max(8, event.clientY - rect.height - 12);
      tooltip.style.left = `${x}px`;
      tooltip.style.top = `${y}px`;
    };
    $$('[data-workload-tooltip]', workload).forEach((bar) => {
      const show = (event) => {
        tooltip.textContent = bar.dataset.workloadTooltip;
        tooltip.hidden = false;
        const rect = bar.getBoundingClientRect();
        position({clientX: event.clientX ?? rect.left, clientY: event.clientY ?? rect.bottom});
      };
      bar.addEventListener('mouseenter', show);
      bar.addEventListener('mousemove', position);
      bar.addEventListener('mouseleave', () => { tooltip.hidden = true; });
      bar.addEventListener('focus', show);
      bar.addEventListener('blur', () => { tooltip.hidden = true; });
    });
    window.addEventListener('scroll', () => { tooltip.hidden = true; }, true);
  }
})();
