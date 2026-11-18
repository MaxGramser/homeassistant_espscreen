"""The alarm panel (app 0.3.8 / firmware 0.3.3): an alarm_control_panel as a tile with Home Assistant's card and code
dialog. tests/test_alarm_panel.cpp checks components/smart_display/alarm_panel.h against Home Assistant (its 2026.9
frontend and core): the modes in ALARM_MODES' order with their actions, feature bits and icons as a static_assert, every
state's colour and icon, when a code is asked, and the layouts; tests/test_tile_controls.cpp when a panel is active;
web/wasm/test_alarm_card.mjs reads the real card (the modes, the keypad, the code with the action, a refused code as an
event without it, arming at once); web/tests/layout.spec.ts the editor's colours. Here: the app's side, the top bar,
and the rules that keep a code private.
"""
from firmware_sources import firmware_domains, runtime_source
import json
import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import alarm_screens  # noqa: E402
import core  # noqa: E402
import page_delivery  # noqa: E402
import header_bar  # noqa: E402

TILES = runtime_source()

# Home Assistant's states, their colours (--state-alarm_control_panel-*-color) and icons (icons.json of the
# integration); disarmed is inactive and grey (stateActive).
STATES = {'disarmed': (None, 'F099E'), 'armed_home': ('GREEN', 'F068A'), 'armed_away': ('GREEN', 'F099D'),
          'armed_night': ('GREEN', 'F1828'), 'armed_vacation': ('GREEN', 'F06BB'), 'armed_custom_bypass': ('GREEN', 'F0483'),
          'arming': ('ORANGE', 'F0498'), 'pending': ('ORANGE', 'F0499'), 'disarming': ('ORANGE', 'F0498'),
          'triggered': ('RED', 'F009E')}
class HomeAssistantsRules(unittest.TestCase):
    def test_the_top_bar_colours_as_home_assistant(self):
        for state, (ha_colour, _) in STATES.items():
            self.assertEqual(header_bar.accent('alarm_control_panel.house', {'state': state}), getattr(header_bar, ha_colour) if ha_colour else None, state)


class CodesStayPrivate(unittest.TestCase):
    def test_the_screen_never_logs_or_keeps_a_code(self):
        section = TILES.split('// ---- Alarm panel (firmware 0.3.3+)', 1)[1].split('// ---- History card', 1)[0]
        # Rules (the code with the action and a refusal without it are read from the real card in test_alarm_card.mjs):
        # no log line names the code, one place sends it and wipes it at once, a restart keeps the count and the time
        # left and nothing else, and an action logs its service and entity only.
        for line in section.splitlines():
            if 'ESP_LOG' in line:
                self.assertNotIn('alarm_pad.code', line, f'a log line names the code: {line.strip()}')
        self.assertEqual(section.count('"code",alarm_pad.code'), 1, 'the code is sent from one place')
        self.assertIn('"code",alarm_pad.code);\n  alarm_wipe(alarm_pad.code);', section, 'and wiped right after it')
        self.assertIn('struct AlarmSaved { uint32_t failures=0, seconds=0; };', section, 'a restart keeps the count and the time left')
        self.assertIn('ESP_LOGI("runtime_action","Sent service=%s entity=%s",service.c_str(),entity.c_str());', TILES,
                      'an action logs its service and entity, never its data')

    def test_the_app_sends_whether_a_default_code_exists_never_the_code(self):
        entry = {'options': {'alarm_control_panel': {'default_code': '4321'}}}
        extra = core.alarm_extras({'state': 'disarmed', 'attributes': {}}, entry)
        self.assertEqual(extra, {'dc': 1})
        self.assertNotIn('4321', repr(extra))
        self.assertEqual(core.alarm_extras({'state': 'disarmed', 'attributes': {}}, {'options': {}}), {})
        self.assertEqual(core.alarm_extras({'state': 'disarmed', 'attributes': {}}, None), {})


class TheApp(unittest.TestCase):
    def test_an_alarm_panel_is_a_tile(self):
        self.assertIn('alarm_control_panel', core.DOMAINS)
        self.assertNotIn('alarm_control_panel', core.HEADER_ONLY_DOMAINS)
        self.assertIn('alarm_control_panel', firmware_domains())
        self.assertTrue(core.entity_id('alarm_control_panel.house'))

    def test_the_card_gets_its_attributes(self):
        states = {'alarm_control_panel.house': {'state': 'armed_away', 'attributes': {
            'friendly_name': 'House', 'code_format': 'number', 'code_arm_required': False, 'changed_by': 'Sam',
            'supported_features': 63}}}
        message = core.state_message(0, {'entity': 'alarm_control_panel.house', 'name': ''}, states)
        self.assertEqual(message['a'], {'code_format': 'number', 'code_arm_required': False, 'changed_by': 'Sam',
                                        'supported_features': 63})

    def test_a_delay_counts_down_where_the_integration_reports_it(self):
        state = {'state': 'arming', 'attributes': {'delay': 30}, 'last_changed': '2026-09-26T10:00:00+00:00'}
        self.assertEqual(core.alarm_extras(state, None), {'ae': 1790416830, 'ad': 30})
        for delay in (None, 0, -5, True, float('nan'), 90000, '30'):
            self.assertEqual(core.alarm_extras({**state, 'attributes': {'delay': delay}}, None), {}, delay)
        self.assertEqual(core.alarm_extras({**state, 'state': 'armed_away'}, None), {})

    def test_older_firmware_waits_for_the_update(self):
        layout = {'tiles': [{'entity': 'alarm_control_panel.house', 'options': {}}]}
        self.assertEqual(core.min_firmware(layout), core.ALARM_MIN_FIRMWARE)
        self.assertGreaterEqual(tuple(int(n) for n in core.FIRMWARE_VERSION.split('.')), core.ALARM_MIN_FIRMWARE,
                                'the release that ships the alarm panel carries the firmware that draws it')


if __name__ == '__main__':
    unittest.main()


class AlarmScreens(unittest.TestCase):
    """What the screens do when an alarm goes off, set once per alarm on the Events page (alarm_screens.py,
    docs/ALARM_PANEL.md): which screens open the keypad by themselves, and after how many digits the code sends itself.
    Home Assistant reports no length of a code (only code_format), so the person says it, once for the alarm."""

    STATES = {'alarm_control_panel.house': {'state': 'disarmed', 'attributes': {'friendly_name': 'House', 'code_format': 'number'}},
              'alarm_control_panel.shed': {'state': 'disarmed', 'attributes': {}}, 'light.hall': {'state': 'on', 'attributes': {}}}

    def store(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        return alarm_screens.AlarmScreens(folder.name), folder.name

    def test_every_screen_and_the_ok_key_by_default_and_nothing_stored(self):
        store, folder = self.store()
        self.assertEqual(store.choice('alarm_control_panel.house'), {'screens': 'all', 'send_after': 'off'})
        self.assertTrue(store.wakes('alarm_control_panel.house', 'any-screen'))
        self.assertEqual(store.options('alarm_control_panel.house', 'any-screen'), {})
        self.assertEqual(store.set('alarm_control_panel.house', 'all', 'off'), {'screens': 'all', 'send_after': 'off'})
        self.assertEqual(json.loads((Path(folder) / 'alarm_screens.json').read_text())['alarms'], {})

    def test_a_choice_is_kept_and_read_again(self):
        store, folder = self.store()
        store.set('alarm_control_panel.house', ['kitchen', 'hall'], '6')
        again = alarm_screens.AlarmScreens(folder)
        self.assertEqual(again.choice('alarm_control_panel.house'), {'screens': ['hall', 'kitchen'], 'send_after': '6'})
        self.assertEqual(again.options('alarm_control_panel.house', 'hall'), {'send_after': '6'})
        self.assertEqual(again.options('alarm_control_panel.house', 'bedroom'), {'send_after': '6', 'alarm_wake': 'off'})
        for bad in (('light.hall', 'all', 'off'), ('alarm_control_panel.house', 'some', 'off'), ('alarm_control_panel.house', 'all', '3'),
                    ('alarm_control_panel.house', 'all', '10'), ('alarm_control_panel.house', [''], 'off')):
            with self.assertRaises(ValueError):
                again.set(*bad)
        self.assertEqual(list(alarm_screens.SEND_AFTER), ['off', '4', '5', '6', '7', '8'])

    def test_a_screen_gets_a_tile_without_a_cell_for_an_alarm_it_has_on_no_tile(self):
        store, _ = self.store()
        store.set('alarm_control_panel.shed', ['hall'], '4')
        placed = [{'entity': 'alarm_control_panel.house', 'slot': 0, 'options': {}}]
        self.assertEqual(store.tiles('hall', self.STATES, placed),
                         [{'entity': 'alarm_control_panel.shed', 'name': '', 'bar': True, 'options': {'send_after': '4'}}])
        self.assertEqual(store.tiles('kitchen', self.STATES, placed), [], 'the kitchen does not wake for the shed and has the house on a tile')
        self.assertEqual(store.with_options(placed[0], 'kitchen'), placed[0], 'the house keeps its defaults')
        self.assertEqual(store.with_options({'entity': 'light.hall', 'options': {}}, 'hall'), {'entity': 'light.hall', 'options': {}})

    def test_the_tiles_count_in_the_screens_memory(self):
        memory = {'tile': 100, 'extra': 50, 'psram': True, 'bar_cards': True, 'alarms': ['alarm_control_panel.house', 'alarm_control_panel.shed']}
        tiles = [{'entity': 'alarm_control_panel.house', 'slot': 0, 'options': {}}]
        with_alarm = core.layout_cost(tiles, memory)
        self.assertEqual(with_alarm - core.layout_cost(tiles, {**memory, 'alarms': []}), core.tile_cost({'entity': 'alarm_control_panel.shed'}, memory),
                         'only the alarm on no tile costs a tile')
        self.assertEqual(core.layout_cost(tiles, {**memory, 'bar_cards': False}), core.layout_cost(tiles, {**memory, 'bar_cards': False, 'alarms': []}),
                         'a screen that takes no tiles without a cell gets none')

    def test_a_layout_saved_with_the_choice_on_its_tile_loads_without_it(self):
        layout = {'title': 'Home', 'tiles': [{'entity': 'alarm_control_panel.house', 'slot': 0, 'options': {'send_after': '4'}}]}
        self.assertEqual(core.validate_layout(layout)['tiles'][0].get('options', {}), {})

    def test_the_screen_gets_the_choice_with_the_tile(self):
        message = core.state_message(0, {'entity': 'alarm_control_panel.house', 'name': '', 'options': {'send_after': '6', 'alarm_wake': 'off'}}, self.STATES)
        self.assertEqual((message['o']['send_after'], message['o']['alarm_wake']), ('6', 'off'))
        # What the screen does with them is read from the real card in web/wasm/test_alarm_card.mjs, and the range of
        # lengths it takes (4 to 8) is alarm_panel::send_after in tests/test_alarm_panel.cpp.

    def test_a_change_gives_the_screen_its_tiles_again(self):
        record = {'layout': {'pages': []}, 'sourceGrid': {'columns': 3, 'rows': 3}}
        plain = page_delivery.configuration(record, {})
        self.assertEqual(plain, page_delivery.configuration(record, {}, alarms=None))
        self.assertNotEqual(plain, page_delivery.configuration(record, {}, alarms={'alarm_control_panel.house': {'send_after': '4'}}))
