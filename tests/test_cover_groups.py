"""A cover group's covers (firmware 0.57.0): what the group page of a cover group gets in its state message.

The shapes below are what Home Assistant reports for a cover group (the group helper) of mixed covers: the group lists
its members in `entity_id`, a venetian blind reports its position and its tilt, a roller shade its position only, a
motor without a position neither, a group may name a cover Home Assistant no longer knows, and one may be unavailable.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import cover_groups  # noqa: E402
from core import encode, extras, state_message  # noqa: E402


def cover(state, name, features, **attrs):
    return {'state': state, 'attributes': {'friendly_name': name, 'supported_features': features, **attrs}}


def living_room():
    return {
        'cover.living_room': cover('open', 'Living room', 255, current_position=60, current_tilt_position=45,
                                   entity_id=['cover.left', 'cover.right', 'cover.gone', 'cover.bay', 'cover.left',
                                              'cover.living_room', 'switch.fan', 'cover.broken']),
        'cover.left': cover('open', 'Left', 255, current_position=60, current_tilt_position=45, device_class='blind'),
        'cover.right': cover('closed', 'Right', 255, current_position=0, current_tilt_position=0, device_class='blind'),
        'cover.bay': cover('opening', 'Bay window', 11, device_class='curtain'),
        'cover.broken': cover('unavailable', 'Broken', 255, restored=True),
    }


class CoverTests(unittest.TestCase):
    def test_the_covers_of_a_group_in_home_assistants_order(self):
        covers = cover_groups.covers('cover.living_room', living_room())
        self.assertEqual([c['e'] for c in covers], ['cover.left', 'cover.right', 'cover.bay', 'cover.broken'])
        left, right, bay, broken = covers
        # A venetian blind: its state, its own features, its position and its tilt, its device class.
        self.assertEqual(left, {'e': 'cover.left', 'n': 'Left', 's': 'open', 'f': 255, 'p': 60, 't': 45, 'dc': 'blind'})
        # Closed and tilted shut: the zeros travel, they are values.
        self.assertEqual((right['p'], right['t'], right['s']), (0, 0, 'closed'))
        # A curtain on its way, without a position: its keys point sideways on the screen.
        self.assertEqual(bay, {'e': 'cover.bay', 'n': 'Bay window', 's': 'opening', 'f': 11, 'dc': 'curtain'})
        # An unavailable cover is sent as such, without a state.
        self.assertEqual(broken['u'], 1)
        self.assertNotIn('s', broken)

    def test_a_cover_that_is_not_a_group_has_none(self):
        states = living_room()
        self.assertIsNone(cover_groups.covers('cover.left', states))
        self.assertIsNone(cover_groups.covers('switch.fan', states))
        self.assertEqual(cover_groups.cover_ids('light.living_room', states), [])

    def test_a_big_group_stays_inside_its_budget(self):
        states = {'cover.house': cover('open', 'House', 255, entity_id=[f'cover.blind_{i}' for i in range(60)])}
        for i in range(60):
            states[f'cover.blind_{i}'] = cover('open', 'A blind with a rather long name number %d' % i, 255,
                                               current_position=55, current_tilt_position=40, device_class='blind')
        covers = cover_groups.covers('cover.house', states)
        self.assertLessEqual(len(covers), cover_groups.MAX_COVERS)
        self.assertLessEqual(len(json.dumps(covers, separators=(',', ':')).encode()), cover_groups.COVERS_BYTES)
        self.assertTrue(all(len(c['n']) <= cover_groups.NAME_LIMIT for c in covers))
        # The whole state message of the group, with its covers, still fits one message to the screen.
        tile = {'entity': 'cover.house', 'name': 'House'}
        message = state_message(0, tile, states, extras(tile, states))
        message.setdefault('x', {})['covers'] = covers
        self.assertLessEqual(len(encode(message).encode()), 4096)

    def test_the_firmware_reads_what_the_app_sends(self):
        # The keys page_receiver.cpp reads for a cover of a group, and the feature its hello says.
        receiver = (ROOT / 'components/smart_display/page_receiver.cpp').read_text()
        for key in ('"e"', '"n"', '"s"', '"dc"', '"u"', '"f"', '"p"', '"t"'):
            self.assertIn(f'c[{key}]', receiver)
        self.assertIn('extra["covers"]', receiver)
        self.assertIn(f'features.add("{cover_groups.FEATURE}")', (ROOT / 'packages/core.yaml').read_text())


if __name__ == '__main__':
    unittest.main()
