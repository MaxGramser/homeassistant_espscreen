"""tools/literal_margin.py: the Xtensa literal margin read from a linker map (docs/RELEASING.md, "The Xtensa literal
range"). A function's margin is the l32r reach less the distance from its own literals to the end of its own code, in one
output section; a map without literals in flash (an ESP32-P4) has no limit; --floor fails a build under it."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import literal_margin  # noqa: E402

KB = 1024
# A map as GNU ld writes it: discarded sections first (address 0), then the memory map with output sections, input
# sections on one line or with a long name on a line of its own.
MAP = """Discarded input sections

 .literal._ZN4demo4farEv
                0x00000000       0x10 esp-idf/src/libsrc.a(main.cpp.obj)

Linker script and memory map

.iram0.text     0x40374000     0x2000
 .literal.port_isr
                0x40374000        0x8 esp-idf/freertos/libfreertos.a(port.c.obj)
 .text.port_isr 0x40374008       0x40 esp-idf/freertos/libfreertos.a(port.c.obj)

.flash.text     0x42000020   0x100000
 .literal._ZN4demo4farEv
                0x42000100       0x48 esp-idf/src/libsrc.a(main.cpp.obj)
 .literal._ZN4demo4nearEv
                0x42010000       0x10 esp-idf/src/libsrc.a(main.cpp.obj)
 .text._ZN4demo4nearEv
                0x42010010      0x200 esp-idf/src/libsrc.a(main.cpp.obj)
 .text._ZN4demo4farEv
                0x42030000      0x400 esp-idf/src/libsrc.a(main.cpp.obj)
 .text.port_isr_flash
                0x42040000       0x20 esp-idf/freertos/libfreertos.a(port.c.obj)
"""


class Margin(unittest.TestCase):
    def test_each_function_from_its_own_literals_to_the_end_of_its_code(self):
        found = literal_margin.margins(MAP.splitlines(keepends=True))
        far = literal_margin.REACH - (0x42030400 - 0x42000100)
        near = literal_margin.REACH - (0x42010210 - 0x42010000)
        self.assertEqual(found[0], (far, 'main.cpp.obj', '_ZN4demo4farEv'), 'the tightest first')
        self.assertIn((near, 'main.cpp.obj', '_ZN4demo4nearEv'), found)
        self.assertEqual(len(found), 3, 'the discarded copy and code without literals of its own do not count')

    def test_the_floor_fails_a_build_and_a_map_without_literals_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            xtensa = Path(folder) / 'xtensa.map'
            xtensa.write_text(MAP)
            riscv = Path(folder) / 'riscv.map'
            riscv.write_text('Linker script and memory map\n\n.flash.text     0x42000000   0x100\n'
                             ' .text.main     0x42000000       0x20 esp-idf/src/libsrc.a(main.cpp.obj)\n')
            least = (literal_margin.REACH - (0x42030400 - 0x42000100)) / KB
            quiet = io.StringIO()
            with redirect_stdout(quiet), redirect_stderr(quiet):
                self.assertEqual(literal_margin.main([str(xtensa), '--floor', str(least - 1)]), 0)
                self.assertEqual(literal_margin.main([str(xtensa), '--floor', str(least + 1)]), 1)
                self.assertEqual(literal_margin.main([str(riscv), '--floor', '8']), 0)
            self.assertIn('no limit', quiet.getvalue())


if __name__ == '__main__':
    unittest.main()
