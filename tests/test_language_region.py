"""Settings -> Language & region (app 0.2.90): how the screens write the clock and numbers, the language each screen's
messages go in, the language in the screens' YAML and the 24 hours an app from before it kept."""
from manager_fixtures import with_screen_grid
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import i18n  # noqa: E402
import yaml  # noqa: E402
from firmware import Firmware, LenientLoader  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
PROFILE_TAIL = 'packages:\n  display: !include /r/packages/core.yaml\n'


def region(tmp, ha='en', **stored):
    path = Path(tmp) / 'language.json'
    if stored:
        path.write_text(json.dumps({'version': 1, **stored}))
    return i18n.Region(path, ha_language=lambda: ha)


class NotationTests(unittest.TestCase):
    def test_every_home_assistant_language_has_a_notation(self):
        tool = importlib.util.spec_from_file_location('i18n_tool', ROOT / 'tools' / 'i18n.py')
        module = importlib.util.module_from_spec(tool)
        tool.loader.exec_module(module)
        self.assertEqual(set(module.HA_LANGUAGES), set(i18n.REGIONS) - {'_about'})
        for code, written in i18n.REGIONS.items():
            if code == '_about':
                continue
            self.assertIn(written['clock'], ('12', '24'), code)
            self.assertIn(written['numbers'], ('point', 'comma', 'space'), code)
            self.assertIn(written['group_min'], (1, 2), code)

    def test_automatic_follows_home_assistants_own_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Finnish: English texts (no file yet), Finnish clock and numbers.
            sv = region(tmp, 'fi')
            self.assertEqual((sv.language(), sv.clock_24h(), sv.number_style(), sv.group_min(), sv.percent_space()),
                             ('en', True, 'space', 1, True))
            # Brazilian Portuguese: the Portuguese texts, Brazil's numbers.
            br = region(tmp, 'pt-BR')
            self.assertEqual((br.language(), br.number_style(), br.group_min()), ('pt', 'comma', 1))
            pt = region(tmp, 'pt')
            self.assertEqual((pt.number_style(), pt.group_min(), pt.percent_space()), ('space', 2, False))
            us, uk = region(tmp, 'en'), region(tmp, 'en-GB')
            self.assertEqual((us.clock_24h(), uk.clock_24h(), uk.language()), (False, True, 'en-GB'))
            de = region(tmp, 'de')
            self.assertEqual((de.number_style(), de.percent_space()), ('comma', True))

    def test_a_chosen_language_and_format_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            chosen = region(tmp, 'nl', language='es', clock='12', numbers='point')
            # A chosen format is Home Assistant's for it, which groups from four digits; the space before % stays the
            # language's.
            self.assertEqual((chosen.language(), chosen.clock_24h(), chosen.number_style(), chosen.group_min()),
                             ('es', False, 'point', 1))
            self.assertEqual(region(tmp, 'nl', language='es', clock='auto', numbers='auto').group_min(), 2)
        with tempfile.TemporaryDirectory() as tmp:
            view = region(tmp, 'de').view()
            self.assertEqual({key: view[key] for key in ('group_min', 'percent_space', 'numbers_effective')},
                             {'group_min': 1, 'percent_space': True, 'numbers_effective': 'comma'})

    def test_numbers_and_units_as_home_assistant_writes_them(self):
        self.assertEqual(i18n.format_number('1234.5', 'comma', 2), '1234,5')
        self.assertEqual(i18n.format_number('12345.5', 'comma', 2), '12.345,5')
        self.assertEqual(i18n.format_number('1234', 'space'), '1 234')
        self.assertEqual(i18n.format_number('-1234567', 'point'), '-1,234,567')
        self.assertEqual(i18n.format_number('on', 'comma'), 'on')
        try:
            i18n.set_screens('de', 'comma', True, 1, True)
            self.assertEqual([i18n.unit_suffix(unit) for unit in ('%', '°', '°C', '', None)], [' %', '°', ' °C', '', ''])
            i18n.set_screens('nl', 'comma', True, 1, False)
            self.assertEqual(i18n.unit_suffix('%'), '%')
        finally:
            i18n.set_screens('en', 'point')

    def test_plural_rules_match_the_firmware(self):
        """Python's rules against the C++ ones a screen's build writes (screen_text_gen.PLURAL_RULES), n from -30."""
        compiler = shutil.which(os.environ.get('CXX', 'clang++')) or shutil.which('g++')
        if not compiler:
            self.skipTest('no C++ compiler')
        spec = importlib.util.spec_from_file_location('gen', ROOT / 'components/smart_display/screen_text_gen.py')
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        numbers = list(range(-30, 131)) + [1001, 1011, 1021, 1112]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'rules.cpp'
            functions = '\n'.join(f'int rule_{name}(int n) {{ {body} }}' for name, body in gen.PLURAL_RULES.items())
            calls = '\n'.join(f'  for (int n : ns) std::printf("{name} %d %d\\n", n, rule_{name}(n));' for name in gen.PLURAL_RULES)
            source.write_text('#include <cstdio>\n' + functions + '\nint main() {\n  int ns[] = {' + ','.join(map(str, numbers)) +
                              '};\n' + calls + '\n}\n')
            subprocess.run([compiler, '-std=c++17', str(source), '-o', str(Path(tmp) / 'rules')], check=True)
            out = subprocess.run([str(Path(tmp) / 'rules')], check=True, capture_output=True, text=True).stdout.split('\n')
        for line in filter(None, out):
            name, n, index = line.split()
            self.assertEqual(i18n.PLURAL[name](int(n)), int(index), f'{name}({n})')


class ScreenContextTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_screens('en', 'point')

    def test_each_screen_gets_the_words_its_firmware_speaks(self):
        import header_bar
        i18n.set_screens('nl', 'comma', True, 1, False)
        legacy = i18n.screen_context({'language': None, 'language_sensor': False})
        dutch = i18n.screen_context({'language': 'nl', 'language_sensor': True})
        restarting = i18n.screen_context({'language': None, 'language_sensor': True})
        self.assertEqual(i18n.screen_t('screen.ha.on'), 'Aan')
        for context, word, number, letters in ((legacy, 'On', '1,234.5', 'Waz'), (dutch, 'Aan', '1.234,5', 'Wąż'),
                                               (restarting, 'Aan', '1.234,5', 'Wąż')):
            token = i18n.SCREEN.set(context)
            try:
                self.assertEqual((i18n.screen_t('screen.ha.on'), i18n.screen_number('1234.5')), (word, number))
                # Firmware from before the languages lacks most accented letters: they fold to the base letter.
                self.assertEqual(header_bar.clean_text('Wąż'), letters)
            finally:
                i18n.SCREEN.reset(token)
        self.assertIsNone(i18n.screen_context(None))


class ProfileLanguageTests(unittest.TestCase):
    CASES = {
        'plain': ('substitutions:\n  DEVICE_NAME: "a"\n\n' + PROFILE_TAIL, True),
        'four spaces': ('substitutions:\n    DEVICE_NAME: "a"\n    FONT: "x"\n' + PROFILE_TAIL, True),
        'a comment inside': ('substitutions:\n  DEVICE_NAME: "a"\n# a note\n  LANGUAGE: "en"\n' + PROFILE_TAIL, True),
        'quoted key': ('substitutions:\n  "LANGUAGE": "en"\n  DEVICE_NAME: a\n' + PROFILE_TAIL, True),
        'no final newline': (PROFILE_TAIL + 'substitutions:\n  DEVICE_NAME: "a"\n  LANGUAGE: "de"', True),
        'document start': ('# mine\n---\n' + PROFILE_TAIL, True),
        'comments after the key': ('substitutions:   # mine\n  DEVICE_NAME: "a"  # name\n\n\n# esphome\nesphome:\n  name: a\n' + PROFILE_TAIL, True),
        'windows line ends': (('substitutions:\n  DEVICE_NAME: "a"\n' + PROFILE_TAIL).replace('\n', '\r\n'), True),
        'include': ('substitutions: !include subs.yaml\n' + PROFILE_TAIL, False),
        'flow mapping': ('substitutions: {DEVICE_NAME: a}\n' + PROFILE_TAIL, False),
        'not ours': ('substitutions:\n  A: b\nesphome:\n  name: z\n', False),
    }

    def test_the_language_line_changes_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Firmware(tmp, tmp)
            for index, (name, (text, writes)) in enumerate(self.CASES.items()):
                with self.subTest(name):
                    path = Path(tmp) / f'p{index}.yaml'
                    path.write_bytes(text.encode())
                    before = yaml.load(text.replace('\r\n', '\n'), Loader=LenientLoader)
                    with self.assertLogs('screen_manager', 'WARNING') if name in ('include', 'flow mapping') else _quiet():
                        self.assertEqual(firmware.set_language(path.name, 'nl'), writes)
                    out = path.read_bytes().decode()
                    self.assertEqual('\r\n' in out, '\r\n' in text, 'line ends stay as they were')
                    after = yaml.load(out.replace('\r\n', '\n'), Loader=LenientLoader)
                    if writes:
                        self.assertEqual(after['substitutions']['LANGUAGE'], 'nl')
                        strip = lambda data: ({k: v for k, v in data.items() if k != 'substitutions'},
                                              {k: v for k, v in (data.get('substitutions') or {}).items() if k != 'LANGUAGE'})
                        self.assertEqual(strip(after), strip(before))
                        self.assertFalse(firmware.set_language(path.name, 'nl'), 'nothing to do the second time')
                    else:
                        self.assertEqual(out, text)
            english = Path(tmp) / 'english.yaml'
            english.write_text(PROFILE_TAIL)
            self.assertFalse(firmware.set_language(english.name, 'en'), 'English is the default: no line needed')

    def test_every_build_writes_the_language_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Firmware(tmp, tmp)
            path = Path(tmp) / 'screen.yaml'
            path.write_text('substitutions:\n  DEVICE_NAME: "screen"\n' + PROFILE_TAIL)
            firmware.language = lambda: 'de'
            firmware.run = lambda *args: asyncio.sleep(0)
            with unittest.mock.patch('shutil.which', return_value='/usr/bin/esphome'):
                async def start():
                    firmware.start({'file': 'screen.yaml', 'action': 'validate'})
                    self.assertNotIn('LANGUAGE', path.read_text(), 'validating changes nothing')
                    await firmware.task
                    firmware.start({'file': 'screen.yaml', 'action': 'build'})
                    await firmware.task
                asyncio.run(start())
            self.assertIn('LANGUAGE: "de"', path.read_text())


class _quiet:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class ClockPinTests(unittest.IsolatedAsyncioTestCase):
    def manager(self, path, switches=None):
        import test_scaling
        from server import Manager
        ha = test_scaling.fake_ha(firmware='0.2.75')
        for index, state in enumerate(switches or []):
            ha.registry.append({'entity_id': f'switch.clock_{index}', 'platform': 'esphome', 'original_name': '24-hour clock',
                                'device_id': 'd1'})
            if state is not None:
                ha.states[f'switch.clock_{index}'] = {'state': state}
        ha.ha_language = 'en'
        ha.services_changed = asyncio.Event()
        return Manager(with_screen_grid(ha), path)

    async def test_a_new_install_follows_the_language_from_the_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screens.json'
            first = self.manager(path)
            self.assertTrue((Path(tmp) / 'language.json').exists(), 'stored at once')
            first.save('text.screen', {'title': 'Home', 'tiles': [{'entity': 'light.a'}]})
            again = self.manager(path, ['on'])
            self.assertEqual((again.region.clock, again.region.pinned, again.region.clock_24h()), ('auto', False, False))

    async def test_an_older_app_keeps_its_24_hours_until_the_switches_tell(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screens.json'
            path.write_text(json.dumps({'version': 1, 'screens': {'text.screen': {'title': 'Home', 'tiles': [{'entity': 'light.a'}]}}}))
            waiting = self.manager(path, ['off', None])
            self.assertEqual((waiting.region.clock, waiting.region.pinned), ('24', True))
            self.assertFalse(waiting.resolve_clock_pin(), 'a switch without a state: ask again later')
            self.assertTrue(json.loads((Path(tmp) / 'language.json').read_text())['pinned'], 'the question survives a restart')
            twelve = self.manager(path, ['off', 'off'])
            self.assertTrue(twelve.resolve_clock_pin())
            self.assertEqual((twelve.region.clock, twelve.region.pinned), ('12', False))
            (Path(tmp) / 'language.json').unlink()
            mixed = self.manager(path, ['off', 'on'])
            self.assertFalse(mixed.resolve_clock_pin())
            self.assertEqual((mixed.region.clock, mixed.region.pinned), ('24', False))
            (Path(tmp) / 'language.json').unlink()
            chosen = self.manager(path, ['off', None])
            chosen.region.change({'clock': 'auto'})
            self.assertFalse(chosen.region.pinned, 'the owner chose a clock')

    async def test_home_assistants_words_follow_the_screen(self):
        """Old firmware keeps English words from Home Assistant too, a new one its language's (found in the second test pass:
        a playing media player said "Speelt" among English words on firmware 0.2.75)."""
        from server import HomeAssistant
        ha = HomeAssistant(None, 'http://127.0.0.1:1/api', 'token')
        ha.language_of = lambda: 'nl'
        ha.words_by_language = {'nl': {'state': 'Speelt'}, 'en': {'state': 'Playing'}}
        self.assertEqual(ha.state_words, {'state': 'Speelt'})
        for context, word in ((i18n.LEGACY, 'Playing'), ({'language': 'nl', 'legacy': False}, 'Speelt'),
                              ({'language': 'de', 'legacy': False}, 'Speelt')):
            token = i18n.SCREEN.set(context)
            try:
                self.assertEqual(ha.state_words, {'state': word})
            finally:
                i18n.SCREEN.reset(token)

    async def test_language_and_region_over_http(self):
        from server import create_app
        from aiohttp.test_utils import TestClient, TestServer
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(Path(tmp) / 'screens.json')
            async with TestClient(TestServer(create_app(m, True))) as client:
                csrf = (await (await client.get('/api/inventory?light=1')).json())['csrf']
                answer = await client.put('/api/language', json={'setting': 'de', 'numbers': 'point'}, headers={'X-Screen-CSRF': csrf})
                view = (await answer.json())['language']
                self.assertEqual((view['effective'], view['numbers_effective'], view['group_min'], view['percent_space']),
                                 ('de', 'point', 1, True))
                # What the screen reports stays English (the app reads it); the editor shows it in its own language.
                dutch = await (await client.get('/api/inventory?light=1', headers={'X-ESP-Screens-Language': 'nl'})).json()
                self.assertEqual((m.screens()[0]['status'], dutch['screens'][0]['status']), ('Synced', 'Gesynchroniseerd'))
                refused = await client.put('/api/language', json={'clock': '13'}, headers={'X-Screen-CSRF': csrf, 'X-ESP-Screens-Language': 'nl'})
                self.assertEqual(refused.status, 400)
                self.assertEqual((await refused.json())['error'], i18n.TRANSLATIONS.text('addon.errors.region_choice', 'nl'))
            self.assertEqual(json.loads((Path(tmp) / 'language.json').read_text())['language'], 'de')


import unittest.mock  # noqa: E402

if __name__ == '__main__':
    unittest.main()
