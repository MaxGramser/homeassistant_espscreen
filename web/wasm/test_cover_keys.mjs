// A cover's one-cell card with keys (firmware 0.57.0, cover_row_card in runtime_tiles.h): a tap on its first key sends
// the cover an action, as the tilt cards' keys do. Until firmware 0.60.0 the keys' handler asked for the slat controls
// that only the tilt cards have, so the key pressed and nothing went out (GitHub #363). The same card with the slats
// keeps working; the preview runs the firmware's own C++, so it fails the way the glass did.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
// The Waveshare 7B's glass, where the report came from, and the 10.1-inch Guition's: large glass, where a one-cell
// card has the room for a row of keys (on a 4-inch glass it keeps its tap alone).
const SHAPES = [
  { key: 'waveshare7b', width: 1024, height: 600, dpi: 170, columns: 4, rows: 4 },
  { key: 'jc8012p4a1', width: 1280, height: 800, dpi: 149, columns: 5, rows: 4 },
];
// open, close, set_position, stop: a closed shutter with keys and a position, no slats. Closed, so its open key is
// live (Home Assistant greys the key of the way the cover is already at).
const shutter = { entity: 'cover.shutter', name: 'Shutter', state: 'closed', slot: 0,
  a: { current_position: 0, supported_features: 15, device_class: 'shutter' }, o: {} };

for (const shape of SHAPES) {
  for (const controls of ['buttons', 'buttons_tilt']) {
    const m = await createModule({ wasmBinary });
    assert.equal(m._preview_init(shape.width, shape.height, shape.dpi, shape.columns, shape.rows), 1);
    const receive = connection(m);
    // The slats take a wider card (one row high, two cells wide); the one-cell card is the report's.
    const tile = controls === 'buttons_tilt'
      ? { ...shutter, a: { ...shutter.a, supported_features: 255, current_tilt_position: 50 }, o: { controls, size: 'wide' } }
      : { ...shutter, o: { controls } };
    configure(receive, 'Room', 1, [tile]);
    let ms = 0;
    const tick = (n = 4) => { for (let i = 0; i < n; i++) { ms += 32; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
    const actions = () => { const out = []; for (let a; (a = m.ccall('preview_next_action', 'string', [], [])); ) out.push(JSON.parse(a)); return out; };
    const objects = () => JSON.parse(m.ccall('preview_layout', 'string', [], [])).objects;
    const touch = (x, y) => { m._preview_touch(x, y, 1); tick(4); m._preview_touch(x, y, 0); tick(10); };
    tick(10);
    const card = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles[0];
    // The keys: the small clickable objects inside the card (media_key makes a round, clickable lv_obj with an icon in
    // it), in reading order; the first of them is the open key of the first group.
    const inside = (o) => o.x1 >= card.x - 1 && o.y1 >= card.y - 1 && o.x2 <= card.x + card.width && o.y2 <= card.y + card.height;
    const keys = objects().filter((o) => o.type === 'object' && o.clickable && inside(o)
      && o.x2 - o.x1 < card.width / 2 && o.y2 - o.y1 < card.height / 2).sort((a, b) => a.y1 - b.y1 || a.x1 - b.x1);
    assert.ok(keys.length >= 3, `${shape.key}/${controls}: a row of keys on the card (${keys.length})`);
    const open = keys[0];
    touch((open.x1 + open.x2) / 2, (open.y1 + open.y2) / 2);
    const sent = actions();
    assert.equal(sent.length, 1, `${shape.key}/${controls}: one tap, one action (${JSON.stringify(sent)})`);
    assert.equal(sent[0].service, 'cover.open_cover', `${shape.key}/${controls}: the open key opens`);
    assert.deepEqual(sent[0].data, { entity_id: 'cover.shutter' });
  }
}
console.log('cover keys: ok');
