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

// More cards on a screen of their own: a light's slider, a lamp's own colour by Home Assistant's contrast rule, an airco
// that is off, and a card over the whole page.
async function screen(tiles) {
  const n = await createModule({ wasmBinary });
  assert.equal(n._preview_init(480, 480, 170, 3, 3), 1);
  let t = 0;
  configure(connection(n), 'Look', 1, tiles);
  for (let i = 0; i < 8; i++) { t += 64; n._preview_time(t, 1789401840, 7200); n._preview_render(); }
  const layout = JSON.parse(n.ccall('preview_layout', 'string', [], []));
  return (entity) => {
    const card = layout.cards.findIndex((c) => c.entity === entity);
    assert.ok(card >= 0, `${entity} is on the glass`);
    const own = layout.objects.filter((o) => o.card === card);
    return { card: layout.objects.find((o) => o.id === layout.cards[card].object), icon: own.find((o) => o.icon),
      slider: own.find((o) => o.type === 'slider'), words: own.filter((o) => o.type === 'label' && !o.icon).map((o) => o.text) };
  };
}
const lamp = (hs) => ({ supported_color_modes: ['hs'], color_mode: 'hs', brightness: 200, hs_color: hs });
const more = await screen([
  { entity: 'light.slider_off', name: 'Desk', state: 'off', a: { supported_color_modes: ['brightness'] }, slot: 0, o: { inline: 'slider' } },
  { entity: 'light.slider_on', name: 'Desk', state: 'on', a: { supported_color_modes: ['brightness'], brightness: 128 }, slot: 1, o: { inline: 'slider' } },
  { entity: 'light.blue', name: 'Blue', state: 'on', a: lamp([200, 60]), slot: 2, o: {} },
  { entity: 'light.pale', name: 'Pale', state: 'on', a: lamp([200, 5]), slot: 3, o: {} },
  { entity: 'climate.airco', name: 'Airco', state: 'off', unit: '°C', slot: 4, o: {},
    a: { temperature: 21, current_temperature: 19, hvac_modes: ['off', 'cool'], min_temp: 16, max_temp: 30, target_temp_step: 1 } },
]);
// Home Assistant's grey itself (theme.h ha::GREY) and its amber (ha::AMBER) on a slider's fill.
assert.equal(hex(more('light.slider_off').slider.fill), '#9e9e9e', 'the slider of a light that is off is grey');
assert.equal(hex(more('light.slider_on').slider.fill), '#ffc107', 'the slider of a light that is on is its amber');
assert.notEqual(hex(more('light.blue').icon.color), hex(on.color), 'a lamp that is on shows its own colour');
assert.equal(hex(more('light.pale').icon.color), hex(on.color), 'a lamp too pale to lift keeps the amber of a lamp that is on');
const airco = more('climate.airco').words.find((w) => w !== 'Airco');
assert.ok(airco?.startsWith('Off'), `an airco that is off says so first, before its temperatures (${airco})`);
assert.ok(!airco.includes('21'), 'and shows no setpoint');
// A card over the whole page is the card like every other, on or off: its state shows in its icon and controls.
const whole = await screen([{ entity: 'light.whole', name: 'Whole', state: 'on', a: { supported_color_modes: ['brightness'], brightness: 200 }, slot: 0, o: { size: 'full' } }]);
assert.equal(hex(whole('light.whole').card.bg), '#ffffff', 'a light that is on over the whole page is a white card');

console.log('state look: off is grey and the bulb crossed out, on is coloured, every domain alike; sliders, lamp colours, an airco, a whole page');
