"""Builds on a build server (build_server.py, docs/BUILDS.md "On a build server"): pairing, the link, a build sent and
fetched back, every way it falls back to a build here, and how Firmware uses what came back. A small receiver in this
file speaks the server's side of Device Builder's peer link (Noise XX, then encrypted JSON frames)."""
import asyncio
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))

HAS_DEPS = all(importlib.util.find_spec(name) is not None for name in ('aiohttp', 'noise', 'yaml'))

if HAS_DEPS:
    from aiohttp import web
    from noise.connection import Keypair, NoiseConnection
    import build_server
    from build_server import BuildServer, Failed, Fallback, Refused


def tarball(files):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w:gz') as tar:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return out.getvalue()


ARTIFACTS = {'storage.json': json.dumps({'name': 'kitchen'}).encode(), 'idedata.json': b'{}',
             'build/firmware.factory.bin': b'F' * 3000, 'build/kitchen.bin': b'O' * 2000,
             'build/firmware.elf': b'E' * 5000, 'build/partition_table/partition-table.bin': b'P' * 3072}


class Receiver:
    """The server's side: one static key, pairing by a one-time key or by a person (`accept`), and builds whose outcome
    the test chooses (`outcome`: completed, failed, provision, drop)."""

    def __init__(self):
        self.private = bytes(range(1, 33))
        self.key, self.approved, self.pending = 'ABCD-EFGH-JKLM-NPQR', set(), set()
        self.window = True
        self.outcome, self.lines = 'completed', ['[1/2] Compiling', '\\033[32mINFO done\\033[0m']
        self.bundles, self.accept = [], asyncio.Event()
        self.version = '2026.9.1'
        self.targets = []
        self.jobs = []   # the target of each submitted job: compile, or clean first for a fresh build

    @property
    def pin(self):
        from noise.backends.default.keypairs import KeyPair25519
        return hashlib.sha256(bytes(KeyPair25519.from_private_bytes(self.private).public_bytes)).hexdigest()

    async def start(self):
        app = web.Application()
        app.router.add_get(build_server.PATH, self.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]

    async def close(self):
        await self.runner.cleanup()

    async def handle(self, request):
        ws = web.WebSocketResponse(max_msg_size=8 * 1024 * 1024)
        await ws.prepare(request)
        noise = NoiseConnection.from_name(build_server.PATTERN)
        noise.set_as_responder()
        noise.set_keypair_from_private_bytes(Keypair.STATIC, self.private)
        noise.start_handshake()
        state = noise.noise_protocol.handshake_state
        intent = json.loads(bytes(noise.read_message((await ws.receive()).data)))['intent']
        await ws.send_bytes(bytes(noise.write_message(b'')))
        third = await ws.receive()
        if not isinstance(third.data, bytes):   # the app went away after msg2: the key was not the one it checked
            return ws
        details = json.loads(bytes(noise.read_message(third.data)) or b'{}')
        peer = hashlib.sha256(bytes(state.rs.public_bytes)).hexdigest()

        async def answer(response, **extra):
            body = {'intent_response': response, 'esphome_version': self.version, 'friendly_name': 'Workshop PC',
                    'auto_provision_supported': True, **extra}
            await ws.send_bytes(bytes(noise.encrypt(json.dumps(body).encode())))
        if intent == 'preview':
            await answer('ok', requires_pairing_key=True)
        elif intent == 'pair_request':
            if details.get('pairing_key') == self.key:
                self.approved.add(peer)
                await answer('approved')
            elif not self.window:
                await answer('no_pairing_window')
            else:
                self.pending.add(peer)
                await answer('pending')
        elif intent == 'pair_status':
            await self.accept.wait()
            self.approved.add(peer)
            await answer('approved')
        elif intent == 'peer_link':
            if peer not in self.approved:
                await answer('rejected', reason='no_approved_peer')
            else:
                await answer('ok')
                await self.session(ws, noise)
        await ws.close()
        return ws

    async def session(self, ws, noise):
        async def send(frame):
            await ws.send_bytes(bytes(noise.encrypt(json.dumps(frame).encode())))
        await send({'type': 'queue_status', 'idle': True, 'running': False, 'queue_depth': 0})
        parts, header = [], None
        async for message in ws:
            frame = json.loads(bytes(noise.decrypt(message.data)))
            kind = frame['type']
            if kind == 'submit_job':
                header, parts = frame, []
                self.targets.append(frame.get('target_esphome_version'))
                self.jobs.append(frame.get('target'))
            elif kind == 'submit_job_chunk':
                parts.append(base64.b64decode(frame['data_b64']))
                if frame['is_last']:
                    bundle = b''.join(parts)
                    ok = hashlib.sha256(bundle).hexdigest() == header['bundle_sha256']
                    self.bundles.append(bundle)
                    await send({'type': 'submit_job_ack', 'job_id': header['job_id'], 'accepted': ok})
                    await send({'type': 'job_state_changed', 'job_id': header['job_id'], 'status': 'running', 'error_message': ''})
                    for line in self.lines:
                        await send({'type': 'job_output', 'job_id': header['job_id'], 'stream': 'stdout', 'line': line + '\n'})
                    if self.outcome == 'drop':
                        await ws.close()
                        return
                    status = {'completed': 'completed', 'failed': 'failed', 'provision': 'failed'}[self.outcome]
                    await send({'type': 'job_state_changed', 'job_id': header['job_id'], 'status': status,
                                'error_message': 'compile failed' if status == 'failed' else '',
                                **({'failure_reason': 'provision'} if self.outcome == 'provision' else {})})
            elif kind == 'download_artifacts':
                data = tarball(ARTIFACTS)
                chunks = [data[i:i + 1000] for i in range(0, len(data), 1000)]
                await send({'type': 'artifacts_start', 'job_id': frame['job_id'], 'total_bytes': len(data),
                            'num_chunks': len(chunks), 'artifacts_sha256': hashlib.sha256(data).hexdigest(),
                            'firmware_offset': '0x10000'})
                for index, chunk in enumerate(chunks):
                    await send({'type': 'artifacts_chunk', 'job_id': frame['job_id'], 'chunk_index': index,
                                'data_b64': base64.b64encode(chunk).decode(), 'is_last': index == len(chunks) - 1})
                await send({'type': 'artifacts_end', 'job_id': frame['job_id'], 'accepted': True})


@unittest.skipUnless(HAS_DEPS, 'needs aiohttp, noiseprotocol and PyYAML')
class BuildServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.data = Path(self.folder.name)
        self.receiver = Receiver()
        await self.receiver.start()
        self.server = BuildServer(self.data, version='2026.9.0')
        self.bundle_calls = []

        async def bundle(profile, root, env, log):
            self.bundle_calls.append(profile.name)
            return tarball({'manifest.json': b'{"manifest_version": 1}', profile.name: b'esphome: {}'})
        self.original_bundle = build_server.make_bundle
        build_server.make_bundle = bundle

    async def asyncTearDown(self):
        build_server.make_bundle = self.original_bundle
        await self.server.stop()
        await self.receiver.close()
        self.folder.cleanup()

    async def paired(self):
        await self.server.preview('127.0.0.1', self.receiver.port)
        await self.server.pair('127.0.0.1', self.receiver.port, self.receiver.key)
        for _ in range(100):
            if self.server.connection == 'online':
                return
            await asyncio.sleep(0.02)
        self.fail(f'not linked: {self.server.connection} {self.server.error}')

    async def build(self, logs=None, phases=None, text='esphome: {}', fresh=False):
        profile = self.data / 'kitchen.yaml'
        profile.write_text(text)
        logs, phases = (logs if logs is not None else []), (phases if phases is not None else [])
        return await self.server.compile(profile, self.data, self.data, {}, logs.append, phases.append, fresh)

    def test_the_fingerprint_is_the_seven_emoji_device_builder_shows(self):
        # As a headless Device Builder printed it for this pin.
        names = [name for _, name in build_server.fingerprint('4954658d9bc4952eac4abace0900e42c740c1fe43832884e5924467431a065f9')]
        self.assertEqual(names, ['Mushroom', 'Cloud', 'Cactus', 'Umbrella', 'Santa', 'Strawberry', 'Key'])

    async def test_preview_shows_the_server_and_its_fingerprint(self):
        found = await self.server.preview('127.0.0.1', self.receiver.port)
        self.assertEqual(found['pin'], self.receiver.pin)
        self.assertEqual((found['name'], found['esphome'], found['needs_key']), ('Workshop PC', '2026.9.1', True))
        self.assertEqual(len(found['emoji']), 7)

    async def test_a_server_that_does_not_answer_is_said_in_words(self):
        with self.assertRaises(Refused) as caught:
            await self.server.preview('127.0.0.1', 1)
        self.assertEqual(caught.exception.args[0], 'unreachable')
        with self.assertRaises(Refused):
            await self.server.preview('bad host/x')

    async def test_pairing_needs_the_preview_and_then_links_at_once_with_the_key(self):
        with self.assertRaises(Refused) as caught:
            await self.server.pair('127.0.0.1', self.receiver.port, self.receiver.key)
        self.assertEqual(caught.exception.args[0], 'preview_first')
        await self.paired()
        view = self.server.view()
        self.assertTrue(view['enabled'])
        self.assertEqual(view['server']['state'], 'paired')
        self.assertEqual(view['connection'], 'online')
        # Stored: a restarted app knows the server and its key, and keeps its own identity.
        again = BuildServer(self.data, version='2026.9.0')
        self.assertEqual(again.server['pin'], self.receiver.pin)
        self.assertEqual((again.id, again.pin), (self.server.id, self.server.pin))

    async def test_a_pairing_waits_for_the_person_to_accept_it_on_the_server(self):
        await self.server.preview('127.0.0.1', self.receiver.port)
        view = await self.server.pair('127.0.0.1', self.receiver.port)
        self.assertEqual(view['server']['state'], 'pending')
        self.assertFalse(view['enabled'])
        self.receiver.accept.set()
        for _ in range(100):
            if self.server.connection == 'online':
                break
            await asyncio.sleep(0.02)
        self.assertEqual(self.server.server['state'], 'paired')
        self.assertTrue(self.server.enabled)

    async def test_a_closed_pairing_window_is_said(self):
        self.receiver.window = False
        await self.server.preview('127.0.0.1', self.receiver.port)
        with self.assertRaises(Refused) as caught:
            await self.server.pair('127.0.0.1', self.receiver.port)
        self.assertEqual(caught.exception.args[0], 'no_window')

    async def test_a_server_with_another_key_than_the_one_checked_gets_nothing(self):
        await self.server.preview('127.0.0.1', self.receiver.port)
        self.receiver.private = bytes(range(2, 34))   # reinstalled, or someone else at that address
        with self.assertRaises(Refused) as caught:
            await self.server.pair('127.0.0.1', self.receiver.port, self.receiver.key)
        self.assertEqual(caught.exception.args[0], 'mismatch')
        self.assertFalse(self.receiver.approved)

    async def test_a_fresh_build_empties_the_server_folder_first(self):
        """A plugin part changed (screen camera's Video): the server runs `esphome clean` for the screen before the
        compile, so a component the earlier build left behind does not shadow the real one. A build that is not fresh
        sends one job, as before."""
        await self.paired()
        await self.build()
        self.assertEqual(self.receiver.jobs, ['compile'])
        logs = []
        images = await self.build(logs, text='esphome: {name: changed}', fresh=True)
        self.assertEqual(self.receiver.jobs, ['compile', 'clean', 'compile'])
        self.assertTrue(any('empties its build folder' in line for line in logs))
        self.assertEqual(images['ota'].read_bytes(), b'O' * 2000)

    async def test_a_build_goes_there_and_its_images_come_back_where_the_app_looks(self):
        await self.paired()
        logs, phases = [], []
        images = await self.build(logs, phases)
        self.assertEqual(phases, ['bundle', 'send', 'queued', 'build', 'fetch'])
        self.assertEqual(self.receiver.targets, ['2026.9.0'])   # the server builds with the app's ESPHome
        staged = self.data / 'build' / 'kitchen' / 'server'
        self.assertEqual(images['factory'], staged / 'build' / 'firmware.factory.bin')
        self.assertEqual(images['ota'].read_bytes(), b'O' * 2000)   # build/<node>.bin under the name the app reads
        self.assertEqual(images['ota'].name, 'firmware.ota.bin')
        self.assertEqual(images['table'].stat().st_size, 3072)
        self.assertFalse((staged / 'build' / 'firmware.elf').exists())   # the debug symbols stay on the server
        self.assertIn('INFO done', [line.strip() for line in logs])   # the colour codes, written out, are gone
        self.assertEqual(self.server.last['where'], 'server')
        self.assertIsNone(self.server.building)

    async def test_the_same_yaml_again_takes_the_build_just_made(self):
        # An update builds, then installs: the second asks the server nothing when the YAML did not change.
        await self.paired()
        first = await self.build()
        logs = []
        second = await self.build(logs)
        self.assertEqual(len(self.receiver.bundles), 1)
        self.assertEqual(first, second)
        self.assertTrue(any('the same as in the build' in line for line in logs))

    async def test_a_yaml_on_a_branch_builds_again_after_the_update_it_was_built_for(self):
        # The same `ref: dev` is another firmware after a push: the server fetches the branch, the bundle has the YAML.
        await self.paired()
        on_dev = 'packages:\n  display:\n    url: https://github.com/example/screens\n    ref: dev\n'
        await self.build(text=on_dev)
        await self.build(text=on_dev)   # the install of the same update
        self.assertEqual(len(self.receiver.bundles), 1)
        digest, images, pin, at = self.server.built['kitchen.yaml']
        self.server.built['kitchen.yaml'] = (digest, images, pin, at - build_server.REUSE_MOVING_SECONDS - 1)
        logs = []
        await self.build(logs, text=on_dev)   # a reinstall later
        self.assertEqual(len(self.receiver.bundles), 2)
        self.assertFalse(any('the same as in the build' in line for line in logs))
        # A release tag builds the same whenever.
        tagged = on_dev.replace('ref: dev', 'ref: screens-v0.57.0')
        digest, images, pin, at = self.server.built['kitchen.yaml']
        self.server.built['kitchen.yaml'] = (digest, images, pin, at - 3600)
        await self.build(text=tagged)
        self.assertEqual(len(self.receiver.bundles), 2)

    async def test_a_build_that_fails_on_the_server_fails(self):
        await self.paired()
        self.receiver.outcome = 'failed'
        with self.assertRaises(Failed):
            await self.build()

    async def test_a_server_that_cannot_install_the_esphome_falls_back(self):
        await self.paired()
        self.receiver.outcome = 'provision'
        with self.assertRaises(Fallback) as caught:
            await self.build()
        self.assertEqual(caught.exception.reason, 'provision')
        self.assertEqual(self.server.last['where'], 'here')

    async def test_a_link_that_drops_during_the_build_falls_back(self):
        await self.paired()
        self.receiver.outcome = 'drop'
        with self.assertRaises(Fallback) as caught:
            await self.build()
        self.assertEqual(caught.exception.reason, 'lost')

    async def test_off_or_away_the_build_falls_back(self):
        with self.assertRaises(Fallback) as caught:
            await self.build()
        self.assertEqual(caught.exception.reason, 'off')
        await self.paired()
        self.server.set_enabled(False)
        with self.assertRaises(Fallback):
            await self.build()
        self.server.set_enabled(True)
        # The server went away: the link is gone and the next try has not reached it.
        await self.server.stop()
        self.server.connection = 'offline'
        with self.assertRaises(Fallback) as caught:
            await self.build()
        self.assertEqual(caught.exception.reason, 'offline')

    async def test_a_server_that_forgot_the_app_says_pair_again(self):
        await self.paired()
        await self.server.stop()
        self.receiver.approved.clear()
        self.server.start()
        for _ in range(100):
            if self.server.connection == 'refused':
                break
            await asyncio.sleep(0.02)
        self.assertEqual(self.server.view()['connection'], 'refused')

    async def test_forget_stops_sending_builds(self):
        await self.paired()
        view = await self.server.forget()
        self.assertIsNone(view['server'])
        self.assertFalse(view['enabled'])
        with self.assertRaises(Refused):
            self.server.set_enabled(True)


@unittest.skipUnless(HAS_DEPS, 'needs aiohttp, noiseprotocol and PyYAML')
class BundleTest(unittest.TestCase):
    def test_plugins_from_the_folder_beside_esphome_go_inside_the_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'esphome'
            plugin = Path(folder) / 'tessera-plugins' / 'clock'
            (plugin / 'components' / 'clock').mkdir(parents=True)
            root.mkdir()
            (plugin / 'plugin.yaml').write_text('logger: {}')
            (plugin / 'components' / 'clock' / '__init__.py').write_text('# a component')
            sidecar = ('packages:\n  plugin_clock: !include ../tessera-plugins/clock/plugin.yaml\nexternal_components:\n'
                       '  - source: {type: local, path: ../tessera-plugins/clock/components}\n')
            bundle = tarball({'manifest.json': json.dumps({'manifest_version': 1, 'files': ['k.yaml']}).encode(),
                              'k.yaml': b'esphome: {}', 'k.plugins.yaml': sidecar.encode()})
            out = build_server.bundle_folder_plugins(bundle, root, 'k')
            with tarfile.open(fileobj=io.BytesIO(out)) as tar:
                names = tar.getnames()
                text = tar.extractfile('k.plugins.yaml').read().decode()
                manifest = json.loads(tar.extractfile('manifest.json').read())
            self.assertIn('tessera-plugins/clock/plugin.yaml', names)
            self.assertIn('tessera-plugins/clock/components/clock/__init__.py', names)
            self.assertNotIn('../', text)
            self.assertIn('tessera-plugins/clock/plugin.yaml', manifest['files'])
            # A screen without such plugins keeps ESPHome's bundle as it is.
            plain = tarball({'manifest.json': b'{}', 'k.yaml': b''})
            self.assertEqual(build_server.bundle_folder_plugins(plain, root, 'k'), plain)

    def test_only_plain_files_inside_the_folder_are_staged(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'server'
            images = build_server.stage_artifacts(tarball({**ARTIFACTS, '../escape.bin': b'x', '/abs.bin': b'x'}), target)
            self.assertFalse((Path(folder) / 'escape.bin').exists())
            self.assertTrue(images['factory'].is_file())
            with self.assertRaises(Fallback):
                build_server.stage_artifacts(tarball({'storage.json': b'{}'}), target)


@unittest.skipUnless(HAS_DEPS, 'needs aiohttp, noiseprotocol and PyYAML')
class FirmwareTest(unittest.IsolatedAsyncioTestCase):
    """How a job uses the server: its images for the upload, and the reason it builds here when it does."""

    async def asyncSetUp(self):
        from firmware import Firmware
        self.folder = tempfile.TemporaryDirectory()
        base = Path(self.folder.name)
        (base / 'esphome').mkdir()
        self.profile = base / 'esphome' / 'kitchen.yaml'
        self.profile.write_text('esphome: {name: kitchen}')
        self.firmware = Firmware(base / 'esphome', base / 'data')
        self.firmware.job = {'file': 'kitchen.yaml', 'state': 'running'}
        self.firmware._secret_values = set()
        images = build_server.stage_artifacts(tarball(ARTIFACTS), base / 'data' / 'build' / 'kitchen' / 'server')

        class Server:
            server = {'name': 'Workshop PC'}
            outcome = images

            def wanted(self):
                return True

            fresh = []

            async def compile(self, profile, root, data, env, log, phase, fresh=False):
                self.fresh.append(fresh)
                phase('build')
                log('[3/9] Compiling \\033[32mok\\033[0m')
                if isinstance(self.outcome, Exception):
                    raise self.outcome
                return self.outcome
        self.server = self.firmware.server = Server()

        async def seed(profile, env):
            self.seeded = True
        self.seeded = False
        self.firmware.seed_cache = seed

    async def asyncTearDown(self):
        self.folder.cleanup()

    async def test_a_cleaned_build_folder_is_cleaned_on_the_server_too(self):
        """Firmware.clean_build (a plugin part changed) marks the profile; its next build on the server is fresh, the one
        after it is not."""
        profile = self.firmware.profile('kitchen.yaml')
        await self.firmware.clean_build('kitchen.yaml')
        self.assertTrue(await self.firmware.compile_on_server(profile, {}))
        self.assertTrue(await self.firmware.compile_on_server(profile, {}))
        self.assertEqual(self.server.fresh, [True, False])

    async def test_the_upload_sends_what_the_server_built(self):
        self.assertTrue(await self.firmware.compile_on_server(self.firmware.profile('kitchen.yaml'), {}))
        self.assertEqual(self.firmware.job['where'], 'server')
        profile = self.firmware.profile('kitchen.yaml')
        ota = self.firmware.served_file(profile, 'install', '192.168.1.20')
        usb = self.firmware.served_file(profile, 'install', '/dev/ttyUSB0')
        table = self.firmware.served_file(profile, 'widen', '192.168.1.20')
        self.assertTrue(ota[1].endswith('build/firmware.ota.bin'))
        self.assertTrue(usb[1].endswith('build/firmware.factory.bin'))
        self.assertTrue(table[1].endswith('partition-table.bin'))
        # The app's own lookups read the server's build as one made here.
        self.assertEqual(self.firmware.factory_image(profile), Path(usb[1]))
        self.assertEqual(self.firmware.image_size('kitchen.yaml'), 2000)

    async def test_a_fallback_builds_here_and_says_why(self):
        self.server.outcome = Fallback('offline')
        self.assertFalse(await self.firmware.compile_on_server(self.firmware.profile('kitchen.yaml'), {}))
        self.assertEqual((self.firmware.job['where'], self.firmware.job['fallback']), ('here', 'offline'))
        self.assertTrue(self.seeded)   # the compile cache a build here starts from
        self.assertTrue(any('Building here instead' in line for line in self.firmware.logs))
        self.assertEqual(self.firmware.served_file(self.firmware.profile('kitchen.yaml'), 'install', 'host'), [])

    async def test_a_failure_on_the_server_fails_the_job(self):
        self.server.outcome = Failed('The build failed on Workshop PC')
        with self.assertRaises(RuntimeError):
            await self.firmware.compile_on_server(self.firmware.profile('kitchen.yaml'), {})


if __name__ == '__main__':
    unittest.main()
