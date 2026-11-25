"""Every ESP32-P4 screen builds on one core file (packages/hardware/esp32p4-core.yaml, docs/PLATFORM_PLAN.md 3.1).

The Tab5 carried its own copy of the chip's block and missed the 20 s task watchdog and the Wi-Fi driver's buffers in
PSRAM that the other P4 boards had (2026-10-25). So: the chip's variant is named in the core file alone, every hardware
file with a Wi-Fi co-processor on SDIO (esp32_hosted, which only the P4 boards have) includes it, and the core keeps
the options the P4's memory work rests on."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / 'packages' / 'hardware'
CORE = HARDWARE / 'esp32p4-core.yaml'


def includes(path, seen=None):
    """Every file `path` includes, transitively (the `!include` lines of ESPHome's packages)."""
    seen = set() if seen is None else seen
    for name in re.findall(r'!include\s+(\S+\.yaml)', path.read_text()):
        target = (path.parent / name).resolve()
        if target.exists() and target not in seen:
            seen.add(target)
            includes(target, seen)
    return seen


class P4Core(unittest.TestCase):
    def test_the_variant_is_named_in_the_core_alone(self):
        named = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'packages').rglob('*.yaml')
                       if re.search(r'^\s*variant:\s*esp32p4\b', p.read_text(), re.M))
        self.assertEqual(named, ['packages/hardware/esp32p4-core.yaml'])

    def test_every_p4_hardware_file_reaches_the_core(self):
        p4 = [p for p in HARDWARE.glob('*.yaml') if re.search(r'^esp32_hosted:', p.read_text(), re.M)]
        self.assertGreaterEqual(len(p4), 2)
        for path in p4:
            self.assertIn(CORE.resolve(), includes(path), path.name)

    def test_every_board_of_a_p4_file_reaches_the_core(self):
        p4 = {p.resolve() for p in HARDWARE.glob('*.yaml') if re.search(r'^esp32_hosted:', p.read_text(), re.M)}
        for board in (ROOT / 'packages' / 'boards').glob('*.yaml'):
            reached = includes(board)
            if reached & p4:
                self.assertIn(CORE.resolve(), reached, board.name)

    def test_the_core_keeps_what_the_p4_rests_on(self):
        core = CORE.read_text()
        for line in ('watchdog_timeout: 20s', 'execute_from_psram: true', 'CONFIG_ESP_HOSTED_MEMPOOL_PREFER_SPIRAM: "y"',
                     'CONFIG_ESP_HOSTED_DFLT_TASK_FROM_SPIRAM: "y"', 'CONFIG_ESP_HOSTED_USE_MEMPOOL: "n"'):
            self.assertIn(line, core)

    def test_what_differs_between_chip_revisions_is_decided_in_the_core_alone(self):
        """One number, CHIP_REVISION, and the rules that follow from it next to the setting each one changes
        (docs/CHIP_REVISIONS.md): no board or hardware file sets the revision switch or names a DSI driver itself, so a
        board sold with either silicon builds right for the chip the app read."""
        core = CORE.read_text()
        self.assertIn('CHIP_REVISION: "0"', core)
        self.assertRegex(core, r"engineering_sample: '\$\{ .*CHIP_REVISION")
        self.assertRegex(core, r"DSI_PLATFORM: '\$\{ .*CHIP_REVISION")
        # The image's lowest revision follows the same number: a chip read as v3.0 builds from v3.0, every other rev3
        # one from ESP-IDF's default v3.1, so the header never refuses the chip the build was made for.
        self.assertRegex(core, r"CONFIG_ESP32P4_REV_MIN_300: '\$\{ \"y\" if \(CHIP_REVISION \| int\) == 300")
        self.assertRegex(core, r"CONFIG_ESP32P4_REV_MIN_301: '\$\{ \"y\" if \(CHIP_REVISION \| int\) > 300")
        for path in (ROOT / 'packages').rglob('*.yaml'):
            if path == CORE:
                continue
            text = path.read_text()
            self.assertNotRegex(text, r'(?m)^\s*engineering_sample:', path.name)
            self.assertNotRegex(text, r'(?m)^\s*board:\s*esp32-p4', f'{path.name}: board: ${{P4_EV_BOARD}}')
            self.assertNotRegex(text, r'(?m)^\s*-?\s*platform: mipi_dsi(_v3)?\s*$', f'{path.name}: platform: ${{DSI_PLATFORM}}')
            revision = re.search(r'(?m)^\s*CHIP_REVISION:\s*"(\d+)"', text)
            if revision:
                self.assertIn(CORE.resolve(), includes(path), f'{path.name} states a chip revision but is no P4 board')

    def test_every_p4_board_takes_its_dsi_driver_from_the_chip_revision(self):
        p4 = {p.resolve() for p in HARDWARE.glob('*.yaml') if re.search(r'^esp32_hosted:', p.read_text(), re.M)}
        for board in (ROOT / 'packages' / 'boards').glob('*.yaml'):
            if includes(board) & p4 and re.search(r'(?m)^display:', board.read_text()):
                self.assertIn('platform: ${DSI_PLATFORM}', board.read_text(), board.name)


if __name__ == '__main__':
    unittest.main()
