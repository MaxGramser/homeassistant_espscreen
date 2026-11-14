"""The icons a screen takes on top of the fixed set (docs/ICONS.md): the three lists, the plugins file, what a screen is sent."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))

import core  # noqa: E402
import screen_icons  # noqa: E402
import tile_icons  # noqa: E402
from build_queue import Build  # noqa: E402

BIG = next(board for board, shape in core.SHAPES.items() if shape.get('own_icons'))
SMALL = next(board for board, shape in core.SHAPES.items() if not shape.get('own_icons'))
INBOX, FOUR_MB = 'text.big_tile_settings', 'text.small_tile_settings'
# Names the fixed set does not have.
EXTRA = [name for name in sorted(tile_icons.mdi()) if name not in tile_icons.GLYPHS][:3]


class Line:
    def __init__(self):
        self.added = []

    def on_the_way(self, **_):
        return []

    def add(self, by, file, run, screen=None, target='', round=None):
        build = Build(len(self.added) + 1, by, file, run, screen, target=target, round=round)
        self.added.append(build)
        return build

    def place(self, _build):
        return 1


class Manager:
    def __init__(self, path, online=True):
        self.screens_list = [{'id': INBOX, 'name': 'Big', 'board': BIG}, {'id': FOUR_MB, 'name': 'Small', 'board': SMALL}]
        self.build_queue = Line()
        self.written = []
        self.plugins = SimpleNamespace(rewrite_sidecar=self.written.append, file_for=lambda inbox: {'file': 'x.plugins.yaml', 'content': '', 'line': ''})
        self.updates = SimpleNamespace(resolve=lambda screen: ('x.yaml', 'x.local' if online else None))
        self.ha = SimpleNamespace(states={'sensor.a': {'attributes': {'icon': f'mdi:{EXTRA[0]}'}}, 'sensor.b': {'attributes': {'icon': 'mdi:lamp'}}})
        self.icons = screen_icons.ScreenIcons(self, path)

    def screen(self, inbox):
        return next((s for s in self.screens_list if s['id'] == inbox), None)

    def screens(self):
        return self.screens_list

    def notify(self):
        pass


class ScreenIconsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.manager = Manager(self.folder.name)
        self.icons = self.manager.icons
        original = core.board_of
        core.board_of = lambda screen: screen.get('board')
        self.addCleanup(setattr, core, 'board_of', original)

    def test_a_board_with_4mb_has_no_room(self):
        self.assertEqual(self.icons.room(self.manager.screen(INBOX)), tile_icons.MOST_ICONS - len(tile_icons.GLYPHS))
        self.assertEqual(self.icons.room(self.manager.screen(FOUR_MB)), 0)
        with self.assertRaises(ValueError):
            self.icons.choose(FOUR_MB, EXTRA)

    def test_room_is_held(self):
        too_many = [name for name in sorted(tile_icons.mdi()) if name not in tile_icons.GLYPHS][:tile_icons.room() + 1]
        with self.assertRaises(ValueError):
            self.icons.choose(INBOX, too_many)
        self.assertEqual(len(self.icons.choose(INBOX, too_many[:-1])['chosen']), tile_icons.room())

    def test_the_fixed_set_and_unknown_names_are_never_added(self):
        view = self.icons.choose(INBOX, [EXTRA[0], 'lamp', 'no-such-icon', EXTRA[0]])
        self.assertEqual(view['chosen'], [EXTRA[0]])

    def test_the_font_lines_extend_three_fonts_once(self):
        self.icons.choose(INBOX, EXTRA)
        self.assertEqual(self.icons.font_lines(INBOX), [])     # nothing in the file before a build is asked
        self.icons.apply(INBOX)
        lines = '\n'.join(self.icons.font_lines(INBOX))
        for font in screen_icons.FONTS:
            self.assertIn(f'id: !extend {font}', lines)
        self.assertEqual(lines.count('\\U000'), len(EXTRA))    # a YAML alias repeats the list, not the bytes
        self.assertEqual(self.manager.written, [INBOX])

    def test_the_fonts_exist_in_the_core(self):
        core_yaml = (ROOT / 'packages/core.yaml').read_text()
        for font in screen_icons.FONTS:
            self.assertIn(f'id: {font}\n', core_yaml)

    def test_a_set_that_grows_leaves_the_file(self):
        self.icons.choose(INBOX, EXTRA)
        self.icons.apply(INBOX)
        original = tile_icons.GLYPHS
        tile_icons.GLYPHS = {**original, EXTRA[0]: tile_icons.mdi()[EXTRA[0]][0]}
        self.addCleanup(setattr, tile_icons, 'GLYPHS', original)
        self.assertNotIn(EXTRA[0], '\n'.join(self.icons.font_lines(INBOX)))

    def test_what_goes_out_follows_what_is_built(self):
        self.icons.choose(INBOX, EXTRA)
        self.assertEqual(self.icons.on_screen(INBOX), {})
        self.icons.apply(INBOX)
        self.assertEqual(self.icons.on_screen(INBOX), {})      # asked, not there yet
        build = self.manager.build_queue.added[0]
        build.installed = True
        for end in build.ends:
            end(build)
        self.assertEqual(sorted(self.icons.on_screen(INBOX)), sorted(EXTRA))
        self.assertEqual(self.icons.view(INBOX)['waiting'], [])

    def test_a_failed_build_puts_the_file_back(self):
        self.icons.choose(INBOX, EXTRA)
        self.icons.apply(INBOX)
        build = self.manager.build_queue.added[0]
        build.installed = False
        for end in build.ends:
            end(build)
        self.assertEqual(self.icons.font_lines(INBOX), [])
        self.assertEqual(self.icons.view(INBOX)['waiting'], EXTRA)

    def test_another_build_brings_what_the_screen_has(self):
        self.icons.choose(INBOX, EXTRA)
        self.icons.apply(INBOX)     # the app restarted while this ran: nothing settled it
        update = Build(9, 'update', 'x.yaml', None, INBOX)
        self.icons.before_build(update)
        self.assertEqual(self.icons.font_lines(INBOX), [])

    def test_a_screen_without_a_profile_gets_the_file(self):
        self.manager.updates.resolve = lambda screen: (None, None)
        self.icons.choose(INBOX, EXTRA)
        outcome = self.icons.apply(INBOX)
        self.assertTrue(outcome['own_yaml'])
        self.assertEqual(sorted(self.icons.on_screen(INBOX)), sorted(EXTRA))

    def test_an_offline_screen_is_refused_before_anything_changes(self):
        self.manager.updates.resolve = lambda screen: ('x.yaml', None)
        self.icons.choose(INBOX, EXTRA)
        with self.assertRaises(ValueError):
            self.icons.apply(INBOX)
        self.assertEqual(self.icons.font_lines(INBOX), [])

    def test_every_screen_gets_the_list_but_4mb(self):
        self.icons.choose(INBOX, EXTRA)
        outcome = self.icons.apply_everywhere(INBOX)
        self.assertEqual(outcome['queued'], ['Big'])
        self.assertEqual(self.icons.view(FOUR_MB)['chosen'], [])
        self.assertTrue(self.manager.build_queue.added[0].round)

    def test_suggested_are_icons_the_screen_lacks(self):
        self.assertEqual(self.icons.view(INBOX)['suggested'], [EXTRA[0]])
        self.icons.choose(INBOX, [EXTRA[0]])
        self.assertEqual(self.icons.view(INBOX)['suggested'], [])


class WhatAScreenIsSentTest(unittest.TestCase):
    def test_a_chosen_icon_goes_out_only_on_a_screen_that_has_it(self):
        name = EXTRA[0]
        states = {'light.a': {'state': 'on', 'attributes': {'icon': 'mdi:lamp'}}}
        tile = {'entity': 'light.a', 'name': '', 'options': {'icon': name}}
        lamp = tile_icons.GLYPHS['lamp']
        self.assertEqual(core.state_message(0, tile, states)['o']['icon'], lamp)    # falls back as `auto` does
        code = tile_icons.mdi()[name][0]
        with tile_icons.carrying({name: code}):
            self.assertEqual(core.state_message(0, tile, states)['o']['icon'], code)
        self.assertEqual(core.state_message(0, tile, states)['o']['icon'], lamp)

    def test_home_assistants_own_icon_follows_too(self):
        name = EXTRA[0]
        attributes = {'icon': f'mdi:{name}'}
        self.assertIsNone(tile_icons.ha_icon(attributes))
        with tile_icons.carrying({name: 'F0001'}):
            self.assertEqual(tile_icons.ha_icon(attributes), 'F0001')

    def test_any_icon_is_a_valid_choice(self):
        self.assertTrue(tile_icons.known(EXTRA[0]))
        self.assertTrue(tile_icons.known('lamp'))
        self.assertFalse(tile_icons.known('no-such-icon'))


if __name__ == '__main__':
    unittest.main()
