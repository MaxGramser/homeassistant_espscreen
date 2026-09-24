// Runs the actual WebAssembly renderer, without Vue or a second tile renderer.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';

const width = Number(process.env.PREVIEW_WIDTH || 480), height = Number(process.env.PREVIEW_HEIGHT || 480);
const columns = Number(process.env.PREVIEW_COLUMNS || 2), rows = Number(process.env.PREVIEW_ROWS || 3);
const dpi = Number(process.env.PREVIEW_DPI || 170);
const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(width, height, dpi, columns, rows), 1);
let ms = 0;
function tick(delta = 32) { ms += delta; m._preview_time(ms, 1789401840, 7200); m._preview_render(); }
function receive(packet) {
  const result = m.ccall('preview_receive', 'string', ['string'], [JSON.stringify(packet)]);
  assert.ok(!/invalid|error/i.test(result), result);
  return result;
}
function info() { return JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])); }
function frame() { const p = m._preview_frame(); return new Uint8Array(m.HEAPU8.subarray(p, p + width * height * 4)); }
function tap(x, y) {
  tick(250); m._preview_touch(x, y, 1); tick(120); m._preview_touch(x, y, 0); tick(300);
}
const cells = columns * rows;
const messages = process.env.PREVIEW_MESSAGES ? JSON.parse(readFileSync(process.env.PREVIEW_MESSAGES)) : [
  { v: 1, op: 'layout', title: 'Renderer test', entities: ['weather.test', 'screen.clock', 'light.yellow', 'light.green'], slots: [0, columns, cells, cells + 1], pages: 3, swipe_pages: true },
  { v: 1, op: 'state', i: 0, entity: 'weather.test', name: 'Weather', state: 'partlycloudy', a: { temperature: 19, temperature_unit: '°C', supported_features: 3 }, o: { display: 'forecast', size: 'wide' }, x: { days: [
    { d: 'Tue', c: 'sunny', h: 22, l: 12, p: 20 }, { d: 'Wed', c: 'rainy', h: 18, l: 11, p: 70 },
    { d: 'Thu', c: 'cloudy', h: 20, l: 13, p: 30 }, { d: 'Fri', c: 'sunny', h: 21, l: 14, p: 10 },
  ] } },
  { v: 1, op: 'state', i: 1, entity: 'screen.clock', name: 'Clock', state: '', a: {}, o: { display: 'digital', size: 'wide' } },
  { v: 1, op: 'state', i: 2, entity: 'light.yellow', name: 'Yellow', state: 'on', a: { brightness: 200 }, o: { background: 'yellow' } },
  { v: 1, op: 'state', i: 3, entity: 'light.green', name: 'Green', state: 'on', a: { brightness: 200 }, o: { background: 'green' } },
];
for (const packet of messages) receive(packet);
tick();
const first = info(); console.log(JSON.stringify(first));
const expectedSource = readFileSync(new URL('generated/firmware_renderer_manifest.h', import.meta.url), 'utf8').match(/SHA256 "([a-f0-9]+)"/)[1];
assert.equal(first.source, expectedSource, 'the WASM binary must be rebuilt after its source manifest changes');
assert.equal(first.tiles.length, 2, 'both first-page tiles must be visible');
assert.equal(first.tiles[0].mode, 'forecast');
const [a, b] = first.tiles;
assert.ok(a.y + a.height <= b.y || b.y + b.height <= a.y || a.x + a.width <= b.x || b.x + b.width <= a.x, 'tiles must not overlap');
assert.ok(a.width > width * 0.6 || columns > 2, 'forecast must span its grid columns');
const original = frame();
const inForecast = first.icons.filter(icon => icon.y >= a.y && icon.y + icon.height <= a.y + a.height);
assert.ok(inForecast.length >= 4, 'forecast must have current and upcoming-day icons');
for (const icon of inForecast) {
  let ink = 0;
  for (let y = Math.max(0, icon.y); y < Math.min(height, icon.y + icon.height); ++y) {
    for (let x = Math.max(0, icon.x); x < Math.min(width, icon.x + icon.width); ++x) {
      const p = (y * width + x) * 4;
      if (original[p] < 120 && original[p + 1] < 120 && original[p + 2] < 120) ink++;
    }
  }
  assert.ok(ink > 10, 'each forecast glyph must leave visible ink inside its LVGL bounds');
}
if (process.env.PREVIEW_OUTPUT) writeFileSync(process.env.PREVIEW_OUTPUT, original);
tap(width - 30, height - 22);
assert.equal(m._preview_page(), 1, 'next button');
assert.equal(info().tiles.length, 2, 'both second-page tiles must be visible');
const second = frame();
assert.notDeepEqual(second, original, 'page two must replace page one');
if (!process.env.PREVIEW_MESSAGES) {
  const [left, right] = info().tiles;
  const pixel = tile => second.slice(((tile.y + 8) * width + tile.x + Math.floor(tile.width / 2)) * 4).slice(0, 4);
  assert.notDeepEqual(pixel(left), pixel(right), 'green and yellow card backgrounds must differ');
}
tap(30, height - 22);
assert.equal(m._preview_page(), 0, 'previous button');
assert.deepEqual(info().tiles, first.tiles, 'page one geometry must survive a round trip');
assert.deepEqual(frame(), original, 'returning home restores the complete framebuffer');
// Raw contact motion goes to the firmware edge-swipe detector.
tick(250); m._preview_touch(width - 2, Math.floor(height / 2), 1); tick(32);
m._preview_touch(width - 140, Math.floor(height / 2), 1); tick(32);
m._preview_touch(width - 140, Math.floor(height / 2), 0); tick(500);
assert.equal(m._preview_page(), 1, 'firmware edge swipe');
if (!process.env.PREVIEW_MESSAGES) {
  const tile = info().tiles[0];
  const touch = () => tap(tile.x + Math.floor(tile.width / 2), tile.y + Math.floor(tile.height / 2));
  const nextAction = () => JSON.parse(m.ccall('preview_next_action', 'string', [], []));
  touch();
  const request = nextAction();
  assert.equal(request.service, 'light.toggle', 'the command comes from the firmware tap route');
  assert.deepEqual(request.data, { entity_id: 'light.yellow' }, 'StringRef fields must survive the firmware call stack');
  assert.equal(request.event, false);
  assert.ok(request.call_id > 0, 'the firmware must ask for a real action response');
  assert.equal(m.ccall('preview_next_action', 'string', [], []), '', 'one touch emits one command');
  assert.equal(info().tiles[0].state, 'off', 'firmware optimistic feedback');
  m.ccall('preview_action_response', null, ['number', 'number', 'string'], [request.call_id, 1, '']);
  receive({ ...messages[3], state: 'off' });
  tick(4000);
  assert.equal(info().tiles[0].state, 'off', 'HA confirmation persists past the firmware timeout');
  assert.equal(info().tiles[0].pending, false);
  touch();
  const refused = nextAction();
  assert.equal(info().tiles[0].state, 'on');
  m.ccall('preview_action_response', null, ['number', 'number', 'string'], [refused.call_id, 0, 'Device unavailable']);
  tick();
  assert.equal(info().tiles[0].state, 'off', 'a refusal uses the firmware rollback');
  assert.equal(info().tiles[0].pending, false);
}
console.log(`PASS ${width}x${height} ${columns}x${rows}: firmware forecast, two tiles, backgrounds, navigation, edge swipe and command responses`);
