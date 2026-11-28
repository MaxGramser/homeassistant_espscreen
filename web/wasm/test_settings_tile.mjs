// The settings card (screen.settings, firmware 0.2.49+) opens the screen's own Settings page under a tap, also when
// the link to Home Assistant is gone: the built-in cards need nothing from it, where a light's tap waits for a link
// that is fresh. Read from the real firmware in the preview; took the place of a quote of runtime_tiles::event
// (tests/test_screen_owned_settings.py, docs/TESTING.md "A test reads behaviour, not lines").
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const TILES = [
  { entity: 'screen.settings', name: 'Settings', state: '', a: {}, slot: 0, o: {} },
  { entity: 'switch.fan', name: 'Fan', state: 'off', a: {}, slot: 1, o: {} },
];

for (const [width, height, dpi] of [[320, 240, 143], [480, 480, 170], [1280, 800, 149]]) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(width, height, dpi, 2, 3), 1);
  let ms = 0;
  const tick = (duration = 256) => { for (let t = 0; t < duration; t += 32) { ms += 32; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  configure(connection(m), 'Room', 1, TILES);
  tick(512);
  const tiles = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles;
  const tap = (tile) => {
    const x = tile.x + Math.floor(tile.width / 2), y = tile.y + Math.floor(tile.height / 2);
    m._preview_touch(x, y, 1); tick(96); m._preview_touch(x, y, 0); tick(512);
  };
  const actions = () => { const out = []; for (let a; (a = m.ccall('preview_next_action', 'string', [], [])); ) out.push(JSON.parse(a)); return out; };
  const settingsShown = () => JSON.parse(m.ccall('preview_layout', 'string', [], [])).objects
    .some((o) => o.type === 'label' && o.text === 'Settings' && o.card === -1 && o.y1 < height / 4);

  // Minutes without a word from Home Assistant: the link is no longer fresh, so the fan's tap goes nowhere.
  tick(10 * 60 * 1000);
  actions();
  tap(tiles[1]);
  assert.deepEqual(actions(), [], `${width}x${height}: a tap on a card that needs Home Assistant waits for a fresh link`);
  // The settings card opens Settings all the same.
  tap(tiles[0]);
  assert.ok(settingsShown(), `${width}x${height}: the settings card opens Settings without Home Assistant`);
}
console.log('The settings card opens Settings without Home Assistant');
