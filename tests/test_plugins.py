"""Plugins (docs/PLUGINS.md): the manifest check, the map language, fetch's rules, the plugins file, a plugin tile in a
layout, and one plugin API version in the firmware, the component and the add-on.

What reads the firmware's source here is a rule over it (docs/TESTING.md, "A test reads behaviour, not lines"): one API
version everywhere, every CardColor a swatch, a number both sides write the same (SameNumbers), a name that must stay
gone. What the firmware does with them is the host probe's (tools/render/run.py's plugin round) and plugin_host.cpp's
static_assert on the card colours."""
import asyncio
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))

import core  # noqa: E402
from build_queue import BuildQueue  # noqa: E402
import page_layout  # noqa: E402
import plugin_fetch  # noqa: E402
import plugin_manifest as pm  # noqa: E402
import picture_legacy  # noqa: E402
import picture_paint  # noqa: E402
import picture_question as pq  # noqa: E402
import plugin_pictures  # noqa: E402
from firmware import Firmware  # noqa: E402
from page_delivery import plugins_of  # noqa: E402

SCREEN = {'board': 'guition', 'firmware': '0.50.0'}   # 480 x 480 glass
FIRMWARE = ROOT / 'components' / 'smart_display'


def cpp_number(file, name):
    """The number a firmware header gives a constant (`constexpr <type> NAME = 8;`, also one of several in a line), read
    by its name wherever it stands outside a comment, or None."""
    code = re.sub(r'//[^\n]*|/\*.*?\*/', '', (FIRMWARE / file).read_text(), flags=re.S)
    found = re.search(rf'\b{name}\s*=\s*(\d+)\b', code)
    return int(found.group(1)) if found else None


def cpp_block(text, opening):
    """What lies between the braces of the first block `opening` (a regex ending before its `{`) starts, braces counted,
    or None."""
    found = re.search(opening + r'[^;{]*\{', text)
    if not found:
        return None
    depth, at = 1, found.end()
    while depth and at < len(text):
        depth += {'{': 1, '}': -1}.get(text[at], 0)
        at += 1
    return text[found.end():at - 1]


def python_value(path, name):
    """The value a module assigns to a name at its top (`NAME = (0, 28)`), read by parsing it, not by its spelling."""
    import ast
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def refused(question, manifest, tile, of_entity=None):
    """Why a plugin place's question is not answered with pictures (plugin_pictures.refused_source for each of its
    sources, the first that may not be), or None."""
    return next((problem for problem in (plugin_pictures.refused_source(source, len(question.sources), manifest, tile, of_entity)
                                         for source in question.sources) if problem), None)


def styles(question):
    """How each place of a plugin's question is painted: its fit, its turn and whether a reflection goes under it."""
    return [(place.fit, place.turn, place.mirror) for place in question.places]


ENGLISH = {'app': {'name': 'Bus', 'summary': 'Next bus.', 'tile': 'Next', 'stop': 'Stop', 'line': 'Line',
                   'walk': 'Walk', 'key': 'Key'}, 'screen': {'now': 'now'}}


def manifest(**changes):
    data = {
        'id': 'bus', 'version': '1.0.0', 'api': '0.4', 'icon': 'bus', 'maintainer': 'someone', 'license': 'MIT', 'topics': ['travel'],
        'permissions': {'network': ['api.example.org']}, 'attributes': ['cloud'], 'privacy': 'https://example.org/p',
        'tiles': [{'id': 'next', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 900,
                   'data': 'departures', 'options': [
                       {'id': 'stop', 'kind': 'text', 'label': 'stop'},
                       {'id': 'line', 'kind': 'choice', 'options_from': 'lines', 'label': 'line'},
                       {'id': 'walk', 'kind': 'number', 'min': 0, 'max': 20, 'default': 3, 'label': 'walk'}]}],
        'fetch': [
            {'id': 'departures', 'url': 'https://api.example.org/stops/{stop}', 'every': '60s',
             'map': {'items': '$.{stop}.passes[*]', 'fields': {'line': 'line', 'at': {'path': 'when', 'as': 'epoch'}},
                     'where': {'line': '{line}'}, 'sort': 'at', 'limit': 2}},
            {'id': 'lines', 'url': 'https://api.example.org/stops/{stop}', 'every': '1h',
             'map': {'items': '$.{stop}.passes[*]', 'value': 'line', 'label': ['line', 'to']}}],
    }
    data.update(changes)
    return data


class Manifest(unittest.TestCase):
    def test_a_complete_manifest_passes(self):
        out = pm.check(manifest(), ENGLISH)
        self.assertEqual(out['tiles'][0]['options'][2]['default'], 3)
        self.assertEqual(out['fetch'][0]['every'], 60)
        self.assertEqual(out['fetch'][0]['placeholders'], ['stop'])

    def test_entity_option_names_domains_and_attributes(self):
        data = manifest(api='0.15')
        data['tiles'][0]['options'].append({'id': 'power', 'kind': 'entity', 'label': 'key',
                                             'domains': ['sensor'], 'attributes': ['unit_of_measurement']})
        option = pm.check(data, ENGLISH)['tiles'][0]['options'][-1]
        self.assertEqual(pm.option_value(option, 'sensor.grid_power'), 'sensor.grid_power')
        self.assertEqual(pm.option_value(option, ''), '')
        for wrong in ('switch.grid', 'not-an-entity', 12):
            with self.subTest(wrong), self.assertRaises(pm.ManifestError):
                pm.option_value(option, wrong)
        # It names the API that brought it, and belongs to a tile only.
        with self.assertRaises(pm.ManifestError) as older:
            pm.check({**data, 'api': '0.14'}, ENGLISH)
        self.assertIn('0.15', str(older.exception))
        for missing in ({'domains': []}, {'domains': ['Sensor']}):
            broken = manifest(api='0.15')
            broken['tiles'][0]['options'].append({'id': 'power', 'kind': 'entity', 'label': 'key', **missing})
            with self.subTest(missing), self.assertRaises(pm.ManifestError):
                pm.check(broken, ENGLISH)

    def test_the_real_plugins_pass(self):
        plugins = ROOT.parent / 'tessera-plugins'
        for folder in [*(plugins / 'plugins').glob('*'), plugins / 'template', *(ROOT / 'tests' / 'fixtures' / 'plugins').glob('*')]:
            if (folder / 'tessera-plugin.yaml').is_file():
                import yaml
                with self.subTest(folder.name):
                    pm.check(yaml.safe_load((folder / 'tessera-plugin.yaml').read_text()),
                             json.loads((folder / 'translations' / 'en.json').read_text()))

    def test_a_new_kind_of_right_does_not_ask_everyone_again(self):
        import hashlib
        out = pm.check(manifest(), ENGLISH)
        # The fingerprint as plugin API 0.1 made it, before ha_commands existed: an installed plugin keeps its consent.
        before = {'permissions': {'read_entities': [], 'home_assistant_actions': [], 'network': ['api.example.org']},
                  'attributes': ['cloud']}
        self.assertEqual(pm.permission_hash(out), hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()[:16])
        asking = pm.check(manifest(permissions={'network': ['api.example.org'], 'ha_commands': ['history/history_during_period']}), ENGLISH)
        self.assertNotEqual(pm.permission_hash(asking), pm.permission_hash(out))

    def test_a_preview_names_fields_of_its_data(self):
        def with_preview(preview):
            data = manifest()
            data['tiles'][0]['preview'] = preview
            return data
        self.assertEqual(pm.check(with_preview({'badge': '{line}', 'countdown': 'at'}), ENGLISH)['tiles'][0]['preview'],
                         {'badge': '{line}', 'countdown': 'at'})
        for wrong in ({'title': '{nowhere}'}, {'countdown': 'line'}, {'value': '{line}', 'countdown': 'at'}, {'colour': 'x'}):
            with self.subTest(wrong), self.assertRaises(pm.ManifestError):
                pm.check(with_preview(wrong), ENGLISH)

    def test_stage_is_the_makers_word_and_beta_without_one(self):
        self.assertEqual(pm.check(manifest(), ENGLISH)['stage'], 'beta')
        for stage in pm.STAGES:
            with self.subTest(stage):
                self.assertEqual(pm.check(manifest(stage=stage), ENGLISH)['stage'], stage)

    def test_mistakes_say_where(self):
        cases = [
            (manifest(colour='red'), 'unknown field'),
            (manifest(api='1'), 'api'),
            (manifest(id='Bus'), 'id'),
            (manifest(license='Proprietary'), 'license'),
            (manifest(privacy=None, attributes=['cloud']), 'privacy'),
            (manifest(attributes=[]), 'cloud'),
            (manifest(attributes=['cloud', 'experimental']), 'attributes'),
            (manifest(stage='test'), 'stage'),
            (manifest(permissions={'network': ['192.168.1.2']}), 'public host'),
            (manifest(permissions={'network': ['router.local']}), 'public host'),
        ]
        bad_fetch = manifest()
        bad_fetch['fetch'][0]['url'] = 'https://other.example.org/x'
        cases.append((bad_fetch, 'permissions.network'))
        often = manifest()
        often['fetch'][0]['every'] = '5s'
        cases.append((often, '30s'))
        secret_in_path = manifest(inputs=[{'id': 'key', 'kind': 'secret', 'label': 'key'}])
        secret_in_path['fetch'][0]['url'] = 'https://api.example.org/{key}/stops/{stop}'
        cases.append((secret_in_path, 'never in the path'))
        secret_over_http = manifest(inputs=[{'id': 'key', 'kind': 'secret', 'label': 'key'}])
        secret_over_http['fetch'][0]['url'] = 'http://api.example.org/stops/{stop}?key={key}'
        cases.append((secret_over_http, 'https'))
        unknown = manifest()
        unknown['fetch'][0]['url'] = 'https://api.example.org/stops/{nope}'
        cases.append((unknown, '{nope}'))
        for data, words in cases:
            with self.subTest(words):
                with self.assertRaises(pm.ManifestError) as caught:
                    pm.check(data, ENGLISH)
                self.assertIn(words, str(caught.exception))

    def test_every_text_is_in_english(self):
        english = {'app': dict(ENGLISH['app']), 'screen': {}}
        del english['app']['walk']
        with self.assertRaises(pm.ManifestError) as caught:
            pm.check(manifest(), english)
        self.assertIn('walk', str(caught.exception))

    def test_api_versions(self):
        self.assertTrue(pm.api_fits('0.1', (0, 1)))
        self.assertTrue(pm.api_fits('0.1', (0, 2)))    # something new raises the minor and breaks nothing
        self.assertFalse(pm.api_fits('0.3', (0, 2)))   # a plugin that needs a newer core says so
        self.assertTrue(pm.api_fits('1.1', (1, 3)))
        self.assertFalse(pm.api_fits('1.4', (1, 3)))
        self.assertFalse(pm.api_fits('2.0', (1, 3)))
        # While the major is 0 a minor may change a name: a plugin written before it does not fit what comes after.
        self.assertFalse(pm.api_fits('0.3', (0, 8)))
        self.assertTrue(pm.api_fits('0.4', (0, 8)))
        self.assertTrue(pm.api_fits('0.7', (0, 8)))
        self.assertFalse(pm.api_fits('0.2', (0, 5), {0: (3,)}))
        self.assertTrue(pm.api_fits('0.2', (0, 2), {0: (3,)}))

    def test_a_tile_says_its_sizes_and_the_whole_page(self):
        """Plugin API 0.25: min and max, `full: true` beside them, or `full: true` alone for a tile of only the whole page."""
        sizes = lambda **given: pm.check(manifest(fetch=[], tiles=[{'id': 'next', 'name': 'tile', 'sizes': given, 'memory': 900}]), ENGLISH)['tiles'][0]
        tile = sizes(min='2x2', max='3x3', full=True)
        self.assertEqual((tile['min'], tile['max'], tile['full']), ('2x2', '3x3', True))
        self.assertFalse(sizes(min='1x1', max='2x3')['full'])
        tile = sizes(full=True)
        self.assertEqual((tile['min'], tile['max'], tile['full']), (None, None, True))
        for wrong in ({'full': False}, {}, {'min': '1x1'}, {'max': '2x2', 'full': True}, {'min': '3x3', 'max': '2x2'}):
            with self.assertRaises(pm.ManifestError):
                sizes(**wrong)

    def test_a_card_colour_of_a_plugin_tile_is_one_of_the_screens_own(self):
        """ui::set_card_color (0.26) names every swatch of theme.h, each once, so a plugin's card is drawn by the same
        table as a tile a person coloured, in both looks; the palette takes it over the tile's own."""
        enum = cpp_block((FIRMWARE / 'plugin_api.h').read_text(), r'enum\s+class\s+CardColor\b')
        table = cpp_block((FIRMWARE / 'theme.h').read_text(), r'\bSWATCHES\s*\[\s*\]\s*=')
        self.assertTrue(enum and table, 'plugin_api.h has an `enum class CardColor` and theme.h a `SWATCHES[]` table: '
                                        'this rule reads both, so name the new places here when they move')
        names = [part.split('=')[0].strip() for part in enum.split(',') if part.strip()]
        swatches = re.findall(r'\{\s*"([^"]+)"', table)
        self.assertEqual(names[0], 'NONE', 'CardColor starts with NONE, which gives the card back to the colour the '
                                           'person chose for the tile')
        # INSTRUMENT (0.28) comes after them: the instrument roles' ground, no swatch (theme::Face::instrument).
        self.assertEqual(names[-1], 'INSTRUMENT', 'CardColor ends with INSTRUMENT, the one colour that is no swatch: a new '
                                                  'swatch goes in before it')
        # Every colour the API names is a swatch of the screen's own table, and the API names them all. How the host
        # gets from one to the other is plugin_host.cpp's static_assert (card_swatches_whole), checked when it compiles,
        # and that the card then wears it in both looks is tools/render/run.py's plugin round, which sets a colour and
        # reads the card's ground on the glass (docs/TESTING.md, "A test reads behaviour, not lines").
        self.assertEqual(sorted(name.lower() for name in names[1:-1]), sorted(swatches),
                         'every swatch of theme::SWATCHES is a CardColor of the plugin API by its name, once, and every '
                         'CardColor between NONE and INSTRUMENT is a swatch: a new swatch gets its CardColor (before '
                         'INSTRUMENT) and its line in plugin_host.cpp\'s CARD_SWATCHES, and raises the API\'s minor')

    def test_one_plugin_api_everywhere(self):
        """One plugin API version: plugin_api.h, the component's __init__.py, the add-on's manifest check, the docs and
        the host probe, which is written for the newest API and uses its newest moments."""
        api = (cpp_number('plugin_api.h', 'PLUGIN_API_MAJOR'), cpp_number('plugin_api.h', 'PLUGIN_API_MINOR'))
        self.assertNotIn(None, api, 'plugin_api.h states PLUGIN_API_MAJOR and PLUGIN_API_MINOR')
        version = f'{api[0]}.{api[1]}'
        raise_all = (f'plugin_api.h says {version}: a new API raises PLUGIN_API_MINOR there, PLUGIN_API in '
                     'components/smart_display/__init__.py and screen_manager/app/plugin_manifest.py, "the plugin API '
                     'is X.Y now" in docs/PLUGINS.md and the host probe\'s `api`, together')
        component = FIRMWARE / '__init__.py'
        self.assertEqual(python_value(component, 'PLUGIN_API'), api, raise_all)
        self.assertEqual(pm.PLUGIN_API, api, raise_all)
        self.assertEqual(python_value(component, 'PLUGIN_API_BREAKS'), pm.PLUGIN_API_BREAKS,
                         'PLUGIN_API_BREAKS is the same in components/smart_display/__init__.py (which refuses a plugin '
                         'when it is built) and screen_manager/app/plugin_manifest.py (which refuses it in the app)')
        doc = (ROOT / 'docs/PLUGINS.md').read_text()
        self.assertEqual(re.findall(r'the plugin API is (\d+\.\d+) now', doc), [version], raise_all)
        import yaml
        probe = yaml.safe_load((ROOT / 'tests/fixtures/plugins/host_probe/tessera-plugin.yaml').read_text())
        self.assertEqual(probe['api'], version, raise_all)

    def test_a_tile_may_have_places_for_pictures(self):
        """`pictures` (0.10): how many places a tile has at most, 0 without; the screen asks for as many at most."""
        self.assertEqual(pm.check(manifest(), ENGLISH)['tiles'][0]['pictures'], 0)
        tiles = manifest()['tiles']
        tiles[0]['pictures'] = 8
        self.assertEqual(pm.check(manifest(tiles=tiles), ENGLISH)['tiles'][0]['pictures'], 8)
        for bad in (9, -1, 'two', 2.5, True):
            tiles[0]['pictures'] = bad
            with self.assertRaises(pm.ManifestError) as caught:
                pm.check(manifest(tiles=tiles), ENGLISH)
            self.assertIn('tiles[0].pictures', str(caught.exception))

    def test_the_two_ticks_have_two_names(self):
        """A plugin's 250 ms moment with millis() is on_interval; on_tick is a tile's or a card's second with the clock.
        That the screen calls on_interval is the host probe's (it overrides it, and tools/render/run.py's plugin round
        reads `interval=1` among the moments of boot); here, the name that must stay gone."""
        plugin = cpp_block((FIRMWARE / 'plugin_api.h').read_text(), r'\bclass\s+Plugin\b')
        self.assertIsNotNone(plugin, 'plugin_api.h defines tessera::Plugin, the class a plugin derives from')
        self.assertIsNone(re.search(r'\bon_tick\b', re.sub(r'//[^\n]*|/\*.*?\*/', '', plugin, flags=re.S)),
                          'tessera::Plugin has no on_tick: before 0.4 that was its 250 ms moment, and a plugin of then '
                          'that overrides it must fail to build instead of being called once a second. The plugin\'s '
                          'moment is on_interval; on_tick belongs to a tile and a card')


class SameNumbers(unittest.TestCase):
    """A number the add-on and the firmware both use, written in each (they cannot share a file): the same on both
    sides, read by its name in the header, whatever line it stands in."""
    NUMBERS = [
        # (the add-on's value, its name, the firmware header, the constant there, what the number is)
        (pm.MAX_PICTURES, 'plugin_manifest.MAX_PICTURES', 'tile_picture.h', 'MAX_PARTS',
         'how many places for pictures a tile may have, which the screen asks for at most'),
        (core.PLUGIN_PLACEHOLDER_BYTES, 'core.PLUGIN_PLACEHOLDER_BYTES', 'plugin_host.h', 'PLACEHOLDER_BYTES',
         'what a tile of a plugin the screen does not have costs of the layout memory'),
        (picture_paint.MIRROR_PERCENT, 'picture_paint.MIRROR_PERCENT', 'plugin_api.h', 'MIRROR_PERCENT',
         'the share of a picture\'s height its reflection takes, which the plugin keeps room for and the app paints'),
    ]

    def test_the_add_on_and_the_firmware_say_the_same(self):
        for value, python, header, name, what in self.NUMBERS:
            with self.subTest(name):
                self.assertEqual(cpp_number(header, name), value,
                                 f'{name} in components/smart_display/{header} and {python} in the add-on are {what}: '
                                 'change both together')


class Pictures(unittest.IsolatedAsyncioTestCase):
    """The pictures of a plugin tile (plugin API 0.10, plugin_pictures): the question as the screen asks it, where a
    picture may come from, and a cache by address."""
    ATLAS = '[[0,0,60,90,6,0],[70,0,60,90,6,0]]'
    SRC = '["https://api.example.org/a.jpg","https://api.example.org/b.jpg"]'

    def question(self, **changes):
        """The question a plugin tile asks (picture_legacy: plugin API 0.10's shape), or None."""
        request = {'tiles': 'plugin:bus.next', 'idx': '3', 'bg': '202020', 'dark': '1', 'atlas': self.ATLAS, 'src': self.SRC,
                   'fit': '["cover","contain"]', 'view': '12'}
        request.update(changes)
        found = picture_legacy.read(request, SCREEN)
        return found.question if found else None

    def test_the_question_names_the_tile_its_frames_and_their_addresses(self):
        found = picture_legacy.read({'tiles': 'plugin:bus.next', 'idx': '3', 'bg': '202020', 'dark': '1', 'atlas': self.ATLAS,
                                     'src': self.SRC, 'fit': '["cover","contain"]', 'view': '12'}, SCREEN)
        q = found.question
        self.assertEqual((found.kind, found.entity, q.owner.kind, q.owner.key, q.owner.index, q.dark, q.number),
                         ('live', 'plugin:bus.next', 'plugin_tile', 'plugin:bus.next', 3, True, 12))
        self.assertEqual(core.plugin_tile(q.owner.key), ('bus', 'next'))
        self.assertEqual({place.ground for place in q.places}, {0x202020})
        self.assertEqual((q.box, [(p.x, p.y, p.w, p.h, p.radius, p.shade) for p in q.places]),
                         ((130, 90), [(0, 0, 60, 90, 6, 0), (70, 0, 60, 90, 6, 0)]))
        self.assertEqual([source.text for source in q.sources], ['https://api.example.org/a.jpg', 'https://api.example.org/b.jpg'])
        # A plugin's `contain` shows the picture whole on what lies under its place (`within`).
        self.assertEqual([place.fit for place in q.places], ['cover', 'within'])
        self.assertEqual([place.fit for place in self.question(fit=None).places], ['cover', 'cover'])   # cover without a word
        for bad in (dict(tiles='camera.front'), dict(idx='x'), dict(bg='red'), dict(src='["one"]'), dict(src='[1,2]'),
                    dict(fit='["cover"]'), dict(fit='["fill","cover"]'), dict(atlas='[[0,0,60,90,6,0]]'), dict(src='[]'),
                    dict(src='[' + ','.join(['"https://api.example.org/x.jpg"'] * 9) + ']'), dict(atlas='[[0,0,600,90,6,0],[70,0,60,90,6,0]]')):
            self.assertIsNone(self.question(**bad), bad)

    def test_places_may_overlap_turn_and_mirror(self):
        """The places of one card are its layers (0.10): their frames may overlap, each may turn and have a reflection."""
        q = self.question(atlas='[[0,0,60,90,6,0],[40,0,60,90,6,0]]', turn='["right",""]', mirror='[0,1]')
        self.assertEqual(([p.turn for p in q.places], [p.mirror for p in q.places]), (['right', ''], [False, True]))
        self.assertEqual(styles(q), [('cover', 'right', False), ('within', '', True)])
        self.assertEqual([p.turn for p in self.question().places], ['', ''])   # a flat card asks without them
        for bad in (dict(turn='["up",""]'), dict(turn='["left"]'), dict(mirror='[2,0]'), dict(mirror='{}'), dict(turn='x')):
            self.assertIsNone(self.question(**bad), bad)
        # Covers of different tiles still never overlap.
        self.assertIsNone(picture_legacy.frames('[[0,0,60,90,6,0],[40,0,60,90,6,0]]', (480, 480), 2))

    @unittest.skipUnless(__import__('importlib').util.find_spec('PIL'), 'Pillow')
    def test_layers_overlap_turn_and_mirror(self):
        from PIL import Image
        import io
        def picture(colour):
            raw = io.BytesIO()
            Image.new('RGB', (100, 150), colour).save(raw, 'PNG')
            return raw.getvalue()
        red, blue = picture((255, 0, 0)), picture((0, 0, 255))

        def layers(raws, frames, styles):
            atlas = picture_legacy.frames(frames, (480, 480), len(raws), overlap=True)
            places = tuple(pq.Place(*frame[:5], 0, 'cover', 0x202020, turn=turn, mirror=mirror)
                           for frame, (turn, mirror) in zip(atlas[2], styles))
            question = pq.Question(pq.Owner('plugin_tile', 0, 'plugin:bus.next'), (pq.Source('url', 'https://x'),) * len(raws),
                                   atlas[:2], places)
            return picture_paint.paint(question, raws, 'bmp24')
        body = layers([red, blue], '[[0,0,60,90,8,0],[40,0,60,117,8,0]]', [('', False), ('', True)])
        with Image.open(io.BytesIO(body)) as image:
            rgb = image.convert('RGB')
            self.assertEqual(rgb.getpixel((20, 45)), (255, 0, 0))      # the first, where nothing lies over it
            self.assertEqual(rgb.getpixel((50, 45)), (0, 0, 255))      # the later place lies over the earlier
            self.assertGreater(rgb.getpixel((40, 1))[0], 245)          # its rounded corner shows the red under it
            self.assertEqual(rgb.getpixel((99, 0)), (0x20, 0x20, 0x20))  # and the card where nothing lies under it
            below = rgb.getpixel((70, 92))                            # the reflection: faint blue on the card
            self.assertTrue(below[2] > 0x40 and below[2] < 160 and below[0] < 0x30, below)
            self.assertTrue(all(abs(c - 0x20) <= 3 for c in rgb.getpixel((70, 116))))   # faded out at its foot
        # Turned to face the right: the left edge near (full height), the right edge far (lower and shorter).
        body = layers([red], '[[0,0,40,100,0,0]]', [('right', False)])
        with Image.open(io.BytesIO(body)) as image:
            rgb = image.convert('RGB')
            self.assertEqual(rgb.getpixel((1, 2))[0], 255)
            self.assertEqual(rgb.getpixel((38, 2)), (0x20, 0x20, 0x20))
            self.assertEqual(rgb.getpixel((38, 50))[0], 255)

    def test_where_a_picture_may_come_from(self):
        checked = pm.check(manifest(), ENGLISH)
        tile = dict(checked['tiles'][0], pictures=2)
        allowed = lambda url, t=tile: plugin_pictures.allowed(url, checked, t)
        self.assertEqual(allowed('https://api.example.org/a.jpg'), 'network')
        self.assertIsNone(allowed('https://image.tmdb.org/a.jpg'))         # a host the manifest does not name
        self.assertIsNone(allowed('https://10.0.0.5/a.jpg'))
        self.assertIsNone(allowed('ftp://api.example.org/a.jpg'))
        # Home Assistant's own pictures: on a tile of an entity only, and only the paths a map marker takes.
        self.assertIsNone(allowed('/api/image/serve/abc/512x512'))
        entity_tile = dict(tile, domains=['person'])
        self.assertEqual(allowed('/api/image/serve/abc/512x512', entity_tile), 'home_assistant')
        self.assertEqual(allowed('/api/image_proxy/image.door?token=1', entity_tile), 'home_assistant')
        self.assertEqual(allowed('/local/me.png', entity_tile), 'home_assistant')
        for bad in ('/api/camera_proxy/camera.x', '/api/image/serve/../x', '/local//x', '/api/states'):
            self.assertIsNone(allowed(bad, entity_tile), bad)
        # A tile without places shows nothing, whatever the address.
        self.assertIsNone(allowed('https://api.example.org/a.jpg', dict(tile, pictures=0)))
        q = self.question()
        self.assertIsNone(refused(q, checked, tile))
        self.assertIn('allows 1', refused(q, checked, dict(tile, pictures=1)))
        self.assertIn('no pictures', refused(q, checked, checked['tiles'][0]))
        self.assertIn('not an address', refused(self.question(src='["https://x.org/a","https://api.example.org/b"]'), checked, tile))
        self.assertIn('does not run', refused(q, None, None))
        # The core's sources of an entity (plugin API 0.17): only on a place of an entity (Sources.may then checks that
        # it is the place's own entity).
        cover = pq.Source('cover', 'media_player.kitchen')
        self.assertIn('shows no entity', plugin_pictures.refused_source(cover, 1, checked, tile))
        self.assertIsNone(plugin_pictures.refused_source(cover, 1, checked, entity_tile))
        self.assertIsNone(plugin_pictures.refused_source(cover, 1, checked, tile, True))

    async def test_a_picture_is_fetched_once_and_a_failure_waits(self):
        checked = pm.check(manifest(), ENGLISH)
        tile = dict(checked['tiles'][0], pictures=2, domains=['person'])
        asked, now = [], [1000.0]

        class Fetcher:
            check_host = staticmethod(plugin_fetch.Fetcher.check_host)

            async def download_bytes(self, url, headers, network, limit):
                asked.append(url)
                if url.endswith('gone.jpg'):
                    raise OSError('HTTP 404')
                return b'JPEG' + url.encode()
        ha = []

        async def ha_picture(path):
            ha.append(path)
            return b'PNG'
        pictures = plugin_pictures.Pictures(Fetcher(), ha_picture, clock=lambda: now[0])
        self.assertEqual(await pictures.fetch('https://api.example.org/a.jpg', checked, tile), b'JPEGhttps://api.example.org/a.jpg')
        self.assertEqual(await pictures.fetch('https://api.example.org/a.jpg', checked, tile), b'JPEGhttps://api.example.org/a.jpg')
        self.assertEqual(asked, ['https://api.example.org/a.jpg'])   # the second time from the cache
        self.assertEqual(await pictures.fetch('/local/me.png', checked, tile), b'PNG')
        self.assertEqual(ha, ['/local/me.png'])
        self.assertIsNone(await pictures.fetch('https://other.org/a.jpg', checked, tile))   # refused: never asked
        self.assertEqual(len(asked), 1)
        # A picture that does not come is not asked again within the minute, then it is.
        self.assertIsNone(await pictures.fetch('https://api.example.org/gone.jpg', checked, tile))
        self.assertIsNone(await pictures.fetch('https://api.example.org/gone.jpg', checked, tile))
        self.assertEqual(asked.count('https://api.example.org/gone.jpg'), 1)
        now[0] += plugin_pictures.FAIL_SECONDS + 1
        self.assertIsNone(await pictures.fetch('https://api.example.org/gone.jpg', checked, tile))
        self.assertEqual(asked.count('https://api.example.org/gone.jpg'), 2)
        # A picture that came is fetched again after a long while.
        now[0] += plugin_pictures.KEEP_SECONDS
        await pictures.fetch('https://api.example.org/a.jpg', checked, tile)
        self.assertEqual(asked.count('https://api.example.org/a.jpg'), 2)

    @unittest.skipUnless(__import__('importlib').util.find_spec('PIL'), 'Pillow')
    async def test_the_atlas_paints_each_frame_as_asked(self):
        from PIL import Image
        import io
        q = self.question()
        wide = io.BytesIO()
        Image.new('RGB', (200, 100), (255, 0, 0)).save(wide, 'PNG')
        body = picture_paint.paint(q, [wide.getvalue(), wide.getvalue()], 'bmp24')
        with Image.open(io.BytesIO(body)) as atlas:
            self.assertEqual(atlas.size, (130, 90))
            rgb = atlas.convert('RGB')
            self.assertEqual(rgb.getpixel((30, 45)), (255, 0, 0))     # cover: the frame is filled
            self.assertEqual(rgb.getpixel((30, 2)), (255, 0, 0))
            self.assertEqual(rgb.getpixel((100, 45))[0], 255)        # contain: the picture whole, in the middle
            self.assertEqual(rgb.getpixel((100, 4)), (0x20, 0x20, 0x20))   # on the card's own colour, not black
            self.assertTrue(all(abs(c - 0x20) <= 2 for c in rgb.getpixel((0, 0))))  # a corner, rounded over the card's colour
        # Without any picture the frames stay the card's colour.
        body = picture_paint.paint(q, [None, None], 'bmp24')
        with Image.open(io.BytesIO(body)) as atlas:
            self.assertEqual(atlas.convert('RGB').getpixel((30, 45)), (0x20, 0x20, 0x20))


class Everywhere(unittest.TestCase):
    """Plugins are on in every app since 0.4.87: the stable app (added from the repository URL), the dev app and a copy
    without a Supervisor all have the Plugins page, its routes and its loops."""

    def test_every_channel_has_plugins(self):
        before = core.channel()
        self.addCleanup(core.set_channel, before)
        for channel in ('main', 'dev', None):
            core.set_channel(channel)
            self.assertTrue(core.plugins_enabled(), channel)


class Boards(unittest.TestCase):
    """A plugin for one board's hardware (P4 panel audio) is offered to that board's screens only, and to a screen
    whose core is too old for its API to none."""

    def test_a_board_plugin_fits_its_board_only(self):
        import plugins as plugin_service
        entry = type('Entry', (), {'manifest': pm.check(manifest(boards=['wavesharep4'], api='0.4',
                                                                 requires={'psram': True}), ENGLISH)})()
        service = type('Service', (), {'blocked': lambda self, entry: False})()
        fits = lambda screen: plugin_service.Plugins.fits(service, entry, screen)  # noqa: E731
        self.assertIsNone(fits({'board': 'wavesharep4', 'pictures': True}))
        self.assertEqual(fits({'board': 'guition', 'pictures': True}), 'board')
        self.assertEqual(fits({'board': 'waveshare4b', 'pictures': True}), 'board')
        # The editor names the boards as people know them.
        self.assertEqual(plugin_service.board_name('wavesharep4'), 'Waveshare ESP32-P4-86-Panel-ETH-2RO')
        self.assertEqual(plugin_service.board_name('nonexistent'), 'nonexistent')
        # PSRAM comes from the board when the screen says nothing about it (a KeyError before).
        self.assertIsNone(fits({'board': 'wavesharep4'}))
        entry.manifest = pm.check(manifest(requires={'psram': True}), ENGLISH)
        self.assertEqual(fits({'board': 'cyd'}), 'psram')
        self.assertIsNone(fits({'board': 'guition'}))


class ReadWhole(unittest.IsolatedAsyncioTestCase):
    """The index arrives in pieces: every piece is read, and a body past the limit is refused (the index of three
    plugins, 25 KB, came back cut off with content.read(n))."""

    async def test_every_piece_and_the_limit(self):
        import plugins as plugin_service

        class Content:
            def __init__(self, pieces):
                self.pieces = pieces

            async def iter_chunked(self, size):
                for piece in self.pieces:
                    yield piece

        response = type('Response', (), {'content': Content([b'{"a": ', b'"' + b'x' * 20000 + b'"', b'}'])})()
        self.assertEqual(len(json.loads(await plugin_service.read_whole(response, 1 << 20))['a']), 20000)
        with self.assertRaises(ValueError):
            await plugin_service.read_whole(type('Response', (), {'content': Content([b'x' * 10, b'x' * 10])})(), 15)


class Links(unittest.IsolatedAsyncioTestCase):
    """A plugin added with a link follows its repository's releases: a new release is read and offered as an update,
    the same one costs two calls of GitHub's API and nothing more, and nothing of it goes through Tessera."""

    async def test_a_new_release_is_read_the_same_one_is_not(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        manager = type('Manager', (), {'page_senders': {}})()
        service = plugin_service.Plugins(manager, Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        installed = plugin_service.Entry(manifest(), {'en': ENGLISH}, {}, 'link', 'community',
                                         repo='https://github.com/someone/tessera-bus', path='.', ref='a' * 40)
        service.keep_snapshot(installed)
        service.store.put('kitchen', {'id': 'bus', 'version': '1.0.0', 'source': 'link', 'ref': 'a' * 40})
        newest = {'sha': 'a' * 40}
        asked, read = [], []

        async def github(url, text=False):
            asked.append(url)
            return {'tag_name': 'v1.0.0'} if url.endswith('/releases/latest') else dict(newest)

        async def resolve_link(url, branch=None, folder=None, path=None):
            read.append((url, path))
        service._github, service.resolve_link = github, resolve_link
        await service.refresh_links(force=True)
        self.assertEqual((len(asked), read), (2, []))
        self.assertIs(service.links['bus'], installed)
        newest['sha'] = 'b' * 40   # the maker published a release
        await service.refresh_links()           # within the hour: nothing asked
        self.assertEqual(len(asked), 2)
        await service.refresh_links(force=True)
        self.assertEqual(read, [('https://github.com/someone/tessera-bus', '.')])

    async def test_an_update_builds_the_new_release_in(self):
        """#260: the plugins file of an update named the new release, not nothing. A release added with a link is not
        in the index and its snapshot is kept only after the file is written, so the link it was read from stands in."""
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()

        class FakeFirmware:
            task = None
            job = None

            def save_plugins(self, profile, text):
                (config / profile.replace('.yaml', '.plugins.yaml')).write_text(text)

            def start(self, data):
                async def build():
                    self.job = {'state': 'success'}
                self.task = asyncio.get_running_loop().create_task(build())

        class FakeManager:
            firmware = FakeFirmware()

            def __init__(self):
                self.build_queue = BuildQueue(self)
            ha = type('HA', (), {'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'board': 'guition'}

            def notify(self):
                pass
        FakeManager.updates = type('U', (), {'resolve': lambda self, screen: (screen['id'] + '.yaml', '10.0.0.1')})()
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        for version, ref in (('1.0.0', 'a' * 40), ('1.1.0', 'b' * 40)):
            service.links['bus'] = plugin_service.Entry(manifest(version=version), {'en': ENGLISH}, {}, 'link', 'community',
                                                        repo='https://github.com/someone/tessera-bus', path='.', ref=ref)
            await service.apply('hall', {'add': [{'id': 'bus', 'source': 'link', 'consent': True}]})
            await service.manager.build_queue.idle()
            with self.subTest(version):
                self.assertIn(f'ref: {ref}  # bus {version}', (config / 'hall.plugins.yaml').read_text())
                self.assertEqual(service.store.get('hall', 'bus')['state'], 'active')

    async def test_the_index_an_app_reads_is_the_version_a_screen_gets_back_and_forth(self):
        """The dev app reads the plugins index of the dev branch, the stable app that of main (Plugins.index_branches):
        a screen moved to dev and back takes each index's version through the same update,
        the newer one on dev and the older one again on main, so a lower version is an update too."""
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()

        class FakeFirmware:
            task = None
            job = None

            def save_plugins(self, profile, text):
                (config / profile.replace('.yaml', '.plugins.yaml')).write_text(text)

            def start(self, data):
                async def build():
                    self.job = {'state': 'success'}
                self.task = asyncio.get_running_loop().create_task(build())

        class FakeManager:
            firmware = FakeFirmware()

            def __init__(self):
                self.build_queue = BuildQueue(self)
            ha = type('HA', (), {'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'board': 'guition'}

            def notify(self):
                pass
        FakeManager.updates = type('U', (), {'resolve': lambda self, screen: (screen['id'] + '.yaml', '10.0.0.1')})()
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        for version, ref in (('1.0.0', 'a' * 40), ('1.1.0', 'b' * 40), ('1.0.0', 'a' * 40)):   # main, dev, main again
            service.index['bus'] = plugin_service.Entry(manifest(version=version), {'en': ENGLISH}, {}, 'index', 'community',
                                                        repo='https://github.com/someone/tessera-bus', path='.', ref=ref)
            await service.apply('hall', {'add': [{'id': 'bus', 'source': 'index', 'consent': True}]})
            await service.manager.build_queue.idle()
            with self.subTest(version=version, ref=ref[0]):
                self.assertIn(f'ref: {ref}  # bus {version}', (config / 'hall.plugins.yaml').read_text())
                self.assertEqual(service.store.get('hall', 'bus')['state'], 'active')


class LinkPath(unittest.IsolatedAsyncioTestCase):
    """The folder in a link goes into the screen's plugins file and into git's path: only plain names, never a step up."""

    async def test_a_strange_folder_is_refused_before_github_is_asked(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        manager = type('Manager', (), {'page_senders': {}})()
        service = plugin_service.Plugins(manager, Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        asked = []

        async def github(url, text=False):
            asked.append(url)
            raise AssertionError('GitHub was asked')
        service._github = github
        for folder in ('plugins/../secrets', 'a b', "x'y", 'plugins/bus:', 'plugins/bus #'):
            with self.subTest(folder):
                with self.assertRaises(ValueError):
                    await service.resolve_link(f'https://github.com/someone/repo/tree/main/{folder}')
        self.assertEqual(asked, [])


class LinkFolder(unittest.IsolatedAsyncioTestCase):
    """A link copied from GitHub to a plugin's folder (.../tree/main/plugins/bus) builds the newest release of that
    folder; a repository without a release keeps the link's own commit."""

    async def test_the_folder_of_the_newest_release(self):
        import yaml
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), Path(tmp.name) / 'data',
                                         Path(tmp.name) / 'esphome')
        released = {'v2.0.0': 'r' * 40, 'main': 'm' * 40}
        release = {'tag_name': 'v2.0.0'}
        asked = []

        async def github(url, text=False):
            asked.append(url)
            if url.endswith('/releases/latest'):
                if not release:
                    raise ValueError('not found')
                return release
            if '/commits/' in url:
                return {'sha': released[url.rsplit('/', 1)[1]]}
            if url.endswith('tessera-plugin.yaml'):
                return yaml.safe_dump(manifest())
            if '/contents/' in url and 'translations' in url:
                return [{'name': 'en.json'}]
            if url.endswith('translations/en.json'):
                return json.dumps(ENGLISH)
            return []
        service._github = github
        entry = await service.resolve_link('https://github.com/someone/plugins/tree/main/plugins/bus')
        self.assertEqual((entry.path, entry.ref, entry.label), ('plugins/bus', 'r' * 40, 'community'))
        self.assertTrue(any(u.endswith(f"{'r' * 40}/plugins/bus/tessera-plugin.yaml") for u in asked))
        release.clear()
        entry = await service.resolve_link('https://github.com/someone/plugins/tree/main/plugins/bus')
        self.assertEqual(entry.ref, 'm' * 40)

    async def test_a_link_nobody_runs_can_be_forgotten(self):
        # A release read from a link lives in the app's memory only; with no screen running it, it can leave the list.
        import yaml
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), Path(tmp.name) / 'data',
                                         Path(tmp.name) / 'esphome')

        async def github(url, text=False):
            if url.endswith('/releases/latest'):
                return {'tag_name': 'v1.0.0'}
            if '/commits/' in url:
                return {'sha': 'r' * 40}
            if url.endswith('tessera-plugin.yaml'):
                return yaml.safe_dump(manifest())
            if '/contents/' in url and 'translations' in url:
                return [{'name': 'en.json'}]
            if url.endswith('translations/en.json'):
                return json.dumps(ENGLISH)
            return []
        service._github = github
        entry = await service.resolve_link('https://github.com/someone/tessera-bus')
        self.assertIn(entry.id, service.listed())
        service.store.put('screen-1', {'id': entry.id, 'source': 'link', 'ref': entry.ref, 'version': entry.version})
        with self.assertRaises(ValueError):
            service.forget_link(entry.id)           # a screen still runs it
        self.assertIn(entry.id, service.listed())
        service.store.remove('screen-1', entry.id)
        service.forget_link(entry.id)
        self.assertNotIn(entry.id, service.listed())
        with self.assertRaises(ValueError):
            service.forget_link(entry.id)           # already gone

    async def test_its_picture_for_the_plugins_page(self):
        # store.png beside the manifest, at most a megabyte, is the plugin's picture; the app fetches it when shown.
        import yaml
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), Path(tmp.name) / 'data',
                                         Path(tmp.name) / 'esphome')
        listing = [{'name': 'README.md', 'size': 10}, {'name': 'store.png', 'size': 300_000}]

        async def github(url, text=False):
            if url.endswith('/releases/latest'):
                return {'tag_name': 'v1.0.0'}
            if '/commits/' in url:
                return {'sha': 'r' * 40}
            if url.endswith('tessera-plugin.yaml'):
                return yaml.safe_dump(manifest())
            if '/contents/' in url and 'translations' in url:
                return [{'name': 'en.json'}]
            if url.endswith('translations/en.json'):
                return json.dumps(ENGLISH)
            if '/contents/' in url:
                return listing
            return '# Bus'
        service._github = github
        entry = await service.resolve_link('https://github.com/someone/tessera-bus')
        self.assertEqual(service.editor_plugin(entry)['image'], f'api/plugins/{entry.id}/image?v={"r" * 40}')
        listing[1]['size'] = 2_000_000
        entry = await service.resolve_link('https://github.com/someone/tessera-bus')
        self.assertIsNone(entry.image, 'larger than the page takes')


class ImageRoom(unittest.TestCase):
    """The editor's room for a plugin on a 4 MB board comes from the screen's own last image and its slot."""

    def test_the_slot_follows_the_screen_table(self):
        firmware = Firmware.__new__(Firmware)
        firmware.wide_slots = lambda name: name == 'cyd.yaml'
        firmware.image_size = lambda name: 1_879_231
        self.assertEqual(firmware.image_room('cyd.yaml', 'wide'), {'size': 1_879_231, 'slot': 2_031_616})
        self.assertEqual(firmware.image_room('cyd.yaml', 'old'), {'size': 1_879_231, 'slot': 0x1C0000})
        self.assertIsNone(firmware.image_room('guition.yaml', 'wide'))   # 16 MB: no meter
        firmware.image_size = lambda name: None
        self.assertIsNone(firmware.image_room('cyd.yaml'))               # not built here yet


class Map(unittest.TestCase):
    ANSWER = {'30003025': {'passes': {
        'b': {'line': '7', 'to': 'Slotermeer', 'when': '2026-10-07T17:30:00', 'state': 'DRIVING'},
        'a': {'line': '15', 'to': 'Sloterdijk', 'when': '2026-10-07T17:20:00+02:00', 'state': 'PASSED'},
        'c': {'line': '15', 'to': 'Sloterdijk', 'when': '2026-10-07T17:25:00', 'state': 'PLANNED'}}}}

    def spec(self, **extra):
        return pm.check_map({'items': '$.{stop}.passes[*]', 'fields': {
            'line': 'line', 'at': {'path': 'when', 'as': 'epoch', 'tz': 'Europe/Amsterdam'}, 'state': 'state'}, **extra},
            'map', False)

    def test_items_of_an_object_sorted_filtered_and_cut(self):
        out = plugin_fetch.apply_map(self.spec(skip={'state': ['PASSED']}, sort='at', limit=1), self.ANSWER,
                                     {'stop': '30003025'})
        self.assertEqual([i['line'] for i in out['items']], ['15'])
        self.assertEqual(out['items'][0]['at'], 1791386700)    # 17:25 in Amsterdam (CEST), 15:25 UTC

    def test_where_with_an_empty_option_keeps_everything(self):
        spec = self.spec(where={'line': '{line}'}, sort='at')
        everything = plugin_fetch.apply_map(spec, self.ANSWER, {'stop': '30003025', 'line': ''})
        only = plugin_fetch.apply_map(spec, self.ANSWER, {'stop': '30003025', 'line': '7'})
        self.assertEqual(len(everything['items']), 3)
        self.assertEqual([i['line'] for i in only['items']], ['7'])

    def test_choices_once_each(self):
        spec = pm.check_map({'items': '$.{stop}.passes[*]', 'value': 'line', 'label': ['line', 'to']}, 'map', True)
        self.assertEqual(plugin_fetch.apply_choices(spec, self.ANSWER, {'stop': '30003025'}),
                         [{'value': '7', 'label': '7 · Slotermeer'}, {'value': '15', 'label': '15 · Sloterdijk'}])

    def test_paths(self):
        self.assertEqual(pm.parse_path('$.a[*].b[:2][0]'), [('key', 'a'), ('all',), ('key', 'b'), ('first', 2), ('at', 0)])
        for bad in ('a.b', '$.a[?(@.x)]', '$..a'):
            with self.subTest(bad), self.assertRaises(ValueError):
                pm.parse_path(bad)

    def test_text_is_bounded(self):
        spec = pm.check_map({'fields': {'name': 'name'}}, 'map', False)
        self.assertEqual(len(plugin_fetch.apply_map(spec, {'name': 'é' * 100})['name'].encode()), 48)


class Fetch(unittest.TestCase):
    def test_fill_encodes_and_needs_every_value(self):
        fetch = pm.check(manifest(), ENGLISH)['fetch'][0]
        url, _ = plugin_fetch.fill(fetch, {'stop': 'a b/c'}, {})
        self.assertEqual(url, 'https://api.example.org/stops/a%20b%2Fc')
        with self.assertRaises(plugin_fetch.FetchRefused):
            plugin_fetch.fill(fetch, {'stop': ''}, {})

    def test_home_addresses_are_refused(self):
        for address in ('192.168.1.10', '10.0.0.1', '127.0.0.1', '::1', 'fe80::1', '169.254.1.1', '::ffff:192.168.1.1'):
            with self.subTest(address):
                self.assertTrue(plugin_fetch.blocked_address(address))
        self.assertFalse(plugin_fetch.blocked_address('195.201.197.190'))

    def test_a_failure_keeps_the_last_answer_and_waits(self):
        clock = [1000.0]
        fetcher = plugin_fetch.Fetcher(clock=lambda: clock[0])
        answers = [{'x': 1}, OSError('HTTP 503')]

        async def download(url, headers, network):
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        fetcher.download = download
        checked = pm.check(manifest(), ENGLISH)
        fetch = checked['fetch'][0]

        async def run():
            _, first = await fetcher.get('bus', checked, fetch, {'stop': '1'}, {})
            self.assertEqual(first['data'], {'x': 1})
            clock[0] += 30
            _, same = await fetcher.get('bus', checked, fetch, {'stop': '1'}, {})   # not due yet: no ask
            self.assertEqual(len(answers), 1)
            clock[0] += 60
            _, failed = await fetcher.get('bus', checked, fetch, {'stop': '1'}, {})
            self.assertTrue(failed['stale'])
            self.assertEqual(failed['data'], {'x': 1})
            self.assertEqual(failed['retry'], clock[0] + 60)
        asyncio.run(run())

    def test_secrets_are_redacted(self):
        self.assertEqual(plugin_fetch.redact('GET /x?key=abc123 failed', {'key': 'abc123'}), 'GET /x?key=*** failed')


class Layout(unittest.TestCase):
    DOC = {'title': 'T', 'homePageId': 'aaaaaaaaaaaaaaaa', 'pages': [{
        'id': 'aaaaaaaaaaaaaaaa', 'navigation': {'excludeFromPagination': False},
        'topbar': {'leading': [], 'title': {'source': 'screen'}, 'trailing': []},
        'tiles': [{'id': 't1', 'content': {'kind': 'plugin', 'plugin': 'bus', 'tile': 'next',
                                            'options': {'stop': '30003025', 'walk': 3}},
                   'placement': {'row': 0, 'column': 0, 'columns': 2, 'rows': 1}, 'appearance': {'label': ''},
                   'interaction': {}}]}]}

    def test_a_plugin_tile_round_trips(self):
        page_layout.validate_document(json.loads(json.dumps(self.DOC)), core.DEFAULT_GRID)
        flat = page_layout.compile_tiles(self.DOC, core.DEFAULT_GRID)[0]
        self.assertEqual(flat['entity'], 'plugin:bus.next')
        self.assertEqual(flat['options']['plugin'], {'stop': '30003025', 'walk': 3})
        back = page_layout.tile_from_fields(flat, core.DEFAULT_GRID, ['aaaaaaaaaaaaaaaa'], id_factory=lambda: 't1')
        self.assertEqual(back['content'], self.DOC['pages'][0]['tiles'][0]['content'])

    def test_a_tile_of_an_entity_round_trips(self):
        doc = json.loads(json.dumps(self.DOC))
        doc['pages'][0]['tiles'][0]['content']['entityId'] = 'sensor.waste_next'
        page_layout.validate_document(json.loads(json.dumps(doc)), core.DEFAULT_GRID)
        flat = page_layout.compile_tiles(doc, core.DEFAULT_GRID)[0]
        self.assertEqual(flat['options']['plugin_entity'], 'sensor.waste_next')
        back = page_layout.tile_from_fields(flat, core.DEFAULT_GRID, ['aaaaaaaaaaaaaaaa'], id_factory=lambda: 't1')
        self.assertEqual(back['content'], doc['pages'][0]['tiles'][0]['content'])
        for wrong in ('screen.clock', 'not an entity'):
            with self.subTest(wrong), self.assertRaises(ValueError):
                core.validate_layout({'title': '', 'tiles': [{'entity': 'plugin:bus.next', 'name': '', 'slot': 0,
                                                              'options': {'plugin_entity': wrong}}]})

    def test_only_the_shape_is_checked(self):
        ok = {'title': '', 'tiles': [{'entity': 'plugin:bus.next', 'name': '', 'slot': 0,
                                      'options': {'plugin': {'a': 'x', 'b': 2, 'c': True}, 'tap': 'none'}}]}
        core.validate_layout(ok)
        for options in ({'plugin': {'a': {'nested': 1}}}, {'plugin': {'a': 'x' * 65}}, {'display': 'watch'},
                        {'plugin': {str(i): 1 for i in range(13)}}):
            with self.subTest(options), self.assertRaises(ValueError):
                core.validate_layout({'title': '', 'tiles': [{'entity': 'plugin:bus.next', 'name': '', 'slot': 0,
                                                              'options': options}]})
        self.assertFalse(core.entity_id('plugin:bus.next'))   # commands and events keep Home Assistant's ids

    def test_price(self):
        memory = {'psram': False, 'tile': 300, 'extra': 200}
        core.PLUGIN_MEMORY['plugin:bus.next'] = 900
        try:
            self.assertEqual(core.tile_cost({'entity': 'plugin:bus.next'}, memory), 1400)
            self.assertEqual(core.tile_cost({'entity': 'plugin:gone.tile'}, {**memory, 'psram': True}),
                             core.PLUGIN_PLACEHOLDER_BYTES)
        finally:
            core.PLUGIN_MEMORY.pop('plugin:bus.next')


class EntityTile(unittest.IsolatedAsyncioTestCase):
    async def test_state_name_and_named_attributes_only(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class FakeManager:
            ha = type('HA', (), {'states': {'sensor.waste_next': {'state': 'paper', 'attributes': {
                'friendly_name': 'Next collection', 'next_date': '2026-10-09', 'days': 2, 'secret': 'no'}}},
                'time_zone': 'Europe/Amsterdam', 'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        kind = {'id': 'next', 'domains': ['sensor'], 'attributes': ['next_date', 'days']}
        entity, part = service.entity_part(kind, {'options': {'plugin_entity': 'sensor.waste_next'}})
        self.assertEqual(entity, 'sensor.waste_next')
        self.assertEqual(part['state'], 'paper')
        self.assertEqual(part['name'], 'Next collection')
        self.assertEqual(set(part['attributes']), {'next_date', 'days'})
        self.assertIsInstance(part['attributes']['next_date'], int)   # a date as seconds, for the screen's own words
        _, wrong = service.entity_part(kind, {'options': {'plugin_entity': 'light.kitchen'}})
        self.assertEqual(wrong, {'wait': 'wrong_entity'})

    async def test_a_screensaver_step_names_its_entity(self):
        # #286: the screen asks for a step's pictures `for` its x.entity, and the app shows Home Assistant's pictures
        # only for the entity chosen for the step, so the step's x names it, after its fetch's answer.
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        states = {'sensor.photo': {'state': '/api/image_proxy/image.holiday?v=1', 'attributes': {'friendly_name': 'Photo'}},
                  'light.kitchen': {'state': 'on', 'attributes': {}}}

        class FakeManager:
            ha = type('HA', (), {'states': states, 'time_zone': 'UTC', 'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        kind = {'id': 'slideshow', 'domains': ['sensor'], 'attributes': [], 'options': [], 'data': True}
        step = lambda entity: service.saver_step('hall', 'plugin:photos.slideshow', None, kind, {'entity': entity}, states)
        service.saver_cache[('hall', 'plugin:photos.slideshow')] = {'entity': 'sensor.other', 'caption': 'Beach'}
        x = step('sensor.photo')
        self.assertEqual((x['entity'], x['state'], x['caption']), ('sensor.photo', states['sensor.photo']['state'], 'Beach'))
        self.assertEqual(step('light.kitchen'), {'wait': 'wrong_entity', 'caption': 'Beach'})
        self.assertIsNone(step(''))
        # A step without an entity sends its fetch's answer as it is.
        bare = {**kind, 'domains': []}
        self.assertEqual(service.saver_step('hall', 'plugin:photos.slideshow', None, bare, {}, states),
                         {'entity': 'sensor.other', 'caption': 'Beach'})


class PluginEntities(unittest.TestCase):
    def test_only_the_domains_the_editor_has_not(self):
        # GitHub #262: a plugin's tile of a plant was called gone, as the editor's list has only Tessera's own domains.
        # The add-on lists the entities of the domains plugins name that the editor lacks: a tile's, an input's and a
        # screensaver step's, and none it already has (sensors, a top bar's counter, and since the to-do card a to-do list),
        # so a plant is never cut off.
        import plugins as plugin_service
        entry = lambda **manifest: type('Entry', (), {'manifest': {'tiles': [], 'inputs': [], **manifest}})()
        states = {'plant.monstera': {'state': 'ok', 'attributes': {'friendly_name': 'Monstera'}},
                  'todo.shopping': {'state': '2', 'attributes': {'friendly_name': 'Shopping'}},
                  'schedule.heating': {'state': 'on', 'attributes': {}}, 'calendar.bins': {'state': 'off', 'attributes': {}},
                  'sensor.moisture': {'state': '40', 'attributes': {}}, 'counter.visits': {'state': '3', 'attributes': {}}}
        listed = [entry(tiles=[{'domains': ['sensor', 'plant']}], inputs=[{'domains': ['todo', 'counter', 'calendar']}]),
                  entry(savers=[{'domains': ['schedule']}, {'step': 'clock', 'domains': []}])]
        self.assertEqual(plugin_service.plugin_entities(listed, states),
                         [{'id': 'plant.monstera', 'name': 'Monstera'}, {'id': 'schedule.heating', 'name': 'schedule.heating'}])
        self.assertEqual(len(plugin_service.plugin_entities(listed, states, most=1)), 1)
        self.assertEqual(plugin_service.plugin_entities([entry()], states), [])
    async def test_selected_entity_options_are_sent_together(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class FakeManager:
            ha = type('HA', (), {'states': {
                'sensor.grid': {'state': '120', 'attributes': {'friendly_name': 'Grid', 'unit_of_measurement': 'W'}},
                'sensor.solar': {'state': '850', 'attributes': {'friendly_name': 'Solar', 'unit_of_measurement': 'W'}},
            }, 'time_zone': 'Europe/Amsterdam', 'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        kind = {'id': 'flow', 'domains': [], 'attributes': [], 'options': [
            {'id': 'grid', 'kind': 'entity', 'domains': ['sensor'], 'attributes': ['unit_of_measurement']},
            {'id': 'solar', 'kind': 'entity', 'domains': ['sensor'], 'attributes': ['unit_of_measurement']},
        ]}
        chosen = {'grid': 'sensor.grid', 'solar': 'sensor.solar'}
        self.assertEqual(service.option_entities(kind, chosen), ('sensor.grid', 'sensor.solar'))
        _, grid = service.state_part(kind['options'][0], chosen['grid'])
        self.assertEqual(grid['state'], '120')
        self.assertEqual(grid['attributes'], {'unit_of_measurement': 'W'})


class EntityOptions(unittest.IsolatedAsyncioTestCase):
    """Plugin API 0.15 (PR #288): a tile's options of kind entity choose Home Assistant entities, which the app sends
    under x.entities.<option id> and follows, without a new build."""

    async def asyncSetUp(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.states = {'sensor.grid': {'state': '120', 'last_updated': '2026-10-19T06:00:00+00:00',
                                       'attributes': {'friendly_name': 'Grid', 'unit_of_measurement': 'W'}},
                       'sensor.solar': {'state': '850', 'attributes': {'friendly_name': 'Solar', 'unit_of_measurement': 'W',
                                                                      'forecast': list(range(2000))}},
                       'sensor.soc': {'state': '64', 'attributes': {'friendly_name': 'Battery'}}}

        class FakeManager:
            ha = type('HA', (), {'states': self.states, 'time_zone': 'UTC', 'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}
        self.service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        data = manifest(api='0.15', tiles=[{'id': 'flow', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 900,
                                            'domains': ['sensor'], 'options': [
            {'id': 'grid', 'kind': 'entity', 'label': 'stop', 'domains': ['sensor'], 'attributes': ['unit_of_measurement']},
            {'id': 'solar', 'kind': 'entity', 'label': 'line', 'domains': ['sensor'], 'attributes': ['unit_of_measurement', 'forecast']}]}],
            fetch=[])
        checked = pm.check(data, ENGLISH)
        self.kind = checked['tiles'][0]
        kind = self.kind
        self.entry = type('Entry', (), {'tile': lambda self, tile_id: kind, 'text': lambda self, key: 'Flow'})()
        self.service.known = lambda plugin, inbox=None: self.entry

        async def no_data(*args, **kwargs):
            return None
        self.service.tile_data = no_data

    async def message(self, chosen, own=''):
        options = {'plugin': chosen, **({'plugin_entity': own} if own else {})}
        return await self.service.tile_message(0, {'entity': 'plugin:bus.flow', 'name': '', 'options': options})

    async def test_each_chosen_entity_goes_with_its_state_its_attributes_and_its_moment(self):
        x = (await self.message({'grid': 'sensor.grid'}, own='sensor.soc'))['x']
        self.assertEqual(x['entities']['grid']['state'], '120')
        self.assertEqual(x['entities']['grid']['attributes'], {'unit_of_measurement': 'W'})
        self.assertEqual(x['entities']['grid']['updated'], 1792389600)
        # The tile's own entity keeps the x it had before 0.15: no moment of its own.
        self.assertEqual((x['state'], x['name']), ('64', 'Battery'))
        self.assertNotIn('updated', x)
        self.assertEqual(self.service.option_entities(self.kind, {'grid': 'sensor.grid', 'solar': ''}), ('sensor.grid',))

    async def test_one_with_long_attributes_shares_the_room_and_never_takes_the_tile_with_it(self):
        x = (await self.message({'grid': 'sensor.grid', 'solar': 'sensor.solar'}))['x']
        self.assertEqual(x['entities']['grid']['state'], '120')
        self.assertEqual(x['entities']['solar']['state'], '850')
        self.assertLess(len(x['entities']['solar']['attributes']['forecast']), 2000)
        self.assertLessEqual(len(json.dumps(x, separators=(',', ':')).encode()), plugin_service_budget())

    async def test_a_place_keeps_its_room_beside_a_long_list_whose_last_items_give_way(self):
        # A radar's sky fills the room on its own; its place (an entity option) still goes, and the sky loses items.
        self.states['zone.home'] = {'state': '2', 'attributes': {'friendly_name': 'Home', 'latitude': 52.37, 'longitude': 4.89}}
        self.kind['options'][0]['domains'] = ['sensor', 'zone']
        self.kind['options'][0]['attributes'] = ['latitude', 'longitude']
        sky = {'items': [{'hex': f'{n:06x}', 'flight': f'KLM{n:04d}', 'lat': 52.3 + n / 1000, 'lon': 4.8 + n / 1000,
                          'alt': 30000 + n, 'gs': 420.5, 'track': 270.1, 'dst': n / 10} for n in range(40)]}

        async def full_sky(*args, **kwargs):
            return sky
        self.service.tile_data = full_sky
        x = (await self.message({'grid': 'zone.home'}))['x']
        self.assertEqual(x['entities']['grid']['attributes'], {'latitude': 52.37, 'longitude': 4.89})
        self.assertGreater(len(x['items']), 5)
        self.assertLess(len(x['items']), 40)
        self.assertLessEqual(len(json.dumps(x, separators=(',', ':')).encode()), plugin_service_budget())

    def test_a_fetch_says_how_to_reach_the_project(self):
        # planespotters.net (and others) refuse a server's request whose User-Agent has no contact URL or email.
        # The app's own fetcher, not a bare one: the app gave it a string of its own until 2026-11-15.
        self.assertRegex(self.service.fetcher.user_agent, r'\(\+https://')

    async def test_a_choice_of_another_domain_is_left_out(self):
        x = (await self.message({'grid': 'light.kitchen'})).get('x') or {}
        self.assertNotIn('entities', x)

    def test_the_editor_gets_the_entities_of_an_options_own_domain(self):
        import plugins as plugin_service
        entry = type('Entry', (), {'manifest': {'tiles': [{'domains': [], 'options': [
            {'kind': 'entity', 'domains': ['plant', 'sensor']}, {'kind': 'text'}]}], 'inputs': []}})()
        states = {'plant.fern': {'state': 'ok', 'attributes': {}}, 'sensor.moisture': {'state': '1', 'attributes': {}}}
        self.assertEqual(plugin_service.plugin_entities([entry], states), [{'id': 'plant.fern', 'name': 'plant.fern'}])


AIR_ENGLISH = {'app': {'name': 'Air', 'summary': 'The air in a room.', 'tile': 'Air quality', 'co2': 'CO2', 'pm25': 'PM2.5',
                       'voc': 'VOC', 'limits': 'Limits', 'standard': 'Standard', 'who': 'WHO', 'eu': 'EU',
                       'co2_limit': 'CO2 limit', 'label': 'Label'}, 'screen': {}}
AIR_OPTIONS = [
    {'id': 'co2', 'kind': 'entity', 'label': 'co2', 'domains': ['sensor'], 'device_class': ['carbon_dioxide']},
    {'id': 'pm25', 'kind': 'entity', 'label': 'pm25', 'domains': ['sensor'], 'device_class': ['pm25']},
    {'id': 'voc', 'kind': 'entity', 'label': 'voc', 'domains': ['sensor'],
     'matches': ['voc_index', 'total_volatile_organic_component_index']},
    {'id': 'standard', 'kind': 'choice', 'label': 'standard', 'default': 'who',
     'choices': [{'value': 'who', 'label': 'who'}, {'value': 'eu', 'label': 'eu'}]},
    {'id': 'co2_limit', 'kind': 'number', 'label': 'co2_limit', 'min': 400, 'max': 5000, 'step': 50, 'unit': 'ppm',
     'optional': True, 'group': 'limits', 'placeholder_from': {'option': 'standard', 'values': {'who': 1000, 'eu': 800}}},
]


def air(options=None, api='0.26', **tile):
    """A manifest of one tile of the air in a room, with the options of plugin API 0.26."""
    return {'id': 'air', 'version': '1.0.0', 'api': api, 'icon': 'air-filter', 'maintainer': 'someone', 'license': 'MIT',
            'topics': ['home'], 'tiles': [{'id': 'room', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 900,
                                           'options': [dict(option) for option in (AIR_OPTIONS if options is None else options)],
                                           **tile}]}


def air_option(**changes):
    """AIR_OPTIONS with one option changed, by its id; a value of None takes the field off."""
    out = []
    for option in AIR_OPTIONS:
        option = dict(option)
        if option['id'] == changes.get('id'):
            option.update(changes)
            option = {key: value for key, value in option.items() if value is not None}
        out.append(option)
    return out


class MoreOptions(unittest.TestCase):
    """Plugin API 0.26: an entity option that says which entities it is for, a tile filled from one device, options
    under a heading, a number that may stay empty, and up to 24 options of a tile."""

    def refuses(self, data, word=None):
        with self.assertRaises(pm.ManifestError) as caught:
            pm.check(data, AIR_ENGLISH)
        if word:
            self.assertIn(word, str(caught.exception))

    def test_the_whole_tile_passes_and_keeps_every_field(self):
        tile = pm.check(air(from_device=True), AIR_ENGLISH)['tiles'][0]
        options = {option['id']: option for option in tile['options']}
        self.assertTrue(tile['from_device'])
        self.assertEqual(options['co2']['device_class'], ['carbon_dioxide'])
        self.assertEqual(options['voc']['matches'], ['voc_index', 'total_volatile_organic_component_index'])
        self.assertEqual((options['co2_limit']['optional'], options['co2_limit']['group']), (True, 'limits'))
        self.assertEqual(options['co2_limit']['placeholder_from'], {'option': 'standard', 'values': {'who': 1000, 'eu': 800}})
        self.assertNotIn('default', options['co2_limit'])
        self.assertFalse(pm.check(air(), AIR_ENGLISH)['tiles'][0]['from_device'])

    def test_every_new_field_belongs_to_0_26(self):
        plain = [{'id': 'label', 'kind': 'text', 'label': 'label'}]
        pm.check(air(plain, api='0.25'), AIR_ENGLISH)
        for name, options, tile in (
                ('device_class', [AIR_OPTIONS[0]], {}), ('matches', [AIR_OPTIONS[2]], {}),
                ('group', [{**plain[0], 'group': 'limits'}], {}),
                ('optional', [{'id': 'n', 'kind': 'number', 'label': 'label', 'min': 0, 'max': 9, 'optional': True}], {}),
                # A number with `placeholder_from` is `optional` too, which the sentence names first.
                ('optional', [AIR_OPTIONS[3], {k: v for k, v in AIR_OPTIONS[4].items() if k != 'group'}], {}), ('from_device', plain, {'from_device': False}),
                ('more than 12', [{**plain[0], 'id': f'o{i}'} for i in range(13)], {})):
            with self.subTest(name):
                self.refuses(air(options, api='0.25', **tile), 'needs plugin API 0.26 (api: "0.26")')
                self.refuses(air(options, api='0.15', **tile), name)

    def test_which_entities_an_option_is_for(self):
        for field in ('device_class', 'matches'):
            for wrong in ([], ['Carbon-Dioxide'], [f'w{i}' for i in range(9)], 'pm25', [''], [3]):
                with self.subTest(field=field, wrong=wrong):
                    self.refuses(air(air_option(id='co2', **{'device_class': None, field: wrong})))
            # Only an option of kind entity names them.
            self.refuses(air([{'id': 'label', 'kind': 'text', 'label': 'label', field: ['pm25']}]), 'does not belong')
        both = pm.check(air(air_option(id='co2', matches=['co2'])), AIR_ENGLISH)['tiles'][0]['options'][0]
        self.assertEqual((both['device_class'], both['matches']), (['carbon_dioxide'], ['co2']))

    def test_an_entity_fits_by_its_class_its_translation_key_or_the_end_of_its_id(self):
        options = {option['id']: option for option in pm.check(air(), AIR_ENGLISH)['tiles'][0]['options']}
        co2, voc = options['co2'], options['voc']
        self.assertTrue(pm.entity_fits(co2, 'sensor.hall_co2', 'carbon_dioxide'))
        self.assertFalse(pm.entity_fits(co2, 'sensor.hall_co2', 'pm25'))
        self.assertFalse(pm.entity_fits(co2, 'sensor.hall_co2'))
        self.assertTrue(pm.entity_fits(voc, 'sensor.hall_air', None, 'voc_index'))
        self.assertTrue(pm.entity_fits(voc, 'sensor.hall_voc_index'))
        self.assertTrue(pm.entity_fits(voc, 'sensor.hall_total_volatile_organic_component_index', 'aqi', 'other'))
        self.assertFalse(pm.entity_fits(voc, 'sensor.hall_voc_index_raw'))
        self.assertFalse(pm.entity_fits(voc, 'sensor.hallvoc_index'), 'a word of the id, never the end of another word')
        self.assertFalse(pm.entity_fits(voc, 'sensor.hall_temperature', 'temperature', 'temperature'))
        # Never an entity of another domain, whatever it says of itself.
        self.assertFalse(pm.entity_fits(co2, 'number.hall_co2', 'carbon_dioxide'))
        # An option that names neither takes every entity of its domains, as before 0.26.
        every = {'kind': 'entity', 'domains': ['sensor', 'binary_sensor']}
        self.assertTrue(pm.entity_fits(every, 'binary_sensor.door'))
        self.assertFalse(pm.entity_fits(every, 'light.door'))
        # The rule shapes the editor's list only: a value of any entity of the domains is kept.
        self.assertEqual(pm.option_value(co2, 'sensor.hall_temperature'), 'sensor.hall_temperature')

    def test_a_tile_filled_from_a_device_has_two_options_that_say_which_entities(self):
        pm.check(air(from_device=True), AIR_ENGLISH)
        pm.check(air([AIR_OPTIONS[0], AIR_OPTIONS[2]], from_device=True), AIR_ENGLISH)
        any_sensor = {'id': 'other', 'kind': 'entity', 'label': 'label', 'domains': ['sensor']}
        for options in ([AIR_OPTIONS[0]], [AIR_OPTIONS[0], any_sensor], [AIR_OPTIONS[3]], []):
            with self.subTest(options=[o['id'] for o in options]):
                self.refuses(air(options, from_device=True), 'from_device')
                pm.check(air(options, from_device=False), AIR_ENGLISH)
        self.refuses(air(from_device='yes'), 'true or false')

    def test_a_group_is_a_text_of_the_plugin(self):
        english = {**AIR_ENGLISH, 'app': {k: v for k, v in AIR_ENGLISH['app'].items() if k != 'limits'}}
        with self.assertRaises(pm.ManifestError) as caught:
            pm.check(air(), english)
        self.assertIn('limits', str(caught.exception))
        self.refuses(air(air_option(id='co2', group='Not a key')))
        # Every kind of option may stand under one, a screensaver's too.
        self.assertEqual(pm.check(air(air_option(id='co2', group='limits')), AIR_ENGLISH)['tiles'][0]['options'][0]['group'], 'limits')
        saver = {'id': 'face', 'name': 'tile', 'step': 'clock', 'memory': 900,
                 'options': [{'id': 'label', 'kind': 'text', 'label': 'label', 'group': 'limits'}]}
        self.assertEqual(pm.check({**air([]), 'savers': [saver]}, AIR_ENGLISH)['savers'][0]['options'][0]['group'], 'limits')
        self.refuses({**air([], api='0.25'), 'savers': [saver]}, '0.26')

    def test_a_number_may_stay_empty(self):
        number = lambda **given: [{'id': 'n', 'kind': 'number', 'label': 'label', 'min': 400, 'max': 5000, **given}]
        option = pm.check(air(number(optional=True)), AIR_ENGLISH)['tiles'][0]['options'][0]
        self.assertTrue(option['optional'])
        self.assertNotIn('default', option)
        for wrong in (number(optional=False), number(optional='yes'), number(optional=True, default=800),
                      [{'id': 'label', 'kind': 'text', 'label': 'label', 'optional': True}]):
            with self.subTest(wrong=wrong):
                self.refuses(air(wrong))
        # A filled value is checked as every number; an empty one is no key at all, never 0.
        self.assertEqual(pm.option_value(option, 800), 800)
        for wrong in (399, 5001, '', None, '800'):
            with self.subTest(value=wrong), self.assertRaises(pm.ManifestError):
                pm.option_value(option, wrong)
        self.assertTrue(core.plugin_options({'co2': 'sensor.hall_co2'}))
        self.assertFalse(core.plugin_options({'co2_limit': None}))

    def test_the_values_leave_an_empty_number_out(self):
        import plugins as plugin_service
        tile = pm.check(air(), AIR_ENGLISH)['tiles'][0]
        values = lambda chosen: plugin_service.Plugins.values_of(None, None, tile, chosen)
        self.assertEqual(values({'co2': 'sensor.hall_co2'}), {'standard': 'who', 'co2': 'sensor.hall_co2'})
        self.assertEqual(values({}), {'standard': 'who'})
        self.assertEqual(values({'co2_limit': 900, 'standard': 'eu'}), {'standard': 'eu', 'co2_limit': 900})
        # A value that is no number of the option (an older editor's empty text, one out of range) is left out too.
        for wrong in ('', 0, 99999):
            with self.subTest(value=wrong):
                self.assertNotIn('co2_limit', values({'co2_limit': wrong}))

    def test_what_applies_while_a_number_is_empty(self):
        limit = lambda **source: air_option(id='co2_limit', placeholder_from={'option': 'standard', 'values': {'who': 1000}, **source})
        # A value of the choice may lack a number.
        self.assertEqual(pm.check(air(limit()), AIR_ENGLISH)['tiles'][0]['options'][4]['placeholder_from']['values'], {'who': 1000})
        for wrong, word in ((limit(option='missing'), 'choice'), (limit(option='co2'), 'choice'), (limit(option='co2_limit'), 'choice'),
                            (limit(values={'us': 900}), 'us'), (limit(values={'who': 'high'}), 'number'), (limit(values={}), 'values'),
                            (limit(values=[1000]), 'mapping'), (limit(more=1), 'more'),
                            (air_option(id='co2_limit', optional=None), 'optional'),
                            (air_option(id='co2_limit', placeholder_from={'option': 'standard'}), 'values')):
            with self.subTest(word=word):
                self.refuses(air(wrong), word)
        # The choice it names has fixed choices and keeps one value: no list from a fetch, no list of picks.
        several = [{**AIR_OPTIONS[3], 'multiple': 2, 'default': []}, AIR_OPTIONS[4]]
        self.refuses(air(several), 'choice')

    def test_a_tile_takes_24_options_and_a_screensaver_twelve(self):
        options = lambda n: [{'id': f'o{i}', 'kind': 'text', 'label': 'label'} for i in range(n)]
        self.assertEqual(len(pm.check(air(options(24)), AIR_ENGLISH)['tiles'][0]['options']), 24)
        self.refuses(air(options(25)), 'at most 24')
        saver = lambda n: {**air([]), 'savers': [{'id': 'face', 'name': 'tile', 'step': 'clock', 'memory': 900, 'options': options(n)}]}
        pm.check(saver(12), AIR_ENGLISH)
        self.refuses(saver(13), 'at most 12')
        # The layout check keeps as many, within the same bytes.
        self.assertEqual(core.PLUGIN_OPTION_MAX, pm.MAX_OPTIONS)
        self.assertTrue(core.plugin_options({f'o{i}': 'sensor.hall_carbon_dioxide' for i in range(24)}))
        self.assertFalse(core.plugin_options({f'o{i}': 1 for i in range(25)}))
        self.assertFalse(core.plugin_options({f'o{i}': 'x' * 64 for i in range(24)}), 'the 1280 bytes stay')

    def test_the_editor_gets_the_entities_that_fit_and_their_devices(self):
        import plugins as plugin_service
        entry = type('Entry', (), {'manifest': pm.check(air(from_device=True), AIR_ENGLISH)})()
        registry = [
            {'entity_id': 'sensor.one_co2', 'device_id': 'd1', 'translation_key': 'carbon_dioxide'},
            {'entity_id': 'sensor.one_pm25', 'device_id': 'd1'},
            {'entity_id': 'sensor.one_raw_pm25', 'device_id': 'd1', 'translation_key': 'raw_pm25', 'disabled_by': 'integration',
             'original_device_class': 'pm25'},
            {'entity_id': 'sensor.one_voc_index', 'device_id': 'd1', 'entity_category': 'diagnostic'},
            {'entity_id': 'sensor.one_temperature', 'device_id': 'd1'},
            {'entity_id': 'sensor.two_air', 'device_id': 'd2', 'translation_key': 'voc_index'},
            {'entity_id': 'number.one_co2', 'device_id': 'd1'}]
        states = {'sensor.one_co2': {'state': '612', 'attributes': {'device_class': 'carbon_dioxide'}},
                  'sensor.one_pm25': {'state': '4', 'attributes': {'device_class': 'pm25'}},
                  'sensor.one_voc_index': {'state': '90', 'attributes': {}},
                  'sensor.one_temperature': {'state': '21', 'attributes': {'device_class': 'temperature'}},
                  'sensor.two_air': {'state': '80', 'attributes': {}},
                  'sensor.yaml_co2': {'state': '500', 'attributes': {'device_class': 'carbon_dioxide'}},
                  'number.one_co2': {'state': '1', 'attributes': {'device_class': 'carbon_dioxide'}}}
        devices = [{'id': 'd1', 'name': 'airgradient-one', 'name_by_user': 'AirGradient ONE'}, {'id': 'd2', 'name': 'Sensirion'},
                   {'id': 'd3', 'name': 'A lamp'}]
        facts, names = plugin_service.entity_facts([entry], states, registry, devices)
        self.assertEqual(facts, {
            'sensor.one_co2': {'device': 'd1', 'device_class': 'carbon_dioxide', 'translation_key': 'carbon_dioxide'},
            'sensor.one_pm25': {'device': 'd1', 'device_class': 'pm25'},
            'sensor.one_raw_pm25': {'device': 'd1', 'device_class': 'pm25', 'translation_key': 'raw_pm25', 'disabled': True},
            'sensor.one_voc_index': {'device': 'd1', 'category': 'diagnostic'},
            'sensor.two_air': {'device': 'd2', 'translation_key': 'voc_index'},
            'sensor.yaml_co2': {'device_class': 'carbon_dioxide'}})
        self.assertEqual(names, {'d1': 'AirGradient ONE', 'd2': 'Sensirion'})
        # No plugin with such an option: nothing travels, however many sensors a home has.
        plain = type('Entry', (), {'manifest': pm.check(air([{'id': 'any', 'kind': 'entity', 'label': 'label', 'domains': ['sensor']}]),
                                                         AIR_ENGLISH)})()
        self.assertEqual(plugin_service.entity_facts([plain], states, registry, devices), ({}, {}))
        self.assertEqual(plugin_service.entity_facts([entry], states, None, None)[0]['sensor.one_co2'], {'device_class': 'carbon_dioxide'})

    def test_the_payload_names_them_and_every_field_of_an_option(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class FakeManager:
            ha = type('HA', (), {'states': {'sensor.one_co2': {'state': '612', 'attributes': {'device_class': 'carbon_dioxide'}}},
                                 'registry': [{'entity_id': 'sensor.one_co2', 'device_id': 'd1'}],
                                 'devices': [{'id': 'd1', 'name': 'AirGradient ONE'}],
                                 'changed': asyncio.Event(), 'dirty': set()})()
            page_senders, aliases, firmware = {}, {}, None
            updates = type('Updates', (), {'resolve': lambda self, screen: (None, None)})()

            def screens(self):
                return []
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        service._take_index({'format': 1, 'plugins': [{
            'id': 'air', 'repo': 'https://github.com/MaxGramser/tessera-plugins', 'path': 'plugins/air', 'label': 'tessera',
            'release': {'version': '1.0.0', 'sha': 'a' * 40, 'date': '2026-11-14'}, 'manifest': air(from_device=True),
            'translations': {'en': AIR_ENGLISH, 'nl': {'app': {'limits': 'Grenzen'}}}}]})
        payload = service.payload()
        self.assertEqual(payload['entity_facts'], {'sensor.one_co2': {'device': 'd1', 'device_class': 'carbon_dioxide'}})
        self.assertEqual(payload['devices'], {'d1': 'AirGradient ONE'})
        tile = payload['plugins'][0]['tiles'][0]
        options = {option['id']: option for option in tile['options']}
        self.assertTrue(tile['from_device'])
        self.assertEqual((options['co2']['device_class'], options['voc']['matches'][0]), (['carbon_dioxide'], 'voc_index'))
        limit = options['co2_limit']
        self.assertEqual(limit['group'], {'en': 'Limits', 'nl': 'Grenzen'})
        self.assertEqual((limit['optional'], limit['placeholder_from']['values']['eu'], limit['unit']), (True, 800, 'ppm'))
        self.assertNotIn('default', limit)
        self.assertNotIn('group', options['co2'])


PLACE_ENGLISH = {'app': {'name': 'Weather', 'summary': 'The weather where you are.', 'tile': 'Weather', 'place': 'Place',
                         'label': 'Label', 'card': 'Card'}, 'screen': {}}
PLACE_OPTION = {'id': 'place', 'kind': 'entity', 'label': 'place', 'domains': ['zone', 'person', 'device_tracker'],
                'attributes': ['latitude', 'longitude'], 'default': 'zone.home'}
PLACE_URL = 'https://api.example.org/forecast?lat={place.latitude:2}&lon={place.longitude:2}'


def place_plugin(api='0.27', url=PLACE_URL, options=None, fetch=None, tiles=None, **more):
    """A manifest of the weather where a chosen entity is (plugin API 0.27): its fetch reads the entity's latitude and
    longitude, and a second fetch the screen asks for, with the details of a row."""
    data = {'id': 'weather', 'version': '1.0.0', 'api': api, 'icon': 'weather-partly-cloudy', 'maintainer': 'someone',
            'license': 'MIT', 'topics': ['weather'], 'permissions': {'network': ['api.example.org']},
            'attributes': ['cloud'], 'privacy': 'https://example.org/p',
            'tiles': tiles if tiles is not None else [{'id': 'now', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 600,
                                                       'data': 'forecast', 'options': [dict(o) for o in (options or [PLACE_OPTION])]}],
            'fetch': [{'id': 'forecast', 'url': url, 'every': '10m',
                       'map': {'fields': {'temp': {'path': 'current.temperature', 'as': 'number'}, 'sky': 'current.sky'}}},
                      *(fetch or [])]}
    data.update(more)
    return data


DETAIL = {'id': 'detail', 'url': 'https://api.example.org/rows/{row}?day={day}', 'every': '1m', 'asked': ['row', 'day'],
          'map': {'fields': {'title': 'title', 'at': {'path': 'when', 'as': 'epoch'}}}}


class FetchMore(unittest.TestCase):
    """Plugin API 0.27, the manifest: a fetch that reads an attribute of the entity a person chose, an entity option
    with a default, a fetch the screen asks for, twelve fields, and places for pictures in a popup."""

    def refuses(self, data, word=None):
        with self.assertRaises(pm.ManifestError) as caught:
            pm.check(data, PLACE_ENGLISH)
        if word:
            self.assertIn(word, str(caught.exception))

    def test_a_fetch_reads_the_chosen_entitys_attributes(self):
        out = pm.check(place_plugin(), PLACE_ENGLISH)
        fetch = out['fetch'][0]
        self.assertEqual(fetch['reads'], [{'option': 'place', 'attribute': 'latitude', 'decimals': 2},
                                          {'option': 'place', 'attribute': 'longitude', 'decimals': 2}])
        self.assertEqual(fetch['placeholders'], [])
        self.assertEqual(out['tiles'][0]['options'][0]['default'], 'zone.home')
        self.assertEqual(out['sends'], [{'fetch': 'forecast', 'host': 'api.example.org',
                                         'reads': ['place.latitude', 'place.longitude']}])
        # Its state, without decimals, in a header too.
        stated = pm.check(place_plugin(url='https://api.example.org/now', fetch=None), PLACE_ENGLISH)
        self.assertEqual(stated['sends'], [])
        data = place_plugin()
        data['fetch'][0]['headers'] = {'X-Where': '{place.state}'}
        self.assertIn({'option': 'place', 'attribute': 'state', 'decimals': None}, pm.check(data, PLACE_ENGLISH)['fetch'][0]['reads'])

    def test_every_wrong_attribute_placeholder_is_named(self):
        text = {'id': 'place', 'kind': 'text', 'label': 'place'}
        for data, word in (
                (place_plugin(options=[text]), 'option of kind entity'),
                (place_plugin(url='https://api.example.org/x?a={place.altitude}'), '"altitude"'),
                (place_plugin(url='https://{place.state}.example.org/x'), 'fixed host'),
                (place_plugin(url='https://api.example.org:{place.state}/x'), 'fixed host'),
                (place_plugin(url='https://{place.state}@api.example.org/x'), 'fixed host'),
                (place_plugin(url='https://api.example.org/x?a={place.latitude:7}'), 'decimals from 0 to 6'),
                (place_plugin(url='https://api.example.org/x?a={place.lat-x}'), 'no placeholder'),
                (place_plugin(url='https://api.example.org/x?a={where.latitude}'), '"where"'),
                (place_plugin(api='0.26', options=[{k: v for k, v in PLACE_OPTION.items() if k != 'default'}]),
                 'needs plugin API 0.27 (api: "0.27")')):
            with self.subTest(word=word, url=data['fetch'][0]['url']):
                self.refuses(data, word)
        # Every tile whose data the fetch is has the option: a second tile without it is refused.
        second = {'id': 'other', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '1x1'}, 'memory': 600, 'data': 'forecast'}
        tiles = place_plugin()['tiles'] + [second]
        self.refuses(place_plugin(tiles=tiles), 'every tile')
        # A fetch that fills a list of choices has no tile's entity to read.
        choices = place_plugin(url='https://api.example.org/x', fetch=[{
            'id': 'areas', 'url': 'https://api.example.org/areas?lat={place.latitude}', 'every': '1h',
            'map': {'items': '$.areas[*]', 'value': 'id', 'label': 'name'}}])
        choices['tiles'][0]['options'].append({'id': 'area', 'kind': 'choice', 'label': 'label', 'options_from': 'areas'})
        self.refuses(choices, 'only a fetch that is a tile')

    def test_an_entity_option_may_start_with_an_entity(self):
        tile = pm.check(place_plugin(), PLACE_ENGLISH)['tiles'][0]
        import plugins as plugin_service
        self.assertEqual(plugin_service.Plugins.values_of(None, None, tile, {}), {'place': 'zone.home'})
        self.assertEqual(plugin_service.Plugins.values_of(None, None, tile, {'place': 'person.someone'}), {'place': 'person.someone'})
        self.assertEqual(plugin_service.Plugins.values_of(None, None, tile, {'place': ''}), {'place': ''}, 'taken off stays off')
        for wrong, word in (('light.kitchen', 'domains'), ('zone', 'entity id'), (3, 'text')):
            with self.subTest(wrong=wrong):
                self.refuses(place_plugin(options=[{**PLACE_OPTION, 'default': wrong}]), word)
        self.refuses(place_plugin(api='0.26', url='https://api.example.org/now'), 'needs plugin API 0.27')
        pm.check(place_plugin(api='0.26', url='https://api.example.org/now', options=[{**PLACE_OPTION, 'default': ''}]), PLACE_ENGLISH)

    def test_a_fetch_the_screen_asks_for(self):
        out = pm.check(place_plugin(fetch=[DETAIL]), PLACE_ENGLISH)
        detail = out['fetch'][1]
        self.assertEqual((detail['asked'], detail['placeholders']), (['row', 'day'], ['day', 'row']))
        secret = place_plugin(fetch=[{**DETAIL, 'headers': {'Authorization': 'Bearer {key}'}}],
                              inputs=[{'id': 'key', 'kind': 'secret', 'label': 'label'}])
        self.assertEqual(pm.check(secret, PLACE_ENGLISH)['fetch'][1]['placeholders'], ['day', 'key', 'row'])
        saver = {'id': 'face', 'name': 'tile', 'step': 'own', 'memory': 600, 'data': 'detail'}
        with_choice = place_plugin(fetch=[{**DETAIL, 'map': {'items': '$[*]', 'value': 'id', 'label': 'name'}}])
        with_choice['tiles'][0]['options'].append({'id': 'pick', 'kind': 'choice', 'label': 'label', 'options_from': 'detail'})
        for data, word in (
                (place_plugin(fetch=[{**DETAIL, 'asked': ['row', 'day', 'a', 'b', 'c']}]), 'at most 4'),
                (place_plugin(fetch=[{**DETAIL, 'asked': []}]), '1 to 4'),
                (place_plugin(fetch=[{**DETAIL, 'asked': ['row', 'row']}]), '1 to 4'),
                (place_plugin(fetch=[{**DETAIL, 'asked': ['Row']}]), '1 to 4'),
                (place_plugin(fetch=[{**DETAIL, 'url': 'https://api.example.org/rows/{row}?day={day}&x={nope}'}]), '{nope}'),
                (place_plugin(fetch=[{**DETAIL, 'asked': ['row', 'day', 'unused']}]), '"unused"'),
                (place_plugin(fetch=[{**DETAIL, 'url': 'https://api.example.org/rows/{row}?day={day}&l={place.latitude}'}]),
                 'only a fetch that is a tile'),
                (place_plugin(fetch=[{**DETAIL, 'url': 'https://{row}.example.org/{day}'}]), 'fixed host'),
                (place_plugin(fetch=[{**DETAIL, 'url': 'https://elsewhere.example.org/{row}/{day}'}]), 'permissions.network'),
                (place_plugin(fetch=[{**DETAIL, 'each': 'row'}]), 'each'),
                (place_plugin(fetch=[DETAIL], inputs=[{'id': 'row', 'kind': 'text', 'label': 'label'}]), 'input'),
                (place_plugin(url='https://api.example.org/now', fetch=[DETAIL],
                              tiles=[{**place_plugin()['tiles'][0], 'data': 'detail'}]), 'no tile'),
                ({**place_plugin(fetch=[DETAIL]), 'savers': [saver]}, 'no tile'),
                (with_choice, 'no tile'),
                (place_plugin(api='0.26', url='https://api.example.org/now', options=[{'id': 'place', 'kind': 'text', 'label': 'place'}],
                              fetch=[DETAIL]), 'needs plugin API 0.27 (api: "0.27")')):
            with self.subTest(word=word):
                self.refuses(data, word)

    def test_twelve_fields_and_the_api_that_brought_them(self):
        fields = lambda n: {f'f{i}': f'a.f{i}' for i in range(n)}
        plain = lambda api, n: place_plugin(api=api, url='https://api.example.org/now', options=[{'id': 'place', 'kind': 'text', 'label': 'place'}],
                                            fetch=None) | {'fetch': [{'id': 'forecast', 'url': 'https://api.example.org/now', 'every': '10m',
                                                                      'map': {'fields': fields(n)}}]}
        self.assertEqual(len(pm.check(plain('0.27', 12), PLACE_ENGLISH)['fetch'][0]['map']['fields']), 12)
        pm.check(plain('0.26', 8), PLACE_ENGLISH)
        self.refuses(plain('0.27', 13), '1 to 12 fields')
        self.refuses(plain('0.26', 9), 'more than 8 fields needs plugin API 0.27')
        # An answer's fields and a tile's, the same.
        answers = plain('0.26', 1) | {'permissions': {'network': ['api.example.org'], 'ha_commands': ['history/history_during_period']},
                                       'answers': [{'command': 'history/history_during_period', 'fields': fields(9)}]}
        self.refuses(answers, 'answers[0].fields')
        pm.check(answers | {'api': '0.27'}, PLACE_ENGLISH)
        self.assertEqual(pm.MAX_FIELDS, 12)

    def test_a_picture_address_comes_whole(self):
        # A text stops at 48 bytes, which cut planespotters' addresses into ones that answer 404; `as: url` (0.28) keeps
        # an http(s) address whole up to 255 bytes, or gives none.
        import plugin_fetch
        photo = 'https://t.plnspttrs.net/03074/1998710_fdd0467702_280.jpg'
        item = {'photos': [{'thumbnail_large': {'src': photo}}]}
        path = pm.parse_path('photos[0].thumbnail_large.src', root=False)
        self.assertEqual(plugin_fetch.field_value(item, {'path': path, 'as': 'url'}), photo)
        self.assertNotEqual(plugin_fetch.field_value(item, {'path': path, 'as': 'text'}), photo)
        for wrong in ('ftp://example.org/a.jpg', 'https://example.org/' + 'a' * 300, 'not an address', 7):
            self.assertIsNone(plugin_fetch.field_value({'src': wrong}, {'path': pm.parse_path('src', root=False), 'as': 'url'}))
        with_url = lambda api: place_plugin(api=api, url='https://api.example.org/now', options=[{'id': 'place', 'kind': 'text', 'label': 'place'}],
                                            fetch=None) | {'fetch': [{'id': 'forecast', 'url': 'https://api.example.org/now', 'every': '1d',
                                                                      'map': {'fields': {'photo': {'path': 'src', 'as': 'url'}}}}]}
        # And whole in the answer to the screen's own ask. A text is bounded once, by its kind, in the map; the answer
        # that came through a map is then only fitted to its bytes, and one that came as it was has no kinds, so every
        # text in it stops at TEXT_BYTES, an address too: nothing guesses a kind from what a text looks like.
        import plugins as plugin_service
        spec = pm.check_map({'items': '$.list[*]', 'fields': {'photo': {'path': 'src', 'as': 'url'}, 'by': 'by'}}, 'map', False)
        mapped = plugin_fetch.apply_map(spec, {'list': [{'src': photo, 'by': 'x' * 80}]})
        self.assertEqual(plugin_service.bounded(mapped, mapped=True)['items'][0], {'photo': photo, 'by': 'x' * 48})
        self.assertEqual(plugin_service.bounded({'photo': photo, 'by': 'x' * 80}),
                         {'photo': photo[:plugin_fetch.TEXT_BYTES], 'by': 'x' * 48})
        pm.check(with_url('0.28'), PLACE_ENGLISH)
        self.refuses(with_url('0.27'), 'a field "as: url" needs plugin API 0.28')

    def test_places_for_pictures_in_a_popup(self):
        base = place_plugin(url='https://api.example.org/now', cards=[{'id': 'sky', 'name': 'card', 'pictures': 1}])
        out = pm.check({**base, 'popups': [{'id': 'photo', 'pictures': 2}]}, PLACE_ENGLISH)
        self.assertEqual(out['popups'], [{'id': 'photo', 'pictures': 2}])
        self.assertEqual(pm.check(base, PLACE_ENGLISH)['popups'], [])
        for popups, word in (([{'id': 'sky', 'pictures': 1}], 'a card too'), ([{'id': 'photo', 'pictures': 9}], 'between 1 and 8'),
                             ([{'id': 'photo', 'pictures': 0}], 'between 1 and 8'), ([{'id': 'photo'}], '"pictures" is required'),
                             ([{'id': 'photo', 'pictures': 1}] * 2, 'used twice'),
                             ([{'id': f'p{i}', 'pictures': 1} for i in range(9)], 'at most 8'),
                             ([{'id': 'photo', 'pictures': 1, 'wide': True}], 'unknown field')):
            with self.subTest(word=word):
                self.refuses({**base, 'popups': popups}, word)
        self.refuses({**base, 'api': '0.26', 'popups': [{'id': 'photo', 'pictures': 1}]}, 'needs plugin API 0.27')

    def test_what_a_fetch_sends_is_part_of_the_yes(self):
        plain = pm.check(place_plugin(url='https://api.example.org/now'), PLACE_ENGLISH)
        reading = pm.check(place_plugin(), PLACE_ENGLISH)
        # A plugin that sends nothing of Home Assistant keeps the fingerprint it had before 0.27.
        import hashlib
        before = {'permissions': {'read_entities': [], 'home_assistant_actions': [], 'network': ['api.example.org']},
                  'attributes': ['cloud']}
        self.assertEqual(pm.permission_hash(plain), hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()[:16])
        self.assertNotEqual(pm.permission_hash(reading), pm.permission_hash(plain))
        # Another attribute asks again; another name of the fetch, or other decimals, do not.
        more = pm.check(place_plugin(url=PLACE_URL + '&s={place.state}'), PLACE_ENGLISH)
        self.assertNotEqual(pm.permission_hash(more), pm.permission_hash(reading))
        renamed = place_plugin(url=PLACE_URL.replace(':2}', ':3}'))
        renamed['fetch'][0]['id'] = 'weather_now'
        renamed['tiles'][0]['data'] = 'weather_now'
        self.assertEqual(pm.permission_hash(pm.check(renamed, PLACE_ENGLISH)), pm.permission_hash(reading))


class FetchFill(unittest.TestCase):
    """Plugin API 0.27: an entity's attribute filled into a fetch, rounded, and a tile's line of asking."""

    def setUp(self):
        self.fetch = pm.check(place_plugin(), PLACE_ENGLISH)['fetch'][0]

    def test_rounded_and_encoded(self):
        url, _ = plugin_fetch.fill(self.fetch, {'place.latitude': 52.3676, 'place.longitude': '4,9041'}, {})
        self.assertEqual(url, 'https://api.example.org/forecast?lat=52.37&lon=4.90')
        data = place_plugin(url='https://api.example.org/x?q={place.state}&n={place.latitude:0}')
        data['fetch'][0]['headers'] = {'X-Where': '{place.state}'}
        fetch = pm.check(data, PLACE_ENGLISH)['fetch'][0]
        url, headers = plugin_fetch.fill(fetch, {'place.state': 'not home/away', 'place.latitude': 52.6}, {})
        self.assertEqual(url, 'https://api.example.org/x?q=not%20home%2Faway&n=53')
        self.assertEqual(headers, {'X-Where': 'not home/away'})
        # A value filled in is never a placeholder itself.
        url, headers = plugin_fetch.fill(fetch, {'place.state': '{place.latitude:0}', 'place.latitude': 1}, {})
        self.assertEqual(headers['X-Where'], '{place.latitude:0}')

    def test_missing_or_no_number_waits_as_not_filled(self):
        for values, word in (({}, 'place.latitude'), ({'place.latitude': 52.1}, 'place.longitude'),
                             ({'place.latitude': 'north', 'place.longitude': 4.9}, 'place.latitude (no number)'),
                             ({'place.latitude': float('nan'), 'place.longitude': 4.9}, 'no number'),
                             ({'place.latitude': True, 'place.longitude': 4.9}, 'no number'),
                             ({'place.latitude': [52], 'place.longitude': 4.9}, 'place.latitude')):
            with self.subTest(values=values), self.assertRaises(plugin_fetch.FetchRefused) as caught:
                plugin_fetch.fill(self.fetch, values, {})
            self.assertIn('not filled in', str(caught.exception))
            self.assertIn(word, str(caught.exception))

    def test_the_cache_keeps_a_bounded_number_of_questions(self):
        # A fetch the screen asks makes a question per value; past MAX_QUESTIONS the one asked longest ago makes way,
        # never the one a tile's line still follows.
        clock = [1000.0]
        fetcher = plugin_fetch.Fetcher(clock=lambda: clock[0])

        async def download(url, headers, network):
            return {'current': {'temperature': 1}}
        fetcher.download = download
        manifest = pm.check(place_plugin(), PLACE_ENGLISH)
        at = lambda n: {'place.latitude': n % 80, 'place.longitude': n // 80}   # whole degrees: each its own question

        async def run():
            followed, _ = await fetcher.get('weather', manifest, self.fetch, at(0), {}, line='L')
            first, _ = await fetcher.get('weather', manifest, self.fetch, at(1), {})
            for n in range(2, plugin_fetch.MAX_QUESTIONS + 20):
                clock[0] += 1
                await fetcher.get('weather', manifest, self.fetch, at(n), {})
            self.assertEqual(len(fetcher.cache), plugin_fetch.MAX_QUESTIONS)
            self.assertIn(followed, fetcher.cache)
            self.assertNotIn(first, fetcher.cache)
            self.assertEqual(set(fetcher.locks) - set(fetcher.cache), set())
        asyncio.run(run())

    def test_a_busy_service_is_left_alone_as_a_whole(self):
        # HTTP 429 or 503 is the host's word, not one question's: every other question of that host waits with it, for
        # as long as its Retry-After says, and none of them reaches the service meanwhile.
        clock, asked = [1000.0], []
        fetcher = plugin_fetch.Fetcher(clock=lambda: clock[0])

        async def download(url, headers, network):
            asked.append(url)
            if len(asked) == 1:
                raise plugin_fetch.ServiceBusy(429, plugin_fetch.busy_wait('300'))
            return {'current': {'temperature': 1}}
        fetcher.download = download
        manifest = pm.check(place_plugin(), PLACE_ENGLISH)
        at = lambda n: {'place.latitude': n, 'place.longitude': 4}

        async def run():
            _, first = await fetcher.get('weather', manifest, self.fetch, at(1), {})
            self.assertEqual((len(asked), first['data']), (1, None))
            for n in range(2, 8):
                _, other = await fetcher.get('weather', manifest, self.fetch, at(n), {})
                self.assertIsNone(other['data'])
            self.assertEqual(len(asked), 1, 'six more questions, none of them asked of the busy service')
            clock[0] += 301
            _, again = await fetcher.get('weather', manifest, self.fetch, at(2), {})
            self.assertEqual((len(asked), again['data']), (2, {'current': {'temperature': 1}}))
            fetcher.forget_unused()
            self.assertEqual(fetcher.busy, {})
        asyncio.run(run())
        self.assertEqual([plugin_fetch.busy_wait(v) for v in ('5', '300', '99999', None, 'Wed, 21 Oct 2026 07:28:00 GMT', 'nan')],
                         [60, 300, 3600, 60, 60, 60])

    def test_a_line_asks_a_moving_place_at_most_every_interval(self):
        clock, asked = [1000.0], []
        fetcher = plugin_fetch.Fetcher(clock=lambda: clock[0])

        async def download(url, headers, network):
            asked.append(url)
            return {'current': {'temperature': len(asked)}}
        fetcher.download = download
        manifest = pm.check(place_plugin(), PLACE_ENGLISH)
        at = lambda lat: {'place.latitude': lat, 'place.longitude': 4.9}

        async def run():
            first, entry = await fetcher.get('weather', manifest, self.fetch, at(52.1), {}, line='L')
            self.assertEqual(len(asked), 1)
            clock[0] += 60
            # The place moved: the line keeps its answer until ten minutes after it last asked.
            key, held = await fetcher.get('weather', manifest, self.fetch, at(52.2), {}, line='L')
            self.assertEqual((key, len(asked)), (first, 1))
            self.assertIs(fetcher.peek('weather', self.fetch, at(52.2), {}, line='L'), held)
            clock[0] += 60
            key, _ = await fetcher.get('weather', manifest, self.fetch, at(52.3), {}, line='L')
            self.assertEqual((key, len(asked)), (first, 1))
            # Another tile without a line asks the new place at once; the line takes that answer from the cache.
            other, _ = await fetcher.get('weather', manifest, self.fetch, at(52.3), {})
            self.assertEqual(len(asked), 2)
            key, entry = await fetcher.get('weather', manifest, self.fetch, at(52.3), {}, line='L')
            self.assertEqual((key, len(asked), entry['data']['current']['temperature']), (other, 2, 2))
            clock[0] += 60
            key, _ = await fetcher.get('weather', manifest, self.fetch, at(52.4), {}, line='L')
            self.assertEqual(len(asked), 2, 'taking over a cached answer is not the line asking')
            # Once ten minutes have passed since the line asked, its new question is asked.
            clock[0] = 1000.0 + 600
            key, entry = await fetcher.get('weather', manifest, self.fetch, at(52.4), {}, line='L')
            self.assertEqual((len(asked), asked[-1]), (3, 'https://api.example.org/forecast?lat=52.40&lon=4.90'))
            self.assertEqual(entry['data']['current']['temperature'], 3)
            # A line nobody follows is forgotten with its questions.
            clock[0] += 10_000
            fetcher.forget_unused()
            self.assertEqual((fetcher.lines, fetcher.cache), ({}, {}))
        asyncio.run(run())


def place_service(tmp, states, manifest_data=None, english=PLACE_ENGLISH):
    """A Plugins with the place plugin in a test folder on the screen `hall`, Home Assistant's states `states`, and a
    fetcher whose service answers with how many times it was asked."""
    import plugins as plugin_service
    import yaml
    config = Path(tmp) / 'esphome'
    config.mkdir()
    folder = Path(tmp) / 'tessera-plugins' / 'weather'
    (folder / 'translations').mkdir(parents=True)
    (folder / 'tessera-plugin.yaml').write_text(yaml.safe_dump(manifest_data or place_plugin(fetch=[DETAIL])))
    (folder / 'translations' / 'en.json').write_text(json.dumps(english))
    sent, asked = [], []

    class FakeManager:
        ha = type('HA', (), {'states': states, 'time_zone': 'UTC', 'changed': asyncio.Event(), 'dirty': set()})()
        page_senders, aliases, layouts = {}, {}, {}

        def screen(self, inbox):
            return {'id': inbox, 'node': inbox, 'name': 'Hall', 'board': 'guition', 'online': True}

        def transport(self, inbox, screen=None):
            return 'action'

        async def send_auxiliary(self, inbox, message, action, request):
            sent.append(message['m'])
    service = plugin_service.Plugins(FakeManager(), Path(tmp) / 'data', config)
    service.scan_folders()
    service.store.put('hall', {'id': 'weather', 'source': 'folder', 'state': 'active'})

    async def download(url, headers, network):
        asked.append(url)
        return {'current': {'temperature': len(asked), 'sky': 'clear'}, 'title': f'Row {len(asked)}', 'when': 1792389600}
    service.fetcher.download = download
    return service, sent, asked


class FetchOfThePlace(unittest.IsolatedAsyncioTestCase):
    """Plugin API 0.27, the app: a tile's fetch filled in from Home Assistant's state of the chosen entity, asked again
    within one loop turn when it moves but never more often than `every`, and what the editor says it sends."""

    async def asyncSetUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.states = {'zone.home': {'state': '1', 'attributes': {'latitude': 52.3676, 'longitude': 4.9041, 'friendly_name': 'Home'}},
                       'person.someone': {'state': 'not_home', 'attributes': {'latitude': 51.92, 'longitude': 4.48}},
                       'person.away': {'state': 'unavailable', 'attributes': {'latitude': 1, 'longitude': 2}}}
        self.service, self.sent, self.asked = place_service(tmp.name, self.states)
        self.tile = {'entity': 'plugin:weather.now', 'name': '', 'slot': 0, 'options': {'plugin': {}}}
        self.service.manager.layouts = {'hall': {'tiles': [self.tile]}}

    async def test_the_default_entity_fills_the_fetch_and_goes_with_the_tile(self):
        message = await self.service.tile_message(0, self.tile, inbox='hall')
        self.assertEqual(self.asked, ['https://api.example.org/forecast?lat=52.37&lon=4.90'])
        self.assertEqual(message['x']['temp'], 1)
        self.assertEqual(message['x']['entities']['place']['attributes'], {'latitude': 52.3676, 'longitude': 4.9041})
        self.assertEqual(message['o']['plugin'], {'place': 'zone.home'})

    async def test_no_entity_an_unavailable_one_or_a_missing_attribute_waits(self):
        for chosen in ({'place': ''}, {'place': 'person.away'}, {'place': 'person.gone'}):
            with self.subTest(chosen=chosen):
                message = await self.service.tile_message(0, {**self.tile, 'options': {'plugin': chosen}}, inbox='hall')
                self.assertEqual(message['x']['wait'], 'not_filled')
        self.assertEqual(self.asked, [])
        # A choice of another domain is no value of the option, as every value that does not fit: the default applies.
        message = await self.service.tile_message(0, {**self.tile, 'options': {'plugin': {'place': 'light.kitchen'}}}, inbox='hall')
        self.assertEqual((message['o']['plugin'], len(self.asked)), ({'place': 'zone.home'}, 1))
        self.asked.clear()
        self.service.fetcher.cache.clear()
        self.states['zone.home']['attributes'].pop('longitude')
        message = await self.service.tile_message(0, self.tile, inbox='hall')
        self.assertEqual(message['x']['wait'], 'not_filled')
        self.assertEqual(self.asked, [])

    async def test_a_place_that_moves_is_asked_in_the_next_turn_but_never_more_often_than_every(self):
        clock = [5000.0]
        self.service.fetcher.clock = lambda: clock[0]
        self.tile['options']['plugin'] = {'place': 'person.someone'}
        await self.service.refresh_data()
        self.assertEqual(len(self.asked), 1)
        self.assertIn('plugin:weather.now', self.service.manager.ha.dirty)
        self.service.manager.ha.dirty.clear()
        # The person moves, every turn of the loop: the service is not asked again before ten minutes have passed.
        for step in range(1, 40):
            clock[0] += 15
            self.states['person.someone']['attributes']['latitude'] = 51.92 + step / 100
            await self.service.refresh_data()
            await self.service.tile_message(0, self.tile, inbox='hall')
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(self.service.manager.ha.dirty, set())
        # The turn after ten minutes asks where the person is now, and sends the tile.
        clock[0] = 5000.0 + 600
        await self.service.refresh_data()
        self.assertEqual(self.asked[-1], 'https://api.example.org/forecast?lat=52.31&lon=4.48')
        self.assertEqual(len(self.asked), 2)
        self.assertIn('plugin:weather.now', self.service.manager.ha.dirty)
        message = await self.service.tile_message(0, self.tile, inbox='hall')
        self.assertEqual(message['x']['temp'], 2)
        # A person who chooses another entity is asked at once: a choice is no move.
        self.tile['options']['plugin'] = {'place': 'zone.home'}
        clock[0] += 15
        await self.service.refresh_data()
        self.assertEqual(len(self.asked), 3)

    async def test_the_editor_hears_what_it_sends(self):
        entry = self.service.listed()['weather']
        sends = self.service.editor_plugin(entry)['sends']
        self.assertEqual(sends, [{'host': 'api.example.org', 'options': [
            {'option': 'place', 'label': {'en': 'Place'}, 'attributes': ['latitude', 'longitude']}]}])
        # GET api/plugins lists editor_plugin of every plugin, and its fingerprint counts what it sends.
        self.assertEqual(self.service.editor_plugin(entry)['permission_hash'], pm.permission_hash(entry.manifest))
        self.assertEqual(self.service.sends_of(type('E', (), {'manifest': pm.check(place_plugin(url='https://api.example.org/now'),
                                                                                       PLACE_ENGLISH), 'texts': {}})()), [])


class FetchAsked(unittest.IsolatedAsyncioTestCase):
    """Plugin API 0.27: the screen asks one of its plugin's fetches with values of its own (tessera::send with
    `fetch:<id>`), shared and cached as every fetch, at most twenty a minute, every value checked."""

    async def asyncSetUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.service, self.sent, self.asked = place_service(tmp.name, {})
        self.re = 0

    async def ask(self, ask, data=None, plugin='weather'):
        self.re += 1
        body = {'re': self.re, 'ask': ask, **({'data': data} if data is not None else {})}
        await self.service.answer({'inbox': 'hall', 'plugin': plugin, 'body': json.dumps(body)})
        return self.sent[-1] if self.sent else None

    async def test_mapped_as_a_tile_would_get_it_and_cached(self):
        with self.assertLogs('plugins', 'INFO') as logged:
            reply = await self.ask('fetch:detail', {'row': 'KL 1234', 'day': 3})
        self.assertEqual(reply, {'re': 1, 'ok': True, 'result': {'title': 'Row 1', 'at': 1792389600}})
        self.assertEqual(self.asked, ['https://api.example.org/rows/KL%201234?day=3'])
        self.assertIn('asks its fetch: detail', logged.output[0])
        self.assertNotIn('KL', logged.output[0], 'the values stay out of the log')
        # The same question again: from the cache, the service is not asked.
        reply = await self.ask('fetch:detail', {'day': '3', 'row': 'KL 1234'})
        self.assertEqual((reply['ok'], reply['result']['title'], len(self.asked)), (True, 'Row 1', 1))
        # A tile's fetch is shared the same way: the screen's own row and a tile never ask twice for one URL.
        self.assertEqual(len(self.service.fetcher.cache), 1)

    async def test_every_value_is_checked(self):
        for data in ({'row': 'a/b', 'day': '1'}, {'row': 'x' * 65, 'day': '1'}, {'row': '', 'day': '1'}, {'row': 'a'},
                     {'row': 'a', 'day': '1', 'more': 'x'}, {'row': True, 'day': '1'}, {'row': ['a'], 'day': '1'},
                     {'row': 'a?b=c', 'day': '1'}, {'row': 'ä', 'day': '1'}, 'row=a', None):
            with self.subTest(data=data):
                reply = await self.ask('fetch:detail', data)
                self.assertEqual((reply['ok'], reply['error']), (False, 'refused'))
        reply = await self.ask('fetch:detail', {'row': 'A_b.c:d+e -f', 'day': 2.0})
        self.assertTrue(reply['ok'])
        self.assertEqual(self.asked, ['https://api.example.org/rows/A_b.c%3Ad%2Be%20-f?day=2'])

    async def test_only_a_fetch_with_asked_and_never_a_command_it_does_not_name(self):
        for ask in ('fetch:forecast', 'fetch:nowhere', 'fetch:'):
            with self.subTest(ask=ask):
                reply = await self.ask(ask, {'row': 'a', 'day': '1'})
                self.assertEqual((reply['ok'], reply['error']), (False, 'refused'))
        reply = await self.ask('get_states')
        self.assertEqual(reply, {'re': self.re, 'ok': False, 'error': 'not_allowed'})
        reply = await self.ask('call_service:weather.get_forecasts', {'entity_id': 'weather.home'})
        self.assertEqual(reply['error'], 'not_allowed')
        self.assertEqual(self.asked, [])
        # A plugin the screen does not run gets nothing at all.
        count = len(self.sent)
        await self.ask('fetch:detail', {'row': 'a', 'day': '1'}, plugin='other')
        self.assertEqual(len(self.sent), count)

    async def test_twenty_a_minute(self):
        clock = [100.0]
        import plugins as plugin_service
        original = plugin_service.time.monotonic
        plugin_service.time.monotonic = lambda: clock[0]
        self.addCleanup(setattr, plugin_service.time, 'monotonic', original)
        for i in range(plugin_service.FETCH_ASKS_PER_MINUTE):
            reply = await self.ask('fetch:detail', {'row': f'r{i % 2}', 'day': '1'})
            self.assertTrue(reply['ok'])
        reply = await self.ask('fetch:detail', {'row': 'r0', 'day': '1'})
        self.assertEqual((reply['ok'], reply['error']), (False, 'too_often'))
        self.assertEqual(len(self.asked), 2, 'twenty asks of two rows asked the service twice')
        clock[0] += 61
        self.assertTrue((await self.ask('fetch:detail', {'row': 'r0', 'day': '1'}))['ok'])

    async def test_a_failed_service_and_a_missing_secret(self):
        async def broken(url, headers, network):
            raise OSError('HTTP 503')
        self.service.fetcher.download = broken
        reply = await self.ask('fetch:detail', {'row': 'a', 'day': '1'})
        self.assertEqual((reply['ok'], reply['error']), (False, 'failed'))
        entry = self.service.listed()['weather']
        secret = {**pm.check(place_plugin(fetch=[{**DETAIL, 'url': 'https://api.example.org/rows/{row}?day={day}&key={key}'}],
                                          inputs=[{'id': 'key', 'kind': 'secret', 'label': 'label'}]), PLACE_ENGLISH)}
        entry.manifest = secret
        reply = await self.ask('fetch:detail', {'row': 'a', 'day': '1'})
        self.assertEqual((reply['ok'], reply['error']), (False, 'not_filled'))


class PopupPictures(unittest.TestCase):
    """Plugin API 0.27: a popup's places for pictures ask as a card's do (owner plugin_card), from a host of
    permissions.network only."""

    def test_a_popup_is_found_as_a_card_and_shows_no_home_assistant_picture(self):
        import types
        import server
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = place_plugin(url='https://api.example.org/now', cards=[{'id': 'sky', 'name': 'card', 'pictures': 1}],
                            popups=[{'id': 'photo', 'pictures': 2}])
        service, _, _ = place_service(tmp.name, {}, data)
        entry = service.listed()['weather']
        self.assertEqual(entry.card('photo'), {'id': 'photo', 'pictures': 2, 'popup': True})
        self.assertEqual(entry.card('sky')['pictures'], 1)
        self.assertNotIn('popup', entry.card('sky'))
        self.assertIsNone(entry.card('nowhere'))

        class Fake:
            plugin_place = server.Manager.plugin_place
            plugin_picture_refused = server.Manager.plugin_picture_refused

            def __init__(self):
                self.plugins = service
                self.layouts = {'hall': {'tiles': [{'entity': 'media_player.kitchen', 'options': {}}]}}
        fake = Fake()
        ask = lambda key, *texts: types.SimpleNamespace(owner=pq.Owner('plugin_card', key=key, of='media_player.kitchen'),
                                                        sources=[pq.source(text) for text in texts])
        network, home = 'https://api.example.org/p.jpg', '/api/image_proxy/media_player.kitchen'
        popup = ask('plugin:weather.photo', network, home)
        self.assertEqual(fake.plugin_place('hall', {}, popup)[2], False)
        self.assertIsNone(fake.plugin_picture_refused('hall', {}, popup, popup.sources[0]))
        self.assertIn('not an address', fake.plugin_picture_refused('hall', {}, popup, popup.sources[1]))
        self.assertIn('no entity', fake.plugin_picture_refused('hall', {}, popup, pq.source('cover:media_player.kitchen')))
        self.assertIn('allows 2', fake.plugin_picture_refused('hall', {}, ask('plugin:weather.photo', network, network, network),
                                                              pq.source(network)))
        self.assertIn('not an address', fake.plugin_picture_refused('hall', {}, popup, pq.source('https://elsewhere.example.org/p.jpg')))
        # A card shown for an entity of the layout keeps Home Assistant's pictures, as before.
        card = ask('plugin:weather.sky', home)
        self.assertEqual(fake.plugin_place('hall', {}, card)[2], True)
        self.assertIsNone(fake.plugin_picture_refused('hall', {}, card, card.sources[0]))


class SharedRoom(unittest.TestCase):
    """The parts of a tile's `x` share its room by one rule (plugins.shared, docs/PLUGINS.md): the smallest whole, the
    rest split alike among the larger."""

    @staticmethod
    def size(value):
        return len(json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode())

    def test_a_small_part_goes_whole_and_two_long_ones_each_give_way(self):
        import plugins as plugin_service
        place = {'state': '2', 'attributes': {'latitude': 52.37, 'longitude': 4.89}}
        sky = {'items': [{'hex': f'{n:06x}', 'flight': f'KLM{n:04d}', 'alt': 30000 + n} for n in range(200)]}
        prices = {'prices': [n / 7 for n in range(400)]}
        parts = plugin_service.shared(2000, [
            lambda budget: place if self.size(place) <= budget else {'wait': 'too_large'},
            lambda budget: plugin_service.fitted_data(sky, budget),
            lambda budget: plugin_service.fitted_data(prices, budget)])
        self.assertEqual(parts[0], place)
        self.assertTrue(0 < len(parts[1]['items']) < 200)
        self.assertTrue(0 < len(parts[2]['prices']) < 400)
        self.assertLessEqual(sum(self.size(part) for part in parts), 2000)
        # The two long ones got about as much each: neither starved the other.
        self.assertLess(abs(self.size(parts[1]) - self.size(parts[2])), 700)

    def test_whatever_the_sizes_the_parts_stay_within_the_room(self):
        import plugins as plugin_service
        for room in (0, 40, 300, 1200, 2600):
            for lengths in ((0,), (5, 5), (1, 400), (400, 1, 400), (300, 300, 300, 300)):
                shapers = [lambda budget, n=n: plugin_service.fitted_data({'numbers': list(range(n))}, budget) for n in lengths]
                parts = plugin_service.shared(room, shapers)
                used = sum(self.size(part) for part in parts)
                waits = sum(self.size(part) for part in parts if part == {'wait': 'too_large'})
                # A part that does not fit at all says so in its own place: that word is all that may pass the room.
                self.assertLessEqual(used - waits, max(room, 0), (room, lengths))

    def test_data_without_items_shortens_its_lists_and_with_items_loses_the_last(self):
        import plugins as plugin_service
        day = {'unit': 'ct', 'prices': list(range(500)), 'peaks': list(range(500))}
        got = plugin_service.fitted_data(day, 600)
        self.assertEqual((got['unit'], len(got['prices'])), ('ct', len(got['peaks'])))
        self.assertTrue(0 < len(got['prices']) < 500)
        sky = {'stale': True, 'items': [{'n': n} for n in range(100)]}
        got = plugin_service.fitted_data(sky, 300)
        self.assertEqual(got['items'], sky['items'][:len(got['items'])])
        self.assertLessEqual(self.size(got), 300)
        self.assertGreater(self.size({**got, 'items': sky['items'][:len(got['items']) + 1]}), 300)
        self.assertEqual(plugin_service.fitted_data({'name': 'x' * 400}, 100), {'wait': 'too_large'})


def plugin_service_budget():
    import plugins as plugin_service
    return plugin_service.X_BUDGET


class BlamedBuilds(unittest.TestCase):
    """A screen's update that stops on a plugin's code says which plugin, and its update when one is on offer."""

    def test_compiler_error_in_a_plugin_names_it(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), Path(tmp.name) / 'data',
                                         Path(tmp.name) / 'esphome')
        logs = ["../src/esphome/components/smart_display/page_bar.h:169:36: warning: '%d' directive output may be truncated",
                "../src/esphome/components/tap_sound/tap_sound.h:19:8: error: 'void esphome::tap_sound::TapSound::on_step()'"
                " marked 'override', but does not override",
                'ninja: build stopped: subcommand failed.', 'ESPHome compile failed; see the log.']
        self.assertEqual(plugin_service.failed_components(logs), {'tap_sound'})
        # The core refused the plugin by its API while ESPHome read the configuration (smart_display.register_plugin):
        # no compiler ran, and the plugin is to blame all the same.
        refused = ['INFO Reading configuration /config/esphome/tablet.yaml...',
                   'Failed config', 'tap_sound: [source /config/esphome/tablet.plugins.yaml:4]',
                   '  Plugin tap_sound wants plugin API 0.14; this firmware offers 0.13. Update the plugin, or the screen\'s firmware.',
                   'ESPHome compile failed; see the log.']
        self.assertEqual(plugin_service.failed_components(refused), {'tap_sound'})
        self.assertEqual(plugin_service.failed_components(['Plugin tap_sound was written for plugin API 0.10; plugin API 0.11 changed a name it may use']), {'tap_sound'})
        self.assertEqual(plugin_service.failed_components(['Plugin smart_display wants plugin API 0.1']), set())
        self.assertIsNone(service.blame('tablet', logs))   # not a plugin of this screen
        service.store.put('tablet', {'id': 'tap_sound', 'version': '0.2.0', 'source': 'index', 'ref': 'a' * 40})
        self.assertEqual(service.blame('tablet', logs),
                         {'id': 'tap_sound', 'name': 'tap_sound', 'version': '0.2.0', 'update': None})
        service.index['tap_sound'] = type('Entry', (), {'version': '0.2.1', 'ref': 'b' * 40, 'text': lambda self, key: 'Tap sound'})()
        self.assertEqual(service.blame('tablet', logs), {'id': 'tap_sound', 'name': 'Tap sound', 'version': '0.2.0', 'update': '0.2.1'})
        # An error in Tessera's own code, or none at all, blames no plugin.
        self.assertIsNone(service.blame('tablet', [logs[0].replace('warning', 'error'), logs[-1]]))
        self.assertIsNone(service.blame('tablet', ['Succeeded: install']))


class Questions(unittest.IsolatedAsyncioTestCase):
    """A plugin asks Home Assistant something through the app: only what its manifest names, the answer bounded."""

    async def test_named_commands_only_and_bounded(self):
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / 'calendar_peek', Path(tmp.name) / 'tessera-plugins' / 'calendar_peek')
        asked, sent = [], []

        class FakeHA:
            states, changed, dirty = {}, asyncio.Event(), set()

            async def request(self, kind, **data):
                asked.append((kind, data))
                return {'response': {'calendar.waste': {'events': [{'summary': 'Paper ' * 20, 'start': '2026-10-09'}] * 100}}}

        class FakeManager:
            ha = FakeHA()
            page_senders, aliases = {}, {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'name': 'Kitchen', 'board': 'guition', 'online': True}

            def transport(self, inbox, screen=None):
                return 'action'

            async def send_auxiliary(self, inbox, message, action, request):
                sent.append(message)
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        service.scan_folders()
        service.store.put('kitchen', {'id': 'calendar_peek', 'source': 'folder', 'state': 'active'})
        body = {'re': 7, 'ask': 'call_service:calendar.get_events', 'data': {'entity_id': 'calendar.waste', 'duration': {'days': 28}}}
        await service.answer({'inbox': 'kitchen', 'plugin': 'calendar_peek', 'body': json.dumps(body)})
        self.assertEqual(asked[0][0], 'call_service')
        self.assertEqual(asked[0][1]['target'], {'entity_id': 'calendar.waste'})
        self.assertTrue(asked[0][1]['return_response'])
        reply = sent[0]['m']
        self.assertEqual((sent[0]['op'], sent[0]['p'], reply['re'], reply['ok']), ('plugin', 'calendar_peek', 7, True))
        self.assertLessEqual(len(json.dumps(reply)), 3400)
        await service.answer({'inbox': 'kitchen', 'plugin': 'calendar_peek', 'body': json.dumps({'re': 8, 'ask': 'get_states'})})
        self.assertEqual(sent[1]['m'], {'re': 8, 'ok': False, 'error': 'not_allowed'})
        self.assertEqual(len(asked), 1)
        # A plugin the screen does not run gets nothing at all.
        await service.answer({'inbox': 'kitchen', 'plugin': 'other', 'body': json.dumps(body)})
        self.assertEqual(len(sent), 2)

    def test_a_folder_someone_was_making_is_set_aside_not_deleted(self):
        # The Plugins page's Remove for a folder plugin: refused while a screen runs it from the folder, then the folder
        # moves to tessera-plugins/.removed/ (a second one beside it gets -2), and the page no longer lists it.
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        fixture = ROOT / 'tests' / 'fixtures' / 'plugins' / 'calendar_peek'
        folders = Path(tmp.name) / 'tessera-plugins'
        shutil.copytree(fixture, folders / 'calendar_peek')
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), Path(tmp.name) / 'data', config)
        service.scan_folders()
        self.assertIn('calendar_peek', service.listed())
        service.store.put('kitchen', {'id': 'calendar_peek', 'source': 'folder', 'state': 'active'})
        with self.assertRaises(ValueError):
            service.forget_folder('calendar_peek')      # a screen still builds it from the folder
        self.assertTrue((folders / 'calendar_peek').is_dir())
        service.store.remove('kitchen', 'calendar_peek')
        service.store.put('hall', {'id': 'calendar_peek', 'source': 'index', 'ref': 'abc'})   # another origin is no reason
        moved = service.forget_folder('calendar_peek')
        self.assertEqual(moved, folders / '.removed' / 'calendar_peek')
        self.assertTrue((moved / 'tessera-plugin.yaml').is_file())
        self.assertFalse((folders / 'calendar_peek').exists())
        self.assertNotIn('calendar_peek', service.folders)
        self.assertEqual(service.folder_errors, {})
        shutil.copytree(fixture, folders / 'calendar_peek')
        self.assertEqual(service.forget_folder('calendar_peek'), folders / '.removed' / 'calendar_peek-2')
        with self.assertRaises(ValueError):
            service.forget_folder('calendar_peek')      # already gone

    async def test_settings_of_the_screens_own_entities_only(self):
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / 'calendar_peek', Path(tmp.name) / 'tessera-plugins' / 'calendar_peek')
        calls = []

        class FakeHA:
            changed, dirty = asyncio.Event(), set()
            registry = [{'entity_id': 'switch.kitchen_peek_in_bar', 'device_id': 'dev1'},
                        {'entity_id': 'number.kitchen_peek_days', 'device_id': 'dev1'},
                        {'entity_id': 'switch.hall_peek_in_bar', 'device_id': 'dev2'}]
            states = {'switch.kitchen_peek_in_bar': {'state': 'on'},
                      'number.kitchen_peek_days': {'state': '2.0', 'attributes': {'min': 0, 'max': 3, 'step': 1}}}

            async def call_service(self, domain, service, data):
                calls.append((domain, service, data))

        class FakeManager:
            ha = FakeHA()
            page_senders, aliases = {}, {}

            def screen(self, inbox):
                return {'id': inbox, 'device_id': 'dev1', 'online': True}
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        service.scan_folders()
        service.store.put('kitchen', {'id': 'calendar_peek', 'source': 'folder', 'state': 'active'})
        groups = service.settings_for('kitchen')
        rows = groups[0]['rows']
        self.assertEqual([(r['entity'], r['kind'], r['value']) for r in rows],
                         [('switch.kitchen_peek_in_bar', 'switch', True), ('number.kitchen_peek_days', 'number', 2.0)])
        await service.set_setting('kitchen', 'number.kitchen_peek_days', 3)
        self.assertEqual(calls, [('number', 'set_value', {'entity_id': 'number.kitchen_peek_days', 'value': 3})])
        for entity, value in (('switch.hall_peek_in_bar', True), ('light.kitchen', True), ('switch.kitchen_peek_in_bar', 'yes')):
            with self.subTest(entity), self.assertRaises(ValueError):
                await service.set_setting('kitchen', entity, value)

    def test_the_manifest_refuses_commands_that_reach_home_assistant_itself(self):
        for wrong in ('call_service', 'config/entity_registry/update', 'auth/sign_path', 'fire_event', 'supervisor/api'):
            with self.subTest(wrong), self.assertRaises(pm.ManifestError):
                pm.check(manifest(permissions={'network': ['api.example.org'], 'ha_commands': [wrong]}), ENGLISH)
        pm.check(manifest(permissions={'network': ['api.example.org'], 'ha_commands': ['history/history_during_period']}), ENGLISH)


class Hello(unittest.TestCase):
    def test_plugins_of_a_hello(self):
        self.assertEqual(plugins_of({}), (None, []))
        api, plugins = plugins_of({'plugin_api': '0.1', 'plugins': [
            {'id': 'bus', 'version': '1.0.0', 'tiles': ['next', 'Bad!']}, {'id': 'Nope'}, 'junk']})
        self.assertEqual(api, '0.1')
        self.assertEqual(plugins, [{'id': 'bus', 'version': '1.0.0', 'tiles': ['next'], 'savers': []}])


class Sidecar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / 'esphome'
        root.mkdir()
        (root / 'kitchen.yaml').write_text('esphome:\n  name: kitchen\npackages:\n  display:\n    url: x\n'
                                           '  local_overrides: !include kitchen.local.yaml\napi:\n')
        self.firmware = Firmware(root, Path(self.tmp.name) / 'data')

    def tearDown(self):
        self.tmp.cleanup()

    def test_written_then_attached_once_and_hidden(self):
        content = '# Written by Tessera.\npackages:\n  plugin_bus: !include ../tessera-plugins/bus/plugin.yaml\n'
        self.firmware.save_plugins('kitchen.yaml', content)
        self.firmware.save_plugins('kitchen.yaml', content)
        text = (self.firmware.root / 'kitchen.yaml').read_text()
        self.assertEqual(text.count('tessera_plugins: !include kitchen.plugins.yaml'), 1)
        self.assertLess(text.index('tessera_plugins'), text.index('api:'))
        self.assertEqual([p['file'] for p in self.firmware.profiles()], ['kitchen.yaml'])
        self.assertTrue(self.firmware.plugins_file('kitchen.yaml')['attached'])

    def test_only_packages_and_components(self):
        with self.assertRaises(ValueError):
            self.firmware.save_plugins('kitchen.yaml', 'wifi:\n  ssid: x\n')
        self.assertFalse((self.firmware.root / 'kitchen.plugins.yaml').exists())


class Queue(unittest.IsolatedAsyncioTestCase):
    """Ticking several screens builds them one after the other, never two at once and never a refusal."""

    async def test_screens_build_one_after_the_other(self):
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / 'clock_words', Path(tmp.name) / 'tessera-plugins' / 'clock_words')
        started, running = [], []

        class FakeFirmware:
            task = None
            job = None

            def save_plugins(self, profile, text):
                (config / profile.replace('.yaml', '.plugins.yaml')).write_text(text)

            def start(self, data):
                assert not (self.task and not self.task.done()), 'two builds at once'
                started.append(data['file'])

                async def build():
                    running.append(data['file'])
                    await asyncio.sleep(0.01)
                    self.job = {'state': 'success'}
                self.task = asyncio.get_running_loop().create_task(build())

        class FakeManager:
            firmware = FakeFirmware()

            def __init__(self):
                self.build_queue = BuildQueue(self)
            ha = type('HA', (), {'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'board': 'guition'}

            def notify(self):
                pass
        FakeManager.updates = type('U', (), {'resolve': lambda self, screen: (screen['id'] + '.yaml', '10.0.0.1')})()
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        for inbox in ('one', 'two', 'three'):
            result = await service.apply(inbox, {'add': [{'id': 'clock_words', 'source': 'folder'}]})
            self.assertTrue(result['built'])
        await service.manager.build_queue.idle()
        self.assertEqual(started, ['one.yaml', 'two.yaml', 'three.yaml'])
        self.assertEqual({i: service.store.get(i, 'clock_words')['state'] for i in ('one', 'two', 'three')},
                         {'one': 'active', 'two': 'active', 'three': 'active'})
        self.assertIn('../tessera-plugins/clock_words/plugin.yaml', (config / 'one.plugins.yaml').read_text())

    async def test_every_update_of_a_screen_in_one_build_keeps_what_was_filled_in(self):
        """Update all on this screen: two plugins in one request build the screen once, and an update that sends no
        values keeps the ones given when the plugin was added (a calendar, an optional part)."""
        import shutil
        import yaml
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        folders = Path(tmp.name) / 'tessera-plugins'
        shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / 'clock_words', folders / 'clock_words')
        shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / 'clock_words', folders / 'city_words')
        manifest = yaml.safe_load((folders / 'city_words' / 'tessera-plugin.yaml').read_text())
        manifest.update(id='city_words', inputs=[{'id': 'city', 'kind': 'text', 'label': 'tile'}],
                        parts=[{'id': 'extra', 'file': 'extra.yaml', 'label': 'tile', 'flash_kb': 4}])
        (folders / 'city_words' / 'tessera-plugin.yaml').write_text(yaml.safe_dump(manifest))
        started = []

        class FakeFirmware:
            task = None
            job = None

            def save_plugins(self, profile, text):
                (config / profile.replace('.yaml', '.plugins.yaml')).write_text(text)

            async def clean_build(self, name):
                started.append(('clean', name))

            def start(self, data):
                started.append(data['file'])

                async def build():
                    self.job = {'state': 'success'}
                self.task = asyncio.get_running_loop().create_task(build())

        class FakeManager:
            firmware = FakeFirmware()

            def __init__(self):
                self.build_queue = BuildQueue(self)
            ha = type('HA', (), {'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'board': 'guition'}

            def notify(self):
                pass
        FakeManager.updates = type('U', (), {'resolve': lambda self, screen: (screen['id'] + '.yaml', '10.0.0.1')})()
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        await service.apply('hall', {'add': [{'id': 'city_words', 'source': 'folder', 'values': {'city': 'Utrecht'},
                                              'parts': ['extra']}]})
        await service.manager.build_queue.idle()
        started.clear()
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}, {'id': 'city_words', 'source': 'folder'}]})
        await service.manager.build_queue.idle()
        self.assertEqual(started, ['hall.yaml'])
        record = service.store.get('hall', 'city_words')
        self.assertEqual((record['values'], record['parts']), ({'city': 'Utrecht'}, ['extra']))
        text = (config / 'hall.plugins.yaml').read_text()
        self.assertIn('"CITY": "Utrecht"', text)
        self.assertIn('extra.yaml', text)
        self.assertIn('clock_words/plugin.yaml', text)
        # Only a change of a plugin's parts starts the build from an empty build folder (BuildQueue, Build.fresh): above,
        # adding and updating kept the folder.
        started.clear()
        await service.apply('hall', {'add': [{'id': 'city_words', 'source': 'folder', 'parts': []}]})
        await service.manager.build_queue.idle()
        self.assertEqual(started, [('clean', 'hall.yaml'), 'hall.yaml'])
        self.assertNotIn('extra.yaml', (config / 'hall.plugins.yaml').read_text())


class BuildOutcome(unittest.IsolatedAsyncioTestCase):
    """What a build's end and a change during a build do to a screen's plugins (plugins.py apply, _build_queue,
    _settle_build): nothing asked is lost, and a failed build leaves a plugins file that builds."""

    def make(self, results=None, host='10.0.0.1', refuse=False):
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        folders = Path(tmp.name) / 'tessera-plugins'
        for name in ('clock_words', 'calendar_peek'):
            shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / name, folders / name)
        outcomes = list(results or [])
        started = []

        class FakeFirmware:
            task = None
            job = None
            gate = None
            logs = []

            def save_plugins(self, profile, text):
                if refuse:
                    raise ValueError('another include')
                (config / profile.replace('.yaml', '.plugins.yaml')).write_text(text)

            def start(self, data):
                assert not (self.task and not self.task.done()), 'two builds at once'
                started.append((config / 'hall.plugins.yaml').read_text())
                state = outcomes.pop(0) if outcomes else 'success'

                async def build():
                    if self.gate:
                        await self.gate.wait()
                    self.job = {'state': state}
                    self.logs = ['ESPHome: compile'] + ([] if state == 'success' else ['compile failed'])
                self.task = asyncio.get_running_loop().create_task(build())

        class FakeManager:
            firmware = FakeFirmware()

            def __init__(self):
                self.build_queue = BuildQueue(self)
            ha = type('HA', (), {'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'name': inbox.title(), 'board': 'guition'}

            def notify(self):
                pass
        FakeManager.updates = type('U', (), {'resolve': lambda self, screen: (screen['id'] + '.yaml', host)})()
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        return service, config, started

    async def test_a_change_while_the_screen_builds_gets_a_build_of_its_own(self):
        service, config, started = self.make()
        service.manager.firmware.gate = asyncio.Event()
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        while not service.manager.build_queue.running:
            await asyncio.sleep(0)
        await service.apply('hall', {'add': [{'id': 'calendar_peek', 'source': 'folder'}]})
        service.manager.firmware.gate.set()
        await service.manager.build_queue.idle()
        self.assertEqual(len(started), 2)
        self.assertIn('calendar_peek', started[1])
        self.assertEqual({p: service.store.get('hall', p)['state'] for p in ('clock_words', 'calendar_peek')},
                         {'clock_words': 'active', 'calendar_peek': 'active'})
        self.assertFalse(service.manager.build_queue.busy())

    async def test_a_plugin_asked_while_the_screen_s_update_waits_comes_with_that_update(self):
        """A plugin build and an update of one screen are one build (build_queue): the update builds the plugins file
        too, and its install settles the plugin."""
        service, config, started = self.make()
        line = service.manager.build_queue
        service.manager.firmware.gate = asyncio.Event()

        async def other(build):
            return 'success' if await line.step({'file': 'desk.yaml', 'action': 'install', 'target': '10.0.0.2'}) else 'failed'

        async def update(build):
            return 'success' if await line.step({'file': 'hall.yaml', 'action': 'install', 'target': '10.0.0.1'}) else 'failed'
        line.add('update', 'desk.yaml', other, screen='desk')
        waiting = line.add('update', 'hall.yaml', update, screen='hall')
        result = await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        self.assertEqual(result['queued'], 1)
        self.assertEqual((waiting.by, waiting.plugins['add']), ('update', ['clock_words']))
        self.assertEqual(service.store.get('hall', 'clock_words')['state'], 'building')
        service.manager.firmware.gate.set()
        await line.idle()
        self.assertEqual(len(started), 2, 'desk, then hall once')
        self.assertEqual(service.store.get('hall', 'clock_words')['state'], 'active')

    async def test_a_new_plugin_that_fails_leaves_the_file(self):
        service, config, _ = self.make(['failed'])
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        await service.manager.build_queue.idle()
        record = service.store.get('hall', 'clock_words')
        self.assertEqual((record['state'], record['reason']), ('failed', 'compile failed'))
        self.assertNotIn('clock_words', (config / 'hall.plugins.yaml').read_text())
        # Trying again puts it back in the file and builds.
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        await service.manager.build_queue.idle()
        self.assertEqual(service.store.get('hall', 'clock_words')['state'], 'active')
        self.assertNotIn('reason', service.store.get('hall', 'clock_words'))
        self.assertIn('clock_words', (config / 'hall.plugins.yaml').read_text())

    async def test_an_update_that_fails_goes_back_to_what_worked(self):
        service, config, _ = self.make(['success', 'failed'])
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder', 'parts': []}]})
        await service.manager.build_queue.idle()
        before = service.store.get('hall', 'clock_words')
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder', 'parts': ['missing']}]})
        self.assertEqual(service.store.get('hall', 'clock_words')['previous']['version'], before['version'])
        await service.manager.build_queue.idle()
        record = service.store.get('hall', 'clock_words')
        self.assertEqual(record['state'], 'active')
        self.assertEqual(record['failed_update']['reason'], 'compile failed')
        self.assertNotIn('previous', record)
        self.assertIn('clock_words', (config / 'hall.plugins.yaml').read_text())

    async def test_a_file_that_cannot_be_written_changes_nothing(self):
        service, config, started = self.make(refuse=True)
        with self.assertRaises(ValueError):
            await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        self.assertIsNone(service.store.get('hall', 'clock_words'))
        self.assertEqual(started, [])

    async def test_a_screen_without_an_address_is_not_changed(self):
        service, config, started = self.make(host=None)
        with self.assertRaises(ValueError) as caught:
            await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        self.assertIn('Hall', str(caught.exception))
        self.assertIsNone(service.store.get('hall', 'clock_words'))
        self.assertFalse((config / 'hall.plugins.yaml').exists())

    def test_a_failed_build_says_why_in_one_line(self):
        from plugins import build_reason
        self.assertEqual(build_reason(['INFO x', 'src/a.cpp:3:1: error: foo', 'ninja: build stopped: subcommand failed.',
                                       'ESPHome compile failed; see the log.']), 'src/a.cpp:3:1: error: foo')
        self.assertEqual(build_reason(['ninja failed with exit code 1', 'The compiler ran out of memory: more is needed.']),
                         'The compiler ran out of memory: more is needed.')
        self.assertEqual(build_reason(None), 'build')

    def test_a_screen_that_goes_forgets_its_own_secrets(self):
        from plugin_store import PluginSecrets
        secrets = PluginSecrets(Path(tempfile.mkdtemp()) / 'secrets.json')
        secrets.set('bus', 'key', 'one', 'hall')
        secrets.set('bus', 'key', 'all', 'all')
        secrets.drop_scope('bus', 'hall')
        self.assertEqual(secrets.of('bus', 'hall'), {'key': 'all'})

    def test_a_secret_kept_before_origins_is_handed_out_after_the_update(self):
        # The files of app 0.4.86: a plugin added with a link, and its key with no origin. A plugin of the same id from
        # another repository still gets nothing, and a key whose plugin is on no screen stays without an origin.
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name) / 'data'
        data.mkdir()
        (data / 'plugins.json').write_text(json.dumps({'version': 1, 'screens': {'hall': {'plugins': [
            {'id': 'bus', 'source': 'link', 'repo': 'https://github.com/Maker/Bus-Plugin.git', 'path': '.', 'ref': 'v1.0.0',
             'version': '1.0.0', 'state': 'active'}]}}}))
        (data / 'plugin_secrets.json').write_text(json.dumps({'version': 1, 'values': {
            'bus/key/all': 'abc', 'bus/token/hall': 'def', 'gone/key/all': 'ghi'}}))
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), data, Path(tmp.name) / 'esphome')
        origin = plugin_service.origin_of('https://github.com/maker/bus-plugin')
        self.assertEqual(service.secrets.of('bus', 'hall', origin), {'key': 'abc', 'token': 'def'})
        self.assertTrue(service.secrets.has('bus', 'key', origin=origin))
        self.assertEqual(service.secrets.of('bus', 'hall', plugin_service.origin_of('https://github.com/fork/bus')), {})
        kept = json.loads((data / 'plugin_secrets.json').read_text())
        self.assertEqual(kept['origins'], {'bus/key/all': origin, 'bus/token/hall': origin})


class Suggested(unittest.IsolatedAsyncioTestCase):
    """Plugins the app suggests for a board (plugin_defaults.py): a rule names the hardware and the plugin, a person
    answers once, on New screen's Plugins step or on the card above a screen, and the app never adds one unasked."""

    RULE = ({'plugin': 'clock_words', 'feature': 'feat', 'since': (0, 0, 1), 'why': 'camera'},)

    def ready(self, available=False, **make):
        from unittest import mock
        import core
        import plugin_defaults
        self.mock, self.core = mock, core
        service, config, started = BuildOutcome.make(self, **make)
        service.scan_folders()
        service.index['clock_words'] = service.folders['clock_words']
        service.ready = True
        board = dict(core.SHAPES.get('guition') or {}, features=['feat'])
        self.update = {'profile': 'hall.yaml', 'host': '10.0.0.1', 'available': available, 'state': 'idle'}
        service.manager.updates.state_for = lambda screen: self.update
        service.manager.firmware.profile_names = lambda: {'hall.yaml': {'node': 'hall'}}
        for patch in (mock.patch.dict(core.SHAPES, {'guition': board}), mock.patch.object(plugin_defaults, 'RULES', self.RULE),
                      mock.patch.object(core, 'plugins_enabled', lambda: True),
                      mock.patch.object(service, '_entry_asked', lambda item: service.index[item['id']])):
            patch.start()
            self.addCleanup(patch.stop)
        return service, config, started

    def card(self, service):
        return service.suggest_card(service.screen_of('hall'))

    async def test_a_board_with_the_hardware_gets_the_card_and_another_board_does_not(self):
        service, _, started = self.ready()
        card = self.card(service)
        self.assertEqual([(p['id'], p['why']) for p in card['plugins']], [('clock_words', 'camera')])
        self.assertEqual(started, [], 'a suggestion builds nothing')
        self.assertIsNone(service.store.get('hall', 'clock_words'))
        with self.mock.patch.dict(self.core.SHAPES, {'guition': dict(self.core.SHAPES['guition'], features=[])}):
            self.assertIsNone(self.card(service))

    async def test_no_is_kept_and_the_card_never_comes_back(self):
        service, _, started = self.ready()
        self.assertEqual(await service.answer_suggestion('hall', 'clock_words', False), {'declined': True})
        self.assertIsNone(self.card(service))
        self.assertEqual((started, service.store.declined('hall')), ([], ['clock_words']))
        with self.assertRaises(ValueError):
            await service.answer_suggestion('hall', 'clock_words', True)

    async def test_yes_builds_it_now_when_no_update_waits(self):
        service, _, started = self.ready()
        await service.answer_suggestion('hall', 'clock_words', True)
        await service.manager.build_queue.idle()
        record = service.store.get('hall', 'clock_words')
        self.assertEqual((len(started), record['state'], record.get('suggested')), (1, 'active', True))
        self.assertIsNone(self.card(service))

    async def test_yes_waits_for_the_update_that_is_due_and_comes_with_it(self):
        service, config, started = self.ready(available=True)
        self.assertEqual(await service.answer_suggestion('hall', 'clock_words', True), {'with_update': True})
        self.assertEqual((started, self.card(service)), ([], None), 'no build of its own, and asked only once')
        self.assertEqual(await service.join_accepted('hall'), ['clock_words'])
        self.assertIn('clock_words', (config / 'hall.plugins.yaml').read_text())
        self.assertEqual(service.store.get('hall', 'clock_words')['state'], 'building')
        service.settle_joined('hall', ['clock_words'], True)
        self.assertEqual((service.store.get('hall', 'clock_words')['state'], service.store.accepted('hall')), ('active', []))

    async def test_an_update_brings_nothing_nobody_said_yes_to(self):
        service, _, _ = self.ready(available=True)
        self.assertEqual(await service.join_accepted('hall'), [])
        self.assertIsNone(service.store.get('hall', 'clock_words'))

    async def test_an_update_that_stops_on_it_goes_on_without_it(self):
        service, config, _ = self.ready(available=True)
        await service.answer_suggestion('hall', 'clock_words', True)
        await service.join_accepted('hall')
        service.settle_joined('hall', ['clock_words'], False, logs=['compile failed'])
        self.assertEqual(service.store.get('hall', 'clock_words')['state'], 'failed')
        self.assertNotIn('clock_words', (config / 'hall.plugins.yaml').read_text())
        self.assertIsNone(self.card(service), 'listed as failed on the Plugins page, not suggested again')

    async def test_a_plugin_a_person_took_off_is_not_suggested_again(self):
        service, _, _ = self.ready()
        await service.answer_suggestion('hall', 'clock_words', True)
        await service.manager.build_queue.idle()
        await service.apply('hall', {'remove': ['clock_words']})
        await service.manager.build_queue.idle()
        self.assertIsNone(self.card(service))
        # Added again on the Plugins page: theirs, and the answer is spent.
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'index'}]})
        await service.manager.build_queue.idle()
        self.assertEqual(service.store.declined('hall'), [])
        self.assertNotIn('suggested', service.store.get('hall', 'clock_words'))

    async def test_new_screen_builds_what_stayed_ticked_and_keeps_what_was_unticked(self):
        service, config, started = self.ready()
        self.assertEqual([p['id'] for p in service.suggest_for_board('guition')], ['clock_words'])
        paired = []
        service.manager.screens = lambda: paired
        # Ticked: in the plugins file before the first build, and the screen's own once Home Assistant has it.
        self.assertEqual(service.start_with('hall.yaml', 'hall', 'guition', {'add': ['clock_words', 'calendar_peek']}), ['clock_words'])
        self.assertIn('clock_words', (config / 'hall.plugins.yaml').read_text())
        self.assertNotIn('calendar_peek', (config / 'hall.plugins.yaml').read_text(), 'only what the board suggests')
        service.adopt_started()
        self.assertIsNone(service.store.get('hall', 'clock_words'), 'not before the screen is paired')
        paired.append(dict(service.manager.screen('hall')))
        service.adopt_started()
        record = service.store.get('hall', 'clock_words')
        self.assertEqual((record['state'], record['suggested'], service.store.starting), ('active', True, {}))
        self.assertEqual(started, [], 'the first build is New screen\'s own')

    async def test_new_screen_unticked_is_never_suggested_for_that_screen(self):
        service, config, _ = self.ready()
        service.manager.screens = lambda: [dict(service.manager.screen('hall'))]
        self.assertEqual(service.start_with('hall.yaml', 'hall', 'guition', {'add': [], 'declined': ['clock_words']}), [])
        self.assertFalse((config / 'hall.plugins.yaml').exists())
        service.adopt_started()
        self.assertEqual(service.store.declined('hall'), ['clock_words'])
        self.assertIsNone(self.card(service))

    async def test_a_profile_removed_before_its_screen_came_leaves_nothing(self):
        service, _, _ = self.ready()
        service.manager.screens = lambda: []
        service.start_with('hall.yaml', 'hall', 'guition', {'add': ['clock_words']})
        service.manager.firmware.profile_names = lambda: {}
        service.adopt_started()
        self.assertEqual(service.store.starting, {})

    def test_every_rule_names_a_feature_a_board_can_have_and_a_reason_with_words(self):
        import json
        import plugin_defaults
        import plugin_manifest
        words = json.loads((ROOT / 'screen_manager/translations/en.json').read_text())['editor']['plugins']['suggest']['why']
        for rule in plugin_defaults.RULES:
            self.assertIn(rule['feature'], plugin_manifest.FEATURES, rule)
            self.assertIn(rule['why'], words, rule)
            self.assertRegex(rule['plugin'], r'^[a-z][a-z0-9_]+$')


class Builds(unittest.IsolatedAsyncioTestCase):
    """Manager.builds: one record per screen for whatever is being built for it, whoever asked (the build line,
    build_queue), so the editor tracks every build in one place."""

    def manager(self):
        manager = type('M', (), {})()
        manager.updates = type('U', (), {'resolve': lambda self, screen, profiles=None: (screen['id'] + '.yaml', '10.0.0.1')})()
        manager.firmware = type('F', (), {'job': None, 'logs': [], 'profile_names': lambda self: [],
                                          'check': lambda self, data: None})()
        manager.build_queue = BuildQueue(manager)
        self.gate = asyncio.Event()
        self.addAsyncCleanup(self.finish, manager)
        return manager

    async def finish(self, manager):
        for build in list(manager.build_queue.line):
            manager.build_queue.drop(build)
        self.gate.set()
        await manager.build_queue.idle()

    async def held(self, build):
        await self.gate.wait()
        return 'success'

    def builds(self, manager):
        import server
        screens = [{'id': name} for name in ('hall', 'kitchen', 'desk')]
        return server.Manager.builds(manager, screens, [])

    async def test_nothing_on_the_way_is_no_record(self):
        self.assertEqual(self.builds(self.manager()), {})

    async def test_every_kind_of_build_once_per_screen(self):
        m = self.manager()
        line = m.build_queue
        hall = line.add('update', 'hall.yaml', self.held, screen='hall')
        hall.phase = 'install'
        kitchen = line.add('plugins', 'kitchen.yaml', self.held, screen='kitchen', plugins={'add': ['bus']})
        desk = line.add('update', 'desk.yaml', self.held, screen='desk')
        # A plugin asked for a screen whose update waits joins that update: one build, which brings the plugin too.
        self.assertIs(line.add('plugins', 'desk.yaml', self.held, screen='desk', plugins={'add': ['waste']}), desk)
        out = self.builds(m)
        self.assertEqual(out['hall'], {'id': hall.id, 'by': 'update', 'state': 'running', 'phase': 'install',
                                       'file': 'hall.yaml', 'stage': None})
        self.assertEqual(out['kitchen'], {'id': kitchen.id, 'by': 'plugins', 'state': 'queued', 'plugins': ['bus'],
                                          'file': 'kitchen.yaml', 'stage': None, 'place': 1})
        self.assertEqual(out['desk'], {'id': desk.id, 'by': 'update', 'state': 'queued', 'phase': None, 'plugins': ['waste'],
                                       'file': 'desk.yaml', 'stage': None, 'place': 2})

    async def test_an_install_from_firmware_and_usb_counts_and_a_check_does_not(self):
        m = self.manager()
        m.build_queue.add('update', 'hall.yaml', self.held, screen='hall')
        check = m.build_queue.attended({'file': 'kitchen.yaml', 'action': 'validate'})
        install = m.build_queue.attended({'file': 'desk.yaml', 'action': 'install', 'target': '10.0.0.9'})
        out = self.builds(m)
        self.assertNotIn('kitchen', out)
        self.assertEqual((check.by, install.by), ('check', 'install'))
        self.assertEqual(out['desk'], {'id': install.id, 'by': 'install', 'state': 'queued', 'file': 'desk.yaml',
                                       'stage': None, 'place': 2})


if __name__ == '__main__':
    unittest.main()


# ---- A day of prices or a forecast (plugin API 0.5) ----
# Real day-ahead prices (two days of 96 quarters) in the shapes the integrations give them, as their source builds
# them: an attribute list of numbers or of objects, or an action's answer, with every way of writing a moment seen.

PRICES = json.loads((ROOT / 'tests/fixtures/plugins/prices/nordpool_nl.json').read_text())


def moments(day, step=None, offset='+02:00', space=False, utc=False):
    """The start of every slot of a day of PRICES as Home Assistant writes it: ISO with an offset (a datetime the
    websocket serialises), str(datetime) with a space (energyzero, easyenergy, ENTSO-e), or UTC."""
    from datetime import datetime, timedelta, timezone
    start = datetime.fromisoformat(day['start'])
    zone = timezone.utc if utc else timezone(timedelta(hours=int(offset[:3]), minutes=int(offset[4:])))
    out = []
    for i in range(len(day['prices'])):
        moment = (start + timedelta(minutes=(step or day['minutes']) * i)).astimezone(zone)
        out.append(str(moment) if space else moment.isoformat())
    return out


def series_sources():
    """{source: (where, data, fields)}: where 'attributes' (the entity's) or 'answer' (an action's response), and the
    fields a plugin maps to get the day as one list of numbers plus its first moment."""
    today, tomorrow = PRICES['days'][1], PRICES['days'][0]
    kwh = [round(p / 1000, 3) for p in today['prices']]
    at = moments(today)
    half = lambda values: values[::2]          # 48 slots of half an hour
    price_fields = lambda path, first: {'prices': {'path': path, 'as': 'numbers'}, 'start': {'path': first, 'as': 'epoch'}}
    return {
        'nordpool (HACS), raw_today': ('attributes', {
            'today': kwh, 'tomorrow': [round(p / 1000, 3) for p in tomorrow['prices']], 'unit_of_measurement': 'EUR/kWh',
            'raw_today': [{'start': s, 'end': s, 'value': v} for s, v in zip(at, kwh)]},
            price_fields('raw_today[*].value', 'raw_today[0].start')),
        'entsoe (HACS)': ('attributes', {
            'prices_today': [{'time': s, 'price': round(p / 1000, 5)} for s, p in zip(moments(today, space=True), today['prices'])]},
            price_fields('prices_today[*].price', 'prices_today[0].time')),
        'frank_energie (HACS)': ('attributes', {'prices': [{'from': s, 'till': s, 'price': v} for s, v in zip(at, kwh)]},
            price_fields('prices[*].price', 'prices[0].from')),
        'zonneplan_one (HACS)': ('attributes', {'forecast': [
            {'start_date': s, 'end_date': s, 'price_tax_included': {'amount': int(v * 1e7)}, 'tariff_group': 'normal'}
            for s, v in zip(at, kwh)]}, price_fields('forecast[*].price_tax_included.amount', 'forecast[0].start_date')),
        'octopus_energy (HACS), event': ('attributes', {'rates': [
            {'start': s, 'end': s, 'value_inc_vat': v, 'is_capped': False} for s, v in zip(half(moments(today, offset='+01:00')), half(kwh))]},
            price_fields('rates[*].value_inc_vat', 'rates[0].start')),
        'solcast_solar (HACS)': ('attributes', {'detailedForecast': [
            {'period_start': s, 'pv_estimate': v * 10, 'pv_estimate10': v, 'pv_estimate90': v * 12} for s, v in zip(half(at), half(kwh))]},
            price_fields('detailedForecast[*].pv_estimate', 'detailedForecast[0].period_start')),
        'amberelectric': ('attributes', {'forecasts': [
            {'duration': 30, 'per_kwh': v, 'spot_per_kwh': v, 'start_time': s, 'end_time': s, 'descriptor': 'low'}
            for s, v in zip(half(moments(today, utc=True)), half(kwh))]},
            price_fields('forecasts[*].per_kwh', 'forecasts[0].start_time')),
        'nordpool, get_prices_for_date': ('answer', {'NL': [
            {'start': s, 'end': s, 'price': p} for s, p in zip(moments(today, utc=True), today['prices'])]},
            price_fields('[*][*].price', '[*][0].start')),
        'energyzero, get_energy_prices (quarter)': ('answer', {'prices': [
            {'price': v, 'timestamp': s, 'start': s, 'end': s} for s, v in zip(moments(today, space=True, utc=True), kwh)]},
            price_fields('prices[*].price', 'prices[0].start')),
        'easyenergy, get_energy_usage_prices (quarter)': ('answer', {'prices': [
            {'timestamp': s, 'price': v} for s, v in zip(moments(today, space=True, utc=True), kwh)]},
            price_fields('prices[*].price', 'prices[0].timestamp')),
        'tibber, get_prices': ('answer', {'prices': {'Home': [
            {'start_time': s.replace('+02:00', '.000+02:00'), 'price': v} for s, v in zip(at, kwh)]}},
            price_fields('prices[*][*].price', 'prices[*][0].start_time')),
        'weather, get_forecasts (hourly)': ('answer', {'weather.home': {'forecast': [
            {'datetime': s, 'condition': 'cloudy', 'temperature': 12 + v * 10, 'precipitation': 0.0} for s, v in zip(at[::4], kwh[::4])]}},
            price_fields('[*].forecast[*].temperature', '[*].forecast[0].datetime')),
    }


class Series(unittest.IsolatedAsyncioTestCase):
    """A day of prices or a forecast reaches a plugin whole, from every shape an integration gives it in."""

    def service(self, states, request=None):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class FakeHA:
            changed, dirty, time_zone, registry = asyncio.Event(), set(), 'Europe/Amsterdam', []

            async def request(self, kind, **data):
                return await request(kind, **data)
        FakeHA.states = states

        class FakeManager:
            ha = FakeHA()
            page_senders, aliases = {}, {}
        return plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')

    def test_every_source_gives_its_whole_day_as_numbers(self):
        from datetime import datetime
        first_slot = int(datetime.fromisoformat(PRICES['days'][1]['start']).timestamp())
        for source, (where, data, fields) in series_sources().items():
            with self.subTest(source):
                spec = pm.check_fields(fields, 'fields')
                got = {name: plugin_fetch.field_value(data, {**field, 'tz': 'Europe/Amsterdam'}) for name, field in spec.items()}
                slots = 24 if source.startswith('weather') else 48 if any(s in source for s in ('octopus', 'solcast', 'amber')) else 96
                self.assertEqual(len(got['prices']), slots)
                self.assertTrue(all(isinstance(p, (int, float)) for p in got['prices']))
                self.assertEqual(got['start'], first_slot)
                # The day as numbers fits a screen's message with room to spare, an answer and a tile alike.
                self.assertLess(len(json.dumps(got['prices'], separators=(',', ':'))), 1300)

    def test_a_tile_of_an_entity_gets_two_days_whole(self):
        _, attrs, _ = series_sources()['nordpool (HACS), raw_today']
        service = self.service({'sensor.price': {'state': '0.1', 'attributes': attrs}})
        kind = pm.check(yaml_manifest('price_peek'), None)['tiles'][0]
        _, part = service.entity_part(kind, {'options': {'plugin_entity': 'sensor.price'}})
        got = part['attributes']
        self.assertEqual((len(got['today']), len(got['tomorrow']), len(got['today_raw'])), (96, 96, 96))  # 16 before 0.5
        self.assertEqual(got['today_raw'], attrs['today'])
        self.assertEqual(got['unit_of_measurement'], 'EUR/kWh')
        self.assertIsInstance(got['starts_at'], int)
        self.assertNotIn('raw_today', got)            # 8 KB of objects never go to the screen
        self.assertLessEqual(len(json.dumps(part, separators=(',', ':'))), 2600)

    def test_lists_too_large_together_are_shortened_alike_from_the_end(self):
        effects = [f'Effect number {i}' for i in range(218)]
        service = self.service({'light.strip': {'state': 'on', 'attributes': {'effect_list': effects, 'options': list(range(300))}}})
        kind = {'id': 't', 'domains': ['light'], 'attributes': ['effect_list', 'options'], 'fields': {}}
        _, part = service.entity_part(kind, {'options': {'plugin_entity': 'light.strip'}})
        got = part['attributes']
        self.assertEqual(len(got['effect_list']), len(got['options']))
        self.assertEqual(got['effect_list'], effects[:len(got['effect_list'])])
        self.assertGreater(len(got['options']), 16)
        self.assertLessEqual(len(json.dumps(part, separators=(',', ':'))), 2600)

    def test_the_entity_list_keeps_to_the_attributes_a_tile_needs(self):
        _, attrs, _ = series_sources()['nordpool (HACS), raw_today']
        service = self.service({'sensor.price': {'attributes': attrs}, 'sensor.temperature': {'attributes': {'unit_of_measurement': 'C'}},
                                'sensor.average': {'attributes': {'raw_today': []}}, 'light.raw': {'attributes': {'raw_today': []}}})
        self.assertEqual(service.entities_with(['sensor'], ['raw_today']), ['sensor.average', 'sensor.price'])
        self.assertEqual(service.entities_with(['sensor'], ['raw_today', 'tomorrow']), ['sensor.price'])

    async def test_an_answer_the_manifest_maps_goes_as_its_fields(self):
        import shutil
        _, answer, _ = series_sources()['nordpool, get_prices_for_date']
        _, quarter, _ = series_sources()['energyzero, get_energy_prices (quarter)']
        sent = []

        async def request(kind, **data):
            return {'response': answer if data['domain'] == 'nordpool' else quarter}
        service = self.service({}, request)
        service.manager.screen = lambda inbox: {'id': inbox, 'node': inbox, 'name': 'Kitchen', 'online': True}
        service.manager.transport = lambda inbox, screen=None: 'action'

        async def send_auxiliary(inbox, message, action, request):
            sent.append(message)
        service.manager.send_auxiliary = send_auxiliary
        plugins_dir = service.folder_root()
        plugins_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / 'tests/fixtures/plugins/price_peek', plugins_dir / 'price_peek')
        service.scan_folders()
        service.store.put('kitchen', {'id': 'price_peek', 'source': 'folder', 'state': 'active'})
        ask = lambda n, command: service.answer({'inbox': 'kitchen', 'plugin': 'price_peek', 'body': json.dumps(
            {'re': n, 'ask': command, 'data': {'config_entry': 'x', 'date': '2026-10-09'}})})
        await ask(1, 'call_service:nordpool.get_prices_for_date')
        result = sent[0]['m']['result']
        self.assertEqual(set(result), {'prices', 'start'})
        self.assertEqual(result['prices'], PRICES['days'][1]['prices'])        # all 96; 24 objects before 0.5
        # An answer without a map goes as it came, bounded by bytes: as many whole slots as fit, never cut open.
        await ask(2, 'call_service:energyzero.get_energy_prices')
        raw = sent[1]['m']['result']['prices']
        self.assertTrue(24 <= len(raw) < 96)
        self.assertEqual(raw[0], quarter['prices'][0])
        for message in sent:
            self.assertLessEqual(len(json.dumps(message['m'])), 3400)


def yaml_manifest(name):
    import yaml
    return yaml.safe_load((ROOT / 'tests/fixtures/plugins' / name / 'tessera-plugin.yaml').read_text())


class SeriesManifest(unittest.TestCase):
    """The manifest's side of plugin API 0.5: fields of an entity and of an answer, has_attributes, the kind numbers."""

    def tile(self, **changes):
        tile = {'id': 'day', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 900, 'domains': ['sensor']}
        tile.update(changes)
        return manifest(tiles=[tile], fetch=[])

    def test_the_price_plugin_passes(self):
        checked = pm.check(yaml_manifest('price_peek'), json.loads(
            (ROOT / 'tests/fixtures/plugins/price_peek/translations/en.json').read_text()))
        self.assertEqual(checked['tiles'][0]['has_attributes'], ['raw_today'])
        self.assertEqual(checked['answers'][0]['fields']['prices']['as'], 'numbers')
        self.assertEqual(checked['answers'][0]['fields']['prices']['path'], [('all',), ('all',), ('key', 'price')])

    def test_wrong_ones_are_refused_with_a_reason(self):
        wrong = {
            'fields without domains': self.tile(domains=[], fields={'p': 'a[*].b'}),
            'has_attributes without domains': self.tile(domains=[], has_attributes=['raw_today']),
            'a field named as an attribute': self.tile(attributes=['today'], fields={'today': {'path': 'raw[*].v', 'as': 'numbers'}}),
            'a field named state': self.tile(fields={'state': 'a'}),
            'an unknown kind': self.tile(fields={'p': {'path': 'a', 'as': 'list'}}),
            'a path with a filter': self.tile(fields={'p': {'path': 'a[?(@.x)]', 'as': 'numbers'}}),
            'a countdown to numbers': self.tile(fields={'p': {'path': 'a[*].t', 'as': 'numbers'}}, preview={'countdown': 'p'}),
            'an answer of a command not allowed': manifest(answers=[{'command': 'call_service:nordpool.get_prices_for_date', 'fields': {'p': 'a'}}]),
            'an answer mapped twice': manifest(permissions={'network': ['api.example.org'], 'ha_commands': ['history/history_during_period']},
                                               answers=[{'command': 'history/history_during_period', 'fields': {'p': 'a'}}] * 2),
        }
        for reason, data in wrong.items():
            with self.subTest(reason), self.assertRaises(pm.ManifestError):
                pm.check(data, ENGLISH)

    def test_a_field_path_may_start_with_a_list_step(self):
        self.assertEqual(pm.parse_path('[*].price', root=False), [('all',), ('key', 'price')])
        self.assertEqual(pm.parse_path('[0]', root=False), [('at', 0)])
        for wrong in ('.price', '$.price', ''):
            with self.subTest(wrong), self.assertRaises(ValueError):
                pm.parse_path(wrong, root=False)

    def test_numbers_keep_gaps_and_refuse_what_json_cannot_carry(self):
        field = {'path': pm.parse_path('[*]', root=False), 'as': 'numbers'}
        self.assertEqual(plugin_fetch.field_value([0.1, None, '0,25', 'x', True, float('nan'), 3], field),
                         [0.1, None, 0.25, None, 1, None, 3])


class PanelSettings(unittest.IsolatedAsyncioTestCase):
    """A plugin's settings on a screen (plugin API 0.6): found by their name in plugin.yaml through the entity registry,
    so a rename in Home Assistant keeps them; a text and a button with its status; only the screen's own entities."""

    def service(self, registry, states):
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        folder = Path(tmp.name) / 'tessera-plugins' / 'voice_probe'
        (folder / 'translations').mkdir(parents=True)
        (folder / 'tessera-plugin.yaml').write_text(
            'id: voice_probe\nversion: 1.0.0\napi: "0.6"\nicon: microphone\nmaintainer: someone\nlicense: MIT\ntopics: [voice]\n'
            'settings:\n  - { key: wake_word, label: word }\n  - { key: spotify_market, label: market }\n'
            '  - { key: test_wake, label: test, status: test_wake_result }\n')
        (folder / 'translations' / 'en.json').write_text(json.dumps(
            {'app': {'name': 'Voice', 'summary': 'Voice.', 'word': 'Word', 'market': 'Market', 'test': 'Test'}, 'screen': {}}))
        calls = []

        class FakeHA:
            changed, dirty = asyncio.Event(), set()

            async def call_service(self, domain, service, data):
                calls.append((domain, service, data))
        FakeHA.registry, FakeHA.states = registry, states

        class FakeManager:
            ha = FakeHA()
            page_senders, aliases = {}, {}

            def screen(self, inbox):
                return {'id': inbox, 'device_id': 'dev1', 'online': True}
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        service.scan_folders()
        service.store.put('kitchen', {'id': 'voice_probe', 'source': 'folder', 'state': 'active'})
        return service, calls

    def esphome(self, entity_id, name, device='dev1'):
        return {'entity_id': entity_id, 'device_id': device, 'platform': 'esphome', 'original_name': name}

    async def test_found_by_name_after_a_rename_and_never_on_another_device(self):
        registry = [self.esphome('select.my_kitchen_word', 'Wake word'),          # renamed in Home Assistant
                    self.esphome('text.kitchen_spotify_market', 'Spotify market'),
                    self.esphome('button.kitchen_test_wake', 'Test wake'),
                    self.esphome('sensor.kitchen_test_wake_result', 'Test wake result'),
                    self.esphome('select.hall_wake_word', 'Wake word', device='dev2')]
        states = {'select.my_kitchen_word': {'state': 'Okay Nabu', 'attributes': {'options': ['Okay Nabu', 'Hey Jarvis']}},
                  'text.kitchen_spotify_market': {'state': 'NL', 'attributes': {'min': 2, 'max': 2, 'mode': 'text'}},
                  'button.kitchen_test_wake': {'state': 'unknown'},
                  'sensor.kitchen_test_wake_result': {'state': 'Heard: Okay Nabu'}}
        service, calls = self.service(registry, states)
        rows = {row['key']: row for row in service.settings_for('kitchen')[0]['rows']}
        self.assertEqual(rows['wake_word']['entity'], 'select.my_kitchen_word')
        self.assertEqual(rows['wake_word']['options'], ['Okay Nabu', 'Hey Jarvis'])
        self.assertEqual((rows['spotify_market']['kind'], rows['spotify_market']['value'], rows['spotify_market']['max']), ('text', 'NL', 2))
        self.assertEqual((rows['test_wake']['kind'], rows['test_wake']['status']), ('button', 'Heard: Okay Nabu'))
        self.assertTrue(rows['test_wake']['available'])            # a button that was never pressed is there
        await service.set_setting('kitchen', 'button.kitchen_test_wake', True)
        await service.set_setting('kitchen', 'text.kitchen_spotify_market', 'BE')
        await service.set_setting('kitchen', 'select.my_kitchen_word', 'Hey Jarvis')
        self.assertEqual(calls, [('button', 'press', {'entity_id': 'button.kitchen_test_wake'}),
                                 ('text', 'set_value', {'entity_id': 'text.kitchen_spotify_market', 'value': 'BE'}),
                                 ('select', 'select_option', {'entity_id': 'select.my_kitchen_word', 'option': 'Hey Jarvis'})])
        for entity, value in (('text.kitchen_spotify_market', 'NLD'),            # longer than the entity takes
                              ('button.kitchen_test_wake', 'yes'),
                              ('sensor.kitchen_test_wake_result', 'x'),          # a status is shown, never set
                              ('select.hall_wake_word', 'Hey Jarvis')):           # another screen's entity
            with self.subTest(entity), self.assertRaises(ValueError):
                await service.set_setting('kitchen', entity, value)

    def test_the_object_id_is_esphomes(self):
        import plugins as plugin_service
        for name, key in (('Tap sound', 'tap_sound'), ('Mic gain (dB)', 'mic_gain__db_'), ('AEC', 'aec'), ('Wake-word', 'wake-word')):
            self.assertEqual(plugin_service.Plugins.object_id(name), key)

    def test_a_status_is_an_id_too(self):
        good = manifest(settings=[{'key': 'test_wake', 'label': 'tile', 'status': 'test_wake_result'}])
        self.assertEqual(pm.check(good, ENGLISH)['settings'][0]['status'], 'test_wake_result')
        with self.assertRaises(pm.ManifestError):
            pm.check(manifest(settings=[{'key': 'test_wake', 'label': 'tile', 'status': 'Test wake result'}]), ENGLISH)


MUSIC_ENGLISH = {'app': {'name': 'New music', 'summary': 'New releases.', 'tile': 'Releases', 'artists': 'Artists',
                         'kinds': 'Kinds', 'album': 'Albums', 'single': 'Singles', 'tags': 'Tags'}, 'screen': {}}


def music(**changes):
    """New music (plugin API 0.12): artists found by searching, one ask per artist, the answers as one list."""
    data = {
        'id': 'music', 'version': '1.0.0', 'api': '0.12', 'icon': 'music', 'maintainer': 'someone', 'license': 'MIT',
        'topics': ['media'], 'permissions': {'network': ['api.deezer.com'], 'home_assistant_actions': ['music_assistant.play_media']},
        'attributes': ['cloud'], 'privacy': 'https://example.org/p',
        'tiles': [{'id': 'releases', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 1200,
                   'data': 'releases', 'preview': {'title': '{title}', 'badge': '{artist}'}, 'options': [
                       {'id': 'artists', 'kind': 'choice', 'multiple': 8, 'options_from': 'artist_search', 'search': True,
                        'label': 'artists'},
                       {'id': 'kinds', 'kind': 'choice', 'multiple': 2, 'label': 'kinds',
                        'choices': [{'value': 'album', 'label': 'album'}, {'value': 'single', 'label': 'single'}]},
                       {'id': 'tags', 'kind': 'text', 'multiple': 4, 'label': 'tags', 'default': ['new']}]}],
        'fetch': [
            {'id': 'releases', 'each': 'artists', 'url': 'https://api.deezer.com/artist/{artists}/albums?limit=25',
             'every': '6h', 'map': {'items': '$.data[*]', 'fields': {
                 'title': 'title', 'date': {'path': 'release_date', 'as': 'epoch', 'tz': 'UTC'}, 'kind': 'record_type',
                 'artist': {'each': 'label'}, 'id': {'each': 'value'}}, 'sort': '-date', 'limit': 4}},
            {'id': 'artist_search', 'url': 'https://api.deezer.com/search/artist?q={search}', 'every': '1d',
             'map': {'items': '$.data[*]', 'value': 'id', 'label': 'name'}}],
    }
    data.update(changes)
    return data


class JsonValues(unittest.IsolatedAsyncioTestCase):
    """Plugin API 0.12: an option keeps a list (texts, or picks of a choice with their words), a choice is found by
    searching, a fetch asks once per value and puts the answers together, and a list joins into one ask."""

    def test_the_manifest_takes_lists_searches_and_each(self):
        out = pm.check(music(), MUSIC_ENGLISH)
        artists, kinds, tags = out['tiles'][0]['options']
        self.assertEqual((artists['multiple'], artists['search'], artists['default']), (8, True, []))
        self.assertTrue(pm.keeps_picks(artists) and pm.keeps_picks(kinds) and not pm.keeps_picks(tags))
        self.assertEqual(tags['default'], ['new'])
        self.assertEqual(out['fetch'][0]['each'], 'artists')
        self.assertEqual(out['fetch'][1]['placeholders'], ['search'])

    def test_wrong_ones_say_why(self):
        tile = music()['tiles'][0]
        artist, kinds, tags = tile['options']

        def with_options(*options, fetch=None):
            changed = json.loads(json.dumps(music()))
            changed['tiles'][0]['options'] = list(options)
            if fetch:
                changed['fetch'][0].update(fetch)
            return changed
        cases = {
            'only a text or a choice keeps several values': with_options({**tags, 'kind': 'toggle', 'default': False}),
            'must be between 2 and 16': with_options(artist, kinds, {**tags, 'multiple': 17}),
            'starts empty': with_options({**artist, 'default': [{'value': '1', 'label': 'x'}]}, kinds, tags),
            'search': with_options(artist, {**kinds, 'search': True}, tags),
            '"each" asks once per value': with_options({k: v for k, v in artist.items() if k != 'multiple'}, kinds, tags),
            'joins them': with_options(artist, kinds, tags, fetch={'each': None, 'url': 'https://api.deezer.com/a/{artists}'}),
            'is not this fetch\'s "each"': with_options(artist, kinds, tags, fetch={'url': 'https://api.deezer.com/a/{artists|,}'}),
            'only in a fetch with "each"': with_options(artist, kinds, tags, fetch={'each': None, 'url': 'https://api.deezer.com/a/{artists|,}'}),
        }
        for reason, manifest in cases.items():
            manifest['fetch'][0] = {k: v for k, v in manifest['fetch'][0].items() if v is not None}
            with self.subTest(reason), self.assertRaises(pm.ManifestError) as caught:
                pm.check(manifest, MUSIC_ENGLISH)
            if reason == '"each" asks once per value':
                self.assertIn('"multiple"', str(caught.exception))
            elif reason != 'search':
                self.assertIn(reason, str(caught.exception))

    def test_a_value_fits_its_option_or_not(self):
        artists, kinds, tags = pm.check(music(), MUSIC_ENGLISH)['tiles'][0]['options']
        picks = [{'value': '9635624', 'label': 'Billie Eilish'}, {'value': '27'}]
        self.assertEqual(pm.option_value(artists, picks), [picks[0], {'value': '27', 'label': '27'}])
        self.assertEqual(pm.option_value(kinds, [{'value': 'single', 'label': 'Singles'}]), [{'value': 'single', 'label': 'Singles'}])
        self.assertEqual(pm.option_value(tags, ['a', 'b']), ['a', 'b'])
        single = {**artists, 'multiple': None}
        self.assertEqual(pm.option_value(single, {'value': '1', 'label': 'One'}), {'value': '1', 'label': 'One'})
        self.assertEqual(pm.option_value(single, ''), '')
        for option, value in ((artists, ['9635624']), (artists, picks * 5), (artists, [picks[0], picks[0]]),
                              (kinds, [{'value': 'ep', 'label': 'EP'}]), (tags, ['a', '']), (tags, 'a'),
                              (tags, ['x' * 65]), (artists, [{'value': '1', 'label': 'x', 'more': 1}]), (single, '1')):
            with self.subTest(value=value), self.assertRaises(pm.ManifestError):
                pm.option_value(option, value)

    def test_the_stored_shape(self):
        ok = {'artists': [{'value': '1', 'label': 'One'}], 'tags': ['a'], 'pick': {'value': '2', 'label': ''},
              'n': 3, 'on': True, 'word': 'x'}
        self.assertTrue(core.plugin_options(ok))
        for wrong in ({'a': [[1]]}, {'a': [{'value': ''}]}, {'a': ['x'] * 17}, {'a': {'value': '1', 'deep': {}}},
                      {'a': [{'value': '1', 'label': 'é' * 65}]}, {'a': [1]},
                      {f'o{i}': [{'value': f'{i}{j}', 'label': 'l' * 60} for j in range(4)] for i in range(5)}):
            with self.subTest(wrong=str(wrong)[:60]):
                self.assertFalse(core.plugin_options(wrong))

    def test_one_number_everywhere(self):
        self.assertEqual((core.PLUGIN_LIST_MAX, core.PLUGIN_OPTIONS_BYTES), (pm.MAX_MULTIPLE, pm.OPTIONS_BYTES))
        # How many options a tile keeps (0.26): the manifest's and the layout check's.
        self.assertEqual(core.PLUGIN_OPTION_MAX, pm.MAX_OPTIONS)
        # The editor has no numbers of its own: it reads the manifest's from page-rules.json, which
        # tools/generate_page_rules.py writes and tests/test_page_conformance.py keeps current.
        for source in sorted((ROOT / 'web/src').rglob('*')):
            if source.suffix in ('.ts', '.vue'):
                with self.subTest(source.name):
                    self.assertIsNone(re.search(r'PLUGIN_(OPTIONS_BYTES|LIST_MAX|OPTION_MAX)[^=\n]*=\s*\d', source.read_text()),
                                      f'{source.relative_to(ROOT)} writes a plugin option number by hand: the editor '
                                      'reads it from page-rules.json (rules.plugins), which tools/generate_page_rules.py '
                                      'writes from the manifest\'s')
        rules = json.loads((ROOT / 'web/src/model/page-rules.json').read_text())['plugins']
        self.assertEqual(rules, {'optionsBytes': pm.OPTIONS_BYTES, 'listMax': pm.MAX_MULTIPLE, 'optionMax': pm.MAX_OPTIONS})

    def test_the_add_on_and_the_editor_say_alike_which_entity_an_option_is_for(self):
        # The cases the editor's entityFits answers too (web/tests/plugin-conformance.spec.ts).
        cases = json.loads((ROOT / 'tests/fixtures/plugin-conformance.json').read_text())['entity_fits']
        self.assertGreater(len(cases), 10)
        for case in cases:
            with self.subTest(case=case['name']):
                self.assertEqual(pm.entity_fits(case['option'], case['entity'], case.get('device_class'), case.get('translation_key')),
                                 case['fits'])

    def test_words_and_joins(self):
        self.assertEqual(plugin_fetch.words_of({'on': True, 'off': False, 'n': 3.0, 'x': 2.5, 'pick': {'value': '7', 'label': 'L'},
                                                'list': [{'value': 'a'}, 'b', {'value': ''}]}),
                         {'on': 'true', 'off': 'false', 'n': '3', 'x': '2.5', 'pick': '7', 'list': ['a', 'b']})
        fetch = {'url': 'https://api.example.org/q?ids={ids|,}&k={key}', 'headers': {'X-Ids': '{ids|;}'},
                 'placeholders': ['ids', 'key']}
        url, headers = plugin_fetch.fill(fetch, {'ids': ['a b', 'c,d']}, {'key': 's'})
        self.assertEqual(url, 'https://api.example.org/q?ids=a%20b,c%2Cd&k=s')
        self.assertEqual(headers, {'X-Ids': 'a b;c,d'})
        with self.assertRaises(plugin_fetch.FetchRefused):
            plugin_fetch.fill(fetch, {'ids': []}, {'key': 's'})
        with self.assertRaises(plugin_fetch.FetchRefused):
            plugin_fetch.fill({'url': 'https://x.org/{ids}', 'headers': {}, 'placeholders': ['ids']}, {'ids': ['a']}, {})

    def service(self, answers):
        import plugins as plugin_service
        from types import SimpleNamespace
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class FakeManager:
            ha = type('HA', (), {'states': {}, 'time_zone': 'UTC', 'changed': asyncio.Event(), 'dirty': set()})()
            page_senders, layouts = {}, {}
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        asked = []

        async def download(url, headers, network):
            asked.append(url)
            answer = answers.get(url)
            if isinstance(answer, Exception) or answer is None:
                raise answer or OSError('HTTP 404')
            return answer
        service.fetcher.download = download
        service.secret_values = lambda entry, inbox=None: {}
        checked = pm.check(music(), MUSIC_ENGLISH)
        entry = SimpleNamespace(id='music', manifest=checked, fetch=lambda i: next(f for f in checked['fetch'] if f['id'] == i),
                                tile=lambda i: checked['tiles'][0], text=lambda key, language='en': key)
        return service, entry, checked['tiles'][0], asked

    ALBUMS = 'https://api.deezer.com/artist/{}/albums?limit=25'

    async def test_one_ask_per_artist_and_one_list_newest_first(self):
        answers = {self.ALBUMS.format('1'): {'data': [{'title': 'Old', 'release_date': '2024-01-01', 'record_type': 'album'},
                                                      {'title': 'Newest', 'release_date': '2026-10-01', 'record_type': 'single'}]},
                   self.ALBUMS.format('2'): {'data': [{'title': 'Middle', 'release_date': '2025-05-05', 'record_type': 'album'}]}}
        service, entry, tile, asked = self.service(answers)
        chosen = service.values_of(entry, tile, {'artists': [{'value': '1', 'label': 'One'}, {'value': '2', 'label': 'Two'}]})
        data = await service.tile_data(entry, tile, chosen)
        self.assertEqual(sorted(asked), sorted(answers))
        self.assertEqual([(i['title'], i['artist'], i['id']) for i in data['items']],
                         [('Newest', 'One', '1'), ('Middle', 'Two', '2'), ('Old', 'One', '1')])
        self.assertNotIn('stale', data)
        # A second tile with one of the same artists shares its ask.
        await service.tile_data(entry, tile, service.values_of(entry, tile, {'artists': [{'value': '2', 'label': 'Two'}]}))
        self.assertEqual(len(asked), 2)

    async def test_an_artist_that_fails_is_left_out_and_the_list_is_stale(self):
        service, entry, tile, _ = self.service({self.ALBUMS.format('1'): {'data': [{'title': 'A', 'release_date': '2026-01-01'}]},
                                                self.ALBUMS.format('2'): OSError('HTTP 503')})
        data = await service.tile_data(entry, tile, service.values_of(entry, tile, {'artists': [
            {'value': '1', 'label': 'One'}, {'value': '2', 'label': 'Two'}]}))
        self.assertEqual([i['title'] for i in data['items']], ['A'])
        self.assertTrue(data['stale'])
        none = await service.tile_data(entry, tile, service.values_of(entry, tile, {'artists': [{'value': '2', 'label': 'Two'}]}))
        self.assertEqual(none, {'wait': 'failed'})
        empty = await service.tile_data(entry, tile, service.values_of(entry, tile, {}))
        self.assertEqual(empty, {'wait': 'not_filled'})

    async def test_a_search_asks_with_what_was_typed(self):
        url = 'https://api.deezer.com/search/artist?q=billie%20e'
        service, entry, _, asked = self.service({url: {'data': [{'id': 9635624, 'name': 'Billie Eilish'}]}})
        service.known = lambda plugin, inbox=None: entry
        out = await service.choices('music', 'artist_search', {'kinds': [{'value': 'album', 'label': 'Albums'}]}, search=' billie e ')
        self.assertEqual(out, {'choices': [{'value': '9635624', 'label': 'Billie Eilish'}]})
        self.assertEqual(asked, [url])
        self.assertEqual(service.fetcher.cache[next(iter(service.fetcher.cache))]['every'], 600)
        self.assertEqual(await service.choices('music', 'artist_search', {}), {'choices': [], 'wait': 'not_filled'})

    async def test_the_options_count_in_the_message(self):
        service, entry, tile, _ = self.service({})
        service.known = lambda plugin, inbox=None: entry
        long = [{'value': f'{i:02d}' * 30, 'label': 'L' * 60} for i in range(8)]
        items = {'items': [{'title': 'x' * 40, 'n': i} for i in range(60)]}

        async def data(*args, **kwargs):
            return dict(items)
        service.tile_data = data
        message = await service.tile_message(0, {'entity': 'plugin:music.releases', 'name': 'N' * 80,
                                                 'options': {'plugin': {'artists': long}}})
        import page_delivery
        size = len(json.dumps({**message, 'v': 2, 'session': '0' * 16, 'seq': 0xFFFFFFFF, 'rev': '0' * 16, 'slot': 63},
                              ensure_ascii=False, separators=(',', ':')).encode())
        self.assertLessEqual(size, page_delivery.MAX_MESSAGE)
        self.assertGreater(len(message['x']['items']), 10)


class WhetherTheScreenRunsIt(unittest.TestCase):
    """plugins.runs: the editor says when a screen does not run a plugin the app built into it (a crash at boot, a
    firmware built without it), and nothing while that cannot be known."""

    def test_the_hello_decides_once_the_screen_has_said_it(self):
        import plugins as plugin_service
        record = {'id': 'tap_sound', 'version': '0.2.0', 'state': 'active', 'settled': 1000}
        running = {'tablet': [{'id': 'tap_sound', 'version': '0.2.0', 'tiles': []}, {'id': 'cinema', 'version': '0.1.0'}]}
        self.assertTrue(plugin_service.runs('tablet', record, running, now=5000))
        self.assertFalse(plugin_service.runs('tablet', dict(record, version='0.2.1'), running, now=5000), 'another version')
        self.assertFalse(plugin_service.runs('tablet', dict(record, id='bt_proxy'), running, now=5000), 'not in the hello')
        self.assertTrue(plugin_service.runs('tablet', {'id': 'cinema', 'version': '0.1.0'}, running, now=5000), 'a record from before `settled`')

    def test_the_version_a_screen_runs_instead(self):
        import plugins as plugin_service
        record = {'id': 'co2_ring', 'version': '0.2.16', 'state': 'active', 'settled': 1000}
        running = {'tablet': [{'id': 'co2_ring', 'version': '0.2.17', 'tiles': ['co2']}]}
        self.assertEqual(plugin_service.runs_version('tablet', record, running, now=5000), '0.2.17', 'built elsewhere')
        self.assertIsNone(plugin_service.runs_version('tablet', dict(record, version='0.2.17'), running, now=5000), 'this version')
        self.assertIsNone(plugin_service.runs_version('tablet', dict(record, id='cinema'), running, now=5000), 'not in the hello')
        self.assertIsNone(plugin_service.runs_version('kitchen', record, running, now=5000), 'not known')
        self.assertIsNone(plugin_service.runs_version('tablet', record, running, now=1001), 'just built')

    def test_nothing_while_it_cannot_be_known(self):
        import plugins as plugin_service
        record = {'id': 'tap_sound', 'version': '0.2.0', 'state': 'active', 'settled': 1000}
        running = {'tablet': []}
        self.assertIsNone(plugin_service.runs('kitchen', record, running, now=5000), 'the screen has not said: offline, or no plugins in its hello')
        self.assertIsNone(plugin_service.runs('tablet', dict(record, state='building'), running, now=5000))
        self.assertIsNone(plugin_service.runs('tablet', dict(record, state='failed'), running, now=5000))
        self.assertIsNone(plugin_service.runs('tablet', record, running, now=1000 + plugin_service.SETTLING - 1), 'the screen reboots after its build')
        self.assertFalse(plugin_service.runs('tablet', record, running, now=1000 + plugin_service.SETTLING))


class CardPictures(unittest.TestCase):
    """Pictures on a plugin's card over the page (plugin API 0.13): the manifest's `pictures` of a card, the card's
    question, and where its pictures may come from."""

    def checked(self, **card):
        data = manifest(api='0.13', cards=[{'id': 'release', 'name': 'tile', **card}])
        return pm.check(data, ENGLISH)

    def question(self, **changes):
        """The question a plugin's card asks (picture_legacy: plugin API 0.13's shape), or None."""
        request = {'tiles': 'plugin:bus.release', 'idx': '0', 'card': '1', 'for': '', 'bg': '202020', 'dark': '0',
                   'atlas': '[[300,0,160,160,8,0]]', 'src': '["https://api.example.org/cover.jpg"]', 'fit': '["cover"]'}
        request.update(changes)
        found = picture_legacy.read(request, SCREEN)
        return found.question if found else None

    def test_a_card_may_have_places(self):
        self.assertEqual(self.checked(pictures=1)['cards'][0]['pictures'], 1)
        self.assertEqual(self.checked()['cards'][0]['pictures'], 0)           # none without the field, as before
        for wrong in (9, -1, 1.5, 'one'):
            with self.subTest(wrong), self.assertRaises(pm.ManifestError):
                self.checked(pictures=wrong)

    def test_the_question_names_the_card_and_what_it_shows(self):
        q = self.question()
        self.assertEqual((q.owner.kind, core.plugin_tile(q.owner.key), q.owner.index, q.owner.of),
                         ('plugin_card', ('bus', 'release'), -1, ''))
        self.assertEqual(self.question(**{'for': 'media_player.kitchen'}).owner.of, 'media_player.kitchen')
        self.assertEqual(self.question(idx='').owner.index, -1)                    # a card has no index of its own
        self.assertEqual(picture_legacy.read({'tiles': 'plugin:bus.release', 'card': '1', 'bg': '202020', 'src': '["https://api.example.org/cover.jpg"]',
                                              'atlas': '[[300,0,160,160,8,0]]'}, SCREEN).kind, 'pcard')
        for bad in ({'for': 'screen.clock'}, {'for': 'not an entity'}, {'tiles': 'media_player.kitchen'}, {'saver': '1'}):
            self.assertIsNone(self.question(**bad), bad)
        tile = picture_legacy.read({'tiles': 'plugin:bus.next', 'idx': '3', 'bg': '202020', 'atlas': '[[0,0,60,90,6,0]]',
                                    'src': '["https://api.example.org/a.jpg"]'}, SCREEN)
        self.assertEqual((tile.kind, tile.question.owner.kind), ('live', 'plugin_tile'))   # a tile's question as before

    def test_where_a_cards_picture_may_come_from(self):
        checked = self.checked(pictures=1)
        card = checked['cards'][0]
        self.assertEqual(plugin_pictures.allowed('https://api.example.org/cover.jpg', checked, card, False), 'network')
        self.assertIsNone(plugin_pictures.allowed('https://image.tmdb.org/cover.jpg', checked, card, False))
        # Home Assistant's own pictures only for a card shown for an entity of the layout.
        self.assertIsNone(plugin_pictures.allowed('/api/image_proxy/media_player.kitchen', checked, card, False))
        self.assertEqual(plugin_pictures.allowed('/api/image_proxy/media_player.kitchen', checked, card, True), 'home_assistant')
        self.assertIsNone(plugin_pictures.allowed('https://api.example.org/cover.jpg', checked, self.checked()['cards'][0], False))
        q = self.question()
        self.assertIsNone(refused(q, checked, card, False))
        self.assertIn('no pictures', refused(q, self.checked(), self.checked()['cards'][0], False))
        self.assertIn('no such place', refused(q, checked, None, False))
        self.assertIn('allows 1', refused(self.question(atlas='[[0,0,60,60,0,0],[100,0,60,60,0,0]]',
                                                        src='["https://api.example.org/a.jpg","https://api.example.org/b.jpg"]',
                                                        fit='["cover","cover"]'), checked, card, False))
