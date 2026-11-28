// A change of look draws again what was drawn (firmware 0.2.54, docs/THEME.md): a screen switched to Dark mode is,
// pixel for pixel, the screen that booted in it. Read from the real firmware's frame, no line of it quoted: a page of
// computed cards (the sun path keeps Home Assistant's sunny fill, the thermostat, the blind, a coloured lamp) and the
// settings page with its switches, whose knobs stand where the size they were given puts them.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const W = 1280, H = 800, NOW = 1789401840, SUNNY = 0xffb300;
const TILES = [
  { entity: 'sun.sun', name: 'Sun', state: 'above_horizon', slot: 0, o: { size: 'wide', display: 'sunpath' }, a: { elevation: 30 }, x: { rise: '07:12', set: '19:40' } },
  { entity: 'climate.living', name: 'Living', state: 'heat', slot: 2, o: { size: 'wide' },
    a: { hvac_modes: ['off', 'heat'], temperature: 20, current_temperature: 19, min_temp: 7, max_temp: 30, target_temp_step: 0.5 } },
  { entity: 'cover.blind', name: 'Blind', state: 'open', slot: 4, o: { size: 'wide' }, a: { supported_features: 15, current_position: 60 } },
  { entity: 'light.desk', name: 'Desk', state: 'on', slot: 6, o: { size: 'wide' }, a: { supported_color_modes: ['hs'], brightness: 128, hs_color: [200, 80] } },
  { entity: 'screen.settings', name: '', state: 'ok', slot: 8, o: {}, a: {} },
];

// One screen: `dark` at boot (before the layout) or switched once everything is drawn; `settings` opens the settings
// page and its Brightness page first.
async function frame({ dark, booted, settings }) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(W, H, 149, 4, 3), 1);
  let ms = 0;
  const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, NOW, 7200); m._preview_render(); } };
  const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
  const press = (o) => { tick(10); const x = (o.x1 + o.x2) / 2, y = (o.y1 + o.y2) / 2; m._preview_touch(x, y, 1); tick(2); m._preview_touch(x, y, 0); tick(20); };
  if (dark && booted) m._preview_dark(1);
  configure(connection(m), 'Look', 1, TILES);
  tick(20);
  if (settings) {
    let l = layout();
    press(l.objects.find((o) => o.id === l.cards[l.cards.findIndex((c) => c.entity === 'screen.settings')].object));
    l = layout();
    let row = l.objects.find((o) => o.card < 0 && o.text === 'Brightness');
    while (row && !row.clickable) row = l.objects.find((p) => p.id === row.parent);
    press(row);
    assert.ok(layout().objects.some((o) => o.card < 0 && o.text === 'Dark mode'), 'the Brightness page with its switches is open');
  }
  if (dark && !booted) { m._preview_dark(1); tick(20); }
  const sun = layout().objects.filter((o) => o.card === 0 && o.bg === SUNNY);
  const p = m._preview_frame();
  return { pixels: new Uint8Array(m.HEAPU8.subarray(p, p + W * H * 4)), sun: sun.length };
}
const differ = (a, b) => { let n = 0; for (let i = 0; i < a.length; i += 4) if (a[i] !== b[i] || a[i + 1] !== b[i + 1] || a[i + 2] !== b[i + 2]) ++n; return n; };

for (const settings of [false, true]) {
  const where = settings ? 'the settings page' : 'a page of cards';
  const light = await frame({ dark: false, settings }), booted = await frame({ dark: true, booted: true, settings });
  const switched = await frame({ dark: true, booted: false, settings });
  assert.ok(differ(light.pixels, booted.pixels) > W * H / 4, `${where}: Dark mode changes the screen`);
  assert.equal(differ(switched.pixels, booted.pixels), 0, `${where}: switched to Dark mode is the screen that booted in it, pixel for pixel`);
  if (!settings) assert.ok(booted.sun > 0 && switched.sun === booted.sun, 'the sun path keeps its sunny fill after the change');
}

console.log('dark switch: a page of cards and the settings page, switched equals booted, pixel for pixel');
