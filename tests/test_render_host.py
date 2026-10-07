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
                # Nothing of the ESP32 is left in any file of the chain.
                for path in (mirror / 'packages').rglob('*.yaml'):
                    blocks = set(re.findall(r'(?m)^([a-z_0-9]+):', path.read_text()))
                    self.assertFalse(blocks & set(host.HARDWARE_BLOCKS), f'{item.key}: {path.name}')
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
