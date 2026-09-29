"""The alert card's layout is one rule, written twice: the firmware's (alert_overlay.h) and ESP Screens' (app 0.2.128).

The screen lays its alert out on the glass it draws on (screen_alert::layout), and ESP Screen Manager sizes the picture
of an alert with a camera to the frame that layout gives it, from screen_manager/app/alert_layout.py through boards.json. This
compiles the C++ rule and checks that the Python one gives the same numbers on every glass, density and look, and that
boards.json carries the box every board's firmware draws, lying down and standing up.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import alert_layout  # noqa: E402
import font_metrics  # noqa: E402
import profiles  # noqa: E402

FIELDS = ('card_w', 'card_h', 'icon_x', 'icon_y', 'text_x', 'text_w', 'title_y', 'title_h', 'subtitle_y', 'subtitle_h',
          'button_x', 'button_y', 'button_w', 'button_h', 'button_inset', 'image_x', 'image_y', 'image_w', 'image_h')
LOOKS = ('standard', 'compact')
DPIS = (110, 133, 143, 149, 170, 190, 196, 217, 294)
SIDES = (170, 180, 240, 272, 320, 480, 600, 800, 1024, 1280)
# The proportions of a picture: none (no image), the default, 16:9, square, a standing doorbell (3:4), 21:9 and 9:16.
SHAPES = ((0, 0), (392, 220), (16, 9), (1, 1), (3, 4), (21, 9), (9, 16))


def title_line(look, dpi):
    """A line height of the kind a board's headline font has (the look's, at this density)."""
    _, scale = alert_layout.configure(dpi, look)
    return alert_layout.px(32 if look == 'standard' else 21, scale)


def line(look, dpi):
    _, scale = alert_layout.configure(dpi, look)
    return alert_layout.px(25 if look == 'standard' else 16, scale)


class OneRule(unittest.TestCase):
    def test_python_and_the_firmware_lay_every_card_out_alike(self):
        compiler = shutil.which(os.environ.get('CXX', 'clang++')) or shutil.which('g++')
        if not compiler:
            self.skipTest('no C++ compiler')
        cases = [(look, dpi, w, h, shape) for look in LOOKS for dpi in DPIS for w in SIDES for h in SIDES
                 for shape in SHAPES]
        rows = ',\n'.join(f'  {{"{look}", {dpi}, {w}, {h}, {shape[0]}, {shape[1]}, {title_line(look, dpi)}, {line(look, dpi)}}}'
                          for look, dpi, w, h, shape in cases)
        fields = ', '.join(f'l.{name}' for name in FIELDS)
        source = f'''#include "screen_text_en.h"
#define THEME_TEST
#include "components/smart_display/alert_overlay.h"
#include <cstdio>
struct Case {{ const char *look; int dpi, w, h, aw, ah, title, line; }};
static const Case CASES[] = {{
{rows}
}};
int main() {{
  for (const auto &c : CASES) {{
    ui::configure(c.dpi, c.look);
    const auto l = screen_alert::layout(c.w, c.h, c.title, c.line, c.aw > 0, c.aw, c.ah);
    std::printf("{' '.join(['%d'] * len(FIELDS))}\\n", {fields});
  }}
}}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'layout.cpp'
            path.write_text(source)
            subprocess.run([compiler, '-std=c++17', f'-I{ROOT}', f'-I{ROOT / "tests"}', str(path), '-o', str(Path(tmp) / 'layout')],
                           check=True)
            out = subprocess.run([str(Path(tmp) / 'layout')], check=True, capture_output=True, text=True).stdout.split('\n')
        self.assertEqual(len([row for row in out if row]), len(cases))
        for (look, dpi, w, h, (aw, ah)), row in zip(cases, out):
            mine = alert_layout.layout(w, h, title_line(look, dpi), line(look, dpi), aw > 0, dpi, look, aw, ah)
            self.assertEqual([getattr(mine, name) for name in FIELDS], [int(value) for value in row.split()],
                             f'{look} {dpi} dpi {w} x {h} picture {aw}:{ah}')

    def test_boards_json_carries_the_frame_each_screen_draws(self):
        shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        core = profiles.CORE.read_text()
        for board in profiles.BOARDS:
            values = profiles.board_values(board)
            shape = shapes[board]
            if 'CAMERA_FULL_W' not in values:
                self.assertNotIn('camera', shape, board)
                continue
            title = font_metrics.line_height(ROOT / font_metrics.font_file(core, 'headline'), int(values['FONT_HEADLINE_SIZE']))
            sub = font_metrics.line_height(ROOT / font_metrics.font_file(core, 'sublabel_big'), int(values['FONT_SUBLABEL_BIG_SIZE']))
            for way, side in shape['orientations'].items():
                card = alert_layout.layout(side['width'], side['height'], title, sub, True,
                                           round(float(values['DISPLAY_DPI'])), values['LOOK'])
                self.assertEqual(side['camera']['full'], [side['width'], side['height']], f'{board} {way}')
                self.assertEqual(side['camera'].get('thumb'), [card.image_w, card.image_h], f'{board} {way}')
                # The picture fits the card it lands on, and the card the glass.
                self.assertLessEqual(card.image_x + card.image_w, card.card_w, f'{board} {way}')
                self.assertLessEqual(card.card_h, side['height'], f'{board} {way}')
            self.assertEqual(shape['camera'], shape['orientations']['landscape']['camera'], board)

    def test_the_card_fonts_are_worked_out_as_the_build_makes_them(self):
        # ESP Screens works the card's two line heights out itself for a screen whose Override YAML changed its density
        # or look (camera_feed.alert_box): the fonts' own measure, the look's sizes, and every board's result.
        core = profiles.CORE.read_text()
        for font_id in ('headline', 'sublabel_big'):
            font = ROOT / font_metrics.font_file(core, font_id)
            for size in range(8, 97):
                self.assertEqual(alert_layout.font_line(size), font_metrics.line_height(font, size), (font_id, size))
        for look, (reference, title, words) in alert_layout.LOOK_FONTS.items():
            text = (ROOT / f'packages/looks/{look}.yaml').read_text()
            self.assertIn(f'LOOK_SCALE: ${{ (DISPLAY_DPI | float) / {reference} }}', text, look)
            self.assertIn(f'FONT_HEADLINE_SIZE: ${{ [8, ({title} * LOOK_SCALE | float) | round | int] | max }}', text, look)
            self.assertIn(f'FONT_SUBLABEL_BIG_SIZE: ${{ [8, ({words} * LOOK_SCALE | float) | round | int] | max }}', text, look)
        shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        for board in profiles.BOARDS:
            values = profiles.board_values(board)
            if 'alert' in shapes[board]:
                self.assertEqual(alert_layout.lines(float(values['DISPLAY_DPI']), values['LOOK']),
                                 (shapes[board]['alert']['title_line'], shapes[board]['alert']['line']), board)

    def test_the_two_boards_each_look_was_drawn_on_keep_their_card(self):
        guition = alert_layout.layout(480, 480, 32, 25, True, 170, 'standard')
        self.assertEqual((guition.card_w, guition.card_h, guition.image_w, guition.image_h, guition.subtitle_y),
                         (420, 452, 392, 220, 304))
        cyd = alert_layout.layout(320, 240, 21, 16, False, 143, 'compact')
        self.assertEqual((cyd.card_w, cyd.card_h, cyd.text_w, cyd.subtitle_h), (292, 196, 212, 80))

    def test_every_board_takes_the_picture_where_it_shows_most_of_it(self):
        # (board, way) -> where a 16:9, a square and a standing (3:4) camera go; the button is on the right edge always.
        shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        seen = {}
        for board, shape in shapes.items():
            if board != shape.get('board') or 'camera' not in shape:
                continue
            for way, side in shape['orientations'].items():
                for aw, ah in ((16, 9), (1, 1), (3, 4)):
                    card = alert_layout.layout(side['width'], side['height'], shape['alert']['title_line'],
                                               shape['alert']['line'], True, shape['dpi'], shape['look'], aw, ah)
                    self.assertEqual(card.button_x + card.button_w + card.button_inset, card.card_w, (board, way, aw, ah))
                    self.assertGreater(card.image_w, 0, (board, way, aw, ah))
                    # The frame has the picture's own proportions, to within the rounding of a pixel.
                    self.assertAlmostEqual(card.image_w / card.image_h, aw / ah, delta=0.02 * aw / ah + 1 / card.image_h,
                                           msg=(board, way, aw, ah))
                    seen[(board, way, aw, ah)] = 'beside' if card.image_x + card.image_w <= card.icon_x else 'above'
        # A wide picture stays on top, also on the big 10.1-inch (a picture keeps its size in millimetres); a square or
        # standing one on the wide, low 4.3-inch goes on the left of the words, where it can be taller.
        self.assertEqual(seen[('guition', 'landscape', 16, 9)], 'above')
        self.assertEqual(seen[('jc8012p4a1', 'landscape', 16, 9)], 'above')
        self.assertEqual(seen[('jc8012p4a1', 'landscape', 3, 4)], 'above')
        self.assertEqual(seen[('waveshare43', 'landscape', 1, 1)], 'beside')
        self.assertEqual(seen[('waveshare43', 'landscape', 3, 4)], 'beside')
        self.assertEqual(seen[('waveshare43', 'portrait', 16, 9)], 'above')

    def test_glass_too_low_for_a_picture_shows_the_alert_without_one(self):
        card = alert_layout.layout(480, 240, 32, 25, True, 170, 'standard')
        self.assertEqual((card.image_w, card.image_h), (0, 0))
        self.assertEqual(card, alert_layout.layout(480, 240, 32, 25, False, 170, 'standard'))


if __name__ == '__main__':
    unittest.main()
