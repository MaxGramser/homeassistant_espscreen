"""Swipe between pages: on for a new screen, as it was for a screen that is out there.

A screen keeps its choice in a preference of its own (runtime_tiles::load_settings, key 0x53575031), but a screen
whose settings were never changed stores none, and every screen set up before had swiping off. A firmware default of
on turned it on for all of those with the update (the bench upgrade test of 0.4.89). So the firmware's own default
stays off, and the start value comes from the screen's YAML: SWIPE_PAGES_DEFAULT, "0" in the core, "1" in the YAML
New screen writes. A screen known before has a YAML without the line and keeps off; a stored choice wins either way.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))
import profiles  # noqa: E402
import core  # noqa: E402

# A screen's YAML as New screen wrote it up to app 0.4.89, frozen here (with made-up keys): what every screen that is
# out there builds from when it updates.
KNOWN_BEFORE = '''# Keep this file safe: it contains the unique keys for this screen.
# Wi-Fi comes from the secrets.yaml of ESPHome Device Builder.
substitutions:
  DEVICE_NAME: "hall"
  DEVICE_FRIENDLY_NAME: "Hall"
  LANGUAGE: "en"

esphome:
  name: "hall"
  friendly_name: "Hall"

packages:
  display:
    url: https://github.com/example/esphome-cyd-display
    ref: main
    files: [packages/cyd.yaml]
    refresh: 0s
  local_overrides: !include hall.local.yaml

api:
  encryption:
    key: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
ota:
  - platform: esphome
    password: "made-up"
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
'''


def start_value(board, profile):
    """SWIPE_PAGES_DEFAULT as ESPHome resolves it for this screen: its own YAML over the board's package chain."""
    chain = profiles.raw_substitutions(ROOT / f'packages/{board}.yaml')
    return {**chain, **profiles.substitutions_in(profile)}['SWIPE_PAGES_DEFAULT']


def swipe_after_boot(start, stored):
    """What the boot lambda and runtime_tiles::load_settings() leave in settings_screen::swipe_pages, in Python:
    the start value first, then a stored record when there is one (the checks below hold the C++ to this order)."""
    swipe = int(start)
    if stored is not None:
        swipe = 1 if stored == 1 else 0
    return swipe


class NewScreenSwipes(unittest.TestCase):
    def test_a_new_screen_starts_with_swiping_on(self):
        for board in core.BOARD_KEYS:
            profile = core.installation_yaml({'board': board, 'name': 'hall', 'friendly_name': 'Hall'})
            self.assertIn('\n  SWIPE_PAGES_DEFAULT: "1"\n', profile, board)
            self.assertEqual(start_value(board, profile), '1', board)
            self.assertEqual(swipe_after_boot(start_value(board, profile), stored=None), 1, board)

    def test_a_screen_known_before_keeps_swiping_off(self):
        # No board file, look or feature says otherwise: the core's off is what a YAML without the line builds.
        for board in core.BOARD_KEYS:
            old = KNOWN_BEFORE.replace('packages/cyd.yaml', f'packages/{board}.yaml')
            self.assertEqual(start_value(board, old), '0', board)
            self.assertEqual(swipe_after_boot(start_value(board, old), stored=None), 0, board)

    def test_a_stored_choice_wins_over_the_start_value(self):
        # A new screen whose owner turned swiping off keeps it off; one that turned it on keeps it on.
        self.assertEqual(swipe_after_boot('1', stored=0), 0)
        self.assertEqual(swipe_after_boot('0', stored=1), 1)

    def test_the_firmware_takes_the_start_value_before_the_stored_choice(self):
        core_yaml = (ROOT / 'packages/core.yaml').read_text()
        self.assertEqual(profiles.substitutions_of(profiles.CORE)['SWIPE_PAGES_DEFAULT'], '0')
        start = core_yaml.index('settings_screen::swipe_pages = ${SWIPE_PAGES_DEFAULT};')
        self.assertLess(start, core_yaml.index('runtime_tiles::load_settings();'))
        # The firmware's own default stays off (a build without the core's boot, the WASM preview, is a screen
        # known before too), and load_settings changes it only when a record was stored.
        header = (ROOT / 'components/smart_display/settings_screen.h').read_text()
        self.assertRegex(header, r'inline int32_t swipe_pages = 0,')
        tiles = (ROOT / 'components/smart_display/runtime_tiles.h').read_text()
        load = tiles[tiles.index('inline void load_settings()'):tiles.index('inline void persist_settings()')]
        self.assertEqual(re.findall(r'.*swipe_pages\s*=.*', load),
                         ['  if(swipe_preference.load(&swipe_saved))swipe_pages=swipe_saved==1;'])


if __name__ == '__main__':
    unittest.main()
