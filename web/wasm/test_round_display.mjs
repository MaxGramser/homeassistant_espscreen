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
const presets = [{ b: 20 }, { b: 40 }, { b: 60 }, { b: 80 }];
const tiles = [...fixture.tiles, { ...both, slot: 6, o: { presets } }, { ...warm, slot: 7 }];
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
const forecasts = () => objects().filter(o => o.forecast).map(o => o.forecast);
const minimum = Math.floor((board.dpi * 7 + 12) / 25);
function touch(x, y, n = 3) { tick(); m._preview_touch(Math.round(x), Math.round(y), 1); tick(n); m._preview_touch(Math.round(x), Math.round(y), 0); tick(); }
const tap = o => touch((o.x1 + o.x2) / 2, (o.y1 + o.y2) / 2);
function key(glyph) {
  const all = objects(), label = all.filter(o => o.type === 'label' && o.text === glyph).at(-1);
  assert.ok(label, `native key ${glyph} exists`);
  return all.find(o => o.id === label.parent);
}
function inside(o) {
  const pad = o.click_pad || 0;
  for (const x of [o.x1 - pad, o.x2 + pad]) for (const y of [o.y1 - pad, o.y2 + pad])
    assert.ok((x - 233) ** 2 + (y - 233) ** 2 <= 222 ** 2, `touch rectangle inside the circle: ${JSON.stringify(o)}`);
}
function target(o) {
  inside(o);
  const pad = o.click_pad || 0;
  assert.ok(o.x2 - o.x1 + 1 + 2 * pad >= minimum && o.y2 - o.y1 + 1 + 2 * pad >= minimum,
    `native finger minimum: ${JSON.stringify(o)}`);
}
function swipe(x1, y1, x2, y2) {
  tick(); m._preview_touch(x1, y1, 1); tick(2);
  for (let i = 1; i <= 8; ++i) { m._preview_touch(Math.round(x1 + (x2 - x1) * i / 8), Math.round(y1 + (y2 - y1) * i / 8), 1); tick(2); }
  m._preview_touch(x2, y2, 0); tick(20);
}
function pageThrough(visit) {
  let count = 0;
  do {
    visit(count++);
    assert.ok(count < 20, 'native pager terminates');
    target(key('\u{F0142}')); target(key('\u{F0141}'));
    if (key('\u{F0142}').disabled) break;
    tap(key('\u{F0142}'));
  } while (count < 20);
  return count;
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
  assert.ok(t.width >= minimum && t.height >= minimum);
}
assert.equal(overview[0].x, board.round_frame.grid.x);
assert.equal(overview[0].y, board.spacing.top);
assert.equal(Math.min(...overview.map(t => t.y)) + Math.max(...overview.map(t => t.y + t.height)), 466,
  'the complete control grid is vertically centered on the physical display');
assert.ok(texts().some(t => t.startsWith('Table l')) && texts().includes('Heating'), `native labels, with native dots for long names: ${texts().join('|')}`);
target(key('\u{F0142}'));
const heading = objects().find(o => o.type === 'label' && o.text === 'Living room');
assert.ok(heading && heading.line_height === 30 && heading.y1 >= board.round_frame.heading.y - 4);
shot('overview');
m._preview_dark(1); tick(); shot('dark'); m._preview_dark(0); tick();

// A short press is still the tile's action; a hold opens the existing native light card without an action.
const first = overview[0];
touch(first.x + first.width / 2, first.y + first.height / 2);
const toggle = actions().at(-1);
assert.equal(toggle?.service, 'light.turn_off');
m._preview_action_response(toggle.call_id, 0, 'Fixture refusal'); tick();
touch(first.x + first.width / 2, first.y + first.height / 2, 24);
assert.deepEqual(actions(), []);
assert.ok(objects().some(o => o.type === 'slider'));
target(key('\u{F004D}')); objects().filter(o => o.type === 'slider').forEach(target);
shot('light'); close();

// All three original colour controls remain reachable through the same page bar as the grid and weather.
assert.equal(m._preview_card(6), 2); tick();
const seenPresets = new Set();
const colourPages = pageThrough(page => {
  const sliders = objects().filter(o => o.type === 'slider');
  assert.equal(sliders.length, page < 3 ? 1 : 0, 'native controls keep their rows through paging');
  sliders.forEach(target);
  texts().filter(t => /^(20|40|60|80)$/.test(t)).forEach(t => seenPresets.add(t));
  if (page >= 3) {
    const all = objects();
    for (const label of all.filter(o => o.type === 'label' && /^(20|40|60|80)$/.test(o.text))) target(all.find(o => o.id === label.parent));
  }
  shot(['colour', 'temperature', 'brightness', 'presets-1', 'presets-2'][page]);
});
assert.equal(colourPages, 5);
assert.deepEqual([...seenPresets].sort(), ['20', '40', '60', '80']);
// Rebuild a page after the preset keys have been deleted, then repaint a new state.
tap(key('\u{F0141}')); tap(key('\u{F0141}'));
receive({ op: 'state', i: 6, entity: both.entity, name: both.name, state: 'on', a: { ...both.a, brightness: 204 } }); tick();
assert.ok(texts().includes('80%'));
close();
assert.equal(m._preview_card(7), 2); tick();
assert.equal(pageThrough(() => objects().filter(o => o.type === 'slider').forEach(target)), 2, 'white-only light keeps both controls');
close();

// The weather's seven daily columns survive the smaller chord; hourly still uses the native chart.
m._preview_card(4); tick();
assert.ok(texts().includes('18.4°'));
shot('weather');
const seen = new Set(), hours = new Set();
pageThrough(page => {
  for (const chart of forecasts()) {
    assert.ok(chart.drawn.length, 'daily forecast actually draws');
    chart.days.forEach(day => { assert.ok(chart.drawn.includes(day), `${day} is painted`); seen.add(day); });
  }
  shot(`weather-${page + 1}`);
});
assert.deepEqual([...seen].sort(), ['Today', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun', 'Mon'].sort(), 'all seven supplied days survive native paging');
const hourly = objects().find(o => o.type === 'label' && o.text === 'Hourly');
assert.ok(hourly); target(objects().find(o => o.id === hourly.parent)); tap(hourly);
pageThrough(page => {
  for (const chart of forecasts()) {
    assert.equal(chart.hourly, true); assert.ok(chart.drawn.length, 'hourly chart actually draws');
    chart.hours.forEach(hour => hours.add(hour));
    shot(`weather-hourly-${page + 1}`);
  }
});
assert.deepEqual([...hours].sort((a, b) => a - b), fixture.tiles[4].x.hours.map(h => h.o), 'all 48 supplied hours survive native paging');
close();

// A short forecast still has a native view; a daily-only provider never offers an empty Hourly page.
const weather = fixture.tiles[4];
const updateWeather = x => receive({ op: 'state', i: 4, entity: weather.entity, name: weather.name, state: weather.state, a: weather.a, x });
updateWeather({ days: weather.x.days.slice(0, 1), hours: weather.x.hours.slice(0, 2) });
m._preview_card(4); tick();
const singleDay = new Set(); pageThrough(() => texts().forEach(t => singleDay.add(t)));
assert.ok(singleDay.has('Today') && singleDay.has('21° / 11°'), 'a single forecast day is retained');
tap(objects().find(o => o.type === 'label' && o.text === 'Hourly'));
const shortHours = new Set(); pageThrough(() => texts().forEach(t => shortHours.add(t)));
for (const hour of ['08:00', '09:00']) assert.ok([...shortHours].some(t => t.includes(hour)), `short forecast retains ${hour}`);
close();
updateWeather({ days: weather.x.days }); m._preview_card(4); tick();
assert.ok(!texts().includes('Hourly'), 'daily-only provider has no Hourly key'); close();
updateWeather(weather.x);

// Grid pages use the same chevrons. A full tile is the normal size option, without a second round-only mode.
// Physical edge coordinates remain 466 x 466, independent of the inset overlay workspace.
swipe(464, 233, 300, 233); assert.equal(m._preview_page(), 1);
tap(key('\u{F0142}')); tick(); assert.equal(m._preview_page(), 2);
shot('glance');
const full = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles;
assert.equal(full.length, 1);
assert.equal(full[0].width, board.round_frame.grid.w);
assert.equal(full[0].height, board.round_frame.grid.h);
assert.equal(2 * full[0].y + full[0].height, 466, 'the Full glance tile keeps the same vertical center');
inside({ x1: full[0].x, y1: full[0].y, x2: full[0].x + full[0].width - 1, y2: full[0].y + full[0].height - 1 });
// The native Dock is on LVGL's top layer. Its resting drawer and page targets fit the circular glass.
const dots = objects().find(o => o.clickable && o.x1 > 175 && o.x2 < 290 && o.y1 === board.round_frame.footer.y);
assert.ok(dots, 'native page dots open the Dock'); target(dots); tap(dots); tick(20);
const layer = objects().filter(o => o.parent === -1).at(-1);
const dock = objects().find(o => o.parent === layer.id);
const drawer = objects().find(o => o.parent === dock.id);
inside(drawer); shot('dock');
const pick = objects().find(o => o.id > drawer.id && o.clickable && o.x1 > 80 &&
  objects().some(label => label.parent === o.id && label.type === 'label' && label.text === 'Living room'));
assert.ok(pick, 'Dock keeps a native page target'); target(pick); tap(pick); tick(20);
assert.ok(!objects().some(o => o.id === drawer.id && o.x1 === drawer.x1 && o.y1 === drawer.y1 && o.y2 === drawer.y2));
console.log('PASS round firmware: canonical devices, actions/hold, badge/frame geometry, four/full tiles, safe touch rectangles, light/preset paging, seven days/48 hours, physical edge swipes, Dock and light/dark');
