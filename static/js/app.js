(() => {
  const copyButton = document.querySelector('[data-copy-task-link]');
  if (copyButton) {
    copyButton.addEventListener('click', async () => {
      const url = copyButton.dataset.copyTaskLink || window.location.href;
      try {
        await navigator.clipboard.writeText(url);
        const old = copyButton.textContent;
        copyButton.textContent = 'Ссылка скопирована';
        setTimeout(() => { copyButton.textContent = old; }, 1500);
      } catch (_) {
        window.prompt('Скопируйте ссылку:', url);
      }
    });
  }

  const commentForm = document.querySelector('.comment-form');
  const commentText = commentForm?.querySelector('textarea');
  if (commentForm && commentText) {
    commentText.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        if (commentText.value.trim()) commentForm.requestSubmit();
      }
    });
  }

  const compactToggle = document.querySelector('[data-compact-toggle]');
  const taskTable = document.querySelector('[data-task-table]');
  if (compactToggle && taskTable) {
    const key = 'task-tracker-compact-table';
    const apply = (compact) => {
      taskTable.classList.toggle('table-compact', compact);
      compactToggle.setAttribute('aria-pressed', compact ? 'true' : 'false');
      compactToggle.textContent = compact ? 'Обычный вид' : 'Компактный вид';
    };
    apply(localStorage.getItem(key) === '1');
    compactToggle.addEventListener('click', () => {
      const compact = !taskTable.classList.contains('table-compact');
      localStorage.setItem(key, compact ? '1' : '0');
      apply(compact);
    });
  }

  const kanbanFilter = document.querySelector('.kanban-filter');
  if (kanbanFilter) {
    const key = 'task-tracker-kanban-filter';
    const names = ['scope', 'priority', 'assigned'];
    const params = new URLSearchParams(window.location.search);
    if (params.toString()) {
      const state = {};
      names.forEach((name) => {
        const field = kanbanFilter.elements.namedItem(name);
        if (field) state[name] = field.value;
      });
      localStorage.setItem(key, JSON.stringify(state));
    } else {
      try {
        const state = JSON.parse(localStorage.getItem(key) || '{}');
        let changed = false;
        names.forEach((name) => {
          const field = kanbanFilter.elements.namedItem(name);
          if (field && Object.prototype.hasOwnProperty.call(state, name) && field.value !== state[name]) {
            field.value = state[name];
            changed = true;
          }
        });
        if (changed) kanbanFilter.requestSubmit();
      } catch (_) {
        localStorage.removeItem(key);
      }
    }
  }


  const updateTimelineTitleAlignment = () => {
    document.querySelectorAll('[data-timeline-title]').forEach((label) => {
      const bar = label.closest('.timeline-bar');
      if (!bar) return;
      // With a 2-line clamp, scrollHeight still exposes whether more text exists.
      const clipped = label.scrollHeight > label.clientHeight + 2;
      bar.classList.toggle('is-long-title', clipped);
    });
  };

  if (document.querySelector('[data-timeline-title]')) {
    window.requestAnimationFrame(updateTimelineTitleAlignment);
    if ('ResizeObserver' in window) {
      const observer = new ResizeObserver(updateTimelineTitleAlignment);
      observer.observe(document.querySelector('.workload-timeline-wrap'));
    } else {
      window.addEventListener('resize', updateTimelineTitleAlignment);
    }
  }



  const bulkForm = document.querySelector('[data-bulk-form]');
  if (bulkForm) {
    const checkboxes = Array.from(document.querySelectorAll('[data-task-select]'));
    const selectAll = document.querySelector('[data-select-all]');
    const action = bulkForm.querySelector('[name="action"]');
    const submit = bulkForm.querySelector('[data-bulk-submit]');
    const count = bulkForm.querySelector('[data-selected-count]');
    const fields = Array.from(bulkForm.querySelectorAll('[data-bulk-field]'));

    const updateCount = () => {
      const selected = checkboxes.filter((item) => item.checked).length;
      if (count) count.textContent = `${selected} выбрано`;
      if (submit) submit.disabled = selected === 0;
      if (selectAll) {
        selectAll.checked = selected > 0 && selected === checkboxes.length;
        selectAll.indeterminate = selected > 0 && selected < checkboxes.length;
      }
    };

    const updateBulkField = () => {
      const value = action?.value || '';
      fields.forEach((field) => {
        field.hidden = field.dataset.bulkField !== value;
      });
    };

    checkboxes.forEach((item) => item.addEventListener('change', updateCount));
    selectAll?.addEventListener('change', () => {
      checkboxes.forEach((item) => { item.checked = selectAll.checked; });
      updateCount();
    });
    action?.addEventListener('change', updateBulkField);
    updateBulkField();
    updateCount();
  }

  document.querySelectorAll('[data-auto-submit]').forEach((element) => {
    element.addEventListener('change', () => element.form?.requestSubmit());
  });
})();
