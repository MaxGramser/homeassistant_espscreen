"""A board file declares its parts and pins, nothing else (docs/PLATFORM_PLAN.md 3.7, "Declare below, resolve above").

The rule is `packages:` and `substitutions:`: the board names its parts (packages/hardware/parts/) and gives their pins
and sizes, and the part files turn that into ESPHome's components. Most board files still hold components of their
own, so this test is a ratchet: STILL_HELD lists, per top-level key, the board files that may still hold it. A key or a
board not listed fails, so nothing new lands in a board file; a listed board that no longer holds its key fails too, so
the list is shortened as each board moves to parts, and a key leaves once its boards are gone. The panels and touch move
last, because their blocks carry each board's LVGL settings today. STILL_TO_MOVE holds what a move left behind on
purpose (an old name kept for a release, a feature that waits for its part). When it passes, the test says what is
left."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARDS = ROOT / 'packages' / 'boards'
DECLARATIONS = {'packages', 'substitutions'}
# Per top-level key, the board files (their names without .yaml) that still hold it, panels and touch last.
STILL_HELD = {
    'audio_adc': ('reterminald1001',),
    'audio_dac': ('reterminald1001',),
    'binary_sensor': ('reterminald1001',),
    'esp32': (
        'crowpanel101', 'cyd-2432s028', 'freenove-fnk0104s', 'guition-4848s040', 'guition-jc3248w535',
        'guition-jc8012p4a1-v3', 'guition-jc8048w550c-i', 'hosyond40', 'reterminald1001', 'seeed-sensecap-indicator-d1',
        'sunton-8048s070', 'waveshare-esp32s3-35', 'waveshare-esp32s3-43', 'waveshare-esp32s3-4b',
        'waveshare-esp32s3-4v4', 'waveshare-esp32s3-7', 'waveshare-esp32s3-7b', 'waveshare101', 'waveshare43c',
        'wavesharep4', 'wavesharep47', 'wavesharep47b', 'wt32sc01plus',
    ),
    'esp_ldo': ('crowpanel101',),
    'esphome': (
        'cyd-2432s028-ili9342', 'guition-jc1060p470-v2', 'guition-jc1060p470', 'guition-jc4880p443',
        'guition-jc8012p4a1-v2', 'guition-jc8012p4a1-v3', 'guition-jc8012p4a1', 'reterminald1001', 'tab5',
        'waveshare-esp32s3-4v4', 'waveshare-esp32s3-7b', 'waveshare101', 'waveshare43c', 'wavesharep4', 'wavesharep47',
        'wavesharep47b',
    ),
    'globals': ('reterminald1001',),
    'i2c': (
        'freenove-fnk0104s', 'guition-4848s040', 'guition-jc3248w535', 'guition-jc8048w550c-i', 'reterminald1001',
        'seeed-sensecap-indicator-d1', 'sunton-8048s070', 'waveshare-esp32s3-35', 'waveshare-esp32s3-4b',
        'waveshare-esp32s3-4v4', 'wt32sc01plus',
    ),
    'i2s_audio': ('crowpanel101', 'reterminald1001',),
    'interval': ('reterminald1001',),
    'light': ('guition-jc8048w550c-i', 'waveshare-esp32s3-4b',),
    'logger': (
        'guition-4848s040', 'guition-jc8048w550c-i', 'reterminald1001', 'seeed-sensecap-indicator-d1',
        'sunton-8048s070', 'waveshare-esp32s3-4b', 'waveshare-esp32s3-4v4', 'waveshare-esp32s3-7b', 'waveshare43c',
        'wavesharep47b',
    ),
    'microphone': ('crowpanel101',),
    'motion': ('reterminald1001',),
    'output': (
        'crowpanel101', 'cyd-2432s028', 'freenove-fnk0104s', 'guition-4848s040', 'guition-jc3248w535',
        'guition-jc8048w550c-i', 'hosyond40', 'reterminald1001', 'seeed-sensecap-indicator-d1', 'sunton-8048s070',
        'waveshare-esp32s3-35', 'waveshare-esp32s3-4b', 'waveshare-esp32s3-4v4', 'waveshare101', 'wavesharep4',
        'wavesharep47', 'wavesharep47b', 'wt32sc01plus',
    ),
    'pca9554': ('seeed-sensecap-indicator-d1', 'waveshare-esp32s3-35', 'waveshare-esp32s3-4b',),
    'psram': ('freenove-fnk0104s', 'guition-jc3248w535', 'waveshare-esp32s3-35', 'wt32sc01plus',),
    'script': ('reterminald1001',),
    'sensor': ('reterminald1001',),
    'speaker': ('crowpanel101',),
    'spi': (
        'cyd-2432s028', 'freenove-fnk0104s', 'guition-4848s040', 'guition-jc3248w535', 'hosyond40',
        'seeed-sensecap-indicator-d1', 'waveshare-esp32s3-35', 'waveshare-esp32s3-4b', 'waveshare-esp32s3-4v4',
        'wt32sc01plus',
    ),
    'switch': (
        'crowpanel101', 'reterminald1001', 'seeed-sensecap-indicator-d1', 'tab5', 'waveshare-esp32s3-4v4',
        'wavesharep4',
    ),
    'text_sensor': ('guition-4848s040', 'guition-jc8012p4a1',),
    'time': ('reterminald1001',),
    'waveshare_io_ch32v003': ('waveshare-esp32s3-4v4',),
    'xl9535': ('reterminald1001',),
    'display': (
        'crowpanel101', 'cyd-2432s028-ili9342', 'cyd-2432s028', 'freenove-fnk0104s', 'guition-4848s040',
        'guition-jc1060p470-v2', 'guition-jc1060p470', 'guition-jc3248w535', 'guition-jc4880p443',
        'guition-jc8012p4a1-v2', 'guition-jc8012p4a1-v3', 'guition-jc8012p4a1', 'guition-jc8048w550c-i', 'hosyond40',
        'reterminald1001', 'seeed-sensecap-indicator-d1', 'sunton-8048s070', 'tab5', 'waveshare-esp32s3-35',
        'waveshare-esp32s3-43', 'waveshare-esp32s3-4b', 'waveshare-esp32s3-4v4', 'waveshare-esp32s3-7',
        'waveshare-esp32s3-7b', 'waveshare101', 'waveshare43c', 'wavesharep4', 'wavesharep47', 'wavesharep47b',
        'wt32sc01plus',
    ),
    'touchscreen': (
        'crowpanel101', 'cyd-2432s028', 'freenove-fnk0104s', 'guition-4848s040', 'guition-jc3248w535',
        'guition-jc4880p443', 'guition-jc8012p4a1', 'guition-jc8048w550c-i', 'hosyond40', 'reterminald1001',
        'seeed-sensecap-indicator-d1', 'sunton-8048s070', 'tab5', 'waveshare-esp32s3-35', 'waveshare-esp32s3-4b',
        'waveshare-esp32s3-4v4', 'waveshare101', 'wavesharep4', 'wavesharep47', 'wavesharep47b', 'wt32sc01plus',
    ),
}

# What a move to parts left behind on purpose, each with the text that says so in its file: a debt, listed here so it
# does not stay. A line goes when its text is gone.
STILL_TO_MOVE = {
    'packages/hardware/parts/es7210-controls.yaml':
        'becomes one that comes along by itself once the part declares AUDIO_MIC_ALC: true',
    'packages/boards/tab5.yaml': 'TAB5_AUDIO_TRANSPORT, its old name,',
    'packages/hardware/wavesharep4-audio.yaml': 'P4_AUDIO_TRANSPORT, its old name,',
}


def keys(path):
    """The top-level keys of a board file, as written."""
    return set(re.findall(r'^([a-z_0-9]+):', path.read_text(), re.M))


class BoardDeclarations(unittest.TestCase):
    def test_a_board_file_holds_only_what_is_listed(self):
        for path in sorted(BOARDS.glob('*.yaml')):
            for key in sorted(keys(path) - DECLARATIONS):
                self.assertIn(path.stem, STILL_HELD.get(key, ()),
                              f'{path.name} holds `{key}:`: a part file under packages/hardware/parts/ resolves it')

    def test_the_list_only_shrinks(self):
        for key, boards in STILL_HELD.items():
            self.assertNotIn(key, DECLARATIONS)
            for board in boards:
                path = BOARDS / f'{board}.yaml'
                self.assertTrue(path.exists(), f'{board} has no board file: take it out of STILL_HELD')
                self.assertIn(key, keys(path), f'{board} no longer holds `{key}:`: take it out of STILL_HELD')

    def test_every_debt_is_still_there(self):
        for name, text in STILL_TO_MOVE.items():
            path = ROOT / name
            self.assertTrue(path.exists() and text in ' '.join(path.read_text().replace('#', ' ').split()),
                            f'{name} no longer says "{text}": take it out of STILL_TO_MOVE')

    def test_what_is_left(self):
        left = sorted(STILL_HELD.items(), key=lambda item: -len(item[1]))
        print('\nBoard files still hold: ' + ', '.join(f'{key} {len(boards)}' for key, boards in left)
              + f'; {len(STILL_TO_MOVE)} debts of the moves to parts', file=sys.stderr)


if __name__ == '__main__':
    unittest.main()
