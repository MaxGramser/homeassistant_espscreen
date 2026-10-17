"""Synthetic private imports use the existing immutable model and plugin build lifecycle."""
import io
import copy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import zipfile
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
import test_plugin_models as fixtures
import test_plugins as plugin_fixtures

models = fixtures.models


class PrivateSources(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = fixtures.encoded(fixtures.manifest('Synthetic private wake', model='file:///never-fetch.tflite'))
        self.binary = fixtures.binary()

    def register(self):
        return models.import_model(fixtures.SPEC, self.source, self.binary, self.root)

    async def test_persistent_identity_dedup_and_portable_export(self):
        entry = self.register()
        self.assertNotIn('url', entry)
        self.assertRegex(entry['upload'], r'^[0-9a-f]{32}$')
        self.assertRegex(entry['id'], r'^ww_[0-9a-f]{24}$')
        # Reloading proves there is no in-memory authority or deduplication cache.
        importlib.reload(models)
        self.assertEqual(self.register(), entry)
        fetcher = fixtures.OfflineFetcher()
        resolved = await models.resolve_models(fixtures.SPEC, [models.model_source(entry)], [], fetcher, self.root)
        self.assertEqual(resolved, [entry])
        self.assertEqual(fetcher.calls, [])
        registry = self.root / models.SNAPSHOT_DIR / models.IMPORT_DIR
        self.assertEqual(registry.stat().st_mode & 0o777, 0o700)
        self.assertEqual((registry / (entry['upload'] + '.json')).stat().st_mode & 0o777, 0o600)
        files = models.snapshot_files(self.root, resolved)
        self.assertEqual(len(files), 3)
        self.assertTrue(all(models.IMPORT_DIR not in path for path in files))
        with tempfile.TemporaryDirectory() as exported:
            for relative, raw in files.items():
                path = Path(exported) / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            from esphome.components.micro_wake_word import _load_model_data
            metadata, binary = _load_model_data(Path(exported) / models.snapshot_manifest_path(entry))
            self.assertEqual(metadata['wake_word'], 'Synthetic private wake')
            self.assertEqual(binary, self.binary)

    async def test_token_id_digest_and_union_are_not_client_authority(self):
        entry = self.register()
        invalid = [
            {'upload': '../outside'}, {'upload': entry['snapshot']}, {'upload': 'f' * 32},
            {'upload': entry['upload'], 'url': fixtures.SOURCE},
            {'upload': entry['upload'], 'snapshot': entry['snapshot']},
            {'upload': entry['upload'], 'id': 'ww_' + 'a' * 24},
            {'upload': entry['upload'], 'id': 'va_hey_jarvis'},
            {'url': fixtures.SOURCE, 'id': entry['id']},
        ]
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(models.ModelError):
                await models.resolve_models(fixtures.SPEC, [request], [entry], fixtures.OfflineFetcher(), self.root)
        with self.assertRaisesRegex(models.ModelError, 'twice'):
            models.validate_requested(fixtures.SPEC, [{'upload': entry['upload']}] * 2)
        self.assertEqual(models.validate_requested(fixtures.SPEC, [{'upload': 'f' * 32}]), [{'upload': 'f' * 32}])

    async def test_upload_and_url_preserve_their_own_immutable_sources(self):
        upload = self.register()
        fetcher = fixtures.OfflineFetcher()
        public = (await models.resolve_models(fixtures.SPEC, [{'url': fixtures.SOURCE}], [], fetcher, self.root))[0]
        fetcher.calls.clear()
        fetcher.sources.clear()
        result = await models.resolve_models(fixtures.SPEC,
                                            [models.model_source(entry) for entry in (upload, public)],
                                            [public, upload], fetcher, self.root)
        self.assertEqual(result, [upload, public])
        self.assertEqual(fetcher.calls, [])
        (self.root / models.snapshot_manifest_path(upload)).write_bytes(b'{}')
        with self.assertRaises(models.ModelError):
            await models.resolve_models(fixtures.SPEC, [models.model_source(upload)], [upload], fetcher, self.root)

    async def test_registry_symlinks_and_corruption_are_refused(self):
        entry = self.register()
        registry = self.root / models.SNAPSHOT_DIR / models.IMPORT_DIR
        path = registry / (entry['upload'] + '.json')
        saved = path.read_bytes()
        path.unlink()
        outside = self.root / 'outside.json'
        outside.write_bytes(saved)
        path.symlink_to(outside)
        with self.assertRaises(models.ModelError):
            await models.resolve_models(fixtures.SPEC, [models.model_source(entry)], [], None, self.root)
        path.unlink()
        path.write_bytes(b'{"id":"ww_bad","snapshot":"../outside"}')
        with self.assertRaises(models.ModelError):
            self.register()
        path.write_bytes(saved)
        registry.rename(self.root / 'registry')
        registry.symlink_to(self.root / 'registry', target_is_directory=True)
        with self.assertRaises(models.ModelError):
            self.register()

    def test_invalid_assets_never_register(self):
        for source, binary in ((b'{}', self.binary), (self.source, b'invalid'),
                               (fixtures.encoded(fixtures.manifest(step=20)), self.binary),
                               (self.source + b' ' * models.MAX_MANIFEST_BYTES, self.binary),
                               (self.source, fixtures.binary(models.MAX_MODEL_BYTES + 1))):
            with self.subTest(size=(len(source), len(binary))), self.assertRaises(models.ModelError):
                models.import_model(fixtures.SPEC, source, binary, self.root)
        self.assertFalse((self.root / models.SNAPSHOT_DIR).exists())

    def test_firmware_zip_contains_uploaded_assets_but_not_registry(self):
        from firmware import Firmware
        from test_firmware_download import PROFILE, ManagedModelFiles
        firmware = Firmware(self.root, self.root / 'data')
        firmware.create(PROFILE)
        entry = self.register()
        firmware.save_plugins('kitchen.yaml', ManagedModelFiles.sidecar([
            {'id': entry['id'], 'model': models.snapshot_manifest_path(entry)}]))
        data, _ = firmware.files('kitchen.yaml')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertFalse(any(models.IMPORT_DIR in name for name in archive.namelist()))
            for path, raw in models.snapshot_files(self.root, [entry]).items():
                self.assertEqual(archive.read('kitchen/' + path), raw)

    def test_failed_registry_publication_keeps_no_partial_token(self):
        with patch.object(models.os, 'link', side_effect=OSError('disk failure')):
            with self.assertRaises(models.ModelError):
                self.register()
        registry = self.root / models.SNAPSHOT_DIR / models.IMPORT_DIR
        self.assertEqual(list(registry.iterdir()), [])
        self.assertEqual(self.register(), self.register())

class ImportLifecycle(unittest.IsolatedAsyncioTestCase):
    make = plugin_fixtures.BuildOutcome.make
    request = plugin_fixtures.ModelLifecycle.request

    def service(self, results=None):
        import yaml
        service, root, started = self.make(results)
        path = root.parent / 'tessera-plugins' / 'clock_words' / 'tessera-plugin.yaml'
        manifest = yaml.safe_load(path.read_text())
        manifest['build_settings'] = [plugin_fixtures.wake_models_spec()]
        path.write_text(yaml.safe_dump(manifest))
        service.scan_folders()
        service.fetcher = fixtures.OfflineFetcher()
        return service, root, started

    def upload(self, service, word='Synthetic private wake'):
        return service.import_model('hall', 'clock_words', 'wake_models', 'folder',
                                    fixtures.encoded(fixtures.manifest(word)), fixtures.binary())

    async def test_import_is_inert_apply_update_and_failed_retry_preserve_pair(self):
        service, root, started = self.service(['success', 'success', 'failed', 'success'])
        upload = self.upload(service)
        self.assertEqual(self.upload(service), upload)
        self.assertEqual(service.store.of('hall'), [])
        self.assertEqual(started, [])
        self.assertFalse(service.manager.build_queue.busy())
        self.assertFalse((root / 'hall.plugins.yaml').exists())
        await service.apply('hall', self.request([{'url': fixtures.SOURCE}, models.model_source(upload)]))
        await service.manager.build_queue.idle()
        before = copy.deepcopy(service.store.get('hall', 'clock_words')['build_values'])
        service.fetcher.calls.clear()
        service.fetcher.sources.clear()
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        await service.manager.build_queue.idle()
        self.assertEqual(service.store.get('hall', 'clock_words')['build_values'], before)
        self.assertEqual(service.fetcher.calls, [])
        second = self.upload(service, 'Another synthetic wake')
        requested = [models.model_source(entry) for entry in before['wake_models']] + [models.model_source(second)]
        await service.apply('hall', self.request(requested))
        await service.manager.build_queue.idle()
        failed = service.store.get('hall', 'clock_words')
        self.assertEqual(failed['build_values'], before)
        retry = [models.model_source(entry) for entry in failed['failed_update']['build_values']['wake_models']]
        self.assertEqual(retry, requested)
        await service.apply('hall', self.request(retry))
        await service.manager.build_queue.idle()
        record = service.store.get('hall', 'clock_words')
        self.assertEqual(len(record['build_values']['wake_models']), 3)
        self.assertEqual(service.fetcher.calls, [])
        self.assertEqual(len(started), 4)
        self.assertEqual(len(models.snapshot_files(root, record['build_values']['wake_models'])), 9)

    async def test_rejected_apply_preserves_sidecar_records_and_queue(self):
        service, root, started = self.service()
        upload = self.upload(service)
        await service.apply('hall', self.request([models.model_source(upload)]))
        await service.manager.build_queue.idle()
        before = copy.deepcopy(service.store.of('hall'))
        sidecar = (root / 'hall.plugins.yaml').read_bytes()
        for source in ({'upload': 'f' * 32}, {'upload': upload['upload'], 'id': 'forged'},
                       {'upload': upload['snapshot']}, {'upload': upload['upload'], 'url': fixtures.SOURCE}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                await service.apply('hall', self.request([source]))
        self.assertEqual(service.store.of('hall'), before)
        self.assertEqual((root / 'hall.plugins.yaml').read_bytes(), sidecar)
        self.assertEqual(len(started), 1)

    async def client(self, service, root):
        from server import Manager, create_app
        from test_screen_owned_settings import fake_ha
        manager = Manager(fake_ha(), root.parent / 'screens.json')
        manager.plugins = service
        with patch('server.secrets.token_urlsafe', return_value='import-test-csrf'):
            app = create_app(manager, development=True)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    @staticmethod
    def form(parts=None):
        data = FormData()
        parts = parts if parts is not None else [('manifest', fixtures.encoded(fixtures.manifest('Synthetic private wake'))),
                                                ('model', fixtures.binary())]
        for name, body in parts:
            data.add_field(name, body, filename='../../untrusted-name', content_type='application/octet-stream')
        return data

    async def test_real_endpoint_security_destination_and_repeat_import(self):
        service, root, started = self.service()
        client = await self.client(service, root)
        endpoint = '/api/screens/hall/plugins/clock_words/models/wake_models/import?source=folder'
        response = await client.post(endpoint, data=self.form())
        self.assertEqual(response.status, 403)
        self.assertFalse((root / models.SNAPSHOT_DIR).exists())
        headers = {'X-Screen-CSRF': 'import-test-csrf'}
        for url in (endpoint.replace('wake_models', 'unknown'), endpoint.replace('source=folder', 'source=index'),
                    endpoint.replace('source=folder', 'source=invalid')):
            response = await client.post(url, headers=headers, data=self.form())
            self.assertEqual(response.status, 400, await response.text())
        self.assertFalse((root / models.SNAPSHOT_DIR).exists())
        with patch.object(service.manager, 'screen', return_value=None):
            response = await client.post(endpoint, headers=headers, data=self.form())
            self.assertEqual(response.status, 400, await response.text())
        first = await client.post(endpoint, headers=headers, data=self.form())
        self.assertEqual(first.status, 200, await first.text())
        entry = await first.json()
        second = await client.post(endpoint, headers=headers, data=self.form())
        self.assertEqual(await second.json(), entry)
        self.assertNotIn('url', entry)
        self.assertEqual(service.store.of('hall'), [])
        self.assertEqual(started, [])
        # The same declared setting is reachable for every supported editor origin.
        import plugins
        for source in ('index', 'branch', 'link'):
            entry = plugins.Entry(plugin_fixtures.manifest(build_settings=[plugin_fixtures.wake_models_spec()]),
                                  {'en': plugin_fixtures.ENGLISH}, {}, source, 'community',
                                  repo='https://github.com/example/models', ref='a' * 40)
            (service.index if source == 'index' else service.links)[entry.id] = entry
            url = endpoint.replace('clock_words', entry.id).replace('source=folder', 'source=' + source)
            response = await client.post(url, headers=headers, data=self.form())
            self.assertEqual(response.status, 200, await response.text())
            self.assertEqual(await response.json(), await second.json())

    async def test_real_endpoint_refuses_encoded_nested_and_excess_envelope(self):
        service, root, _ = self.service()
        client = await self.client(service, root)
        endpoint = '/api/screens/hall/plugins/clock_words/models/wake_models/import?source=folder'
        headers = {'X-Screen-CSRF': 'import-test-csrf', 'Content-Type': 'multipart/form-data; boundary=upload'}
        prefix = b'--upload\r\nContent-Disposition: form-data; name="manifest"; filename="x"\r\n'
        for extra in (b'Content-Transfer-Encoding: base64\r\n', b'Content-Encoding: gzip\r\n',
                      b'Content-Type: multipart/mixed; boundary=nested\r\n',
                      b'X-Large: ' + b'x' * 8200 + b'\r\n'):
            response = await client.post(endpoint, headers=headers, data=prefix + extra + b'\r\n{}\r\n--upload--\r\n')
            self.assertEqual(response.status, 400, await response.text())
        self.assertFalse((root / models.SNAPSHOT_DIR).exists())

    async def test_real_endpoint_bounded_parts_and_missing_extra_duplicate_rejection(self):
        service, root, started = self.service()
        client = await self.client(service, root)
        endpoint = '/api/screens/hall/plugins/clock_words/models/wake_models/import?source=folder'
        headers = {'X-Screen-CSRF': 'import-test-csrf'}
        manifest = fixtures.encoded(fixtures.manifest())
        pair = [('manifest', manifest), ('model', fixtures.binary())]
        for parts in (pair[:1], pair + [pair[0]], pair + [('extra', b'x')],
                      [('_charset_', b'utf-8')] + pair,
                      [('manifest', manifest + b' ' * models.MAX_MANIFEST_BYTES), pair[1]],
                      [pair[0], ('model', fixtures.binary(models.MAX_MODEL_BYTES + 1))]):
            response = await client.post(endpoint, headers=headers, data=self.form(parts))
            self.assertEqual(response.status, 400, await response.text())
        self.assertFalse((root / models.SNAPSHOT_DIR).exists())
        exact_manifest = manifest + b' ' * (models.MAX_MANIFEST_BYTES - len(manifest))
        response = await client.post(endpoint, headers=headers,
                                     data=self.form([('manifest', exact_manifest),
                                                     ('model', fixtures.binary(models.MAX_MODEL_BYTES))]))
        self.assertEqual(response.status, 200, await response.text())
        self.assertEqual((await response.json())['model_bytes'], models.MAX_MODEL_BYTES)
        self.assertEqual(service.store.of('hall'), [])
        self.assertEqual(started, [])
