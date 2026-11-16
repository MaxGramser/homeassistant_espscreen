// The strip a hold opens Settings from (settings_screen::attach_hold, docs/SETTINGS.md): the top bar's band less the side
// bands the page swipe owns, measured on the live canvas, and under every card, so a card's own keys at its top keep
// their taps. Read from the real firmware in the preview on the smallest, a middle and the largest glass; took the place
// of quotes of core.yaml's attach_hold call and of settings_screen.h's and runtime_tiles.h's stacking lines
// (tests/test_settings_page.py, docs/TESTING.md "A test reads behaviour, not lines").
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const boards = JSON.parse(readFileSync(new URL('../../screen_manager/app/boards.json', import.meta.url)));
const LIGHT = { entity: 'light.desk', name: 'Desk', state: 'on', a: { brightness: 128, supported_color_modes: ['brightness'], color_mode: 'brightness' } };

for (const key of ['cyd', 'guition', 'jc8012p4a1']) {
  const { width, height, dpi, spacing } = boards[key];
  const start = async () => {
    const m = await createModule({ wasmBinary });
    assert.equal(m._preview_init(width, height, dpi, 2, 3), 1);
    let ms = 0;
    const tick = (duration = 256) => { for (let t = 0; t < duration; t += 16) { ms += 16; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
    configure(connection(m), 'Room', 1, [{ ...LIGHT, slot: 0, o: {} }]);
    tick(512);
    const objects = () => JSON.parse(m.ccall('preview_layout', 'string', [], [])).objects;
    const settingsShown = () => objects().some((o) => o.type === 'label' && o.text === 'Settings');
    const hold = (x, y, duration = 1700) => { m._preview_touch(x, y, 1); tick(duration); m._preview_touch(x, y, 0); tick(256); };
    return { m, objects, settingsShown, hold };
  };

  // The strip: the top bar's band, from the top of the glass to the tiles, its two ends left to the page swipe.
  {
    const { objects } = await start();
    const strips = objects().filter((o) => o.clickable && o.card === -1 && o.y1 === 0 && o.y2 === spacing.top - 1);
    assert.equal(strips.length, 1, `${key}: one hold strip across the top bar, as high as the bar (${spacing.top} px)`);
    const [strip] = strips;
    assert.equal(strip.x1, width - 1 - strip.x2, `${key}: the strip leaves the same band free at each side`);
    // Resistive glass turns its pages by a flick anywhere and has no side bands: its strip is the whole bar.
    if (boards[key].catalog.touch === 'XPT2046') assert.equal(strip.x1, 0, `${key}: resistive glass holds the whole bar`);
    else assert.ok(strip.x1 > 0, `${key}: the side bands are the page swipe's, not the hold's`);
  }
  // With no card open, a hold on the top bar opens Settings; with a card open it does not: the strip lies under the card.
  {
    const { settingsShown, hold } = await start();
    hold(width / 2, 8);
    assert.ok(settingsShown(), `${key}: a hold on the top bar opens Settings`);
  }
  {
    const { m, objects, settingsShown, hold } = await start();
    const tile = JSON.parse(m.ccall('preview_diagnostics', 'string', [], [])).tiles[0];
    hold(tile.x + Math.floor(tile.width / 2), tile.y + Math.floor(tile.height / 2), 900);
    assert.ok(objects().some((o) => o.type === 'label' && o.text === 'Brightness'), `${key}: holding the light opens its card`);
    hold(width / 2, 8);
    assert.ok(!settingsShown(), `${key}: a hold at the top of an open card is the card's, not the Settings strip's`);
  }
}
console.log('The Settings hold strip is the top bar less its side bands, and lies under every card');
