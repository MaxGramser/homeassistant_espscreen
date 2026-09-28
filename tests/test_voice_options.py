"""Saved add-on options govern voice independently of credentials and old flags."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_voice_preview  # Makes the add-on imports available.
import voice_preview


class VoiceOptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_default_and_supervisor_require_explicit_opt_in(self):
        self.assertFalse(voice_preview.voice_enabled(self.data))
        os.environ.update(SUPERVISOR_TOKEN='test-only', SCREEN_VOICE_POC='1', SCREEN_VOICE_ENABLED='1')
        self.assertFalse(voice_preview.voice_enabled(self.data))
        for option in ('{}', '{"voice_assistant":false}', '{"voice_assistant":"true"}',
                       '{"voice_assistant":1}', 'null', '[]', 'broken JSON'):
            with self.subTest(option=option):
                (self.data / 'options.json').write_text(option)
                self.assertFalse(voice_preview.voice_enabled(self.data))
        (self.data / 'options.json').write_text('{"voice_assistant":true}')
        self.assertTrue(voice_preview.voice_enabled(self.data))

    def test_standalone_environment_and_legacy_flag_cannot_override_saved_options(self):
        os.environ['SCREEN_VOICE_POC'] = '1'
        self.assertTrue(voice_preview.voice_enabled(self.data))
        os.environ['SCREEN_VOICE_ENABLED'] = '0'
        self.assertFalse(voice_preview.voice_enabled(self.data))
        os.environ['SCREEN_VOICE_ENABLED'] = '1'
        self.assertTrue(voice_preview.voice_enabled(self.data))
        (self.data / 'options.json').write_text('{"voice_assistant":false}')
        self.assertFalse(voice_preview.voice_enabled(self.data))

    def test_disabling_does_not_load_or_delete_private_voice_settings(self):
        manager = SimpleNamespace(path=self.data / 'screens.json', ha=SimpleNamespace(registry=[]))
        settings = {'provider': 'claude', 'idle_seconds': 6, 'reply_speaker': 'media_player.reply', 'reply_volume': 23}
        (self.data / 'voice-settings.json').write_text(json.dumps(settings))
        for name in ('voice-api-key', 'voice-claude-api-key'):
            (self.data / name).write_text('test-only-private-key')
        disabled = voice_preview.VoicePreview(manager)
        self.assertFalse(disabled.enabled)
        self.assertEqual((disabled.key, disabled.claude_key), ('', ''))
        self.assertEqual(disabled.provider, 'openai')
        (self.data / 'options.json').write_text('{"voice_assistant":true}')
        enabled = voice_preview.VoicePreview(manager)
        self.assertEqual((enabled.key, enabled.claude_key), ('test-only-private-key', 'test-only-private-key'))
        for key, value in settings.items():
            self.assertEqual(getattr(enabled, key), value)


if __name__ == '__main__':
    unittest.main()
