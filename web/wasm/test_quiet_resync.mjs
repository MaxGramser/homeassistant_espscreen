// Two links of a slider that turned red on release (app 0.2.55, firmware 0.2.47; tests/test_quiet_resync.py has the
// story), read from the real firmware in the preview instead of the lines that do them:
// - a layout that comes again (a new session, the same revision and counts) is "Synced" and changes nothing: the glass
//   is the same and a finger held on a tile meanwhile is still its tap, where a new layout cancels it;
// - the GT911's stray (0, 0) contact never moves the edge swipe on: a short swipe from the right edge with that sample
//   stays on its page, where a real contact one pixel away turns it.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const TILES = [{ entity: 'switch.a', name: 'A', state: 'off', a: {}, slot: 0, o: {} }, { entity: 'light.b', name: 'B', state: 'on', a: {}, slot: 1, o: {} }];
const W = 480, H = 480;

async function screen() {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(W, H, 170, 2, 3), 1);
  let ms = 0;
  const tick = (duration = 256) => { for (let t = 0; t < duration; t += 16) { ms += 16; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  const frame = () => { const p = m._preview_frame(); return Buffer.from(m.HEAPU8.slice(p, p + W * H * 4)); };
  return { m, tick, frame };
}

// A finger on a tile while the layout comes again: the screen holds the same, so the press goes on and its release is
// the tap; a new layout in the same moment cancels the press, as it must for cards that are gone.
for (const [again, action] of [[true, 'switch.turn_on'], [false, '']]) {
  const { m, tick, frame } = await screen();
  configure(connection(m, '1111111111111111'), 'Room', 1, TILES);
  tick(512);
  const tile = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles[0];
  const x = tile.x + Math.floor(tile.width / 2), y = tile.y + Math.floor(tile.height / 2);
  m._preview_touch(x, y, 1); tick(64);
  const glass = frame();
  if (again) {
    // The add-on's resync: a new session whose begin names the revision and counts the screen has.
    assert.equal(connection(m, '4444444444444444')({ op: 'begin', title: 'Room', pages: 1, tiles: TILES.length, home: 0, keepalive: 60 }), 'Synced');
    tick(64);
    assert.ok(frame().equals(glass), 'a layout that comes again leaves the glass as it was');
  } else {
    configure(connection(m, '5555555555555555', '6666666666666666'), 'Room', 1, [...TILES, { entity: 'switch.c', name: 'C', state: 'off', a: {}, slot: 2, o: {} }]);
    tick(64);
  }
  m._preview_touch(x, y, 0); tick(256);
  const sent = m.ccall('preview_next_action', 'string', [], []);
  assert.equal(sent ? JSON.parse(sent).service : '', action,
    again ? 'a press held while the layout comes again is still the tap' : 'a press held while a new layout comes is cancelled');
}

for (const [contact, page, why] of [[[0, 0], 0, 'the stray (0, 0) is no part of a swipe'], [[1, 1], 1, 'a real contact at the edge turns the page']]) {
  const { m, tick } = await screen();
  configure(connection(m), 'Room', 2, TILES);
  tick(512);
  m._preview_touch(W - 2, H / 2, 1); tick(32);
  m._preview_touch(W - 40, H / 2, 1); tick(32);
  m._preview_touch(contact[0], contact[1], 1); tick(32);
  m._preview_touch(W - 40, H / 2, 0); tick(500);
  assert.equal(m._preview_page(), page, `a short edge swipe with a contact at (${contact}): ${why}`);
}
console.log('A layout that comes again redraws nothing, and the stray (0, 0) is no swipe');
