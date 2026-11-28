// The climate card's state line ("Heat · Now 65° · 48%") stands clear of the setpoint card under it. The layout
// reserves the line's height (climate_card::Metrics::status_h); until dev it was a fixed 25 px while the line is
// written in the card's text font, taller on the larger glass, so a thermostat with many modes and a fan row ran its
// state line into the card once the gaps had given way. On the smallest glass, the Guition, the dense P4 and Tab5,
// and the largest glass.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const SHAPES = [
  { key: 'cyd', width: 320, height: 240, dpi: 143, columns: 3, rows: 2 },
  { key: 'guition', width: 480, height: 480, dpi: 170, columns: 2, rows: 3 },
  // The dense glass where the line ran into the card: the Waveshare P4 and the Tab5.
  { key: 'wavesharep4', width: 720, height: 720, dpi: 255, columns: 2, rows: 3 },
  { key: 'tab5', width: 1280, height: 720, dpi: 294, columns: 3, rows: 3 },
  { key: 'jc8012p4a1', width: 1280, height: 800, dpi: 149, columns: 5, rows: 5 },
];
// A heat pump with every mode and a fan row: the card that has to give up the most room.
const heatPump = { entity: 'climate.heat_pump', name: 'Heat pump', state: 'heat', slot: 0, o: {}, unit: '°F',
  a: { supported_features: 9, hvac_modes: ['off', 'heat_cool', 'cool', 'heat', 'fan_only', 'dry'],
       fan_modes: ['auto', 'low', 'medium', 'high'], fan_mode: 'low', temperature: 70, current_temperature: 65,
       current_humidity: 48, min_temp: 45, max_temp: 95, target_temp_step: 1, hvac_action: 'heating' } };

for (const shape of SHAPES) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(shape.width, shape.height, shape.dpi, shape.columns, shape.rows), 1);
  const receive = connection(m);
  configure(receive, 'Room', 1, [heatPump]);
  let ms = 0;
  const tick = (n = 4) => { for (let i = 0; i < n; i++) { ms += 32; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  const objects = () => JSON.parse(m.ccall('preview_layout', 'string', [], [])).objects;
  tick(10);
  const tile = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles[0];
  m._preview_touch(tile.x + tile.width / 2, tile.y + tile.height / 2, 1); tick(2);
  m._preview_touch(tile.x + tile.width / 2, tile.y + tile.height / 2, 0); tick(6);

  const all = objects();
  const labels = all.filter((o) => o.type === 'label');
  // The card's own labels: the page stays under the card, and the tile's own line there says "Now" too since it rolls
  // and keeps all its words. A tile's labels belong to its card on the page (`card` 0 and up), the open card's to none.
  const status = labels.findLast((o) => o.card === -1 && /Now/.test(o.text ?? ''));
  if (!status) {  // glass with no room for the line puts the state under the number instead
    assert.ok(labels.some((o) => /Heat/.test(o.text ?? '')), `${shape.key}: the state somewhere (${labels.map((o) => o.text).join(' | ')})`);
    console.log(`  ${shape.key}: the state under the number`);
    continue;
  }
  const number = labels.findLast((o) => o.text === '70°');
  assert.ok(number, `${shape.key}: the setpoint drawn`);
  // The setpoint card: the smallest object that holds the number and both its keys, wider than the number alone.
  const holds = (o) => o.type !== 'label' && o.x1 <= number.x1 && o.x2 >= number.x2 && o.y1 <= number.y1 && o.y2 >= number.y2;
  const area = (o) => (o.x2 - o.x1) * (o.y2 - o.y1);
  // The number's label may be as wide as its row; its text is what the card is wider than.
  const card = all.filter((o) => holds(o) && o.x2 - o.x1 >= 2 * (number.text_width ?? number.x2 - number.x1) && o.x2 - o.x1 < shape.width - 4)
    .sort((a, b) => area(a) - area(b))[0];
  assert.ok(card, `${shape.key}: the setpoint card found`);
  const air = card.y1 - status.y2;
  console.log(`  ${shape.key}: state line ${status.y1}-${status.y2}, card from ${card.y1}, air ${air}`);
  assert.ok(air >= 1, `${shape.key}: the state line (to ${status.y2}) runs into the setpoint card (from ${card.y1})`);
}
console.log(`PASS climate detail: the state line clear of the setpoint card on ${SHAPES.map((s) => s.key).join(', ')}`);
