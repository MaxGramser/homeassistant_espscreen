"""Wake and Sleep buttons for Home Assistant automations (app 0.2.53, firmware 0.2.45) and the standby
code around them (tidied in app 0.2.54, firmware 0.2.46).

Both board profiles have to wire them the same way: Wake lights the screen and restarts the standby time,
Sleep is the standby time running out right away, and a Sleep holds until a tap, Wake or an alert ends it,
whatever turns Auto standby off. Since app 0.2.65 (firmware 0.2.56) Wake is no tap: Back to page 1 counts
from the last touch, so an automation pressing Wake on every motion no longer holds a card or page 2 up.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import FIRMWARE_VERSION, WAKE_SLEEP_MIN_FIRMWARE  # noqa: E402

PROFILES = ('checkout/cyd.yaml', 'checkout/guition.yaml', 'packages/cyd.yaml', 'packages/guition.yaml')


def section(text, top):
    """One top-level YAML section of a profile, up to the next one."""
    # The core and the board file may both carry the section (app 0.2.84+).
    return '\n'.join(re.findall(rf'^{top}:\n(.*?)(?=^[a-z_]+:|\Z)', text, re.M | re.S))


def item(text, key, value):
    """The list item in a section that carries `key: value`, up to the next item at the same depth."""
    chunks = re.split(r'^  - ', text, flags=re.M)[1:]
    # The item that starts with `key: value` first: a script that names another one (`id: alert_dismiss` in
    # alert_timeout) may come before that one's own block now that the board file adds scripts of its own.
    for chunk in chunks:
        if re.match(rf'{key}: "?{re.escape(value)}"?$', chunk, re.M):
            return chunk
    for chunk in chunks:
        if re.search(rf'^\s*{key}: "?{re.escape(value)}"?$', chunk, re.M):
            return chunk
    return ''


def script(text, name):
    return item(section(text, 'script'), 'id', name)


class Profiles(unittest.TestCase):
    def setUp(self):
        self.profiles = {name: profiles.text(name) for name in PROFILES}

    def test_the_firmware_that_carries_the_buttons_is_this_release_or_older(self):
        version = lambda text: tuple(int(part) for part in text.split('.'))
        self.assertLessEqual(version(WAKE_SLEEP_MIN_FIRMWARE), version(FIRMWARE_VERSION))

    def test_both_buttons_are_plain_controls_home_assistant_sees(self):
        for name, text in self.profiles.items():
            buttons = section(text, 'button')
            for label in ('Wake', 'Sleep'):
                button = item(buttons, 'name', label)
                self.assertTrue(button, f'{name}: no {label} button')
                self.assertIn('platform: template', button, name)
                self.assertNotIn('entity_category', button, f'{name}: {label} is a control, not a setting')
                self.assertNotIn('internal', button, f'{name}: {label} must reach Home Assistant')

    def test_wake_is_light_not_a_tap(self):
        for name, text in self.profiles.items():
            wake = item(section(text, 'button'), 'name', 'Wake')
            # A dimmed screen lights up the way the tap on its wake overlay does, then goes to page 1 at once when
            # that time ran out during standby; one that is on only restarts the standby time.
            self.assertRegex(wake, r"return id\(display_dimmed\);'\s+then:\s+- script\.execute: wake_display\s+"
                                   r"(?:#[^\n]*\s+)?- script\.execute: back_to_page_1_when_due\s+else:\s+"
                                   r"- lambda: 'id\(last_touch_ms\) = millis\(\);'", name)
            self.assertNotIn('last_use_ms', wake, f'{name}: Wake must not postpone Back to page 1')
            self.assertNotIn('last_use_ms', script(text, 'wake_display'), f'{name}: waking is no touch')
            self.assertIn('id(sleep_requested) = false;', script(text, 'wake_display'), f'{name}: waking ends a Sleep')
            overlay = re.search(r'id: dim_wake_overlay\n.*?on_click:\s+- script\.execute: (\w+)', text, re.S)
            self.assertEqual(overlay[1], 'wake_display', f'{name}: a tap and Wake share one path')

    def test_back_to_page_1_counts_from_the_last_touch(self):
        for name, text in self.profiles.items():
            clock = item(section(text, 'globals'), 'id', 'last_use_ms')
            self.assertIn('type: uint32_t', clock, name)
            self.assertIn('restore_value: no', clock, name)
            check = script(text, 'back_to_page_1_when_due')
            self.assertIn('if (!runtime_tiles::auto_home || id(touch_down) || id(calibration_active) || id(alert_active)) return false;', check, name)
            self.assertIn('if (id(display_dimmed)) return false;', check, f'{name}: standby keeps its page ("Also on standby")')
            self.assertRegex(check, r'return away && \(millis\(\) - id\(last_use_ms\)\) > \(uint32_t\) runtime_tiles::auto_home_seconds \* 1000UL;'
                                    r'\s+then:\s+- script\.execute: go_home', name)
            self.assertNotIn('last_touch_ms', check, f'{name}: the standby clock is not the page clock')
            # The one-second interval and Wake run it; nothing else decides about page 1 by itself.
            interval = section(text, 'interval')
            self.assertIn('- script.execute: back_to_page_1_when_due', interval, name)
            self.assertNotIn('auto_home', interval, f'{name}: one copy of the rule')
            self.assertEqual(len(re.findall(r'script\.execute: back_to_page_1_when_due', text)), 2, name)
            # Written by the boot, the three touchscreen triggers, Home Assistant opening the settings page or a page of
            # tiles (and, on the Guition, a camera) and the UI self test only; Wake, an alert ending and Auto standby
            # restart the standby time alone.
            # A board whose touchscreen triggers call the shared handler writes the page clock once, in the hook
            # the shared boot sets (runtime_tiles::touch_input::contact); a board that still carries its own
            # three lambdas writes it in each of them. Either way every trigger leads to the clock.
            touch = section(text, 'touchscreen')
            # A board that hands its touches to the shared handler, rather than one that only asks the shared
            # tree to turn a point for it (the CYD does that for its calibration wizard, firmware 0.2.92+).
            shared = 'runtime_tiles::touch_input::pressed' in touch
            # Five in the shared tree whatever the board (the boot, Home Assistant opening the settings page or a
            # page of tiles, the UI self test, an alarm panel that wakes the screen with its card, firmware 0.3.3+)
            # plus the one in the hook the shared touch handler calls; a board that kept its own three lambdas writes
            # the clock three more times.
            expected = 6 + (0 if shared else 3)
            if 'preview_camera' in text:
                expected += 1
            self.assertEqual(len(re.findall(r'id\(last_use_ms\) = millis\(\);', text)), expected, name)
            for trigger in ('on_touch', 'on_update', 'on_release'):
                # The trigger at whatever depth its touchscreen item has (the board's, or a touch feature's !extend).
                body = re.search(rf'^( +){trigger}:\n(.*?)(?=^\1[a-z_]+:|^\S|\Z)', touch, re.M | re.S)[2]
                self.assertIn('id(last_use_ms) = millis();' if not shared else 'runtime_tiles::touch_input::',
                              body, f'{name}: {trigger}')
            if shared:
                contact = re.search(r'touch_input::contact = \[\]\(bool down\) \{(.*?)\};', text, re.S)
                self.assertTrue(contact, f'{name}: the shared handler needs the clock hook')
                self.assertIn('id(last_use_ms) = millis();', contact[1], name)
            for opened in ('open_settings', 'show_page'):
                self.assertIn('id(last_use_ms) = millis();', re.search(rf'- action: {opened}\n(.*?)- action:', text, re.S)[1], f'{name}: {opened}')
            self.assertIn('id(last_use_ms) = millis();', script(text, 'ui_self_test'), name)
            for quiet in (script(text, 'alert_dismiss'), item(section(text, 'switch'), 'name', 'Auto standby')):
                self.assertIn('id(last_touch_ms) = millis();', quiet, name)
                self.assertNotIn('last_use_ms', quiet, name)

    def test_sleep_dims_now_and_holds_with_auto_standby_off(self):
        for name, text in self.profiles.items():
            sleep = item(section(text, 'button'), 'name', 'Sleep')
            # Not during a touch calibration (said in the log); otherwise the flag, a closed alert, then the dim.
            self.assertRegex(sleep, r"return id\(calibration_active\);'\s+then:\s+- lambda: 'ESP_LOGI\(\"standby\", \"Sleep from Home Assistant ignored", name)
            steps = re.findall(r'script\.execute:(?:\s+id:)?\s+(\w+)|(id\(sleep_requested\) = true;)', sleep.split('else:', 1)[1])
            self.assertEqual([step[0] or 'flag' for step in steps], ['flag', 'alert_dismiss', 'dim_display'], name)
            self.assertIn('reason: "remote"', sleep, f'{name}: HA hears the alert was closed from Home Assistant')
            apply = script(text, 'apply_screen_settings')
            self.assertIn('if (id(display_dimmed) && !settings.standby_enabled && !id(sleep_requested)) {', apply,
                          f'{name}: the minute tick must not undo a Sleep')
            self.assertEqual(len(re.findall(r'id\(sleep_requested\) = true;', text)), 1, f'{name}: only the button starts a Sleep')

    def test_standby_has_one_way_in(self):
        for name, text in self.profiles.items():
            # dim_display decides nothing itself: the interval asks for Auto standby, the Sleep button sets the flag.
            dim = script(text, 'dim_display')
            self.assertRegex(dim, r"then:\s+- lambda: \|-\s+id\(display_dimmed\) = true;\s+id\(apply_screen_settings\)\.execute\(\);\s+- if:", name)
            self.assertRegex(dim, r"return screen_settings::current\.home_on_standby;'\s+then:\s+- script\.execute: go_home\s+else:\s+"
                                  r"- lambda: 'settings_screen::close\(\);'\s+- script\.execute: close_cards", name)
            self.assertNotIn('lvgl.widget.hide', dim, f'{name}: cards close through close_cards')
            callers = re.findall(r'script\.execute: dim_display', text)
            self.assertEqual(len(callers), 2, f'{name}: the standby interval and the Sleep button')
            interval = re.search(r'if \(!screen_settings::current\.standby_enabled\) return false;\s+'
                                 r'if \(id\(display_dimmed\) \|\| id\(touch_down\) \|\| id\(calibration_active\) \|\| id\(alert_active\)\) return false;\s+'
                                 r'return \(millis\(\) - id\(last_touch_ms\)\) > [^\n]+\n\s+then:\s+- script\.execute: dim_display', text)
            self.assertTrue(interval, f'{name}: the standby time only dims with Auto standby on')

    def test_every_card_closes_through_dismiss(self):
        for name, text in self.profiles.items():
            body = [line.strip() for line in script(text, 'close_cards').split('then:', 1)[1].splitlines()
                    if line.strip() and not line.strip().startswith('#')]
            self.assertEqual(body, ["- lambda: 'if (runtime_tiles::dismiss) runtime_tiles::dismiss();'"], name)
            dismiss = re.search(r'runtime_tiles::dismiss = \[\]\(\) \{(.*?)\};', text, re.S)[1]
            # hide_detail() closes every computed card, the light and fan card among them since 0.2.80.
            for step in ('runtime_tiles::hide_detail();', 'id(active_entity).clear();',
                         'id(color_detail_overlay)'):
                self.assertIn(step, dismiss, name)

    def test_the_backlight_belongs_to_the_firmware(self):
        for name, text in self.profiles.items():
            light = item(section(text, 'light'), 'id', 'back_light')
            self.assertIn('platform: monochromatic', light, name)
            self.assertIn('internal: true', light, f'{name}: Home Assistant would fight standby over it')

    def test_the_flag_starts_false_and_is_never_saved(self):
        for name, text in self.profiles.items():
            flag = item(section(text, 'globals'), 'id', 'sleep_requested')
            self.assertIn('type: bool', flag, name)
            self.assertIn('restore_value: no', flag, name)
            self.assertIn("initial_value: 'false'", flag, name)

    def test_only_a_tap_wake_or_an_alert_end_a_sleep(self):
        for name, text in self.profiles.items():
            # wake_display is the one place that clears the flag; Auto standby, from any side, leaves it alone.
            self.assertEqual(len(re.findall(r'id\(sleep_requested\) = false;', text)), 1, name)
            self.assertIn('id(sleep_requested) = false;', script(text, 'wake_display'), name)
            self.assertNotIn('sleep_requested', item(section(text, 'switch'), 'name', 'Auto standby'), name)


if __name__ == '__main__':
    unittest.main()
