(() => {
  const root = document.querySelector('[data-employee-combobox]');
  if (!root) return;

  const search = root.querySelector('#employee-search');
  const toggle = root.querySelector('.employee-picker-toggle');
  const list = root.querySelector('#employee-options');
  const hiddenEmployee = document.querySelector('#id_employee');
  const password = document.querySelector('#id_password');
  const form = document.querySelector('#employee-login-form');
  const options = Array.from(root.querySelectorAll('.employee-picker-option'));
  const empty = root.querySelector('.employee-picker-empty');

  if (!search || !toggle || !list || !hiddenEmployee) return;

  let visibleOptions = options.slice();
  let activeIndex = -1;

  const normalize = (value) =>
    (value || '')
      .toLocaleLowerCase('ru-RU')
      .replace(/\s+/g, ' ')
      .trim();

  const isOpen = () => !list.hidden;

  const setActive = (index) => {
    visibleOptions.forEach((option) => {
      option.classList.remove('active');
      option.setAttribute('aria-selected', 'false');
    });

    activeIndex = index;

    if (index >= 0 && visibleOptions[index]) {
      const option = visibleOptions[index];
      option.classList.add('active');
      option.setAttribute('aria-selected', 'true');
      search.setAttribute('aria-activedescendant', option.id);
      option.scrollIntoView({block: 'nearest'});
    } else {
      search.removeAttribute('aria-activedescendant');
    }
  };

  const openList = () => {
    list.hidden = false;
    search.setAttribute('aria-expanded', 'true');
  };

  const closeList = () => {
    list.hidden = true;
    search.setAttribute('aria-expanded', 'false');
    setActive(-1);
  };

  const filterOptions = () => {
    const query = normalize(search.value);
    const tokens = query.split(' ').filter(Boolean);

    visibleOptions = options.filter((option) => {
      const label = normalize(option.dataset.label);
      const match = !tokens.length || tokens.every((token) => label.includes(token));
      option.hidden = !match;
      return match;
    });

    if (empty) empty.hidden = visibleOptions.length !== 0;
    setActive(visibleOptions.length ? 0 : -1);
  };

  const choose = (option, moveToPassword = true) => {
    if (!option) return;

    hiddenEmployee.value = option.dataset.userId;
    search.value = option.dataset.label.trim();
    search.classList.add('has-selection');
    search.classList.remove('input-error');

    closeList();

    if (moveToPassword && password) {
      window.requestAnimationFrame(() => {
        password.focus();
      });
    }
  };

  options.forEach((option, index) => {
    option.id = `employee-option-${index}`;

    // PointerDown fires before the input can lose focus and is more reliable
    // than click/mousedown combinations in Chromium-based browsers.
    option.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      event.stopPropagation();
      choose(option, true);
    });
  });

  // Restore the selected employee after a wrong password without opening the list.
  if (hiddenEmployee.value) {
    const selected = options.find(
      (option) => option.dataset.userId === hiddenEmployee.value
    );
    if (selected) {
      search.value = selected.dataset.label.trim();
      search.classList.add('has-selection');
    }
  }

  // Mouse/touch click on the field must always open the list.
  search.addEventListener('pointerdown', (event) => {
    event.stopPropagation();
    filterOptions();
    openList();
  });

  // Typing opens and filters the list.
  search.addEventListener('input', () => {
    hiddenEmployee.value = '';
    search.classList.remove('has-selection');
    filterOptions();
    openList();
  });

  search.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (!isOpen()) {
        filterOptions();
        openList();
      }
      if (!visibleOptions.length) return;
      setActive(activeIndex < 0 ? 0 : (activeIndex + 1) % visibleOptions.length);
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (!isOpen()) {
        filterOptions();
        openList();
      }
      if (!visibleOptions.length) return;
      setActive(
        activeIndex <= 0 ? visibleOptions.length - 1 : activeIndex - 1
      );
      return;
    }

    if (event.key === 'Enter') {
      if (!isOpen()) return;

      event.preventDefault();
      if (visibleOptions.length) {
        choose(
          activeIndex >= 0 ? visibleOptions[activeIndex] : visibleOptions[0],
          true
        );
      }
      return;
    }

    if (event.key === 'Escape') {
      if (!isOpen()) return;
      event.preventDefault();
      closeList();
    }
  });

  toggle.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    event.stopPropagation();

    if (isOpen()) {
      closeList();
      search.focus();
      return;
    }

    filterOptions();
    openList();
    search.focus();
  });

  // Capture phase makes outside-click closing reliable even if another
  // component stops propagation later.
  document.addEventListener(
    'pointerdown',
    (event) => {
      if (!root.contains(event.target)) {
        closeList();
      }
    },
    true
  );

  // Tab from the picker should leave it closed.
  root.addEventListener('focusout', (event) => {
    const next = event.relatedTarget;
    if (next && root.contains(next)) return;

    window.requestAnimationFrame(() => {
      if (!root.contains(document.activeElement)) {
        closeList();
      }
    });
  });

  form?.addEventListener('submit', (event) => {
    if (hiddenEmployee.value) return;

    event.preventDefault();
    search.classList.add('input-error');
    search.focus();
    filterOptions();
    openList();
  });
})();
