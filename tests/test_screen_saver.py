"""The screensaver (app 0.4.48, firmware 0.29.0): what a screen shows in standby instead of its dimmed tiles.

- Each screen keeps its own choice, by its Home Assistant device, in screensavers.json beside the layouts: a media
  player, a camera and the order of the steps, with the clock as a step of its own. The layouts' storage is untouched.
- The app picks the first step that is on and available: a player that plays with a cover, a camera Home Assistant has,
  the clock always. A board without pictures has the clock alone.
- A screen whose hello lists `screensaver` hears what to show in one small message, when it changes and once in every
  session; it may then load that player's cover and that camera, which are on none of its tiles.
"""
from manager_fixtures import with_screen_grid, seed_layout
import asyncio
import importlib.util
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import header_bar  # noqa: E402
import screen_saver  # noqa: E402
from core import SCREENSAVER_MIN_FIRMWARE, media_extras, short, validate_layout  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import Manager

PLAYER, CAMERA = 'media_player.living_room', 'camera.front_door'
PLAYING = {'state': 'playing', 'attributes': {'friendly_name': 'Living room', 'media_title': 'Song', 'media_artist': 'Band',
                                              'media_duration': 200, 'entity_picture': '/api/media_player_proxy/x?cache=1'}}
DOOR = {'state': 'idle', 'attributes': {'friendly_name': 'Front door'}}
CHOICE = {'show': True, 'media': PLAYER, 'camera': CAMERA, 'order': ['media', 'camera', 'clock'], 'off': [], 'weather': 'auto', 'more': [], 'items': []}


class Choice(unittest.TestCase):
    def test_a_choice_is_checked_and_filled_in(self):
        self.assertEqual(screen_saver.validate({}), screen_saver.DEFAULT)
        self.assertEqual(screen_saver.validate({'show': True})['order'], ['media', 'camera', 'clock'])
        for wrong in ({'show': 'yes'}, {'media': 'camera.front'}, {'camera': 'media_player.x'}, {'media': 'Media Player'},
                      {'order': ['media', 'clock']}, {'order': ['media', 'media', 'clock']}, {'off': ['tv']}, {'colour': 1}, None):
            with self.assertRaises(ValueError, msg=wrong):
                screen_saver.validate(wrong)
        # An image entity is a camera too (a doorbell's last snapshot), as on an alert.
        self.assertEqual(screen_saver.validate({'camera': 'image.doorbell'})['camera'], 'image.doorbell')
        # What is off keeps the order's order.
        self.assertEqual(screen_saver.validate({'order': ['clock', 'camera', 'media'], 'off': ['media', 'clock']})['off'], ['clock', 'media'])

    def test_the_first_step_that_is_available(self):
        states = {PLAYER: PLAYING, CAMERA: DOOR}
        self.assertEqual(screen_saver.pick(CHOICE, states, True), 'media')
        paused = {**states, PLAYER: {**PLAYING, 'state': 'paused'}}
        self.assertEqual(screen_saver.pick(CHOICE, paused, True), 'camera')
        bare = {**states, PLAYER: {'state': 'playing', 'attributes': {'media_title': 'Radio'}}}
        self.assertEqual(screen_saver.pick(CHOICE, bare, True), 'camera', 'a player without a cover is not the screensaver')
        gone = {**paused, CAMERA: {'state': 'unavailable'}}
        self.assertEqual(screen_saver.pick(CHOICE, gone, True), 'clock')
        self.assertEqual(screen_saver.pick({**CHOICE, 'off': ['clock']}, gone, True), '', 'nothing available: dark as before')
        self.assertEqual(screen_saver.pick({**CHOICE, 'order': ['clock', 'media', 'camera']}, states, True), 'clock')
        self.assertEqual(screen_saver.pick({**CHOICE, 'show': False}, states, True), '')
        # A board without pictures: the clock alone.
        self.assertEqual(screen_saver.pick(CHOICE, states, False), 'clock')

    def test_the_music_step_tries_its_players_in_their_order(self):
        """App 0.4.54: a speaker first and the television under it next; the step shows the first that plays with a cover."""
        tv = 'media_player.apple_tv'
        poster = {'state': 'playing', 'attributes': {'friendly_name': 'Apple TV', 'media_title': 'Series',
                                                     'entity_picture': '/api/media_player_proxy/tv?cache=2'}}
        choice = {**CHOICE, 'more': [tv]}
        self.assertEqual(screen_saver.validate(choice)['more'], [tv])
        self.assertEqual(screen_saver.players(choice), [PLAYER, tv])
        self.assertEqual(screen_saver.entities(choice), {PLAYER, tv, CAMERA})
        both = {PLAYER: PLAYING, tv: poster, CAMERA: DOOR}
        self.assertEqual(screen_saver.player(choice, both), PLAYER)
        # The speaker plays the television's sound: it plays, without a cover, so the television's poster shows.
        sound = {**both, PLAYER: {'state': 'playing', 'attributes': {'friendly_name': 'Living room', 'source': 'TV'}}}
        self.assertEqual(screen_saver.player(choice, sound), tv)
        said = screen_saver.message(choice, sound, True, short, media_extras)
        self.assertEqual((said['k'], said['e'], said['n'], said['t']), ('media', tv, 'Apple TV', 'Series'))
        # Neither plays: the next step. A paused television keeps its poster in Home Assistant and still counts as off.
        idle = {**sound, tv: {**poster, 'state': 'paused'}}
        self.assertEqual((screen_saver.player(choice, idle), screen_saver.pick(choice, idle, True)), ('', 'camera'))
        # Without a first player the others still count, and a board without pictures has the clock alone.
        self.assertEqual(screen_saver.message({**choice, 'media': ''}, both, True, short, media_extras)['e'], tv)
        self.assertEqual(screen_saver.pick(choice, both, False), 'clock')
        for wrong in ([PLAYER], [tv, tv], ['camera.front_door'], ['Media Player'], [''], [f'media_player.p{i}' for i in range(4)], tv, [1]):
            with self.assertRaises(ValueError, msg=wrong):
                screen_saver.validate({**CHOICE, 'more': wrong})
        # A choice kept before 0.4.54 has one player.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screensavers.json'
            path.write_text(json.dumps({'version': 1, 'screens': {'d1': {key: CHOICE[key] for key in CHOICE if key != 'more'}}}))
            self.assertEqual(screen_saver.ScreenSavers(path).get('d1'), CHOICE)

    def test_a_screen_with_keys_keeps_a_paused_player_for_a_while(self):
        """App 0.4.55, firmware 0.33.0: the screensaver has play or pause and the volume, so a player paused there still
        shows; one that plays goes first, and a pause of long ago gives way to the camera."""
        tv = 'media_player.apple_tv'
        now = 1_800_000_000
        stamp = lambda ago: datetime.fromtimestamp(now - ago, timezone.utc).isoformat()
        paused = {**PLAYING, 'state': 'paused', 'last_changed': stamp(30)}
        poster = {'state': 'playing', 'attributes': {'friendly_name': 'Apple TV', 'media_title': 'Series', 'supported_features': 3,
                                                     'entity_picture': '/api/media_player_proxy/tv?cache=2'}}
        choice = {**CHOICE, 'more': [tv]}
        states = {PLAYER: paused, tv: poster, CAMERA: DOOR}
        # Without keys nothing changed: a paused player is no step.
        self.assertEqual(screen_saver.pick(CHOICE, {PLAYER: paused, CAMERA: DOOR}, True), 'camera')
        self.assertEqual(screen_saver.player(CHOICE, {PLAYER: paused}, True, now), PLAYER)
        # One that plays goes before one that is paused, whatever their order.
        self.assertEqual(screen_saver.player(choice, states, True, now), tv)
        self.assertEqual(screen_saver.player(choice, {**states, tv: {**poster, 'state': 'paused', 'last_changed': stamp(5)}}, True, now), PLAYER)
        # The player on the glass, paused there, keeps it for two minutes although the other plays; then that one shows.
        self.assertEqual(screen_saver.player(choice, states, True, now, held=PLAYER), PLAYER)
        later = {**states, PLAYER: {**paused, 'last_changed': stamp(screen_saver.HELD_SECONDS + 1)}}
        self.assertEqual(screen_saver.player(choice, later, True, now, held=PLAYER), tv)
        self.assertEqual(screen_saver.player(choice, states, True, now, held='media_player.gone'), tv)
        self.assertEqual(screen_saver.player(choice, states, False, now, held=PLAYER), tv)
        # Ten minutes after the pause the next step shows, and a paused player without a cover never did.
        old = {PLAYER: {**paused, 'last_changed': stamp(screen_saver.PAUSED_SECONDS + 1)}, CAMERA: DOOR}
        self.assertEqual(screen_saver.pick(CHOICE, old, True, True, now), 'camera')
        self.assertEqual(screen_saver.player(CHOICE, {PLAYER: {'state': 'paused', 'attributes': {}, 'last_changed': stamp(5)}}, True, now), '')
        self.assertEqual(screen_saver.player(CHOICE, {PLAYER: {**paused, 'last_changed': None}}, True, now), '')
        # The message names the state and what the player can do, for the keys; a screen without keys gets neither.
        said = screen_saver.message(CHOICE, {PLAYER: {**paused, 'attributes': {**paused['attributes'], 'supported_features': 21437}}},
                                    True, short, media_extras, keys=True, now=now)
        self.assertEqual((said['k'], said['e'], said['s'], said['f']), ('media', PLAYER, 'paused', 21437))
        plain = screen_saver.message(CHOICE, {PLAYER: PLAYING}, True, short, media_extras)
        self.assertTrue('s' not in plain and 'f' not in plain)
        self.assertEqual(screen_saver.message(CHOICE, {PLAYER: PLAYING}, True, short, media_extras, keys=True)['f'], 0)
        # A muted player says so, for the volume keys.
        muted = {PLAYER: {**PLAYING, 'attributes': {**PLAYING['attributes'], 'is_volume_muted': True}}}
        self.assertEqual(screen_saver.message(CHOICE, muted, True, short, media_extras, keys=True)['m'], 1)
        self.assertNotIn('m', screen_saver.message(CHOICE, {PLAYER: PLAYING}, True, short, media_extras, keys=True))
        self.assertNotIn('m', screen_saver.message(CHOICE, muted, True, short, media_extras))

    def test_the_message_carries_what_the_screen_draws(self):
        states = {PLAYER: PLAYING, CAMERA: DOOR}
        media = screen_saver.message(CHOICE, states, True, short, media_extras, lambda e, a: '102030,102030')
        self.assertEqual((media['op'], media['k'], media['e'], media['n'], media['t']), ('saver', 'media', PLAYER, 'Living room', 'Song'))
        self.assertEqual((media['x']['artist'], media['x']['g']), ('Band', '102030,102030'))
        self.assertIn('pic', media['x'])
        # Where the track is shows nowhere: a new position is no new message.
        self.assertEqual(set(media['x']), {'artist', 'pic', 'g'})
        camera = screen_saver.message({**CHOICE, 'off': ['media']}, states, True, short, media_extras)
        self.assertEqual(camera, {'op': 'saver', 'k': 'camera', 'e': CAMERA, 'n': 'Front door'})
        self.assertEqual(screen_saver.message(CHOICE, states, False, short, media_extras), {'op': 'saver', 'k': 'clock'})
        self.assertEqual(screen_saver.message({**CHOICE, 'show': False}, states, True, short, media_extras), {'op': 'saver', 'k': ''})

    def test_the_clock_shows_the_outside_temperature(self):
        """App 0.4.52: under the clock the outside temperature, whole degrees in Home Assistant's own unit, from its
        first weather entity unless the owner chose one, or none."""
        home = {'state': 'cloudy', 'attributes': {'temperature': 21.6, 'temperature_unit': '°C', 'friendly_name': 'Home'}}
        north = {'state': 'sunny', 'attributes': {'temperature': 70.4, 'temperature_unit': '°F'}}
        states = {'weather.home': home, 'weather.north': north, 'weather.broken': {'state': 'unavailable', 'attributes': {}}}
        clock = {**CHOICE, 'off': ['media', 'camera']}
        self.assertEqual(screen_saver.message(clock, states, True, short, media_extras), {'op': 'saver', 'k': 'clock', 'w': '22°'})
        self.assertEqual(screen_saver.message({**clock, 'weather': 'weather.north'}, states, True, short, media_extras)['w'], '70°')
        self.assertNotIn('w', screen_saver.message({**clock, 'weather': ''}, states, True, short, media_extras))
        self.assertNotIn('w', screen_saver.message({**clock, 'weather': 'weather.broken'}, states, True, short, media_extras))
        # The forecast Home Assistant made for its home comes first, whatever its id sorts as.
        self.assertEqual(screen_saver.weather_entity(clock, {**states, 'weather.forecast_home': home}), 'weather.forecast_home')
        # Without a weather entity in Home Assistant there is no temperature, and minus zero is zero.
        self.assertEqual(screen_saver.message(clock, {}, True, short, media_extras), {'op': 'saver', 'k': 'clock'})
        self.assertEqual(screen_saver.temperature(clock, {'weather.cold': {'state': 'snowy', 'attributes': {'temperature': -0.4}}}), '0°')
        self.assertEqual(screen_saver.temperature(clock, {'weather.cold': {'state': 'snowy', 'attributes': {'temperature': -3.6}}}), '-4°')
        # A picture step carries no temperature, and the app follows the weather entity so a new value goes out.
        self.assertNotIn('w', screen_saver.message(CHOICE, {**states, PLAYER: PLAYING}, True, short, media_extras))
        self.assertIn('weather.home', screen_saver.entities(clock, states))
        self.assertNotIn('weather.home', screen_saver.entities({**clock, 'show': False}, states))
        self.assertEqual(screen_saver.validate({'weather': 'weather.home'})['weather'], 'weather.home')
        for wrong in ('sensor.outside', 'Weather', 7):
            with self.assertRaises(ValueError):
                screen_saver.validate({'weather': wrong})
        # A choice kept before 0.4.52 reads as the automatic temperature.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screensavers.json'
            path.write_text('{"version": 1, "screens": {"d1": {"show": true, "media": "", "camera": "", "order": ["media", "camera", "clock"], "off": []}}}')
            self.assertEqual(screen_saver.ScreenSavers(path).get('d1')['weather'], 'auto')

    def test_the_clock_shows_entities_beside_the_temperature(self):
        """App 0.4.81: the top bar's entity items on the clock, by their text, their icon or both, one row after the
        temperature; a screen that did not say it takes the row gets the temperature alone."""
        home = {'state': 'cloudy', 'attributes': {'temperature': 21.6, 'temperature_unit': '°C'}}
        door = {'state': 'on', 'attributes': {'device_class': 'door', 'friendly_name': 'Door'}}
        items = [{'type': 'entity', 'entity': 'binary_sensor.door', 'content': 'state', 'icon': 'none', 'show': 'always'},
                 {'type': 'entity', 'entity': 'sensor.power', 'content': 'icon', 'icon': 'auto', 'show': 'always'}]
        states = {'weather.home': home, 'binary_sensor.door': door, 'sensor.power': {'state': '5', 'attributes': {}}}
        clock = {**CHOICE, 'off': ['media', 'camera'], 'items': screen_saver.valid_items(items)}
        # The top bar's own wire items, without their colour: the clock has one ink.
        bar = lambda item: header_bar.entity_item(item, states)[0]
        row = screen_saver.message(clock, states, True, short, media_extras, bar=bar)
        self.assertEqual(row['w'], '22°')
        self.assertEqual(row['wi'], [{'k': 'text', 't': '22°'}, {'k': 'text', 't': 'Open'},
                                     {'k': 'text', 'i': bar(items[1])['i'], 't': ''}])
        self.assertNotIn('wi', screen_saver.message(clock, states, True, short, media_extras))
        self.assertNotIn('wi', screen_saver.message({**clock, 'items': []}, states, True, short, media_extras, bar=bar))
        self.assertNotIn('wi', screen_saver.message(CHOICE, {**states, PLAYER: PLAYING}, True, short, media_extras, bar=bar))
        self.assertLessEqual({'binary_sensor.door', 'sensor.power'}, screen_saver.entities(clock, states))
        self.assertFalse({'binary_sensor.door'} & screen_saver.entities({**clock, 'show': False}, states))
        # Checked as the top bar checks its own items, and the clock takes only a few of them.
        self.assertEqual(screen_saver.validate({'items': [{'entity': 'sensor.power'}]})['items'],
                         [{'type': 'entity', 'entity': 'sensor.power', 'content': 'state', 'icon': 'auto', 'show': 'always'}])
        for wrong in ('x', [{'entity': 'camera.front_door'}], [{'entity': 'sensor.power', 'content': 'last_changed'}],
                      [{'entity': 'sensor.power', 'show': 'active'}], [{'type': 'clock'}],
                      [{'entity': 'sensor.power', 'content': 'icon', 'icon': 'none'}],
                      [{'entity': f'sensor.p{n}'} for n in range(screen_saver.ITEMS_MAX + 1)]):
            with self.assertRaises(ValueError):
                screen_saver.validate({'items': wrong})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screensavers.json'
            savers = screen_saver.ScreenSavers(path)
            savers.set('d1', {'items': items})
            self.assertEqual(screen_saver.ScreenSavers(path).get('d1')['items'], screen_saver.valid_items(items))
            savers.get('d1')['items'][0]['content'] = 'icon'
            self.assertEqual(savers.get('d1')['items'][0]['content'], 'state', 'a copy, never the kept choice')

    def test_kept_per_device_beside_the_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screensavers.json'
            savers = screen_saver.ScreenSavers(path)
            self.assertEqual(savers.get('d1'), screen_saver.DEFAULT)
            savers.set('d1', CHOICE)
            self.assertEqual(screen_saver.ScreenSavers(path).get('d1'), CHOICE)
            self.assertEqual(json.loads(path.read_text())['version'], 1)
            savers.get('d1')['order'].reverse()
            self.assertEqual(savers.get('d1')['order'], CHOICE['order'], 'a copy, never the kept choice')
            savers.set('d1', {})
            self.assertNotIn('d1', screen_saver.ScreenSavers(path).choices, 'the default is not written down')
            path.write_text('{"version": 1, "screens": {"d2": {"show": "x"}}}')
            self.assertEqual(screen_saver.ScreenSavers(path).get('d2'), screen_saver.DEFAULT)


HAS_PIL = importlib.util.find_spec('PIL') is not None


@unittest.skipUnless(HAS_PIL, 'Run using .venv-portal/bin/python for picture tests')
class Picture(unittest.TestCase):
    """camera_feed.encode_saver: one picture of the screen's whole box, a little darker everywhere."""

    def picture(self, size, colour=(200, 200, 200)):
        from PIL import Image
        out = io.BytesIO()
        Image.new('RGB', size, colour).save(out, 'JPEG')
        return out.getvalue()

    def open(self, bmp):
        from PIL import Image
        return Image.open(io.BytesIO(bmp)).convert('RGB')

    def test_a_camera_fills_the_glass_darkened(self):
        import camera_feed
        image = self.open(camera_feed.encode_saver(self.picture((1920, 1080)), (480, 480), 'camera'))
        self.assertEqual(image.size, (480, 480))
        # Cut to the glass, not fitted into it: no black bars, and every pixel a little darker, the same everywhere.
        for point in ((2, 2), (240, 240), (477, 477)):
            self.assertTrue(120 <= image.getpixel(point)[0] <= 160, image.getpixel(point))

    def test_a_cover_fills_square_glass_and_stands_beside_its_colour_on_long_glass(self):
        import camera_feed
        cover = self.picture((640, 640), (240, 240, 240))
        square = self.open(camera_feed.encode_saver(cover, (480, 480), 'media', 0x204060))
        self.assertGreater(square.getpixel((470, 240))[0], 140)
        wide = self.open(camera_feed.encode_saver(cover, (1024, 600), 'media', 0x204060))
        self.assertEqual(wide.size, (1024, 600))
        self.assertGreater(wide.getpixel((300, 300))[0], 140, 'the cover at the left, the full height')
        right = wide.getpixel((900, 300))
        self.assertTrue(abs(right[2] - 0x60 * 0.7) < 12 and right[0] < 40, right)
        tall = self.open(camera_feed.encode_saver(cover, (600, 1024), 'media', 0x204060))
        self.assertGreater(tall.getpixel((300, 300))[0], 140, 'the cover at the top, the full width')
        self.assertLess(tall.getpixel((300, 900))[0], 40)

    def test_the_firmware_lays_its_words_by_the_same_rule(self):
        import camera_feed
        header = (ROOT / 'components/smart_display/saver_view.h').read_text()
        self.assertEqual(camera_feed.SAVER_SQUARE, (5, 4))
        self.assertIn('width * 4 <= height * 5 && height * 4 <= width * 5', header)
        for box, shape in (((480, 480), 'fill'), ((500, 400), 'fill'), ((501, 400), 'side'), ((400, 501), 'top'), ((1024, 600), 'side')):
            self.assertEqual(camera_feed.saver_shape(box), shape, box)


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class TheApp(unittest.IsolatedAsyncioTestCase):
    def ha(self, firmware='0.29.0'):
        class HA:
            online = True

            def __init__(self):
                self.registry = [{'entity_id': 'text.d1_tiles', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                                 {'entity_id': 'sensor.d1_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                                 {'entity_id': 'sensor.d1_fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'},
                                 {'entity_id': 'select.d1_type', 'platform': 'esphome', 'original_name': 'Guition screen type', 'device_id': 'd1'}]
                self.devices, self.areas = [{'id': 'd1', 'name': 'Hall'}], []
                self.states = {'text.d1_tiles': {'state': 'Synced'}, 'sensor.d1_node': {'state': 'hall'}, 'sensor.d1_fw': {'state': firmware},
                               PLAYER: PLAYING, CAMERA: DOOR}
                self.changed, self.dirty, self.log = asyncio.Event(), set(), []

            async def send(self, inbox, message, action=None, respond=False):
                self.log.append(('send', inbox, dict(message)))
        return HA()

    async def test_the_screen_hears_once_per_change_and_per_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = self.ha()
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Hall', 'tiles': [{'entity': 'light.hall', 'name': 'Hall'}]}))
            sent = []

            class Sender:
                protocol, session, confirmed, features = 2, 'S1', 'R1', {screen_saver.FEATURE}

                async def auxiliary(self, message, *, session, revision):
                    sent.append((dict(message), session, revision))
                    return True
            m.page_senders['text.d1_tiles'] = sender = Sender()
            screen = m.screen('text.d1_tiles')
            m.savers.set('d1', CHOICE)
            # The player and the camera are followed, and the screen may load them though no tile shows them.
            self.assertTrue({PLAYER, CAMERA} <= m.watched_entities())
            self.assertTrue(m.camera_allowed('text.d1_tiles', CAMERA) and m.camera_allowed('text.d1_tiles', PLAYER))
            self.assertFalse(m.camera_allowed('text.d1_tiles', 'camera.garden'))
            # So are the players the music step tries next (app 0.4.54).
            m.savers.set('d1', {**CHOICE, 'more': ['media_player.apple_tv']})
            self.assertIn('media_player.apple_tv', m.watched_entities())
            self.assertTrue(m.camera_allowed('text.d1_tiles', 'media_player.apple_tv'))
            await m.sync_saver('text.d1_tiles', screen)
            await m.sync_saver('text.d1_tiles', screen)
            self.assertEqual([(s[0]['k'], s[1], s[2]) for s in sent], [('media', 'S1', 'R1')])
            ha.states[PLAYER] = {**PLAYING, 'state': 'paused'}
            await m.sync_saver('text.d1_tiles', screen)
            self.assertEqual(sent[-1][0], {'op': 'saver', 'k': 'camera', 'e': CAMERA, 'n': 'Front door'})
            sender.session = 'S2'
            await m.sync_saver('text.d1_tiles', screen)
            self.assertEqual((len(sent), sent[-1][1]), (3, 'S2'), 'a new session hears it again')
            # A screen whose screensaver has keys (firmware 0.33.0+) hears the player's state and what it can do.
            m.savers.set('d1', CHOICE)
            ha.states[PLAYER] = PLAYING
            sender.features = {screen_saver.FEATURE, screen_saver.KEYS_FEATURE}
            await m.sync_saver('text.d1_tiles', screen)
            self.assertEqual((sent[-1][0]['k'], sent[-1][0]['s'], sent[-1][0]['f']), ('media', 'playing', 0))
            # The clock's entities (firmware 0.50.0+) go to a screen that takes the row, as the top bar sends them, and
            # follow their entity.
            ha.states['light.hall'] = {'state': 'on', 'attributes': {'friendly_name': 'Hall'}}
            m.savers.set('d1', {**CHOICE, 'off': ['media', 'camera'], 'weather': '',
                                'items': [{'entity': 'light.hall', 'icon': 'none'}]})
            self.assertIn('light.hall', m.watched_entities())
            await m.sync_saver('text.d1_tiles', screen)
            self.assertNotIn('wi', sent[-1][0], 'a screen without the row hears the clock alone')
            sender.features = {screen_saver.FEATURE, screen_saver.ITEMS_FEATURE}
            sender.session = 'S3'
            await m.sync_saver('text.d1_tiles', screen)
            self.assertEqual(sent[-1][0]['wi'], [{'k': 'text', 't': 'On'}])
            count = len(sent)
            # A screen whose hello does not list it hears nothing.
            sender.features = set()
            m.savers.set('d1', {})
            await m.sync_saver('text.d1_tiles', screen)
            self.assertEqual(len(sent), count)

    async def test_the_editor_sees_the_choice_and_what_the_screen_can(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(with_screen_grid(self.ha('0.28.0')), Path(tmp) / 'screens.json')
            screen = m.screen('text.d1_tiles')
            self.assertLess(m.firmware_version('text.d1_tiles', screen), SCREENSAVER_MIN_FIRMWARE)
            m.savers.set('d1', CHOICE)
            self.assertEqual(m.saver_entities('text.d1_tiles'), {PLAYER, CAMERA})
            self.assertEqual(m.saver_message(screen)['k'], 'media')


if __name__ == '__main__':
    unittest.main()
