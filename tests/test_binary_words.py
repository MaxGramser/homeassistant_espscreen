"""Binary sensors in Home Assistant's words (app 0.2.62 / firmware 0.2.53): a door tile says Open or Closed.

The screen maps the device class itself, from the `device_class` attribute every state message has carried since app
0.2.23: nothing new on the wire, so it works with older apps too. Its words are the add-on's `header_bar.BINARY_STATES`,
which the top bar and the history card use: tests/fixtures/binary-words.json holds that table for both sides, and
web/wasm/test_binary_words.mjs reads the real firmware's cards for every class, on and off, a card's heading and the
words its history brings. Here: the fixture is the add-on's table, the add-on's sides say the same, and the fonts
carry every word.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import header_bar  # noqa: E402
import history_card  # noqa: E402
from core import state_message  # noqa: E402

FIXTURE = ROOT / 'tests/fixtures/binary-words.json'
PROFILES = ('checkout/guition.yaml', 'checkout/cyd.yaml', 'packages/cyd.yaml', 'packages/guition.yaml')


ENGLISH = json.loads((ROOT / 'screen_manager/translations/en.json').read_text(encoding='utf-8'))


class BinaryWords(unittest.TestCase):
    def test_the_screen_s_fixture_is_the_add_on_s_table(self):
        found = {kind: tuple(words) for kind, words in json.loads(FIXTURE.read_text(encoding='utf-8')).items()}
        self.assertEqual(found, header_bar.BINARY_STATES,
                         'Write tests/fixtures/binary-words.json from header_bar.BINARY_STATES; the firmware preview test reads it.')

    def test_top_bar_and_history_card_say_the_same(self):
        for device_class, (on, off) in header_bar.BINARY_STATES.items():
            attrs = {'device_class': device_class}
            for raw, words in (('on', on), ('off', off)):
                self.assertEqual(header_bar.value('binary_sensor.x', {'state': raw, 'attributes': attrs}), (words, None))
                self.assertEqual(history_card.state_label('binary_sensor', raw, attrs), words)
        # Without a class, or with one Home Assistant adds later, all of them say On and Off.
        for attrs in ({}, {'device_class': 'future_class'}):
            self.assertEqual(header_bar.value('binary_sensor.x', {'state': 'on', 'attributes': attrs}), ('On', None))
            self.assertEqual(history_card.state_label('binary_sensor', 'off', attrs), 'Off')
        self.assertEqual((ENGLISH['screen']['ha']['on'], ENGLISH['screen']['ha']['off']), ('On', 'Off'))

    def test_the_state_message_already_carries_the_class(self):
        tile = {'entity': 'binary_sensor.front_door', 'name': ''}
        states = {'binary_sensor.front_door': {'state': 'on', 'attributes': {'device_class': 'door', 'friendly_name': 'Front door'}}}
        message = state_message(0, tile, states)
        self.assertEqual((message['state'], message['a']['device_class']), ('on', 'door'))
        self.assertNotIn('x', message)
        self.assertLessEqual(max(map(len, header_bar.BINARY_STATES)), 24)

    def test_the_fonts_carry_every_word(self):
        letters = set(''.join(on + off for on, off in header_bar.BINARY_STATES.values()))
        self.assertLessEqual(letters, set(header_bar.GLYPHS))
        for name in PROFILES:
            text = profiles.resolved(name)
            for font in ('headline', 'watch_value', 'label', 'sublabel', 'sublabel_big'):
                glyphs = profiles.glyphs(text, font)
                self.assertIsNotNone(glyphs, (name, font))
                self.assertLessEqual(letters, glyphs, (name, font))


if __name__ == '__main__':
    unittest.main()
