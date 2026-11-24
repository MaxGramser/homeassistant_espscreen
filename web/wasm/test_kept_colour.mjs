// A card on a kept page follows a change of colour alone (GitHub #349): a thermostat that goes from Auto to Heat stays
// active, only its colour changes. While its page is out of sight the change arrives; when the page comes back the
// card wears the new colour, the same pixels as a card that was on the glass when the change came. Read from the real
// firmware's frame.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const width = 480, height = 480, columns = 2, rows = 2;
const climate = (state) => ({ entity: 'climate.living', name: 'Living', state, slot: columns * rows, o: {},
  a: { hvac_modes: ['off', 'heat', 'cool', 'auto'], current_temperature: 20.5, temperature: 21, target_temp_step: 0.5,
       min_temp: 7, max_temp: 35, supported_features: 1 } });
const TILES = [{ entity: 'light.desk', name: 'Desk', state: 'on', slot: 0, o: {}, a: { brightness: 128 } }, climate('auto')];

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
const state = (s) => { const { slot, o, ...tile } = climate(s); receive({ op: 'state', i: 1, ...tile }); settle(); };
// The pixels of the thermostat's card.
const card = () => {
  const layout = JSON.parse(m.ccall('preview_layout', 'string', [], []));
  const c = layout.cards.find((k) => k.entity === 'climate.living');
  assert.ok(c, 'the thermostat is on the glass');
  const box = layout.objects.find((o) => o.id === c.object), p = m._preview_frame(), out = [];
  for (let y = box.y1; y <= box.y2; y++) out.push(...m.HEAPU8.subarray(p + (y * width + box.x1) * 4, p + (y * width + box.x2 + 1) * 4));
  return Buffer.from(out).toString('base64');
};

next();
assert.equal(m._preview_page(), 1, 'the thermostat\'s page');
const auto = card();
previous();
assert.equal(m._preview_page(), 0, 'back to the first page; the thermostat\'s page is kept');
state('heat');
next();
const returned = card();
assert.notEqual(returned, auto, 'a thermostat that went from Auto to Heat out of sight comes back in its new colour');
// The same change while it is on the glass: the card it should have come back as.
state('auto');
state('heat');
assert.equal(returned, card(), 'the card that comes back is the card the glass shows for Heat');
console.log('kept colour: a card on a kept page comes back in the colour its state changed to');
