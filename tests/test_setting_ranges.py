"""A screen setting has one range, written in five places (firmware 0.2.49+, docs/SETTINGS.md).

The screen owns its settings: settings_screen::set() clamps every value any writer gives it, and the settings page on
the glass steps between the same ends (settings_screen.h). Home Assistant changes them through the screen's entities,
whose min and max are in packages/core.yaml; ESP Screens validates a value with SETTING_RULES (core.py) and its
editor offers it between the ends of SETTING_GROUPS (web/src/model/settings.ts). This reads all five and checks that every
setting is the same kind and has the same ends in each, so a range changed in one place shows up here.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import SETTING_RULES  # noqa: E402

SCREEN = (ROOT / 'components/smart_display/settings_screen.h').read_text()
CORE_YAML = (ROOT / 'packages/core.yaml').read_text()
# The editor's table of the settings (SETTING_GROUPS), beside the store in its model.
SETTINGS_TS = (ROOT / 'web/src/model/settings.ts').read_text()
CORE_PY = (ROOT / 'screen_manager/app/core.py').read_text()
# The minutes of a day, the range of a night's start and end: Home Assistant's time entity (hour * 60 + minute) and the
# settings page's moment row have no ends of their own but these.
DAY = (0, 24 * 60 - 1)
# The brightness a dim level may not exceed: the firmware clamps it to the normal brightness, ESP Screens refuses a
# value above it and the editor caps it there.
CAPPED = 'brightness'


def firmware_set():
    """{key: 'bool' | (low, high)} from settings_screen::set(); a high of the normal brightness is CAPPED."""
    body = SCREEN.split('inline SetResult set(', 1)[1].split('else return SetResult::unknown;', 1)[0]
    out = {}
    for key, code in re.findall(r'key == "(\w+)"\)(.*?)(?=else if \(key ==|\Z)', body, re.S):
        if 'flag(value)' in code:
            out[key] = 'bool'
            continue
        low, high = re.search(r'std::clamp<int32_t>\(value, (-?\d+), ([\w.]+)\)', code).groups()
        out[key] = (int(low), CAPPED if high == 's.brightness' else int(high))
    return out


def page_rows():
    """{key: 'bool' | 'moment' | (low, high, step)} from the settings page's rows, and the rotations it offers."""
    out = {}
    for kind, key, low, high, step in re.findall(
            r'(number|duration)\(screen_text::txt::\w+, \[\]\(\) -> int32_t \{[^}]*\},\s*'
            r'\[\]\(int32_t value\) \{ set\("(\w+)", value\); \}, (\d+), (\d+)(?:, (\d+))?', SCREEN):
        out[key] = (int(low), int(high), int(step) if step else None)
    for key in re.findall(r'toggle\(screen_text::txt::\w+, \[\]\(\) -> int32_t \{[^}]*\},\s*'
                          r'\[\]\(int32_t value\) \{ set\("(\w+)", value\); \}', SCREEN):
        out[key] = 'bool'
    for key in re.findall(r'moment\(screen_text::txt::\w+, \[\]\(\) -> int32_t \{[^}]*\},\s*'
                          r'\[\]\(int32_t value\) \{ set\("(\w+)", value\); \}', SCREEN):
        out[key] = 'moment'
    turns = set()
    if 'set("rotation", value ? 180 : 0)' in SCREEN:
        turns |= {0, 180}
    if 'set("rotation", std::clamp<int32_t>(value, 0, 3) * 90)' in SCREEN:
        turns |= {0, 90, 180, 270}
    out['rotation'] = tuple(sorted(turns))
    return out


def entities():
    """{key: ('number', low, high, step) | ('switch',) | ('time',) | ('select', options)} from packages/core.yaml: the
    entities whose action goes through settings_screen::set()."""
    sections = [(m.start(), m.group(1)) for m in re.finditer(r'^([a-z_]+):\s*$', CORE_YAML, re.M)]
    out = {}
    for block in re.finditer(r'\n  - platform: template\n(.*?)(?=\n  - platform: |\n[a-z_]+:|\Z)', CORE_YAML, re.S):
        keys = set(re.findall(r'settings_screen::set\("(\w+)"', block.group(1)))
        if not keys:
            continue
        section = [name for start, name in sections if start < block.start()][-1]
        (key,) = keys
        text = block.group(1)
        number = lambda name: float(re.search(rf'^\s+{name}: (-?[\d.]+)\s*$', text, re.M).group(1))
        if section == 'number':
            out[key] = ('number', number('min_value'), number('max_value'), number('step'))
        elif section == 'switch':
            out[key] = ('switch',)
        elif section == 'datetime':
            out[key] = ('time',)
        elif section == 'select':
            # Every option the entity can have: the quarter turns of square glass and the half turn of the rest.
            options = re.search(r'options: \$\{ (\[.*?\]) if', text).group(1)
            out[key] = ('select', tuple(sorted(int(v) for v in re.findall(r'"(\d+)°"', options))))
        else:
            raise AssertionError(f'{key}: a setting entity in {section}:, which this test does not know')
    return out


def editor_rows():
    """{key: {kind, min, max, step, cap, options}} from SETTING_GROUPS in web/src/model/settings.ts."""
    block = SETTINGS_TS.split('export const SETTING_GROUPS = [', 1)[1].split('] as const;', 1)[0]
    out = {}
    for row in re.findall(r'\{ key: "[^{}]*\}', block):
        fields = dict(re.findall(r'(\w+): ("[^"]*"|\[[^\]]*\]|-?\d+)', row))
        value = lambda v: v.strip('"') if v.startswith('"') else [int(x) for x in re.findall(r'-?\d+', v)] if v.startswith('[') else int(v)
        out[fields['key'].strip('"')] = {name: value(v) for name, v in fields.items() if name != 'key'}
    return out


class OneRange(unittest.TestCase):
    def setUp(self):
        self.firmware, self.page, self.entities, self.editor = firmware_set(), page_rows(), entities(), editor_rows()
        # The settings the screen owns: every one ESP Screens knows, but the clock (Language & region, app 0.2.90).
        self.owned = [key for key in SETTING_RULES if key not in ('show_clock', 'clock_24h')]

    def test_every_setting_is_in_every_place(self):
        self.assertEqual(set(self.firmware), set(SETTING_RULES) - {'show_clock'})
        self.assertEqual(set(self.entities), set(self.owned))
        self.assertEqual(set(self.editor), set(self.owned))
        self.assertEqual(set(self.page), set(self.owned))

    def test_a_switch_is_a_switch_everywhere(self):
        for key in self.owned:
            if SETTING_RULES[key][1] is None:
                self.assertEqual(self.firmware[key], 'bool', key)
                self.assertEqual(self.page[key], 'bool', key)
                self.assertEqual(self.entities[key], ('switch',), key)
                self.assertEqual(self.editor[key]['kind'], 'toggle', key)
            else:
                self.assertNotEqual(self.firmware[key], 'bool', key)

    def test_a_number_has_the_same_ends_everywhere(self):
        for key in self.owned:
            _, low, high = SETTING_RULES[key]
            if low is None or key in ('rotation', 'night_start', 'night_end'):
                continue
            firmware = self.firmware[key]
            # A dim level ends at the normal brightness on the screen, whose own highest is the end everywhere else.
            ends = (firmware[0], SETTING_RULES[CAPPED][2] if firmware[1] == CAPPED else firmware[1])
            self.assertEqual((low, high), ends, f'{key}: SETTING_RULES and settings_screen::set()')
            self.assertEqual(self.page[key][:2], ends, f"{key}: the settings page's row")
            kind, entity_low, entity_high, _ = self.entities[key]
            self.assertEqual((kind, entity_low, entity_high), ('number', low, high), f"{key}: the number entity's min and max")
            row = self.editor[key]
            self.assertIn(row['kind'], ('number', 'duration'), key)
            self.assertEqual((row['min'], row['max']), ends, f"{key}: SETTING_GROUPS' min and max")
            # The editor steps as the glass does; Home Assistant's entity may be finer.
            self.assertEqual(row.get('step'), self.page[key][2], f'{key}: the step of the editor and of the settings page')

    def test_a_dim_level_never_exceeds_the_normal_brightness(self):
        capped = {key for key, value in self.firmware.items() if isinstance(value, tuple) and value[1] == CAPPED}
        self.assertEqual(capped, {'standby_brightness', 'night_brightness'})
        self.assertEqual({key for key, row in self.editor.items() if row.get('cap') == CAPPED}, capped)
        refused = re.search(r"if max\(clean\['(\w+)'\], clean\['(\w+)'\]\) > clean\['brightness'\]:", CORE_PY)
        self.assertEqual(set(refused.groups()), capped)

    def test_the_night_is_minutes_of_a_day(self):
        for key in ('night_start', 'night_end'):
            self.assertEqual(SETTING_RULES[key][1:], DAY, key)
            self.assertEqual(self.firmware[key], DAY, key)
            self.assertEqual(self.page[key], 'moment', key)
            self.assertEqual(self.entities[key], ('time',), key)
            self.assertEqual(self.editor[key]['kind'], 'moment', key)

    def test_the_turns_are_quarters(self):
        self.assertEqual(SETTING_RULES['rotation'][1:], (0, 270))
        self.assertEqual(self.firmware['rotation'], (0, 270))
        self.assertIn('std::clamp<int32_t>(value, 0, 270) / 90 * 90', SCREEN)
        self.assertIn('valid = valid and value in (0, 90, 180, 270)', CORE_PY)
        turns = (0, 90, 180, 270)
        self.assertEqual(self.page['rotation'], turns)
        self.assertEqual(self.entities['rotation'], ('select', turns))
        self.assertEqual(tuple(self.editor['rotation']['options']), turns)


if __name__ == '__main__':
    unittest.main()
