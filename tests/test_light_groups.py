"""A light group's lamps (app 0.3.16 / firmware 0.3.9): what the lamp page of a group gets in its state message.

The shapes below are what Home Assistant 2026.9 reports for light groups of mixed lamps: a group lists its lamps in
`entity_id`, a lamp says what it can take in `supported_color_modes` (onoff, brightness, color_temp, xy, rgb), an off
lamp reports no brightness, and a group may still name a lamp Home Assistant no longer knows.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import light_groups  # noqa: E402
from core import encode, extras, state_message  # noqa: E402
from page_delivery import Sender  # noqa: E402
from test_page_delivery import Screen  # noqa: E402


def light(state, name, modes, **attrs):
    return {'state': state, 'attributes': {'friendly_name': name, 'supported_color_modes': modes, **attrs}}


def living_room():
    return {
        'light.living_room': light('on', 'Living room', ['color_temp', 'rgb', 'xy'], brightness=64, color_temp_kelvin=2128,
                                   min_color_temp_kelvin=2000, max_color_temp_kelvin=6535, supported_features=44,
                                   entity_id=['light.tv', 'light.table', 'light.gone', 'light.cabinet', 'light.hood',
                                              'light.strip', 'light.tv', 'light.living_room', 'switch.fan']),
        'light.tv': light('on', 'TV light', ['color_temp', 'xy'], brightness=84, hs_color=[4.235, 100.0],
                          color_temp_kelvin=None, min_color_temp_kelvin=2000, max_color_temp_kelvin=6535),
        'light.table': light('on', 'Table lamp', ['brightness'], brightness=59),
        'light.cabinet': light('off', 'Cabinet', ['color_temp'], brightness=None, color_temp_kelvin=None,
                               min_color_temp_kelvin=2202, max_color_temp_kelvin=6535),
        'light.hood': light('on', 'Hood', ['onoff'], brightness=None),
        'light.strip': light('unavailable', 'Strip', ['rgb'], hs_color=None),
    }


class LampTests(unittest.TestCase):
    def test_the_lamps_of_a_group_in_home_assistants_order(self):
        lamps = light_groups.lamps('light.living_room', living_room())
        self.assertEqual([l['e'] for l in lamps], ['light.tv', 'light.table', 'light.cabinet', 'light.hood', 'light.strip'])
        tv, table, cabinet, hood, strip = lamps
        # A colour lamp with white shades: dims, colour and white, its hue, its range; no kelvin while it shows a colour.
        self.assertEqual(tv, {'e': 'light.tv', 'n': 'TV light', 's': 1, 'd': 1, 'c': 3, 'b': 33, 'h': 4, 'lo': 2000, 'hi': 6535})
        # A lamp that only dims.
        self.assertEqual(table, {'e': 'light.table', 'n': 'Table lamp', 's': 1, 'd': 1, 'b': 23})
        # An off lamp with white shades: no brightness, its own range.
        self.assertEqual(cabinet, {'e': 'light.cabinet', 'n': 'Cabinet', 'd': 1, 'c': 2, 'lo': 2202, 'hi': 6535})
        # A lamp that only switches: no slider.
        self.assertEqual(hood, {'e': 'light.hood', 'n': 'Hood', 's': 1})
        # An unavailable lamp is sent as such.
        self.assertEqual(strip['u'], 1)
        self.assertNotIn('s', strip)

    def test_a_light_that_is_not_a_group_has_none(self):
        states = living_room()
        self.assertIsNone(light_groups.lamps('light.tv', states))
        self.assertIsNone(light_groups.lamps('switch.fan', states))
        self.assertEqual(light_groups.lamp_ids('light.missing', states), [])

    def test_a_big_group_stays_inside_its_budget(self):
        states = {'light.hall': light('on', 'Hall', ['brightness'], entity_id=[f'light.lamp_{i}' for i in range(60)])}
        for i in range(60):
            states[f'light.lamp_{i}'] = light('on', 'A lamp with a rather long name number %d' % i, ['color_temp', 'xy'], brightness=200,
                                              hs_color=[123.4, 50], color_temp_kelvin=3000, min_color_temp_kelvin=2000,
                                              max_color_temp_kelvin=6535)
        lamps = light_groups.lamps('light.hall', states)
        self.assertLessEqual(len(lamps), light_groups.MAX_LAMPS)
        self.assertLessEqual(len(json.dumps(lamps, separators=(',', ':')).encode()), light_groups.LAMPS_BYTES)
        self.assertTrue(all(len(l['n']) <= light_groups.NAME_LIMIT for l in lamps))
        # The whole state message of the group, with its lamps, still fits one message to the screen.
        tile = {'entity': 'light.hall', 'name': 'Hall'}
        message = state_message(0, tile, states, extras(tile, states))
        message.setdefault('x', {})['lamps'] = lamps
        self.assertLessEqual(len(encode(message).encode()), 4096)


class HelloTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_a_screen_that_says_so_gets_lamps(self):
        screen = Screen()
        sender = Sender(screen.send)
        await sender.probe()
        self.assertFalse(sender.group_lamps)

        async def newer(message):
            answer = await screen.send(message)
            if message['op'] == 'hello':
                answer['group_lamps'] = 1
            return answer
        sender = Sender(newer)
        await sender.probe()
        self.assertTrue(sender.group_lamps)


if __name__ == '__main__':
    unittest.main()
