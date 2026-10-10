"""The plugin catalogue of plugin API 0.7 (docs/PLUGINS.md): what a plugin is about and what it adds, which plugin of an
id a screen runs (its origin), what comes along when a plugin needs another or needs a feature, and the plugins that
need one when it goes."""
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import plugin_manifest as pm  # noqa: E402

TESSERA = 'https://github.com/MaxGramser/tessera-plugins'


def manifest(plugin_id, **changes):
    return {'id': plugin_id, 'version': '1.0.0', 'api': '0.7', 'icon': 'puzzle', 'maintainer': 'someone',
            'license': 'MIT', 'topics': ['tech'], **changes}


def item(plugin_id, repo=TESSERA, **changes):
    return {'id': plugin_id, 'repo': repo, 'path': f'plugins/{plugin_id}', 'label': 'tessera',
            'release': {'version': '1.0.0', 'sha': 'a' * 40, 'date': '2026-10-09'},
            'manifest': manifest(plugin_id, **changes),
            'translations': {'en': {'app': {'name': plugin_id.title(), 'summary': 'x'}, 'screen': {}}}}


class Manifest(unittest.TestCase):
    def test_topics_are_the_makers_word_and_the_type_is_read(self):
        with self.assertRaises(pm.ManifestError):
            pm.check({k: v for k, v in manifest('clock').items() if k != 'topics'})
        with self.assertRaises(pm.ManifestError):
            pm.check(manifest('clock', topics=['cars']))
        # A newer index may name a topic this app does not know: the plugin stays, the topic goes.
        self.assertEqual(pm.check(manifest('clock', topics=['cars', 'time']), strict=False)['topics'], ['time'])
        self.assertEqual(pm.plugin_type(pm.check(manifest('audio', provides=['speaker']))), 'hardware')
        self.assertEqual(pm.plugin_type(pm.check(manifest('voice'))), 'functions')

    def test_a_feature_is_one_of_the_core_and_never_needed_by_its_bringer(self):
        with self.assertRaises(pm.ManifestError):
            pm.check(manifest('audio', provides=['laser']))
        with self.assertRaises(pm.ManifestError):
            pm.check(manifest('audio', provides=['speaker'], requires={'features': ['speaker']}))
        with self.assertRaises(pm.ManifestError):
            pm.check(manifest('voice', requires={'plugins': ['voice']}))
        # An unknown feature a plugin needs is kept when reading leniently, so it fits no screen.
        self.assertEqual(pm.check(manifest('voice', requires={'features': ['laser']}), strict=False)['requires']['features'],
                         ['laser'])

    def test_a_camera_sensor_only_a_board_brings(self):
        # Plugin API 0.8: the camera sensor is hardware a plugin drives; the board names its bus (CAMERA_I2C) and powers it.
        self.assertEqual(pm.BOARD_ONLY, ('camera_sensor',))
        with self.assertRaises(pm.ManifestError):
            pm.check(manifest('camera', provides=['camera_sensor']))
        camera = pm.check(manifest('camera', provides=['camera'], requires={'features': ['camera_sensor']}))
        self.assertEqual((camera['provides'], camera['requires']['features']), (['camera'], ['camera_sensor']))
        self.assertEqual(pm.FEATURES['camera'], ('esp_video_camera', 'ts_camera'))


class Catalogue(unittest.TestCase):
    def service(self, *items, board='guition'):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class FakeManager:
            ha = type('HA', (), {'states': {}, 'changed': asyncio.Event(), 'dirty': set()})()
            page_senders, aliases, firmware = {}, {}, None
            updates = type('Updates', (), {'resolve': lambda self, screen: (None, None)})()

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'name': inbox.title(), 'board': board}

            def screens(self):
                return [self.screen('kitchen')]

            def notify(self):
                pass
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        service._take_index({'format': 1, 'plugins': list(items)})
        return service

    def test_a_plugin_it_needs_comes_along(self):
        service = self.service(item('clock', requires={'plugins': ['base']}), item('base'))
        plan = service.plan('kitchen', {'add': [{'id': 'clock'}]})
        self.assertEqual([(s['id'], s['auto'], s['for']) for s in plan['add']],
                         [('clock', False, []), ('base', True, ['clock'])])

    def test_the_one_plugin_that_brings_a_feature_comes_along_and_two_ask_a_choice(self):
        audio = item('audio', provides=['speaker', 'microphone'])
        service = self.service(item('voice', requires={'features': ['microphone']}), audio)
        plan = service.plan('kitchen', {'add': [{'id': 'voice'}]})
        self.assertEqual([s['id'] for s in plan['add']], ['voice', 'audio'])
        service = self.service(item('voice', requires={'features': ['microphone']}), audio, item('mic', provides=['microphone']))
        plan = service.plan('kitchen', {'add': [{'id': 'voice'}]})
        self.assertEqual(plan['choose'], [{'feature': 'microphone', 'for': 'voice', 'options': ['audio', 'mic']}])
        plan = service.plan('kitchen', {'add': [{'id': 'voice'}], 'providers': {'microphone': 'mic'}})
        self.assertEqual([s['id'] for s in plan['add']], ['voice', 'mic'])
        # Nothing that brings it: the plugin does not fit, with its reason.
        service = self.service(item('voice', requires={'features': ['microphone']}))
        self.assertEqual(service.fits(service.index['voice'], {'id': 'kitchen', 'board': 'guition'}), 'feature')
        self.assertTrue(service.plan('kitchen', {'add': [{'id': 'voice'}]})['error'])

    def test_one_of_each_feature_on_a_screen(self):
        service = self.service(item('audio', provides=['speaker']), item('beeper', provides=['speaker']))
        service.store.put('kitchen', {'id': 'audio', 'source': 'index', 'repo': TESSERA, 'path': 'plugins/audio',
                                      'ref': 'a' * 40, 'version': '1.0.0'})
        service.keep_snapshot(service.index['audio'])
        self.assertTrue(service.plan('kitchen', {'add': [{'id': 'beeper'}]})['error'])

    def test_what_the_board_brings_no_plugin_brings_again(self):
        # The reTerminal D1001 brings a speaker, a microphone and a media player itself (boards.json `features`).
        audio = item('audio', provides=['speaker', 'microphone'])
        service = self.service(item('voice', requires={'features': ['microphone']}), audio, board='reterminald1001')
        self.assertEqual(service.fits(service.index['audio'], service.manager.screen('kitchen')), 'built_in')
        self.assertTrue(service.plan('kitchen', {'add': [{'id': 'audio'}]})['error'])
        plan = service.plan('kitchen', {'add': [{'id': 'voice'}]})
        self.assertEqual([s['id'] for s in plan['add']], ['voice'], 'nothing comes along: the board has the microphone')
        # A screen that had such a plugin before its board brought the feature builds without it, and the editor says why.
        service.store.put('kitchen', {'id': 'audio', 'source': 'index', 'repo': TESSERA, 'path': 'plugins/audio',
                                      'ref': 'a' * 40, 'version': '1.0.0'})
        service.keep_snapshot(service.index['audio'])
        self.assertNotIn('plugin_audio', service.sidecar('kitchen'))
        self.assertEqual(service.payload()['fit']['kitchen'].get('audio'), 'built_in')
        # On a board that brings none, the same plugin is built.
        other = self.service(audio)
        other.store.put('kitchen', {'id': 'audio', 'source': 'index', 'repo': TESSERA, 'path': 'plugins/audio',
                                    'ref': 'a' * 40, 'version': '1.0.0'})
        other.keep_snapshot(other.index['audio'])
        self.assertIn('plugin_audio', other.sidecar('kitchen'))

    def test_a_camera_plugin_fits_a_board_with_a_camera_sensor(self):
        # The reTerminal D1001 names its camera's bus (CAMERA_I2C): a plugin that drives the sensor fits it, alone; a board
        # without one has no plugin that could bring it.
        camera = item('camera', provides=['camera'], requires={'features': ['camera_sensor']})
        d1001 = self.service(camera, board='reterminald1001')
        self.assertIsNone(d1001.fits(d1001.index['camera'], d1001.manager.screen('kitchen')))
        self.assertEqual([s['id'] for s in d1001.plan('kitchen', {'add': [{'id': 'camera'}]})['add']], ['camera'])
        guition = self.service(camera)
        self.assertEqual(guition.fits(guition.index['camera'], guition.manager.screen('kitchen')), 'feature')

    def test_what_another_plugin_needs_goes_only_together_and_what_came_along_may_go(self):
        service = self.service(item('voice', requires={'features': ['microphone']}), item('audio', provides=['microphone']))
        asyncio.run(service.apply('kitchen', {'add': [{'id': 'voice'}]}))
        records = {r['id']: r for r in service.store.of('kitchen')}
        self.assertTrue(records['audio'].get('auto'))
        self.assertFalse(records['voice'].get('auto'))
        refused = service.plan('kitchen', {'remove': ['audio']})
        self.assertEqual(refused['needed_by'], {'audio': ['voice']})
        self.assertEqual(service.plan('kitchen', {'remove': ['voice']})['orphans'], ['audio'])
        self.assertIsNone(service.plan('kitchen', {'remove': ['voice', 'audio']})['error'])
        # Every source is built from one commit, never a branch's newest.
        self.assertNotIn('refresh: 0s', service.sidecar('kitchen'))

    def test_a_fork_of_the_same_id_never_gets_the_originals_secret_nor_its_screen(self):
        service = self.service(item('bus'))
        listed = service.index['bus']
        service.secrets.set('bus', 'key', 'secret-1', origin=listed.origin)
        fork = type(listed)(listed.raw, listed.translations, {}, 'link', 'community', repo='https://github.com/someone/bus',
                            ref='b' * 40)
        self.assertEqual(service.secret_values(listed), {'key': 'secret-1'})
        self.assertEqual(service.secret_values(fork), {})
        # The same repository written another way is the same origin.
        self.assertEqual(fork.origin, 'github.com/someone/bus')
        asyncio.run(service.apply('kitchen', {'add': [{'id': 'bus'}]}))
        service.links['bus'] = fork
        with self.assertRaises(ValueError):
            asyncio.run(service.apply('kitchen', {'add': [{'id': 'bus', 'source': 'link'}]}))
        asyncio.run(service.apply('kitchen', {'add': [{'id': 'bus', 'source': 'link', 'switch': True}]}))
        self.assertEqual(service.store.get('kitchen', 'bus')['repo'], 'https://github.com/someone/bus')


if __name__ == '__main__':
    unittest.main()
