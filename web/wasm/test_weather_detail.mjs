// The weather card's full view looks the same whatever the first cell shows (GitHub #52, firmware 0.43.0). The card
// took its small text from the value label of the first cell as that label was dressed at the moment, so a big value
// there (the watch digits, or the setpoint digits that carry no letters) blew up the hours, the rain and the lows on
// the 10.1 inch, and the rain ended in dots. Opens the card from the real firmware on the smallest, a middle and the
// largest glass, with a light, a big number and a big word in the first cell, and wants the same picture three times.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const SHAPES = [
  { key: 'cyd', width: 320, height: 240, dpi: 143, columns: 3, rows: 2 },
  { key: 'guition', width: 480, height: 480, dpi: 170, columns: 3, rows: 3 },
  { key: 'jc8012p4a1', width: 1280, height: 800, dpi: 149, columns: 5, rows: 4 },
];
const weather = {
  entity: 'weather.home', name: 'Weather', state: 'rainy',
  a: { temperature: 18, temperature_unit: '°C', humidity: 88, wind_speed: 9, wind_speed_unit: 'km/h', supported_features: 3 },
  o: { display: 'forecast', size: 'wide' },
  x: {
    days: [
      { d: 'Fri', c: 'lightning-rainy', h: 24, l: 14, r: 9.9 }, { d: 'Sat', c: 'lightning-rainy', h: 23, l: 16, r: 5.5 },
      { d: 'Sun', c: 'rainy', h: 26, l: 17, r: 2 }, { d: 'Mon', c: 'rainy', h: 24, l: 18, r: 8.9 },
      { d: 'Tue', c: 'rainy', h: 23, l: 17, r: 6.3 },
    ],
    hours: ['18:00', '19:00', '20:00', '21:00', '22:00', '23:00'].map((t, i) =>
      ({ t, c: i < 5 ? 'rainy' : 'cloudy', h: i ? 17 : 18, r: i < 5 ? (i ? 0.1 : 0.4) : 0 })),
  },
};
const FIRST = {
  light: { entity: 'light.kitchen', name: 'Kitchen', state: 'on', a: { brightness: 200 }, o: {} },
  'big number': { entity: 'sensor.living_temperature', name: 'Living room', state: '21.4',
    a: { unit_of_measurement: '°C', device_class: 'temperature', state_class: 'measurement' }, o: { display: 'watch' } },
  'big word': { entity: 'sensor.washer_status', name: 'Washer', state: 'Washing', a: {}, o: { display: 'watch' } },
};

async function detail(shape, first) {
  const { width, height } = shape;
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(width, height, shape.dpi, shape.columns, shape.rows), 1);
  let ms = 0;
  const tick = (delta = 32) => { ms += delta; m._preview_time(ms, 1789401840, 7200); m._preview_render(); };
  configure(connection(m), 'Home', 1, [{ ...first, slot: 0 }, { ...weather, slot: 1 }]);
  for (let i = 0; i < 12; i++) tick(64);
  const card = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles.find(tile => tile.mode === 'forecast');
  assert.ok(card, `${shape.key}: the weather tile shows its forecast`);
  const x = card.x + Math.floor(card.width / 2), y = card.y + Math.floor(card.height / 2);
  tick(250); m._preview_touch(x, y, 1); tick(120); m._preview_touch(x, y, 0);
  for (let i = 0; i < 12; i++) tick(64);
  const p = m._preview_frame();
  return Buffer.from(m.HEAPU8.slice(p, p + width * height * 4));
}

for (const shape of SHAPES) {
  const plain = await detail(shape, FIRST.light);
  for (const [name, first] of Object.entries(FIRST)) {
    if (first === FIRST.light) continue;
    assert.ok(plain.equals(await detail(shape, first)),
      `${shape.key}: the weather card's full view changes with a ${name} in the first cell`);
  }
}
console.log(`PASS weather detail: the same full view whatever the first cell shows, on ${SHAPES.map(s => s.key).join(', ')}`);
