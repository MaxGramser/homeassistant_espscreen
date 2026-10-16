"""Tiers and modules (docs/MODULES.md).

A screen's tier follows from its flash (components/smart_display/modules.py): lite below 8 MB, full above. A module
lives in components/smart_display/module_<name>.h, and the shared code reaches it only inside `#ifdef` of its define, so
a lite screen compiles none of it. These tests keep it that way: every module has its code and its define, nothing
outside a module's guard names it, every 4 MB board is lite, and boards.json says what the firmware works out.
"""
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402

BOARDS = [b for b in profiles.NAMES if '/' not in b]
COMPONENT = ROOT / 'components/smart_display'
spec = importlib.util.spec_from_file_location('smart_display_modules', COMPONENT / 'modules.py')
modules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modules)


def unguarded(text, define, needle):
    """Lines of `text` that name `needle` outside an `#ifdef define` ... `#endif`."""
    depth, guarded, found = 0, [], []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('#if'):
            depth += 1
            guarded.append(stripped in (f'#ifdef {define}', f'#if defined({define})'))
        elif stripped.startswith('#endif'):
            depth -= 1
            guarded.pop()
        elif needle in line and not any(guarded):
            found.append(number)
    return found


class ModuleTests(unittest.TestCase):
    def test_every_module_has_its_code_and_a_known_tier(self):
        for name, module in modules.MODULES.items():
            self.assertIn(module['min_tier'], modules.TIERS, name)
            self.assertTrue((COMPONENT / f'module_{name}.h').exists(), f'module_{name}.h is missing')
            self.assertRegex(module['define'], r'^SD_MOD_[A-Z_]+$')

    def test_no_module_is_reached_outside_its_guard(self):
        # The code of the core, the board files and the packages: a module's namespace or header named anywhere
        # without its #ifdef would put it into a lite screen's build (or break it).
        sources = [p for p in COMPONENT.glob('*.[hc]*') if p.suffix in ('.h', '.cpp')]
        sources += list((ROOT / 'packages').rglob('*.yaml'))
        for name, module in modules.MODULES.items():
            for path in sources:
                text = path.read_text()
                for needle in (f'{name}::', f'module_{name}.h'):
                    lines = unguarded(text, module['define'], needle)
                    self.assertEqual(lines, [], f'{path.relative_to(ROOT)} names {needle} outside #ifdef {module["define"]}')

    def test_every_4mb_board_is_lite_and_the_rest_full(self):
        for board in BOARDS:
            expected = 'lite' if profiles.wide_slots(board) or profiles.flash_mb(board) < 8 else 'full'
            self.assertEqual(profiles.tier(board), expected, board)
        self.assertEqual(profiles.tier('cyd'), 'lite')
        self.assertEqual(profiles.modules('cyd'), [])

    def test_boards_json_says_what_the_firmware_works_out(self):
        shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        for board in BOARDS:
            self.assertEqual(shapes[board]['tier'], profiles.tier(board), board)
            self.assertEqual(shapes[board]['modules'], profiles.modules(board), board)

    def test_the_component_sets_the_defines_from_the_flash(self):
        init = (COMPONENT / '__init__.py').read_text()
        self.assertIn('modules.tier_for_flash(_flash_mb(config))', init)
        self.assertIn('cg.add_define(modules.MODULES[name]["define"])', init)
        self.assertEqual(modules.tier_for_flash(4), 'lite')
        self.assertEqual(modules.tier_for_flash(8), 'full')
        self.assertEqual(modules.tier_for_flash(None), 'full')


if __name__ == '__main__':
    unittest.main()
