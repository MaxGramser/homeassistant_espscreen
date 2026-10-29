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

    def test_docker_names_its_channel_and_the_supervisor_slug_wins(self):
        # docs/DOCKER.md, "Testing dev": without a Supervisor SCREEN_CHANNEL says it, which dev's image carries.
        self.assertEqual(core.start_channel(None, {'SCREEN_CHANNEL': 'dev'}), 'dev')
        self.assertEqual(core.start_channel(None, {'SCREEN_CHANNEL': 'main'}), 'main')
        for value in ('', ' ', 'Dev', 'feature', None):
            with self.subTest(value):
                self.assertIsNone(core.start_channel(None, {'SCREEN_CHANNEL': value}))
        self.assertIsNone(core.start_channel(None, {}))
        self.assertEqual(core.start_channel('fa6a7b50_esp_screen_manager', {'SCREEN_CHANNEL': 'main'}), 'dev')
        self.assertIsNone(core.start_channel('local_esp_screen_manager', {'SCREEN_CHANNEL': 'dev'}))
        # The image of a push to dev is built with CHANNEL=dev and keeps it; every other build leaves it empty.
        workflow = yaml.safe_load((ROOT / '.github/workflows/docker.yml').read_text())
        self.assertIn('dev', workflow[True]['push']['branches'])
        self.assertIn('screen_manager/**', workflow[True]['push']['paths'])
        build = workflow['jobs']['image']['steps'][-1]['with']['build-args']
        self.assertIn("CHANNEL=${{ github.ref == 'refs/heads/dev' && 'dev' || '' }}", build)
        dockerfile = (ROOT / 'screen_manager/Dockerfile').read_text()
        self.assertRegex(dockerfile, r'ARG CHANNEL=""\nENV SCREEN_CHANNEL="\$\{CHANNEL\}"\n')

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


class Release(unittest.TestCase):
    """The stable app builds its screens from the tag of its own release (app 0.4.85), so whatever starts a build (the
    app, Home Assistant's firmware update, ESPHome Device Builder) makes the firmware this app knows, and newer firmware
    arrives only with an update of the app."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.firmware = Firmware(self.tmp.name, self.tmp.name)

    def tearDown(self):
        set_channel(None)
        core.set_version(None)
        self.tmp.cleanup()

    def write(self, text, name='kitchen.yaml'):
        path = Path(self.tmp.name) / name
        path.write_bytes(text.encode())
        return path

    def test_the_stable_app_builds_from_its_own_tag(self):
        core.set_version('0.4.85')
        for channel, ref in ((None, 'main'), ('main', 'screens-v0.4.85'), ('dev', 'dev')):
            with self.subTest(channel):
                set_channel(channel)
                self.assertEqual(core.ref(), ref)
                screen = load(installation_yaml({'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall'}))
                self.assertEqual(screen['packages']['display']['ref'], ref)
                self.assertEqual(screen['substitutions'].get('GITHUB_REF'), None if ref == 'main' else ref)
        # Without a version the Supervisor gave (or one that is no release number), the stable app stays on main.
        set_channel('main')
        for version in (None, '', 'dev', '0.4', '0.4.85b1'):
            with self.subTest(version):
                core.set_version(version)
                self.assertEqual(core.ref(), 'main')

    def test_the_tag_is_the_one_a_release_makes(self):
        # tools/release.py publish tags screens-v<config.yaml's version>, the version the Supervisor reports.
        source = (ROOT / 'tools/release.py').read_text()
        self.assertIn("tag = f'screens-v{version}'", source)
        version = yaml.safe_load((ROOT / 'screen_manager/config.yaml').read_text())['version']
        core.set_version(version)
        self.assertRegex(core.release_ref(), core.RELEASE_TAG)
        self.assertEqual(core.release_ref(), f'screens-v{version}')

    def test_main_moves_to_the_tag_and_on_to_the_next(self):
        path = self.write(SCREEN)
        self.assertTrue(self.firmware.set_branch(path.name, 'screens-v0.4.85'))
        on_tag = (SCREEN.replace('    ref: main   # the branch', '    ref: screens-v0.4.85   # the branch')
                  .replace('substitutions:\n', 'substitutions:\n  GITHUB_REF: "screens-v0.4.85"\n', 1))
        self.assertEqual(path.read_text(), on_tag, 'the ref line and GITHUB_REF alone')
        self.assertFalse(self.firmware.set_branch(path.name, 'screens-v0.4.85'), 'nothing to do the second time')
        self.assertTrue(self.firmware.set_branch(path.name, 'screens-v0.4.86'))
        self.assertEqual(path.read_text(), on_tag.replace('0.4.85', '0.4.86'))
        # To the dev channel and back to a release.
        self.assertTrue(self.firmware.set_branch(path.name, 'dev'))
        self.assertEqual(path.read_text(), ON_DEV)
        self.assertTrue(self.firmware.set_branch(path.name, 'screens-v0.4.86'))
        self.assertEqual(path.read_text(), on_tag.replace('0.4.85', '0.4.86'))

    def test_a_ref_the_owner_chose_stays_on_the_stable_app(self):
        for index, text in enumerate((SCREEN.replace('ref: main', 'ref: v0.4.83'),
                                      SCREEN.replace('ref: main', 'ref: screens-v0.4'),
                                      SCREEN.replace('ref: main', 'ref: 3f2a9c1'),
                                      SCREEN.replace('ref: main', 'ref: release-candidate'),
                                      SCREEN.replace(REPO, 'https://github.com/someone/fork'))):
            with self.subTest(index):
                path = self.write(text, f'own{index}.yaml')
                self.assertFalse(self.firmware.set_branch(path.name, 'screens-v0.4.85'))
                self.assertEqual(path.read_text(), text)
        self.assertFalse(self.firmware.set_branch(self.write(SCREEN).name, 'v1.0'), 'only main, dev and our own tags')

    def test_the_start_points_every_screen_at_the_release(self):
        self.write(SCREEN, 'kitchen.yaml')
        self.write(SCREEN.replace('ref: main', 'ref: screens-v0.4.84'), 'hall.yaml')
        self.write(SCREEN.replace('ref: main', 'ref: release-candidate'), 'bench.yaml')
        self.write('substitutions: {}\n', 'kitchen.local.yaml')
        names = lambda: {p.name: load(p.read_text()) for p in Path(self.tmp.name).glob('*.yaml')}
        before = names()
        # An app without a channel (the bench, a fork) changes nothing.
        self.assertEqual(self.firmware.follow_release(), [])
        self.assertEqual(names(), before)
        set_channel('main')
        core.set_version('0.4.85')
        self.assertEqual(sorted(self.firmware.follow_release()), ['hall.yaml', 'kitchen.yaml'])
        after = names()
        for name in ('hall.yaml', 'kitchen.yaml'):
            self.assertEqual(after[name]['packages']['display']['ref'], 'screens-v0.4.85')
            self.assertEqual(after[name]['substitutions']['GITHUB_REF'], 'screens-v0.4.85')
        self.assertEqual(after['bench.yaml'], before['bench.yaml'])
        self.assertEqual(after['kitchen.local.yaml'], before['kitchen.local.yaml'])
        self.assertEqual(self.firmware.follow_release(), [], 'a second start has nothing to do')

    def test_every_build_of_the_stable_app_takes_its_tag(self):
        path = self.write(SCREEN)
        self.firmware.run = lambda *args: asyncio.sleep(0)
        set_channel('main')
        core.set_version('0.4.85')
        async def build():
            self.firmware.start({'file': path.name, 'action': 'build'})
            await self.firmware.task
        with unittest.mock.patch('shutil.which', return_value='/usr/bin/esphome'):
            asyncio.run(build())
        self.assertEqual(load(path.read_text())['packages']['display']['ref'], 'screens-v0.4.85')

    def test_a_publish_pushes_main_and_its_tag_together(self):
        source = (ROOT / 'tools/release.py').read_text()
        self.assertIn("git('push', '--quiet', '--atomic', 'origin', f'{head}:refs/heads/{RELEASES}', f'refs/tags/{tag}')", source)
        self.assertNotIn("git('push', '--quiet', 'origin', f'refs/tags/{tag}')", source, 'never the tag on its own')


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
            await m.build_queue.idle()
            self.assertEqual(m.firmware.calls, [{'file': 'living-room.yaml', 'action': 'install', 'target': '10.0.0.5'}])
            self.assertEqual(m.updates.results['text.screen1']['state'], 'success')


class ReinstallAll(unittest.IsolatedAsyncioTestCase):
    """Reinstall all from dev (Settings, Updates, on the dev app): every screen again with the newest dev, as one round."""

    def tearDown(self):
        set_channel(None)

    async def test_every_screen_again_on_dev_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = test_updates.UpdaterTests.setup_manager(self, tmp)
            m.updates.hosts['text.screen2'] = '10.0.0.6'
            m.ha.states.update({'text.fw1': {'state': core.FIRMWARE_VERSION}, 'text.fw2': {'state': core.FIRMWARE_VERSION}})
            self.assertNotIn('reinstallable', m.updates.summary())
            with self.assertRaisesRegex(ValueError, 'dev channel'):
                m.updates.start_all(reinstall=True)
            set_channel('dev')
            self.assertEqual(m.updates.summary()['reinstallable'], 2)
            # Nothing is an update (the same number), so Update all has nothing; Reinstall all takes both.
            with self.assertRaises(ValueError):
                m.updates.start_all()
            self.assertEqual(m.updates.start_all(reinstall=True), ['text.screen1', 'text.screen2'])
            self.assertEqual(m.updates.summary()['reinstallable'], 0, 'what is on its way is not counted again')
            with self.assertRaisesRegex(ValueError, 'No screen can be reinstalled'):
                m.updates.start_all(reinstall=True)
            await m.build_queue.idle()
            self.assertEqual([c['file'] for c in m.firmware.calls], ['living-room.yaml', 'kitchen.yaml'])
            self.assertEqual(m.updates.summary()['reinstallable'], 2)


class AskedDuringTheNight(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        set_channel(None)

    async def test_reinstall_from_dev_of_a_screen_in_the_failing_round_still_builds(self):
        """Found on the bench: the nightly round on the dev app stopped at a screen whose build failed, and Reinstall from
        dev of a screen later in that round, asked while it waited, was left out with the round."""
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as tmp:
            set_channel('dev')
            m = test_updates.UpdaterTests.setup_manager(self, tmp, outcome='failed')
            m.updates.hosts['text.screen2'] = '10.0.0.6'
            m.updates.set_auto(True)
            gate = asyncio.Event()
            original = m.firmware.run

            async def held(data):
                await gate.wait()
                if data['file'] == 'kitchen.yaml':
                    m.firmware.outcome = 'success'
                await original(data)
            m.firmware.run = held
            round = m.updates.look(datetime(2026, 10, 14, 3, 30, tzinfo=timezone.utc))
            self.assertEqual([b.screen for b in round.builds], ['text.screen1', 'text.screen2'])
            self.assertEqual(m.updates.start('text.screen2', reinstall=True)['state'], 'queued')
            gate.set()
            await m.build_queue.idle()
            self.assertEqual([c['file'] for c in m.firmware.calls], ['living-room.yaml', 'kitchen.yaml'])
            self.assertEqual((m.updates.results['text.screen1']['state'], m.updates.results['text.screen2']['state']), ('failed', 'success'))


class NightOnDev(unittest.IsolatedAsyncioTestCase):
    """Automatic updates at night on the dev channel (docs/RELEASING.md, "Testing dev"): the firmware number stays the
    same from one dev to the next, so a screen on it is left alone every night instead of being built again and again;
    a screen behind it (a release raised the number) gets its update, in the build line with whatever else waits."""

    def tearDown(self):
        set_channel(None)

    async def test_the_nightly_round_on_dev(self):
        from datetime import datetime, timezone
        night = datetime(2026, 10, 14, 3, 30, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            set_channel('dev')
            m = test_updates.UpdaterTests.setup_manager(self, tmp)
            m.updates.hosts['text.screen2'] = '10.0.0.6'
            m.updates.set_auto(True)
            # Living room runs the dev's number; Kitchen is behind it (a release came to dev after it was built).
            m.ha.states['text.fw1'] = {'state': core.FIRMWARE_VERSION}
            self.assertIsNone(m.updates.look(night.replace(hour=14)), 'not in the day')
            gate = asyncio.Event()
            original = m.firmware.run

            async def held(data):
                await gate.wait()
                await original(data)
            m.firmware.run = held
            round = m.updates.look(night)
            self.assertEqual([b.screen for b in round.builds], ['text.screen2'])
            # Reinstall from dev asked while the round builds waits its turn; asked again, it stays one build.
            m.updates.start('text.screen1', reinstall=True)
            m.updates.start('text.screen1', reinstall=True)
            self.assertEqual(m.updates.queue, ['text.screen1'])
            # The next minute of the same night starts nothing more, while it runs and after.
            self.assertIsNone(m.updates.look(night.replace(minute=31)))
            gate.set()
            await m.build_queue.idle()
            self.assertEqual([c['file'] for c in m.firmware.calls], ['kitchen.yaml', 'living-room.yaml'])
            self.assertEqual({k: v['state'] for k, v in m.updates.results.items()}, {'text.screen1': 'success', 'text.screen2': 'success'})
            # The next night every screen is on the dev's number: nothing is built again.
            self.assertIsNone(m.updates.look(night.replace(day=15)))
            self.assertEqual(len(m.firmware.calls), 2)
            self.assertEqual(m.updates.last_round, '2026-10-15')


if __name__ == '__main__':
    unittest.main()
