// Every card's name and state stand on one line, cut with an ellipsis, on every board shape: the real firmware's cards
// (runtime_tiles), opened with names and states far too long for any glass, read back from the preview's layout (the
// label's long mode and its height against its font's line). Took the place of a test that quoted the two lines of
// runtime_tiles.h that do it (tests/test_guition.py, docs/TESTING.md "A test reads behaviour, not lines").
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const SHAPES = [
  { key: 'cyd', width: 320, height: 240, dpi: 143, columns: 2, rows: 3 },
  { key: 'guition', width: 480, height: 480, dpi: 170, columns: 2, rows: 3 },
  { key: 'jc8012p4a1', width: 1280, height: 800, dpi: 149, columns: 5, rows: 4 },
];
const NAME = 'A name far too long for any card on any screen, whatever its glass';
const STATE = 'A state far too long for any card on any screen as well';
const TILES = [
  { entity: 'light.desk', name: NAME, state: 'on', a: { brightness: 128, supported_color_modes: ['brightness'], color_mode: 'brightness' } },
  { entity: 'switch.kettle', name: NAME, state: 'off', a: {} },
  { entity: 'sensor.words', name: NAME, state: STATE, a: {} },
  { entity: 'cover.blind', name: NAME, state: 'open', a: { current_position: 70, supported_features: 15 } },
];

for (const shape of SHAPES) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(shape.width, shape.height, shape.dpi, shape.columns, shape.rows), 1);
  let ms = 0;
  const tick = () => { for (let t = 0; t < 256; t += 32) { ms += 32; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  configure(connection(m), 'Labels', 1, TILES.map((tile, slot) => ({ ...tile, slot, o: {} })));
  tick();
  const layout = JSON.parse(m.ccall('preview_layout', 'string', [], []));
  // `card` of an object is its card's place in `cards`; a label's `text` is what it shows, cut where it is cut.
  const long = (text) => text.startsWith(NAME.slice(0, 8)) || text.startsWith(STATE.slice(0, 8));
  const drawn = layout.cards.map((card, index) => ({ ...card, index })).filter((card) => TILES.some((tile) => tile.entity === card.entity));
  assert.equal(drawn.length, TILES.length, `${shape.key}: every card is drawn`);
  for (const card of drawn) {
    const labels = layout.objects.filter((o) => o.type === 'label' && o.card === card.index && long(o.text));
    assert.ok(labels.length, `${shape.key} ${card.entity}: its long name is a label of the card`);
    for (const label of labels) {
      const what = `${shape.key} ${card.entity} "${label.text}"`;
      assert.equal(label.mode, 'dots', `${what}: a name or state too long for the card is cut with an ellipsis`);
      assert.ok(label.dots, `${what}: and the ellipsis shows`);
      assert.ok(label.y2 - label.y1 + 1 <= label.line_height + 1, `${what}: one line high (${label.y2 - label.y1 + 1} px for a line of ${label.line_height})`);
    }
  }
}
console.log('Every card name and state is one line with an ellipsis, on the smallest, a middle and the largest glass');
