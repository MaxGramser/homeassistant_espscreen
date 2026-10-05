"""Colours live in one place, and Dark mode reaches every screen (app 0.2.63 / firmware 0.2.54).

components/smart_display/theme.h holds every colour the firmware chooses: roles with a light and a dark value, the named
card colours and Home Assistant's state colours. The board profiles name paints (shared LVGL styles theme.h fills) and
the firmware asks theme.h for roles, so a new look is a refill of a few styles plus one redraw. These tests keep it that
way: no colour written anywhere else, every paint defined and filled, and the look applied at boot and after
every settings change. tests/test_theme.cpp checks the values themselves.
"""
from firmware_sources import runtime_source
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import DARK_MODE_MIN_FIRMWARE, FIRMWARE_VERSION, SETTING_ENTITIES, SETTING_RULES, SETTINGS_BESIDE_BLOCK  # noqa: E402

COMPONENT = ROOT / 'components/smart_display'
THEME = (COMPONENT / 'theme.h').read_text()
PROFILES = list(profiles.NAMES)
HEX = re.compile(r'0x[0-9A-Fa-f]{6}\b')
# What may still carry a number that looks like a colour: the light's colour picker shows the colours a light can take,
# a mask and a codepoint check are no colours, and the value card's colour key is a wheel of fixed hues.
ALLOWED_IN_FIRMWARE = {
    'light_controls.h': ('constexpr uint32_t WARM = 0xFF9C32, COOL = 0xC6E6FF;',
                         'inline constexpr uint32_t RAINBOW[] = {0xFF0000, 0xFFFF00, 0x00FF00, 0x00FFFF, 0x0000FF, 0xFF00FF, 0xFF0000};'),
    'tile_icon.h': ('if (cp < 0x10000 || cp > 0x10FFFF) return {};',),
    'runtime_tiles.h': ('accent=lv_color_to_u32(lv_color_hsv_to_rgb(t.hue%360,t.saturation<40?40:t.saturation,100))&0xFFFFFF;',),
}
# The eight hues of the rainbow key the brightness overlay carried, until firmware 0.2.80 removed it. Kept as a
# reminder of what a profile is no longer allowed to write; the colour card draws its wheel from theme.h.
COLOUR_WHEEL = {'0xFF3B30', '0xFF9500', '0xFFD60A', '0x30D158', '0x32D6FF', '0x0A84FF', '0x5856D6', '0xBF5AF2'}


def paint_names():
    block = re.search(r'enum class Paint : uint8_t \{(.*?)\};', THEME, re.S)[1]
    return [name.strip() for name in block.replace('\n', ' ').split(',') if name.strip() and name.strip() != 'COUNT']


class OnePlace(unittest.TestCase):
    def test_no_header_writes_a_colour_of_its_own(self):
        for path in sorted(COMPONENT.glob('*.h')):
            if path.name == 'theme.h':
                continue
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if HEX.search(line):
                    self.assertIn(line.strip(), ALLOWED_IN_FIRMWARE.get(path.name, ()), f'{path.name}:{number}: a colour outside theme.h')

    def test_no_profile_writes_a_colour_of_its_own(self):
        for path in PROFILES:
            text = profiles.text(path)
            # Since firmware 0.2.80 there is no fixed hue left in a profile at all: the rainbow key of the old
            # brightness overlay carried the last eight (COLOUR_WHEEL), and it went with that overlay. Every
            # colour a screen draws now comes from theme.h, which is what this test was always driving at.
            self.assertEqual(HEX.findall(text), [], f'{path}: a colour outside theme.h')
            self.assertNotIn('BG_TOP_COLOR', text)
            self.assertNotIn('ACCENT_AUTO', text)
            self.assertNotRegex(text, r'^\s+(bg|text|border|bg_grad|line|outline|shadow)_color:', path)

    def test_every_role_has_a_light_and_a_dark_value(self):
        roles = re.search(r'enum Role : uint8_t \{(.*?)ROLE_COUNT', THEME, re.S)[1]
        names = re.findall(r'^\s+([A-Z][A-Z0-9_]*),', roles, re.M)
        values = re.findall(r'/\* (\w+) \*/\s+\{0x([0-9A-F]{6}), 0x([0-9A-F]{6})\}', THEME)
        self.assertEqual(names, [name for name, _, _ in values], 'the table follows the enum, one row per role')
        self.assertGreater(len(names), 40)


class Paints(unittest.TestCase):
    def test_every_paint_is_defined_adopted_and_used_in_every_profile(self):
        paints = paint_names()
        for path in PROFILES:
            text = profiles.merged(path)
            defined = re.findall(r'^    - id: (paint_\w+)$', text, re.M)
            used = set(re.findall(r'styles: (paint_\w+)$', text, re.M))
            filling = text.split('theme::paints = []() {', 1)[1].split('\n          };', 1)[0]
            explicit = re.findall(r'theme::fill\(id\((\w+)\), Paint::(\w+)\);', filling)
            listed = re.search(r'for \(auto \*style : \{([^}]*)\}\) theme::fill\(style, Paint::(\w+)\);', filling)
            looped = [(name, listed[2]) for name in re.findall(r'id\((\w+)\)', listed[1])]
            adopted = dict(explicit + looped)
            self.assertEqual(len(adopted), len(explicit) + len(looped), f'{path}: every style is filled once')
            self.assertEqual(text.count('theme::fill('), len(explicit) + 1, f'{path}: styles are filled in theme::paints only')
            self.assertEqual(set(defined), used, f'{path}: every paint style is used, every used one defined')
            for style in defined + ['style_page', 'style_tile', 'style_icon_circle', 'style_room', 'style_time', 'style_title',
                                    'style_value', 'style_value_big']:
                self.assertIn(style, adopted, f'{path}: {style} takes its colours from theme.h')
                self.assertIn(adopted[style], paints, f'{path}: {style}')
            for style, paint in adopted.items():
                if style.startswith('paint_'):
                    self.assertEqual(style, f'paint_{paint}', f'{path}: a paint style is named after its paint')
            # The styles that carry colours have none written down.
            styles = re.search(r'^  style_definitions:\n(.*?)^  # ---------- ALERT', text, re.M | re.S)[1]
            self.assertNotRegex(styles, r'_color:', path)

    def test_the_look_is_applied_at_boot_after_a_change_and_drawn_again(self):
        for path in PROFILES:
            text = profiles.text(path)
            boot = text.split('runtime_tiles::load_settings();', 1)[1].split('runtime_tiles::settings_changed', 1)[0]
            self.assertIn('theme::paints();\n          theme::set_dark(settings_screen::dark_mode != 0);', boot,
                          f'{path}: the paints filled, then the saved look, before the first frame')
            apply = text.split('  - id: apply_screen_settings\n', 1)[1].split('\n  - id: ', 1)[0]
            self.assertIn('theme::set_dark(settings_screen::dark_mode != 0);', apply, f'{path}: a change of the setting')
            redraw = text.split('theme::redraw = []() {', 1)[1].split('};', 1)[0]
            # The computed cards (the thermostat, the blind, the robot) are drawn again by runtime_tiles::restyle.
            for needle in ('runtime_tiles::restyle();', 'light_controls::restyle();', 'settings_screen::restyle();',
                           'theme::surface(id(alert_card_color))'):
                self.assertIn(needle, redraw, f'{path}: {needle}')
            self.assertIn('id(alert_card_color) = alert.color;', text)
            self.assertIn('lv_color_hex(theme::surface(alert.color))', text)

    def test_the_firmware_draws_long_lived_parts_with_paints(self):
        tiles = runtime_source()
        for needle in ('lv_obj_add_style(w.slider,theme::style(theme::Paint::knob),LV_PART_KNOB);',
                       'lv_obj_add_style(w.busy,theme::style(theme::Paint::veil),0);',
                       'lv_obj_add_style(spinner, theme::style(theme::Paint::spinner), LV_PART_MAIN);',
                       'inline void restyle() {'):
            self.assertIn(needle, tiles)
        self.assertIn('lv_obj_add_style(part, theme::style(theme::Paint::slate), 0);',
                      (COMPONENT / 'page_header.h').read_text())
        # Dark mode is kept in a preference of its own, next to the others outside the frozen settings block.
        self.assertIn('make_preference<uint32_t>(0x44524B31)', tiles)
        self.assertIn('inline void restyle() {', (COMPONENT / 'settings_screen.h').read_text())
        self.assertIn('inline void restyle() {', (COMPONENT / 'light_controls.h').read_text())


class RedrawnTheSame(unittest.TestCase):
    """A change of look draws again what was drawn, and the renders compare a screen that switched with one that
    booted in that look. Two differences they found were older than Dark mode: what a page showed depended on the
    order it was drawn in."""

    def test_a_switch_knob_follows_the_size_it_was_given(self):
        page = (COMPONENT / 'settings_screen.h').read_text()
        move = page.split('inline void move_knob(', 1)[1].split('\n}\n', 1)[0]
        # draw() ends in refresh() before LVGL has laid the new rows out, when coordinates still read 0.
        self.assertNotIn('lv_obj_get_width', move)
        self.assertNotIn('lv_obj_get_height', move)
        self.assertIn('knob_x(lv_obj_get_style_width(track, LV_PART_MAIN), lv_obj_get_style_height(track, LV_PART_MAIN), on)', move)
        pill = page.split('inline lv_obj_t *pill(', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('plain(track, knob_x(w, h, on), inset, size, size)', pill)

    def test_the_sun_path_keeps_its_own_fill_after_a_palette_change(self):
        tiles = runtime_source()
        self.assertIn('w.fill_color=lv_color_hex(theme::ha::SUNNY);', tiles)
        self.assertIn('if(w.extra_mode!="sunpath")w.fill_color=color;', tiles)
        self.assertEqual(len(re.findall(r'\bw\.fill_color=', tiles)), 2, 'the sun path and the palette are the only two')


class Setting(unittest.TestCase):
    def test_dark_mode_is_a_setting_the_screen_owns(self):
        self.assertEqual(SETTING_RULES['dark_mode'], (False, None, None))
        self.assertIn('dark_mode', SETTINGS_BESIDE_BLOCK, 'never inside the eleven-key block older firmware insists on')
        self.assertEqual(SETTING_ENTITIES['dark_mode'], ('switch', 'Dark mode'))
        self.assertEqual(DARK_MODE_MIN_FIRMWARE, '0.2.54')
        self.assertLessEqual(tuple(map(int, DARK_MODE_MIN_FIRMWARE.split('.'))), tuple(map(int, FIRMWARE_VERSION.split('.'))))
        page = (COMPONENT / 'settings_screen.h').read_text()
        self.assertIn('toggle(screen_text::txt::settings_dark_mode, []() -> int32_t { return dark_mode; },', page)
        self.assertIn('else if (key == "dark_mode") reported = dark_mode = flag(value);', page)
        editor = (ROOT / 'web/src/store.ts').read_text()
        self.assertIn('{ key: "dark_mode", kind: "toggle" },', editor)
        texts = json.loads((ROOT / 'screen_manager/translations/en.json').read_text(encoding='utf-8'))['editor']
        self.assertEqual(texts['screen_settings']['rows']['dark_mode'], 'Dark mode')
        brightness = editor.split('{ group: "brightness"', 1)[1].split('] },', 1)[0]
        self.assertLess(brightness.index('"brightness"'), brightness.index('"dark_mode"'), 'right under Brightness, as on the screen')
        self.assertLess(brightness.index('"dark_mode"'), brightness.index('"standby_enabled"'))


if __name__ == '__main__':
    unittest.main()
