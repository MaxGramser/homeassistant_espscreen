"""Peripheral text tables keep their indices without carrying unused audio strings."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/smart_display'))
import screen_text_gen as texts


class OptionalAudio(unittest.TestCase):
    def test_voice_words_are_only_in_the_opted_in_build(self):
        _, on = texts.definitions('en', audio=True, audio_tests=False, voice=True)
        for audio, diagnostics in ((False, False), (True, False), (True, True)):
            _, off = texts.definitions('en', audio=audio, audio_tests=diagnostics, voice=False)
            self.assertEqual(on.splitlines()[0], off.splitlines()[0])
            for word in ('Start voice', 'Stop voice', 'Listening'):
                self.assertIn(texts.cpp_string(word), on)
                self.assertNotIn(texts.cpp_string(word), off)

    def test_text_features_keep_the_abi_and_omit_disabled_words(self):
        _, off = texts.definitions('en', audio=False, audio_tests=False)
        _, hardware = texts.definitions('en', audio=True, audio_tests=False)
        _, diagnostic = texts.definitions('en', audio=True, audio_tests=True)
        self.assertEqual(off.splitlines()[0], hardware.splitlines()[0])
        self.assertEqual(off.splitlines()[0], diagnostic.splitlines()[0])
        for word in ('Microphone mute', 'Automatic gain', 'Speaker volume'):
            self.assertNotIn(texts.cpp_string(word), off)
            self.assertIn(texts.cpp_string(word), hardware)
        for word in ('Test microphone', 'Playing recording', 'No wake word detected'):
            self.assertNotIn(texts.cpp_string(word), off)
            self.assertNotIn(texts.cpp_string(word), hardware)
            self.assertIn(texts.cpp_string(word), diagnostic)
