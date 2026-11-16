import json
import sys
import tempfile
import unittest
from pathlib import Path
import test_portal
from core import validate_layout, validate_settings, packets

class TwentyTiles(unittest.IsolatedAsyncioTestCase):
    async def test_twenty_and_old_firmware_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=test_portal.ManagerTests().setup_manager(Path(tmp)/'screens.json')
            layout={'title':'Twenty','tiles':[{'entity':f'light.item{i}'} for i in range(20)],
                    'settings':validate_settings({'swipe_pages':True})}
            for tile in layout['tiles']:m.ha.states[tile['entity']]={'state':'on','attributes':{}}
            with self.assertRaises(ValueError):m.save('text.screen',layout)
            m.ha.registry[0]['device_id']='screen-device'
            next(item for item in m.ha.registry if item.get('original_name') == 'Screen layout')['device_id']='screen-device'
            m.ha.registry.append({'entity_id':'sensor.version','platform':'esphome','original_name':'Screen firmware','device_id':'screen-device'})
            m.ha.states['sensor.version']={'state':'0.2.7'}
            m.save('text.screen',layout)
            await m.sync_one('text.screen',m.layouts['text.screen'])
            self.assertEqual(len(m.ha.messages),21)
            wire=m.ha.messages[0][1]
            self.assertEqual(len(wire['entities']),20)
            self.assertEqual(len(wire['settings']),11)
            self.assertTrue(wire['swipe_pages'])
            for _,message in m.ha.messages:self.assertTrue(packets(message))
            old=dict(layout);old['settings']={k:v for k,v in layout['settings'].items() if k!='swipe_pages'}
            m.save('text.screen',old)
            self.assertTrue(m.layouts['text.screen']['settings']['swipe_pages'])
            m.ha.states['sensor.version']['state']='0.2.6'
            m.ha.messages.clear()
            await m.sync_one('text.screen',m.layouts['text.screen'],True)
            self.assertEqual(m.ha.messages,[])
            self.assertEqual(len(m.layouts['text.screen']['tiles']),20)
