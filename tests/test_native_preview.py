from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'screen_manager/app'))
from media_library import preview_items
from page_delivery import Sender
class NativePreview(unittest.TestCase):
 def test_legacy_and_disconnect_drop_native_config(self):
  sender=Sender(None)
  sender.heard({'preview':{'media_screen':{'entity':'media_player.test','library_entry':'entry','secret':'discard'}}})
  self.assertEqual(sender.preview,{'media_screen':{'entity':'media_player.test','library_entry':'entry'}})
  sender.heard({});self.assertIn('media_screen',sender.preview)
  sender.disconnected();self.assertEqual(sender.preview,{})
  sender.heard({});self.assertEqual(sender.preview,{})
  sender.heard({'preview':{'media_screen':{'entity':'switch.test'}}});self.assertEqual(sender.preview,{})
 def test_compact_library_limits_and_invalid_rows(self):
  rows=[None,{},*({'name':str(i),'uri':'track:'+str(i),'media_type':'track','secret':'discard'} for i in range(100))]
  result=preview_items('music_assistant.get_library',{'items':rows})
  self.assertEqual(len(result['items']),48)
  self.assertEqual(set(result['items'][0]),{'name','uri','kind'})
 def test_queue_and_search(self):
  self.assertEqual(preview_items('music_assistant.get_queue',{'player':{'current_item':{'name':'Now'},'next_item':{'name':'Next'}}})['items'][1],{'name':'Next: Next','uri':'next_item','kind':'queue'})
  self.assertEqual(preview_items('music_assistant.search',{'tracks':[{'name':'Song','uri':'track:1'}]})['items'][0]['name'],'Song')
if __name__=='__main__':unittest.main()
