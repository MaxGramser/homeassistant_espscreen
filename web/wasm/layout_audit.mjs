// The layout geometry of the real firmware, without drawing a picture (app 0.4.32). Reads a list of screens from the
// file named on the command line, each with its glass, grid, density and a list of layouts (its tiles, and how many
// pages it has where a card goes to another), runs every layout through
// the WebAssembly build of runtime_tiles.h, and writes what preview_layout() reports for each to stdout as one JSON
// array. tests/test_layout_audit.py writes the list and checks the answer; see there for what is checked and why.
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const screens = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const out = [];
for (const screen of screens) {
  // One module per glass and grid: preview_init sets them once, and every layout after it replaces the one before.
  const m = await createModule({ wasmBinary });
  if (m._preview_init(screen.width, screen.height, screen.dpi, screen.columns, screen.rows) !== 1) {
    out.push({ screen: screen.key, error: 'preview_init refused the glass or grid' });
    continue;
  }
  // A board that draws no pictures (the CYD) lays its media cards out without a cover's place (firmware 0.46.0).
  if (screen.pictures === false) m._preview_pictures(0);
  let ms = 0;
  const tick = (delta = 32) => { ms += delta; m._preview_time(ms, 1789401840, 7200); m._preview_render(); };
  let n = 0;
  for (const layout of screen.layouts) {
    // A fresh session per layout, as a screen gets from the app after a save.
    // A layout the firmware refuses is reported with its reason, and the next one goes on.
    try {
      const receive = connection(m, (++n).toString(16).padStart(16, '1'), (n + 1000).toString(16).padStart(16, '2'));
      configure(receive, 'Audit', layout.pages ?? 1, layout.tiles);
    } catch (error) {
      out.push({ screen: screen.key, layout: layout.key, error: String(error.message ?? error).split('\n')[0] });
      continue;
    }
    // Long enough for the pages to be built and the first frame drawn; marquees and animations need no more.
    for (let i = 0; i < 12; i++) tick(64);
    const report = JSON.parse(m.ccall('preview_layout', 'string', [], []));
    out.push({ screen: screen.key, layout: layout.key, ...report });
  }
}
process.stdout.write(JSON.stringify(out));
