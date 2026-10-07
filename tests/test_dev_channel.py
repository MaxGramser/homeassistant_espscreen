"""The dev channel (docs/RELEASING.md, "Testing dev"): an app added from the repository's `#dev` URL builds every screen
from dev, its packages, components and fonts, and offers to reinstall the newest dev. The plain URL keeps main, and an
app added from anywhere else leaves a screen's `ref:` as it is."""
import asyncio
import hashlib
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(1, str(ROOT / 'tests'))
import yaml  # noqa: E402
import core  # noqa: E402
from core import REPO, channel_of, installation_yaml, set_channel  # noqa: E402
from firmware import Firmware, LenientLoader  # noqa: E402

# A screen's YAML as ESP Screens writes it, with a line of the owner's own and a comment next to the ref.
SCREEN = f'''# Keep this file safe: it contains the unique keys for this screen.
substitutions:
  DEVICE_NAME: "kitchen"
  DEVICE_FRIENDLY_NAME: "Kitchen"
  LANGUAGE: "nl"

esphome:
  name: "kitchen"
  friendly_name: "Kitchen"

packages:
  display:
    url: {REPO}
    ref: main   # the branch
    files: [packages/guition.yaml]
    refresh: 0s
  local_overrides: !include kitchen.local.yaml

api:
  encryption:
    key: "a2l0Y2hlbi1rZXktZm9yLXRoZS10ZXN0LW9ubHktMzI="
ota:
  - platform: esphome
    password: "kitchen-ota-password-for-the-test"
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
'''
ON_DEV = (SCREEN.replace('    ref: main   # the branch', '    ref: dev   # the branch')
          .replace('substitutions:\n', 'substitutions:\n  GITHUB_REF: "dev"\n', 1))


def load(text):
    return yaml.load(text.replace('\r\n', '\n'), Loader=LenientLoader)


class Channel(unittest.TestCase):
    def tearDown(self):
        set_channel(None)

    def test_the_slug_says_which_url_the_app_came_from(self):
        # The Supervisor's hash (supervisor/store/utils.py): the first eight of sha1 of the URL as added, lower case.
        url = 'https://github.com/MaxGramser/homeassistant_espscreen'
        self.assertEqual(hashlib.sha1(url.lower().encode()).hexdigest()[:8], 'ec8ae0ed')
        self.assertEqual(hashlib.sha1((url + '#dev').lower().encode()).hexdigest()[:8], 'fa6a7b50')
        self.assertEqual(channel_of('ec8ae0ed_esp_screen_manager'), 'main')
        self.assertEqual(channel_of('fa6a7b50_esp_screen_manager'), 'dev')
        for slug in ('local_esp_screen_manager', '1234abcd_esp_screen_manager', 'esp_screen_manager', '', None):
            with self.subTest(slug):
                self.assertIsNone(channel_of(slug))

    def test_a_new_screen_builds_from_the_channel(self):
        data = {'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall'}
        for channel, ref in ((None, 'main'), ('main', 'main'), ('dev', 'dev')):
            with self.subTest(channel):
                set_channel(channel)
                screen = load(installation_yaml(data))
                self.assertEqual(screen['packages']['display']['ref'], ref)
                # The components and fonts follow; main is the package's own default and needs no line.
                self.assertEqual(screen['substitutions'].get('GITHUB_REF'), 'dev' if ref == 'dev' else None)

    def test_every_published_entry_fetches_its_components_and_fonts_from_the_ref(self):
        for path in [*sorted((ROOT / 'packages').glob('*.yaml'))]:
            entry = load(path.read_text())
            if not isinstance(entry, dict) or 'external_components' not in entry:
                continue
            with self.subTest(path.name):
                self.assertEqual(entry['substitutions']['GITHUB_REF'], 'main')
                self.assertEqual({source['source']['ref'] for source in entry['external_components']}, {'${GITHUB_REF}'})
                if 'FONT_DIR' in entry['substitutions']:
                    self.assertIn('/${GITHUB_REF}/fonts', entry['substitutions']['FONT_DIR'])


class Branch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.firmware = Firmware(self.tmp.name, self.tmp.name)

    def tearDown(self):
        set_channel(None)
        self.tmp.cleanup()

    def write(self, text, name='kitchen.yaml'):
        path = Path(self.tmp.name) / name
        path.write_bytes(text.encode())
        return path

    def test_main_to_dev_and_back_changes_that_line_alone(self):
        path = self.write(SCREEN)
        self.assertTrue(self.firmware.set_branch(path.name, 'dev'))
        self.assertEqual(path.read_text(), ON_DEV)
        self.assertFalse(self.firmware.set_branch(path.name, 'dev'), 'nothing to do the second time')
        self.assertTrue(self.firmware.set_branch(path.name, 'main'))
        self.assertEqual(path.read_text(), ON_DEV.replace('dev', 'main'))
        self.assertEqual(load(path.read_text()), load(SCREEN) | {'substitutions': {**load(SCREEN)['substitutions'], 'GITHUB_REF': 'main'}})

    def test_windows_line_ends_stay(self):
        path = self.write(SCREEN.replace('\n', '\r\n'))
        self.assertTrue(self.firmware.set_branch(path.name, 'dev'))
        self.assertEqual(path.read_bytes().decode(), ON_DEV.replace('\n', '\r\n'))

    def test_a_ref_the_owner_chose_stays(self):
        for index, text in enumerate((SCREEN.replace('ref: main', 'ref: 0.4.83'),
                                      SCREEN.replace('ref: main', 'ref: 3f2a9c1'),
                                      SCREEN.replace('ref: main', 'ref: release-candidate'),
                                      SCREEN.replace(REPO, 'https://github.com/someone/fork'),
                                      SCREEN.replace('    ref: main   # the branch\n', ''))):
            with self.subTest(index):
                path = self.write(text, f'own{index}.yaml')
                self.assertFalse(self.firmware.set_branch(path.name, 'dev'))
                self.assertEqual(path.read_text(), text)

    def test_a_ref_line_elsewhere_is_not_ours(self):
        # The owner's own external_components says `ref: main` too, before the package: only the package's line moves.
        text = SCREEN.replace('packages:\n', f'external_components:\n  - source:\n      type: git\n      url: https://github.com/someone/parts\n      ref: main\n\npackages:\n')
        path = self.write(text)
        self.assertTrue(self.firmware.set_branch(path.name, 'dev'))
        after = load(path.read_text())
        self.assertEqual(after['external_components'][0]['source']['ref'], 'main')
        self.assertEqual(after['packages']['display']['ref'], 'dev')

    def test_every_build_takes_the_channel_and_no_channel_leaves_it(self):
        path = self.write(SCREEN.replace('ref: main', 'ref: dev'))
        self.firmware.run = lambda *args: asyncio.sleep(0)
        async def build():
            self.firmware.start({'file': path.name, 'action': 'build'})
            await self.firmware.task
        with unittest.mock.patch('shutil.which', return_value='/usr/bin/esphome'):
            # A local copy of the app (the bench, a deploy of dev): the screen keeps the dev it was pointed at.
            asyncio.run(build())
            self.assertEqual(load(path.read_text())['packages']['display']['ref'], 'dev')
            set_channel('main')
            asyncio.run(build())
            self.assertEqual(load(path.read_text())['packages']['display']['ref'], 'main')
            set_channel('dev')
            asyncio.run(build())
            self.assertEqual(path.read_text(), ON_DEV)

    def test_the_bridge_builds_from_the_channel(self):
        text = installation_yaml({'board': 'cyd', 'name': 'hall', 'friendly_name': 'Hall'})
        set_channel('dev')
        path = self.write(text, 'hall.yaml')
        self.firmware.set_branch(path.name, 'dev')
        bridge = load((Path(self.tmp.name) / self.firmware.bridge(path.name)).read_text())
        self.assertEqual(bridge['packages']['bridge']['ref'], 'dev')
        self.assertEqual(bridge['substitutions']['GITHUB_REF'], 'dev')


try:
    import aiohttp  # noqa: F401
    import test_updates
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Reinstall(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        set_channel(None)

    async def test_the_same_firmware_again_on_dev_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = test_updates.UpdaterTests.setup_manager(self, tmp)
            m.ha.states['text.fw1'] = {'state': core.FIRMWARE_VERSION}
            self.assertIsNone(m.updates.summary()['channel'])
            with self.assertRaisesRegex(ValueError, 'latest'):
                m.updates.start('text.screen1')
            for channel in (None, 'main'):
                set_channel(channel)
                with self.assertRaisesRegex(ValueError, 'dev channel'):
                    m.updates.start('text.screen1', reinstall=True)
            set_channel('dev')
            self.assertEqual(m.updates.summary()['channel'], 'dev')
            m.updates.start('text.screen1', reinstall=True)
            await m.updates.task
            self.assertEqual(m.firmware.calls, [{'file': 'living-room.yaml', 'action': 'install', 'target': '10.0.0.5'}])
            self.assertEqual(m.updates.results['text.screen1']['state'], 'success')


if __name__ == '__main__':
    unittest.main()
