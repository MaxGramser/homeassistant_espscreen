// The frame round the tiles, read from the real firmware, no line of it quoted: nothing stands on the glass before a
// layout arrives; one margin all round (firmware 0.14.0), the top bar's title, the tiles and the ink of the page keys'
// chevrons all GRID_MARGIN from the edges; the page bar with its dots only when there is more than one page; and a
// tap's guard (docs/OPTIMISTIC.md): a tile that switches takes every clean tap, where the 600 ms guard of any other
// tap would drop the second (TouchGuard::accept and accept_repeat: tests/test_screen_input.cpp).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const boards = JSON.parse(readFileSync(new URL('../../screen_manager/app/boards.json', import.meta.url)));
const W = 800, H = 480, PREVIOUS = 0xf0141, NEXT = 0xf0142;
// The 4.3-inch Waveshare's glass and grid: the margin its look states.
const MARGIN = boards.waveshare43.spacing.margin;
const TILES = [{ entity: 'switch.a', name: 'A', state: 'on', slot: 0, o: {}, a: {} }, { entity: 'scene.b', name: 'B', state: '2026-01-01T00:00:00+00:00', slot: 1, o: {}, a: {} },
  { entity: 'light.c', name: 'C', state: 'off', slot: 2, o: {}, a: {} }, { entity: 'script.e', name: 'E', state: 'off', slot: 3, o: {}, a: {} },
  { entity: 'button.f', name: 'F', state: '2026-01-01T00:00:00+00:00', slot: 4, o: {}, a: {} }, { entity: 'light.d', name: 'D', state: 'off', slot: 6, o: {}, a: {} }];

async function screen() {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(W, H, 217, 3, 2), 1);
  let ms = 0;
  const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  tick();
  return { m, tick, layout: () => JSON.parse(m.ccall('preview_layout', 'string', [], [])) };
}

// Before a layout: no card on the glass.
{
  const { layout } = await screen();
  const l = layout();
  assert.deepEqual([l.cards.length, l.objects.filter((o) => o.card >= 0).length], [0, 0], 'nothing is placed before a layout arrives');
}

// Two pages: the margin all round and the page bar.
const { m, tick, layout } = await screen();
const receive = connection(m);
configure(receive, 'Home', 2, TILES);
tick();
const l = layout();
const box = (entity) => l.objects.find((o) => o.id === l.cards[l.cards.findIndex((c) => c.entity === entity)].object);
const pixels = m._preview_frame(), px = (x, y) => { const i = pixels + (y * W + x) * 4; return (m.HEAPU8[i] << 16) | (m.HEAPU8[i + 1] << 8) | m.HEAPU8[i + 2]; };
// Where a label's ink lies, left and right: the pixels of its box that differ from its corner.
const ink = (label) => {
  const ground = px(label.x1, label.y1); let left = W, right = -1;
  for (let y = label.y1; y <= label.y2; y++) for (let x = label.x1; x <= label.x2; x++) if (px(x, y) !== ground) { left = Math.min(left, x); right = Math.max(right, x); }
  return [left, right];
};
const chevron = (code) => l.objects.find((o) => o.card < 0 && o.icon && o.text.codePointAt(0) === code);
assert.equal(box('switch.a').x1, MARGIN, 'the first tile stands the margin from the left');
assert.equal(W - 1 - box('light.c').x2, MARGIN, 'the last of a row the margin from the right');
assert.equal(l.objects.find((o) => o.card < 0 && o.text === 'Home').x1, MARGIN, "the top bar's title the margin from the left");
assert.ok(chevron(PREVIOUS) && chevron(NEXT), 'two pages: the page keys show');
assert.equal(ink(chevron(PREVIOUS))[0], MARGIN, "the previous key's chevron is inked the margin from the left");
assert.equal(W - 1 - ink(chevron(NEXT))[1], MARGIN, "the next key's chevron the margin from the right");
const bar = l.objects.filter((o) => o.card < 0 && o.y1 >= chevron(PREVIOUS).y1 - 20 && o.x1 > W / 4 && o.x2 < W * 3 / 4 && o.x2 - o.x1 < 20);
assert.equal(bar.length, 2, 'and a dot for each page between them');

// A tap's guard: a switch takes every clean tap.
const actions = () => { const out = []; for (let a = m.ccall('preview_next_action', 'string', [], []); a; a = m.ccall('preview_next_action', 'string', [], [])) out.push(JSON.parse(a)); return out; };
const tap = (entity, then) => {
  const b = box(entity), x = (b.x1 + b.x2) / 2, y = (b.y1 + b.y2) / 2;
  m._preview_touch(x, y, 1); tick(1); m._preview_touch(x, y, 0); tick(then);
};
actions();
tick(20);
// Home Assistant takes the first call and reports the switch off before the second tap (a tap while one is on its
// way folds into it, docs/OPTIMISTIC.md).
tap('switch.a', 2);
let sent = actions().filter((a) => a.service.startsWith('switch.'));
for (const a of sent) m._preview_action_response(a.call_id, 1, 0);
receive({ op: 'state', i: 0, entity: 'switch.a', name: 'A', state: 'off', a: {} });
tick(1);
tap('switch.a', 2);
sent = sent.concat(actions().filter((a) => a.service.startsWith('switch.')));
assert.equal(sent.length, 2, 'two clean taps on a switch 330 ms apart: two calls');
// A scene, a script and a button have no on or off to show: a tap runs them and the tile waits for Home Assistant (its
// sheet swallows taps meanwhile: Tile::waiting, runtime_tiles set_busy). Home Assistant answers in 342-599 ms
// (runtime_model.h, BUSY_GRACE), so a finger that taps once a second runs it every time; two taps 260 ms apart are one
// (the 600 ms guard).
for (const [entity, slot] of [['scene.b', 1], ['script.e', 3], ['button.f', 4]]) {
  let moment = 0;
  const run = (then) => {
    const b = box(entity), x = (b.x1 + b.x2) / 2, y = (b.y1 + b.y2) / 2;
    m._preview_touch(x, y, 1); tick(1); m._preview_touch(x, y, 0); tick(6);
    const out = actions().filter((a) => a.data.entity_id === entity);
    for (const a of out) {
      m._preview_action_response(a.call_id, 1, 0);
      // What Home Assistant reports after it: a scene's and a button's state is the moment it ran, a script stays off and
      // the app sends when it last ran (`last`, core.extras).
      ++moment;
      receive(entity.startsWith('script.') ? { op: 'state', i: slot, entity, name: entity, state: 'off', a: {}, x: { last: 1789401840 + moment } }
        : { op: 'state', i: slot, entity, name: entity, state: `2026-01-01T00:00:0${moment}+00:00`, a: {} });
    }
    tick(then);
    return out.length;
  };
  tick(20);
  assert.deepEqual([run(8), run(8), run(8), run(8)], [1, 1, 1, 1], `${entity}: a tap a second runs it every time`);
  tick(20);
  assert.equal(run(0) + run(0), 1, `${entity}: two taps 450 ms apart run it once`);
}

// One page: no page bar.
{
  const one = await screen();
  configure(connection(one.m), 'Home', 1, TILES.slice(0, 5));
  one.tick();
  const shown = one.layout().objects.filter((o) => o.card < 0 && o.icon && [PREVIOUS, NEXT].includes(o.text.codePointAt(0)));
  assert.equal(shown.length, 0, 'one page: no page keys and no dots');
}

console.log(`page frame: nothing before a layout, one margin of ${MARGIN} px all round, the page bar for two pages, a switch takes every clean tap`);
