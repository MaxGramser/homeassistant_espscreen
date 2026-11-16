// A player's library on the screen (app 0.4.42, firmware 0.24.0), read from the real firmware, no line of it quoted: the
// card's library key asks the add-on for the top folder (esphome.screen_browse), the answer the add-on makes
// (tests/fixtures/media-library.json, which tests/test_media_library.py keeps equal to media_library.py) shows its
// folders, a folder opens with its own number, and a tap on an album plays it (esphome.screen_play with its number).
// An answer for a view the screen no longer shows is dropped.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const FIXTURE = JSON.parse(readFileSync(new URL('../../tests/fixtures/media-library.json', import.meta.url), 'utf8'));
const LIBRARY_KEY = 0xf0cb8, BACK = 0xf004d;

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(1280, 800, 149, 4, 3), 1);
let ms = 0;
const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
const receive = connection(m);
receive({ op: 'begin', title: 'Music', pages: 1, tiles: 1, home: 0, keepalive: 60 });
receive({ op: 'page', p: 0, id: '0000000000000001', title: '', home_control: false, excluded: false, items: [] });
receive({ op: 'tile', i: 0, slot: 0, entity: FIXTURE.entity, name: 'Spotify', state: 'playing', o: {},
  a: { supported_features: FIXTURE.features, media_title: 'A song', media_artist: 'Someone' }, x: FIXTURE.x });
receive({ op: 'commit' });
tick();

const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
const press = (o) => { const x = (o.x1 + o.x2) / 2, y = (o.y1 + o.y2) / 2; m._preview_touch(x, y, 1); tick(2); m._preview_touch(x, y, 0); tick(6); };
const action = () => { const a = m.ccall('preview_next_action', 'string', [], []); return a ? JSON.parse(a) : null; };
const actions = () => { const out = []; for (let a = action(); a; a = action()) out.push(a); return out; };
// What lies over the page (the card, the library): its labels, and the clickable object a label stands in.
const over = () => {
  const l = layout(), labels = l.objects.filter((o) => o.card < 0 && o.type === 'label' && o.text);
  const keyOf = (label) => { for (let o = label; o; o = l.objects.find((p) => p.id === o.parent)) if (o.clickable) return o; return label; };
  return { words: labels.filter((o) => !o.icon).map((o) => o.text),
    word: (text) => keyOf(labels.find((o) => !o.icon && o.text === text)),
    icon: (code) => { const label = labels.find((o) => o.icon && o.text.codePointAt(0) === code); return label && keyOf(label); } };
};
const event = (service) => {
  const found = actions().filter((a) => a.service === service);
  assert.equal(found.length, 1, `one ${service}`);
  return found[0].data;
};

// The card opens on a tap; its library key asks for the top folder.
{ const l = layout(); press(l.objects.find((o) => o.id === l.cards[0].object)); }
assert.ok(over().icon(BACK), "the player's card is open");
actions();
press(over().icon(LIBRARY_KEY));
let asked = event(FIXTURE.browse);
assert.deepEqual([asked.entity, asked.folder, asked.page], [FIXTURE.entity, '0', '0'], 'the top folder, page 0');

// An answer for another view is dropped; the one asked for shows its folders.
receive({ ...FIXTURE.top, view: Number(asked.view) + 1 });
tick();
assert.ok(!over().words.includes('Albums'), 'an answer for a view the screen does not show is dropped');
receive({ ...FIXTURE.top, view: Number(asked.view) });
tick();
const folders = FIXTURE.top.k.map((item) => item[1]);
for (const name of folders.slice(0, 4)) assert.ok(over().words.includes(name), `the library shows ${name}`);

// A folder opens with its own number.
press(over().word('Albums'));
asked = event(FIXTURE.browse);
assert.equal(asked.folder, String(FIXTURE.albums.f), 'Albums is asked for by its number');
receive({ ...FIXTURE.albums, view: Number(asked.view) });
tick();
const [first] = FIXTURE.albums.k;
assert.ok(over().words.includes(FIXTURE.albums.t), 'the folder shows its title');
assert.ok(over().words.includes(first[1]), 'and its albums');

// A tap on an album plays it, by its number.
press(over().word(first[1]));
const played = event(FIXTURE.play);
assert.deepEqual([played.entity, played.item], [FIXTURE.entity, String(first[0])], 'an album plays by its number');

console.log(`media library: ${folders.length} folders, ${FIXTURE.albums.k.length} albums, browse and play as the add-on reads them`);
