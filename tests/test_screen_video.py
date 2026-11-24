"""Video in Home Assistant (screen_video.py, ha_integration/tessera_video, docs/CAMERA.md "Live video").

The app ships Home Assistant's tessera_video integration and writes it into Home Assistant's configuration folder only
when a person presses Install; once Home Assistant restarted with it, the app keeps one entry of it for each screen with
Screen camera's part Video, through the integration's own config flow, and takes away the entry of a screen of its own
that lost the video. A device the app does not know keeps its entry. The integration and the firmware work the stream's
password out of the screen's API key the same way (Screen camera's components/screen_video/__init__.py).
"""
import ast
import asyncio
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import screen_video  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app

INTEGRATION = ROOT / 'screen_manager/app/ha_integration/tessera_video'


def integration_camera():
    """The integration's camera.py as Home Assistant loads it, with the few names it takes from Home Assistant stood in
    for: what it works out of a screen's ESPHome entry is plain Python."""
    class Camera:
        def __init__(self):
            pass

        async def async_added_to_hass(self):
            pass

    names = {
        'homeassistant': {}, 'homeassistant.components': {}, 'homeassistant.helpers': {},
        'homeassistant.components.camera': {'Camera': Camera, 'CameraEntityFeature': types.SimpleNamespace(STREAM=2)},
        'homeassistant.components.ffmpeg': {'async_get_image': None},
        'homeassistant.config_entries': {'ConfigEntry': object},
        'homeassistant.const': {'MAJOR_VERSION': 2026, 'MINOR_VERSION': 11},
        'homeassistant.core': {'HomeAssistant': object},
        'homeassistant.exceptions': {'ConfigEntryNotReady': Exception},
        'homeassistant.helpers.device_registry': {'CONNECTION_NETWORK_MAC': 'mac', 'DeviceInfo': dict},
        'homeassistant.helpers.entity_platform': {'AddEntitiesCallback': object},
    }
    stubs = {name: types.ModuleType(name) for name in names}
    for name, attributes in names.items():
        for key, value in attributes.items():
            setattr(stubs[name], key, value)
    stubs['homeassistant.helpers'].device_registry = stubs['homeassistant.helpers.device_registry']
    package = types.ModuleType('tessera_video_under_test')
    package.__path__ = [str(INTEGRATION)]
    stubs['tessera_video_under_test'] = package
    with mock.patch.dict(sys.modules, stubs):
        return importlib.import_module('tessera_video_under_test.camera')


class FakeStore:
    def __init__(self, records):
        self.records = records

    def of(self, inbox):
        return [dict(r) for r in self.records.get(inbox, [])]


class FakePlugins:
    def __init__(self, records):
        self.store = FakeStore(records)


class FakeHA:
    """Home Assistant's websocket and REST answers for the integration, as its config flow gives them."""

    def __init__(self, loaded='1.0.0', entries=()):
        self.loaded = loaded
        # Home Assistant's list of entries has no unique id: the entity registry says which device an entry's camera
        # is on. As Home Assistant 2026.11 answers: a device belongs to one entry, the ESPHome one.
        self.entries = [{'state': 'loaded', **{k: v for k, v in e.items() if k != 'unique_id'}} for e in entries]
        self.held = {e['entry_id']: e.get('unique_id') for e in entries}
        self.deleted, self.flows = [], {}
        self.apart = set()  # entries whose camera sits on a device of its own (an integration before 1.0.3 on 2026.11)

    def waits(self, entry_id):
        """The entry's screen is gone from ESPHome: the integration says ConfigEntryNotReady, and no camera is made."""
        next(e for e in self.entries if e['entry_id'] == entry_id)['state'] = 'setup_retry'

    @property
    def devices(self):
        return [{'id': device, 'config_entries': ['esphome-' + device], 'primary_config_entry': 'esphome-' + device}
                for device in self.held.values() if device]

    @property
    def registry(self):
        if getattr(self, 'no_cameras', False):
            return []
        return [{'entity_id': f'camera.{entry}_video', 'platform': 'tessera_video', 'config_entry_id': entry,
                 'device_id': 'own-' + entry if entry in self.apart else device}
                for entry, device in self.held.items()
                if device and any(e['entry_id'] == entry and e['state'] == 'loaded' for e in self.entries)]

    async def request(self, kind, **data):
        if kind == 'manifest/get':
            if self.loaded is None:
                raise ConnectionError('Integration not found')
            return {'domain': data['integration'], 'version': self.loaded}
        if kind == 'config_entries/get':
            return [e for e in self.entries if e.get('domain', 'tessera_video') == data['domain']]
        raise AssertionError(kind)

    async def flow(self, method, path, data=None):
        if method == 'post' and path == 'flow':
            assert data == {'handler': 'tessera_video'}
            flow_id = f'f{len(self.flows) + 1}'
            self.flows[flow_id] = None
            return {'type': 'form', 'flow_id': flow_id, 'step_id': 'user'}
        if method == 'post' and path.startswith('flow/'):
            device = data['device']
            if device in self.held.values():
                return {'type': 'abort', 'reason': 'already_configured'}
            self.entries.append({'entry_id': 'e' + device, 'title': device, 'state': 'loaded'})
            self.held['e' + device] = device
            return {'type': 'create_entry', 'result': {'entry_id': 'e' + device}}
        if method == 'delete':
            return {}
        raise AssertionError((method, path))

    async def delete_config_entry(self, entry_id):
        self.deleted.append(entry_id)
        self.entries = [e for e in self.entries if e['entry_id'] != entry_id]


def screens():
    return [{'id': 'tablet', 'device_id': 'dev-tablet', 'name': 'Tablet'},
            {'id': 'kitchen', 'device_id': 'dev-kitchen', 'name': 'Kitchen'},
            {'id': 'hall', 'device_id': 'dev-hall', 'name': 'Hall'},
            {'id': 'new', 'name': 'Not in Home Assistant yet'}]


RECORDS = {
    'tablet': [{'id': 'screen_camera', 'state': 'active', 'parts': ['video']}, {'id': 'voice_assist', 'state': 'active'}],
    'kitchen': [{'id': 'screen_camera', 'state': 'active', 'parts': []}],
    'hall': [{'id': 'screen_camera', 'state': 'building', 'parts': ['video']}],
}


def home_assistant(folder):
    """A folder that is a Home Assistant configuration, as /homeassistant is under the Supervisor."""
    Path(folder, 'configuration.yaml').write_text('default_config:\n')
    return folder


class Install(unittest.TestCase):
    def test_install_writes_the_integration_and_status_compares_it(self):
        with tempfile.TemporaryDirectory() as folder:
            target = screen_video.target(home_assistant(folder))
            self.assertEqual(target, Path(folder) / 'custom_components' / 'tessera_video')
            self.assertEqual(screen_video.status(target)['installed'], False)
            done = screen_video.install(target)
            self.assertTrue(done['installed'] and done['current'] and done['restart'])
            for name in ('__init__.py', 'camera.py', 'config_flow.py', 'const.py', 'manifest.json', 'strings.json',
                         'translations/en.json', 'translations/nl.json'):
                self.assertEqual((target / name).read_bytes(), (INTEGRATION / name).read_bytes(), name)
            self.assertFalse(any('__pycache__' in str(p) for p in target.rglob('*')))
            (target / 'camera.py').write_text('# an older copy\n')
            self.assertEqual(screen_video.status(target), {'installed': True, 'current': False, 'path': str(target),
                                                           'version': screen_video.version(), 'home_assistant': True})

    def test_a_folder_that_cannot_be_written_says_so(self):
        with tempfile.TemporaryDirectory() as folder:
            home_assistant(folder)
            blocked = Path(folder) / 'custom_components'
            blocked.write_text('a file where the folder goes')
            with self.assertRaises(ValueError):
                screen_video.install(blocked / 'tessera_video')

    def test_an_app_without_home_assistant_writes_nothing_and_offers_the_zip(self):
        # GitHub #357: an app in Docker on its own has a /homeassistant that Home Assistant never reads.
        with tempfile.TemporaryDirectory() as folder:
            target = screen_video.target(folder)
            self.assertFalse(screen_video.status(target)['home_assistant'])
            with self.assertRaises(ValueError):
                screen_video.install(target)
            self.assertFalse(target.exists(), 'nothing written')
            Path(folder, '.storage').mkdir()
            self.assertTrue(screen_video.status(target)['home_assistant'], 'a configuration with .storage only counts too')
        # The zip unpacks in Home Assistant's configuration folder, every file of the integration, nothing else.
        import io, zipfile
        with zipfile.ZipFile(io.BytesIO(screen_video.archive())) as bundle:
            names = set(bundle.namelist())
            self.assertEqual(names, {f'custom_components/tessera_video/{name}' for name in screen_video.files()})
            self.assertEqual(bundle.read('custom_components/tessera_video/manifest.json'),
                             (INTEGRATION / 'manifest.json').read_bytes())

    def test_manifest_and_translations(self):
        manifest = json.loads((INTEGRATION / 'manifest.json').read_text())
        self.assertEqual(manifest['domain'], screen_video.DOMAIN)
        self.assertTrue(manifest['config_flow'])
        self.assertIn('esphome', manifest['dependencies'])
        self.assertEqual(manifest['version'], screen_video.version())
        english = json.loads((INTEGRATION / 'translations/en.json').read_text())
        self.assertEqual(json.loads((INTEGRATION / 'strings.json').read_text()), english)
        dutch = json.loads((INTEGRATION / 'translations/nl.json').read_text())
        keys = lambda d, p='': {p + k for k, v in d.items() for k in ([k] if not isinstance(v, dict) else [])} | \
            {x for k, v in d.items() if isinstance(v, dict) for x in keys(v, p + k + '.')}
        self.assertEqual(keys(dutch), keys(english))

    def test_the_stream_is_the_one_the_firmware_serves(self):
        # Screen camera's components/screen_video/__init__.py works the password out of the screen's API key when it is
        # built (sha256 of "tessera-video:" and the key, its first 24 hex digits) and serves the stream as user tessera
        # on port 8554. These are its answers for this key and for none; the integration must ask with the same.
        camera = integration_camera()
        key = 'MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI='
        self.assertEqual(camera.password(key), '1c013c2215e26f7ce1ca2da3')
        self.assertEqual(camera.password(None), '0f2f6ecab7ca79bec56631db')
        esphome = types.SimpleNamespace(data={'host': '192.0.2.7', 'noise_psk': key})
        video = camera.ScreenVideo('AA:BB:CC:DD:EE:FF', esphome)
        self.assertEqual(asyncio.run(video.stream_source()), 'rtsp://tessera:1c013c2215e26f7ce1ca2da3@192.0.2.7:8554/')
        self.assertEqual(video._attr_unique_id, 'AA:BB:CC:DD:EE:FF-video')
        # Read each time: Home Assistant changes the host and the key in the ESPHome entry.
        esphome.data = {'host': '192.0.2.8'}
        self.assertEqual(asyncio.run(video.stream_source()), 'rtsp://tessera:0f2f6ecab7ca79bec56631db@192.0.2.8:8554/')

    def test_the_camera_asks_home_assistant_for_its_screens_entry_and_says_when_it_is_gone(self):
        # The entry the camera was made with is never kept: asked by its id, so the key of a screen that was added again
        # is never the old one. Once Home Assistant has no such entry the camera is unavailable, hands out no address,
        # and its own entry is set up again, once, to wait for the screen where a person sees it.
        camera = integration_camera()
        key = 'MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI='
        made_with = types.SimpleNamespace(entry_id='esphome-1', data={'host': '192.0.2.7', 'noise_psk': 'an old key'})
        entries = {'esphome-1': types.SimpleNamespace(entry_id='esphome-1', data={'host': '192.0.2.9', 'noise_psk': key})}
        reloads = []
        video = camera.ScreenVideo('AA:BB:CC:DD:EE:FF', made_with, 'video-1')
        video.hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(
            async_get_entry=entries.get, async_schedule_reload=reloads.append))
        self.assertTrue(video.available)
        self.assertEqual(asyncio.run(video.stream_source()), 'rtsp://tessera:1c013c2215e26f7ce1ca2da3@192.0.2.9:8554/')
        del entries['esphome-1']
        self.assertFalse(video.available)
        self.assertIsNone(asyncio.run(video.stream_source()))
        self.assertIsNone(asyncio.run(video.async_camera_image()))
        self.assertEqual(reloads, ['video-1'])


class Screens(unittest.TestCase):
    def test_which_screens_have_the_video(self):
        wanted, without = screen_video.video_screens(FakePlugins(RECORDS), screens())
        self.assertEqual(wanted, {'dev-tablet': 'Tablet'})
        # The kitchen runs Screen camera without Video; the hall's build is under way, so it is in neither.
        self.assertEqual(without, {'dev-kitchen'})


class Sync(unittest.TestCase):
    def run_sync(self, ha, folder, installed=True):
        target = screen_video.target(home_assistant(folder))
        if installed:
            screen_video.install(target)
        videos = screen_video.Videos(target)
        return videos, asyncio.run(videos.sync(ha, *screen_video.video_screens(FakePlugins(RECORDS), screens())))

    def test_nothing_before_the_person_installed_it(self):
        with tempfile.TemporaryDirectory() as folder:
            ha = FakeHA()
            videos, done = self.run_sync(ha, folder, installed=False)
            self.assertEqual(done, {'added': [], 'removed': []})
            self.assertEqual(ha.entries, [])
            self.assertIsNone(videos.loaded)

    def test_nothing_before_home_assistant_restarted_with_it(self):
        with tempfile.TemporaryDirectory() as folder:
            ha = FakeHA(loaded=None)
            videos, done = self.run_sync(ha, folder)
            self.assertEqual(done, {'added': [], 'removed': []})
            self.assertIsNone(videos.loaded)

    def test_an_entry_for_each_screen_with_video_and_away_with_one_that_lost_it(self):
        with tempfile.TemporaryDirectory() as folder:
            ha = FakeHA(entries=[{'entry_id': 'old', 'unique_id': 'dev-kitchen', 'title': 'Kitchen'},
                                 {'entry_id': 'mine', 'unique_id': 'dev-elsewhere', 'title': 'Built elsewhere'},
                                 {'entry_id': 'hall', 'unique_id': 'dev-hall', 'title': 'Hall'}])
            videos, done = self.run_sync(ha, folder)
            self.assertEqual(done, {'added': ['dev-tablet'], 'removed': ['dev-kitchen']})
            self.assertEqual(videos.loaded, '1.0.0')
            self.assertEqual(sorted(ha.held[e['entry_id']] for e in ha.entries), ['dev-elsewhere', 'dev-hall', 'dev-tablet'])
            # Again: nothing more to do.
            again = asyncio.run(videos.sync(ha, *screen_video.video_screens(FakePlugins(RECORDS), screens())))
            self.assertEqual(again, {'added': [], 'removed': []})

    def test_an_entry_that_waits_for_a_screen_that_is_gone_goes_and_the_screen_of_today_gets_one(self):
        # The tablet was added to Home Assistant again: another device, another key. Its old entry names the old
        # device, which ESPHome holds no more, and Home Assistant says the entry waits (setup_retry).
        with tempfile.TemporaryDirectory() as folder:
            ha = FakeHA(entries=[{'entry_id': 'stale', 'unique_id': 'dev-tablet-before', 'title': 'Tablet'},
                                 {'entry_id': 'mine', 'unique_id': 'dev-elsewhere', 'title': 'Built elsewhere'}])
            ha.waits('stale')
            videos, done = self.run_sync(ha, folder)
            self.assertEqual(done, {'added': ['dev-tablet'], 'removed': ['stale']})
            self.assertEqual(ha.deleted, ['stale'])
            # A screen built elsewhere and added by hand has a working entry: it stays.
            self.assertEqual(sorted(ha.held[e['entry_id']] for e in ha.entries), ['dev-elsewhere', 'dev-tablet'])

    def test_a_working_entry_whose_camera_sits_on_a_device_of_its_own_stays(self):
        # Home Assistant 2026.11 with an integration before 1.0.3: the camera is on a second device with the screen's
        # name, which no ESPHome entry holds. The entry works, and nothing but Home Assistant's own word that an entry
        # waits takes one away (a guess from the registries took this one away, again and again, 2026-11-17).
        with tempfile.TemporaryDirectory() as folder:
            ha = FakeHA(entries=[{'entry_id': 'works', 'unique_id': 'dev-tablet', 'title': 'Tablet'}])
            ha.apart = {'works'}
            _, done = self.run_sync(ha, folder)
            self.assertEqual(done, {'added': [], 'removed': []})
            self.assertEqual(ha.deleted, [])
            self.assertEqual(len(ha.entries), 1)

    def test_an_entry_whose_camera_is_not_there_yet_is_not_added_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            # The tablet's entry is there, but its camera is in no registry yet (Home Assistant is starting).
            ha = FakeHA(entries=[{'entry_id': 'starting', 'unique_id': 'dev-tablet', 'title': 'Tablet'}])
            ha.no_cameras = True
            _, done = self.run_sync(ha, folder)
            self.assertEqual(done, {'added': [], 'removed': []})
            self.assertEqual(len(ha.entries), 1)

    def test_the_camera_names_the_screens_device_and_second_devices_let_go_after_it_moved(self):
        # From Home Assistant 2025.8 the camera names the screen's device itself and hands out no device of its own;
        # a device this entry made before lets go of the entry once the camera is on the screen's device.
        camera = integration_camera()
        self.assertTrue(camera.NAMES_ITS_DEVICE)
        screen = types.SimpleNamespace(id='dev-tablet', config_entry_id='esphome-1')
        self.assertEqual(camera._entries_of(screen), {'esphome-1'})
        self.assertEqual(camera._entries_of(types.SimpleNamespace(config_entries={'esphome-1', 'video-1'})),
                         {'esphome-1', 'video-1'})
        video = camera.ScreenVideo('AA:BB:CC:DD:EE:FF', types.SimpleNamespace(entry_id='esphome-1', data={}), 'video-1', screen)
        self.assertIs(video.device_entry, screen)
        self.assertFalse(hasattr(video, '_attr_device_info'))
        let_go = []
        registry = types.SimpleNamespace(
            async_update_device=lambda device, remove_config_entry_id: let_go.append((device, remove_config_entry_id)),
            async_remove_device=lambda device: let_go.append((device, 'removed')))
        camera.dr.async_get = lambda hass: registry
        # One as 2026.11 has it (the device is this entry's alone), one as before (a device of several entries).
        camera.dr.async_entries_for_config_entry = lambda registry, entry: [
            screen, types.SimpleNamespace(id='second', config_entry_id='video-1'), types.SimpleNamespace(id='before')]
        video.hass = object()
        asyncio.run(video.async_added_to_hass())
        self.assertEqual(let_go, [('second', 'removed'), ('before', 'video-1')])


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Endpoint(unittest.IsolatedAsyncioTestCase):
    """Settings, Video in Home Assistant, through the app's own routes. The editor's buttons, and that the restart waits
    for the person's yes, are web/tests/video-settings.spec.ts."""

    async def test_the_inventory_says_install_writes_and_restart_asks_home_assistant(self):
        class HA:
            online = True
            registry, devices, areas, states = [], [], [], {}
            changed = asyncio.Event()
            calls = []
            closes = False

            async def call_service(self, domain, service, data):
                self.calls.append((domain, service, data))
                if self.closes:
                    raise ConnectionError('Home Assistant went away: it restarts')

        with tempfile.TemporaryDirectory() as tmp:
            ha = HA()
            manager = Manager(ha, Path(tmp) / 'data' / 'screens.json')
            (Path(tmp) / 'config').mkdir()
            manager.videos = screen_video.Videos(screen_video.target(home_assistant(Path(tmp) / 'config')))
            async with TestClient(TestServer(create_app(manager, True))) as client:
                full = await (await client.get('/api/inventory')).json()
                self.assertEqual(full['video'], {**screen_video.status(manager.videos.directory), 'loaded': None,
                                                 'screens': [], 'entries': 0})
                self.assertFalse(full['video']['installed'])
                csrf = {'X-Screen-CSRF': full['csrf']}
                # Nothing restarts Home Assistant for a video it has not got.
                refused = await client.post('/api/video/restart', headers=csrf)
                self.assertEqual(refused.status, 409)
                self.assertEqual(ha.calls, [])
                self.assertEqual((await client.post('/api/video')).status, 403, 'CSRF like every other change')
                self.assertFalse(manager.videos.directory.exists(), 'written only on request')
                done = await (await client.post('/api/video', headers=csrf)).json()
                self.assertTrue(done['installed'] and done['current'] and done['restart'])
                self.assertTrue((manager.videos.directory / 'manifest.json').is_file())
                # Restarted as Home Assistant's own Restart does, which checks the configuration first; Home Assistant
                # may close the connection before it answers.
                for closes in (False, True):
                    ha.closes = closes
                    restarted = await client.post('/api/video/restart', headers=csrf)
                    self.assertEqual(await restarted.json(), {'restarting': True})
                self.assertEqual(ha.calls, [('homeassistant', 'restart', {})] * 2)
                # The zip for a Home Assistant the app cannot write to (GitHub #357): a download, nothing written.
                download = await client.get('/api/video.zip')
                self.assertEqual(download.status, 200)
                self.assertEqual(download.headers['Content-Type'], 'application/zip')
                self.assertEqual(await download.read(), screen_video.archive())


class Loops(unittest.TestCase):
    def test_the_app_runs_every_loop_of_its_manager(self):
        # A loop of the Manager that main() does not start never runs: the screens' video entries would never be kept.
        tree = ast.parse((ROOT / 'screen_manager/app/server.py').read_text())
        manager = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Manager')
        loops = {f.name for f in manager.body if isinstance(f, ast.AsyncFunctionDef) and f.name.endswith('_loop')}
        main = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'main')
        started = {call.func.attr for call in ast.walk(main) if isinstance(call, ast.Call)
                   and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                   and call.func.value.id == 'manager'}
        self.assertIn('video_loop', loops)
        self.assertEqual(loops - started, set(), 'every Manager.*_loop is started in server.py main(), in its asyncio.gather '
                                                 'with the others')


if __name__ == '__main__':
    unittest.main()
