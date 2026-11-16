// A card shows its state as Home Assistant shows it (app 0.2.62, firmware 0.2.53 and 0.2.71), read from the real
// firmware's cards, no line of it quoted: a light that is off shows the bulb that is crossed out (mdi:lightbulb-off), one
// that is on its own bulb; whatever is off is Home Assistant's grey, whatever is on its colour (Tile::active, Home
// Assistant's stateActive, for every domain alike). tests/test_off_look.py keeps what the add-on does the same way.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
// Home Assistant's grey (theme.h ha::GREY, 0x9E9E9E) as the firmware paints it on a light card: the icon a touch darker
// (theme::icon), its circle the grey tinted into the card (theme::tint, 38).
const OFF = { icon: 0x898989, circle: 0xf0f0f0 };
const BULB = 0xf0335, BULB_OFF = 0xf0e4f;

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(480, 480, 170, 3, 3), 1);
let ms = 0;
const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
configure(connection(m), 'Look', 1, [
  { entity: 'light.off', name: 'Off', state: 'off', a: { supported_color_modes: ['brightness'] }, slot: 0, o: {} },
  { entity: 'light.on', name: 'On', state: 'on', a: { supported_color_modes: ['brightness'], brightness: 200 }, slot: 1, o: {} },
  { entity: 'switch.off', name: 'Socket', state: 'off', a: {}, slot: 2, o: {} },
  { entity: 'switch.on', name: 'Socket on', state: 'on', a: {}, slot: 3, o: {} },
]);
tick();

// A card's icon as the firmware drew it: its glyph, its ink and the circle behind it.
function icon(entity) {
  const layout = JSON.parse(m.ccall('preview_layout', 'string', [], []));
  const card = layout.cards.findIndex((c) => c.entity === entity);
  assert.ok(card >= 0, `${entity} is on the glass`);
  const glyph = layout.objects.find((o) => o.card === card && o.icon);
  assert.ok(glyph, `${entity} has an icon`);
  const circle = layout.objects.find((o) => o.id === glyph.parent);
  return { glyph: glyph.text.codePointAt(0), color: glyph.color, circle: circle?.bg };
}
const hex = (v) => '#' + (v ?? 0).toString(16).padStart(6, '0');

const off = icon('light.off'), on = icon('light.on');
assert.equal(off.glyph.toString(16), BULB_OFF.toString(16), 'a light that is off shows the bulb that is crossed out');
assert.equal(on.glyph.toString(16), BULB.toString(16), 'a light that is on shows its own bulb');
assert.equal(hex(off.color), hex(OFF.icon), 'a light that is off is grey');
assert.equal(hex(off.circle), hex(OFF.circle), 'and so is its circle');
assert.notEqual(hex(on.color), hex(OFF.icon), 'a light that is on is not grey');
assert.notEqual(hex(on.circle), hex(OFF.circle), 'nor is its circle');

// Every domain alike (Tile::active): a switch that is off is the same grey, one that is on is not, its icon the same.
const socket = icon('switch.off'), socketOn = icon('switch.on');
assert.deepEqual([hex(socket.color), hex(socket.circle)], [hex(OFF.icon), hex(OFF.circle)], 'a switch that is off is the same grey');
assert.notEqual(hex(socketOn.color), hex(OFF.icon), 'a switch that is on is not grey');
assert.equal(socket.glyph, socketOn.glyph, 'a switch keeps its icon off and on: only a light crosses out its bulb');

console.log('state look: off is grey and the bulb crossed out, on is coloured, every domain alike');
