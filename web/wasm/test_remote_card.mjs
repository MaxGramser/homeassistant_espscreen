// A remote as a tile (firmware 0.22.0, GitHub #117), read from the real firmware, no line of it quoted: its tile names
// the activity it runs and is crossed out while off (Home Assistant's remote/icons.json); its card is Home Assistant's
// dialog (more-info-remote.ts), the power key beside the activities, each activity remote.turn_on with `activity`, and
// the power key alone and large in the middle of a remote with nothing else; a remote whose integration has a keypad
// (the add-on sends its keys) gets the ring of arrows round OK, each key remote.send_command with that integration's
// name, and every clean tap counts.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const POWER = 0xf0425, BACK = 0xf004d, REMOTE = 0xf0454, REMOTE_OFF = 0xf0ec4;
const SHAPE = { width: 800, height: 480, dpi: 217, columns: 3, rows: 3 };
const tiles = [
  { entity: 'remote.hub', name: 'Hub', state: 'on', slot: 0, o: {},
    a: { supported_features: 4, current_activity: 'Watch TV', activity_list: ['Watch TV', 'Music', 'Games'] } },
  // An Apple TV's keys as catalogue.remote_keypad gives them (catalogue/remote.yaml): up, down, left, right, OK, then
  // the round keys.
  { entity: 'remote.box', name: 'Box', state: 'on', slot: 1, o: {}, a: {},
    x: { keys: ['up', 'down', 'left', 'right', 'select', 'menu', 'home', 'top_menu', 'volume_up', 'volume_down', ''] } },
  { entity: 'remote.ir', name: 'IR', state: 'off', slot: 2, o: {}, a: {} },
];

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(SHAPE.width, SHAPE.height, SHAPE.dpi, SHAPE.columns, SHAPE.rows), 1);
let ms = 0;
const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
configure(connection(m), 'Remotes', 1, tiles);
tick();
const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
const glyph = (o) => o.text.codePointAt(0);
const press = (o) => { const x = (o.x1 + o.x2) / 2, y = (o.y1 + o.y2) / 2; m._preview_touch(x, y, 1); tick(2); m._preview_touch(x, y, 0); tick(6); };
const action = () => { const a = m.ccall('preview_next_action', 'string', [], []); return a ? JSON.parse(a) : null; };
const actions = () => { const out = []; for (let a = action(); a; a = action()) out.push(a); return out; };
const tile = (entity) => {
  const l = layout(), card = l.cards.findIndex((c) => c.entity === entity);
  const own = l.objects.filter((o) => o.card === card && o.type === 'label');
  return { box: l.objects.find((o) => o.id === l.cards[card].object), icon: glyph(own.find((o) => o.icon)), words: own.filter((o) => !o.icon).map((o) => o.text) };
};
// The card open over the page: its labels, and the key (a clickable object) a label stands in.
const card = () => {
  const l = layout(), labels = l.objects.filter((o) => o.card < 0 && o.type === 'label' && o.text);
  const keyOf = (label) => { for (let o = label; o; o = l.objects.find((p) => p.id === o.parent)) if (o.clickable) return o; return label; };
  return { words: labels.filter((o) => !o.icon).map((o) => o.text), icons: labels.filter((o) => o.icon),
    word: (text) => keyOf(labels.find((o) => o.text === text)), icon: (code) => keyOf(labels.find((o) => o.icon && glyph(o) === code)) };
};
const open = (entity) => { press(tile(entity).box); assert.ok(card().icons.some((o) => glyph(o) === BACK), `${entity}'s card is open`); };
const close = () => press(card().icon(BACK));

// The tiles.
assert.equal(tile('remote.hub').icon, REMOTE, 'a remote that is on shows mdi:remote');
assert.ok(tile('remote.hub').words.includes('Watch TV'), 'and names the activity it runs');
assert.equal(tile('remote.ir').icon, REMOTE_OFF, 'a remote that is off shows mdi:remote-off');
assert.ok(tile('remote.ir').words.includes('Off'), 'and says Off');
actions();

// Home Assistant's dialog: the power key and the activities, the one running checked; an activity is remote.turn_on.
open('remote.hub');
let c = card();
assert.ok(['Watch TV', 'Music', 'Games'].every((a) => c.words.includes(a)), 'the card lists the activities');
const power = c.icon(POWER);
assert.ok(power, 'and has the power key');
press(c.word('Music'));
const turnOn = actions().find((a) => a.service === 'remote.turn_on');
assert.deepEqual(turnOn?.data, { entity_id: 'remote.hub', activity: 'Music' }, 'an activity is remote.turn_on with activity');
close();

// A keypad: the ring round OK, OK is the integration's own name, and every clean tap counts.
open('remote.box');
c = card();
assert.ok(c.word('OK'), 'the keypad has OK');
press(c.word('OK'));
press(c.word('OK'));
const sent = actions().filter((a) => a.service === 'remote.send_command');
assert.equal(sent.length, 2, 'two taps on OK send two commands');
assert.ok(sent.every((a) => a.data.entity_id === 'remote.box' && a.data.command === 'select'), 'OK sends the integration\'s "select"');
close();

// A remote with nothing else: the power key alone, larger and in the middle.
open('remote.ir');
const alone = card().icon(POWER);
const middle = (o) => [(o.x1 + o.x2) / 2, (o.y1 + o.y2) / 2];
assert.ok(alone.x2 - alone.x1 > power.x2 - power.x1, 'the power key alone is larger than beside activities');
const [x, y] = middle(alone);
assert.ok(Math.abs(x - SHAPE.width / 2) < SHAPE.width / 8 && y > SHAPE.height / 4, 'and stands in the middle of the card');
press(alone);
assert.ok(actions().some((a) => a.service === 'remote.toggle' || a.service === 'remote.turn_on'), 'it switches the remote');

console.log('remote card: tiles, activities, keypad and the power key, as Home Assistant\'s dialog');
