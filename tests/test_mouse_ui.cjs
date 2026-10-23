const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../static/js/soundscape.js'), 'utf8');

function setup(reducedMotion = false, values = new Map(), wallet = null) {
  const intervals = [];
  const nodes = [];
  const count = { textContent: '' }, title = { textContent: '' };
  const caught = { textContent: '' }, speed = { textContent: '' }, feedback = { textContent: '' };
  const hatButton = { listeners: {}, addEventListener(name, callback) { this.listeners[name] = callback; } };
  const scarfButton = { listeners: {}, addEventListener(name, callback) { this.listeners[name] = callback; } };
  const settings = { querySelector: (selector) => ({
    '[data-cheese-count]': count, '[data-cheese-title]': title,
    '[data-mouse-catches]': caught, '[data-mouse-speed]': speed,
    '[data-buy-hat]': hatButton, '[data-buy-scarf]': scarfButton,
    '[data-cheese-feedback]': feedback,
  })[selector] ?? null };

  function element(tag) {
    return {
      tag, listeners: {}, style: { setProperty(name, value) { this[name] = value; } },
      classList: { toggle() {} }, isConnected: false,
      setAttribute() {},
      addEventListener(name, callback) { this.listeners[name] = callback; },
      append(...children) { children.forEach(child => { child.isConnected = true; nodes.push(child); }); },
      remove() { this.isConnected = false; },
      getBoundingClientRect() { return { left: 110, right: 206, top: 640, bottom: 728, width: 96, height: 88 }; },
    };
  }
  const body = element('body');
  body.dataset = { soundUser: '7', mouseWallet: wallet ? '/mouse/wallet/' : undefined };
  body.append = (...children) => children.forEach(child => { child.isConnected = true; nodes.push(child); });
  const document = {
    body, hidden: false, cookie: 'csrftoken=test', hasFocus: () => true,
    querySelector: (selector) => selector === '#sound-settings' ? settings : null,
    createElement: element, addEventListener() {},
  };
  const window = {
    innerWidth: 1200, innerHeight: 800,
    matchMedia: (query) => ({ matches: query.includes('reduced-motion') ? reducedMotion : true }),
    addEventListener() {},
    setInterval: callback => { intervals.push(callback); return intervals.length; },
    clearInterval() {},
    setTimeout() {},
  };
  const deterministicMath = Object.create(Math);
  deterministicMath.random = () => 0.5;
  const context = {
    document, window, performance: { now: () => 0 },
    Math: deterministicMath,
    localStorage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) },
    setInterval: window.setInterval, setTimeout: window.setTimeout,
    fetch: wallet?.fetch,
  };
  vm.runInNewContext(source, context);
  return { window, intervals, nodes, count, title, caught, speed, hatButton, scarfButton, values };
}

test('legacy cheese imports once and wallet syncs to another browser', async () => {
  const values = new Map([
    ['ratracker:cheese:7', '6'], ['ratracker:cheese-earned:7', '11'],
    ['ratracker:catches:7', '3'], ['ratracker:wardrobe:7', JSON.stringify({ hat: true, scarf: false })],
  ]);
  const state = { cheese: 0, earned: 0, catches: 0, wardrobe: { hat: false, scarf: false }, legacy_imported: false };
  const seen = new Set();
  const actions = [];
  let offline = false;
  const wallet = { fetch: async (_url, options = {}) => {
    if (offline) throw Error('offline');
    if (options.method === 'POST') {
      const op = JSON.parse(options.body); actions.push(op.action);
      if (!seen.has(op.event_id)) {
        seen.add(op.event_id);
        if (op.action === 'import' && !state.legacy_imported) {
          state.cheese += op.legacy.cheese; state.earned += op.legacy.earned;
          state.catches += op.legacy.catches; state.wardrobe = { ...op.legacy.wardrobe };
          state.legacy_imported = true;
        } else if (op.action === 'catch') {
          state.cheese += op.reward; state.earned += op.reward; state.catches++;
        }
      }
    }
    return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(state)) };
  } };
  const tick = async () => { for (let i = 0; i < 12; i++) await new Promise(resolve => setImmediate(resolve)); };
  const first = setup(false, values, wallet);
  await tick();
  assert.equal(first.window.RaTrackerMouse.status().cheese, 6);
  assert.equal(state.cheese, 6);
  offline = true;
  first.window.RaTrackerMouse.spawn({ legendary: false });
  first.nodes.findLast(node => node.className === 'ratracker-runner').listeners.click();
  await tick();
  assert.equal(first.window.RaTrackerMouse.status().cheese, 7);
  assert.equal(state.cheese, 6);
  assert.equal(JSON.parse(values.get('ratracker:mouse-queue:7')).length, 1);
  offline = false;
  // Visibility events are not wired in this fake DOM; reopening the page retries the durable queue.
  const restored = setup(false, values, wallet);
  await tick();
  assert.equal(state.cheese, 7);
  assert.equal(restored.window.RaTrackerMouse.status().catches, 4);
  assert.equal(JSON.parse(values.get('ratracker:mouse-queue:7')).length, 0);
  const otherDevice = setup(false, new Map(), wallet);
  await tick();
  assert.equal(otherDevice.window.RaTrackerMouse.status().cheese, 7);
  assert.equal(otherDevice.window.RaTrackerMouse.status().wardrobe.hat, true);
  assert.equal(actions.filter(action => action === 'import').length, 1);
});

test('a catch stores one cheese; a golden catch stores five and leaves temporary paws', () => {
  const app = setup();
  assert.equal(app.window.RaTrackerMouse.status().cheese, 0);
  assert.equal(app.hatButton.disabled, true);
  assert.equal(app.window.RaTrackerMouse.spawn({ legendary: false }), true);
  let mouse = app.nodes.find(node => node.className === 'ratracker-runner');
  const initialDuration = parseFloat(mouse.style.animationDuration);
  app.intervals.at(-1)();
  assert.equal(app.nodes.filter(node => node.className === 'ratracker-paw').length, 1);
  mouse.listeners.click();
  assert.equal(app.window.RaTrackerMouse.status().cheese, 1);
  assert.equal(app.count.textContent, '1');
  assert.equal(app.values.get('ratracker:cheese:7'), '1');
  assert.equal(app.window.RaTrackerMouse.status().catches, 1);
  assert.ok(app.nodes.some(node => node.className === 'ratracker-cheese-bit'));

  assert.equal(app.window.RaTrackerMouse.spawn({ legendary: true }), true);
  mouse = app.nodes.find(node => node.className === 'ratracker-runner legendary');
  mouse.listeners.click();
  assert.equal(app.window.RaTrackerMouse.status().cheese, 6);
  assert.equal(app.values.get('ratracker:cheese:7'), '6');
  assert.equal(app.title.textContent, 'Начинающий мышелов');
  assert.equal(app.window.RaTrackerMouse.spawn({ legendary: true }), true);
  app.nodes.findLast(node => node.className === 'ratracker-runner legendary').listeners.click();
  assert.equal(app.window.RaTrackerMouse.status().cheese, 11);
  assert.equal(app.title.textContent, 'Опытный мышелов');
  assert.ok(app.nodes.some(node => node.className === 'mouse-toast' && node.textContent.includes('Новое звание')));
  assert.equal(app.window.RaTrackerMouse.status().catches, 3);
  assert.equal(app.window.RaTrackerMouse.spawn({ legendary: false }), true);
  mouse = app.nodes.findLast(node => node.className === 'ratracker-runner');
  assert.ok(parseFloat(mouse.style.animationDuration) < initialDuration);
  app.window.RaTrackerMouse.remove();

  app.hatButton.listeners.click();
  assert.equal(app.window.RaTrackerMouse.status().cheese, 6);
  assert.equal(app.window.RaTrackerMouse.status().earned, 11);
  assert.equal(app.window.RaTrackerMouse.status().title, 'Опытный мышелов');
  assert.equal(app.scarfButton.disabled, true);
  app.scarfButton.listeners.click();
  assert.equal(app.window.RaTrackerMouse.status().cheese, 6);
  assert.equal(app.window.RaTrackerMouse.spawn({ legendary: true }), true);
  app.nodes.findLast(node => node.className === 'ratracker-runner legendary').listeners.click();
  app.scarfButton.listeners.click();
  assert.equal(app.window.RaTrackerMouse.status().cheese, 3);
  assert.equal(app.window.RaTrackerMouse.status().catches, 4);
  assert.equal(app.window.RaTrackerMouse.status().wardrobe.hat, true);
  assert.equal(app.window.RaTrackerMouse.status().wardrobe.scarf, true);

  const reloaded = setup(false, app.values);
  assert.equal(reloaded.window.RaTrackerMouse.status().cheese, 3);
  assert.equal(reloaded.window.RaTrackerMouse.status().catches, 4);
  reloaded.window.RaTrackerMouse.spawn({ legendary: false });
  const outfit = reloaded.nodes.find(node => node.className === 'ratracker-outfit');
  assert.ok(outfit);
  const hat = reloaded.nodes.find(node => node.className === 'ratracker-hat');
  const scarf = reloaded.nodes.find(node => node.className === 'ratracker-scarf');
  assert.notEqual(hat.style['--hat-color'], scarf.style['--scarf-color']);
});

test('reduced-motion preference disables mouse and paw trail', () => {
  const app = setup(true);
  assert.equal(app.window.RaTrackerMouse.spawn(), false);
  assert.equal(app.nodes.length, 0);
});
