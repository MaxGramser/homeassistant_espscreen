"""Opt-in audio needs its components and settings without changing the default build."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import generate_entries
import profiles


class AudioVariants(unittest.TestCase):
    def test_metadata_includes_optional_transport_but_default_resolution_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / 'board.yaml').write_text(
                'packages:\n  audio: !include audio/${TRANSPORT}.yaml\n'
                'substitutions:\n  TRANSPORT: "i2s"\n')
            (root / 'audio').mkdir()
            (root / 'audio/i2s.yaml').write_text('microphone:\n  - platform: i2s_audio\n')
            (root / 'audio/aec.yaml').write_text('packages:\n  shared: !include ../shared.yaml\n')
            (root / 'shared.yaml').write_text('esp_aec:\n  id: board_aec\n')
            normal = profiles.chain(root / 'board.yaml')
            metadata = profiles.chain(root / 'board.yaml', all_variants=True)
            self.assertNotIn(root / 'audio/aec.yaml', normal)
            self.assertNotIn(root / 'shared.yaml', normal)
            self.assertIn(root / 'audio/aec.yaml', metadata)
            self.assertIn(root / 'shared.yaml', metadata)
            self.assertEqual(profiles.substitutions_of(root / 'board.yaml')['TRANSPORT'], 'i2s')

    def test_tab5_takes_echo_cancellation_by_default(self):
        self.assertEqual(profiles.substitutions('checkout/tab5.yaml')['TAB5_AUDIO_TRANSPORT'], 'aec')
        self.assertEqual(profiles.substitutions('checkout/tab5.yaml')['AUDIO_HALF_DUPLEX'], 'false')
        self.assertIn('es7210_extended', generate_entries.components('tab5'))
        self.assertIn('esp_aec', generate_entries.components('tab5'))
        default_files = profiles.chain(profiles.BOARDS['tab5'])
        self.assertIn(ROOT / 'packages/hardware/es7210-aec.yaml', default_files)
        self.assertNotIn('esp_aec', generate_entries.components('cyd'))
        self.assertNotIn('es7210_extended', generate_entries.components('cyd'))


if __name__ == '__main__':
    unittest.main()
