"""Download: ESP Screens builds a screen's firmware and the owner flashes the file from their own computer."""
import importlib.util
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
import zipfile
import yaml

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
# (PlatformIO: <build>/<node>/.pioenvs/<node>/, native ESP-IDF: <build>/<node>/build/). Its switches are in the ESPHOME_
# family, the one a build passes on (firmware.build_environment). ESPHOME_FAKE_LAYOUT=none writes
# nothing, ESPHOME_FAKE_EXIT makes it fail, ESPHOME_FAKE_SLEEP keeps it busy.
FAKE_CLI = '''#!{python}
import os, sys, time
from pathlib import Path
stage, profile = [arg for arg in sys.argv[1:] if arg != '--quiet'][:2]
profile = Path(profile)
# The real CLI reads esphome.name, not the private input root's basename.
profile = Path(os.environ['ESPHOME_BUILD_PATH']).with_suffix('.yaml')
print('INFO Reading configuration ' + profile.name, flush=True)
time.sleep(float(os.environ.get('ESPHOME_FAKE_SLEEP', '0')))
if os.environ.get('ESPHOME_FAKE_EXIT'):
    print('ERROR Compiling ' + profile.stem + ' failed', flush=True)
    sys.exit(int(os.environ['ESPHOME_FAKE_EXIT']))
if stage == 'compile':
    build = Path(os.environ['ESPHOME_BUILD_PATH']) / profile.stem
    folder = {{'pio': build / '.pioenvs' / profile.stem, 'idf': build / 'build'}}.get(os.environ.get('ESPHOME_FAKE_LAYOUT', 'pio'))
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
    # No compile cache from GitHub before these builds (build_cache, app 0.4.49): tests stay off the network.
    return {'PATH': f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", 'ESP_SCREENS_BUILD_CACHE': 'off'}


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



class ManagedModelFiles(unittest.TestCase):
    def setup_firmware(self, tmp):
        firmware = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
        firmware.create(PROFILE)
        return firmware

    @staticmethod
    def sidecar(models=None):
        return yaml.safe_dump({'packages': {}, 'micro_wake_word': {
            'id': 'va_wake', 'models': models or []}})

    def test_sidecar_accepts_only_bounded_generated_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.setup_firmware(tmp)
            model = {'id': 'ww_one', 'model': '.tessera-models/' + 'a' * 64 + '/manifest.json'}
            self.assertEqual(f.preflight_plugins('kitchen.yaml', self.sidecar([model]))['micro_wake_word']['models'], [model])
            bad_models = [
                [model, model],
                [{'id': 'ww_other', 'model': '../private/manifest.json'}],
                [{'id': '!bad', 'model': model['model']}],
                [{**model, 'extra': True}],
                [{'id': f'ww_{i}', 'model': f'.tessera-models/{i:064x}/manifest.json'} for i in range(17)],
            ]
            before = f.profile('kitchen.yaml').read_bytes()
            for models in bad_models:
                with self.subTest(models=models), self.assertRaises(ValueError):
                    f.save_plugins('kitchen.yaml', self.sidecar(models))
            self.assertEqual(f.profile('kitchen.yaml').read_bytes(), before)
            self.assertFalse((f.root / 'kitchen.plugins.yaml').exists())

    def test_recursive_owner_conflicts_and_unknown_remote_fail_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.setup_firmware(tmp)
            profile = f.profile('kitchen.yaml')
            original = profile.read_text()
            for content in ('micro_wake_word:\n  models: []\n',
                            'micro_wake_word:\n  vad: {}\n',
                            'micro_wake_word:\n  id: owner_wake\n',
                            'packages:\n  inline:\n    micro_wake_word:\n      models: []\n'):
                (f.root / 'nested.yaml').write_text(content + 'password: never-print-this\n')
                (f.root / 'kitchen.local.yaml').write_text('packages:\n  nested: !include nested.yaml\n')
                with self.assertRaises(ValueError) as error:
                    f.save_plugins('kitchen.yaml', self.sidecar())
                self.assertIn('nested.yaml', str(error.exception))
                self.assertIn('micro_wake_word', str(error.exception))
                self.assertNotIn('never-print-this', str(error.exception))
                self.assertEqual(profile.read_text(), original)
                self.assertFalse((f.root / 'kitchen.plugins.yaml').exists())
            (f.root / 'kitchen.local.yaml').write_text('{}\n')
            profile.write_text(original.replace('packages:\n', 'packages:\n  owner:\n    url: https://example.com/unknown\n', 1))
            with self.assertRaisesRegex(ValueError, 'packages.owner'):
                f.preflight_plugins('kitchen.yaml', self.sidecar())

    def test_merged_owned_fields_in_profile_and_override_are_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.setup_firmware(tmp)
            f.save_plugins('kitchen.yaml', self.sidecar())
            profile = f.profile('kitchen.yaml')
            override = f.root / 'kitchen.local.yaml'
            sidecar = f.root / 'kitchen.plugins.yaml'
            original_profile, original_override, original_sidecar = (
                profile.read_bytes(), override.read_bytes(), sidecar.read_bytes())
            for field, value in (('models', '[]'), ('vad', '{}'), ('id', 'owner_wake')):
                mapping = f'{{{field}: {value}}}'
                examples = [
                    f'micro_wake_word:\n  <<: {mapping}\n',
                    f'<<:\n  micro_wake_word: {mapping}\n',
                    f'micro_wake_word:\n  <<: [{mapping}, {{stop_after_detection: false}}]\n',
                    f'micro_wake_word:\n  <<: [&defaults {mapping}, {{<<: *defaults}}]\n',
                ]
                for content in examples:
                    with self.subTest(field=field, content=content):
                        profile.write_bytes(original_profile + content.encode())
                        before = profile.read_bytes()
                        with self.assertRaisesRegex(ValueError, 'micro_wake_word.' + field):
                            f.save_plugins('kitchen.yaml', self.sidecar())
                        self.assertEqual(profile.read_bytes(), before)
                        self.assertEqual(sidecar.read_bytes(), original_sidecar)
                        profile.write_bytes(original_profile)
                        with self.assertRaisesRegex(ValueError, 'micro_wake_word.' + field):
                            f.save_override('kitchen.yaml', content)
                        self.assertEqual(override.read_bytes(), original_override)
                        self.assertEqual(profile.read_bytes(), original_profile)
                        self.assertEqual(sidecar.read_bytes(), original_sidecar)

    def test_yaml_merge_precedence_and_alias_cycles_remain_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.setup_firmware(tmp)
            f.save_plugins('kitchen.yaml', self.sidecar())
            # Explicit fields override merges, and the first mapping of a merge sequence wins.
            f.save_override('kitchen.yaml', 'micro_wake_word:\n  <<: {id: owner_wake}\n  id: va_wake\n')
            f.save_override('kitchen.yaml', 'micro_wake_word:\n  <<: [{id: va_wake}, {id: owner_wake}]\n')
            before = (f.root / 'kitchen.local.yaml').read_bytes()
            cycles = [
                'micro_wake_word: &wake\n  <<: *wake\n',
                'micro_wake_word:\n  <<: &merges [{<<: *merges}]\n',
                'owner: &owner [*owner]\n',
            ]
            profile = f.profile('kitchen.yaml')
            original = profile.read_bytes()
            for content in cycles:
                with self.subTest(content=content):
                    profile.write_bytes(original + content.encode())
                    with self.assertRaises(ValueError):
                        f.preflight_plugins('kitchen.yaml', self.sidecar())
                    profile.write_bytes(original)
                    with self.assertRaises(ValueError):
                        f.save_override('kitchen.yaml', content)
                    self.assertEqual((f.root / 'kitchen.local.yaml').read_bytes(), before)

    def test_include_cycle_symlink_and_override_rejection_preserve_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.setup_firmware(tmp)
            override = f.root / 'kitchen.local.yaml'
            override.write_text('packages:\n  cycle: !include kitchen.local.yaml\n')
            with self.assertRaisesRegex(ValueError, 'cycle'):
                f.preflight_plugins('kitchen.yaml', self.sidecar())
            outside = Path(tmp) / 'private.yaml'
            outside.write_text('micro_wake_word:\n  models: []\n')
            (f.root / 'nested.yaml').symlink_to(outside)
            override.write_text('packages:\n  nested: !include nested.yaml\n')
            with self.assertRaises(ValueError):
                f.preflight_plugins('kitchen.yaml', self.sidecar())
            override.write_text('{}\n')
            f.save_plugins('kitchen.yaml', self.sidecar())
            before = override.read_bytes()
            with self.assertRaisesRegex(ValueError, 'micro_wake_word.models'):
                f.save_override('kitchen.yaml', 'micro_wake_word:\n  models: []\n')
            self.assertEqual(override.read_bytes(), before)
            f.save_override('kitchen.yaml', 'micro_wake_word:\n  id: va_wake\n  stop_after_detection: false\n')

    def test_conflicting_managed_include_does_not_replace_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.setup_firmware(tmp)
            profile = f.profile('kitchen.yaml')
            profile.write_text(profile.read_text().replace('packages:\n', 'packages:\n  tessera_plugins: !include owner.yaml\n', 1))
            sidecar = f.root / 'kitchen.plugins.yaml'
            sidecar.write_text('packages: {}\n')
            with self.assertRaises(ValueError):
                f.save_plugins('kitchen.yaml', self.sidecar())
            self.assertEqual(sidecar.read_text(), 'packages: {}\n')

    def test_zip_exports_only_referenced_verified_portable_snapshots(self):
        from plugin_models import snapshot_files
        from test_plugin_models import manifest
        with tempfile.TemporaryDirectory() as tmp:
            f = self.setup_firmware(tmp)
            source = json.dumps(manifest(word='Test', model='https://example.com/model.tflite')).encode()
            binary = b'\x08\x00\x00\x00TFL3' + b'\x00' * 16
            digest = hashlib.sha256(len(source).to_bytes(8, 'big') + source
                                    + len(binary).to_bytes(8, 'big') + binary).hexdigest()
            directory = f.root / '.tessera-models' / digest
            directory.mkdir(parents=True)
            (directory / 'source.json').write_bytes(source)
            runnable = json.loads(source)
            runnable['model'] = 'model.tflite'
            (directory / 'manifest.json').write_text(json.dumps(runnable, sort_keys=True, separators=(',', ':')) + '\n')
            (directory / 'model.tflite').write_bytes(binary)
            expected = snapshot_files(f.root, [{'snapshot': digest}])
            (f.root / '.tessera-models' / 'unreferenced').mkdir()
            (f.root / '.tessera-models' / 'unreferenced' / 'private').write_text('not exported')
            f.save_plugins('kitchen.yaml', self.sidecar([{'id': 'ww_one', 'model': f'.tessera-models/{digest}/manifest.json'}]))
            data, _ = f.files('kitchen.yaml')
            with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                names = set(bundle.namelist())
                self.assertFalse(any('unreferenced' in name for name in names))
                for path, content in expected.items():
                    self.assertEqual(bundle.read('kitchen/' + path), content)
            (directory / 'model.tflite').unlink()
            (directory / 'model.tflite').symlink_to(f.root / 'secrets.yaml')
            with self.assertRaises(ValueError):
                f.files('kitchen.yaml')

class BoardChips(unittest.TestCase):
    def test_every_board_names_the_chip_its_firmware_is_built_for(self):
        # The browser flasher refuses a board of another chip; the P4 boards' Wi-Fi co-processor (an ESP32-C6 under
        # esp32_hosted) is not the chip the image is for.
        from core import BOARD_KEYS, SHAPES
        chips = {board: SHAPES[board].get('chip') for board in BOARD_KEYS}
        self.assertTrue(set(chips.values()) <= {'ESP32', 'ESP32-S3', 'ESP32-P4'}, chips)
        self.assertEqual((chips['cyd'], chips['guition'], chips['jc8012p4a1']), ('ESP32', 'ESP32-S3', 'ESP32-P4'))


class DownloadJobs(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_before_the_first_instruction_also_removes_private_inputs(self):
        with tempfile.TemporaryDirectory() as tmp, patch('firmware.shutil.which', return_value='/bin/esphome'):
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            f.create(PROFILE)
            f.start({'file': 'kitchen.yaml', 'action': 'build'})
            paths = list(f.root.glob('.tessera-*.plugins.yaml'))
            self.assertTrue(paths)
            f.task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await f.task
            self.assertEqual(f.job['state'], 'interrupted')
            self.assertTrue(all(not path.exists() for path in paths))

    async def test_private_input_is_hidden_and_removed_for_direct_job_outcomes(self):
        for outcome in ('success', 'failed', 'interrupted'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp, patch('firmware.shutil.which', return_value='/bin/esphome'):
                f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
                f.create(PROFILE)
                f.save_plugins('kitchen.yaml', ManagedModelFiles.sidecar())
                f.retire_platformio = AsyncMock()
                f.seed_cache = AsyncMock()
                captured = []
                async def cli(stage, cmd, env):
                    path = Path(next(arg for arg in cmd if str(arg).endswith('.yaml')))
                    captured.extend(f.root.glob('.tessera-*.plugins.yaml'))
                    self.assertEqual(f.profiles(), [{'file': 'kitchen.yaml'}])
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                    with self.assertRaises(ValueError):
                        f.profile(path.name)
                    node = yaml.compose(path.read_text())
                    esphome = next(value for key, value in node.value if key.value == 'esphome')
                    self.assertTrue(esphome.value, 'preserve the original device configuration')
                    self.assertEqual(env['ESPHOME_BUILD_PATH'], str(f.data / 'build' / 'kitchen'))
                    if outcome == 'interrupted':
                        raise asyncio.CancelledError()
                    return (int(outcome == 'failed'), False)
                f.esphome = cli
                f.start({'file': 'kitchen.yaml', 'action': 'build'})
                if outcome == 'interrupted':
                    with self.assertRaises(asyncio.CancelledError):
                        await f.task
                else:
                    await f.task
                self.assertEqual(f.job['state'], outcome)
                self.assertEqual(len(captured), 2)
                self.assertTrue(all(not path.exists() for path in captured))

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
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {**fake_cli(tmp), 'ESPHOME_FAKE_LAYOUT': 'none'}):
            f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
            f.install({**PROFILE, 'target': 'download'})
            await f.task
            self.assertEqual(f.job['state'], 'failed')
            self.assertIn('no factory image', f.logs[-1])
            self.assertEqual(f.status()['downloads'], [])
            with self.assertRaisesRegex(ValueError, 'Build the firmware first'):
                f.image('kitchen.yaml')

    async def test_the_native_esp_idf_layout_is_found_too(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {**fake_cli(tmp), 'ESPHOME_FAKE_LAYOUT': 'idf'}):
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
            with patch.dict(os.environ, {'ESPHOME_FAKE_EXIT': '1'}):
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
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {**fake_cli(tmp), 'ESPHOME_FAKE_SLEEP': '0.3',
                                                                           'ESPHOME_CONFIG': str(Path(tmp) / 'esphome')}):
            m = Manager(fake_ha(), Path(tmp) / 'screens.json')
            async with TestClient(TestServer(create_app(m, True))) as client:
                inventory = await (await client.get('/api/inventory')).json()
                headers = {'X-Screen-CSRF': inventory['csrf']}
                refused = await client.post('/api/firmware/profiles', json={**PROFILE, 'target': 'download'})
                self.assertEqual(refused.status, 403, 'CSRF like every other change')
                response = await client.post('/api/firmware/profiles', headers=headers, json={**PROFILE, 'target': 'download'})
                self.assertEqual(response.status, 200)
                build = (await response.json())['build']
                self.assertEqual((build['action'], build['by'], build['state']), ('download', 'install', 'running'))
                url = '/api/firmware/profiles/kitchen.yaml/download'
                early = await client.get(url)
                self.assertEqual(early.status, 400)
                self.assertIn('still being built', (await early.json())['error'])
                await m.build_queue.idle()
                ended = (await (await client.get('/api/inventory?light=1')).json())['line']
                self.assertEqual([(b['id'], b['state']) for b in ended], [(build['id'], 'success')])
                log = await (await client.get(f"/api/firmware/builds/{build['id']}/log")).json()
                self.assertIn('Succeeded: download', log['logs'])
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
