// Cards from the top bar (firmware 0.56.0, bar_cards): an entity's item opens the card holding its tile opens, through
// the one way to a card (runtime_tiles::hold_card), and nothing else. Its tile is one on a page or a tile of the top bar
// (`bar`: no cell, drawn nowhere), and the item names it (`d`). The real firmware's decoder, top bar and cards, with a
// finger on the glass, on the smallest, a middle and the largest glass.
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
const left = (state, words) => ({ entity: 'sensor.dishwasher_left', name: 'Dishwasher', state,
  a: { unit_of_measurement: 'h', device_class: 'duration' }, x: { w: words } });
// A lamp on a page, and a switch, a sensor and a player on no tile: what the app sends them as
// (page_service.top_bar_tiles). The player's item shows its icon alone (header_bar.entity_item, content icon).
const SPEAKER = '\u{F04C3}', STANDBY = '\u{F0906}';
const TILES = [
  { entity: 'light.desk', name: 'Desk', state: 'on', a: { brightness: 204, supported_color_modes: ['brightness'], color_mode: 'brightness' }, o: {}, slot: 0 },
  { entity: 'switch.coffee', name: 'Coffee', state: 'on', a: {}, o: {}, bar: 1 },
  { ...left('0.2', '12m'), o: {}, bar: 1 },
  { entity: 'media_player.kitchen', name: 'Speaker', state: 'playing', a: { volume_level: 0.4, is_volume_muted: false, supported_features: 252349 }, o: {}, bar: 1 },
];
const ITEMS = [{ k: 'text', t: 'On', d: 1 }, { k: 'text', t: '12m', d: 2 }, { k: 'text', t: '80%', d: 0 }, { k: 'text', i: 'F04C3', t: '', d: 3 }];

for (const shape of SHAPES) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(shape.width, shape.height, shape.dpi, shape.columns, shape.rows), 1);
  const raw = connection(m);
  configure(packet => raw(packet.op === 'page' ? { ...packet, items: ITEMS } : packet), 'Kitchen', 1, TILES);
  let ms = 0;
  const tick = (n = 4) => { for (let i = 0; i < n; i++) { ms += 32; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
  const objects = () => JSON.parse(m.ccall('preview_layout', 'string', [], [])).objects;
  const texts = () => objects().filter((o) => o.type === 'label').map((o) => o.text);
  // What the screen asks of Home Assistant, but for the history a card asks for when it opens.
  const actions = () => { const out = []; for (let a; (a = m.ccall('preview_next_action', 'string', [], [])); ) if (!a.includes('screen_history')) out.push(a); return out; };
  const touch = (x, y) => { m._preview_touch(x, y, 1); tick(2); m._preview_touch(x, y, 0); tick(6); };
  const centre = (o) => [Math.round((o.x1 + o.x2) / 2), Math.round((o.y1 + o.y2) / 2)];
  // The key a glyph is drawn on: the last one, the open card's over the page.
  const key = (glyph) => {
    const all = objects();
    const keys = all.filter((o) => o.type === 'label' && o.text === glyph).map((o) => all.find((p) => p.id === o.parent));
    return keys[keys.length - 1];
  };
  const back = () => touch(...centre(key('\u{F004D}')));
  // A finger on the top bar, after the pause a person makes: the touch guard takes one tap of the bar each 600 ms.
  const tapItem = (words) => {
    tick(20);
    const item = objects().find((o) => o.type === 'label' && o.text === words && o.card < 0 && o.y2 < shape.height / 4);
    assert.ok(item, `${shape.key}: ${words} on the top bar (${texts().join(' | ')})`);
    const [x, y] = centre(item);
    assert.ok(objects().some((o) => o.clickable && o.x1 <= x && x <= o.x2 && o.y1 <= y && y <= o.y2 && o.card < 0),
      `${shape.key}: a finger's area over ${words}`);
    touch(x, y);
  };
  tick(12);
  actions();

  // The tiles of the top bar are drawn nowhere: the page shows the lamp alone.
  const diagnostics = JSON.parse(m.ccall('preview_diagnostics', 'string', [], []));
  assert.deepEqual(diagnostics.tiles.map((t) => t.title), ['Desk'], `${shape.key}: only the lamp is on the page`);

  // The switch opens its card and does not switch; the switch on the card does.
  tapItem('On');
  assert.ok(texts().includes('Coffee'), `${shape.key}: the switch's card (${texts().join(' | ')})`);
  assert.deepEqual(actions(), [], `${shape.key}: a tap on the top bar switches nothing`);
  const knob = objects().find((o) => o.clickable && o.card < 0 && o.x1 > shape.width / 2 && o.y2 < shape.height / 2 &&
    (o.x2 - o.x1) / Math.max(1, o.y2 - o.y1) > 1.5 && (o.x2 - o.x1) / Math.max(1, o.y2 - o.y1) < 2.2 && o.y1 > 0);
  assert.ok(knob, `${shape.key}: the switch on the card`);
  touch(...centre(knob));
  const sent = actions();
  assert.ok(sent.some((a) => a.includes('switch.') && a.includes('switch.coffee')), `${shape.key}: the card's switch switches (${sent})`);
  back();
  assert.ok(!texts().includes('Coffee'), `${shape.key}: Back closes the card`);

  // The sensor opens its history card, which says the duration as the bar does and follows the tile's next state.
  tapItem('12m');
  assert.ok(texts().includes('Dishwasher') && texts().filter((t) => t === '12m').length >= 2,
    `${shape.key}: the sensor's card says 12m (${texts().join(' | ')})`);
  raw({ op: 'state', i: 2, ...left('0.5', '30m') });
  tick(6);
  assert.ok(texts().includes('30m'), `${shape.key}: the open card follows its tile (${texts().join(' | ')})`);
  back();

  // An entity that is on a page opens that tile's card: the lamp's, without switching it.
  tapItem('80%');
  assert.ok(texts().includes('Desk') && objects().some((o) => o.type === 'slider'), `${shape.key}: the lamp's card (${texts().join(' | ')})`);
  assert.deepEqual(actions(), [], `${shape.key}: the lamp is not switched`);
  back();

  // An item that shows its icon alone opens its card too (GitHub #252): the player's, which plays on.
  tapItem(SPEAKER);
  assert.ok(texts().includes('Speaker') && key(STANDBY), `${shape.key}: the player's card (${texts().join(' | ')})`);
  assert.deepEqual(actions(), [], `${shape.key}: the player is not paused`);
  // Its power key turns it off (GitHub #239): the card's command 30 reaches media_action, as the tile's keys do.
  const power = key(STANDBY);
  assert.ok(power?.clickable, `${shape.key}: the power key on the player's card`);
  touch(...centre(power));
  const off = actions();
  assert.ok(off.some((a) => a.includes('media_player.turn_off') && a.includes('media_player.kitchen')), `${shape.key}: the power key turns the player off (${off})`);
}
console.log(`PASS top bar cards: a switch, a sensor, a lamp and a player's icon open their cards from the top bar and nothing else, and the player's power key turns it off, on ${SHAPES.map((s) => s.key).join(', ')}`);
