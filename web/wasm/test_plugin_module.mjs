// A plugin's own code in the preview (docs/EMULATOR_ARCHITECTURE.md, "Plugins"): the preview probe
// (tests/fixtures/plugins/preview_probe) is built into a module (web/wasm/build_plugin.py), written into the preview's
// file system, linked and started, and the test reads back what only that plugin's code can have drawn: a word of its
// own translations in the screen's language, its option, its data, the ticks it counted, and the card a tap opens.
// Without the module the same tile is the plain card of a screen that lacks the plugin.
// Building a module needs Emscripten: where em++ is not on the PATH (tools/check.sh on a computer without it) the test
// says so and passes; CI's preview job, which has just built the preview with it, runs it whole.
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

if (spawnSync('em++', ['--version']).status !== 0) {
  console.log('SKIP a plugin\'s module in the preview: no Emscripten here to build the probe with');
  process.exit(0);
}
const ROOT = fileURLToPath(new URL('../..', import.meta.url));
const work = mkdtempSync(join(tmpdir(), 'preview-probe-'));
const file = join(work, 'preview_probe.wasm');
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python3',
  [join(ROOT, 'web/wasm/build_plugin.py'), join(ROOT, 'tests/fixtures/plugins/preview_probe'), '--out', file],
  { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim().split('\n').pop());
const code = readFileSync(file);
rmSync(work, { recursive: true });

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const SHAPE = { width: 480, height: 480, dpi: 170, columns: 3, rows: 3 };
const TILE = { entity: 'plugin:preview_probe.note', name: 'Note', state: 'ok', a: {}, slot: 0,
  o: { size: 'wide', plugin: { word: 'Proef' } }, x: { value: '42' } };

async function screen(withCode, language) {
  const m = await createModule({ wasmBinary });
  if (withCode) {
    m.FS.writeFile('/plugin-preview_probe.wasm', code);
    await m.loadDynamicLibrary('/plugin-preview_probe.wasm', { loadAsync: true, global: true, nodelete: true });
  }
  assert.equal(m._preview_init(SHAPE.width, SHAPE.height, SHAPE.dpi, SHAPE.columns, SHAPE.rows), 1);
  const start = (id) => m.ccall('preview_plugin', 'number', ['string', 'string', 'string'], ['/plugin-preview_probe.wasm', id, language]);
  if (withCode) {
    assert.equal(start('someone_else'), 0, 'a module starts only the plugin it is');
    assert.equal(start('preview_probe'), 1, 'the probe starts');
    assert.equal(start('preview_probe'), 1, 'and starting it again changes nothing');
  }
  m.ccall('preview_language', 'number', ['string'], [language]);
  let ms = 0, epoch = 1789401840;
  const tick = (span = 512) => { for (let t = 0; t < span; t += 64) { ms += 64; m._preview_time(ms, epoch + Math.floor(ms / 1000), 7200); m._preview_render(); } };
  configure(connection(m), 'Probe', 1, [TILE]);
  tick();
  const labels = () => JSON.parse(m.ccall('preview_layout', 'string', [], [])).objects.filter((o) => o.type === 'label').map((o) => o.text);
  const cards = () => JSON.parse(m.ccall('preview_cards', 'string', [], []));
  return { m, tick, labels, cards };
}

// The number the module carries is the preview's own: the two were built from the same headers.
{
  const m = await createModule({ wasmBinary });
  assert.equal(m.ccall('preview_plugin_abi', 'string', [], []), built.abi, 'the module was built for this preview');
  const renderer = JSON.parse(readFileSync(new URL('../src/wasm/renderer.json', import.meta.url)));
  assert.equal(renderer.plugin_abi, built.abi, 'renderer.json names the same number');
}

// Without its code: the plain card of a screen that lacks the plugin, and the frame says no plugin drew it.
{
  const s = await screen(false, 'en');
  const [card] = s.cards();
  assert.equal(card.plugin, false, 'no plugin code drew the card');
  assert.equal(card.slot, 0);
  assert.ok(s.labels().includes('Plugin missing'), `the card says the plugin is missing: ${s.labels().join(' | ')}`);
}

// With its code, in Dutch: the plugin's own line, from its translation, its option and its data, at the card's place.
{
  const s = await screen(true, 'nl');
  const [card] = s.cards();
  assert.equal(card.plugin, true, 'the plugin\'s own code drew the card');
  assert.ok(card.w > SHAPE.width / 2 && card.h > 0 && card.r > 0, 'the card has its box and its corners');
  assert.ok(s.labels().includes('Hallo Proef 42'), `the plugin wrote its own line: ${s.labels().join(' | ')}`);
  assert.ok(!s.labels().includes('Plugin missing'));
  // Once a second while the card is on the glass: the tile counts its ticks in English, the text Dutch lacks.
  s.tick(3200);
  const ticks = s.labels().find((text) => / ticks$/.test(text));
  assert.ok(ticks && parseInt(ticks, 10) >= 2, `the tile was ticked: ${ticks}`);
  // New data for the tile: the line follows without the card being made again.
  // A tap on the tile reaches the plugin's on_tap, which opens its card.
  const x = card.x + Math.floor(card.w / 2), y = card.y + Math.floor(card.h / 2);
  s.tick(250); s.m._preview_touch(x, y, 1); s.tick(120); s.m._preview_touch(x, y, 0); s.tick(600);
  assert.ok(s.labels().includes('Meer van de proef'), `a tap opened the plugin's card: ${s.labels().join(' | ')}`);
}

// The frame says which cards look different (preview_cards' `n`), so the editor copies a card only when it changed:
// a card the plugin ticks counts on, a card whose state came in counts once, and the cards beside them stay as they were.
{
  const m = await createModule({ wasmBinary });
  m.FS.writeFile('/plugin-preview_probe.wasm', code);
  await m.loadDynamicLibrary('/plugin-preview_probe.wasm', { loadAsync: true, global: true, nodelete: true });
  assert.equal(m._preview_init(SHAPE.width, SHAPE.height, SHAPE.dpi, SHAPE.columns, SHAPE.rows), 1);
  assert.equal(m.ccall('preview_plugin', 'number', ['string', 'string', 'string'], ['/plugin-preview_probe.wasm', 'preview_probe', 'en']), 1);
  let ms = 0;
  // The same minute throughout: the top bar's clock stays as it is, so only the cards can change the frame.
  const tick = (span = 512) => { for (let t = 0; t < span; t += 64) { ms += 64; m._preview_time(ms, 1789401840 + Math.floor(ms / 1000) % 50, 7200); m._preview_render(); } };
  const lamp = (name, slot) => ({ entity: `light.${name}`, name, state: 'off', a: { supported_color_modes: ['onoff'] }, slot, o: {} });
  const receive = connection(m);
  configure(receive, 'Counts', 1, [TILE, lamp('desk', 3), lamp('shelf', 4)]);
  tick(2048);
  const counts = () => Object.fromEntries(JSON.parse(m.ccall('preview_cards', 'string', [], [])).map((card) => [card.slot, card.n]));
  const first = counts();
  assert.ok(first[0] > 0 && first[3] > 0 && first[4] > 0, `every card on the glass was drawn: ${JSON.stringify(first)}`);
  // Two seconds go by: the plugin's tile counts its ticks, the lamps stand still.
  tick(2048);
  const later = counts();
  assert.ok(later[0] > first[0], 'the card the plugin ticks was drawn again');
  assert.deepEqual([later[3], later[4]], [first[3], first[4]], 'the cards nothing happened to were not');
  // One lamp goes on: its card alone changed.
  receive({ op: 'state', i: 1, entity: 'light.desk', name: 'desk', state: 'on', a: { supported_color_modes: ['onoff'] } });
  tick(256);
  const lit = counts();
  assert.ok(lit[3] > later[3], 'the card whose state came in was drawn again');
  assert.equal(lit[4], later[4], 'and the lamp beside it was not');
}
// A glass on which nothing happens says so: no card's count moves, whatever number of frames go by.
{
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(SHAPE.width, SHAPE.height, SHAPE.dpi, SHAPE.columns, SHAPE.rows), 1);
  let ms = 0;
  const tick = (span = 512) => { for (let t = 0; t < span; t += 64) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  const lamp = (name, slot) => ({ entity: `light.${name}`, name, state: 'off', a: { supported_color_modes: ['onoff'] }, slot, o: {} });
  configure(connection(m), 'Still', 1, [lamp('desk', 0), lamp('shelf', 1)]);
  tick(2048);
  const read = () => m.ccall('preview_cards', 'string', [], []);
  const before = read();
  tick(4096);
  assert.equal(read(), before, 'nothing changed, so nothing is to be copied');
}

// In a language the plugin has no translation for, it speaks English, as a screen built in that language.
{
  const s = await screen(true, 'fr');
  assert.ok(s.labels().includes('Hello Proef 42'), `English where the plugin lacks the language: ${s.labels().join(' | ')}`);
}
console.log(`PASS a plugin's module in the preview: ${built.id} ${built.version} (${code.length} bytes), its own line, its ticks, its card, the plain card without it, and a count per card that moves only when that card changed`);
