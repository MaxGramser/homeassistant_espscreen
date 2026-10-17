"""One way to keep a file of the app's own (screen_manager/app/atomic.py): written whole or not at all, and one rule for
a file the app cannot read. Every store of the app goes through it, so no copy of the write can drift."""
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'screen_manager/app'
sys.path.insert(0, str(APP))
import atomic  # noqa: E402


class Writing(unittest.TestCase):
    def test_the_file_is_whole_and_nothing_is_left_beside_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'deep' / 'store.json'
            atomic.write_json(path, {'version': 1, 'a': 'é'}, indent=1)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'version': 1, 'a': 'é'})
            self.assertEqual(oct(path.stat().st_mode & 0o777), '0o600')
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ['store.json'])
            atomic.write_text(path, 'second\n', mode=0o644)
            self.assertEqual(path.read_text(), 'second\n')
            self.assertEqual(oct(path.stat().st_mode & 0o777), '0o644')
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ['store.json'])

    def test_a_write_that_fails_leaves_the_old_file_and_no_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'store.json'
            atomic.write_text(path, 'old\n')
            class Broken:
                def __str__(self): raise RuntimeError('no text')
            with self.assertRaises(TypeError):
                atomic.write_text(path, Broken())   # handle.write refuses what is not a str
            self.assertEqual(path.read_text(), 'old\n')
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ['store.json'])


class Reading(unittest.TestCase):
    def test_no_file_is_an_empty_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(atomic.read_json(Path(tmp) / 'none.json', 1))
            self.assertFalse(atomic.frozen(Path(tmp) / 'none.json'))

    def test_a_readable_store_comes_back_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'store.json'
            atomic.write_json(path, {'version': 2, 'screens': {'a': 1}})
            self.assertEqual(atomic.read_json(path, 2), {'version': 2, 'screens': {'a': 1}})
            self.assertEqual(atomic.read_json(path, (1, 2)), {'version': 2, 'screens': {'a': 1}})

    def test_a_file_that_is_no_json_is_set_aside_and_the_store_starts_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'store.json'
            path.write_text('{"version": 1, "screens": {"a": ')   # half a write of an app from before this helper
            with self.assertLogs('screen_manager', 'ERROR') as logs:
                self.assertIsNone(atomic.read_json(path, 1))
            self.assertIn('store.json.unreadable', logs.output[0])
            self.assertFalse(path.exists())
            self.assertEqual((path.parent / 'store.json.unreadable').read_text(), '{"version": 1, "screens": {"a": ')
            # The store may be written again: it starts over, the person's file is beside it.
            atomic.write_json(path, {'version': 1, 'screens': {}})
            self.assertEqual(atomic.read_json(path, 1), {'version': 1, 'screens': {}})
            # A list is no store either.
            path.write_text('[1, 2]')
            with self.assertLogs('screen_manager', 'ERROR'):
                self.assertIsNone(atomic.read_json(path, 1))
            self.assertEqual((path.parent / 'store.json.unreadable').read_text(), '[1, 2]')

    def test_a_file_of_another_version_is_left_exactly_as_it_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'store.json'
            newer = '{"version": 7, "screens": {"future": true}}\n'
            path.write_text(newer)
            with self.assertLogs('screen_manager', 'ERROR') as logs:
                self.assertIsNone(atomic.read_json(path, 1))
            self.assertIn('version 7', logs.output[0])
            self.assertTrue(atomic.frozen(path))
            self.assertEqual(path.read_text(), newer)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ['store.json'])
            # Nothing of this app's goes over it, until the app that wrote it reads it again.
            with self.assertRaises(atomic.Frozen):
                atomic.write_json(path, {'version': 1, 'screens': {}})
            self.assertIsInstance(atomic.Frozen(), OSError)
            self.assertEqual(path.read_text(), newer)
            self.assertEqual(atomic.read_json(path, 7), {'version': 7, 'screens': {'future': True}})
            self.assertFalse(atomic.frozen(path))
            atomic.write_json(path, {'version': 7, 'screens': {}})


class OneWay(unittest.TestCase):
    def test_no_store_writes_a_file_of_its_own(self):
        """Every write of the app's own files goes through atomic.py: a temporary file, an fsync and a rename written
        again somewhere else is the eleventh copy with the twelfth policy. The one exception is the layout store's backup,
        which links a file into place because a backup refuses to replace an earlier one."""
        own = re.compile(r'mkstemp|NamedTemporaryFile|\.tmp[\'"]|os\.replace\(|\.replace\((?:path|self\.path|target)\)')
        found = {}
        for path in sorted(APP.glob('*.py')):
            if path.name == 'atomic.py':
                continue
            for number, line in enumerate(path.read_text().split('\n'), 1):
                if own.search(line):
                    found.setdefault(path.name, []).append(number)
        self.assertEqual(found, {'layout_store.py': found.get('layout_store.py', [])})
        self.assertLessEqual(len(found.get('layout_store.py', [])), 1, found)

    def test_every_store_reads_through_the_helper(self):
        for name in ('page_capabilities', 'screen_hang', 'screen_labels', 'screen_saver', 'feedback', 'updates',
                     'plugin_likes', 'plugin_store', 'i18n'):
            self.assertIn('atomic.read_json(', (APP / f'{name}.py').read_text(), name)


if __name__ == '__main__':
    unittest.main()
