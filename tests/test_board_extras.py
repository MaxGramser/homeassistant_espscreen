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
        self.assertEqual(listed['reterminald1001'], ['microphone', 'wake_when_moved'])
        labels = SCREEN_TEXT['addon']['labels']['extras']
        for board, keys in listed.items():
            text = profiles.resolved(f'packages/{board}.yaml')
            for key in keys:
                with self.subTest(board=board, key=key):
                    names = {entity_settings.object_id(n) for n in re.findall(r'(?m)^[ \t]+name:[ \t]*"?([^"\n]+)"?', text)}
                    self.assertIn(key, names, 'an entity of the board\'s files is named so')
                    # The screen's own row under Extras, bound to that entity, with the screen's words for it.
                    self.assertIn(f'settings_screen::toggle(screen_text::txt::settings_{key},', text)
                    self.assertIn(key, SCREEN_TEXT['screen']['settings'])
                    self.assertTrue(labels[key]['label'] and labels[key]['hint'], 'the editor\'s words')

    def test_a_board_with_audio_brings_its_features_for_plugins(self):
        # Plugin API 0.7: a plugin that needs a speaker fits a screen whose board brings ts_speaker, without another plugin.
        self.assertEqual(SHAPES['reterminald1001']['features'], ['speaker', 'microphone', 'media_player'])
        self.assertEqual(SHAPES['cyd']['features'], [])
        self.assertEqual(SHAPES['wavesharep4']['features'], [], 'its audio comes with the p4_audio plugin')

    def test_a_board_without_extras_has_no_page_and_no_row(self):
        # The core's hooks are empty: a screen whose files add nothing has no Extras page (settings_screen.h).
        core_yaml = (ROOT / 'packages/core.yaml').read_text()
        self.assertIn('  BOOT_AUDIO_SETTINGS: ""', core_yaml)
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
        ]
        self.states = {'switch.hall_microphone': {'state': 'on'}, 'switch.hall_wake_when_moved': {'state': 'off'},
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
                         [('microphone', 'switch.hall_microphone', 'switch', True, True),
                          ('wake_when_moved', 'switch.hall_wake_when_moved', 'switch', False, True)])
        self.assertEqual(rows[1]['label']['en'], 'Wake when moved')
        self.assertTrue(rows[1]['hint']['en'])
        # A board that lists nothing has no rows.
        self.assertEqual(entity_settings.extras_for(Manager('cyd'), 'text.hall_tiles'), [])

    def test_only_a_listed_entity_of_the_screens_own_device_changes(self):
        manager = Manager('reterminald1001')
        asyncio.run(entity_settings.set_extra(manager, 'text.hall_tiles', 'switch.hall_wake_when_moved', True))
        self.assertEqual(manager.ha.calls, [('switch', 'turn_on', {'entity_id': 'switch.hall_wake_when_moved'})])
        for entity, value in (('switch.hall_dark_mode', True),       # the screen's own, but no extra of its board
                              ('switch.other_microphone', False),    # another screen's
                              ('switch.hall_microphone', 'on'),      # a switch takes true or false
                              (None, True)):
            with self.subTest(entity=entity, value=value), self.assertRaises(ValueError):
                asyncio.run(entity_settings.set_extra(manager, 'text.hall_tiles', entity, value))
        self.assertEqual(len(manager.ha.calls), 1)
        with self.assertRaises(ValueError):
            asyncio.run(entity_settings.set_extra(Manager('cyd'), 'text.hall_tiles', 'switch.hall_microphone', False))


if __name__ == '__main__':
    unittest.main()
