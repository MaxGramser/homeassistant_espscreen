// Firmware 0.17.0 (GitHub #93), read from the real firmware, no line of it quoted: an on/off or run card two rows tall
// is one big key (its icon grows, no key or bar of its own, a tap anywhere switches it), for exactly the domains that
// switch or run and only without another control; the flip clock on a card two columns and two rows fills it with two
// blocks side by side and one line under them, the day at the left and AM or PM at the right; the bedside clock puts
// AM or PM under its time; and a key under the bedside clock whose name is hidden keeps its place.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const WIDTH = 1280, HEIGHT = 800;

async function screen(tiles, clock24 = false) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(WIDTH, HEIGHT, 149, 4, 3), 1);
  let ms = 0;
  const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  const receive = connection(m);
  receive({ op: 'begin', title: 'Shapes', pages: 1, tiles: tiles.length, home: 0, keepalive: 60, clock_24h: clock24 });
  receive({ op: 'page', p: 0, id: '0000000000000001', title: '', home_control: false, excluded: false, items: [] });
  tiles.forEach((t, i) => receive({ name: '', state: 'ok', a: {}, o: {}, ...t, i, op: 'tile' }));
  receive({ op: 'commit' });
  tick(20);
  const layout = JSON.parse(m.ccall('preview_layout', 'string', [], []));
  const card = (entity) => {
    const c = layout.cards.findIndex((x) => x.entity === entity), own = layout.objects.filter((o) => o.card === c);
    return { box: own.find((o) => o.id === layout.cards[c].object), objects: own, labels: own.filter((o) => o.type === 'label' && !o.hidden && o.text),
      // The round ground behind the tile's icon.
      ring: own.filter((o) => o.type === 'object')[1] };
  };
  const tap = (o, dy = 0.75) => {
    const x = (o.x1 + o.x2) / 2, y = o.y1 + (o.y2 - o.y1) * dy;
    m._preview_touch(x, y, 1); tick(2); m._preview_touch(x, y, 0); tick(6);
    const out = []; for (let a = m.ccall('preview_next_action', 'string', [], []); a; a = m.ccall('preview_next_action', 'string', [], [])) out.push(JSON.parse(a));
    return out;
  };
  return { card, tap };
}
const width = (o) => o.x2 - o.x1;

// The big key: the same domain as a one-row card and as a card two rows tall.
const SWITCHES = [['light', 'on', { supported_color_modes: ['onoff'] }, 'light.turn_off'], ['switch', 'on', {}, 'switch.turn_off'],
  ['input_boolean', 'on', {}, 'input_boolean.turn_off'], ['fan', 'on', {}, 'fan.turn_off'], ['script', 'off', {}, 'script.turn_on'],
  ['scene', '2026-01-01T00:00:00+00:00', {}, 'scene.turn_on'], ['button', 'unknown', {}, 'button.press'],
  ['input_button', 'unknown', {}, 'input_button.press']];
const OTHERS = [['cover', 'open', { supported_features: 15, current_position: 100 }], ['media_player', 'playing', { supported_features: 21437 }],
  ['vacuum', 'docked', { supported_features: 12828 }], ['climate', 'heat', { hvac_modes: ['off', 'heat'], temperature: 20, current_temperature: 19 }],
  ['lock', 'locked', {}]];
// A domain as a card two rows tall (.tall) beside a one-row card of it (.one).
const pair = async (domain, state, a, tall = {}) => {
  const s = await screen([{ entity: `${domain}.tall`, name: 'Tall', state, a, slot: 0, o: { size: 'tall', ...tall } },
    { entity: `${domain}.one`, name: 'One', state, a, slot: 1 }]);
  return { ...s, tall: s.card(`${domain}.tall`), one: s.card(`${domain}.one`) };
};
const isBig = ({ tall, one }) => tall.objects.length === one.objects.length && width(tall.ring) > width(one.ring);
for (const [domain, state, a, service] of SWITCHES) {
  const s = await pair(domain, state, a);
  assert.ok(isBig(s), `${domain} two rows tall is one big key: its icon grows and it has no key or bar of its own`);
  const done = s.tap(s.tall.box, 0.85);
  assert.ok(done.some((x) => x.service === service && x.data.entity_id === `${domain}.tall`), `a tap low on the big key: ${service}`);
}
for (const [domain, state, a] of OTHERS) {
  const s = await pair(domain, state, a);
  assert.ok(!isBig(s) && s.tall.objects.length > s.one.objects.length, `${domain} two rows tall keeps its own controls`);
}
// Another control makes it no big key: a lamp with its slider, or with a brightness bar.
const lamp = { supported_color_modes: ['brightness'], brightness: 128 };
assert.ok(!isBig(await pair('light', 'on', lamp, { inline: 'slider' })), 'a lamp with an inline slider is no big key');
assert.ok(!isBig(await pair('light', 'on', lamp, { controls: 'brightness' })), 'a lamp with a brightness bar is no big key');
assert.ok(isBig(await pair('light', 'on', lamp, { controls: 'toggle' })), 'a lamp set to toggle is');
// The flip clock on a card two columns and two rows: two blocks side by side, the day under them, AM or PM at the right.
{
  const { card } = await screen([{ entity: 'screen.clock', slot: 0, o: { size: 'square', display: 'flip' } }]);
  const c = card('screen.clock'), [hours, minutes, day, ampm] = c.labels;
  assert.ok(width(hours) > width(c.box) * 0.4 && width(minutes) > width(c.box) * 0.4, 'each block takes half the card');
  assert.ok(hours.x2 <= minutes.x1 && Math.abs(hours.y1 - minutes.y1) < 2, 'side by side');
  assert.ok(day.y1 > hours.y2 && ampm.y1 === day.y1, 'one line under them');
  assert.ok(day.x1 - c.box.x1 < 40 && c.box.x2 - ampm.x2 < 40, 'the day at the left, AM or PM at the right');
  assert.equal(ampm.text, 'PM', 'in the afternoon, on a 12-hour clock');
}
// The bedside clock: AM or PM under its time, at the end of it; a 24-hour clock has none.
const BEDSIDE = (keyOptions = {}) => [{ entity: 'screen.nightstand', slot: 0, o: { size: 'full' } },
  { entity: 'light.lamp', name: 'Lamp', state: 'on', in: 0, k: 0, o: keyOptions }, { entity: 'light.fan', name: 'Fan', state: 'on', in: 0, k: 1 }];
{
  const { card } = await screen(BEDSIDE());
  const c = card('screen.nightstand'), time = c.labels.find((o) => /\d:\d\d/.test(o.text)), ampm = c.labels.find((o) => o.text === 'PM');
  assert.ok(time && ampm, 'the bedside clock shows its time and PM');
  assert.ok(ampm.y1 > (time.y1 + time.y2) / 2 && ampm.y2 <= time.y2, 'PM under the middle of the time, within its box');
  assert.ok(ampm.x1 > (time.x1 + time.x2) / 2, 'at the end of the time');
  const h24 = (await screen(BEDSIDE(), true)).card('screen.nightstand');
  assert.ok(!h24.labels.some((o) => o.text === 'PM' || o.text === 'AM'), 'a 24-hour clock has no AM or PM');
}
// A key whose name is hidden keeps its place, and the others theirs.
{
  const named = (await screen(BEDSIDE())).card, hidden = (await screen(BEDSIDE({ overlay: 'none' }))).card;
  const names = (card) => card('screen.nightstand').labels.map((o) => o.text);
  assert.ok(names(named).includes('Lamp') && !names(hidden).includes('Lamp'), "the hidden name is not drawn");
  assert.ok(names(hidden).includes('Fan'), 'the other key keeps its name');
  for (const entity of ['light.lamp', 'light.fan']) {
    const [a] = named(entity).labels, [b] = hidden(entity).labels;
    assert.deepEqual([b.x1, b.y1, b.x2, b.y2], [a.x1, a.y1, a.x2, a.y2], `${entity}'s key stands where it stood with its name`);
  }
}

console.log(`tile shapes 0.17.0: ${SWITCHES.length} big keys, ${OTHERS.length} kinds that keep their controls, the flip and bedside clocks, a hidden key name`);
