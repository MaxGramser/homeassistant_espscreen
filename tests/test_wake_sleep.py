"""Wake, Sleep and Motion for Home Assistant automations (app 0.2.53, firmware 0.2.45; Motion firmware 0.64.0) and
what every board's YAML keeps around the screen's standby.

The standby itself is C++ and is proven by running it: components/smart_display/screen_standby.h holds the state and
every rule (lit or in standby, by the time or by hand, which wake lights the screen, the quiet a sensed wake waits for,
the order of a standby that goes to page 1), and tests/test_screen_standby.cpp runs each of them on a glass that writes
down what it was told. `tools/render/run.py guition --only standby` presses Wake and Sleep on the real firmware (a
host build) and reads its clocks and pages back. What stays here is what only the YAML can get wrong: the entities
Home Assistant sees, and that each script is one call into that file.
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
            for label in ('Wake', 'Sleep', 'Motion'):
                button = item(buttons, 'name', label)
                self.assertTrue(button, f'{name}: no {label} button')
                self.assertIn('platform: template', button, name)
                self.assertNotIn('entity_category', button, f'{name}: {label} is a control, not a setting')
                self.assertNotIn('internal', button, f'{name}: {label} must reach Home Assistant')

    def test_every_way_in_and_out_is_one_call_into_the_standby(self):
        # The names a board's key, a feature, a plugin's package and an Override YAML call: each is the standby's own
        # function and nothing beside it, so there is no second place where a rule could live.
        calls = {
            'wake_display': "screen_standby::the().wake(millis());",
            'wake_from': "screen_standby::the().wake_from(source.c_str(), screen_standby::Asker::SCRIPT, sensed, millis());",
            'standby_key': "screen_standby::the().key(millis());",
            'standby_by_hand': "screen_standby::the().standby_by_hand(source.c_str(), millis());",
            'go_home': "screen_standby::the().go_home(millis());",
        }
        for name, text in self.profiles.items():
            for script_id, call in calls.items():
                body = [line.strip() for line in script(text, script_id).split('then:', 1)[1].splitlines()
                        if line.strip() and not line.strip().startswith('#')]
                self.assertEqual(body, [f"- lambda: '{call}'"], f'{name}: {script_id} is one call')
            # The standby time and Back to page 1, every second; the home key held; a plugin's wake.
            self.assertIn("- lambda: 'screen_standby::the().tick(millis());'", section(text, 'interval'), name)
            self.assertIn('runtime_tiles::hold_home = []() { return screen_standby::the().hold_home(millis()); };', text, name)
            # A plugin's wake is sensed (tessera::wake) or an event (a popup, a call, a doorbell).
            self.assertIn('screen_standby::the().wake_from(source.c_str(), screen_standby::Asker::PLUGIN, sensed, millis());',
                          text, name)

    def test_the_standby_has_one_timer(self):
        # Every wait of the standby (the loop's next pass, the power saving of a dark screen) is one script that the
        # latest ask replaces; screen_standby::due finds what is due.
        for name, text in self.profiles.items():
            wait = script(text, 'standby_wait')
            self.assertIn('mode: restart', wait, name)
            self.assertIn('- delay: !lambda return ms;', wait, name)
            self.assertIn("- lambda: 'screen_standby::the().due(millis());'", wait, name)
            self.assertIn('glass.later = [](uint32_t ms) { id(standby_wait).execute(ms); };', text, name)
            self.assertIn('screen_power::later = [](uint32_t ms) { screen_standby::the().power_wait(ms, millis()); };',
                          text, name)

    def test_the_yaml_keeps_no_state_of_the_standby(self):
        # The state is private to screen_standby.h (the compiler keeps that); the globals and scripts that held it in
        # the YAML before are gone, and no package brings one back.
        for name, text in self.profiles.items():
            for gone in ('display_dimmed', 'sleep_requested', 'last_touch_ms', 'last_use_ms', 'touch_down', 'hand_standby',
                         'dim_display', 'go_home_now', 'back_to_page_1_when_due', 'screen_power_wait', 'APPLY_BACKLIGHT'):
                self.assertNotIn(gone, text, f'{name}: {gone} lived in the YAML before screen_standby.h')

    def test_which_wake_senses_someone(self):
        # Home Assistant's Wake is a person or an automation that means it: never held. Its Motion is someone sensed, as
        # a plugin's wake and a board that moved. The board's key is a person (screen_standby::key).
        for name, text in self.profiles.items():
            self.assertIn('sensed: false', item(section(text, 'button'), 'name', 'Wake'), name)
            self.assertIn('sensed: true', item(section(text, 'button'), 'name', 'Motion'), name)
            self.assertIn('standby_by_hand', item(section(text, 'button'), 'name', 'Sleep'), name)
            moved = script(text, 'board_moved')
            if moved:
                self.assertIn('id: wake_from', moved, name)
                self.assertIn('sensed: true', moved, f'{name}: a board moved is a sensed wake')
                self.assertNotIn('wake_button', moved, f'{name}: the board enters wake_from as what it is')

    def test_what_holds_the_screen_lit(self):
        # A calibration, an alert and a doorbell's ring (docs/DOORBELL.md) each keep the standby time, a standby by
        # hand from the home key and Back to page 1 away: the three are what the standby asks the YAML for.
        for name, text in self.profiles.items():
            owned = re.search(r'glass\.owned = \[\]\(\) -> uint8_t \{(.*?)\};', text, re.S)
            self.assertTrue(owned, name)
            for guard, bit in (('id(calibration_active)', 'screen_standby::CALIBRATION'), ('alert_life::the().up()', 'screen_standby::ALERT'),
                               ('runtime_tiles::doorbell_holds()', 'screen_standby::RING')):
                self.assertIn(f'({guard} ? {bit} : 0)', owned[1], name)

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


if __name__ == '__main__':
    unittest.main()
