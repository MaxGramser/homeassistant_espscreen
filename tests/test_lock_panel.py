"""The lock (firmware 0.5.0): a lock entity as a tile that locks with one tap and asks before it unlocks, and a card
with Home Assistant's keys and code dialog. tests/test_lock_panel.cpp checks the logic of
components/smart_display/lock_panel.h; these keep the app, the firmware and the editor in step with each other and with
Home Assistant (its 2026.9 core and frontend), and hold the rules that keep a code private.
"""
from firmware_sources import runtime_source
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import core  # noqa: E402
import page_layout  # noqa: E402

COMPONENT = ROOT / 'components/smart_display'
PANEL = (COMPONENT / 'lock_panel.h').read_text()
MODEL = (COMPONENT / 'runtime_model.h').read_text()
RECEIVER = (COMPONENT / 'page_receiver.cpp').read_text()
TILES = runtime_source()
PALETTE = (ROOT / 'web/src/model/tile-palette.ts').read_text()
VALIDATION = (ROOT / 'web/src/model/page-validation.ts').read_text()


def section():
    return TILES.split('// ---- Lock (firmware 0.5.0+)', 1)[1].split('// ---- History card', 1)[0]


class TheApp(unittest.TestCase):
    def test_a_lock_is_a_tile_and_still_a_top_bar_item(self):
        self.assertIn('lock', core.DOMAINS)
        self.assertNotIn('lock', core.HEADER_ONLY_DOMAINS)
        self.assertTrue(core.entity_id('lock.front_door'))
        self.assertIn('"alarm_control_panel", "lock"})', MODEL)
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
        # The firmware reads a regular expression up to 48 characters, which the app sends whole.
        self.assertIn('next.code_format = string(a["code_format"], 48);', RECEIVER)

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
        # The page document carries it as an interaction, and the editor validates the same two choices.
        self.assertEqual(page_layout.INTERACTION['guard'], 'guard')
        self.assertIn("[i.guard, domain === 'lock' ? ['confirm', 'lock_only'] : []]", VALIDATION)
        self.assertIn('tile.guard = string(options["guard"], 16); if (tile.guard.empty()) tile.guard="confirm";', RECEIVER)

    def test_a_layout_with_a_lock_waits_for_its_firmware_and_the_newest_gate_wins(self):
        self.assertEqual(core.min_firmware({'tiles': [{'entity': 'lock.front'}]}), core.LOCK_MIN_FIRMWARE)
        self.assertEqual(core.LOCK_MIN_FIRMWARE, (0, 5, 0))
        # A tilting blind (0.3.1) beside an alarm panel (0.3.3) needs 0.3.3: the newest gate, not the first one found.
        both = {'tiles': [{'entity': 'cover.a', 'options': {'controls': 'tilt'}}, {'entity': 'alarm_control_panel.a'}]}
        self.assertEqual(core.min_firmware(both), core.ALARM_MIN_FIRMWARE)
        self.assertIsNone(core.min_firmware({'tiles': [{'entity': 'light.a'}]}))


class TheFirmware(unittest.TestCase):
    def test_home_assistants_colours_icons_and_actions(self):
        # --state-lock-*-color and icons.json of the lock integration.
        for text in ('if (state == "locked") return GREEN;', 'if (moving(state)) return ORANGE;', 'return RED;',
                     'LOCK = "\\U000F033E"', 'LOCK_OPEN = "\\U000F0FC6"', 'LOCK_CLOCK = "\\U000F097F"',
                     'LOCK_ALERT = "\\U000F08EE"', '{"lock.lock", "lock.unlock", "lock.open"}'):
            self.assertIn(text, PANEL)
        self.assertIn('if (d == "lock") return state != "locked";', MODEL)
        # The editor's preview colours the same way.
        self.assertIn('if (domain === "lock") return state === "locked" ? c.GREEN', PALETTE)

    def test_the_screen_never_logs_or_keeps_a_code(self):
        lock = section()
        for line in lock.splitlines():
            if 'ESP_LOG' in line:
                self.assertNotIn('code', line.replace('alarm_card_note', ''))
        # A lock with a code opens the alarm panel's keypad, which sends the code once and wipes it (test_alarm_panel).
        self.assertIn('alarm_pad.open=true;alarm_pad.mode=act;', lock)
        self.assertIn('lock_panel::service((lock_panel::Act)alarm_pad.mode)', TILES)
        # Its wrong codes have an event of their own, with the same three values and never the code.
        self.assertIn('"esphome.screen_lock_code_refused"', TILES)

    def test_unlocking_never_goes_out_on_one_tap(self):
        lock = section()
        do = lock.split('inline void lock_do(', 1)[1].split('\n}\n', 1)[0]
        # A code comes first; then an action that confirms waits for the second tap before anything is sent.
        self.assertLess(do.index('needs_code('), do.index('if(confirms(act)){'))
        self.assertLess(do.index('const bool second=c.press(act,now);'), do.index('if(!second){'))
        self.assertLess(do.index('if(!second){'), do.index('action(service(act),t.entity);'))
        # The wait belongs to the tile (firmware 0.16.0+): a first tap ends every other tile's, so a second tap on another
        # tile of the same lock is a first tap there and never unlocks.
        self.assertLess(do.index('lock_end_asks(index);'), do.index('const bool second=c.press(act,now);'))
        self.assertIn('int8_t ask_act = -1;', MODEL)
        self.assertIn('inline bool confirms(Act a) { return a == UNLOCK || a == OPEN; }', PANEL)

    def test_a_heartbeat_travels_with_its_card(self):
        # A kept page's cards leave the glass and come back by swapping places (keep_page). The heartbeat of a lock or an
        # alarm panel belongs to the card, so a card whose lock settled while it was away does not keep beating (firmware
        # 0.16.0; a lock on several pages showed it).
        self.assertIn('uint8_t alarm_look=0; uint32_t alarm_mark=0;', TILES)
        self.assertNotIn('alarm_tile_looks', TILES)
        self.assertNotIn('alarm_tile_marks', TILES)
        look = TILES.split('inline void alarm_tile_look(', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('if(want==w.alarm_look)return;', look)
        self.assertIn('std::swap(widgets[i], (*set)[i]);', TILES)


if __name__ == '__main__':
    unittest.main()
