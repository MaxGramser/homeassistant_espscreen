"""The Guition 4848S040's room for cards and its GT911 check. Its panel, timings and touch are its board file's, measured
on its glass and kept in docs/GUITION.md and docs/GUITION_FACTORY_REFERENCE.md; the rules every board keeps (the RGB
panel settings, no raw correction on a capacitive touch, the standby, square glass) are test_easy_package.py BoardRules."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0,str(ROOT/'tools'))
import verify_gt911
VALUES=profiles.substitutions('checkout/guition.yaml')

class GuitionTests(unittest.TestCase):
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
        # The page keys are 7 mm high on this board since 0.14.0: the least a finger needs (ui::touch_min), where the
        # look's own 60 px was 9 mm. That the keys are the two halves of the band under the tiles, that high, is the
        # firmware preview's web/wasm/test_page_keys.mjs.
        self.assertEqual(v('PAGE_BAR_H'),round(170*7/25.4))

    def test_gt911_verification_accepts_pixels_and_rejects_wrong_orientation(self):
        data=dict(screen=[480,480],rotation=0,points=[dict(name=name,samples=[list(xy)]*3) for name,xy in verify_gt911.TARGETS])
        self.assertEqual(len(verify_gt911.verify(data)),5)
        data['rotation']=180
        with self.assertRaises(ValueError):verify_gt911.verify(data)

    def test_gt911_rotations(self):
        self.assertEqual(verify_gt911.screen_point(20,30,90),(30,459))
        self.assertEqual(verify_gt911.screen_point(20,30,270),(449,20))

if __name__=='__main__':unittest.main()
