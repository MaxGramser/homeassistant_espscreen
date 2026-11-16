"""The release check (tools/i18n.py check) refuses a full language that misses a text, and lets a regional variant
inherit from its base language.

This proves the check, not today's files: on dev a new English text waits for its translations until the release
drafts them (docs/TRANSLATING.md, "Every release"), and falls back to English meanwhile. The files themselves are
checked where a release is: tools/check.sh translations_check."""
from contextlib import redirect_stdout
import copy
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch


def texts(data, prefix=''):
    """Every text's key in a language file, as `group.key`."""
    keys = set()
    for key, value in data.items():
        if key == '_meta' and not prefix:
            continue
        keys |= texts(value, f'{prefix}{key}.') if isinstance(value, dict) else {prefix + key}
    return keys


def only(data, keep, prefix=''):
    """`data` with the texts whose key is in `keep`, and its _meta."""
    out = {}
    for key, value in data.items():
        if key == '_meta' and not prefix:
            out[key] = value
        elif isinstance(value, dict):
            inner = only(value, keep, f'{prefix}{key}.')
            if inner:
                out[key] = inner
        elif prefix + key in keep:
            out[key] = value
    return out


class TranslationCompletenessTests(unittest.TestCase):
    def test_missing_editor_or_firmware_translation_fails(self):
        path = Path(__file__).resolve().parents[1] / 'tools/i18n.py'
        spec = importlib.util.spec_from_file_location('translation_check', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        live = module.languages()
        # The texts every full language has: the files as a release leaves them, with what dev added since left out.
        common = set.intersection(*(texts(data) for code, data in live.items() if '-' not in code))
        complete = {code: only(data, common) for code, data in live.items()}
        self.assertIn('en-GB', complete)
        self.assertLess(len(str(complete['en-GB'])), len(str(complete['en'])), 'en-GB overrides a few texts only')
        with patch.object(module, 'languages', return_value=copy.deepcopy(complete)), redirect_stdout(io.StringIO()):
            self.assertEqual(module.check(), 0, 'every full language complete, and en-GB inherits the rest from en')
        for group, key in [('editor.pages', 'title'), ('screen.status', 'configuration_problem')]:
            languages = copy.deepcopy(complete)
            target = languages['de']
            for part in group.split('.'): target = target[part]
            del target[key]
            output = io.StringIO()
            with patch.object(module, 'languages', return_value=languages), redirect_stdout(output):
                self.assertEqual(module.check(), 1, f'the release refuses German without {group}.{key}')
            self.assertIn(f'{group}.{key}', output.getvalue())


if __name__ == '__main__':
    unittest.main()
