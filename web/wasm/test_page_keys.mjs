// The page keys are the two halves of the band under the tiles, as high as the board's look says (boards.json
// `spacing.page_bar`, the board file's PAGE_BAR_H): the real firmware's page bar (packages/core.yaml page_prev and
// page_next), read back from the preview's layout on the smallest, a middle and the largest glass. Took the place of a
// test that quoted the two widgets' YAML (tests/test_guition.py, docs/TESTING.md "A test reads behaviour, not lines").
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const boards = JSON.parse(readFileSync(new URL('../../screen_manager/app/boards.json', import.meta.url)));

for (const key of ['cyd', 'guition', 'jc8012p4a1']) {
  const { width, height, dpi, spacing } = boards[key];
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(width, height, dpi, 2, 3), 1);
  let ms = 0;
  const tick = () => { for (let t = 0; t < 256; t += 32) { ms += 32; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  // Two pages: the page bar shows only when there is more than one (AGENTS.md, "Touch and navigation").
  configure(connection(m), 'Keys', 2, [{ entity: 'switch.a', name: 'A', state: 'off', a: {}, slot: 0, o: {} }]);
  tick();
  const objects = JSON.parse(m.ccall('preview_layout', 'string', [], [])).objects;
  const keys = objects.filter((o) => o.clickable && o.card === -1 && o.y2 === height - 1).sort((a, b) => a.x1 - b.x1);
  assert.equal(keys.length, 2, `${key}: two page keys at the foot of the glass`);
  const [back, forward] = keys;
  assert.deepEqual([back.x1, back.x2, forward.x1, forward.x2], [0, width / 2 - 1, width / 2, width - 1], `${key}: each key is half the glass wide`);
  for (const k of keys) assert.equal(k.y2 - k.y1 + 1, spacing.page_bar, `${key}: a key is the look's page bar high (${spacing.page_bar} px)`);
}
console.log('The page keys are the two halves of the band under the tiles, as high as each look says');
