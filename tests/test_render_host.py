"""The host build of tools/render/ (app 0.2.129): every board of the catalog becomes a host program the same way.

tools/render/run.py compiles these and runs their self test (tools/check.sh --render, CI's render job), which needs
ESPHome and SDL2. This checks the part before the compiler on every run of the fast checks, so a change to the shape
of packages/core.yaml or of a board file that the host build cuts out is noticed here first.
"""
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
                self.assertIn('id: gpio_backlight_pwm', hardware, item.key)
                # The Guition's backlight keeps its floor on the stand-in: its Dimmest level calls set_min_power().
                if item.key == 'guition':
                    self.assertIn('    id: gpio_backlight_pwm\n    type: float\n    min_power: 0.01\n', hardware)
                # Nothing of the ESP32 is left in any file of the chain, and nothing of the audio, which stands on its
                # I2S: no audio package and no speaker, microphone or codec block of a board file.
                for path in (mirror / 'packages').rglob('*.yaml'):
                    blocks = set(re.findall(r'(?m)^([a-z_0-9]+):', path.read_text()))
                    self.assertFalse(blocks & set(host.HARDWARE_BLOCKS + host.AUDIO_BLOCKS), f'{item.key}: {path.name}')
                    self.assertFalse(host.audio_package(path.relative_to(mirror / 'packages')), f'{item.key}: {path}')
                    self.assertNotRegex(path.read_text(), r'(?m)^[^#\n]*!include \S*audio', f'{item.key}: {path.name}')
                self.assertEqual('\n  LVGL_ROTATION: "' in text, item.key.endswith('-portrait'), item.key)
                for action in ('render_png', 'render_finger', 'render_state'):
                    self.assertIn(f'- action: {action}', text)
                # The SDL panel is read as often as the board reads its own: a finger that moves between reads is what
                # LVGL counts as a swipe.
                interval = '100ms' if item.key.startswith('tab5') else '20ms'
                self.assertIn(f'    update_interval: {interval}\n', hardware, item.key)
                self.assertIn('platform: host', (mirror / 'packages' / 'core.yaml').read_text())

    def test_an_outputs_min_power_stays_on_its_stand_in(self):
        # ESPHome compiles FloatOutput::set_min_power() only while some output of the configuration sets min_power, so
        # a board lambda that calls it (the Guition's Dimmest level) fails on a stand-in without it.
        board = ('''output:
  - platform: ledc
    id: gpio_backlight_pwm
    pin: GPIO38
    min_power: 0.01
  - platform: ledc
    id: buzzer_pwm
    pin: GPIO8
''')
        chain = host.Chain()
        host.host_file(board, chain, 'board.yaml')
        self.assertEqual(chain.outputs, ['gpio_backlight_pwm', 'buzzer_pwm'])
        self.assertEqual(chain.min_power, {'gpio_backlight_pwm': '0.01'})


if __name__ == '__main__':
    unittest.main()
