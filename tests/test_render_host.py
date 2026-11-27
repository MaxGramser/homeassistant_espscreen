"""The host build of tools/render/ (app 0.2.129): every board of the catalog becomes a host program the same way.

tools/render/run.py compiles these and runs their self test (tools/check.sh --render, CI's render job), which needs
ESPHome and SDL2. This checks the part before the compiler on every run of the fast checks, so a change to the shape
of packages/core.yaml or of a board file that the host build cuts out is noticed here first.
"""
import dataclasses
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'render'))
sys.path.insert(0, str(ROOT / 'tools'))
import host  # noqa: E402
import profiles  # noqa: E402


class HostBuild(unittest.TestCase):
    def test_every_board_hangs_every_way_it_can(self):
        keys = [item.key for item in host.variants()]
        self.assertEqual([key for key in keys if not key.endswith('-portrait')], list(profiles.CATALOG))
        # Square glass hangs one way; the others both, standing up at the angle ESP Screens writes into the screen.
        self.assertNotIn('guition-portrait', keys)
        self.assertIn('waveshare43-portrait', keys)
        self.assertEqual(len({item.port for item in host.variants()}), len(keys))
        # Each is a program of its own under a name ESPHome takes (31 characters at most), with a plugin in it as well
        # (tools/render/run.py --plugin): render-freenovefnk0104s-portrait is 32, and ESPHome refused that build.
        names = [item.name for item in host.variants()]
        names += [dataclasses.replace(item, key=f'{item.key}-plugin').name for item in host.variants()]
        self.assertEqual(len(set(names)), len(names))
        self.assertLessEqual(max(map(len, names)), host.NAME_LIMIT)
        self.assertEqual(host.variant('guition').name, 'render-guition')
        self.assertEqual(host.variant('waveshare43-portrait').name, 'render-waveshare43-portrait')
        self.assertEqual(host.variant('freenovefnk0104s-portrait').name, 'render-freenovefnk0104s-tall')

    def test_a_board_says_which_esphome_its_host_build_needs(self):
        # The board file's own min_version, else the core's: tools/render/run.py skips a board that asks for a newer
        # ESPHome than the one running, as tools/check.sh skips its firmware build (board_needs).
        floor = lambda board: host.esphome_floor(ROOT, profiles.CATALOG[board]['file'])  # noqa: E731
        core = tuple(map(int, re.search(r'(?m)^  min_version: (\S+)', profiles.CORE.read_text())[1].split('.')))
        self.assertEqual(floor('guition'), core)
        self.assertEqual(floor('reterminalsticky'), (2026, 11, 0))
        for board, path in profiles.BOARDS.items():
            own = re.search(r'(?m)^  min_version: (\S+)', path.read_text())
            self.assertEqual(floor(board), tuple(map(int, own[1].split('.'))) if own else core, board)

    def test_every_variant_gets_a_host_package_without_its_hardware(self):
        with tempfile.TemporaryDirectory() as tmp:
            for item in host.variants():
                build = host.Build(item, work=tmp)
                text = build.package()
                mirror = Path(tmp) / 'host' / item.key
                hardware = (mirror / 'host-hw.yaml').read_text()
                # One SDL display and touchscreen under the ids the features extend, the panel's own pixels.
                self.assertIn('platform: sdl\n    id: my_display', hardware, item.key)
                self.assertIn('platform: sdl\n    id: ts_touch', hardware, item.key)
                self.assertEqual(hardware.count('platform: sdl\n'), 2, item.key)
                # A glass that is lit keeps the output of its backlight as a stand-in, for the light and its script; a
                # glass of paper (features/paper.yaml) has none, and its panel under the glass is gone with the hardware.
                paper = any(path.name == 'paper.yaml' for path in profiles.chain(profiles.BOARDS[item.board]))
                self.assertEqual('id: gpio_backlight_pwm' in hardware, not paper, item.key)
                self.assertNotIn('paper_panel', hardware + text, item.key)
                # Nothing of the ESP32 is left in any file of the chain, and nothing of the audio, which stands on its
                # I2S: no speaker, microphone or codec block of a board file, and of an audio package only the glyphs
                # it adds to the icon fonts (the call's keys), so an include of one finds nothing else.
                for path in (mirror / 'packages').rglob('*.yaml'):
                    blocks = set(re.findall(r'(?m)^([a-z_0-9]+):', path.read_text()))
                    self.assertFalse(blocks & set(host.HARDWARE_BLOCKS + host.AUDIO_BLOCKS), f'{item.key}: {path.name}')
                    if host.audio_package(path.relative_to(mirror / 'packages')):
                        self.assertEqual(blocks, {'font'}, f'{item.key}: {path}')
                        self.assertNotIn('!include', path.read_text(), f'{item.key}: {path}')
                self.assertEqual('\n  LVGL_ROTATION: "' in text, item.key.endswith('-portrait'), item.key)
                for action in ('render_png', 'render_finger', 'render_state'):
                    self.assertIn(f'- action: {action}', text)
                # The SDL panel is read as often as the board reads its own: a finger that moves between reads is what
                # LVGL counts as a swipe.
                interval = '100ms' if item.key.startswith('tab5') else '20ms'
                self.assertIn(f'    update_interval: {interval}\n', hardware, item.key)
                self.assertIn('platform: host', (mirror / 'packages' / 'core.yaml').read_text())


if __name__ == '__main__':
    unittest.main()
