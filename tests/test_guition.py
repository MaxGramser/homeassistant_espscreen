"""Guition-specific geometry, hardware isolation and capacitive touch checks."""
from firmware_sources import runtime_source
from pathlib import Path
import re
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0,str(ROOT/'tools'))
import verify_gt911
SOURCE=profiles.resolved('checkout/guition.yaml')
VALUES=profiles.substitutions('checkout/guition.yaml')

class GuitionTests(unittest.TestCase):
    def test_hardware_is_s3_rgb_with_capacitive_touch(self):
        self.assertIn('platform: st7701s',SOURCE)
        self.assertNotIn('platform: mipi_rgb',SOURCE)
        self.assertIn('platform: gt911',SOURCE)
        self.assertIn('mode: octal',SOURCE)
        self.assertNotIn('platform: xpt2046',SOURCE)
        self.assertNotIn('set_raw_correction',SOURCE)
        self.assertEqual(VALUES['TOUCH_MIRROR_X'],'false')
        self.assertEqual(VALUES['TOUCH_MIRROR_Y'],'false')
        self.assertIn('pclk_frequency: 16MHz',SOURCE)
        self.assertIn('hsync_back_porch: 50',SOURCE)
        self.assertIn('vsync_back_porch: 20',SOURCE)
        self.assertIn('spi_mode: MODE0',SOURCE)
        self.assertIn('[0x3A, 0x60]',SOURCE)
        # Only as a warning in a comment: never set (packages/hardware/esp32s3-rgb.yaml says why).
        self.assertNotIn('CONFIG_LCD_RGB_RESTART_IN_VSYNC:',SOURCE)
        # The RGB panel settings every ESP32-S3 board shares (firmware 0.3.1): the 4-inch Guition too.
        self.assertIn('CONFIG_LCD_RGB_ISR_IRAM_SAFE: "y"',SOURCE)
        self.assertIn('CONFIG_ESP32S3_DATA_CACHE_LINE_64B: "y"',SOURCE)
        self.assertIn('execute_from_psram: true',SOURCE)
        self.assertNotIn('id: output_red',SOURCE)
        self.assertEqual(VALUES['PANEL_W'],'480')
        self.assertEqual(VALUES['PANEL_H'],'480')
        # Square glass: this is the one board that hangs the same way whichever way it is screwed to the wall, so
        # its page has the same cells standing up and it is never asked about (core.board_shape).
        self.assertEqual(VALUES['ROTATION_LANDSCAPE'],'0')
        self.assertEqual((VALUES['GRID_COLS_PORTRAIT'],VALUES['GRID_ROWS_PORTRAIT']),
                         (VALUES['GRID_COLS'],VALUES['GRID_ROWS']))

    def test_cards_fit_with_gutters_and_reserved_navigation(self):
        v=lambda k:int(VALUES[k])
        cols,rows=v('GRID_COLS'),v('GRID_ROWS')
        self.assertEqual((cols,rows),(2,3))
        self.assertGreaterEqual(v('GRID_MARGIN'),16)
        # The firmware divides the canvas over the cells (firmware 0.2.92+), so what the board states is the room it
        # leaves them: a card of this board still holds three of a CYD's.
        tile_w=(480-2*v('GRID_MARGIN')-(cols-1)*v('GRID_GAP_X'))//cols
        band=480-v('SCROLL_Y')-v('PAGE_BAR_H')
        tile_h=(band-(rows-1)*v('GRID_GAP_Y'))//rows
        self.assertGreaterEqual(tile_w*tile_h,3*147*52)
        # The page keys are the two halves of the band under the tiles (firmware 0.2.69+), 7 mm high since 0.14.0: the
        # least a finger needs (ui::touch_min), where the look's own 60 px was 9 mm.
        self.assertEqual(v('PAGE_BAR_H'),round(170*7/25.4))
        for key in ('page_prev','page_next'):
            block=SOURCE.split(f'id: {key}',1)[1][:200]
            self.assertIn('width: 50%\n',block);self.assertIn(f"height: {v('PAGE_BAR_H')}\n",block)

    def test_every_card_label_is_one_line_with_an_ellipsis(self):
        """The runtime gives every card's name and state a one-line box and an ellipsis, on every board."""
        runtime=runtime_source()
        self.assertIn('lv_obj_set_height(title,lv_font_get_line_height(lv_obj_get_style_text_font(title,LV_PART_MAIN)));',runtime)
        self.assertIn('lv_label_set_long_mode(title,LV_LABEL_LONG_DOT);lv_label_set_long_mode(value,LV_LABEL_LONG_DOT);',runtime)
        self.assertEqual(VALUES['AUTO_DIM_TIMEOUT'],'600')

    def test_gt911_verification_accepts_pixels_and_rejects_wrong_orientation(self):
        data=dict(screen=[480,480],rotation=0,points=[dict(name=name,samples=[list(xy)]*3) for name,xy in verify_gt911.TARGETS])
        self.assertEqual(len(verify_gt911.verify(data)),5)
        data['rotation']=180
        with self.assertRaises(ValueError):verify_gt911.verify(data)

    def test_gt911_rotations(self):
        self.assertEqual(verify_gt911.screen_point(20,30,90),(30,459))
        self.assertEqual(verify_gt911.screen_point(20,30,270),(449,20))

if __name__=='__main__':unittest.main()
