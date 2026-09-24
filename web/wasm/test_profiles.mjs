// The compiled module must accept the shared catalog's real grids and densities.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';

const boards = JSON.parse(readFileSync(new URL('../../screen_manager/app/boards.json', import.meta.url)));
const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
for (const [name, board] of Object.entries(boards).filter(([key]) => key.startsWith('checkout/'))) {
  for (const [orientation, shape] of Object.entries(board.orientations)) {
    const { width, height, columns, rows } = shape;
    const module = await createModule({ wasmBinary });
    assert.equal(module._preview_init(width, height, board.dpi, columns, rows), 1, `${name} ${orientation}`);
    const receive = packet => {
      const result = module.ccall('preview_receive', 'string', ['string'], [JSON.stringify(packet)]);
      assert.ok(!/invalid|error/i.test(result), result);
    };
    const count = columns * rows;
    const entities = Array.from({ length: count }, (_, i) => `sensor.cell_${i}`);
    receive({ v: 1, op: 'layout', title: name, entities, slots: entities.map((_, i) => i), pages: 1 });
    entities.forEach((entity, i) => receive({ v: 1, op: 'state', i, entity, name: `Cell ${i + 1}`, state: '21', a: { unit_of_measurement: '°C' } }));
    module._preview_time(1000, 1789401840, 0);
    module._preview_render();
    const info = JSON.parse(module.ccall('preview_diagnostics', 'string', [], []));
    assert.equal(info.tiles.length, count, 'every grid cell renders');
    for (const tile of info.tiles) {
      assert.ok(tile.width > 0 && tile.height > 0 && tile.x >= 0 && tile.y >= 0);
      assert.ok(tile.x + tile.width <= width && tile.y + tile.height <= height, 'cell stays in the canvas');
    }
    for (let i = 0; i < count; ++i) for (let j = i + 1; j < count; ++j) {
      const a = info.tiles[i], b = info.tiles[j];
      assert.ok(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y,
        `${name} ${orientation}: cells ${i} and ${j} overlap`);
    }
    console.log(`PASS ${name} ${orientation}: ${width}×${height}, ${columns}×${rows}, ${board.dpi} dpi`);
  }
}
