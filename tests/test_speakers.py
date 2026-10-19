"""Where a media player plays, on a screen (speakers.py).

- `source_list` is a player's input (Home Assistant's media_player docs): a Sonos's TV input and favourites go behind
  the input key, never in the speaker pill. Spotify's sources are the Spotify Connect devices it plays on: speakers.
- A player that reports GROUPING lists the players of its own integration that do too; the ones in `group_members`
  are ticked with their volume, and a tap joins or leaves through `media_player.join` and `media_player.unjoin`.
- A speaker whose library lists the Spotify account (a Sonos with Spotify linked) is a speaker of the Spotify tile: a
  tap plays there, and the card follows that speaker while Spotify itself plays nothing.
The states below are shaped as Home Assistant 2026.9 reports them for Spotify and Sonos.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import speakers  # noqa: E402
import media_library  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from manager_fixtures import with_screen_grid, seed_layout
    from core import validate_layout
    from server import Manager

SONOS_FEATURES = 8321599   # what a Sonos reports: GROUPING, VOLUME_SET, PLAY_MEDIA, BROWSE_MEDIA, SELECT_SOURCE, ...
ENTRY = '01M3XFSVN2KFNE8RS03ED5VEM2'
PLATFORMS = {'media_player.spotify_account': 'spotify', 'media_player.living_room': 'sonos', 'media_player.kitchen': 'sonos',
             'media_player.bedroom': 'sonos', 'media_player.tv': 'webostv'}


def sonos(name, state='idle', volume=0.2, group=None, source=None):
    attrs = {'friendly_name': name, 'supported_features': SONOS_FEATURES, 'volume_level': volume,
             'source_list': ['TV', 'Radio One', 'Radio Two'], 'group_members': group or []}
    if source:
        attrs['source'] = source
    return {'state': state, 'attributes': attrs}


def house(**changes):
    states = {
        'media_player.spotify_account': {'state': 'idle', 'attributes': {'friendly_name': 'Spotify', 'supported_features': 2048,
                                                                          'source_list': ['MacBook', 'iMac']}},
        'media_player.living_room': sonos('Living room', 'playing', 0.32, ['media_player.living_room'], 'TV'),
        'media_player.kitchen': sonos('Kitchen', volume=0.24),
        'media_player.bedroom': sonos('Bedroom'),
        'media_player.tv': {'state': 'on', 'attributes': {'friendly_name': 'TV', 'supported_features': 24509,
                                                          'source_list': ['HDMI 1', 'HDMI 2'], 'source': 'HDMI 1'}},
    }
    states.update(changes)
    return states


def menu(entity, states, holders=(), output=None):
    return speakers.menu(entity, states, PLATFORMS.get, holders, output)


class Inputs(unittest.TestCase):
    def test_a_sonos_lists_its_inputs_apart_from_its_speakers(self):
        found = menu('media_player.living_room', house())
        self.assertEqual(found['inputs'], ['TV', 'Radio One', 'Radio Two'])
        self.assertEqual(found['input'], 'TV')
        self.assertNotIn('TV', [r['name'] for r in found['rows']])

    def test_a_tv_has_inputs_and_no_speakers(self):
        found = menu('media_player.tv', house())
        self.assertEqual(found['rows'], [])
        self.assertEqual(found['inputs'], ['HDMI 1', 'HDMI 2'])
        self.assertEqual(found['pill'], '')

    def test_spotify_sources_are_speakers(self):
        found = menu('media_player.spotify_account', house())
        self.assertEqual([r['name'] for r in found['rows']], ['MacBook', 'iMac'])
        self.assertEqual(found['inputs'], [])


class Groups(unittest.TestCase):
    def test_a_sonos_lists_itself_first_and_the_others_by_name(self):
        found = menu('media_player.living_room', house())
        self.assertEqual([r['name'] for r in found['rows']], ['Living room', 'Bedroom', 'Kitchen'])
        self.assertTrue(found['rows'][0]['on'])
        self.assertTrue(all(r['groups'] for r in found['rows']))
        self.assertEqual(found['rows'][0]['volume'], 32)
        self.assertEqual(found['rows'][1]['volume'], -1)   # a volume only for the speakers that play with it
        self.assertEqual(found['pill'], 'Living room')

    def test_the_group_comes_first_and_names_the_pill(self):
        group = ['media_player.living_room', 'media_player.kitchen']
        states = house(**{'media_player.living_room': sonos('Living room', 'playing', 0.32, group),
                          'media_player.kitchen': sonos('Kitchen', 'playing', 0.24, group)})
        found = menu('media_player.living_room', states)
        self.assertEqual([r['name'] for r in found['rows']], ['Living room', 'Kitchen', 'Bedroom'])
        self.assertEqual([r['on'] for r in found['rows']], [True, True, False])
        self.assertEqual(found['pill'], 'Living room + 1')
        extras = speakers.extras(found)
        self.assertEqual(extras['sf'], [speakers.ON | speakers.GROUPS, speakers.ON | speakers.GROUPS, speakers.GROUPS])
        self.assertEqual(extras['sv'], [32, 24, -1])

    def test_join_leave_and_volume_are_home_assistants_actions(self):
        group = ['media_player.living_room', 'media_player.kitchen']
        states = house(**{'media_player.living_room': sonos('Living room', 'playing', 0.32, group),
                          'media_player.kitchen': sonos('Kitchen', 'playing', 0.24, group)})
        found = menu('media_player.living_room', states)
        bedroom, kitchen = speakers.find(found, 'Bedroom'), speakers.find(found, 'Kitchen')
        self.assertEqual(speakers.plan('media_player.living_room', found, bedroom, 'join', states)[0],
                         [('media_player', 'join', {'entity_id': 'media_player.living_room', 'group_members': ['media_player.bedroom']})])
        # A tap on the name of one that is not in the group joins it too; on one that is, nothing happens.
        self.assertEqual(speakers.plan('media_player.living_room', found, bedroom, 'pick', states)[0][0][1], 'join')
        self.assertEqual(speakers.plan('media_player.living_room', found, kitchen, 'pick', states), ([], None))
        self.assertEqual(speakers.plan('media_player.living_room', found, kitchen, 'leave', states)[0],
                         [('media_player', 'unjoin', {'entity_id': 'media_player.kitchen'})])
        self.assertEqual(speakers.plan('media_player.living_room', found, kitchen, 'volume', states, 40)[0],
                         [('media_player', 'volume_set', {'entity_id': 'media_player.kitchen', 'volume_level': 0.4})])

    def test_a_speaker_alone_has_nothing_to_leave(self):
        found = menu('media_player.living_room', house())
        self.assertEqual(speakers.plan('media_player.living_room', found, found['rows'][0], 'leave', house()), ([], None))

    def test_cast_and_music_assistant_groups_are_pickable_targets(self):
        cast_group = {'state': 'idle', 'attributes': {'friendly_name': 'Downstairs Cast',
                                                        'device_class': 'speaker', 'supported_features': 512}}
        ma_group = {'state': 'idle', 'attributes': {'friendly_name': 'Downstairs Music Assistant',
                                                     'device_class': 'speaker', 'supported_features': 8321599,
                                                     'group_members': ['media_player.kitchen', 'media_player.bedroom']}}
        spotify = {'state': 'playing', 'attributes': {'friendly_name': 'Spotify', 'supported_features': 2048 | 512,
                                                       'media_content_id': 'spotify:track:abc',
                                                       'media_content_type': 'music'}}
        states = house(**{'media_player.cast_group': cast_group, 'media_player.ma_group': ma_group,
                          'media_player.spotify_account': spotify})
        found = menu('media_player.spotify_account', states)
        cast, ma = speakers.find(found, 'Downstairs Cast'), speakers.find(found, 'Downstairs Music Assistant')
        self.assertIsNotNone(cast)
        self.assertIsNotNone(ma)
        self.assertTrue(cast['plays'] and ma['plays'])
        self.assertFalse(cast['groups'] or ma['groups'])
        steps, follow = speakers.plan('media_player.spotify_account', found, ma, 'join', states)
        self.assertEqual(steps, [('media_player', 'play_media', {'entity_id': 'media_player.ma_group',
                                                                  'media_content_type': 'music',
                                                                  'media_content_id': 'spotify:track:abc'}),
                                 ('media_player', 'media_pause', {'entity_id': 'media_player.spotify_account'})])
        self.assertEqual(follow, 'media_player.ma_group')

    def test_an_unavailable_speaker_is_not_listed(self):
        states = house(**{'media_player.bedroom': {'state': 'unavailable', 'attributes': {'friendly_name': 'Bedroom', 'supported_features': SONOS_FEATURES}}})
        self.assertNotIn('Bedroom', [r['name'] for r in menu('media_player.living_room', states)['rows']])


class LibrarySpeakers(unittest.TestCase):
    HOLDERS = ('media_player.bedroom', 'media_player.kitchen', 'media_player.living_room')

    def test_a_library_lists_the_account_by_its_config_entry(self):
        self.assertTrue(speakers.holds_account(['favorites', 'spotify://' + ENTRY, 'media-source://tts'], ENTRY))
        self.assertTrue(speakers.holds_account(['spotify://' + ENTRY.lower()], ENTRY))
        self.assertFalse(speakers.holds_account(['favorites', 'media-source://camera'], ENTRY))
        self.assertFalse(speakers.holds_account(['spotify://' + ENTRY], None))

    def test_the_spotify_tile_lists_connect_devices_and_the_speakers_of_its_library(self):
        found = menu('media_player.spotify_account', house(), self.HOLDERS)
        self.assertEqual([r['name'] for r in found['rows']], ['MacBook', 'iMac', 'Bedroom', 'Kitchen', 'Living room'])
        # Every speaker that groups shows its plus at once; the first one starts the music there.
        self.assertEqual([r['groups'] for r in found['rows']], [False, False, True, True, True])
        steps, follow = speakers.plan('media_player.spotify_account', found, speakers.find(found, 'Kitchen'), 'join', house())
        self.assertEqual((steps, follow), ([], 'media_player.kitchen'))
        self.assertIsNone(found['target'])

    def test_picking_a_speaker_moves_what_plays_and_the_card_follows_it(self):
        states = house(**{'media_player.spotify_account': {'state': 'playing', 'attributes': {
            'friendly_name': 'Spotify', 'supported_features': 2048 | 512 | 1, 'source_list': ['MacBook'], 'source': 'MacBook',
            'media_content_id': 'spotify:track:abc', 'media_content_type': 'music'}}})
        found = menu('media_player.spotify_account', states, self.HOLDERS)
        steps, follow = speakers.plan('media_player.spotify_account', found, speakers.find(found, 'Kitchen'), 'pick', states)
        self.assertEqual(steps, [('media_player', 'play_media', {'entity_id': 'media_player.kitchen', 'media_content_type': 'music',
                                                                 'media_content_id': 'spotify:track:abc'}),
                                 ('media_player', 'media_pause', {'entity_id': 'media_player.spotify_account'})])
        self.assertEqual(follow, 'media_player.kitchen')
        # The Connect device it plays on already: nothing to do.
        self.assertEqual(speakers.plan('media_player.spotify_account', found, speakers.find(found, 'MacBook'), 'pick', states), ([], None))

    def test_a_followed_speaker_groups_with_the_others(self):
        found = menu('media_player.spotify_account', house(), self.HOLDERS, output='media_player.living_room')
        self.assertEqual(found['target'], 'media_player.living_room')
        self.assertEqual(found['pill'], 'Living room')
        living, kitchen = speakers.find(found, 'Living room'), speakers.find(found, 'Kitchen')
        self.assertTrue(living['on'] and living['groups'] and living['volume'] == 32)
        self.assertTrue(kitchen['groups'] and not kitchen['on'])
        self.assertFalse(speakers.find(found, 'MacBook')['on'])
        self.assertEqual(speakers.plan('media_player.spotify_account', found, kitchen, 'join', house())[0],
                         [('media_player', 'join', {'entity_id': 'media_player.living_room', 'group_members': ['media_player.kitchen']})])
        self.assertEqual(speakers.extras(found)['ct'], 'media_player.living_room')

    def test_the_card_stops_following_when_spotify_plays_itself_again(self):
        states = house(**{'media_player.spotify_account': {'state': 'playing', 'attributes': {'friendly_name': 'Spotify',
                                                                                                'source_list': ['MacBook'], 'source': 'MacBook'}}})
        self.assertIsNone(speakers.target_of('media_player.spotify_account', states, 'media_player.living_room'))
        gone = house(**{'media_player.living_room': {'state': 'unavailable', 'attributes': {}}})
        self.assertIsNone(speakers.target_of('media_player.spotify_account', gone, 'media_player.living_room'))

    def test_a_connect_device_with_a_speakers_name_is_one_row(self):
        states = house(**{'media_player.spotify_account': {'state': 'idle', 'attributes': {
            'friendly_name': 'Spotify', 'supported_features': 2048, 'source_list': ['Kitchen', 'MacBook']}}})
        found = menu('media_player.spotify_account', states, self.HOLDERS)
        self.assertEqual([r['name'] for r in found['rows']].count('Kitchen'), 1)
        kitchen = speakers.find(found, 'Kitchen')
        self.assertEqual((kitchen['source'], kitchen['entity']), ('Kitchen', 'media_player.kitchen'))
        # Spotify Connect moves itself there: the native way first.
        steps, follow = speakers.plan('media_player.spotify_account', found, kitchen, 'pick', states)
        self.assertEqual(steps, [('media_player', 'select_source', {'entity_id': 'media_player.spotify_account', 'source': 'Kitchen'})])
        self.assertEqual(follow, '')



@unittest.skipUnless(HAS_AIOHTTP, 'needs aiohttp')
class TheApp(unittest.IsolatedAsyncioTestCase):
    """The add-on's side: the libraries it reads to find the speakers of an account, the menu a screen gets with the
    player's state, a tap that moves Spotify to a Sonos, and the card that follows the Sonos from then on."""

    def ha(self):
        class HA:
            online = True

            def __init__(self):
                self.registry = [{'entity_id': 'text.d1_tiles', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                                 {'entity_id': 'sensor.d1_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                                 {'entity_id': 'sensor.d1_fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'},
                                 {'entity_id': 'select.d1_type', 'platform': 'esphome', 'original_name': 'Guition screen type', 'device_id': 'd1'},
                                 {'entity_id': 'media_player.spotify_account', 'platform': 'spotify', 'config_entry_id': ENTRY},
                                 *({'entity_id': e, 'platform': p} for e, p in PLATFORMS.items() if p != 'spotify')]
                self.devices, self.areas = [{'id': 'd1', 'name': 'Hall'}], []
                self.states = {'text.d1_tiles': {'state': 'Synced'}, 'sensor.d1_node': {'state': 'hall'}, 'sensor.d1_fw': {'state': '0.26.0'},
                               **house(**{'media_player.spotify_account': {'state': 'playing', 'attributes': {
                                   'friendly_name': 'Spotify', 'supported_features': 444983, 'source_list': ['MacBook'], 'source': 'MacBook',
                                   'media_content_id': 'spotify:track:abc', 'media_content_type': 'music', 'media_title': 'On the laptop'}}})}
                self.changed, self.dirty, self.log, self.responses = asyncio.Event(), set(), [], set()

            def platform_of(self, entity):
                return next((r.get('platform') for r in self.registry if r.get('entity_id') == entity), None)

            async def send(self, inbox, message, action=None, respond=False):
                self.log.append(('send', inbox, dict(message)))

            async def call_answer(self, domain, service, data):
                # A Sonos lists the linked Spotify account at the top of its library, as Home Assistant's Sonos does.
                entity = data['entity_id']
                children = [{'title': 'Favorites', 'media_class': 'directory', 'media_content_type': 'favorites', 'media_content_id': '',
                             'can_play': False, 'can_expand': True}]
                if PLATFORMS.get(entity) == 'sonos':
                    children.append({'title': 'Spotify', 'media_class': 'directory', 'media_content_type': 'spotify://library',
                                     'media_content_id': 'spotify://' + ENTRY, 'can_play': False, 'can_expand': True})
                return {entity: {'title': 'Media', 'children': children}}

            async def call_service(self, domain, service, data):
                self.log.append(('call', service, data))
                if service == 'play_media':
                    sonos = self.states[data['entity_id']]
                    sonos['state'] = 'playing'
                    sonos['attributes'] = {**sonos['attributes'], 'media_title': 'On the Sonos'}
                if service == 'media_pause':
                    self.states[data['entity_id']]['state'] = 'paused'

            async def request(self, kind, **data):
                raise ConnectionError(kind)
        return HA()

    async def test_spotify_plays_on_a_sonos_and_its_card_follows(self):
        both = frozenset({media_library.FEATURE, speakers.FEATURE})
        with tempfile.TemporaryDirectory() as tmp:
            ha = self.ha()
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            spotify = 'media_player.spotify_account'
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Music', 'tiles': [{'entity': spotify, 'name': 'Spotify'},
                                                                                        {'entity': 'media_player.living_room', 'name': ''}]}))
            tile = {'entity': spotify, 'name': 'Spotify', 'options': {}}
            await m.tile_message(0, tile, features=both)
            await asyncio.sleep(0.05)   # the speakers' libraries are read once
            message = await m.tile_message(0, tile, features=both)
            self.assertEqual(message['x']['sl'], ['MacBook', 'Bedroom', 'Kitchen', 'Living room'])
            self.assertEqual(message['x']['so'], 'MacBook')
            self.assertNotIn('in', message['x'])
            old = await m.tile_message(0, tile, features=frozenset({media_library.FEATURE}))
            self.assertEqual(old['x']['sl'], ['MacBook'], 'a screen before speaker_groups keeps source_list')
            # A tap on a Sonos: what plays moves there, Spotify pauses, and the card follows the Sonos.
            await m.answer_speaker({'inbox': 'text.d1_tiles', 'entity': spotify, 'speaker': 'Living room', 'op': 'pick'})
            self.assertEqual([(e[1], e[2]['entity_id']) for e in ha.log if e[0] == 'call'],
                             [('play_media', 'media_player.living_room'), ('media_pause', spotify)])
            message = await m.tile_message(0, tile, features=both)
            self.assertEqual(message['x']['ct'], 'media_player.living_room')
            self.assertEqual(message['a']['media_title'], 'On the Sonos')
            self.assertEqual(message['state'], 'playing')
            self.assertEqual(message['x']['so'], 'Living room')
            self.assertEqual(m.followed(spotify), 'media_player.living_room')
            # A library tap now plays on the Sonos it follows.
            ha.log.clear()
            m.shelves['text.d1_tiles'] = media_library.Shelf()
            token = m.shelves['text.d1_tiles'].token(spotify, {'title': 'Drive', 'id': 'spotify:playlist:x', 'type': 'spotify://playlist',
                                                             'play': True, 'expand': True, 'thumb': None, 'icon': 'F0CB8', 'class': 'playlist'})
            await m.answer_play({'inbox': 'text.d1_tiles', 'entity': spotify, 'item': str(token)})
            self.assertEqual([(e[1], e[2]['entity_id'], e[2].get('media_content_id')) for e in ha.log if e[0] == 'call'],
                             [('play_media', 'media_player.living_room', 'spotify:playlist:x')])
            # The Sonos's own tile: its group and its inputs.
            sonos = await m.tile_message(1, {'entity': 'media_player.living_room', 'name': '', 'options': {}}, features=both)
            self.assertEqual(sonos['x']['in'], ['TV', 'Radio One', 'Radio Two'])
            self.assertEqual(sonos['x']['sl'][0], 'Living room')
            # Spotify plays on the laptop again: the card is Spotify's own once more.
            ha.states[spotify]['state'] = 'playing'
            message = await m.tile_message(0, tile, features=both)
            self.assertNotIn('ct', message['x'])
            self.assertNotIn(spotify, m.outputs)


if __name__ == '__main__':
    unittest.main()
