// Binary sensors in Home Assistant's words (app 0.2.62, firmware 0.2.53): a door says Open or Closed, read from the real
// firmware's cards, no line of it quoted. The words are the add-on's table (header_bar.BINARY_STATES), which
// tests/fixtures/binary-words.json holds for both sides (tests/test_binary_words.py keeps it equal to the add-on's): every
// device class, on and off, on a tile and in its card's heading; without a class, or with one Home Assistant adds later,
// On and Off. A card that waits for its own history says its own words, never those of the card opened before it.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const WORDS = JSON.parse(readFileSync(new URL('../../tests/fixtures/binary-words.json', import.meta.url), 'utf8'));
const classes = Object.keys(WORDS);
const sensor = (entity, state, kind, slot) => ({ entity, name: kind ?? 'Plain', state, a: kind ? { device_class: kind } : {}, slot, o: {} });
const tiles = classes.flatMap((kind) => [sensor(`binary_sensor.${kind}_on`, 'on', kind), sensor(`binary_sensor.${kind}_off`, 'off', kind)])
  .concat([sensor('binary_sensor.plain', 'off'), sensor('binary_sensor.later', 'on', 'a_class_ha_adds_later')]);

// A screen of two by four cards on large glass, where every word fits whole on its card.
async function screen(batch) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(1280, 800, 149, 2, 4), 1);
  let ms = 0;
  const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  const receive = connection(m);
  configure(receive, 'Words', 1, batch.map((tile, slot) => ({ ...tile, slot })));
  tick();
  const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
  const words = (entity) => {
    const l = layout(), card = l.cards.findIndex((c) => c.entity === entity);
    assert.ok(card >= 0, `${entity} is on the glass`);
    return l.objects.filter((o) => o.card === card && o.type === 'label' && !o.icon).map((o) => o.text);
  };
  return { m, tick, receive, layout, words, batch };
}
const said = new Map();
for (let i = 0; i < tiles.length; i += 8) {
  const { words, batch } = await screen(tiles.slice(i, i + 8));
  for (const tile of batch) said.set(tile.entity, words(tile.entity));
}
for (const [kind, [on, off]] of Object.entries(WORDS)) {
  assert.ok(said.get(`binary_sensor.${kind}_on`).includes(on), `a ${kind} that is on says ${on}`);
  assert.ok(said.get(`binary_sensor.${kind}_off`).includes(off), `a ${kind} that is off says ${off}`);
}
assert.ok(said.get('binary_sensor.plain').includes('Off'), 'without a class: Off');
assert.ok(said.get('binary_sensor.later').includes('On'), 'with a class Home Assistant adds later: On');

// The card's heading says the same. Opened by a tap; the back key (mdi:arrow-left) closes it.
const two = [tiles.find((t) => t.entity === 'binary_sensor.door_on'), tiles.find((t) => t.entity === 'binary_sensor.window_on')];
const { m, tick, receive, layout } = await screen(two);
const press = (x, y) => { m._preview_touch(x, y, 1); tick(2); m._preview_touch(x, y, 0); tick(6); };
const open = (entity) => {
  const tile = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles[two.findIndex((t) => t.entity === entity)];
  press(tile.x + tile.width / 2, tile.y + tile.height / 2);
};
const card = () => layout().objects.filter((o) => o.card < 0 && o.type === 'label' && !o.icon).map((o) => o.text);
const back = () => {
  const objects = layout().objects;
  const key = objects.find((o) => o.clickable && objects.some((k) => k.parent === o.id && k.text === '\u{F004D}'));
  assert.ok(key, 'the card has its back key');
  press((key.x1 + key.x2) / 2, (key.y1 + key.y2) / 2);
};
const [doorOn] = WORDS.door, [windowOn] = WORDS.window;
open('binary_sensor.door_on');
assert.ok(card().includes(doorOn), `the card of a door that is on says ${doorOn}`);
// Its history brings Home Assistant's words for its states (the first card opened asks as view 1).
receive({ op: 'history', view: 1, entity: 'binary_sensor.door_on', hours: 24, kind: 'timeline', start: 1789398240, end: 1789401840,
  off: 7200, xt: [], words: [['on', 'Ajar']] });
tick();
assert.ok(card().includes('Ajar'), 'the card takes the words its history brings');
back();
// The next card, still waiting for its own history, says its own words, not those the last one had.
open('binary_sensor.window_on');
assert.ok(card().includes(windowOn), `a card waiting for its history says its own words (${windowOn})`);
assert.ok(!card().includes('Ajar'), 'and never those of the card opened before it');

console.log(`binary words: ${classes.length} classes on and off, the card's heading, and history words per card`);
