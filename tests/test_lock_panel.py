"""The lock (firmware 0.5.0): a lock entity as a tile that locks with one tap and asks before it unlocks, and a card
with Home Assistant's keys and code dialog. tests/test_lock_panel.cpp checks the logic of
components/smart_display/lock_panel.h (colours, icons, actions, which acts confirm) and tests/test_tile_controls.cpp
when a lock is active; web/wasm/test_lock_card.mjs reads the real cards (icons and colours, one tap locks, unlocking
asks per tile, lock only, the keypad and a refused code); the editor's colours and guards are in web/tests (layout.spec,
pages.spec). Here: the app's side, and the rules that keep a code private.
"""
from firmware_sources import firmware_domains, runtime_source
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import core  # noqa: E402
import page_layout  # noqa: E402

COMPONENT = ROOT / 'components/smart_display'
RECEIVER = (COMPONENT / 'page_receiver.cpp').read_text()
TILES = runtime_source()


def section():
    return TILES.split('// ---- Lock (firmware 0.5.0+)', 1)[1].split('// ---- History card', 1)[0]


class TheApp(unittest.TestCase):
    def test_a_lock_is_a_tile_and_still_a_top_bar_item(self):
        self.assertIn('lock', core.DOMAINS)
        self.assertNotIn('lock', core.HEADER_ONLY_DOMAINS)
        self.assertTrue(core.entity_id('lock.front_door'))
        self.assertIn('lock', firmware_domains())
        core.validate_header({'items': [{'type': 'entity', 'entity': 'lock.front_door'}]})

    def test_the_app_sends_whether_a_default_code_exists_never_the_code(self):
        entry = {'options': {'lock': {'default_code': '4321'}}}
        self.assertEqual(core.lock_extras(entry), {'dc': 1})
        self.assertNotIn('4321', json.dumps(core.lock_extras(entry)))
        self.assertEqual(core.lock_extras({'options': {'lock': {'default_code': ''}}}), {})
        self.assertEqual(core.lock_extras({'options': {'alarm_control_panel': {'default_code': '1'}}}), {})
        self.assertEqual(core.lock_extras(None), {})

    def test_the_attributes_the_card_needs(self):
        states = {'lock.front': {'state': 'locked', 'attributes': {'code_format': '^\\d{4}$', 'changed_by': 'Keypad',
                                                                   'assumed_state': True, 'supported_features': 1}},
                  'light.a': {'state': 'on', 'attributes': {'assumed_state': True}}}
        lock = core.state_message(0, {'entity': 'lock.front', 'name': ''}, states)
        self.assertEqual(lock['a']['code_format'], '^\\d{4}$')
        self.assertEqual(lock['a']['changed_by'], 'Keypad')
        self.assertIs(lock['a']['assumed_state'], True)
        self.assertEqual(lock['a']['supported_features'], 1)
        # assumed_state only travels for a lock, whose keys need it.
        self.assertNotIn('assumed_state', core.state_message(0, {'entity': 'light.a', 'name': ''}, states)['a'])
        # Rule between the two sides: the firmware keeps a regular expression of up to 48 characters, which the app
        # sends whole.
        self.assertIn('next.code_format = string(a["code_format"], 48);', RECEIVER,
                      'page_receiver.cpp keeps 48 characters of code_format, as the app sends it')

    def test_the_guard_option(self):
        def layout(entity, guard):
            return {'title': 'Home', 'tiles': [{'entity': entity, 'slot': 0, 'options': {'guard': guard}}]}
        saved = core.validate_layout(layout('lock.front', 'lock_only'))
        self.assertEqual(saved['tiles'][0]['options'], {'guard': 'lock_only'})
        # The default is not stored.
        self.assertEqual(core.validate_layout(layout('lock.front', 'confirm'))['tiles'][0].get('options', {}), {})
        for bad in (layout('lock.front', 'never'), layout('light.a', 'lock_only')):
            with self.assertRaises(ValueError):
                core.validate_layout(bad)
        # The page document carries it as an interaction (the editor validates the same two choices: pages.spec.ts), and
        # a lock without one asks before it unlocks (test_lock_card.mjs).
        self.assertEqual(page_layout.INTERACTION['guard'], 'guard')
        self.assertEqual(list(core.LOCK_GUARDS), ['confirm', 'lock_only'])

    def test_a_layout_with_a_lock_waits_for_its_firmware_and_the_newest_gate_wins(self):
        self.assertEqual(core.min_firmware({'tiles': [{'entity': 'lock.front'}]}), core.LOCK_MIN_FIRMWARE)
        self.assertEqual(core.LOCK_MIN_FIRMWARE, (0, 5, 0))
        # A tilting blind (0.3.1) beside an alarm panel (0.3.3) needs 0.3.3: the newest gate, not the first one found.
        both = {'tiles': [{'entity': 'cover.a', 'options': {'controls': 'tilt'}}, {'entity': 'alarm_control_panel.a'}]}
        self.assertEqual(core.min_firmware(both), core.ALARM_MIN_FIRMWARE)
        self.assertIsNone(core.min_firmware({'tiles': [{'entity': 'light.a'}]}))


class TheFirmware(unittest.TestCase):
    def test_the_screen_never_logs_or_keeps_a_code(self):
        lock = section()
        # Rule: no log line of the lock names its code. The keypad sending the code with lock.unlock, and a refused code
        # as esphome.screen_lock_code_refused without it, are read from the real firmware in test_lock_card.mjs.
        for line in lock.splitlines():
            if 'ESP_LOG' in line:
                self.assertNotIn('code', line.replace('alarm_card_note', ''), f'a log line names a code: {line.strip()}')

    def test_a_heartbeat_travels_with_its_card(self):
        # A kept page's cards leave the glass and come back by swapping places (keep_page). The heartbeat of a lock or an
        # alarm panel belongs to the card, so a card whose lock settled while it was away does not keep beating (firmware
        # 0.16.0; a lock on several pages showed it). Rule: the look lives on the card's widgets, never in a table of tiles.
        self.assertIn('uint8_t alarm_look=0; uint32_t alarm_mark=0;', TILES, "the heartbeat's look and mark are the card's widgets'")
        for table in ('alarm_tile_looks', 'alarm_tile_marks'):
            self.assertNotIn(table, TILES, f'{table}: a table per tile would stay behind when the card moves')
        look = TILES.split('inline void alarm_tile_look(', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('if(want==w.alarm_look)return;', look, "the look is read from the card it is on")
        self.assertIn('std::swap(widgets[i], (*set)[i]);', TILES, 'a kept page swaps whole widgets, the look with them')


if __name__ == '__main__':
    unittest.main()
