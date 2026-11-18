// The alarm panel (firmware 0.3.3), read from the real firmware, no line of it quoted: its card offers Home Assistant's
// modes in the frontend's order for what the panel supports (never trigger); disarming with a code opens the keypad and
// sends the code with the action; a refused code becomes the event esphome.screen_alarm_code_refused with the panel, the
// count and the lock, never the code; arming without a required code goes out at once. And the alarm's choices from the
// Events page (docs/ALARM_PANEL.md): a code that sends itself after its length with Delete where OK was, the keypad that
// opens on its own when the alarm goes off and that Back closes, and a screen left out that stays quiet.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
const BACK = 0xf004d, OK = 0xf012c;
const MODES = [['Home', 0xf068a], ['Away', 0xf099d], ['Night', 0xf1828], ['Vacation', 0xf06bb], ['Custom', 0xf0483], ['Disarmed', 0xf099e]];
const panel = (entity, state, a) => ({ entity, name: entity.split('.')[1], state, o: {}, a });
const TILES = [panel('alarm_control_panel.house', 'armed_away', { code_format: 'number', code_arm_required: false, supported_features: 63 }),
  panel('alarm_control_panel.shed', 'disarmed', { supported_features: 2 })].map((t, slot) => ({ ...t, slot }));

const m = await createModule({ wasmBinary });
assert.equal(m._preview_init(1280, 800, 149, 4, 3), 1);
let ms = 0;
const tick = (n = 8) => { for (let i = 0; i < n; i++) { ms += 64; m._preview_time(ms, 1789401840, 7200); m._preview_render(); } };
configure(connection(m), 'Alarm', 1, TILES);
tick();
const layout = () => JSON.parse(m.ccall('preview_layout', 'string', [], []));
const press = (o) => { tick(10); const x = (o.x1 + o.x2) / 2, y = (o.y1 + o.y2) / 2; m._preview_touch(x, y, 1); tick(2); m._preview_touch(x, y, 0); tick(6); };
const action = () => { const a = m.ccall('preview_next_action', 'string', [], []); return a ? JSON.parse(a) : null; };
const actions = () => { const out = []; for (let a = action(); a; a = action()) out.push(a); return out; };
// The card over the page: its words and icons in their order, and the key a label stands in.
const over = () => {
  const l = layout(), labels = l.objects.filter((o) => o.card < 0 && o.type === 'label' && o.text);
  const keyOf = (label) => { for (let o = label; o; o = l.objects.find((p) => p.id === o.parent)) if (o.clickable) return o; return label; };
  return { labels, words: labels.filter((o) => !o.icon).map((o) => o.text),
    key: (t) => keyOf(labels.find((o) => (o.icon ? o.text.codePointAt(0) === t : o.text === t))) };
};
const open = (slot) => { const l = layout(); press(l.objects.find((o) => o.id === l.cards[slot].object)); assert.ok(over().key(BACK), 'the card is open'); };
const close = () => { while (over().key(BACK)) press(over().key(BACK)); actions(); };

// Every mode the panel supports, in the frontend's order, each with Home Assistant's icon; disarm last.
open(0);
assert.deepEqual(actions(), [], 'a tap opens the card and sends nothing');
const shown = over().labels.map((o) => (o.icon ? o.text.codePointAt(0) : o.text));
const order = MODES.map(([word]) => shown.indexOf(word));
assert.ok(order.every((at, i) => at >= 0 && (i === 0 || at > order[i - 1])), `the modes in Home Assistant's order: ${MODES.map(([w]) => w)}`);
for (const [word, glyph] of MODES) assert.equal(shown[shown.indexOf(word) - 1] === glyph || shown[shown.indexOf(word) + 1] === glyph, true, `${word} has its icon`);
assert.ok(!over().words.some((w) => /trigger/i.test(w)), 'trigger is never a key');

// Disarming with a code: the keypad, the code with the action, and a refusal that never carries it.
press(over().key('Disarmed'));
assert.deepEqual(actions(), [], 'disarming a panel with a code waits for it');
assert.ok(['1', '2', '3', '0'].every((d) => over().words.includes(d)), 'on the keypad');
for (const digit of '1234') press(over().key(digit));
press(over().key(OK));
const sent = actions();
assert.deepEqual(sent.map((a) => [a.service, a.data]), [['alarm_control_panel.alarm_disarm', { entity_id: 'alarm_control_panel.house', code: '1234' }]],
  'the code goes with alarm_disarm');
m.ccall('preview_action_response', null, ['number', 'number', 'string'], [sent[0].call_id, 0, 'Invalid code']);
tick(8);
const refused = actions();
assert.deepEqual(refused.map((a) => [a.service, a.event, a.data]),
  [['esphome.screen_alarm_code_refused', true, { entity_id: 'alarm_control_panel.house', failures: '1', locked: '0' }]],
  'a refused code is an event with the panel, the count and the lock');
assert.ok(!JSON.stringify(refused).includes('1234'), 'never the code');
assert.ok(over().words.includes('Wrong code'), 'and the keypad says so');
close();

// A panel that supports away alone offers away and disarm; arming it needs no code and goes out at once.
open(1);
const words = over().words;
assert.ok(words.includes('Away') && words.includes('Disarmed') && !['Home', 'Night', 'Vacation', 'Custom'].some((w) => words.includes(w)),
  'a panel that arms away alone offers away and disarm');
press(over().key('Away'));
assert.deepEqual(actions().map((a) => [a.service, a.data]), [['alarm_control_panel.alarm_arm_away', { entity_id: 'alarm_control_panel.shed' }]],
  'arming without a required code goes out at once, with no code');

close();

// The alarm's choices from the Events page, which the app gives every tile of it (alarm_screens.py): the house sends its
// code after four digits; the garage is set to leave this screen out when it goes off.
const house = { entity: 'alarm_control_panel.house', name: 'house', state: 'armed_away', o: { send_after: '4' },
  a: { code_format: 'number', code_arm_required: false, supported_features: 63 } };
const garage = { entity: 'alarm_control_panel.garage', name: 'garage', state: 'armed_away', o: { alarm_wake: 'off' },
  a: { code_format: 'number', code_arm_required: false, supported_features: 63 } };
const receive = connection(m, '3333333333333333', '4444444444444444');
configure(receive, 'Alarm', 1, [house, garage].map((t, slot) => ({ ...t, slot })));
// The shed's arming above still waits for its state; after ten seconds without one the screen lets it go.
tick(200);
const glyphs = (code) => over().labels.filter((o) => o.icon && o.text.codePointAt(0) === code);

// Four digits send the code by themselves: no OK key, and Delete (the keyboard's arrow, after the bar's Back) takes back
// one digit.
open(0);
press(over().key('Disarmed'));
assert.equal(glyphs(OK).length, 0, 'a code that sends itself has no OK key');
assert.equal(glyphs(BACK).length, 2, 'Back in the bar and Delete beside 0');
for (const digit of '12') press(over().key(digit));
press(glyphs(BACK).at(-1));
for (const digit of '23') press(over().key(digit));
assert.deepEqual(actions(), [], 'three digits send nothing');
press(over().key('4'));
const typed = actions();
assert.deepEqual(typed.map((a) => [a.service, a.data]), [['alarm_control_panel.alarm_disarm', { entity_id: 'alarm_control_panel.house', code: '1234' }]],
  'the fourth digit sends the code, the deleted one gone');
m.ccall('preview_action_response', null, ['number', 'number', 'string'], [typed[0].call_id, 1, '']);
close();

// The house goes off: its card opens by itself as the keypad, without a card with one Disarm key first, and Back closes it.
receive({ op: 'state', i: 0, entity: house.entity, name: house.name, state: 'triggered', a: house.a });
tick(12);
assert.ok(over().key(BACK) && ['1', '5', '0'].every((d) => over().words.includes(d)), 'going off opens the keypad at once');
press(over().key(BACK));
assert.ok(!over().key(BACK), 'Back on that keypad closes the card');

// The garage goes off too: this screen was left out for it, so nothing opens.
receive({ op: 'state', i: 1, entity: garage.entity, name: garage.name, state: 'triggered', a: garage.a });
tick(12);
assert.ok(!over().key(BACK), 'a screen left out for an alarm stays quiet when it goes off');

console.log('alarm card: the modes in order, the keypad, a refused code without the code, arming at once, a code that sends itself, '
  + 'Delete, the keypad at once when it goes off, a screen left out');
