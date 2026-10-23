(() => {
  'use strict';
  const lead = document.querySelector('#id_assigned_to');
  const extra = document.querySelector('.field-additional_assignees');
  if (!lead || !extra) return;
  const update = () => {
    const selected = lead.value;
    extra.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
      const matching = checkbox.value === selected;
      const item = checkbox.closest('label')?.parentElement || checkbox.closest('label');
      // Django CheckboxSelectMultiple may use a <div> wrapper per option.
      if (item && item !== extra) item.hidden = matching;
      if (matching) checkbox.checked = false;
    });
  };
  lead.addEventListener('change', update);
  update();
})();
