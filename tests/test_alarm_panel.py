"""The alarm panel (app 0.3.8 / firmware 0.3.3): an alarm_control_panel as a tile with Home Assistant's card and code
dialog. tests/test_alarm_panel.cpp checks the logic and the layouts of components/smart_display/alarm_panel.h; these
keep the firmware, the app and the editor in step with each other and with Home Assistant (its 2026.9 frontend and
core), and hold the rules that keep a code private.
"""
from firmware_sources import runtime_source
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import core  # noqa: E402
import header_bar  # noqa: E402

COMPONENT = ROOT / 'components/smart_display'
PANEL = (COMPONENT / 'alarm_panel.h').read_text()
MODEL = (COMPONENT / 'runtime_model.h').read_text()
TILES = runtime_source()
PALETTE = (ROOT / 'web/src/model/tile-palette.ts').read_text()

# Home Assistant's states, their colours (--state-alarm_control_panel-*-color) and icons (icons.json of the
# integration); disarmed is inactive and grey (stateActive).
STATES = {'disarmed': (None, 'F099E'), 'armed_home': ('GREEN', 'F068A'), 'armed_away': ('GREEN', 'F099D'),
          'armed_night': ('GREEN', 'F1828'), 'armed_vacation': ('GREEN', 'F06BB'), 'armed_custom_bypass': ('GREEN', 'F0483'),
          'arming': ('ORANGE', 'F0498'), 'pending': ('ORANGE', 'F0499'), 'disarming': ('ORANGE', 'F0498'),
          'triggered': ('RED', 'F009E')}
# The frontend's ALARM_MODES (src/data/alarm_control_panel.ts), in its order, with the feature bit and the action.
MODES = [('armed_home', 1, 'alarm_arm_home'), ('armed_away', 2, 'alarm_arm_away'), ('armed_night', 4, 'alarm_arm_night'),
         ('armed_vacation', 32, 'alarm_arm_vacation'), ('armed_custom_bypass', 16, 'alarm_arm_custom_bypass'),
         ('disarmed', 0, 'alarm_disarm')]


def body(source, signature):
    return source.split(signature, 1)[1].split('\n}\n', 1)[0]


class HomeAssistantsRules(unittest.TestCase):
    def test_modes_follow_the_frontend(self):
        table = re.findall(r'\{"(\w+)", "alarm_control_panel\.(\w+)", glyph::\w+, (feature::\w+|0)\}', PANEL)
        self.assertEqual([state for state, _, _ in table], [state for state, _, _ in MODES])
        self.assertEqual([action for _, action, _ in table], [action for _, _, action in MODES])
        bits = dict(re.findall(r'(\w+) = (\d+)', PANEL.split('namespace feature {', 1)[1].split('}', 1)[0]))
        for (state, bit, _), (_, _, feature) in zip(MODES, table):
            self.assertEqual(int(bits[feature.split('::')[1]]) if feature != '0' else 0, bit, state)
        # Trigger is a feature, never a key.
        self.assertNotIn('alarm_trigger', PANEL)

    def test_colours_and_icons_are_home_assistants(self):
        colour = body(PANEL, 'inline uint32_t color(const std::string &state) {')
        icon = body(PANEL, 'inline const char *icon(const std::string &state) {')
        glyphs = dict(re.findall(r'\*?(\w+) = "\\U000(F[0-9A-F]{4})"', PANEL))
        for state, (ha_colour, ha_icon) in STATES.items():
            if ha_colour == 'RED':
                self.assertIn(f'state == "{state}") return RED', colour)
            elif ha_colour == 'ORANGE':
                self.assertIn(f'"{state}"', colour.split('return ORANGE')[0].split('return RED')[-1])
            name = re.search(rf'state == "{state}"\) return glyph::(\w+)', icon)
            self.assertEqual(glyphs[name[1] if name else 'SHIELD'], ha_icon, state)
        self.assertIn('constexpr uint32_t GREEN = theme::ha::GREEN, ORANGE = theme::ha::ORANGE, RED = theme::ha::RED;', PANEL)
        # The same rule on the tile (Tile::active), in the editor's mockup and in the top bar.
        self.assertIn('if (d == "alarm_control_panel") return state != "disarmed";', MODEL)
        self.assertIn('if (domain === "alarm_control_panel") return state !== "disarmed";', PALETTE)
        self.assertIn('if (domain === "alarm_control_panel") return state === "triggered" ? c.RED : ["arming", "pending", "disarming"].includes(state) ? c.ORANGE : c.GREEN;', PALETTE)
        for state, (ha_colour, _) in STATES.items():
            self.assertEqual(header_bar.accent('alarm_control_panel.house', {'state': state}), getattr(header_bar, ha_colour) if ha_colour else None, state)

    def test_a_code_is_asked_as_the_frontend_asks_it(self):
        rule = body(PANEL, 'inline bool needs_code(const Codes &c, unsigned mode) {')
        self.assertIn('if (c.saved || c.format.empty()) return false;', rule)
        self.assertIn('return mode == DISARM || c.arm_required;', rule)


class CodesStayPrivate(unittest.TestCase):
    def test_the_screen_never_logs_or_keeps_a_code(self):
        section = TILES.split('// ---- Alarm panel (firmware 0.3.3+)', 1)[1].split('// ---- History card', 1)[0]
        for line in section.splitlines():
            if 'ESP_LOG' in line:
                self.assertNotIn('alarm_pad.code', line)
        # One place sends it, as the action's `code`, and wipes it right after.
        self.assertEqual(section.count('"code",alarm_pad.code'), 1)
        self.assertIn('action(MODES[alarm_pad.mode].service,t.entity,"code",alarm_pad.code);\n  alarm_wipe(alarm_pad.code);', section)
        # The event Home Assistant hears carries the panel, the count and the lock, never the code.
        event = body(section, 'inline void alarm_refused_event(const std::string &entity,uint32_t locked){')
        self.assertIn('{"entity_id","failures","locked"}', event)
        self.assertNotIn('code', event.replace('screen_alarm_code_refused', ''))
        # What is saved across a restart is the count and the time left.
        self.assertIn('struct AlarmSaved { uint32_t failures=0, seconds=0; };', section)
        # The action logs its service and entity only.
        self.assertIn('ESP_LOGI("runtime_action","Sent service=%s entity=%s",service.c_str(),entity.c_str());', TILES)

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
        self.assertIn('"alarm_control_panel"})', MODEL)
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
