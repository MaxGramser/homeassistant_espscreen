// A light group that only dims (GitHub #458): it opens the light card, not the colour card, and that card has the
// lamps key beside its power key, as the colour card has, which opens the group's page with a card per lamp. A light
// that is no group has the power key alone. Read from the real firmware.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const BACK = 0xF004D, POWER = 0xF0425, LAMPS = 0xF1253;
const dims = { brightness: 128, color_mode: 'brightness', supported_color_modes: ['brightness'] };
const TILES = [
  { entity: 'light.kitchen', name: 'Kitchen', state: 'on', slot: 0, o: {}, a: dims,
    x: { lamps: [{ e: 'light.pendant', n: 'Pendant', s: 1, d: 1, b: 50 }, { e: 'light.spots', n: 'Spots', s: 0, d: 1 }] } },
  { entity: 'light.desk', name: 'Desk', state: 'on', slot: 1, o: {}, a: dims },
];

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(1280, 800, 149, 4, 3), 1);
let ms = 0;
const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
configure(connection(m), 'Lights', 1, TILES);
tick();
const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
const actions = () => { const out = []; for (let a = m.ccall('preview_next_action', 'string', [], []); a; a = m.ccall('preview_next_action', 'string', [], [])) out.push(JSON.parse(a)); return out; };
const touch = (o, hold = 2) => { tick(10); const x = (o.x1 + o.x2) / 2, y = (o.y1 + o.y2) / 2; m._preview_touch(x, y, 1); for (let i = 0; i < hold; ++i) { tick(1); m._preview_touch(x, y, 1); } m._preview_touch(x, y, 0); tick(8); };
const over = () => layout().objects.filter((o) => o.card < 0);
const key = (code) => {
  const l = layout(), label = over().find((o) => o.type === 'label' && o.icon && o.text.codePointAt(0) === code);
  for (let o = label; o; o = l.objects.find((p) => p.id === o.parent)) if (o.clickable) return o;
  return null;
};
const words = () => layout().objects.filter((o) => o.type === 'label' && !o.icon).map((o) => o.text);
const tile = (slot) => { const l = layout(); return l.objects.find((o) => o.id === l.cards[slot].object); };

// The group: a hold opens its light card, with the power key and the lamps key in the top bar.
touch(tile(0), 12);
assert.ok(key(BACK), 'the group opens its card');
const power = key(POWER), lamps = key(LAMPS);
assert.ok(power, 'the power key');
assert.ok(lamps, 'a light group that only dims has the lamps key on its light card');
assert.ok(lamps.x2 <= power.x1 && Math.abs(lamps.y1 - power.y1) < 4, 'the lamps key stands beside the power key, in the bar');
actions();
touch(lamps);
assert.ok(words().includes('Pendant') && words().includes('Spots'), `the lamps key opens the group's page (${words().join(' | ')})`);
assert.deepEqual(actions().filter((a) => a.service), [], 'opening the page sends nothing to Home Assistant');
touch(key(BACK));
touch(key(BACK));
actions();

// A light that is no group: the power key alone.
touch(tile(1), 12);
assert.ok(key(BACK) && key(POWER), 'the light opens its card with the power key');
assert.equal(key(LAMPS), null, 'a light that is no group has no lamps key');
console.log('light group key: the lamps key on a dimming group\'s light card opens its lamps; a single light has none');
