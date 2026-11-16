// The lock (firmware 0.5.0), read from the real firmware, no line of it quoted: Home Assistant's icon and colour for
// every state (lock/icons.json, --state-lock-*-color); a tap locks at once and unlocking asks for a second tap, which
// belongs to the tile (a first tap on another tile of the same lock ends the wait); a lock set to lock only never
// unlocks from the screen; a lock with a code opens the keypad, sends the code with lock.unlock, and a refused code
// becomes the event esphome.screen_lock_code_refused, which never carries the code.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const BACK = 0xf004d, LOCK = 0xf033e, LOCK_OPEN = 0xf0fc6, LOCK_CLOCK = 0xf097f, LOCK_ALERT = 0xf08ee, OK = 0xf012c;
const lock = (entity, state, a = {}, o = {}) => ({ entity, name: entity.split('.')[1], state, a: { supported_features: 1, ...a }, o });
const TILES = [lock('lock.front', 'locked'), lock('lock.back', 'unlocked'), lock('lock.jam', 'jammed'), lock('lock.moving', 'locking'),
  lock('lock.coded', 'locked', { code_format: '^\\d{4}$' }), lock('lock.front', 'locked'), lock('lock.only', 'locked', {}, { guard: 'lock_only' }),
  lock('lock.gate', 'open')].map((t, slot) => ({ ...t, slot }));

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(1280, 800, 149, 4, 3), 1);
let ms = 0;
const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
configure(connection(m), 'Locks', 1, TILES);
tick();
const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
const press = (o) => { const x = (o.x1 + o.x2) / 2, y = (o.y1 + o.y2) / 2; m._preview_touch(x, y, 1); tick(2); m._preview_touch(x, y, 0); tick(6); };
const action = () => { const a = m.ccall('preview_next_action', 'string', [], []); return a ? JSON.parse(a) : null; };
const actions = () => { const out = []; for (let a = action(); a; a = action()) out.push(a); return out; };
const card = (slot) => {
  const l = layout(), own = l.objects.filter((o) => o.card === slot && o.type === 'label');
  return { box: l.objects.find((o) => o.id === l.cards[slot].object), icon: own.find((o) => o.icon), words: own.filter((o) => !o.icon).map((o) => o.text) };
};
// A tap on a tile, after the quiet a finger leaves between two taps; Home Assistant takes what it sends.
const tap = (slot) => {
  tick(10); press(card(slot).box);
  const sent = actions();
  for (const a of sent) if (!a.event) m._preview_action_response(a.call_id, 1, 0);
  tick(2);
  return sent;
};
// The hue of a colour, in degrees.
const hue = (rgb) => {
  const r = (rgb >> 16 & 255) / 255, g = (rgb >> 8 & 255) / 255, b = (rgb & 255) / 255, max = Math.max(r, g, b), d = max - Math.min(r, g, b);
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
};
const near = (a, b) => Math.min(Math.abs(a - b), 360 - Math.abs(a - b)) < 20;

// Home Assistant's icons and colours: green locked, orange on its way, red otherwise.
for (const [slot, glyph, colour, what] of [[0, LOCK, 122, 'locked: mdi:lock, green'], [1, LOCK_OPEN, 4, 'unlocked: mdi:lock-open-variant, red'],
  [2, LOCK_ALERT, 4, 'jammed: mdi:lock-alert, red'], [3, LOCK_CLOCK, 36, 'locking: mdi:lock-clock, orange'], [7, LOCK_OPEN, 4, 'open: red']]) {
  const { icon } = card(slot);
  assert.equal(icon.text.codePointAt(0), glyph, what);
  assert.ok(near(hue(icon.color), colour), `${what} (hue ${Math.round(hue(icon.color))})`);
}
actions();

// A code: the keypad, the code with lock.unlock, and a refusal that never carries it.
assert.deepEqual(tap(4), [], 'a lock with a code sends nothing on a tap');
const pad = () => {
  const l = layout(), labels = l.objects.filter((o) => o.card < 0 && o.type === 'label' && o.text);
  const keyOf = (label) => { for (let o = label; o; o = l.objects.find((p) => p.id === o.parent)) if (o.clickable) return o; return label; };
  return { words: labels.filter((o) => !o.icon).map((o) => o.text), key: (text) => keyOf(labels.find((o) => (o.icon ? o.text.codePointAt(0) === text : o.text === text))) };
};
assert.ok(['1', '2', '3', '4', '0'].every((d) => pad().words.includes(d)), 'it opens the keypad');
for (const digit of '1234') { tick(10); press(pad().key(digit)); }
tick(10); press(pad().key(OK));
const unlock = actions().find((a) => a.service === 'lock.unlock');
assert.deepEqual(unlock?.data, { entity_id: 'lock.coded', code: '1234' }, 'the code goes with lock.unlock');
m.ccall('preview_action_response', null, ['number', 'number', 'string'], [unlock.call_id, 0, 'Wrong code']);
tick(8);
const refused = actions().filter((a) => a.service === 'esphome.screen_lock_code_refused');
assert.equal(refused.length, 1, 'a refused code is an event of its own');
assert.ok(!JSON.stringify(refused[0]).includes('1234'), 'which never carries the code');
tick(10); press(pad().key(BACK));
assert.ok(!pad().words.includes('0'), 'the back key closes the keypad');
assert.ok(['Unlock', 'Open door'].every((w) => pad().words.includes(w)), "onto the lock's card, with Home Assistant's keys");
tick(10); press(pad().key(BACK));

// A tap locks at once.
assert.deepEqual(tap(1).map((a) => [a.service, a.data.entity_id]), [['lock.lock', 'lock.back']], 'an unlocked lock locks on one tap');
// Unlocking asks first; the second tap unlocks.
assert.deepEqual(tap(0), [], 'a first tap on a locked lock sends nothing');
assert.ok(card(0).words.includes('Confirm'), 'and asks to confirm');
assert.deepEqual(tap(0).map((a) => [a.service, a.data.entity_id]), [['lock.unlock', 'lock.front']], 'the second tap unlocks');
// The wait is the tile's: a first tap on another tile of the same lock ends it.
assert.deepEqual(tap(0), [], 'a first tap asks again');
assert.deepEqual(tap(5), [], 'a tap on the other tile of the same lock is a first tap there');
assert.deepEqual(tap(0), [], 'and ended the wait of the first tile, so its next tap asks again and unlocks nothing');
tap(0);
// Lock only: the screen never unlocks it.
assert.deepEqual(tap(6), [], 'a lock set to lock only does not unlock');
assert.deepEqual(tap(6), [], 'not on a second tap either');
assert.ok(card(6).words.some((w) => /only/i.test(w)), 'and says it only locks here');

console.log('lock card: icons and colours, one tap locks, two unlock per tile, lock only, the keypad and a refused code');
