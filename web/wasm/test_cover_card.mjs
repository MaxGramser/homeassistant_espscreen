// A cover's card (firmware 0.2.56 and on), read from the real firmware, no line of it quoted: a tap and a hold open
// the cover's own card, with Home Assistant's state, position and tilt in its status line (current_tilt_position from
// the app), which the card's once-a-second tick keeps; the position slider sends nothing while a finger drags it and
// set_cover_position once on release; a key does its action; a key at its end stop is faded; and a blind whose slats
// stand open at 50 (`tilt_open`) has its open-slats key at the end stop there, where another blind does not.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const BACK = 0xf004d, OPEN = 0xf005d, CLOSE = 0xf0045, OPEN_SLATS = 0xf1011, FADED = 127;
const TILES = [
  { entity: 'cover.blind', name: 'Blind', state: 'open', o: {}, a: { supported_features: 255, current_position: 60, current_tilt_position: 40, device_class: 'blind' } },
  { entity: 'cover.full', name: 'Full', state: 'open', o: {}, a: { supported_features: 15, current_position: 100 } },
  { entity: 'cover.middle', name: 'Middle', state: 'open', o: { tilt_open: '50' }, a: { supported_features: 51, current_tilt_position: 50 } },
  { entity: 'cover.plain', name: 'Plain', state: 'open', o: {}, a: { supported_features: 51, current_tilt_position: 50 } },
].map((t, slot) => ({ ...t, slot }));

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(1280, 800, 149, 4, 3), 1);
let ms = 0;
const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
configure(connection(m), 'Covers', 1, TILES);
tick();
const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
const actions = () => { const out = []; for (let a = m.ccall('preview_next_action', 'string', [], []); a; a = m.ccall('preview_next_action', 'string', [], [])) out.push(JSON.parse(a)); return out; };
const touch = (o, hold = 2) => { tick(10); const x = (o.x1 + o.x2) / 2, y = (o.y1 + o.y2) / 2; m._preview_touch(x, y, 1); for (let i = 0; i < hold; ++i) { tick(1); m._preview_touch(x, y, 1); } m._preview_touch(x, y, 0); tick(8); };
// The card over the page: its words, its sliders and the key a glyph stands in (with the key's opacity).
const card = () => {
  const l = layout(), over = l.objects.filter((o) => o.card < 0);
  const keyOf = (label) => { for (let o = label; o; o = l.objects.find((p) => p.id === o.parent)) if (o.clickable) return o; return null; };
  return { words: over.filter((o) => o.type === 'label' && !o.icon).map((o) => o.text), sliders: over.filter((o) => o.type === 'slider'),
    key: (code) => keyOf(over.find((o) => o.type === 'label' && o.icon && o.text.codePointAt(0) === code)) };
};
const tile = (slot) => { const l = layout(); return l.objects.find((o) => o.id === l.cards[slot].object); };
const open = (slot, hold = 2) => { touch(tile(slot), hold); assert.ok(card().key(BACK), `${TILES[slot].entity}: its card is open`); actions(); };
const close = () => { touch(card().key(BACK)); actions(); };

// A tap opens the cover's card; its status line says the state, the position and the tilt, and a tick keeps it.
open(0);
assert.ok(card().words.includes('Open · 60% · Tilt 40%'), 'the status line: state, position and tilt');
assert.equal(card().sliders.length, 2, 'a slider for the position and one for the slats');
tick(40);
assert.ok(card().words.includes('Open · 60% · Tilt 40%'), 'two seconds of ticks keep the status line');
// The position slider: nothing while a finger drags, set_cover_position once on release.
{
  const [slider] = card().sliders, x = (slider.x1 + slider.x2) / 2;
  m._preview_touch(x, slider.y1 + 100, 1); tick(2);
  for (let y = slider.y1 + 100; y <= slider.y1 + 300; y += 20) { m._preview_touch(x, y, 1); tick(1); }
  assert.deepEqual(actions(), [], 'nothing goes out while the finger drags');
  m._preview_touch(x, slider.y1 + 300, 0); tick(4);
  const sent = actions();
  assert.equal(sent.length, 1, 'one action on release');
  assert.equal(sent[0].service, 'cover.set_cover_position');
  assert.ok(Number(sent[0].data.position) < 60, 'dragged down: the cover goes further closed');
}
tick(10);
touch(card().key(CLOSE));
assert.deepEqual(actions().map((a) => [a.service, a.data]), [['cover.close_cover', { entity_id: 'cover.blind' }]], 'the close key closes');
close();

// A hold opens the same card.
open(1, 20);
assert.ok(card().words.includes('Open · 100%'), "a hold opens the cover's card too");
assert.equal(card().key(OPEN).opa, FADED, 'a cover fully open has its open key faded at the end stop');
assert.notEqual(card().key(CLOSE).opa, FADED, 'and its close key live');
close();

// Slats open at 50: there the open-slats key is the end stop; at 50 another blind can open its slats further.
open(2);
assert.equal(card().key(OPEN_SLATS).opa, FADED, 'slats that open at 50, standing at 50: open-slats faded');
close();
open(3);
assert.notEqual(card().key(OPEN_SLATS).opa, FADED, 'slats that open at 100, standing at 50: open-slats live');
close();

console.log('cover card: tap and hold, the status line and its tick, the slider on release, keys, end stops, tilt_open');
