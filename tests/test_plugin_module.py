"""A plugin's own code for the editor's preview (screen_manager/app/plugin_module.py, docs/EMULATOR_ARCHITECTURE.md
"Plugins"): what the app reads of a module, what it refuses, and where it finds one for a screen's plugin: a folder
being made, what it keeps, or what the plugins repository published, fetched once and checked.

The modules here are written by hand, a section at a time, so the test needs no compiler: web/wasm/test_plugin_module.mjs
loads a real one into the real preview."""
import asyncio
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))

import plugin_module  # noqa: E402

ABI = '0123456789abcdef'


def leb(n):
    out = bytearray()
    while True:
        byte, n = n & 0x7F, n >> 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def name(text):
    return leb(len(text)) + text.encode()


def section(kind, payload):
    return bytes([kind]) + leb(len(payload)) + payload


FUNCTION, TABLE, MEMORY, GLOBAL = (b'\x00' + leb(0), b'\x01\x70\x00' + leb(1), b'\x02\x00' + leb(1), b'\x03\x7f\x01')
# What every module of Emscripten's imports: the preview's memory, table and stack, a function and a datum of its own.
USUAL = (('env', 'memory', MEMORY), ('env', '__indirect_function_table', TABLE), ('env', '__stack_pointer', GLOBAL),
         ('env', 'lv_obj_set_size', FUNCTION), ('env', '_ZN7tessera2ui5labelEP9_lv_obj_tNS_4FontEN5theme4RoleE', FUNCTION),
         ('GOT.mem', '_ZN2ui4lookE', GLOBAL), ('GOT.func', '_ZN7tessera6Plugin8on_readyEv', GLOBAL))


def module(imports=USUAL, exports=('tessera_boot_bus',), about=None, extra=()):
    about = {'id': 'bus', 'version': '1.0.0', 'api': '0.28', 'abi': ABI} if about is None else about
    body = plugin_module.MAGIC
    body += section(2, leb(len(imports)) + b''.join(name(m) + name(n) + kind for m, n, kind in imports))
    body += section(7, leb(len(exports)) + b''.join(name(n) + b'\x00' + leb(0) for n in exports))
    for title in extra:
        body += section(0, name(title) + b'{}')
    if about is not False:
        body += section(0, name('tessera') + json.dumps(about).encode())
    return body


class Reading(unittest.TestCase):
    def test_a_module_says_which_plugin_and_which_preview_it_is_for(self):
        self.assertEqual(plugin_module.read(module()), {'id': 'bus', 'version': '1.0.0', 'api': '0.28', 'abi': ABI})
        self.assertIsNone(plugin_module.fits(module(), 'bus', '1.0.0', ABI))

    def test_it_fits_only_its_own_plugin_version_and_preview(self):
        self.assertEqual(plugin_module.fits(module(), 'tram', '1.0.0', ABI), "it is bus's")
        self.assertEqual(plugin_module.fits(module(), 'bus', '1.1.0', ABI), 'it is version 1.0.0')
        self.assertEqual(plugin_module.fits(module(), 'bus', '1.0.0', 'f' * 16), 'it was built for another preview')

    def test_what_is_no_module_is_refused_with_a_reason(self):
        for body, why in ((b'', 'empty'), (b'<html>', 'not a WebAssembly'), (module(about=False), 'does not say'),
                          (module(about={'id': 'bus'}), 'does not say'), (module()[:-4], 'section past the end'),
                          (module() + b'\0' * plugin_module.MAX_BYTES, 'larger')):
            with self.subTest(why):
                with self.assertRaises(plugin_module.Unfit) as refused:
                    plugin_module.read(body)
                self.assertIn(why, str(refused.exception))

    def test_a_module_reaches_only_into_the_preview(self):
        """Its imports are its only way out: the preview's own functions and data, never the browser's, a file, a socket
        or script for the page."""
        for imports, why in (((('wasi_snapshot_preview1', 'fd_write', FUNCTION),), 'imports from wasi_snapshot_preview1'),
                             ((('env', 'emscripten_run_script', FUNCTION),), 'asks for emscripten_run_script'),
                             ((('env', 'emscripten_asm_const_int', FUNCTION),), 'asks for emscripten_asm_const_int'),
                             ((('env', '__syscall_openat', FUNCTION),), 'asks for __syscall_openat'),
                             ((('env', '_dlopen_js', FUNCTION),), 'asks for _dlopen_js'),
                             ((('js', 'anything', FUNCTION),), 'imports from js')):
            with self.subTest(why):
                self.assertEqual(plugin_module.fits(module(imports=USUAL + imports), 'bus', '1.0.0', ABI), 'it ' + why)

    def test_a_module_with_script_for_the_page_is_refused(self):
        for body in (module(exports=('tessera_boot_bus', '__em_js__alert')), module(exports=('__start_em_asm',)),
                     module(extra=('em_asm',)), module(extra=('em_js',))):
            self.assertEqual(plugin_module.fits(body, 'bus', '1.0.0', ABI), 'it carries script for the page')

    def test_other_sections_of_its_own_are_left_alone(self):
        self.assertIsNone(plugin_module.fits(module(extra=('dylink.0', 'name', 'producers')), 'bus', '1.0.0', ABI))


def manifest(**more):
    return {'id': 'bus', 'version': '1.0.0', 'api': '0.28', 'icon': 'bus', 'topics': ['travel'], 'maintainer': 'someone',
            'license': 'MIT', 'tiles': [{'id': 'next', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 300}],
            **more}


ENGLISH = {'_meta': {'name': 'English'}, 'app': {'name': 'Bus', 'summary': 'The next bus.', 'tile': 'Next'}}


class Reply:
    def __init__(self, status, body=b'', headers=None):
        self.status, self.body, self.headers = status, body, headers or {}
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(self.status)

    async def iter_chunked(self, size):
        for start in range(0, len(self.body), size):
            yield self.body[start:start + size]


class Github:
    """The plugins repository's branch `modules`, as raw.githubusercontent.com serves it."""
    closed = False

    def __init__(self, files):
        self.files, self.asked = files, []

    def get(self, url, headers=None):
        self.asked.append(url.rsplit('/', 1)[-1])
        body = self.files.get(url.rsplit('/', 1)[-1])
        return Reply(200, body, {'ETag': 'one'}) if body is not None else Reply(404)


class Finding(unittest.IsolatedAsyncioTestCase):
    def service(self, source='index'):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        manager = type('Manager', (), {'page_senders': {}})()
        service = plugin_service.Plugins(manager, root / 'data', root / 'esphome')
        entry = plugin_service.Entry(manifest(), {'en': ENGLISH}, {}, source, 'tessera', repo='https://github.com/someone/tessera-bus',
                                     path='.', ref='a' * 40, folder=str(root / 'bus') if source == 'folder' else None)
        (service.folders if source == 'folder' else service.index)['bus'] = entry
        service.store.put('hall', {'id': 'bus', 'version': '1.0.0', 'source': source, 'ref': 'a' * 40, 'state': 'active'})
        service.http = Github({})
        return service, root

    async def test_a_plugin_without_a_module_is_simply_not_listed(self):
        service, _ = self.service()
        self.assertEqual(await service.modules_on('hall', ABI), [])
        self.assertIsNone(await service.module('bus', ABI, 'hall'))
        self.assertEqual(await service.modules_on('hall', 'not a number'), [])
        self.assertEqual(await service.modules_on(None, ABI), [])

    async def test_a_module_the_app_keeps_is_checked_once_and_handed_out(self):
        service, root = self.service()
        kept = root / 'data' / 'plugins' / 'modules' / f'bus-1.0.0-{ABI}.wasm'
        kept.parent.mkdir(parents=True)
        kept.write_bytes(module())
        listed = await service.modules_on('hall', ABI)
        self.assertEqual([(item['id'], item['version']) for item in listed], [('bus', '1.0.0')])
        self.assertEqual(listed[0]['url'], f'api/plugins/bus/module?abi={ABI}&screen=hall&v=1.0.0')
        self.assertEqual(await service.module('bus', ABI, 'hall'), module())
        # Asked again, the file is looked at, not read and checked again.
        checks = dict(service.module_checks)
        reads = []
        read_bytes = Path.read_bytes
        Path.read_bytes = lambda path: reads.append(path) or read_bytes(path)
        try:
            await service.modules_on('hall', ABI)
        finally:
            Path.read_bytes = read_bytes
        self.assertEqual(reads, [])
        self.assertEqual(service.module_checks, checks)
        # A module for another preview, or of another plugin under that name, is not this one.
        self.assertEqual(await service.modules_on('hall', 'f' * 16), [])
        kept.write_bytes(module(about={'id': 'tram', 'version': '1.0.0', 'abi': ABI}) + b' ')
        self.assertEqual(await service.modules_on('hall', ABI), [])

    async def test_a_plugin_that_failed_its_build_has_no_module_on_that_screen(self):
        service, root = self.service()
        kept = root / 'data' / 'plugins' / 'modules' / f'bus-1.0.0-{ABI}.wasm'
        kept.parent.mkdir(parents=True)
        kept.write_bytes(module())
        service.store.put('hall', {'id': 'bus', 'version': '1.0.0', 'source': 'index', 'ref': 'a' * 40, 'state': 'failed'})
        self.assertEqual(await service.modules_on('hall', ABI), [])

    async def test_a_folder_being_made_brings_its_own_module_named_after_its_time(self):
        service, root = self.service('folder')
        built = root / 'bus' / '.preview' / 'bus.wasm'
        built.parent.mkdir(parents=True)
        built.write_bytes(module())
        listed = await service.modules_on('hall', ABI)
        self.assertRegex(listed[0]['url'], rf'^api/plugins/bus/module\?abi={ABI}&screen=hall&v=1\.0\.0-\d+$')
        self.assertEqual(await service.module('bus', ABI, 'hall'), module())

    async def test_a_published_module_is_fetched_once_checked_and_kept(self):
        service, root = self.service()
        body = module()
        listing = {'format': 1, 'modules': {'bus': {'1.0.0': {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}}}}
        service.http = Github({'index.json': json.dumps(listing).encode(), 'bus-1.0.0.wasm': body})
        # Listing asks for the list alone: the module comes when an editor asks for it.
        self.assertEqual([item['id'] for item in await service.modules_on('hall', ABI)], ['bus'])
        self.assertEqual(service.http.asked, ['index.json'])
        self.assertEqual(await service.module('bus', ABI, 'hall'), body)
        self.assertEqual(service.http.asked, ['index.json', 'bus-1.0.0.wasm'])
        self.assertTrue((root / 'data' / 'plugins' / 'modules' / f'bus-1.0.0-{ABI}.wasm').is_file())
        # From then on it is the app's own file: GitHub is not asked again, for the module nor (within its time) the list.
        self.assertEqual(await service.module('bus', ABI, 'hall'), body)
        await service.modules_on('hall', ABI)
        self.assertEqual(service.http.asked, ['index.json', 'bus-1.0.0.wasm'])

    async def test_a_published_module_that_is_not_what_the_list_names_is_not_kept(self):
        service, root = self.service()
        body = module()
        listing = {'format': 1, 'modules': {'bus': {'1.0.0': {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}}}}
        other = module(about={'id': 'bus', 'version': '1.0.0', 'api': '0.28', 'abi': ABI, 'more': 1})
        service.http = Github({'index.json': json.dumps(listing).encode(), 'bus-1.0.0.wasm': other})
        self.assertIsNone(await service.module('bus', ABI, 'hall'))
        self.assertFalse((root / 'data' / 'plugins' / 'modules').exists())

    async def test_only_a_release_of_the_index_takes_a_published_module(self):
        """A link, a branch or a folder is someone's own code under the same id: never the index's module."""
        service, _ = self.service()
        body = module()
        listing = {'format': 1, 'modules': {'bus': {'1.0.0': {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}}}}
        service.http = Github({'index.json': json.dumps(listing).encode(), 'bus-1.0.0.wasm': body})
        service.store.put('hall', {'id': 'bus', 'version': '1.0.0', 'source': 'branch', 'ref': 'a' * 40, 'state': 'active'})
        import plugins as plugin_service
        service.links['bus'] = plugin_service.Entry(manifest(), {'en': ENGLISH}, {}, 'branch', 'test',
                                                    repo='https://github.com/someone/tessera-bus', path='.', ref='a' * 40)
        self.assertEqual(await service.modules_on('hall', ABI), [])
        self.assertIsNone(await service.module('bus', ABI, 'hall'))

    async def test_an_older_version_s_module_goes_when_a_newer_one_is_kept(self):
        service, root = self.service()
        folder = root / 'data' / 'plugins' / 'modules'
        folder.mkdir(parents=True)
        (folder / f'bus-0.9.0-{ABI}.wasm').write_bytes(b'old')
        (folder / f'bus-1.0.0-{"f" * 16}.wasm').write_bytes(b'another preview')
        (folder / f'tram-0.9.0-{ABI}.wasm').write_bytes(b'another plugin')
        body = module()
        listing = {'format': 1, 'modules': {'bus': {'1.0.0': {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}}}}
        service.http = Github({'index.json': json.dumps(listing).encode(), 'bus-1.0.0.wasm': body})
        self.assertEqual(await service.module('bus', ABI, 'hall'), body)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), [f'bus-1.0.0-{ABI}.wasm', f'tram-0.9.0-{ABI}.wasm'])


class SameNumber(unittest.TestCase):
    def test_the_editor_s_preview_and_its_renderer_file_name_one_number(self):
        """The number a module must carry is worked out from the headers a plugin can reach (web/wasm/toolchain.py); the
        preview shipped in the editor says the same one (renderer.json), or its modules would never be found."""
        sys.path.insert(0, str(ROOT / 'web' / 'wasm'))
        import toolchain
        renderer = json.loads((ROOT / 'web/src/wasm/renderer.json').read_text())
        self.assertRegex(renderer['plugin_abi'], r'^[0-9a-f]{16}$')
        self.assertEqual(renderer['plugin_abi'], toolchain.plugin_abi())


if __name__ == '__main__':
    unittest.main()
