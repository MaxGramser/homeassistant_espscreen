import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'screen_manager/app'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from server import KEEPALIVE_SECONDS
from core import validate_layout, state_message, packets
from firmware import Firmware
# The module, not the class: a TestCase imported by name runs its tests a second time in this module.
import test_portal

class ExtendedTests(unittest.TestCase):
 def test_options_validation_and_new_domains(self):
  for domain in ['sensor','number','input_number','select','weather','media_player']:
   layout=validate_layout({'title':'Test','tiles':[{'entity':domain+'.x','options':{'display':'watch'}}]})
   self.assertEqual(layout['tiles'][0]['options']['display'],'watch')
  for options in [{'inline':'slider'},{'history_hours':True},{'history_hours':100},{'arbitrary':'run'}]:
   with self.assertRaises(ValueError):validate_layout({'title':'Test','tiles':[{'entity':'sensor.x','options':options}]})
  # On / off: whether Home Assistant offers <domain>.toggle is checked when saving (app 0.2.67); a built-in card never.
  with self.assertRaises(ValueError):validate_layout({'title':'Test','tiles':[{'entity':'screen.clock','options':{'tap':'toggle'}}]})
  with self.assertRaises(ValueError):validate_layout({'title':'Test','tiles':[{'entity':'light.x','options':{'display':'watch','inline':'slider'}}]})
 def test_attributes_and_history_fit_protocol(self):
  tile={'entity':'sensor.a','name':'Temperature','options':{'history_hours':24,'display':'watch'}}
  msg=state_message(0,tile,{'sensor.a':{'state':'21','attributes':{'unit_of_measurement':'°C','password':'hidden'}}})
  msg['history']={'hours':24,'values':[None,21.5]*12}
  self.assertNotIn('password',msg['a']);self.assertEqual(msg['o'],tile['options']);self.assertTrue(all(len(p)<=255 for p in packets(msg)))
 def test_firmware_profiles_no_overwrite_or_traversal(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=Firmware(Path(tmp)/'config',Path(tmp)/'data');data={'board':'cyd','name':'test','friendly_name':'Test','wifi_ssid':'local-wifi','wifi_password':'private-wifi'}
   result=f.create(data);before=f.profile('test.yaml').read_text();secrets=(f.root/'secrets.yaml').read_text()
   with self.assertRaises(ValueError):f.create(data)
   self.assertEqual(before,f.profile('test.yaml').read_text());self.assertEqual(secrets,(f.root/'secrets.yaml').read_text())
   for value in ['../secrets.yaml','/etc/passwd','test.yaml;echo']:
    with self.assertRaises(ValueError):f.profile(value)
   (f.root/'linked.yaml').symlink_to(f.profile('test.yaml'))
   with self.assertRaises(ValueError):f.profile('linked.yaml')
   self.assertEqual(f.profiles(),[{'file':'test.yaml'}])

class FirmwareJobs(unittest.IsolatedAsyncioTestCase):
 async def test_cli_arguments_redaction_and_busy(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=Firmware(tmp,tmp);f.create({'board':'guition','name':'test','friendly_name':'Test','wifi_ssid':'homewifi','wifi_password':'secretwifi'})
   async def waiting(*args):await asyncio.sleep(20)
   with patch('firmware.shutil.which',return_value='/bin/esphome'),patch.object(f,'run',side_effect=waiting):
    with self.assertRaises(ValueError):f.start({'file':'test.yaml','action':'install','target':'1.2.3.4;evil'})
    with self.assertRaises(ValueError):f.start({'file':'test.yaml','action':'install','target':'/dev/unknown'})
    f.start({'file':'test.yaml','action':'validate'})
    self.assertNotIn('secretwifi',f.redact('Using secretwifi on homewifi'))
    with self.assertRaises(ValueError):f.start({'file':'test.yaml','action':'build'})
    f.task.cancel()
    try:await f.task
    except asyncio.CancelledError:pass
 async def test_old_browser_preserves_new_tile_options(self):
  with tempfile.TemporaryDirectory() as tmp:
   m=test_portal.ManagerTests().setup_manager(Path(tmp)/'screens.json')
   m.save('text.screen',{'title':'Home','tiles':[{'entity':'light.a','name':'Lamp','options':{'inline':'slider'}}]})
   m.save('text.screen',{'title':'New','tiles':[{'entity':'light.a','name':'Lamp'}]})
   self.assertEqual(m.layouts['text.screen']['tiles'][0]['options'],{'inline':'slider'})

class SpecialTiles(unittest.TestCase):
 def test_new_domains_displays_and_wide_option(self):
  from core import extras, min_firmware
  from zoneinfo import ZoneInfo
  layout=validate_layout({'title':'T','tiles':[{'entity':'screen.clock','options':{'display':'analog','size':'wide'}},{'entity':'sun.sun'},{'entity':'timer.egg'},{'entity':'person.max'},
   {'entity':'weather.home','options':{'display':'forecast'}},{'entity':'sensor.t','options':{'display':'graph','size':'wide'}}]})
  self.assertEqual(layout['tiles'][4]['options'],{'display':'forecast','size':'wide'},'forecast forces a wide card')
  self.assertEqual(validate_layout({'title':'T','tiles':[{'entity':'sun.sun','options':{'display':'sunpath'}}]})['tiles'][0]['options'],{'display':'sunpath','size':'wide'})
  self.assertEqual(layout['tiles'][0]['options']['display'],'analog')
  for tile in [{'entity':'screen.other'},{'entity':'light.a','options':{'size':'double'}},{'entity':'light.a','options':{'display':'graph'}},
               {'entity':'sensor.a','options':{'display':'forecast'}},{'entity':'screen.clock','options':{'display':'watch'}}]:
   with self.assertRaises(ValueError):validate_layout({'title':'T','tiles':[tile]})
  self.assertEqual(min_firmware(layout),(0,2,14))
  self.assertEqual(min_firmware({'tiles':[{'entity':f'light.a{n}'} for n in range(11)]}),(0,2,7))
  # One entity on several tiles is firmware 0.16.0's (GitHub #83).
  self.assertEqual(min_firmware({'tiles':[{'entity':'light.a'}]*2}),(0,16,0))
  self.assertIsNone(min_firmware({'tiles':[{'entity':'light.a'}]}))
  tz=ZoneInfo('Europe/Amsterdam')
  states={'sun.sun':{'state':'above_horizon','attributes':{'next_rising':'2026-09-14T05:15:00+00:00','next_setting':'2026-09-13T17:50:12.000000+00:00'}},
          'timer.egg':{'state':'active','attributes':{'finishes_at':'2026-09-13T12:00:00+00:00','duration':'0:05:00','remaining':'0:05:00'}},
          'weather.home':{'state':'sunny','attributes':{'temperature':21.5,'temperature_unit':'°C'}}}
  self.assertEqual(extras({'entity':'sun.sun'},states,None,tz),{'rise':'07:15','set':'19:50'})
  self.assertEqual(extras({'entity':'timer.egg'},states,None,tz),{'end':1789300800,'dur':'0:05:00','rem':'0:05:00'})
  forecast=[{'datetime':f'2026-09-{13+i}T10:00:00+00:00','condition':'partlycloudy','temperature':20+i,'templow':11.5} for i in range(7)]+['junk']
  days=extras({'entity':'weather.home'},states,forecast,tz)['days']
  self.assertEqual([d['d'] for d in days],['Su','Mo','Tu','We','Th'])
  self.assertEqual(days[0],{'d':'Su','c':'partlycloudy','h':20,'l':11.5})
  self.assertIsNone(extras({'entity':'light.a'},states,None,tz))
  msg=state_message(0,{'entity':'screen.clock','name':'','options':{'display':'analog'}},{})
  self.assertEqual((msg['state'],msg['name'],msg['o']),('ok','Clock',{'display':'analog'}))
  msg=state_message(1,{'entity':'weather.home','name':''},states,extras({'entity':'weather.home'},states,forecast,tz))
  self.assertEqual(len(msg['x']['days']),5);self.assertTrue(all(len(p)<=255 for p in packets(msg)))

class SpecialTileSync(unittest.IsolatedAsyncioTestCase):
 async def test_new_domains_need_firmware_and_send_extras(self):
  with tempfile.TemporaryDirectory() as tmp:
   m=test_portal.ManagerTests().setup_manager(Path(tmp)/'screens.json')
   layout={'title':'Home','tiles':[{'entity':'screen.clock','name':''},{'entity':'sun.sun','name':''}]}
   m.ha.states['sun.sun']={'state':'above_horizon','attributes':{'friendly_name':'Sun','next_rising':'2026-09-14T05:15:00+00:00','next_setting':'2026-09-13T17:50:12+00:00'}}
   with self.assertRaises(ValueError):m.save('text.screen',layout)
   m.ha.registry.append({'entity_id':'sensor.screen_firmware','platform':'esphome','original_name':'Screen firmware'})
   m.ha.states['sensor.screen_firmware']={'state':'0.2.13'}
   with self.assertRaises(ValueError):m.save('text.screen',layout)
   m.ha.states['sensor.screen_firmware']={'state':'0.2.14'}
   m.save('text.screen',layout)
   await m.sync_one('text.screen',m.layouts['text.screen'])
   sent=[message for _,message in m.ha.messages]
   self.assertEqual(sent[0]['entities'],['screen.clock','sun.sun'])
   self.assertEqual(sent[0]['keepalive'],KEEPALIVE_SECONDS,'the screen sizes its feed watchdog from the declared cadence')
   self.assertEqual((sent[1]['state'],sent[1]['name']),('ok','Clock'))
   self.assertEqual(sent[2]['x'],{'rise':'05:15','set':'17:50'},'fake HA has no time zone: UTC')
   m.ha.states['sensor.screen_firmware']={'state':'0.2.13'};m.ha.messages.clear()
   await m.sync_one('text.screen',m.layouts['text.screen'])
   self.assertEqual(m.ha.messages,[]);self.assertIn('0.2.14',m.status['text.screen'])
