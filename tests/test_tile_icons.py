from firmware_sources import runtime_source
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import test_portal
import tile_icons
from core import discover, packets, state_message, validate_layout

HEADER = runtime_source()

class IconSetTests(unittest.TestCase):
    def test_set_is_complete_and_carried_by_every_icon_font(self):
        # The pickable icons counted from the table itself, never a number written down: each one once among the groups,
        # each carried by the fonts (GLYPHS), and the editor offers exactly them.
        picked = [name for _, icons in tile_icons.GROUPS for name, _, _ in icons]
        self.assertEqual(len(picked), len(set(picked)), 'an icon stands in two groups of tile_icons.GROUPS')
        self.assertEqual(set(picked), set(tile_icons.ICONS))
        self.assertLessEqual(set(tile_icons.ICONS), set(tile_icons.GLYPHS))
        self.assertEqual({icon['name'] for group in tile_icons.editor()['groups'] for icon in group['icons']}, set(tile_icons.ICONS))
        self.assertTrue(any(group == 'Media and music' and len(icons) >= 20 for group, icons in tile_icons.GROUPS))
        self.assertEqual(len(set(tile_icons.GLYPHS.values())), len(tile_icons.GLYPHS))
        for code in tile_icons.GLYPHS.values():
            self.assertRegex(code, r'^F[0-9A-F]{4}$')
        wanted = [f'\\U000{code}' for code in tile_icons.GLYPHS.values()]
        for name in ('checkout/cyd.yaml', 'checkout/guition.yaml', 'packages/cyd.yaml', 'packages/guition.yaml'):
            text = profiles.resolved(name)
            fonts = re.findall(r'materialdesignicons-webfont\.ttf["\']\n    id: (\w+)\n    size: \d+\n    bpp: [24]\n    glyphs: (.*)\n', text)
            # Back's font carries the chevron and nothing else, written out by hand in the shared core; every other icon
            # font carries the whole set. The home key is the Tessera mark (firmware 0.10.0+), a picture, not a glyph.
            self.assertEqual([font for font, _ in fonts], ['materialdesign_icons', 'materialdesign_icons_mini',
                                                           'materialdesign_icons_back', 'materialdesign_icons_status',
                                                           'materialdesign_icons_big', 'watch_icon'], name)
            self.assertEqual(dict(fonts)['materialdesign_icons_back'].strip(), '["\\U000F0141"]', name)
            # The top bar's Wi-Fi bars (firmware 0.38.0): struck through, then one to four bars, the order header_bar.h counts;
            # then the battery's icons the tile icons lack (firmware 0.41.0, battery_status.h): charging per ten up to 90,
            # the charging outline and the alert outline; then the mark of a squeezed live tile (speedometer-slow,
            # runtime_tiles live_badge).
            status = re.search(r'id: materialdesign_icons_status\n    size: \d+\n    bpp: [24]\n    glyphs: (\[.*?\])', text, re.S)[1]
            self.assertEqual(re.findall(r'\\U000(F[0-9A-F]{4})', status),
                             ['F092E', 'F091F', 'F0922', 'F0925', 'F0928', 'F089C', 'F0086', 'F0087', 'F0088', 'F089D', 'F0089',
                              'F089E', 'F008A', 'F008B', 'F089F', 'F10CD', 'F0F86'], name)
            # The battery's level icons, battery-unknown and the full charging one are tile icons already.
            for code in ('F0079', 'F007A', 'F007B', 'F007C', 'F007D', 'F007E', 'F007F', 'F0080', 'F0081', 'F0082', 'F0091', 'F0084'):
                self.assertIn(code, tile_icons.GLYPHS.values(), code)
            self.assertTrue(fonts[0][1].startswith('&tile_icons ')
                            and all(g == '*tile_icons' for font, g in fonts[1:]
                                    if font not in ('materialdesign_icons_big', 'materialdesign_icons_back', 'materialdesign_icons_status')), name)
            block = text.split('glyphs: &tile_icons ', 1)[1].split('\n\n', 1)[0]
            self.assertEqual(re.findall(r'- "(\\U000F[0-9A-F]{4})"', block), wanted, name)
            # The big font of the full-page card (firmware 0.2.62+) carries the subset the screen draws on its own.
            self.assertEqual(dict(fonts)['materialdesign_icons_big'].split('  #')[0].strip(), '&tile_icons_big', name)
            big = text.split('glyphs: &tile_icons_big', 1)[1].split('\n\n', 1)[0]
            self.assertEqual(re.findall(r'- "(\\U000F[0-9A-F]{4})"', big), [f'\\U000{tile_icons.GLYPHS[n]}' for n in tile_icons.BIG_GLYPHS], name)
            self.assertNotIn('MDI_GLYPH', text, name)
        self.assertTrue((ROOT / 'web/src/assets/tile-icons.woff').exists())

    # tile_icon_names.h, the firmware's name table, is written from GLYPHS and checked by tools/generate_icons.py --check.

    def test_every_glyph_the_firmware_draws_is_in_the_set(self):
        # A rule over the firmware: an icon it draws by its codepoint is one the fonts carry.
        sources = [HEADER] + [profiles.text(name).split('glyphs: &tile_icons', 1)[0] for name in ('checkout/cyd.yaml', 'checkout/guition.yaml')]
        used = {code.upper() for source in sources for code in re.findall(r'\\U000(F[0-9A-Fa-f]{4})', source)}
        self.assertLessEqual(used, set(tile_icons.GLYPHS.values()),
                             'add every icon the firmware draws to tile_icons.py and run tools/generate_icons.py')

    def test_editor_predictions_are_the_fixture_the_firmware_is_read_against(self):
        # web/wasm/test_tile_icons.mjs reads the real firmware's cards against tests/fixtures/tile-icons.json; here the
        # fixture is what the editor predicts.
        editor = tile_icons.editor()
        predicted = {'defaults': {domain: tile_icons.GLYPHS[name] for domain, name in tile_icons.DEFAULTS.items()},
                     'builtin': editor['builtin'], 'weather': editor['weather'], 'sun': editor['sun'],
                     'fallback': tile_icons.GLYPHS[tile_icons.FALLBACK]}
        self.assertEqual(json.loads((ROOT / 'tests/fixtures/tile-icons.json').read_text()), predicted,
                         'write tests/fixtures/tile-icons.json from tile_icons.editor(); the firmware preview test reads it')
        builtin = {entity: tile_icons.GLYPHS[name] for entity, name in tile_icons.BUILTIN_TILES.items()}
        diagrams = {entity: tile_icons.GLYPHS[name] for entity, name in tile_icons.DIAGRAM_TILES.items()}
        self.assertEqual(editor['builtin'], {**builtin, **diagrams})
        self.assertEqual(sum(len(group['icons']) for group in editor['groups']), len(tile_icons.ICONS))

class IconOptionTests(unittest.IsolatedAsyncioTestCase):
    def test_validation_accepts_any_icon_and_auto_only(self):
        # Which icons a screen can draw is its own (docs/ICONS.md): the layout holds any icon's name.
        for value in ('auto', 'lamp', 'spotify', 'speaker', 'weather-fog', 'star-circle'):
            layout = validate_layout({'title': 'Home', 'tiles': [{'entity': 'media_player.a', 'options': {'icon': value}}]})
            self.assertEqual(layout['tiles'][0]['options']['icon'], value)
        for value in ('mdi:lamp', 'F06B5', 'no-such-icon', '', None, 42, ['lamp']):
            with self.assertRaises(ValueError):
                validate_layout({'title': 'Home', 'tiles': [{'entity': 'light.a', 'options': {'icon': value}}]})

    def test_wire_carries_the_codepoint_chosen_or_from_home_assistant(self):
        states = {'light.a': {'state': 'on', 'attributes': {'icon': 'mdi:floor-lamp'}},
                  'light.b': {'state': 'on', 'attributes': {'icon': 'mdi:not-in-the-set'}},
                  'light.c': {'state': 'on', 'attributes': {}}}
        chosen = state_message(0, {'entity': 'light.a', 'name': '', 'options': {'icon': 'lamp', 'tap': 'toggle'}}, states)
        self.assertEqual(chosen['o'], {'tap': 'toggle', 'icon': 'F06B5'})
        automatic = state_message(0, {'entity': 'light.a', 'name': '', 'options': {'icon': 'auto'}}, states)
        self.assertEqual(automatic['o'], {'icon': 'F08DD'})
        self.assertEqual(state_message(0, {'entity': 'light.a', 'name': ''}, states)['o'], {'icon': 'F08DD'})
        self.assertNotIn('o', state_message(0, {'entity': 'light.b', 'name': ''}, states))
        self.assertNotIn('o', state_message(0, {'entity': 'light.c', 'name': ''}, states))
        self.assertEqual(state_message(0, {'entity': 'light.c', 'name': '', 'options': {'icon': 'auto'}}, states)['o'], {})
        packets(chosen)

    def test_discovery_reports_home_assistant_icons_the_screen_can_draw(self):
        states = {'light.a': {'state': 'on', 'attributes': {'icon': 'mdi:chandelier'}}, 'light.b': {'state': 'off', 'attributes': {'icon': 'hass:x'}}}
        _, entities = discover([{'entity_id': 'light.a'}], states, [], [])
        self.assertEqual({e['id']: e['icon'] for e in entities}, {'light.a': 'F1793', 'light.b': None})

    async def test_old_editor_preserves_icon_and_explicit_auto_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = test_portal.ManagerTests().setup_manager(Path(tmp) / 'screens.json')
            m.save('text.screen', {'title': 'Home', 'tiles': [{'entity': 'light.a', 'options': {'icon': 'spotify'}}]})
            m.save('text.screen', {'title': 'Home', 'tiles': [{'entity': 'light.a', 'options': {'inline': 'none'}}]})
            self.assertEqual(m.layouts['text.screen']['tiles'][0]['options'], {'inline': 'none', 'icon': 'spotify'})
            await m.sync_one('text.screen', m.layouts['text.screen'])
            self.assertEqual(m.ha.messages[1][1]['o']['icon'], 'F04C7')
            m.save('text.screen', {'title': 'Home', 'tiles': [{'entity': 'light.a', 'options': {'icon': 'auto'}}]})
            self.assertEqual(m.layouts['text.screen']['tiles'][0]['options']['icon'], 'auto')

if __name__ == '__main__':
    unittest.main()
