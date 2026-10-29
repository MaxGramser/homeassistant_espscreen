"""tools/config_diff.py compares what a board builds, not how its files list it (docs/PROFILES.md, "Parts")."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import config_diff


class ConfigDiff(unittest.TestCase):
    def test_code_keeps_its_lines_and_loses_its_blank_ones(self):
        code = 'a();\n\n   \nb();  \n'
        self.assertEqual(config_diff.canonical(code, {}), 'a();\nb();')
        self.assertEqual(config_diff.canonical(('!lambda', code), {}), ('!lambda', 'a();\nb();'))

    def test_a_side_s_folders_go_by_their_names(self):
        self.assertEqual(config_diff.canonical({'path': '/tmp/x/tree/components'}, {'<tree>': Path('/tmp/x/tree')}),
                         {'path': '<tree>/components'})

    def test_an_action_list_keeps_its_order(self):
        actions = [{'lambda': 'b();'}, {'lambda': 'a();'}]
        self.assertEqual(config_diff.canonical(actions, {}), actions)

    def test_the_differences_name_their_place(self):
        before = {'switch': [{'id': 'amp', 'pin': {'number': 1}}], 'gone': 1}
        after = {'switch': [{'id': 'amp', 'pin': {'number': 2}}]}
        self.assertEqual(config_diff.differences(before, after),
                         [('gone', 1, '<none>'), ('switch[0].pin.number', 1, 2)])
        self.assertEqual(config_diff.differences(before, before), [])

    def test_the_made_up_api_key_is_one_esphome_takes(self):
        import base64
        key = base64.b64decode(config_diff.SECRETS['api_encryption_key'])
        self.assertEqual(len(key), 32)
        self.assertNotEqual(key, bytes(32))


if __name__ == '__main__':
    unittest.main()
