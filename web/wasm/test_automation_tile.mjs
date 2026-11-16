// An automation as a tile (firmware 0.7.0, GitHub #62), read from the real firmware, no line of it quoted: Home
// Assistant's icons (automation/icons.json: robot, robot-off, robot-confused); a tap switches it, and a tile set to
// run runs its actions with automation.trigger and the entity alone (more-info-automation.ts: skip_condition true is
// Home Assistant's default); a run button is coloured while its actions run (`run` from the app), grey otherwise.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const ROBOT = 0xf06a9, ROBOT_OFF = 0xf16a7, ROBOT_CONFUSED = 0xf169f;
const auto = (entity, state, o = {}, x) => ({ entity, name: entity.split('.')[1], state, o, a: {}, ...(x ? { x } : {}) });
const TILES = [auto('automation.on', 'on'), auto('automation.off', 'off'), auto('automation.button', 'on', { tap: 'run' }), auto('automation.busy', 'on', { tap: 'run' }, { run: true }), auto('automation.gone', 'unavailable')].map((t, slot) => ({ ...t, slot }));

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(1280, 800, 149, 4, 3), 1);
let ms = 0;
const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
configure(connection(m), 'Automations', 1, TILES);
tick();
const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
const icon = (slot) => layout().objects.find((o) => o.card === slot && o.type === 'label' && o.icon);
const tap = (slot) => {
  const l = layout(), b = l.objects.find((o) => o.id === l.cards[slot].object), x = (b.x1 + b.x2) / 2, y = (b.y1 + b.y2) / 2;
  tick(10); m._preview_touch(x, y, 1); tick(2); m._preview_touch(x, y, 0); tick(8);
  const out = []; for (let a = m.ccall('preview_next_action', 'string', [], []); a; a = m.ccall('preview_next_action', 'string', [], [])) out.push(JSON.parse(a));
  return out.map((a) => [a.service, a.data]);
};
const grey = (rgb) => { const r = rgb >> 16 & 255, g = rgb >> 8 & 255, b = rgb & 255; return Math.max(r, g, b) - Math.min(r, g, b) < 24; };

assert.equal(icon(0).text.codePointAt(0), ROBOT, 'on: mdi:robot');
assert.equal(icon(1).text.codePointAt(0), ROBOT_OFF, 'off: mdi:robot-off');
assert.equal(icon(4).text.codePointAt(0), ROBOT_CONFUSED, 'unavailable: mdi:robot-confused');
assert.ok(!grey(icon(0).color) && grey(icon(1).color), 'coloured while on, grey while off');
assert.ok(grey(icon(2).color), 'a run button is grey while nothing runs, though the automation is on');
assert.ok(!grey(icon(3).color), 'and coloured while its actions run');

assert.deepEqual(tap(0), [['automation.turn_off', { entity_id: 'automation.on' }]], 'a tap switches it off');
assert.deepEqual(tap(2), [['automation.trigger', { entity_id: 'automation.button' }]], 'a run button runs its actions, the entity alone');

console.log('automation tile: icons, colours of a switch and of a run button, a tap switches, a run button runs');
