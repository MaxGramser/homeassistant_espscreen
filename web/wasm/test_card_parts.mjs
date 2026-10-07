// A card that paints itself (docs/CARD_PARTS.md) must look exactly as the same card built anew. Opens each card from
// the real firmware, sends it a new state that keeps its shape, and wants: the card not built again, and the glass
// pixel for pixel the same as the card built from scratch with that state.
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
const climate = { entity: 'climate.living', name: 'Living', state: 'heat',
  a: { hvac_modes: ['off', 'heat', 'cool', 'auto', 'dry', 'fan_only'], temperature: 21, current_temperature: 19.5, min_temp: 7,
       max_temp: 35, target_temp_step: 0.5, fan_modes: ['low', 'medium', 'high'], fan_mode: 'low', swing_modes: ['off', 'on'],
       swing_mode: 'off', hvac_action: 'heating', supported_features: 425 } };
const media = { entity: 'media_player.kitchen', name: 'Kitchen', state: 'playing',
  a: { volume_level: 0.4, is_volume_muted: false, supported_features: 252349 },
  x: { title: 'Song', artist: 'Band', album: 'Album', dur: 200, pos: 20, at: 1789401800, sh: 0, rp: 'off' } };
const light = { entity: 'light.desk', name: 'Desk', state: 'on', a: { brightness: 128, supported_color_modes: ['brightness'], color_mode: 'brightness' } };
const cover = { entity: 'cover.blind', name: 'Blind', state: 'open', a: { current_position: 70, supported_features: 15 } };
const select = { entity: 'select.speed', name: 'Speed', state: 'Slow', a: { options: ['Slow', 'Medium', 'Fast'] }, x: { options: ['Slow', 'Medium', 'Fast'] } };
const remote = { entity: 'remote.hub', name: 'Hub', state: 'on', a: { activity_list: ['TV', 'Music'], current_activity: 'TV', supported_features: 4 }, x: { options: ['TV', 'Music'], act: 'TV' } };
const fan = { entity: 'fan.attic', name: 'Attic', state: 'on', a: { percentage: 66, percentage_step: 33, supported_features: 1 } };
const timer = { entity: 'timer.tea', name: 'Tea', state: 'active', a: { duration: '0:05:00', remaining: '0:04:00' } };
const vacuum = { entity: 'vacuum.robot', name: 'Robot', state: 'docked', a: { battery_level: 80, fan_speed: 'balanced', fan_speed_list: ['quiet', 'balanced', 'turbo'], supported_features: 14204 } };
const lock = { entity: 'lock.front', name: 'Front', state: 'locked', a: { changed_by: 'Keypad', supported_features: 1 } };
const alarm = { entity: 'alarm_control_panel.home', name: 'Home', state: 'disarmed', a: { code_format: 'number', changed_by: 'Keypad', code_arm_required: true, supported_features: 63 } };
const CASES = [
  ['climate: another mode', climate, { state: 'cool', a: { ...climate.a, hvac_action: 'cooling' } }],
  ['climate: fan, swing and setpoint', climate, { a: { ...climate.a, fan_mode: 'high', swing_mode: 'on', temperature: 22.5 } }],
  ['climate: off', climate, { state: 'off', a: { ...climate.a, hvac_action: 'off' } }],
  ['media: paused, muted, shuffled', media, { state: 'paused', a: { ...media.a, is_volume_muted: true, volume_level: 0.7 }, x: { ...media.x, sh: 1, rp: 'one' } }],
  ['media: another track', media, { x: { ...media.x, title: 'Other', artist: 'Singer' } }],
  // A new track brings its picture, its colour and its length with it: painted, never built (firmware 0.52.0, #177).
  ['media: a new track, its cover colour and length', media, { x: { ...media.x, title: 'Other', artist: 'Singer', pic: 'b2c3', g: '461511,461511', dur: 260, pos: 0 } }],
  ['media: between two tracks', media, { state: 'idle', x: { sh: 0, rp: 'off' } }],
  ['light: dimmer', light, { a: { ...light.a, brightness: 40 } }],
  ['light: off', light, { state: 'off', a: { supported_color_modes: ['brightness'] } }],
  ['cover: moving', cover, { state: 'closing', a: { ...cover.a, current_position: 35 } }],
  ['select: another option', select, { state: 'Fast' }],
  ['remote: another activity', remote, { a: { ...remote.a, current_activity: 'Music' }, x: { ...remote.x, act: 'Music' } }],
  ['remote: off', remote, { state: 'off' }],
  ['fan: slower', fan, { a: { ...fan.a, percentage: 33 } }],
  ['timer: paused', timer, { state: 'paused' }],
  ['vacuum: suction', vacuum, { a: { ...vacuum.a, fan_speed: 'turbo' } }],
  ['lock: locked by someone else', lock, { a: { ...lock.a, changed_by: 'App' } }],
  ['alarm: disarmed by someone else', alarm, { a: { ...alarm.a, changed_by: 'App' } }],
];

async function screen(shape) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(shape.width, shape.height, shape.dpi, shape.columns, shape.rows), 1);
  let ms = 0;
  const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  const frame = () => { const p = m._preview_frame(); return Buffer.from(m.HEAPU8.slice(p, p + shape.width * shape.height * 4)); };
  return { m, tick, frame };
}
function difference(a, b, width) {
  let count = 0, x0 = 1e9, y0 = 1e9, x1 = -1, y1 = -1;
  for (let i = 0; i < a.length; i += 4) {
    if (a[i] === b[i] && a[i + 1] === b[i + 1] && a[i + 2] === b[i + 2]) continue;
    const p = i / 4, x = p % width, y = Math.floor(p / width);
    count++; x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
  }
  return count ? `${count} pixels differ in (${x0},${y0})-(${x1},${y1})` : '';
}

let checked = 0;
for (const shape of SHAPES) {
  for (const [name, tile, change] of CASES) {
    const { m, tick, frame } = await screen(shape);
    const receive = connection(m);
    configure(receive, 'Cards', 1, [{ ...tile, slot: 0, o: {} }]);
    tick();
    assert.equal(m._preview_card(0), 1, `${shape.key} ${name}: the card paints itself`);
    tick();
    const builds = m._preview_card_builds();
    receive({ op: 'state', i: 0, entity: tile.entity, name: tile.name, state: change.state ?? tile.state, a: change.a ?? tile.a, x: change.x ?? tile.x });
    tick();
    assert.equal(m._preview_card_builds(), builds, `${shape.key} ${name}: the new state was painted, not built`);
    const painted = frame();
    m._preview_card(0);
    tick();
    const diff = difference(painted, frame(), shape.width);
    assert.equal(diff, '', `${shape.key} ${name}: painted in place differs from built anew: ${diff}`);
    checked++;
  }
}
// A lock or an alarm panel that changes its state is built again, as it always was, with its animations: the
// security cards keep every state in their shape (docs/CARD_PARTS.md, "Security cards").
for (const [name, tile, state] of [['lock', lock, 'unlocking'], ['alarm', alarm, 'arming']]) {
  const { m, tick } = await screen(SHAPES[1]);
  const receive = connection(m);
  configure(receive, 'Cards', 1, [{ ...tile, slot: 0, o: {} }]);
  tick();
  m._preview_card(0);
  tick();
  const builds = m._preview_card_builds();
  receive({ op: 'state', i: 0, entity: tile.entity, name: tile.name, state, a: tile.a });
  tick();
  assert.ok(m._preview_card_builds() > builds, `${name}: a new state builds the card again`);
}
console.log(`PASS ${checked} cards: painted in place, pixel for pixel the card built anew`);
