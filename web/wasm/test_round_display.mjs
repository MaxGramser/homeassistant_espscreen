// Real firmware, real touches and the repository's usual synthetic Home Assistant devices.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import createModule from '../src/wasm/firmware_preview.js';
import { connection } from './test_protocol.mjs';
import { both, warm } from './light_fixtures.mjs';

const fixture = JSON.parse(execFileSync(process.env.PYTHON || 'python3',
  [fileURLToPath(new URL('../../tools/render/round.py', import.meta.url)), '--fixture'], { encoding: 'utf8' }));
const board = JSON.parse(readFileSync(new URL('../../screen_manager/app/boards.json', import.meta.url))).lilygo175;
const m = await createModule({ wasmBinary: readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url)) });
m._preview_shape(1);
assert.equal(m._preview_init(466, 466, 266, 2, 2), 1);
const receive = connection(m);
const tiles = [...fixture.tiles, { ...both, slot: 6 }, { ...warm, slot: 7 }];
receive({ op: 'begin', title: 'Living room', pages: 3, tiles: tiles.length, home: 0, ...fixture.region });
for (let p = 0; p < 3; ++p) receive({ op: 'page', p, id: (p + 1).toString(16).padStart(16, '0'),
  title: '', home_control: true, excluded: false, items: fixture.items });
tiles.forEach((tile, i) => receive({ ...tile, i, op: 'tile' }));
receive({ op: 'commit' });
let ms = 0;
function tick(n = 8) { for (let i = 0; i < n; ++i) { m._preview_time(ms += 32, 1789459680, 7200); m._preview_render(); } }
const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
const objects = () => layout().objects;
const texts = () => objects().filter(o => o.type === 'label').map(o => o.text);
function touch(x, y, n = 3) { tick(); m._preview_touch(Math.round(x), Math.round(y), 1); tick(n); m._preview_touch(Math.round(x), Math.round(y), 0); tick(); }
const tap = o => touch((o.x1 + o.x2) / 2, (o.y1 + o.y2) / 2);
function key(glyph) {
  const all = objects(), label = all.filter(o => o.type === 'label' && o.text === glyph).at(-1);
  assert.ok(label, `native key ${glyph} exists`);
  return all.find(o => o.id === label.parent);
}
function inside(o) {
  for (const x of [o.x1, o.x2]) for (const y of [o.y1, o.y2])
    assert.ok((x - 233) ** 2 + (y - 233) ** 2 <= 222 ** 2, `touch rectangle inside the circle: ${JSON.stringify(o)}`);
}
function shot(name) {
  if (!process.env.ROUND_RENDER_DIR) return;
  const p = m._preview_frame();
  writeFileSync(`${process.env.ROUND_RENDER_DIR}/lilygo175-${name}.rgba`, m.HEAPU8.subarray(p, p + 466 * 466 * 4));
}
function close() { tap(key('\u{F004D}')); }
function actions() {
  const out = [];
  for (let a; (a = m.ccall('preview_next_action', 'string', [], []));) out.push(JSON.parse(a));
  return out;
}
tick(20);
const overview = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles;
assert.equal(overview.length, 4);
for (const t of overview) {
  inside({ x1: t.x, y1: t.y, x2: t.x + t.width - 1, y2: t.y + t.height - 1 });
  assert.ok(t.width >= 75 && t.height >= 75);
}
assert.equal(overview[0].x, board.round_frame.grid.x);
assert.equal(overview[0].y, board.spacing.top);
assert.ok(texts().includes('Table lamp') && texts().includes('Heating'), `native labels fit: ${texts().join('|')}`);
inside(key('\u{F0142}'));
shot('overview');
m._preview_dark(1); tick(); shot('dark'); m._preview_dark(0); tick();

// A short press is still the tile's action; a hold opens the existing native light card without an action.
const first = overview[0];
touch(first.x + first.width / 2, first.y + first.height / 2);
assert.equal(actions().at(-1)?.service, 'light.toggle');
touch(first.x + first.width / 2, first.y + first.height / 2, 24);
assert.deepEqual(actions(), []);
assert.ok(objects().some(o => o.type === 'slider'));
inside(key('\u{F004D}')); shot('light'); close();

// All three original colour controls remain reachable through the same page bar as the grid and weather.
assert.equal(m._preview_card(6), 2); tick();
for (let page = 0; page < 3; ++page) {
  const sliders = objects().filter(o => o.type === 'slider');
  assert.equal(sliders.length, 1, 'one finger-sized native row per page');
  inside(sliders[0]); inside(key('\u{F0142}'));
  shot(['colour', 'temperature', 'brightness'][page]);
  if (page < 2) tap(key('\u{F0142}'));
}
close();

// The weather's seven daily columns survive the smaller chord; hourly still uses the native chart.
m._preview_card(4); tick();
assert.ok(texts().includes('18.4°'));
shot('weather');
const seen = new Set();
for (let page = 0; page < 5; ++page) {
  texts().forEach(t => seen.add(t));
  inside(key('\u{F0142}'));
  shot(`weather-${page + 1}`);
  tap(key('\u{F0142}'));
}
for (const day of fixture.tiles[4].x.days) assert.ok([...seen].some(t => t.includes(day.d)), `forecast retains ${day.d}`);
const hourly = objects().find(o => o.type === 'label' && o.text === 'Hourly');
assert.ok(hourly); tap(hourly); shot('weather-hourly');
close();

// Grid pages use the same chevrons. A full tile is the normal size option, without a second round-only mode.
tap(key('\u{F0142}')); tick(); assert.equal(m._preview_page(), 1);
tap(key('\u{F0142}')); tick(); assert.equal(m._preview_page(), 2);
shot('glance');
const full = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles;
assert.equal(full.length, 1);
assert.equal(full[0].width, board.round_frame.grid.w);
assert.equal(full[0].height, board.round_frame.grid.h);
inside({ x1: full[0].x, y1: full[0].y, x2: full[0].x + full[0].width - 1, y2: full[0].y + full[0].height - 1 });
console.log('PASS round firmware: canonical demo, native actions/hold, four tiles/full tile, safe keys, colour paging, daily/hourly weather, light/dark');
