// A tile's icon where the add-on sends none of its own is what the editor predicts (tile_icons.py editor(), held for both
// sides in tests/fixtures/tile-icons.json, which tests/test_tile_icons.py keeps equal to the app's tables): read from the
// real firmware's cards, no line of it quoted. Each domain's own icon, the built-in cards', every weather condition's, the
// sun's above and below the horizon, and the fallback of a domain without one.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const ICONS = JSON.parse(readFileSync(new URL('../../tests/fixtures/tile-icons.json', import.meta.url), 'utf8'));
// Each tile in a state that shows its domain's own icon (a light that is on: an off one is crossed out).
const STATE = { light: 'on', humidifier: 'on', automation: 'on', remote: 'on', person: 'home', timer: 'idle', vacuum: 'docked' };
const want = [
  ...Object.entries(ICONS.defaults).filter(([domain]) => domain !== 'screen')
    .map(([domain, code]) => [{ entity: `${domain}.one`, state: STATE[domain] ?? 'on' }, code, `a ${domain}`]),
  // The Call tile only where the board has the call module, which the preview is built without.
  ...Object.entries(ICONS.builtin).filter(([entity]) => entity !== 'screen.call').map(([entity, code]) => [{ entity, state: '' }, code, entity]),
  ...Object.entries(ICONS.weather).map(([condition, code], i) => [{ entity: `weather.w${i}`, state: condition }, code, `the weather when ${condition}`]),
  [{ entity: 'sun.sun', state: 'above_horizon' }, ICONS.sun.above_horizon, 'the sun above the horizon'],
  [{ entity: 'switch.no_icon_of_its_own', state: 'on' }, ICONS.fallback, 'a domain without an icon of its own (the fallback)'],
];
// The cards that draw a face of their own (a clock's dial, the energy diagram, the template's text) show no icon; their
// icon is the editor's alone (its library and its mockup).
const FACES = new Set(['screen.clock', 'screen.energy', 'screen.text']);
const below = [{ entity: 'sun.sun', state: 'below_horizon' }, ICONS.sun.below_horizon, 'the sun below the horizon'];

async function glyphs(list) {
  assert.ok(list.length <= 64, 'one page of 8 x 8');
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(1280, 800, 149, 8, 8), 1);
  configure(connection(m), 'Icons', 8, list.map(([tile], slot) => ({ ...tile, name: '', a: {}, slot, o: {} })));
  let ms = 0;
  for (let i = 0; i < 8; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); }
  const layout = JSON.parse(m.ccall('preview_layout', 'string', [], []));
  return list.map(([tile]) => {
    const card = layout.cards.findIndex((c) => c.entity === tile.entity);
    assert.ok(card >= 0, `${tile.entity} is on the glass`);
    const icon = layout.objects.find((o) => o.card === card && o.icon);
    return icon ? icon.text.codePointAt(0).toString(16).toUpperCase() : null;
  });
}
for (const list of [want, [below]]) {
  const found = await glyphs(list);
  list.forEach(([, code, what], i) => assert.equal(found[i], FACES.has(what) ? null : code,
    FACES.has(what) ? `${what} draws its own face, no icon` : `${what} shows the icon the editor predicts`));
}
console.log(`tile icons: ${want.length + 1} tiles show the icons the editor predicts`);
