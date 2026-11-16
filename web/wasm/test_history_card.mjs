// History on a detail card (app 0.2.59, firmware 0.2.51), read from the real firmware, no line of it quoted. A card of
// an entity with history (sensor, binary_sensor, switch, input_boolean, person, number, input_number) asks the add-on
// with an event, esphome.screen_history, which needs no permission to call actions, carrying its inbox, entity, hours,
// session, rev and view; a light's card asks nothing. The add-on's answers (tests/fixtures/history-card.json, which
// tests/test_history_card.py keeps equal to history_card.py) draw a line and a timeline; an answer for another entity
// or range than the one asked is dropped, and a range other than 1, 24 or 168 hours is refused. The range keys ask
// again while a command of the card waits for Home Assistant, and a finger on the chart reads it without the page or the
// card moving.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const FIXTURE = JSON.parse(readFileSync(new URL('../../tests/fixtures/history-card.json', import.meta.url), 'utf8'));
const BACK = 0xf004d, ASK = 'esphome.screen_history', KEYS = ['entity', 'hours', 'inbox', 'rev', 'session', 'view'];
const tile = (entity, state, a = {}, o = { tap: 'detail' }) => ({ entity, name: entity.split('.')[1], state, o, a });
const WITH_HISTORY = [tile('sensor.t', '20.0', { unit_of_measurement: '°C' }), tile('binary_sensor.door', 'off', { device_class: 'door' }),
  tile('switch.kettle', 'on'), tile('input_boolean.guests', 'off'), tile('person.sam', 'home'),
  tile('number.target', '5', { min: 0, max: 10, step: 1 }), tile('input_number.volume', '3', { min: 0, max: 10, step: 1 })];
const TILES = [...WITH_HISTORY, tile('light.lamp', 'on'), tile('switch.fan', 'on', {}, {})].map((t, slot) => ({ ...t, slot }));

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(1280, 800, 149, 4, 3), 1);
let ms = 0;
const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, FIXTURE.line.end, 7200); m._preview_render(); } };
const receive = connection(m);
configure(receive, 'History', 1, TILES);
tick();
const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
const touch = (x, y, down) => m._preview_touch(Math.round(x), Math.round(y), down);
const middle = (o) => [(o.x1 + o.x2) / 2, (o.y1 + o.y2) / 2];
const press = (o) => { const [x, y] = middle(o); touch(x, y, 1); tick(2); touch(x, y, 0); tick(6); };
const action = () => { const a = m.ccall('preview_next_action', 'string', [], []); return a ? JSON.parse(a) : null; };
const actions = () => { const out = []; for (let a = action(); a; a = action()) out.push(a); return out; };
const asked = () => actions().filter((a) => a.service === ASK);
// The card over the page: its words, and the clickable object a label stands in.
const over = () => {
  const l = layout(), labels = l.objects.filter((o) => o.card < 0 && o.type === 'label' && o.text);
  const keyOf = (label) => { for (let o = label; o; o = l.objects.find((p) => p.id === o.parent)) if (o.clickable) return o; return label; };
  return { words: labels.filter((o) => !o.icon).map((o) => o.text), word: (text) => keyOf(labels.find((o) => !o.icon && o.text === text)),
    back: () => { const label = labels.find((o) => o.icon && o.text.codePointAt(0) === BACK); return label && keyOf(label); } };
};
const box = (entity) => { const l = layout(); return l.objects.find((o) => o.id === l.cards[l.cards.findIndex((c) => c.entity === entity)].object); };
const open = (entity) => { press(box(entity)); assert.ok(over().back(), `${entity}'s card is open`); };
const close = () => { press(over().back()); actions(); };

// Every card with history asks for a day of it with an event, and a light's card asks nothing.
actions();
const views = new Map();
for (const { entity } of WITH_HISTORY) {
  open(entity);
  const [ask, ...more] = asked();
  assert.equal(more.length, 0, `${entity}: one ask`);
  assert.equal(ask?.event, true, `${entity}: an event, which needs no permission to call actions`);
  assert.deepEqual(Object.keys(ask.data).sort(), KEYS, `${entity}: the ask carries ${KEYS.join(', ')}`);
  assert.deepEqual([ask.data.entity, ask.data.hours], [entity, '24'], `${entity}: a day of its own history`);
  views.set(entity, ask.data.view);
  close();
}
open('light.lamp');
assert.equal(asked().length, 0, "a light's card asks for no history");
close();

// The answers draw: a line with its highest and lowest, a timeline with the time in each state.
open('sensor.t');
let [ask] = asked();
receive({ ...FIXTURE.timeline, view: Number(ask.data.view) });
tick();
assert.ok(over().words.includes('Loading history...'), 'an answer for another entity is dropped');
receive({ ...FIXTURE.line, hours: 168, view: Number(ask.data.view) });
tick();
assert.ok(over().words.includes('Loading history...'), 'an answer for another range is dropped');
receive({ ...FIXTURE.line, view: Number(ask.data.view) });
tick();
assert.ok(over().words.some((w) => w.startsWith('High 23.5')) && over().words.some((w) => w.startsWith('Low 19.5')), 'the line shows its highest and lowest');
assert.ok(FIXTURE.line.yt.every(([, text]) => over().words.includes(text)), 'and its axis');

// A finger on the chart reads it; neither the page nor the card moves.
const page = m._preview_page();
touch(200, 400, 1); tick(2);
for (let x = 220; x <= 900; x += 40) { touch(x, 405, 1); tick(1); }
assert.ok(over().words.some((w) => w.startsWith('average of')), 'a finger on the chart reads the hour under it');
touch(900, 405, 0); tick(8);
assert.equal(m._preview_page(), page, 'the drag turns no page');
assert.ok(over().back(), 'and keeps the card open');
assert.equal(actions().length, 0, 'and asks nothing');
close();

open('switch.kettle');
[ask] = asked();
receive({ ...FIXTURE.timeline, view: Number(ask.data.view) });
tick();
for (const [word, , seconds] of FIXTURE.timeline.states) assert.ok(over().words.includes(word), `the timeline names ${word} (${seconds} s)`);
close();

// A range key asks again while the card's command still waits for Home Assistant (no answer to switch.turn_off).
{
  const [x, y] = middle(box('switch.fan'));
  touch(x, y, 1); tick(2); touch(x, y, 0); tick(2);
  assert.ok(actions().some((a) => a.service === 'switch.turn_off'), 'a tap switches the fan, and its call waits');
  ms += 1000; tick(2);
  touch(x, y, 1); for (let k = 0; k < 40; k++) { tick(1); touch(x, y, 1); } touch(x, y, 0); tick(30);
  assert.ok(over().back(), 'holding opens its card');
  asked();
  press(over().word('1 week'));
  [ask] = asked();
  assert.deepEqual([ask?.data.entity, ask?.data.hours], ['switch.fan', '168'], 'the week key asks while the switch waits');
  press(over().word('1 hour'));
  [ask] = asked();
  assert.equal(ask?.data.hours, '1', 'and so does the hour key');
  // A range the card has no key for is refused.
  assert.throws(() => receive({ ...FIXTURE.timeline, entity: 'switch.fan', hours: 12, view: Number(ask.data.view) }), /history/,
    'an answer of 12 hours is refused');
}

console.log(`history card: ${WITH_HISTORY.length} kinds ask by event, a light none; line, timeline, ranges, scrub and a waiting command`);
