"""Wake and Sleep buttons for Home Assistant automations (app 0.2.53, firmware 0.2.45) and the standby
code around them (tidied in app 0.2.54, firmware 0.2.46).

Wake lights the screen and restarts the standby time, Sleep is the standby time running out right away, and a Sleep
holds until a tap, Wake or an alert ends it, whatever turns Auto standby off. Since app 0.2.65 (firmware 0.2.56) Wake
is no tap: Back to page 1 counts from the last touch, so an automation pressing Wake on every motion no longer holds a
card or page 2 up. What the firmware does is proven by running it: `tools/render/run.py guition --only standby` presses
Wake and Sleep on the real firmware (a host build) and reads its clocks and pages back; the colour card closing with
every card is web/wasm/test_colour_card.mjs. What stays here are the rules every board keeps.
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

PROFILES = {board: profile for board, _, profile in profiles.BOARD_TABLE}


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
    @classmethod
    def setUpClass(cls):
        cls.profiles = {board: profiles.text(profile) for board, profile in PROFILES.items()}

    def test_the_firmware_that_carries_the_buttons_is_this_release_or_older(self):
        version = lambda text: tuple(int(part) for part in text.split('.'))  # noqa: E731
        self.assertLessEqual(version(WAKE_SLEEP_MIN_FIRMWARE), version(FIRMWARE_VERSION))

    def test_both_buttons_are_plain_controls_home_assistant_sees(self):
        # Automations press them (README), so every board has both, as controls Home Assistant shows.
        for name, text in self.profiles.items():
            buttons = section(text, 'button')
            for label in ('Wake', 'Sleep'):
                button = item(buttons, 'name', label)
                self.assertTrue(button, f'{name}: no {label} button')
                self.assertIn('platform: template', button, name)
                self.assertNotIn('entity_category', button, f'{name}: {label} is a control, not a setting')
                self.assertNotIn('internal', button, f'{name}: {label} must reach Home Assistant')

    def test_every_wake_that_is_not_a_finger_takes_wake_from(self):
        # Home Assistant's button, a board's sensor (it presses that button) and a plugin (tessera::wake through
        # plugin_host::wake) wake the screen one way, the script wake_from (plugin API 0.16).
        for name, text in self.profiles.items():
            self.assertEqual(len(re.findall(r'id\(wake_from\)|id: wake_from$', text, re.M)), 3,
                             f'{name}: wake the screen through the script wake_from, from the Wake button and '
                             f'plugin_host::wake only; a board\'s sensor presses the Wake button')

    def test_one_way_into_standby_and_one_out_of_a_sleep(self):
        for name, text in self.profiles.items():
            self.assertEqual(len(re.findall(r'script\.execute: dim_display', text)), 2,
                             f'{name}: only the standby interval and the Sleep button run dim_display')
            self.assertEqual(len(re.findall(r'id\(sleep_requested\) = true;', text)), 1, f'{name}: only the Sleep button starts a Sleep')
            self.assertEqual(len(re.findall(r'id\(sleep_requested\) = false;', text)), 1, name)
            self.assertIn('id(sleep_requested) = false;', script(text, 'wake_display'),
                          f'{name}: only wake_display, the way every wake and tap takes, ends a Sleep')
            self.assertEqual(len(re.findall(r'script\.execute: back_to_page_1_when_due', text)), 2,
                             f'{name}: only the one-second interval and Wake decide about page 1')
            # The standby time dims only with Auto standby on, never under a finger, a calibration, an alert or a
            # doorbell's ring (docs/DOORBELL.md): each of those holds the screen lit.
            interval = re.search(r'standby_enabled\) return false;(.*?)then:\s+- script\.execute: dim_display', text, re.S)
            self.assertTrue(interval, f'{name}: the standby interval asks Auto standby first')
            for guard in ('id(touch_down)', 'id(calibration_active)', 'id(alert_active)', 'runtime_tiles::doorbell_holds()'):
                self.assertIn(guard, interval[1], f'{name}: the standby interval must hold the screen lit for {guard}')

    def test_every_card_closes_through_dismiss(self):
        # One way to close every card: close_cards (standby) asks runtime_tiles::dismiss, which hides every card.
        for name, text in self.profiles.items():
            body = [line.strip() for line in script(text, 'close_cards').split('then:', 1)[1].splitlines()
                    if line.strip() and not line.strip().startswith('#')]
            self.assertEqual(body, ["- lambda: 'if (runtime_tiles::dismiss) runtime_tiles::dismiss();'"],
                             f'{name}: close_cards closes through runtime_tiles::dismiss only')
            dismiss = re.search(r'runtime_tiles::dismiss = \[\]\(\) \{(.*?)\};', text, re.S)[1]
            self.assertIn('runtime_tiles::hide_detail();', dismiss, f'{name}: dismiss closes every card through hide_detail')

    def test_the_backlight_belongs_to_the_firmware(self):
        for name, text in self.profiles.items():
            light = item(section(text, 'light'), 'id', 'back_light')
            self.assertIn('internal: true', light, f'{name}: keep back_light internal, or Home Assistant fights standby over it')

    def test_the_clocks_and_the_flag_start_over_with_every_boot(self):
        for name, text in self.profiles.items():
            for flag in ('sleep_requested', 'last_use_ms'):
                self.assertIn('restore_value: no', item(section(text, 'globals'), 'id', flag),
                              f'{name}: {flag} starts over with every boot, never saved')
            # glass: on a CYD calibrating its touch, press Sleep in Home Assistant: the crosshairs stay lit.
            self.assertIn('return id(calibration_active);', item(section(text, 'button'), 'name', 'Sleep'), name)


if __name__ == '__main__':
    unittest.main()
