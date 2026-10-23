(() => {
  'use strict';
  const picker = document.getElementById('chat-emojis');
  const input = document.getElementById('chat-input');
  const trigger = document.getElementById('chat-emoji-button');
  if (!picker || !input || !trigger) return;

  const groups = [
    ['Лица', '😀 😃 😄 😁 😆 😅 😂 🤣 😊 🙂 🙃 😉 😍 🥰 😘 😋 😎 🤩 🥳 🤔 🤨 😐 😶 🙄 😏 😴 😮 😲 😢 😭 😤 😡 🤯 🥺 😇 🤗 🤭 🫡'],
    ['Жесты', '👍 👎 👏 🙌 👐 🤝 👋 ✋ 🤚 👌 🤌 🤏 ✌️ 🤞 🤟 🤘 🤙 💪 🙏 👀 🫶'],
    ['Символы', '❤️ 🧡 💛 💚 💙 💜 🖤 🤍 💔 ✨ ⭐ 🌟 🔥 💯 ✅ ❌ ⚠️ ❗ ❓ 💡 🔔'],
    ['Работа', '📌 📅 ⏰ ⏳ 📝 📋 📎 📁 📊 📈 📉 🔧 🛠️ 💻 🖥️ ☕ 🚀 🎯 🏆'],
    ['Веселье', '🎉 🎊 🎈 🎁 🧀 🐭 🐁 🐀 🐾 🐱 🦊 🐸 🌈 ☀️ 🌙 ⚡ 🍕 🍩 🎮'],
  ];
  let active = 0;
  const tabs = document.createElement('div');
  tabs.className = 'chat-emoji-tabs';
  tabs.setAttribute('role', 'group');
  tabs.setAttribute('aria-label', 'Категории эмодзи');
  const grid = document.createElement('div');
  grid.className = 'chat-emoji-grid';
  const buttons = [];

  function show(index) {
    active = index;
    buttons.forEach((button, i) => button.setAttribute('aria-pressed', String(i === active)));
    grid.replaceChildren();
    for (const emoji of groups[index][1].split(' ')) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = emoji;
      button.setAttribute('aria-label', `Добавить ${emoji}`);
      button.addEventListener('click', () => {
        input.setRangeText(emoji, input.selectionStart, input.selectionEnd, 'end');
        input.focus();
      });
      grid.append(button);
    }
  }
  groups.forEach(([name], index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = name;
    button.addEventListener('click', () => show(index));
    buttons.push(button);
    tabs.append(button);
  });
  picker.append(tabs, grid);
  show(0);
  picker.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      picker.hidden = true;
      trigger.focus();
    }
  });
})();
