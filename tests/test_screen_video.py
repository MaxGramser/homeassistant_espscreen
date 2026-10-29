"""Video in Home Assistant (screen_video.py, ha_integration/tessera_video, docs/CAMERA.md "Live video").

The app ships Home Assistant's tessera_video integration and writes it into Home Assistant's configuration folder only
when a person presses Install; once Home Assistant restarted with it, the app keeps one entry of it for each screen with
Screen camera's part Video, through the integration's own config flow, and takes away the entry of a screen of its own
that lost the video. A device the app does not know keeps its entry. The integration and the firmware work the stream's
password out of the screen's API key the same way (Screen camera's components/screen_video/__init__.py).
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import screen_video  # noqa: E402

INTEGRATION = ROOT / 'screen_manager/app/ha_integration/tessera_video'


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
        # Home Assistant's list of entries has no unique id: the device registry says which device holds an entry.
        self.entries = [{k: v for k, v in e.items() if k != 'unique_id'} for e in entries]
        self.held = {e['entry_id']: e.get('unique_id') for e in entries}
        self.deleted, self.flows = [], {}

    @property
    def devices(self):
        if getattr(self, 'no_devices', False):
            return []
        return [{'id': device, 'config_entries': ['esphome-' + device, entry]} for entry, device in self.held.items()
                if device and any(e['entry_id'] == entry for e in self.entries)]

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
            self.entries.append({'entry_id': 'e' + device, 'title': device})
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


class Install(unittest.TestCase):
    def test_install_writes_the_integration_and_status_compares_it(self):
        with tempfile.TemporaryDirectory() as folder:
            target = screen_video.target(folder)
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
                                                           'version': screen_video.version()})

    def test_a_folder_that_cannot_be_written_says_so(self):
        with tempfile.TemporaryDirectory() as folder:
            blocked = Path(folder) / 'custom_components'
            blocked.write_text('a file where the folder goes')
            with self.assertRaises(ValueError):
                screen_video.install(blocked / 'tessera_video')

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

    def test_the_password_is_the_firmwares(self):
        # Screen camera's components/screen_video/__init__.py: sha256("tessera-video:" + key), its first 24 hex digits.
        const = (INTEGRATION / 'const.py').read_text()
        self.assertIn('PASSWORD_SALT = "tessera-video:"', const)
        self.assertIn('PASSWORD_LENGTH = 24', const)
        self.assertIn('PORT = 8554', const)
        self.assertIn('USER = "tessera"', const)
        camera = (INTEGRATION / 'camera.py').read_text()
        self.assertIn('hashlib.sha256((PASSWORD_SALT + (key or "")).encode()).hexdigest()[:PASSWORD_LENGTH]', camera)
        key = 'MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI='
        self.assertEqual(len(hashlib.sha256(('tessera-video:' + key).encode()).hexdigest()[:24]), 24)


class Screens(unittest.TestCase):
    def test_which_screens_have_the_video(self):
        wanted, without = screen_video.video_screens(FakePlugins(RECORDS), screens())
        self.assertEqual(wanted, {'dev-tablet': 'Tablet'})
        # The kitchen runs Screen camera without Video; the hall's build is under way, so it is in neither.
        self.assertEqual(without, {'dev-kitchen'})


class Sync(unittest.TestCase):
    def run_sync(self, ha, folder, installed=True):
        target = screen_video.target(folder)
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

    def test_an_entry_on_no_device_yet_is_not_added_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            # The tablet's entry is there, but its camera is on no device yet (the ESPHome device is not loaded).
            ha = FakeHA(entries=[{'entry_id': 'waiting', 'unique_id': 'dev-tablet', 'title': 'Tablet'}])
            ha.no_devices = True
            _, done = self.run_sync(ha, folder)
            self.assertEqual(done, {'added': [], 'removed': []})
            self.assertEqual(len(ha.entries), 1)


class Wiring(unittest.TestCase):
    def test_the_app_routes_and_the_editor(self):
        server = (ROOT / 'screen_manager/app/server.py').read_text()
        for needle in ("app.router.add_post('/api/video', install_video)", "app.router.add_post('/api/video/restart',",
                       "payload['video'] = manager.video_status()", 'manager.video_loop()',
                       "call_service('homeassistant', 'restart', {})"):
            self.assertIn(needle, server)
        view = (ROOT / 'web/src/components/AppSettingsView.vue').read_text()
        self.assertIn('id="video-install"', view)
        self.assertIn('id="video-restart"', view)
        # A P4's network buffers: the video's send buffer, and all of it in PSRAM first (docs/CAMERA.md,
        # components/smart_display/p4_build.py).
        component = (ROOT / 'components/smart_display/p4_build.py').read_text()
        self.assertIn('"CONFIG_LWIP_TCP_SND_BUF_DEFAULT": 65534', component)
        self.assertIn('"CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP": True', component)
        # Nothing restarts Home Assistant without the person's yes.
        self.assertIn('confirm(t("editor.settings.video.restart_confirm")', view)


if __name__ == '__main__':
    unittest.main()
