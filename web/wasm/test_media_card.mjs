// A player's card (app 0.2.64 and on), read from the real firmware, no line of it quoted: each of the extras the app
// sends (artist, album, the track's length and where it stands at a moment) reaches the card on its own, so none is
// lost when the others are missing; and the card's keys and the keys of the player's tile over the whole page do the
// same actions (one table).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const NOW = 1789401840, BACK = 0xf004d, PAUSE = 0xf03e4, NEXT = 0xf04ad;
const PLAYER = { entity: 'media_player.office', name: 'Office', state: 'playing',
  a: { supported_features: 21437, media_title: 'Woman at the Loom', volume_level: 0.3 } };

async function screen(x, o = {}) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(1280, 800, 149, 4, 3), 1);
  let ms = 0;
  const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, NOW, 7200); m._preview_render(); } };
  configure(connection(m), 'Music', 1, [{ ...PLAYER, slot: 0, o, x }]);
  tick();
  const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
  const press = (o) => { tick(10); const cx = (o.x1 + o.x2) / 2, cy = (o.y1 + o.y2) / 2; m._preview_touch(cx, cy, 1); tick(2); m._preview_touch(cx, cy, 0); tick(8); };
  const actions = () => { const out = []; for (let a = m.ccall('preview_next_action', 'string', [], []); a; a = m.ccall('preview_next_action', 'string', [], [])) out.push(JSON.parse(a)); return out; };
  // What a layer shows: the card over the page (card < 0) or the tile (card 0); and the key a glyph stands in.
  const shown = (card) => {
    const l = layout(), labels = l.objects.filter((o) => (card < 0 ? o.card < 0 : o.card === card) && o.type === 'label');
    const keyOf = (label) => { for (let o = label; o; o = l.objects.find((p) => p.id === o.parent)) if (o.clickable) return o; return label; };
    return { words: labels.filter((o) => !o.icon).map((o) => o.text), key: (code) => keyOf(labels.find((o) => o.icon && o.text.codePointAt(0) === code)) };
  };
  const open = () => { const l = layout(); press(l.objects.find((o) => o.id === l.cards[0].object)); assert.ok(shown(-1).key(BACK), "the player's card is open"); };
  return { press, actions, shown, open };
}

// Each extra on its own.
for (const [x, want, what] of [[{ artist: 'KATZROAR' }, ['KATZROAR'], 'the artist'], [{ album: 'Loom' }, ['Loom'], 'the album'],
  [{ dur: 200, pos: 30, at: NOW - 10 }, ['0:40', '3:20'], 'where the track stands (30 s, 10 s ago) and its length']]) {
  const s = await screen(x);
  s.open();
  for (const word of want) assert.ok(s.shown(-1).words.includes(word), `the card shows ${what} alone: ${word}`);
}

// The card's keys and the keys of the tile over the whole page: one table.
const keys = async (s, layer) => {
  const done = [];
  for (const code of [PAUSE, NEXT]) { s.actions(); s.press(s.shown(layer).key(code)); done.push(s.actions().map((a) => [a.service, a.data.entity_id])); }
  return done;
};
const card = await screen({ artist: 'KATZROAR' });
card.open();
const fromCard = await keys(card, -1);
assert.deepEqual(fromCard, [[['media_player.media_pause', PLAYER.entity]], [['media_player.media_next_track', PLAYER.entity]]],
  "the card's pause and next keys");
const page = await screen({ artist: 'KATZROAR' }, { size: 'full' });
assert.deepEqual(await keys(page, 0), fromCard, 'the tile over the whole page does the same');

console.log('media card: artist, album and times each on their own, one action table for the card and the page');
