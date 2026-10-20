"""Bounded public wake models and immutable, independently verifiable build inputs."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))

import plugin_models as models
from plugin_fetch import Fetcher, PublicResolver, blocked_address

SOURCE = 'https://models.example.org/alisa.json'
BINARY = 'https://models.example.org/model.tflite'
CATALOGUE = 'https://models.example.org/hey_jarvis.json'
SPEC = {'id': 'wake_models', 'kind': 'micro_wake_word_models', 'target': 'va_wake',
        'feature_step_size': 10, 'catalogue': [{'id': 'va_hey_jarvis', 'url': CATALOGUE, 'label': 'jarvis'}]}


def manifest(word='Алиса', *, step=10, model='model.tflite'):
    return {'type': 'micro', 'wake_word': word, 'author': 'Test', 'version': 2,
            'trained_languages': ['ru'], 'model': model,
            'micro': {'feature_step_size': step, 'tensor_arena_size': 32000,
                      'probability_cutoff': 0.9, 'sliding_window_size': 10,
                      'minimum_esphome_version': '2024.7.0'}}


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


def binary(size=32):
    return b'\x08\x00\x00\x00TFL3' + b'\x00' * (size - 8)


class OfflineFetcher:
    def __init__(self, sources=None):
        self.sources = {SOURCE: encoded(manifest()), BINARY: binary()}
        self.sources.update(sources or {})
        self.calls = []

    async def download_bytes(self, url, headers, network, limit, *, require_status=None):
        self.calls.append((url, headers, network, limit, require_status))
        value = self.sources[url]
        if isinstance(value, Exception):
            raise value
        return value


class RequestValidation(unittest.TestCase):
    def test_no_preselected_models_and_explicit_empty_is_valid_for_existing_install(self):
        self.assertEqual(models.validate_requested(SPEC, []), [])

    def test_bad_urls_and_untrusted_fields(self):
        bad = ['http://models.example.org/a.json', 'file:///a.json',
               'https://127.0.0.1/a.json', 'https://[::1]/a.json',
               'https://router.local/a.json', 'https://localhost/a.json',
               'https://x.home.arpa/a.json', 'https://x.internal/a.json',
               'https://user:password@models.example.org/a.json',
               'https://models.example.org:444/a.json', 'https://models.example.org/a.json#',
               'https://models.example.org/\na.json', 'https://models.example.org/\\a.json',
               'https://models.example.org/' + 'x' * 2048]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(models.ModelError):
                models.validate_requested(SPEC, [{'url': url}])
        for extra in ({'snapshot': 'a' * 64}, {'path': '/tmp/model'}, {'label': 'Forged'}):
            with self.subTest(extra=extra), self.assertRaises(models.ModelError):
                models.validate_requested(SPEC, [{'url': SOURCE, **extra}])
        for bad_list in (None, {}, [{'url': SOURCE}] * 17, [{'id': None, 'url': SOURCE}]):
            with self.subTest(value=bad_list), self.assertRaises(models.ModelError):
                models.validate_requested(SPEC, bad_list)

    def test_catalogue_paste_assigns_identity_and_duplicate_source_is_error(self):
        self.assertEqual(models.validate_requested(SPEC, [{'url': CATALOGUE}], []),
                         [{'id': 'va_hey_jarvis', 'url': CATALOGUE}])
        with self.assertRaisesRegex(models.ModelError, 'twice'):
            models.validate_requested(SPEC, [{'id': 'va_hey_jarvis', 'url': CATALOGUE}, {'url': CATALOGUE}], [])

    def test_id_ownership_is_strict_in_resolution_but_not_dependency_planning(self):
        request = [{'id': 'ww_existing', 'url': SOURCE}]
        self.assertEqual(models.validate_requested(SPEC, request), request)
        with self.assertRaises(models.ModelError):
            models.validate_requested(SPEC, request, [])
        self.assertEqual(models.validate_requested(SPEC, request, request), request)
        with self.assertRaises(models.ModelError):
            models.validate_requested(SPEC, [{'id': 'ww_existing', 'url': CATALOGUE}], request)
        with self.assertRaises(models.ModelError):
            models.validate_requested(SPEC, [{'id': 'va_hey_jarvis', 'url': SOURCE}], [])

    def test_revision_includes_order_snapshots_and_target_not_mapping_key_order(self):
        values = {'wake_models': [{'id': 'a', 'snapshot': 'a' * 64}, {'id': 'b', 'snapshot': 'b' * 64}]}
        revision = models.build_revision([SPEC], values)
        self.assertEqual(revision, models.build_revision([dict(reversed(list(SPEC.items())))], copy.deepcopy(values)))
        self.assertNotEqual(revision, models.build_revision([SPEC], {'wake_models': list(reversed(values['wake_models']))}))
        self.assertNotEqual(revision, models.build_revision([{**SPEC, 'target': 'other'}], values))


class NativeMetadata(unittest.TestCase):
    def test_native_v2_and_v1_conversion_preserve_real_timing(self):
        source, metadata = models.parse_manifest(encoded(manifest()), 10)
        self.assertEqual(source['wake_word'], 'Алиса')
        self.assertEqual(metadata['micro']['feature_step_size'], 10)
        old = {'type': 'micro', 'wake_word': 'Old model', 'author': 'Test',
               'website': 'https://example.org', 'version': 1, 'model': 'old.tflite',
               'micro': {'probability_cutoff': 0.5, 'sliding_window_average_size': 10}}
        original, converted = models.parse_manifest(encoded(old), 20)
        self.assertEqual(original, old)
        self.assertEqual(converted['micro']['feature_step_size'], 20)
        self.assertEqual(converted['micro']['tensor_arena_size'], 45672)
        with self.assertRaisesRegex(models.ModelError, '20 ms'):
            models.parse_manifest(encoded(old), 10)
        old['micro']['sliding_window_average_size'] = 0
        with self.assertRaisesRegex(models.ModelError, 'sliding_window_size must be positive'):
            models.parse_manifest(encoded(old), 20)

    def test_strict_json_and_native_schema_failures(self):
        bad = [b'\xff', b'{', b'[]', b'{"version":2,"version":1}', b'{"x":NaN}', b'{"x":1e9999}',
               encoded({**manifest(), 'version': 3}), encoded({**manifest(), 'extra': True}),
               encoded({**manifest(), 'micro': {'feature_step_size': 10}})]
        for source in bad:
            with self.subTest(source=source), self.assertRaises(models.ModelError):
                models.parse_manifest(source, 10)

    def test_vad_names_bad_ranges_and_incompatible_timing(self):
        bad = [manifest('vad'), manifest(' VAD '), manifest('  '), manifest(step=20)]
        for field, value in [('tensor_arena_size', 0), ('tensor_arena_size', -1),
                             ('feature_step_size', 0), ('probability_cutoff', -0.1),
                             ('probability_cutoff', 1.1), ('sliding_window_size', 0),
                             ('minimum_esphome_version', '9999.1.0')]:
            data = manifest()
            data['micro'][field] = value
            bad.append(data)
        for data in bad:
            with self.subTest(data=data), self.assertRaises(models.ModelError):
                models.parse_manifest(encoded(data), 10)


class Resolution(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fetcher = OfflineFetcher()

    async def resolve(self, requested=None, previous=None):
        return await models.resolve_models(SPEC, [{'url': SOURCE}] if requested is None else requested,
                                           previous or [], self.fetcher, self.root)

    async def test_only_chosen_custom_model_downloads_and_snapshot_is_portable(self):
        result = await self.resolve()
        entry = result[0]
        self.assertRegex(entry['id'], r'^ww_[0-9a-f]{24}$')
        self.assertEqual(entry['label'], 'Алиса')
        self.assertEqual([call[0] for call in self.fetcher.calls], [SOURCE, BINARY])
        self.assertEqual(self.fetcher.calls[0][1:], ({}, ['models.example.org'], models.MAX_MANIFEST_BYTES, 200))
        self.assertEqual(self.fetcher.calls[1][1:], ({}, ['models.example.org'], models.MAX_MODEL_BYTES, 200))
        source, model = self.fetcher.sources[SOURCE], self.fetcher.sources[BINARY]
        expected = hashlib.sha256(len(source).to_bytes(8, 'big') + source + len(model).to_bytes(8, 'big') + model).hexdigest()
        self.assertEqual(entry['snapshot'], expected)
        files = models.snapshot_files(self.root, [{'snapshot': expected}])
        self.assertEqual(set(files), {f'.tessera-models/{expected}/{name}' for name in models.SNAPSHOT_FILES})
        runnable = json.loads(files[models.snapshot_manifest_path(entry)])
        self.assertEqual(runnable, {**manifest(), 'model': 'model.tflite'})
        self.assertEqual(files[f'.tessera-models/{expected}/source.json'], source)
        # The exact export is a native local ESPHome model with no original host.
        from esphome.components.micro_wake_word import _load_model_data
        with tempfile.TemporaryDirectory() as exported:
            for relative, raw in files.items():
                destination = Path(exported) / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            native, native_binary = _load_model_data(Path(exported) / models.snapshot_manifest_path(entry))
            self.assertEqual(native['wake_word'], 'Алиса')
            self.assertEqual(native_binary, model)

    async def test_reuse_survives_restart_and_mutable_url_never_refetches(self):
        old = await self.resolve()
        self.fetcher.sources.clear()
        self.fetcher.calls.clear()
        # No process-local cache is involved; read the three on-disk files again.
        again = await self.resolve(previous=old)
        self.assertEqual(again, old)
        self.assertEqual(self.fetcher.calls, [])
        again[0]['label'] = 'Browser mutation'
        self.assertEqual(old[0]['label'], 'Алиса')

    async def test_catalogue_and_same_label_models_keep_distinct_ids(self):
        self.fetcher.sources[CATALOGUE] = encoded(manifest())
        entries = await self.resolve([{'url': SOURCE}, {'url': CATALOGUE}])
        self.assertEqual([entry['label'] for entry in entries], ['Алиса', 'Алиса'])
        self.assertEqual(entries[1]['id'], 'va_hey_jarvis')
        self.assertNotEqual(entries[0]['id'], entries[1]['id'])
        self.fetcher.sources.clear()
        self.fetcher.calls.clear()
        reordered = await self.resolve([{'id': entry['id'], 'url': entry['url']} for entry in reversed(entries)], entries)
        self.assertEqual(reordered, list(reversed(entries)))
        self.assertEqual(self.fetcher.calls, [])

    async def test_trusted_failed_id_and_snapshot_can_be_retried(self):
        failed = await self.resolve()
        self.fetcher.sources.clear()
        retried = await self.resolve([{'id': failed[0]['id'], 'url': SOURCE}], failed)
        self.assertEqual(retried, failed)

    async def test_unmaterialized_legacy_entries_fetch_and_keep_the_historical_id(self):
        legacy = [{'id': 'va_historical', 'url': SOURCE, 'label': 'Historical'}]
        result = await self.resolve([{'id': 'va_historical', 'url': SOURCE}], legacy)
        self.assertEqual(result[0]['id'], 'va_historical')
        self.assertEqual(len(self.fetcher.calls), 2)

    async def test_existing_model_survives_catalogue_evolution_without_reselection(self):
        existing = await self.resolve()
        self.fetcher.calls.clear()
        self.fetcher.sources.clear()
        changed = {**SPEC, 'catalogue': [{'id': 'new_catalogue_id', 'url': SOURCE, 'label': 'New preset'}]}
        result = await models.resolve_models(changed, [{'id': existing[0]['id'], 'url': SOURCE}],
                                             existing, self.fetcher, self.root)
        self.assertEqual(result, existing)
        self.assertEqual(self.fetcher.calls, [])
        # A historical catalogue ID also survives retargeting of that preset.
        changed['catalogue'] = [{'id': existing[0]['id'], 'url': CATALOGUE, 'label': 'Changed preset'}]
        result = await models.resolve_models(changed, [{'id': existing[0]['id'], 'url': SOURCE}],
                                             existing, self.fetcher, self.root)
        self.assertEqual(result, existing)

    async def test_invalid_request_fails_before_download_or_asset_write(self):
        for requested in ([{'id': 'ww_forged', 'url': SOURCE}],
                          [{'url': SOURCE, 'snapshot': 'a' * 64}],
                          [{'url': SOURCE}, {'url': SOURCE}]):
            with self.subTest(requested=requested), self.assertRaises(models.ModelError):
                await self.resolve(requested)
        self.assertEqual(self.fetcher.calls, [])
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(await self.resolve([]), [])
        self.assertEqual(self.fetcher.calls, [])

    async def test_binary_url_is_independently_checked_and_can_use_another_public_host(self):
        for url in ('http://models.example.org/model.tflite', 'https://192.168.1.1/a.tflite',
                    'https://secret.internal/a.tflite', 'https://user:pass@models.example.org/a.tflite'):
            self.fetcher.sources[SOURCE] = encoded(manifest(model=url))
            self.fetcher.calls.clear()
            with self.subTest(url=url), self.assertRaises(models.ModelError):
                await self.resolve()
            self.assertEqual(len(self.fetcher.calls), 1)
        other = 'https://binary.example.org/custom.tflite'
        self.fetcher.sources[SOURCE] = encoded(manifest(model=other))
        self.fetcher.sources[other] = binary()
        await self.resolve()
        self.assertEqual(self.fetcher.calls[-1][2], ['binary.example.org'])

    async def test_manifest_exact_limit_and_over_limit(self):
        raw = encoded(manifest())
        self.fetcher.sources[SOURCE] = raw + b' ' * (models.MAX_MANIFEST_BYTES - len(raw))
        self.assertEqual(len(await self.resolve()), 1)
        self.fetcher.sources[SOURCE] += b' '
        with self.assertRaises(models.ModelError):
            await self.resolve()

    async def test_binary_limits_and_invalid_tflite_headers(self):
        self.fetcher.sources[BINARY] = binary(models.MAX_MODEL_BYTES)
        self.assertEqual((await self.resolve())[0]['model_bytes'], models.MAX_MODEL_BYTES)
        for raw in (binary(models.MAX_MODEL_BYTES + 1), b'TFL3', b'not a tflite file',
                    b'\xff\xff\xff\xffTFL3' + b'\x00' * 24,
                    b'\x09\x00\x00\x00TFL3' + b'\x00' * 24):
            self.fetcher.sources[BINARY] = raw
            with self.subTest(size=len(raw)), self.assertRaises(models.ModelError):
                await self.resolve()

    async def test_aggregate_limit_accepts_exact_and_rejects_one_more_model(self):
        requested = []
        self.fetcher.sources[BINARY] = binary(models.MAX_MODEL_BYTES)
        for i in range(5):
            url = f'https://models.example.org/model-{i}.json'
            self.fetcher.sources[url] = encoded(manifest(word=f'Model {i}'))
            requested.append({'url': url})
        self.assertEqual(len(await self.resolve(requested[:4])), 4)
        with self.assertRaisesRegex(models.ModelError, '8 MiB'):
            await self.resolve(requested)

    async def test_snapshot_tampering_is_never_repaired_by_refetch(self):
        entries = await self.resolve()
        folder = self.root / '.tessera-models' / entries[0]['snapshot']
        self.fetcher.calls.clear()
        (folder / 'source.json').write_bytes(encoded(manifest(word='Retargeted')))
        with self.assertRaisesRegex(models.ModelError, 'digest'):
            await self.resolve(previous=entries)
        self.assertEqual(self.fetcher.calls, [])

    async def test_runnable_manifest_and_symlinks_are_refused(self):
        entries = await self.resolve()
        folder = self.root / '.tessera-models' / entries[0]['snapshot']
        runnable = folder / 'manifest.json'
        runnable.write_bytes(b'{}')
        with self.assertRaisesRegex(models.ModelError, 'runnable'):
            models.snapshot_files(self.root, entries)
        runnable.unlink()
        runnable.symlink_to(folder / 'source.json')
        with self.assertRaises(models.ModelError):
            models.snapshot_files(self.root, entries)
        runnable.unlink()
        runnable.write_bytes(encoded({**manifest(), 'model': 'model.tflite'}))
        asset_folder = self.root / '.tessera-models'
        asset_folder.rename(self.root / 'elsewhere')
        asset_folder.symlink_to(self.root / 'elsewhere', target_is_directory=True)
        with self.assertRaises(models.ModelError):
            await self.resolve()

    async def test_partial_snapshot_and_forged_digest_export_are_refused(self):
        folder = self.root / '.tessera-models' / ('a' * 64)
        folder.mkdir(parents=True)
        (folder / 'source.json').write_bytes(encoded(manifest()))
        for digest in ('a' * 64, '../outside', 'A' * 64, '/tmp/model', None):
            with self.subTest(digest=digest), self.assertRaises(models.ModelError):
                models.snapshot_files(self.root, [{'snapshot': digest}])

    async def test_failed_download_leaves_no_partial_snapshot(self):
        self.fetcher.sources[BINARY] = OSError('HTTP 206')
        with self.assertRaises(models.ModelError):
            await self.resolve()
        self.assertFalse((self.root / '.tessera-models').exists())

    async def test_failed_atomic_publication_removes_its_temporary_directory(self):
        with patch.object(models.os, 'fsync', side_effect=OSError('disk failure')):
            with self.assertRaises(models.ModelError):
                await self.resolve()
        self.assertEqual(list((self.root / '.tessera-models').iterdir()), [])


class Response:
    def __init__(self, status, pieces):
        self.status, self.pieces, self.content = status, pieces, self
        self.read = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def iter_chunked(self, size):
        for piece in self.pieces:
            self.read += 1
            yield piece


class Session:
    closed = False

    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class PublicDownloads(unittest.IsolatedAsyncioTestCase):
    async def test_required_200_rejects_redirects_partial_and_empty_responses_before_read(self):
        for status in (201, 204, 206, 301, 302, 303, 307, 308, 404):
            response = Response(status, [b'bad'])
            session = Session(response)
            fetcher = Fetcher(session_factory=lambda: session)
            with self.subTest(status=status), self.assertRaises(OSError):
                await fetcher.download_bytes(SOURCE, {}, ['models.example.org'], require_status=200)
            self.assertEqual(response.read, 0)
            self.assertFalse(session.calls[0][1]['allow_redirects'])
        # Existing picture/fetch callers retain their previous status behavior.
        fetcher = Fetcher(session_factory=lambda: Session(Response(206, [b'old behavior'])))
        self.assertEqual(await fetcher.download_bytes(SOURCE, {}, ['models.example.org']), b'old behavior')

    async def test_streaming_exact_limit_and_one_byte_over(self):
        response = Response(200, [b'a' * 8, b'b' * 8])
        fetcher = Fetcher(session_factory=lambda: Session(response))
        self.assertEqual(await fetcher.download_bytes(SOURCE, {}, ['models.example.org'], 16, require_status=200),
                         b'a' * 8 + b'b' * 8)
        fetcher.session.response = Response(200, [b'a' * 8, b'b' * 9, b'never read'])
        with self.assertRaises(OSError):
            await fetcher.download_bytes(SOURCE, {}, ['models.example.org'], 16, require_status=200)
        self.assertEqual(fetcher.session.response.read, 2)

    async def test_public_resolver_blocks_private_dns_at_connection(self):
        resolver = PublicResolver()
        self.addAsyncCleanup(resolver.close)
        for address in ('127.0.0.1', '192.168.1.2', '169.254.169.254', '::1', '::ffff:192.168.1.2', '224.0.0.1'):
            self.assertTrue(blocked_address(address))
            with patch.object(resolver.inner, 'resolve', AsyncMock(return_value=[{'host': address}])):
                with self.subTest(address=address), self.assertRaises(OSError):
                    await resolver.resolve('models.example.org', 443, socket.AF_INET)
        with patch.object(resolver.inner, 'resolve', AsyncMock(return_value=[{'host': '192.168.1.2'}, {'host': '1.1.1.1'}])):
            self.assertEqual(await resolver.resolve('models.example.org', 443), [{'host': '1.1.1.1'}])


if __name__ == '__main__':
    unittest.main()
