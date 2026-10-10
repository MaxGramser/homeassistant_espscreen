"""A board's own settings (docs/SETTINGS.md, "A board's own settings"): the settings a board lists in boards.yaml are
entities of its files, rows of the screen's settings page under Extras, and rows of the editor under Screen settings,
which change only those entities through Home Assistant."""
import asyncio
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(1, str(ROOT / 'tools'))
import core  # noqa: E402
import entity_settings  # noqa: E402
import profiles  # noqa: E402

SHAPES = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
SCREEN_TEXT = json.loads((ROOT / 'screen_manager/translations/en.json').read_text())


class TheBoards(unittest.TestCase):
    def test_every_listed_setting_is_an_entity_a_screen_row_and_words(self):
        listed = {board: shape['catalog'].get('settings') or [] for board, shape in SHAPES.items()
                  if not board.startswith(('checkout/', 'packages/'))}
        self.assertEqual(listed['reterminald1001'], ['media_player', 'microphone', 'wake_when_moved'])
        labels = SCREEN_TEXT['addon']['labels']['extras']
        for board, keys in listed.items():
            text = profiles.resolved(f'packages/{board}.yaml')
            for key in keys:
                with self.subTest(board=board, key=key):
                    names = {entity_settings.object_id(n) for n in re.findall(r'(?m)^[ \t]+name:[ \t]*"?([^"\n]+)"?', text)}
                    self.assertIn(key, names, 'an entity of the board\'s files is named so')
                    # The screen's own row under Extras, bound to that entity, with the screen's words for it: a switch, or
                    # a number (the speaker's volume, its media player's).
                    self.assertRegex(text, rf'settings_screen::(toggle|number)\(screen_text::txt::settings_{key},')
                    self.assertIn(key, SCREEN_TEXT['screen']['settings'])
                    self.assertTrue(labels[key]['label'] and labels[key]['hint'], 'the editor\'s words')

    def test_a_board_with_audio_brings_its_features_for_plugins(self):
        # Plugin API 0.7: a plugin that needs a speaker fits a screen whose board brings ts_speaker, without another plugin.
        self.assertEqual(SHAPES['reterminald1001']['features'], ['speaker', 'microphone', 'media_player', 'camera_sensor'])
        self.assertEqual(SHAPES['cyd']['features'], [])
        # The Waveshare P4 86 has its microphone and speaker on one bus (AUDIO_HALF_DUPLEX), and the same three features.
        self.assertEqual(SHAPES['wavesharep4']['features'], ['speaker', 'microphone', 'media_player'])
        # The M5Stack Tab5 too, on one bus, and its camera clocked from a pin (CAMERA_XCLK_PIN).
        self.assertEqual(SHAPES['tab5']['features'], ['speaker', 'microphone', 'media_player', 'camera_sensor'])

    def test_a_camera_clocked_from_a_pin_has_ledc_timer_0_to_itself(self):
        # The camera driver (esp_video_camera) makes a sensor's clock with LEDC timer 0 and channel 0, which ESPHome gives
        # the first PWM output when it names no channel (timer = channel / 2): on one timer the two undo each other.
        for board, shape in SHAPES.items():
            if board.startswith(('checkout/', 'packages/')) or 'camera_sensor' not in (shape.get('features') or []):
                continue
            text = profiles.resolved(f'packages/{board}.yaml')
            clock = re.search(r'(?m)^\s+CAMERA_XCLK_PIN:\s*"?(-?\d+)"?', text)
            self.assertIsNotNone(clock, f'{board} names the pin that clocks its camera (-1: its own clock)')
            if int(clock.group(1)) < 0:
                continue
            for output in re.findall(r'(?ms)^  - platform: ledc\n(.*?)(?=^  - |^\S|\Z)', text):
                with self.subTest(board=board, output=output.split()[1] if output.split() else output):
                    channel = re.search(r'(?m)^\s+channel:\s*(\d+)', output)
                    self.assertTrue(channel and int(channel.group(1)) >= 2,
                                    'a PWM output beside a camera clock stands on channel 2 or higher')

    def test_a_board_without_extras_has_no_page_and_no_row(self):
        # The core's hooks are empty: a screen whose files add nothing has no Extras page (settings_screen.h).
        core_yaml = (ROOT / 'packages/core.yaml').read_text()
        self.assertIn('  BOOT_AUDIO: ""', core_yaml)
        self.assertIn('  BOOT_BOARD_SETTINGS: ""', core_yaml)
        header = (ROOT / 'components/smart_display/settings_screen.h').read_text()
        self.assertIn('page_row(screen_text::txt::settings_extras, "\\U000F0493", BOARD_PAGE, has_board_rows)', header)
        self.assertNotIn('board_rows.push_back', profiles.resolved('packages/cyd.yaml'))


class HA:
    def __init__(self):
        self.calls = []
        self.registry = [
            {'entity_id': 'switch.hall_microphone', 'device_id': 'd1', 'platform': 'esphome', 'original_name': 'Microphone'},
            {'entity_id': 'switch.hall_wake_when_moved', 'device_id': 'd1', 'platform': 'esphome', 'original_name': 'Wake when moved'},
            {'entity_id': 'switch.hall_dark_mode', 'device_id': 'd1', 'platform': 'esphome', 'original_name': 'Dark mode'},
            {'entity_id': 'switch.other_microphone', 'device_id': 'd2', 'platform': 'esphome', 'original_name': 'Microphone'},
            {'entity_id': 'media_player.hall_media_player', 'device_id': 'd1', 'platform': 'esphome', 'original_name': 'Media Player'},
        ]
        self.states = {'media_player.hall_media_player': {'state': 'idle', 'attributes': {'volume_level': 0.45}},
                       'switch.hall_microphone': {'state': 'on'}, 'switch.hall_wake_when_moved': {'state': 'off'},
                       'switch.hall_dark_mode': {'state': 'off'}, 'switch.other_microphone': {'state': 'on'}}

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))


class Manager:
    def __init__(self, board):
        self.ha = HA()
        self.board = board

    def screen(self, inbox):
        return {'id': inbox, 'device_id': 'd1', 'board': self.board, 'online': True} if inbox == 'text.hall_tiles' else None


class TheApp(unittest.TestCase):
    def test_the_rows_are_the_boards_entities_in_its_order_with_the_apps_words(self):
        rows = entity_settings.extras_for(Manager('reterminald1001'), 'text.hall_tiles', 'nl')
        self.assertEqual([(r['key'], r['entity'], r['kind'], r['value'], r['available']) for r in rows],
                         [('media_player', 'media_player.hall_media_player', 'number', 45, True),
                          ('microphone', 'switch.hall_microphone', 'switch', True, True),
                          ('wake_when_moved', 'switch.hall_wake_when_moved', 'switch', False, True)])
        self.assertEqual(rows[2]['label']['en'], 'Wake when moved')
        self.assertTrue(rows[2]['hint']['en'])
        # The speaker's volume is its media player's, in percent, as Home Assistant's dialog sets it.
        self.assertEqual((rows[0]['label']['en'], rows[0]['min'], rows[0]['max'], rows[0]['unit']), ('Volume', 0, 100, '%'))
        # A board that lists nothing has no rows.
        self.assertEqual(entity_settings.extras_for(Manager('cyd'), 'text.hall_tiles'), [])

    def test_only_a_listed_entity_of_the_screens_own_device_changes(self):
        manager = Manager('reterminald1001')
        asyncio.run(entity_settings.set_extra(manager, 'text.hall_tiles', 'switch.hall_wake_when_moved', True))
        asyncio.run(entity_settings.set_extra(manager, 'text.hall_tiles', 'media_player.hall_media_player', 60))
        self.assertEqual(manager.ha.calls, [('switch', 'turn_on', {'entity_id': 'switch.hall_wake_when_moved'}),
                                            ('media_player', 'volume_set', {'entity_id': 'media_player.hall_media_player',
                                                                            'volume_level': 0.6})])
        for entity, value in (('switch.hall_dark_mode', True),       # the screen's own, but no extra of its board
                              ('switch.other_microphone', False),    # another screen's
                              ('switch.hall_microphone', 'on'),      # a switch takes true or false
                              ('media_player.hall_media_player', 150),  # a volume is 0 to 100 %
                              (None, True)):
            with self.subTest(entity=entity, value=value), self.assertRaises(ValueError):
                asyncio.run(entity_settings.set_extra(manager, 'text.hall_tiles', entity, value))
        self.assertEqual(len(manager.ha.calls), 2)
        with self.assertRaises(ValueError):
            asyncio.run(entity_settings.set_extra(Manager('cyd'), 'text.hall_tiles', 'switch.hall_microphone', False))


if __name__ == '__main__':
    unittest.main()
