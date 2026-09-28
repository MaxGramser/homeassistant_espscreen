"""Live speaker groups, bounded device packets and no playback side effects."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
import media_groups as groups


def player(name, members, volume=.32, **attrs):
    return {'state': 'playing', 'attributes': {'friendly_name': name, 'group_members': members,
        'volume_level': volume, 'supported_features': groups.GROUPING | 12, **attrs}}


class Speakers(unittest.TestCase):
    def setUp(self):
        self.states = {
            'media_player.a': player('Kitchen', ['media_player.a', 'media_player.b']),
            'media_player.b': player('Dining', ['media_player.a', 'media_player.b'], .18),
            'media_player.c': player('Office', ['media_player.c'], .51),
            'media_player.other': player('Other integration', ['media_player.other']),
            'media_player.spotify': player('Spotify', [], supported_features=12),
        }
        self.ha = SimpleNamespace(states=self.states, platform_of=lambda e: 'different' if e == 'media_player.other' else 'sonos')
        self.fields = {'entity': 'media_player.a', 'schema': '1'}

    def test_current_groups_deduplicate_and_use_each_speakers_volume(self):
        packet = groups.snapshot(self.ha, self.fields)
        self.assertEqual(packet['groups'], [{'e': 'media_player.a', 'n': 'Kitchen + Dining'}, {'e': 'media_player.c', 'n': 'Office'}])
        self.assertEqual([s['v'] for s in packet['speakers']], [32, 18])
        self.assertTrue(all(s['enabled'] for s in packet['speakers']))
        other = groups.snapshot(self.ha, {**self.fields, 'group': 'media_player.c'})
        self.assertEqual([s['e'] for s in other['speakers']], ['media_player.c'])
        self.assertEqual(self.states['media_player.a']['attributes']['group_members'], ['media_player.a', 'media_player.b'])

    def test_regrouping_deleted_and_unavailable_members(self):
        self.states['media_player.b']['state'] = 'unavailable'
        self.assertFalse(groups.snapshot(self.ha, self.fields)['speakers'][1]['enabled'])
        for entity in ['media_player.a', 'media_player.b', 'media_player.c']:
            self.states[entity]['attributes']['group_members'] = [entity]
        self.assertEqual(len(groups.snapshot(self.ha, self.fields)['groups']), 3)
        self.states['media_player.a']['attributes']['group_members'] = ['media_player.a', 'media_player.deleted']
        self.assertEqual(groups.snapshot(self.ha, self.fields)['speakers'], [])

    def test_non_grouping_player_and_unknown_platform(self):
        self.assertEqual(groups.snapshot(self.ha, {**self.fields, 'entity': 'media_player.spotify'})['groups'], [])
        self.ha.platform_of = lambda e: None
        self.assertEqual(len(groups.snapshot(self.ha, self.fields)['groups']), 1)

    def test_pagination_payload_bound_and_unusable_volumes(self):
        ids = ['media_player.' + f'{i:02}' * 35 for i in range(12)]
        for entity in ids:
            self.states[entity] = player('長' * 100, ids, float('nan'))
        fields = {**self.fields, 'entity': ids[0], 'count': '4'}
        packet = groups.snapshot(self.ha, fields)
        self.assertEqual(packet['pages'], 3)
        self.assertEqual(len(packet['speakers']), 4)
        self.assertTrue(all(s['v'] == -1 and not s['enabled'] for s in packet['speakers']))
        self.assertLess(len(json.dumps(packet, ensure_ascii=False).encode()), 3500)
        last = groups.snapshot(self.ha, {**fields, 'page': '999'})
        self.assertEqual(last['page'], 2)
        self.assertEqual([s['e'] for s in last['speakers']], ids[8:])

    def test_versioned_preview_requests_are_scoped_and_read_only(self):
        command = {'service': groups.EVENT, 'event': True, 'data': {**self.fields,
            'session': 'a' * 16, 'rev': 'b' * 16, 'view': '7'}}
        packet = groups.preview_answer(self.ha, command)
        self.assertEqual((packet['view'], packet['session'], packet['rev']), (7, 'a' * 16, 'b' * 16))
        for extra in [{'schema': '2'}, {'entity': 'switch.test'}, {'count': '20'}, {'gp': '-1'}, {'view': 'bad'}]:
            with self.assertRaises(ValueError):
                groups.preview_answer(self.ha, {**command, 'data': {**command['data'], **extra}})
        with self.assertRaises(ValueError):
            groups.preview_answer(self.ha, {**command, 'event': False})


if __name__ == '__main__':
    unittest.main()
