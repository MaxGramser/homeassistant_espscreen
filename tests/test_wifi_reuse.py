import json
import sys
import tempfile
import unittest
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
from firmware import Firmware

class WifiReuse(unittest.TestCase):
    def test_existing_wifi_reused_without_browser_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            path = Path(tmp) / 'secrets.yaml'
            original = '# keep comments\nwifi_ssid: example-private-network\nwifi_password: example-private-password\nother_secret: leave-me\n'
            path.write_text(original)
            self.assertEqual(f.wifi_status()['state'], 'ready')
            self.assertNotIn('example-private', json.dumps(f.status()))
            f.create({'board': 'guition', 'name': 'second-screen', 'friendly_name': 'Second'})
            self.assertEqual(path.read_text(), original)
            profile = f.profile('second-screen.yaml').read_text()
            self.assertIn('ssid: !secret wifi_ssid', profile)
            self.assertIn('password: !secret wifi_password', profile)
            self.assertNotIn('example-private', profile)

    def test_missing_keys_are_added_without_touching_other_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            path = Path(tmp) / 'secrets.yaml'
            original = '# keep comments\nother: keep\nwifi_ssid: ""\n'
            path.write_text(original)
            self.assertEqual(f.wifi_status(), {'state': 'missing', 'missing': ['wifi_password', 'wifi_ssid']})
            # Without values nothing is written: no profile, secrets untouched.
            with self.assertRaises(ValueError):
                f.create({'board': 'cyd', 'name': 'screen', 'friendly_name': 'Screen'})
            self.assertEqual(path.read_text(), original)
            self.assertFalse((Path(tmp) / 'screen.yaml').exists())
            f.create({'board': 'cyd', 'name': 'screen', 'friendly_name': 'Screen',
                      'wifi_ssid': 'home: net', 'wifi_password': 'p\\ss "word"'})
            text = path.read_text()
            self.assertTrue(text.startswith('# keep comments\nother: keep\n'))
            self.assertEqual(text.count('wifi_ssid'), 1)
            self.assertEqual(yaml.safe_load(text), {'other': 'keep', 'wifi_ssid': 'home: net', 'wifi_password': 'p\\ss "word"'})
            self.assertEqual(f.wifi_status()['state'], 'ready')
            self.assertTrue((Path(tmp) / 'screen.yaml').exists())

    def test_another_network_replaces_both_lines_and_keeps_the_rest(self):
        # New screen -> Another network (app 0.4.32): a screen that did not come online gets the right Wi-Fi.
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            path = Path(tmp) / 'secrets.yaml'
            path.write_text('# keep comments\nwifi_ssid: old-net\nwifi_password: old-pass\nother: keep\n')
            f.change_wifi({'wifi_ssid': 'new: net', 'wifi_password': 'p "w"'})
            text = path.read_text()
            self.assertTrue(text.startswith('# keep comments\n'))
            self.assertEqual(yaml.safe_load(text), {'wifi_ssid': 'new: net', 'wifi_password': 'p "w"', 'other': 'keep'})
            self.assertNotIn('new: net', json.dumps(f.status()))
            with self.assertRaises(ValueError):
                f.change_wifi({'wifi_ssid': ' ', 'wifi_password': 'x'})
            # No file yet: it is made, readable by the add-on alone.
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            f.change_wifi({'wifi_ssid': 'net', 'wifi_password': 'pw'})
            self.assertEqual(yaml.safe_load((Path(tmp) / 'secrets.yaml').read_text()), {'wifi_ssid': 'net', 'wifi_password': 'pw'})
            self.assertEqual(f.wifi_status()['state'], 'ready')

    def test_the_hotspot_says_which_screen_it_is_within_32_bytes(self):
        # "Tessera" and the screen's name as Tessera shows it (app 0.4.63); a network name holds at most 32 bytes.
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            (Path(tmp) / 'secrets.yaml').write_text('wifi_ssid: net\nwifi_password: pw\n')
            for name, friendly, expected in (('hall', 'Hall', 'Tessera Hall'),
                                             ('long', 'The living room by the big window', 'Tessera The living room by the'),
                                             ('keuken', 'Küche über dem Café Größe', None)):
                f.create({'board': 'guition', 'name': name, 'friendly_name': friendly})
                text = f.profile(f'{name}.yaml').read_text()
                ssid = yaml.safe_load(text.split('captive_portal:')[0].split('wifi:')[1].replace('!secret ', ''))['ap']['ssid']
                self.assertLessEqual(len(ssid.encode('utf-8')), 32, ssid)
                self.assertTrue(ssid.startswith('Tessera '), ssid)
                if expected:
                    self.assertEqual(ssid, expected)

    def test_invalid_secrets_are_never_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            path = Path(tmp) / 'secrets.yaml'
            path.write_text('wifi_ssid: [invalid')
            with self.assertRaises(ValueError):
                f.create({'board': 'cyd', 'name': 'screen', 'friendly_name': 'Screen',
                          'wifi_ssid': 'net', 'wifi_password': 'pw'})
            self.assertEqual(path.read_text(), 'wifi_ssid: [invalid')
            self.assertFalse((Path(tmp) / 'screen.yaml').exists())
            with self.assertRaises(ValueError):
                f.change_wifi({'wifi_ssid': 'net', 'wifi_password': 'pw'})
            self.assertEqual(path.read_text(), 'wifi_ssid: [invalid')

    def test_a_file_of_comments_only_has_no_keys_yet(self):
        # ESPHome's Device Builder leaves a secrets.yaml of comments only (#263): ESPHome reads it as empty, and so does
        # the wizard, which adds the two lines below the comments instead of calling the file invalid.
        comments = '# Your secrets, café wifi and all\n# wifi_ssid: "REPLACEME"\n# wifi_password: "REPLACEME"'
        for original in (comments, comments + '\n', '', '\n\n'):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as tmp:
                f = Firmware(tmp, tmp)
                path = Path(tmp) / 'secrets.yaml'
                path.write_text(original)
                self.assertEqual(f.wifi_status(), {'state': 'missing', 'missing': ['wifi_ssid', 'wifi_password']})
                f.create({'board': 'cyd', 'name': 'screen', 'friendly_name': 'Screen',
                          'wifi_ssid': 'net', 'wifi_password': 'pw'})
                text = path.read_text()
                self.assertTrue(text.startswith(original))
                self.assertEqual(yaml.safe_load(text), {'wifi_ssid': 'net', 'wifi_password': 'pw'})
                self.assertEqual(f.wifi_status()['state'], 'ready')
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            path = Path(tmp) / 'secrets.yaml'
            path.write_text(comments + '\n')
            f.change_wifi({'wifi_ssid': 'other', 'wifi_password': 'secret'})
            self.assertTrue(path.read_text().startswith(comments + '\n'))
            self.assertEqual(yaml.safe_load(path.read_text()), {'wifi_ssid': 'other', 'wifi_password': 'secret'})

    def test_a_document_that_is_no_mapping_stays_untouched(self):
        # `~`, `---` or a list parse without error but are not a file of secrets: invalid, never rewritten.
        for original in ('~\n', 'null\n', '---\n', '[]\n', '- a\n'):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as tmp:
                f = Firmware(tmp, tmp)
                path = Path(tmp) / 'secrets.yaml'
                path.write_text(original)
                self.assertEqual(f.wifi_status(), {'state': 'invalid'})
                with self.assertRaises(ValueError):
                    f.create({'board': 'cyd', 'name': 'screen', 'friendly_name': 'Screen',
                              'wifi_ssid': 'net', 'wifi_password': 'pw'})
                with self.assertRaises(ValueError):
                    f.change_wifi({'wifi_ssid': 'net', 'wifi_password': 'pw'})
                self.assertEqual(path.read_text(), original)

    def test_lines_that_would_break_the_file_are_not_written(self):
        # A flow mapping on one line reads fine, but a line added below it would not: the file stays as it was.
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            path = Path(tmp) / 'secrets.yaml'
            original = '{other: keep,\n'
            path.write_text(original)
            self.assertEqual(f.wifi_status(), {'state': 'invalid'})
            original = '{other: keep}'
            path.write_text(original)
            self.assertEqual(f.wifi_status()['state'], 'missing')
            with self.assertRaises(ValueError):
                f.change_wifi({'wifi_ssid': 'net', 'wifi_password': 'pw'})
            self.assertEqual(path.read_text(), original)

    def test_install_checks_port_and_busy_slot_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            data = {'board': 'cyd', 'name': 'screen', 'friendly_name': 'Screen', 'wifi_ssid': 'net', 'wifi_password': 'pw'}
            with self.assertRaises(ValueError):
                f.install({**data, 'target': '/dev/ttyUSB0'})
            self.assertFalse((Path(tmp) / 'screen.yaml').exists())
            self.assertFalse((Path(tmp) / 'secrets.yaml').exists())
            result = f.install(data)
            self.assertEqual(result['file'], 'screen.yaml')
            self.assertEqual(len(result['api_key']), 44)
            self.assertNotIn('job', result)
            self.assertIn(result['api_key'], f.profile('screen.yaml').read_text())
            meta = f.profile_names()['screen.yaml']
            self.assertEqual((meta['screen'], meta['api_key']), (True, result['api_key']))
            (Path(tmp) / 'other.yaml').write_text('esphome:\n  name: other\napi:\n  encryption:\n    key: !secret k\n')
            self.assertEqual((f.profile_names()['other.yaml']['screen'], f.profile_names()['other.yaml']['api_key']), (False, None))

    def test_first_install_and_invalid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            self.assertEqual(f.wifi_status()['state'], 'new')
            f.create({'board': 'cyd', 'name': 'screen', 'friendly_name': 'Screen',
                      'wifi_ssid': 'network', 'wifi_password': ''})
            self.assertEqual(f.wifi_status()['state'], 'ready')
            (Path(tmp) / 'secrets.yaml').write_text('wifi_ssid: [invalid')
            self.assertEqual(f.wifi_status(), {'state': 'invalid'})
