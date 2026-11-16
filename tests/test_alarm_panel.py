"""The alarm panel (app 0.3.8 / firmware 0.3.3): an alarm_control_panel as a tile with Home Assistant's card and code
dialog. tests/test_alarm_panel.cpp checks components/smart_display/alarm_panel.h against Home Assistant (its 2026.9
frontend and core): the modes in ALARM_MODES' order with their actions, feature bits and icons as a static_assert, every
state's colour and icon, when a code is asked, and the layouts; tests/test_tile_controls.cpp when a panel is active;
web/wasm/test_alarm_card.mjs reads the real card (the modes, the keypad, the code with the action, a refused code as an
event without it, arming at once); web/tests/layout.spec.ts the editor's colours. Here: the app's side, the top bar,
and the rules that keep a code private.
"""
from firmware_sources import firmware_domains, runtime_source
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import core  # noqa: E402
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
