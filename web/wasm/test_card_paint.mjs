// A card's paint follows what it is painted for, with no new state (docs/THEME.md "A card's look", firmware 0.17.0):
// a background changed in the editor arrives as an `appearance` message alone and the card wears it at once; a card that
// moves into a section whose tiles follow its contrast, and out again, wears the other look and then its own; and Dark
// mode turns it. Read from the real firmware's frame: a card's colour is the colour most of its pixels have.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const SHAPE = { width: 480, height: 480, dpi: 170, columns: 3, rows: 3 };
const tile = { entity: 'light.desk', name: 'Desk', state: 'off', a: { supported_color_modes: ['brightness'] }, slot: 0, o: {} };
// The colours of components/smart_display/theme.h this test expects (the table is the source; these are its values).
const CARD = { light: 0xffffff, dark: 0x1a1a1a }, BLUE = { light: 0xd9eafb, dark: 0x1c3448 };

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(SHAPE.width, SHAPE.height, SHAPE.dpi, SHAPE.columns, SHAPE.rows), 1);
let ms = 0;
const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
let receive = connection(m), revisions = 2;
// Each new layout comes with a revision of its own, as the add-on sends one.
const relayout = (sections) => {
  ++revisions;
  receive = connection(m, revisions.toString(16).padStart(16, '1'), (revisions + 1000).toString(16).padStart(16, '2'));
  configure(receive, 'Paint', 1, [tile], sections);
};

// The colour most pixels of the first card have, inside its box (its background).
function cardColour() {
  const layout = JSON.parse(m.ccall('preview_layout', 'string', [], []));
  const card = layout.cards.find((c) => c.entity === tile.entity);
  assert.ok(card, 'the card is on the glass');
  const box = layout.objects.find((o) => o.id === card.object);
  const p = m._preview_frame(), frame = m.HEAPU8.slice(p, p + SHAPE.width * SHAPE.height * 4), counts = new Map();
  for (let y = box.y1 + 4; y <= box.y2 - 4; y++)
    for (let x = box.x1 + 4; x <= box.x2 - 4; x++) {
      const i = (y * SHAPE.width + x) * 4, rgb = (frame[i] << 16) | (frame[i + 1] << 8) | frame[i + 2];
      counts.set(rgb, (counts.get(rgb) ?? 0) + 1);
    }
  return [...counts].sort((a, b) => b[1] - a[1])[0][0];
}
const hex = (v) => '#' + v.toString(16).padStart(6, '0');
const expect = (want, why) => assert.equal(hex(cardColour()), hex(want), why);

configure(receive, 'Paint', 1, [tile]);
tick();
expect(CARD.light, 'a card without a background is the card');
const builds = m._preview_card_builds();

// A background from the editor: the appearance message alone, no state, and the card wears it on its own.
receive({ op: 'appearance', base: '2222222222222222', title: 'Paint', pages: [{ p: 0, title: '' }],
  tiles: [{ i: 0, name: tile.name, background: 'blue' }] });
tick();
expect(BLUE.light, 'an appearance message with a background repaints the card on its own');
receive({ op: 'appearance', base: '2222222222222222', title: 'Paint', pages: [{ p: 0, title: '' }],
  tiles: [{ i: 0, name: tile.name, background: '' }] });
tick();
expect(CARD.light, 'and back to the card');

// Into a section whose tiles follow its contrast: the card is painted in the other look; out again, in its own.
const following = [[0, 0, 2, 2, '', 'Following', '', 3]];
relayout(following);
tick();
expect(CARD.dark, 'in a following section the card is the other look\'s card');
relayout();
tick();
expect(CARD.light, 'out of the section the card is the screen\'s card again');

// Dark mode turns the screen: a plain card is the dark card, one in a following section the light one.
m._preview_dark(1);
tick();
expect(CARD.dark, 'Dark mode: the card is the dark card');
relayout(following);
tick();
expect(CARD.light, 'Dark mode, in a following section: the light card');
m._preview_dark(0);
tick();
expect(CARD.dark, 'back to light, still in the following section: the dark card');
assert.ok(m._preview_card_builds() >= builds, 'the counter of built cards only grows');
console.log('PASS a card\'s paint: an appearance message, a following section in and out, Dark mode, on its own');
