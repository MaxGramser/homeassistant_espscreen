"""Download: ESP Screens builds a screen's firmware and the owner flashes the file from their own computer."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from firmware import Firmware  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app
    from test_screen_owned_settings import fake_ha

PROFILE = {'board': 'cyd', 'name': 'kitchen', 'friendly_name': 'Kitchen', 'wifi_ssid': 'ssid', 'wifi_password': 'password'}

# Stands in for the ESPHome CLI: it logs, and `compile` writes the factory image where ESPHome 2026.6 puts it
# (PlatformIO: <build>/<node>/.pioenvs/<node>/, native ESP-IDF: <build>/<node>/build/). FAKE_LAYOUT=none writes
# nothing, FAKE_EXIT makes it fail, FAKE_SLEEP keeps it busy.
FAKE_CLI = '''#!{python}
import os, sys, time
from pathlib import Path
stage, profile = [arg for arg in sys.argv[1:] if arg != '--quiet'][:2]
profile = Path(profile)
print('INFO Reading configuration ' + profile.name, flush=True)
time.sleep(float(os.environ.get('FAKE_SLEEP', '0')))
if os.environ.get('FAKE_EXIT'):
    print('ERROR Compiling ' + profile.stem + ' failed', flush=True)
    sys.exit(int(os.environ['FAKE_EXIT']))
if stage == 'compile':
    build = Path(os.environ['ESPHOME_BUILD_PATH']) / profile.stem
    folder = {{'pio': build / '.pioenvs' / profile.stem, 'idf': build / 'build'}}.get(os.environ.get('FAKE_LAYOUT', 'pio'))
    if folder:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'firmware.bin').write_bytes(b'app')
        (folder / 'firmware.factory.bin').write_bytes(b'\\xe9factory-' + profile.stem.encode())
print('INFO Successfully compiled program.', flush=True)
'''


def fake_cli(folder):
    """The environment that finds the stand-in `esphome` before any real one."""
    bin_dir = Path(folder) / 'bin'
    bin_dir.mkdir(exist_ok=True)
    cli = bin_dir / 'esphome'
    cli.write_text(FAKE_CLI.format(python=sys.executable))
    cli.chmod(0o755)
    return {'PATH': f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}


class DownloadChecks(unittest.TestCase):
    def test_the_download_target_is_checked_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            with patch('firmware.shutil.which', return_value=None):
                with self.assertRaisesRegex(ValueError, 'ESPHome CLI is missing'):
                    f.install({**PROFILE, 'target': 'download'})
            with patch('firmware.shutil.which', return_value='/usr/bin/esphome'):
                f.task = Mock(done=lambda: False)
                with self.assertRaisesRegex(ValueError, 'already running'):
                    f.install({**PROFILE, 'target': 'download'})
                f.task = None
                for target in ('downloads', ['download'], '/dev/ttyUSB0'):
                    with self.assertRaisesRegex(ValueError, 'USB port'):
                        f.install({**PROFILE, 'target': target})
            self.assertFalse((Path(tmp) / 'esphome' / 'kitchen.yaml').exists())
            self.assertFalse((Path(tmp) / 'esphome' / 'secrets.yaml').exists())

    def test_only_a_profile_built_by_this_app_is_served(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            f.create(PROFILE)
            for name in ('../secrets.yaml', 'secrets', 'kitchen.local.yaml', 'missing.yaml', None):
                with self.assertRaises(ValueError):
                    f.image(name)
            # A factory image left in the build folder, from before this app started, is not offered.
            old = Path(tmp) / 'data' / 'build' / 'kitchen' / 'kitchen' / '.pioenvs' / 'kitchen' / 'firmware.factory.bin'
            old.parent.mkdir(parents=True)
            old.write_bytes(b'old')
            with self.assertRaisesRegex(ValueError, 'Build the firmware first'):
                f.image('kitchen.yaml')
            self.assertEqual(f.downloaded, set())
            self.assertEqual(f.status()['downloads'], [])

    def test_the_newest_image_wins_when_the_node_was_renamed(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            profile = f.profile(f.create(PROFILE)['file'])
            build = Path(tmp) / 'data' / 'build' / 'kitchen'
            images = []
            for node, when in (('old-name', 1_000_000), ('kitchen', 2_000_000)):
                image = build / node / '.pioenvs' / node / 'firmware.factory.bin'
                image.parent.mkdir(parents=True)
                image.write_bytes(node.encode())
                os.utime(image, (when, when))
                images.append(image)
            # A link is never served, even when it points at something newer.
            outside = Path(tmp) / 'elsewhere.bin'
            outside.write_bytes(b'not ours')
            os.utime(outside, (3_000_000, 3_000_000))
            link = build / 'linked' / 'build' / 'firmware.factory.bin'
            link.parent.mkdir(parents=True)
            link.symlink_to(outside)
            self.assertEqual(f.factory_image(profile), images[1])


class BoardChips(unittest.TestCase):
    def test_every_board_names_the_chip_its_firmware_is_built_for(self):
        # The browser flasher refuses a board of another chip; the P4 boards' Wi-Fi co-processor (an ESP32-C6 under
        # esp32_hosted) is not the chip the image is for.
        from core import BOARD_KEYS, SHAPES
        chips = {board: SHAPES[board].get('chip') for board in BOARD_KEYS}
        self.assertTrue(set(chips.values()) <= {'ESP32', 'ESP32-S3', 'ESP32-P4'}, chips)
        self.assertEqual((chips['cyd'], chips['guition'], chips['jc8012p4a1']), ('ESP32', 'ESP32-S3', 'ESP32-P4'))


class DownloadJobs(unittest.IsolatedAsyncioTestCase):
    async def test_the_download_target_builds_and_offers_the_factory_image(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, fake_cli(tmp)):
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            result = f.install({**PROFILE, 'target': 'download'})
            self.assertEqual((result['file'], result['job']['action'], result['job']['state']), ('kitchen.yaml', 'download', 'running'))
            self.assertEqual(len(result['api_key']), 44, 'the page still shows the key for pairing')
            with self.assertRaisesRegex(ValueError, 'still being built'):
                f.image('kitchen.yaml')
            await f.task
            self.assertEqual(f.job['state'], 'success', list(f.logs))
            self.assertIn('ESPHome: compile', f.logs)
            self.assertNotIn('ESPHome: upload', f.logs, 'nothing is flashed from Home Assistant')
            self.assertEqual(f.status()['downloads'], ['kitchen.yaml'])
            path, name = f.image('kitchen.yaml')
            self.assertEqual((name, path.read_bytes()), ('kitchen.factory.bin', b'\xe9factory-kitchen'))
            self.assertEqual((f.installed, f.downloaded), (set(), {'kitchen.yaml'}))

    async def test_a_screen_flashed_from_the_browser_counts_as_installed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, fake_cli(tmp)):
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            f.install({**PROFILE, 'target': 'download'})
            with self.assertRaisesRegex(ValueError, 'Build the firmware first'):
                f.flashed('kitchen.yaml')
            await f.task
            with self.assertRaisesRegex(ValueError, 'Build the firmware first'):
                f.flashed('kitchen.yaml')  # built, but the page never fetched the image
            f.image('kitchen.yaml')
            for name in ('../secrets.yaml', 'missing.yaml', None):
                with self.assertRaises(ValueError):
                    f.flashed(name)
            self.assertEqual(f.flashed('kitchen.yaml'), {'file': 'kitchen.yaml', 'installed': True})
            self.assertEqual((f.installed, f.downloaded), ({'kitchen.yaml'}, set()))

    async def test_the_status_names_the_chip_each_profile_is_built_for(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            f.create(PROFILE)
            f.create({**PROFILE, 'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall'})
            (Path(tmp) / 'esphome' / 'other.yaml').write_text('esphome:\n  name: other\n')
            status = f.status()
            self.assertEqual(status['profiles'], [{'file': 'hall.yaml', 'chip': 'ESP32-S3'},
                                                  {'file': 'kitchen.yaml', 'chip': 'ESP32'}, {'file': 'other.yaml'}])
            self.assertEqual({key: board['chip'] for key, board in status['boards'].items()}.get('cyd'), 'ESP32')

    async def test_a_build_without_a_factory_image_fails_instead_of_offering_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {**fake_cli(tmp), 'FAKE_LAYOUT': 'none'}):
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            f.install({**PROFILE, 'target': 'download'})
            await f.task
            self.assertEqual(f.job['state'], 'failed')
            self.assertIn('no factory image', f.logs[-1])
            self.assertEqual(f.status()['downloads'], [])
            with self.assertRaisesRegex(ValueError, 'Build the firmware first'):
                f.image('kitchen.yaml')

    async def test_the_native_esp_idf_layout_is_found_too(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {**fake_cli(tmp), 'FAKE_LAYOUT': 'idf'}):
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            f.install({**PROFILE, 'target': 'download'})
            await f.task
            path, _ = f.image('kitchen.yaml')
            self.assertEqual(path.parent.name, 'build')

    async def test_a_new_build_withdraws_the_old_file_until_it_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, fake_cli(tmp)):
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            f.install({**PROFILE, 'target': 'download'})
            await f.task
            path, _ = f.image('kitchen.yaml')
            with patch.dict(os.environ, {'FAKE_EXIT': '1'}):
                f.start({'file': 'kitchen.yaml', 'action': 'build'})
                with self.assertRaisesRegex(ValueError, 'still being built'):
                    f.image('kitchen.yaml')
                await f.task
            self.assertEqual(f.job['state'], 'failed')
            self.assertTrue(path.exists(), 'the old file is still on disk')
            with self.assertRaisesRegex(ValueError, 'Build the firmware first'):
                f.image('kitchen.yaml')

    async def test_build_only_offers_the_file_and_a_check_does_not(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, fake_cli(tmp)):
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            f.create(PROFILE)
            f.start({'file': 'kitchen.yaml', 'action': 'validate'})
            await f.task
            self.assertEqual((f.job['state'], f.status()['downloads']), ('success', []))
            f.start({'file': 'kitchen.yaml', 'action': 'build'})
            await f.task
            self.assertEqual((f.job['state'], f.status()['downloads']), ('success', ['kitchen.yaml']))
            with self.assertRaisesRegex(ValueError, 'Unknown firmware action'):
                f.start({'file': 'kitchen.yaml', 'action': 'flash'})
            self.assertEqual(f.status()['downloads'], ['kitchen.yaml'], 'a refused job keeps the file')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class DownloadRoute(unittest.IsolatedAsyncioTestCase):
    async def test_the_page_downloads_the_built_file_and_the_card_says_so(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {**fake_cli(tmp), 'FAKE_SLEEP': '0.3',
                                                                           'ESPHOME_CONFIG': str(Path(tmp) / 'esphome')}):
            m = Manager(fake_ha(), Path(tmp) / 'screens.json')
            async with TestClient(TestServer(create_app(m, True))) as client:
                inventory = await (await client.get('/api/inventory')).json()
                headers = {'X-Screen-CSRF': inventory['csrf']}
                refused = await client.post('/api/firmware/profiles', json={**PROFILE, 'target': 'download'})
                self.assertEqual(refused.status, 403, 'CSRF like every other change')
                response = await client.post('/api/firmware/profiles', headers=headers, json={**PROFILE, 'target': 'download'})
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())['job']['action'], 'download')
                url = '/api/firmware/profiles/kitchen.yaml/download'
                early = await client.get(url)
                self.assertEqual(early.status, 400)
                self.assertIn('still being built', (await early.json())['error'])
                await m.firmware.task
                self.assertEqual((await (await client.get('/api/firmware')).json())['downloads'], ['kitchen.yaml'])
                pending = (await (await client.get('/api/inventory?light=1')).json())['pending']
                self.assertEqual([(p['file'], p['installed'], p['downloaded']) for p in pending], [('kitchen.yaml', False, False)])
                download = await client.get(url)
                self.assertEqual(download.status, 200)
                self.assertEqual(download.headers['Content-Type'], 'application/octet-stream')
                self.assertEqual(download.headers['Content-Disposition'], 'attachment; filename="kitchen.factory.bin"')
                self.assertEqual(download.headers['Cache-Control'], 'no-store', 'the file holds the Wi-Fi password')
                self.assertEqual(await download.read(), b'\xe9factory-kitchen')
                pending = (await (await client.get('/api/inventory?light=1')).json())['pending']
                self.assertEqual([(p['file'], p['installed'], p['downloaded']) for p in pending], [('kitchen.yaml', False, True)])
                flashed = '/api/firmware/profiles/kitchen.yaml/flashed'
                self.assertEqual((await client.post(flashed)).status, 403, 'CSRF like every other change')
                self.assertEqual((await client.post(flashed, headers=headers)).status, 200)
                pending = (await (await client.get('/api/inventory?light=1')).json())['pending']
                self.assertEqual([(p['file'], p['installed'], p['downloaded']) for p in pending], [('kitchen.yaml', True, False)])
                self.assertEqual((await client.post('/api/firmware/profiles/other.yaml/flashed', headers=headers)).status, 400)
                self.assertEqual((await client.get('/api/firmware/profiles/other.yaml/download')).status, 400)
                self.assertNotEqual((await client.get('/api/firmware/profiles/..%2Fsecrets.yaml/download')).status, 200)


if __name__ == '__main__':
    unittest.main()
