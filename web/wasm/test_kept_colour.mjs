// A card on a kept page follows every input of its paint (GitHub #349, runtime_tiles.h PaintedFrom). While its page is
// out of sight one input of each card changes: a thermostat from Auto to Heat (its colour alone: it stays active), a
// lamp's own colour, a light that goes unavailable, a light that goes off. When the page comes back each card wears
// what it changed to, the same pixels as a card that was on the glass when the change came. Read from the real
// firmware's frame, with pages kept as a board with PSRAM keeps them.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const width = 480, height = 480, columns = 2, rows = 2, cells = columns * rows;
const thermostat = (state) => ({ entity: 'climate.living', name: 'Living', state,
  a: { hvac_modes: ['off', 'heat', 'cool', 'auto'], current_temperature: 20.5, temperature: 21, target_temp_step: 0.5,
       min_temp: 7, max_temp: 35, supported_features: 1 } });
const lamp = (hs) => ({ entity: 'light.lamp', name: 'Lamp', state: 'on',
  a: { brightness: 200, color_mode: 'hs', hs_color: hs, supported_color_modes: ['hs'] } });
const light = (entity, name, state) => ({ entity, name, state, a: { brightness: 128, supported_color_modes: ['brightness'] } });
// Each card on the kept page, how it is and the one input that changes.
const CASES = [
  { why: 'the colour alone (Auto to Heat)', before: thermostat('auto'), after: thermostat('heat') },
  { why: "a lamp's own colour", before: lamp([30, 60]), after: lamp([220, 90]) },
  { why: 'available to unavailable', before: light('light.hall', 'Hall', 'on'), after: light('light.hall', 'Hall', 'unavailable') },
  { why: 'on to off', before: light('light.desk', 'Desk', 'on'), after: light('light.desk', 'Desk', 'off') },
];
const TILES = [{ ...light('light.home', 'Home', 'on'), slot: 0, o: {} },
  ...CASES.map((c, n) => ({ ...c.before, slot: cells + n, o: {} }))];

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(width, height, 170, columns, rows), 1);
m._preview_keep_pages(4);  // as a board with PSRAM: the page out of sight keeps its cards
let ms = 0;
const tick = (delta = 32) => { ms += delta; m._preview_time(ms, 1789401840, 7200); m._preview_render(); };
const settle = () => { for (let i = 0; i < 30; i++) tick(); };
const tap = (x, y) => { tick(250); m._preview_touch(x, y, 1); tick(120); m._preview_touch(x, y, 0); tick(300); settle(); };
const next = () => tap(width - 30, height - 22), previous = () => tap(30, height - 22);
const receive = connection(m);
configure(receive, 'Kept', 2, TILES);
settle();
const send = (n, tile) => { receive({ op: 'state', i: 1 + n, ...tile }); settle(); };
// The pixels of a card.
const card = (entity) => {
  const layout = JSON.parse(m.ccall('preview_layout', 'string', [], []));
  const c = layout.cards.find((k) => k.entity === entity);
  assert.ok(c, `${entity} is on the glass`);
  const box = layout.objects.find((o) => o.id === c.object), p = m._preview_frame(), out = [];
  for (let y = box.y1; y <= box.y2; y++) out.push(...m.HEAPU8.subarray(p + (y * width + box.x1) * 4, p + (y * width + box.x2 + 1) * 4));
  return Buffer.from(out).toString('base64');
};

next();
assert.equal(m._preview_page(), 1, 'the kept page');
const before = CASES.map((c) => card(c.before.entity));
previous();
assert.equal(m._preview_page(), 0, 'back to the first page; the other is kept');
CASES.forEach((c, n) => send(n, c.after));
next();
const returned = CASES.map((c) => card(c.after.entity));
// The same changes while the cards are on the glass: the cards they should have come back as.
CASES.forEach((c, n) => { send(n, c.before); send(n, c.after); });
CASES.forEach((c, n) => {
  assert.notEqual(returned[n], before[n], `${c.why}: the card that comes back is painted for the change`);
  assert.equal(returned[n], card(c.after.entity), `${c.why}: the card that comes back is the card the glass shows`);
});
console.log('kept colour: a kept card follows each input of its paint (colour, a lamp\'s own colour, availability, on and off)');
