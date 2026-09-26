"""The alert a Home Assistant action puts over the whole screen: both board profiles and both remote packages."""
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
import tile_icons  # noqa: E402

PROFILES = {'cyd': 'checkout/cyd.yaml', 'guition': 'checkout/guition.yaml'}
PACKAGES = {'cyd': 'packages/cyd.yaml', 'guition': 'packages/guition.yaml'}
FIELDS = [('title', 'string'), ('subtitle', 'string'), ('icon', 'string'), ('color', 'string'), ('button_text', 'string'), ('timeout', 'int'), ('flash', 'bool')]

def section(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]

def script(text, name):
    """One script block without its trailing comment lines, which introduce the next script."""
    return re.sub(r'^\s*#.*\n?', '', section(text, f'  - id: {name}\n', '\n  - id: '), flags=re.M)

class AlertTests(unittest.TestCase):
    def sources(self):
        for name in list(PROFILES.values()) + list(PACKAGES.values()):
            yield name, profiles.text(name)

    def test_action_takes_the_six_fields_and_hands_them_to_one_script(self):
        for name, text in self.sources():
            block = section(text, '    - action: show_alert\n', '    - action: show_alert_choice\n')
            self.assertEqual(re.findall(r'^        (\w+): (\w+)$', block, re.M), FIELDS, name)
            self.assertIn('id: alert_show', block, name)
            for field, _ in FIELDS:
                self.assertIn(f"{field}: !lambda 'return {field};'", block, name)
            remote = text.split('    - action: dismiss_alert\n', 1)[1][:200]
            self.assertIn('id: alert_dismiss', remote, name)
            self.assertIn('reason: "remote"', remote, name)

    def test_show_alert_choice_takes_the_seven_fields_and_three_more(self):
        # A second button and button colours (firmware 0.3.3+) come in an action of their own: Home Assistant makes every
        # field required, so show_alert keeps its seven and passes the new ones empty.
        choice = FIELDS[:5] + [('button_color', 'string'), ('button2_text', 'string'), ('button2_color', 'string')] + FIELDS[5:]
        for name, text in self.sources():
            plain = section(text, '    - action: show_alert\n', '    - action: show_alert_choice\n')
            for field in ('button_color', 'button2_text', 'button2_color'):
                self.assertIn(f'{field}: ""', plain, name)
            block = section(text, '    - action: show_alert_choice\n', '    - action: dismiss_alert\n')
            self.assertEqual(re.findall(r'^        (\w+): (\w+)$', block, re.M), choice, name)
            for field, _ in choice:
                self.assertIn(f"{field}: !lambda 'return {field};'", block, name)
            top = section(section(text, '\nlvgl:\n', '\nscript:\n'), '  top_layer:\n', '  pages:\n')
            second = section(top, 'id: alert_button2\n', 'id: alert_button2_label')
            self.assertIn('hidden: true', second, name)
            self.assertIn('screen_input::touch_guard.accept(millis(), 13)', second, name)
            self.assertIn('reason: "button2"', second, name)
            show = script(text, 'alert_show')
            self.assertLess(show.index('runtime_tiles::alert_two_buttons'), show.index('runtime_tiles::alert_place(false);'), name)

    def test_overlay_lives_on_the_top_layer_above_every_page(self):
        for name, text in self.sources():
            lvgl = section(text, '\nlvgl:\n', '\nscript:\n')
            self.assertLess(lvgl.index('  top_layer:\n'), lvgl.index('  pages:\n'), name)
            top = section(lvgl, '  top_layer:\n', '  pages:\n')
            for widget in ('alert_overlay', 'alert_card', 'alert_icon', 'alert_title', 'alert_subtitle', 'alert_ok', 'alert_ok_label'):
                self.assertIn(f'id: {widget}\n', top, (name, widget))
            self.assertIn('hidden: true', section(top, 'id: alert_overlay\n', 'widgets:'), name)
            self.assertIn(f'text: "\\U000{tile_icons.GLYPHS["alert-outline"]}"', top, name)
            self.assertIn('long_mode: DOT', section(top, 'id: alert_title\n', 'id: alert_subtitle'), name)
            # The subtitle wraps over the whole lines it has and ends in an ellipsis when its text is longer (0.2.103+).
            self.assertIn('long_mode: DOT', section(top, 'id: alert_subtitle\n', 'id: alert_ok\n'), name)
            ok = section(top, 'id: alert_ok\n', 'widgets:')
            self.assertIn('lv_label_set_text(id(alert_ok_label), alert.button.c_str());', script(text, 'alert_show'), name)
            self.assertIn('screen_input::touch_guard.accept(millis(), 13)', ok, name)
            self.assertLess(ok.index('touch_guard.accept'), ok.index('id: alert_dismiss'), name)
            self.assertIn('reason: "ok"', ok, name)

    def test_title_is_one_line_high_so_a_long_title_ends_in_an_ellipsis(self):
        # LVGL 9.5 only puts the ellipsis on a DOT label whose wrapped text is taller than the label. Without a height
        # the label grows with its lines instead, and a long title ran into the subtitle.
        for name, text in self.sources():
            top = section(section(text, '\nlvgl:\n', '\nscript:\n'), '  top_layer:\n', '  pages:\n')
            title = section(top, 'id: alert_title\n', 'id: alert_subtitle')
            self.assertIn('long_mode: DOT\n', title, name)
            self.assertIn('text_font: headline\n', title, name)
        # The height is the title font's own line (firmware 0.2.103+): screen_alert::layout takes it from the font the
        # label draws with, on every board, so no board can state one that is off by a pixel.
        tiles = runtime_source()
        self.assertIn('lv_font_get_line_height(lv_obj_get_style_text_font(p.title, LV_PART_MAIN))', tiles)
        self.assertIn('lv_obj_set_size(p.title, l.text_w, l.title_h);', tiles)
        header = (ROOT / 'components/smart_display/alert_overlay.h').read_text()
        self.assertIn('l.title_h = title_line;', header)

    def test_standby_waits_and_no_other_path_closes_the_card(self):
        for name, text in self.sources():
            guard = re.search(r'if \(id\(display_dimmed\) \|\| id\(touch_down\) \|\| id\(calibration_active\)([^\n]*)\) return false;', text)
            self.assertIsNotNone(guard, name)
            self.assertIn('|| id(alert_active)', guard[1], name)
            for other in ('close_cards', 'dim_display', 'wake_display', 'apply_screen_settings'):
                self.assertNotIn('alert', script(text, other), (name, other))
            dismiss = script(text, 'alert_dismiss')
            self.assertIn('id(alert_active) = false;', dismiss, name)
            self.assertIn('id(last_touch_ms) = millis();', dismiss, name)
            for stopped in ('alert_timeout', 'alert_flash'):
                self.assertIn(f'script.stop: {stopped}', dismiss, name)
            self.assertIn('screen_settings::current.brightness', dismiss, name)

    def test_every_ending_reports_to_home_assistant_but_the_self_test_does_not(self):
        for name, text in self.sources():
            report = script(text, 'alert_report')
            self.assertIn('event: esphome.screen_alert', report, name)
            for key in ('action', 'title', 'screen'):
                self.assertRegex(report, rf'(?m)^\s+{key}: !lambda', name)
            self.assertIn('id: alert_report', script(text, 'alert_dismiss'), name)
            self.assertIn('reason: "timeout"', script(text, 'alert_timeout'), name)
            show = script(text, 'alert_show')
            self.assertIn('id(alert_report).execute("replaced")', show, name)
            self.assertIn('screen_alert::make(title, subtitle, icon, color, button_text, timeout, flash, ${ALERT_TITLE_MAX}, ${ALERT_SUBTITLE_MAX}, ${ALERT_BUTTON_MAX}, button2_text, button_color, button2_color)', show, name)
            self.assertLess(show.index('script.execute: wake_display'), show.index('lvgl.widget.show: alert_overlay'), name)
            self.assertLess(show.index('lvgl.widget.show: alert_overlay'), show.index('script.execute: alert_flash'), name)
            self_test = section(text, '  - id: ui_self_test\n', '\n  - id: ')
            self.assertIn('lvgl.widget.show: alert_overlay', self_test, name)
            self.assertIn('lvgl.widget.hide: alert_overlay', self_test, name)
            for forbidden in ('alert_show', 'alert_dismiss', 'homeassistant.event'):
                self.assertNotIn(forbidden, self_test, name)

    def test_flash_blinks_four_times_and_the_card_fits_the_screen(self):
        for name, text in self.sources():
            flash = script(text, 'alert_flash')
            self.assertIn('count: 4', flash, name)
            self.assertEqual(flash.count('delay:'), 2, name)
            values = profiles.substitutions(name)
            v = lambda key: int(values[key])
            self.assertGreater(v('ALERT_TITLE_MAX'), 0, name)
            self.assertGreater(v('ALERT_BUTTON_MAX'), 0, name)
            self.assertGreater(v('ALERT_SUBTITLE_MAX'), v('ALERT_TITLE_MAX'), name)
        # The card fits every board's glass, lying down and standing up, with its words above its button
        # (screen_alert::layout, which screen_manager/app/alert_layout.py mirrors and tests/test_alert_layout.py keeps alike).
        import alert_layout
        import font_metrics
        core = profiles.CORE.read_text()
        shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        for board in profiles.BOARDS:
            values = profiles.board_values(board)
            title = font_metrics.line_height(ROOT / font_metrics.font_file(core, 'headline'), int(values['FONT_HEADLINE_SIZE']))
            sub = font_metrics.line_height(ROOT / font_metrics.font_file(core, 'sublabel_big'), int(values['FONT_SUBLABEL_BIG_SIZE']))
            for way, side in shapes[board]['orientations'].items():
                card = alert_layout.layout(side['width'], side['height'], title, sub, False,
                                           round(float(values['DISPLAY_DPI'])), values['LOOK'])
                where = f'{board} {way}'
                self.assertLessEqual(card.card_w, side['width'] - 16, where)
                self.assertLessEqual(card.card_h, side['height'] - 16, where)
                self.assertLessEqual(card.text_x + card.text_w, card.card_w - card.icon_x, where)
                self.assertGreaterEqual(card.subtitle_h, 2 * sub, where)
                self.assertLessEqual(card.subtitle_y + card.subtitle_h, card.card_h - card.button_inset - card.button_h, where)

    def test_helper_header_is_included_locally_and_in_the_remote_package(self):
        header = '    - <esphome/components/smart_display/alert_overlay.h>\n'
        for board, name in PROFILES.items():
            self.assertIn(header, profiles.text(name), name)
            self.assertIn(header, profiles.text(PACKAGES[board]), board)

if __name__ == '__main__':
    unittest.main()
