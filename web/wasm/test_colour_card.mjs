// A light with a colour opens the colour card on a hold (app 0.4.86: in C++, so the preview runs it as the screen does):
// its rows for the modes the light has, under every page's top bar, values that go to Home Assistant on release, and
// the back key that closes it. Since dev it is a page over the glass like a light's effects page: built when it opens,
// gone when it closes, painted from the light's tile (a new state from Home Assistant moves its sliders while it is
// open), its colour and white shade wishes the tile shows at once, its brightness what the tile's own slider sends.
// On the smallest, a middle and the largest glass.
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
import { both, warm } from './light_fixtures.mjs';

for (const shape of SHAPES) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(shape.width, shape.height, shape.dpi, shape.columns, shape.rows), 1);
  const receive = connection(m);
  configure(receive, 'Room', 1, [both, warm]);
  let ms = 0;
  const tick = (n = 4) => { for (let i = 0; i < n; i++) { ms += 32; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  const objects = () => JSON.parse(m.ccall('preview_layout', 'string', [], [])).objects;
  const texts = () => objects().filter((o) => o.type === 'label').map((o) => o.text);
  const actions = () => { const out = []; for (let a; (a = m.ccall('preview_next_action', 'string', [], [])); ) out.push(JSON.parse(a)); return out; };
  const touch = (x, y, frames) => { m._preview_touch(x, y, 1); tick(frames); m._preview_touch(x, y, 0); tick(4); };
  tick(10);
  const tile = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles[0];

  // A hold of half a second, as a finger holds it.
  touch(tile.x + tile.width / 2, tile.y + tile.height / 2, 20);
  for (const word of ['Desk', 'Color', 'Color temperature', 'Brightness'])
    assert.ok(texts().includes(word), `${shape.key}: ${word} on the colour card (${texts().join(' | ')})`);
  assert.deepEqual(actions(), [], `${shape.key}: a hold sends nothing`);

  // The back key at the glass's top left, as on every card (detail_bar), and the three sliders on the card.
  const all = objects();
  const arrows = all.filter((o) => o.type === 'label' && o.text === '\u{F004D}').map((o) => all.find((p) => p.id === o.parent));
  const back = arrows[arrows.length - 1];  // the topmost: the card's, drawn last
  assert.ok(back && back.x1 < shape.width / 4 && back.y1 < shape.height / 4, `${shape.key}: the back key at the top left`);
  const sliders = objects().filter((o) => o.type === 'slider').sort((a, b) => a.y1 - b.y1);
  assert.equal(sliders.length, 3, `${shape.key}: three sliders`);
  for (const s of sliders) assert.ok(s.x1 >= 0 && s.x2 < shape.width && s.y2 < shape.height, `${shape.key}: a slider on the glass`);

  // A new state of the light while the card is open: the sliders follow it (the card paints itself from the tile).
  receive({ op: 'state', i: 0, entity: 'light.desk', name: 'Desk', state: 'on', a: { ...both.a, hs_color: [200, 100], color_temp_kelvin: 4500, brightness: 51 } });
  tick();
  for (const word of ['200°', '4500 K', '20%'])
    assert.ok(texts().includes(word), `${shape.key}: the card follows Home Assistant, ${word} (${texts().join(' | ')})`);

  // Each slider sends its value on release: a colour as a list Home Assistant renders, a temperature, a brightness.
  const at = (s, part) => [Math.round(s.x1 + (s.x2 - s.x1) * part), Math.round((s.y1 + s.y2) / 2)];
  touch(...at(sliders[0], 0.5), 2);
  let sent = actions();
  assert.equal(sent.length, 1, `${shape.key}: one colour sent`);
  assert.equal(sent[0].service, 'light.turn_on');
  assert.deepEqual(sent[0].data, { entity_id: 'light.desk' });
  assert.match(sent[0].templates.hs_color, /^\[\d+, 100\]$/);
  touch(...at(sliders[1], 0.5), 2);
  sent = actions();
  assert.equal(sent.length, 1);
  assert.ok(+sent[0].data.color_temp_kelvin >= 2000 && +sent[0].data.color_temp_kelvin <= 6500, JSON.stringify(sent[0]));
  // The colour and the white shade are wishes: the tile shows them at once, before Home Assistant answers.
  assert.ok(!texts().includes('200°'), `${shape.key}: the colour card keeps the value let go, not the old state`);
  // The brightness is what the tile's own slider sends (commit_slider): Home Assistant's 0-255.
  touch(...at(sliders[2], 0.75), 2);
  sent = actions();
  assert.equal(sent.length, 1);
  assert.ok(+sent[0].data.brightness > 128 && +sent[0].data.brightness <= 255, JSON.stringify(sent[0]));

  // The back key closes it; the tiles are back under the finger.
  touch((back.x1 + back.x2) / 2, (back.y1 + back.y2) / 2, 2);
  assert.ok(!texts().includes('Color temperature'), `${shape.key}: the back key closes the colour card`);
  assert.ok(!objects().some((o) => o.type === 'slider'), `${shape.key}: and nothing of it is left on the glass`);

  // A light with a colour temperature alone shows two rows, through the same way the preview opens a card.
  assert.equal(m._preview_card(1), 2, `${shape.key}: preview_card opens the colour card`);
  tick();
  assert.ok(texts().includes('Hall') && texts().includes('Color temperature') && !texts().includes('Color'), `${shape.key}: two rows`);
  assert.equal(objects().filter((o) => o.type === 'slider').length, 2);

  // Dark mode while it is open: its page and its keys follow at once (theme::style, colour_restyle).
  const ground = () => { const p = m._preview_frame() + ((shape.height - 2) * shape.width + 2) * 4; return m.HEAPU8[p] + m.HEAPU8[p + 1] + m.HEAPU8[p + 2]; };
  const light = ground();
  m._preview_dark(1); tick();
  assert.ok(ground() < light / 2, `${shape.key}: the colour card goes dark (${ground()} against ${light})`);
  m._preview_dark(0); tick();
  assert.equal(ground(), light, `${shape.key}: and light again`);
}
console.log('PASS colour card: opened by a hold, its rows, following Home Assistant, its wishes and the tile slider\'s brightness, its back key, on cyd, guition, jc8012p4a1');
