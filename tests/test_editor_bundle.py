"""The editor's bundle the app serves (server.editor_bundle): every live answer names it, so a page that runs an older
editor reloads itself (web/src/stores/editor-version.ts, docs/BUILDS.md "After an update of the app")."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
import server  # noqa: E402


class EditorBundle(unittest.TestCase):
    def test_the_script_index_html_names(self):
        with tempfile.TemporaryDirectory() as folder:
            static = Path(folder)
            self.assertIsNone(server.editor_bundle(static))
            (static / 'index.html').write_text('<script type="module" crossorigin src="./assets/index-AbC_1-x.js"></script>')
            self.assertEqual(server.editor_bundle(static), 'index-AbC_1-x.js')

    def test_the_built_editor_is_named(self):
        self.assertRegex(server.EDITOR_BUNDLE or '', r'^index-[A-Za-z0-9_-]+\.js$')


if __name__ == '__main__':
    unittest.main()
