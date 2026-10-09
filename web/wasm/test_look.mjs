// The editor shows a screen in its own language and look (app 0.4.86): the real firmware takes the language ESP Screens
// builds the screens in (preview_language) and the screen's Dark mode (preview_dark), before a layout and while one is
// on the glass, and draws its own texts and paints in them. It holds as many pages and tiles as the largest board.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const shape = { width: 480, height: 480, dpi: 170, columns: 3, rows: 3 };
const light = { entity: 'light.desk', name: 'Desk', state: 'on', slot: 0, o: {},
  a: { brightness: 128, color_temp_kelvin: 3000, min_color_temp_kelvin: 2000, max_color_temp_kelvin: 6500,
       supported_color_modes: ['color_temp', 'hs'], color_mode: 'color_temp', hs_color: [30, 60] } };

async function screen({ language, dark, before = true }) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(shape.width, shape.height, shape.dpi, shape.columns, shape.rows), 1);
  let ms = 0;
  const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  const look = () => {
    if (language) m.ccall('preview_language', 'number', ['string'], [language]);
    if (dark !== undefined) m._preview_dark(dark ? 1 : 0);
  };
  if (before) look();
  configure(connection(m), 'Room', 1, [light]);
  tick();
  if (!before) { look(); tick(); }
  return { m, tick };
}
const texts = (m) => JSON.parse(m.ccall('preview_layout', 'string', [], [])).objects.filter((o) => o.type === 'label').map((o) => o.text);
const pixel = (m, x, y) => { const p = m._preview_frame() + (y * shape.width + x) * 4; return m.HEAPU8[p] + m.HEAPU8[p + 1] + m.HEAPU8[p + 2]; };

// The language: the light's colour card says its rows in Dutch, in English by default, and in the base language of a code
// without a file of its own; an unknown code is English.
for (const [language, word, own] of [[undefined, 'Brightness'], ['nl', 'Helderheid', 1], ['nl-BE', 'Helderheid', 1],
                                      ['xx', 'Brightness', 0]]) {
  for (const before of [true, false]) {
    const { m, tick } = await screen({ language, before });
    if (language) assert.equal(m.ccall('preview_language', 'number', ['string'], [language]), own, `${language} has a table`);
    assert.equal(m._preview_card(0), 2);  // a light with a colour: its colour card
    tick();
    assert.ok(texts(m).includes(word), `${language ?? 'default'} (${before ? 'before' : 'after'} the layout): ${word} in ${texts(m).join(' | ')}`);
  }
}

// The look: the page under the cards is light, and dark with Dark mode, set before the layout or with it on the glass;
// and light again when it goes off.
const ground = (m) => pixel(m, shape.width / 2, shape.height - 3);
const { m: lightScreen } = await screen({});
for (const before of [true, false]) {
  const { m, tick } = await screen({ dark: true, before });
  assert.ok(ground(m) < ground(lightScreen) / 2, `dark ${before ? 'before' : 'after'} the layout: ${ground(m)} against ${ground(lightScreen)}`);
  m._preview_dark(0); tick();
  assert.equal(ground(m), ground(lightScreen), 'light again');
}

// What the largest board holds (boards.json, build.py): 24 pages and 256 tiles, and the page past it refused, so a
// screen with more than the eight pages every screen once had is previewed whole.
{
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(shape.width, shape.height, shape.dpi, shape.columns, shape.rows), 1);
  const count = Math.min(256, 9 * 24);  // as many as fit the cells of 24 pages of 3 x 3
  const tiles = Array.from({ length: count }, (_, i) => ({ entity: `sensor.t${i}`, name: `T${i}`, state: '1', a: {}, slot: i, o: {} }));
  configure(connection(m), 'Many', 24, tiles);
  m.ccall('preview_render', null, [], []);
  assert.equal(JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).count, count);
  const raw = (packet) => m.ccall('preview_receive', 'string', ['string'], [JSON.stringify(packet)]);
  const granted = raw({ v: 2, op: 'hello', request: '3333333333333333' });
  const refused = raw({ v: 2, session: granted.slice(8), seq: 1, rev: '4444444444444444', op: 'begin', title: 'Too many', pages: 25, tiles: 1, home: 0, keepalive: 60 });
  assert.match(refused, /^Error/, `25 pages: ${refused}`);
}
console.log('Preview language, look and the largest board: ok');
