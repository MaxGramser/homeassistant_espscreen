import re
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_portal
from core import TILE_BACKGROUNDS, validate_layout

def luminance(color):
    rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
    return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))

class PaletteTests(unittest.IsolatedAsyncioTestCase):
    def test_palette_matches_firmware_and_has_readable_text(self):
        # The named card colours live in theme.h (firmware 0.2.54+): name, light value, dark value.
        # Only the card colours: the key colours of an alert's buttons (KEY_SWATCHES, firmware 0.3.3+) share their names.
        header=(Path(__file__).resolve().parents[1]/'components/smart_display/theme.h').read_text().split('SWATCHES[] = {',1)[1].split('};',1)[0]
        native={name:light for name,light,_ in re.findall(r'\{"(\w+)", 0x([A-F0-9]{6}), 0x([A-F0-9]{6})\}',header)}
        expected={k:v['color'][1:] for k,v in TILE_BACKGROUNDS.items() if v['color']}
        self.assertEqual(native,expected)
        for color in expected.values():
            for foreground,minimum in (('#1B1B1B',7),('#46525E',4.5)):
                self.assertGreaterEqual((luminance('#'+color)+.05)/(luminance(foreground)+.05),minimum)

    async def test_old_editor_preserves_color_and_explicit_auto_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=test_portal.ManagerTests().setup_manager(Path(tmp)/'screens.json')
            layout={'title':'Home','tiles':[{'entity':'light.a','options':{'background':'red','inline':'slider'}}]}
            m.save('text.screen',layout)
            m.save('text.screen',{'title':'New','tiles':[{'entity':'light.a','options':{'inline':'none'}}]})
            fresh=test_portal.ManagerTests().setup_manager(m.path)
            tile=fresh.layouts['text.screen']['tiles'][0]
            self.assertEqual(tile['options'],{'background':'red','inline':'none'})
            await fresh.sync_one('text.screen',fresh.layouts['text.screen'])
            self.assertEqual(fresh.ha.messages[1][1]['o']['background'],'red')
            fresh.save('text.screen',{'title':'New','tiles':[{'entity':'light.a','options':{'background':'auto'}}]})
            self.assertEqual(fresh.layouts['text.screen']['tiles'][0]['options']['background'],'auto')

    def test_none_hides_the_card_and_needs_firmware_0216(self):
        from core import min_firmware
        header=(Path(__file__).resolve().parents[1]/'components/smart_display/tile_palette.h').read_text()
        self.assertIn('name=="none"',header)
        self.assertIsNone(TILE_BACKGROUNDS['none']['color'])
        for entity in ('screen.clock','light.a'):
            layout=validate_layout({'title':'Home','tiles':[{'entity':entity,'options':{'background':'none'}}]})
            self.assertEqual(layout['tiles'][0]['options']['background'],'none')
            self.assertEqual(min_firmware(layout),(0,2,16))
        self.assertEqual(min_firmware({'tiles':[{'entity':'light.a','options':{'background':'red'}}]}),None)

    def test_unapproved_colors_rejected(self):
        for value in ('#000000','url(test)','unknown',None,{},42):
            with self.assertRaises(ValueError):validate_layout({'title':'Home','tiles':[{'entity':'light.a','options':{'background':value}}]})
