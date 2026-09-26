"""Camera images on a Guition (app 0.2.66, firmware 0.2.57): the app fetches, sizes and serves the image on its own
port; the screen asks with esphome.screen_camera and loads the link with ESPHome's online_image."""
from firmware_sources import runtime_source
from manager_fixtures import with_screen_grid, seed_layout
import asyncio
import contextlib
import importlib.util
import io
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import camera_feed  # noqa: E402
from core import (ALERT_FIELDS, BROADCAST_SHOW, CAMERA_MIN_FIRMWARE, alert_camera, alert_reference, entity_id,  # noqa: E402
                  header_entity, min_firmware, validate_layout, extras)

HAS_PIL = importlib.util.find_spec('PIL') is not None
HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import HomeAssistant, Manager

PROFILE = profiles.text('checkout/guition.yaml')
TILES = runtime_source()


def picture(fmt, size, mode='RGB'):
    from PIL import Image
    out = io.BytesIO()
    Image.new(mode, size, (200, 30, 90) if mode == 'RGB' else None).save(out, fmt)
    return out.getvalue()


class Rules(unittest.TestCase):
    def test_the_alert_picture_is_sized_for_the_frame_of_its_proportions(self):
        guition = {'board': 'guition', 'firmware_known': '0.2.103'}
        self.assertEqual(camera_feed.alert_box(guition, (1920, 1080)), (391, 220))
        square = camera_feed.alert_box(guition, (720, 720))
        self.assertEqual(square[0], square[1])
        self.assertGreater(square[1], 220)
        # Older firmware has one frame for every picture; it gets the picture for that frame, as before.
        self.assertEqual(camera_feed.alert_box({'board': 'guition', 'firmware_known': '0.2.102'}, (720, 720)), (392, 220))
        # A screen whose Override YAML changed its density reports it ("Screen layout"), and gets the frame of its card
        # at that density, with the fonts it was built with.
        import alert_layout
        denser = {**guition, 'shape': {'width': 480, 'height': 480, 'columns': 2, 'rows': 3, 'dpi': 200, 'look': 'standard'}}
        card = alert_layout.layout(480, 480, *alert_layout.lines(200, 'standard'), True, 200, 'standard', 1080, 1440)
        self.assertEqual(camera_feed.alert_box(denser, (1080, 1440)), (card.image_w, card.image_h))
        self.assertNotEqual(camera_feed.alert_box(denser, (1080, 1440)), camera_feed.alert_box(guition, (1080, 1440)))
        # No picture known, or a board without pictures.
        self.assertEqual(camera_feed.alert_box(guition, None), (392, 220))
        self.assertIsNone(camera_feed.alert_box({'board': 'cyd', 'firmware_known': '0.2.103'}, (720, 720)))
        # Never larger than the screen's own full-screen picture, which is what its board's memory is measured for.
        for board, shape in camera_feed.SHAPES.items():
            if board != shape.get('board') or 'camera' not in shape:
                continue
            for way in ('landscape', 'portrait'):
                screen = {'board': board, 'orientation': way, 'firmware_known': '0.2.103'}
                full = camera_feed.box(screen, 'full')
                for picture in ((1920, 1080), (720, 720), (1080, 1440), (2560, 1080), (1080, 1920)):
                    w, h = camera_feed.alert_box(screen, picture)
                    self.assertLessEqual(w * h, full[0] * full[1], (board, way, picture))
                    self.assertLessEqual(w, full[0], (board, way, picture))
                    self.assertLessEqual(h, full[1], (board, way, picture))

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_a_turned_snapshot_is_measured_the_way_it_is_shown(self):
        from PIL import Image
        out = io.BytesIO()
        image = Image.new('RGB', (1440, 1080))
        exif = image.getexif()
        exif[0x0112] = 6  # turned a quarter: shown 1080 wide, 1440 high
        image.save(out, 'JPEG', exif=exif)
        self.assertEqual(camera_feed.picture_size(out.getvalue()), (1080, 1440))
        self.assertEqual(camera_feed.picture_size(picture('PNG', (640, 360))), (640, 360))

    def test_camera_and_image_tiles_need_the_camera_firmware(self):
        self.assertTrue(entity_id('camera.front_door') and entity_id('image.doorbell'))
        self.assertEqual(camera_feed.MIN_FIRMWARE, CAMERA_MIN_FIRMWARE)
        layout = validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.front_door', 'name': ''}]})
        self.assertEqual(min_firmware(layout), (0, 2, 57))
        # Automatic and "open control" both open the image full screen; view only keeps the tile still.
        validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.front_door', 'name': '', 'options': {'tap': 'detail'}}]})
        validate_layout({'title': 'Hall', 'tiles': [{'entity': 'image.doorbell', 'name': '', 'options': {'tap': 'none'}}]})
        # A top bar item shows a state; a camera has nothing worth reading there.
        self.assertFalse(header_entity('camera.front_door'))

    def test_an_image_tile_knows_when_its_picture_changed(self):
        states = {'image.doorbell': {'state': '2026-09-17T12:00:00+00:00', 'attributes': {}}}
        self.assertEqual(extras({'entity': 'image.doorbell'}, states), {'last': 1789646400})

    def test_which_screens_draw_images(self):
        self.assertTrue(camera_feed.can_show({'board': 'guition', 'firmware': '0.2.57'}))
        self.assertTrue(camera_feed.can_show({'board': 'guition', 'firmware': '0.3.0'}))
        for screen in ({'board': 'guition', 'firmware': '0.2.56'}, {'board': 'unknown', 'firmware': '0.2.57'},
                       {'board': 'guition', 'firmware': 'unknown'}, None, {}):
            self.assertFalse(camera_feed.can_show(screen), screen)
        self.assertTrue(camera_feed.supported('camera.max') and camera_feed.supported('image.max_motion'))
        for value in ('light.kitchen', 'camera', 'Camera.Max', None, 42, 'camera.' + 'x' * 120):
            self.assertFalse(camera_feed.supported(value), value)

    def test_the_alert_camera_field(self):
        self.assertEqual(alert_camera({'camera': 'camera.front_door'}), ('camera.front_door', True))
        self.assertEqual(alert_camera({'camera': ' image.doorbell '}), ('image.doorbell', True))
        self.assertEqual(alert_camera({}), ('', True))
        self.assertEqual(alert_camera({'camera': ''}), ('', True))
        for value in ('light.hall', True, ['camera.max'], 'camera'):
            self.assertEqual(alert_camera({'camera': value}), ('', False), value)
        # Not an argument of the show_alert action: older firmware would refuse the whole call.
        self.assertNotIn('camera', [name for name, *_ in ALERT_FIELDS])
        self.assertEqual(alert_reference()['camera']['name'], 'camera')

    def test_the_boxes_are_the_profile_sizes(self):
        # The Guition's: its canvas, and the frame its alert card makes for a picture (screen_alert::layout), which
        # is the one the standard look was drawn with.
        subs = profiles.substitutions('checkout/guition.yaml')
        self.assertEqual(camera_feed.BOXES['guition'], {'full': (int(subs['CAMERA_FULL_W']), int(subs['CAMERA_FULL_H'])),
                                                        'thumb': (392, 220)})

    def test_the_firmware_and_the_app_speak_the_same_words(self):
        self.assertIn('request.service = esphome::StringRef("esphome.screen_camera");', TILES)
        self.assertIn("event_type='esphome.screen_camera'", (ROOT / 'screen_manager/app/server.py').read_text())
        self.assertIn('if (op == "camera") {', TILES)
        self.assertIn('"camera", "image",', (ROOT / 'components/smart_display/runtime_model.h').read_text())
        # The profile loads both images and binds them; the CYD has none, so it never opens a camera.
        for needle in ('online_image:\n  - id: camera_image', '  - id: alert_image', 'runtime_tiles::camera_loaded(false, cached);',
                       'runtime_tiles::camera_loaded(true, cached);', 'runtime_tiles::camera_tick();', 'runtime_tiles::alert_prepare();',
                       'runtime_tiles::alert_clear();', 'runtime_tiles::camera_close();', 'id: alert_image_frame'):
            self.assertIn(needle, PROFILE, needle)
        # A link only replaces the URL when it is new: set_url() forgets the ETag that makes an unchanged picture a 304.
        # Three images: the camera full screen (and the cover), the alert's picture, the live tiles' strip (app 0.2.91).
        self.assertEqual(PROFILE.count('if (url != current) {'), 3)
        for needle in ('  - id: tile_image', 'runtime_tiles::live_loaded(cached);', 'runtime_tiles::live_failed();', 'runtime_tiles::camera_live.load'):
            self.assertIn(needle, PROFILE, needle)
        # A busy camera port leaves the rest of the app running.
        self.assertIn("except OSError as error:\n            # Everything else still works; only camera images stay away.", (ROOT / 'screen_manager/app/server.py').read_text())
        cyd = profiles.text('checkout/cyd.yaml')
        self.assertNotIn('online_image', cyd)
        self.assertNotIn('camera_full.load', cyd)
        # The add-on's port is published, and the Docker route passes it on with the host network.
        config = (ROOT / 'screen_manager/config.yaml').read_text()
        self.assertIn(f'{camera_feed.PORT}/tcp: {camera_feed.PORT}', config)

    def test_the_first_picture_waits_for_no_tick(self):
        # Firmware 0.2.73+: the camera asks when it opens and loads the link when it comes, not on the next 250 ms tick;
        # the spinner turns until the first picture or a note is there.
        opened = TILES.split('inline void camera_open(const std::string &entity, const std::string &name) {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('camera_spinner = spinner_create(camera_root,', opened)
        self.assertIn('if (awake() && fresh() && camera.should_ask(now)) {', opened)
        answer = TILES.split('inline void camera_answer(const std::string &view, const std::string &entity, const std::string &url) {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('if (awake() && camera.should_load(now)) camera_load(now);', answer)
        # Never under a finger, from the answer or from the tick.
        load = TILES.split('inline void camera_load(uint32_t now) {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('lv_indev_get_state(input) == LV_INDEV_STATE_PRESSED) return;', load)
        note = TILES.split('inline void camera_note_text(const char *text) {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('lv_obj_delete(camera_spinner);', note)
        self.assertNotIn('Loading image', TILES)


@unittest.skipUnless(HAS_PIL, 'Pillow comes with ESPHome in the add-on image')
class Encoding(unittest.TestCase):
    def test_every_snapshot_becomes_a_bmp_that_fits(self):
        from PIL import Image
        cases = [(picture('JPEG', (1920, 1080)), (480, 480), (480, 270)),
                 (picture('JPEG', (1920, 1080)), (392, 220), (391, 220)),
                 (picture('PNG', (400, 100), 'RGBA'), (480, 480), (480, 120)),
                 (picture('GIF', (550, 512), 'P'), (392, 220), (236, 220)),
                 (picture('JPEG', (1080, 1440)), (480, 480), (360, 480)),
                 (picture('PNG', (100, 50)), (480, 480), (480, 240))]
        for raw, box, size in cases:
            bmp = camera_feed.encode(raw, box)
            with Image.open(io.BytesIO(bmp)) as image:
                self.assertEqual((image.format, image.size, image.mode), ('BMP', size, 'RGB'))
            # What ESPHome's BMP decoder reads: 24 bits per pixel, no compression, rows padded to four bytes.
            self.assertEqual((bmp[:2], int.from_bytes(bmp[28:30], 'little'), int.from_bytes(bmp[30:34], 'little')), (b'BM', 24, 0))
            self.assertEqual(len(bmp), int.from_bytes(bmp[10:14], 'little') + size[1] * ((size[0] * 3 + 3) // 4 * 4))
        with self.assertRaises(Exception):
            camera_feed.encode(b'not an image', (480, 480))

    def test_fit_keeps_proportions(self):
        self.assertEqual(camera_feed.fit((1920, 1080), (480, 480)), (480, 270))
        self.assertEqual(camera_feed.fit((1, 5000), (224, 126)), (1, 126))
        self.assertEqual(camera_feed.fit((5000, 1), (224, 126)), (224, 1))


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


@unittest.skipUnless(HAS_PIL, 'Pillow comes with ESPHome in the add-on image')
class Feed(unittest.IsolatedAsyncioTestCase):
    def feed(self, answers):
        self.fetched, self.gate = [], None
        clock = Clock()

        async def fetch(entity):
            self.fetched.append(entity)
            answer = answers[min(len(self.fetched), len(answers)) - 1]
            if self.gate is not None:
                # A camera that takes its time: the fetch stays on its way until the test opens the gate.
                await self.gate.wait()
            if isinstance(answer, Exception):
                raise answer
            return answer
        return camera_feed.CameraFeed(fetch, clock=clock), clock

    async def settle(self):
        """Let the fetch a load started run before counting fetches: whether it already ran when serve() returns
        depends on whether serve() had to wait for anything itself."""
        for _ in range(5):
            await asyncio.sleep(0)

    async def test_links_serve_the_last_frame_and_answer_unchanged_images_with_304(self):
        feed, clock = self.feed([picture('JPEG', (1920, 1080))])
        token = feed.link('camera.max', (480, 480))
        status, bmp, etag = await feed.serve(token)
        self.assertEqual((status, bmp[:2]), (200, b'BM'))
        self.assertRegex(etag, r'^"[0-9a-f]{16}-480x480"$')
        await self.settle()
        # The camera answered the same picture again: the screen keeps what it has.
        self.assertEqual(await feed.serve(token, etag), (304, None, etag))
        self.assertEqual((await feed.serve('unknown'))[0], 404)
        # A link nobody used for LINK_SECONDS is gone; the screen asks for a new one.
        clock.now += camera_feed.LINK_SECONDS + 1
        self.assertEqual((await feed.serve(token))[0], 404)

    async def test_each_load_fetches_the_next_picture_and_nothing_is_fetched_between_loads(self):
        first, second, third = picture('JPEG', (640, 360)), picture('PNG', (640, 360)), picture('BMP', (640, 360))
        feed, clock = self.feed([first, second, third])
        token = feed.link('camera.max', (480, 480))
        _, one, tag_one = await feed.serve(token)
        await self.settle()
        self.assertEqual(self.fetched, ['camera.max'] * 2, 'the first picture, and the next one started at once')
        await asyncio.sleep(0.05)
        self.assertEqual(len(self.fetched), 2, 'nobody loads, nothing is fetched')
        clock.now += 4
        _, two, tag_two = await feed.serve(token, tag_one)
        await self.settle()
        self.assertNotEqual(tag_two, tag_one, 'the picture fetched after the last load')
        self.assertEqual(len(self.fetched), 3)
        # Two screens loading while the next picture is on its way share that one fetch.
        self.gate = asyncio.Event()
        await feed.serve(token, tag_two)
        await feed.serve(token, tag_two)
        await self.settle()
        self.assertEqual(len(self.fetched), 4)
        self.gate.set()
        await self.settle()

    async def test_a_camera_that_fails_is_asked_again_after_a_pause(self):
        feed, clock = self.feed([ConnectionError('500'), ConnectionError('500'), picture('JPEG', (640, 360))])
        token = feed.link('camera.woonkamer_live', (480, 480))
        with self.assertLogs(camera_feed.LOG, 'INFO'):
            self.assertEqual((await feed.serve(token))[0], 503)
            self.assertEqual((await feed.serve(token))[0], 503)
            await self.settle()
            self.assertEqual(len(self.fetched), 1, 'no second try within the pause')
            clock.now += 5
            self.assertEqual((await feed.serve(token))[0], 503)
            await self.settle()
            self.assertEqual(len(self.fetched), 2)
            clock.now += 10
            self.assertEqual((await feed.serve(token))[0], 200)
            await self.settle()
        self.assertEqual(len(self.fetched), 4, 'the good picture, then the next one')

    async def test_an_alert_gets_a_snapshot_of_its_own_moment(self):
        first, second = picture('JPEG', (640, 360)), picture('PNG', (640, 360))
        feed, clock = self.feed([first, second])
        tag_first, _ = await feed.frame('camera.front_door', (392, 220), fresh=False)
        await self.settle()
        self.assertEqual(len(self.fetched), 1)
        clock.now += 20
        # The bell rings 20 s later: the kept snapshot is not the moment, a new fetch is.
        tag_alert, _ = await feed.frame('camera.front_door', (392, 220), fresh=False, now=True)
        await self.settle()
        self.assertEqual(len(self.fetched), 2)
        self.assertNotEqual(tag_alert, tag_first)

    async def test_an_alert_whose_camera_fails_gets_no_old_picture(self):
        feed, clock = self.feed([picture('JPEG', (640, 360)), ConnectionError('offline')])
        await feed.frame('camera.front_door', (392, 220), fresh=False)
        clock.now += 20
        with self.assertLogs(camera_feed.LOG, 'INFO'):
            self.assertIsNone(await feed.frame('camera.front_door', (392, 220), fresh=False, now=True))

    async def test_a_camera_nobody_loads_is_forgotten(self):
        feed, clock = self.feed([picture('JPEG', (64, 36))])
        await feed.frame('camera.max', (480, 480), fresh=False)
        self.assertIn('camera.max', feed.watches)
        clock.now += camera_feed.WATCH_SECONDS + 1
        feed.watch('camera.garden')
        self.assertNotIn('camera.max', feed.watches)

    async def test_a_still_is_one_fixed_image(self):
        feed, _ = self.feed([RuntimeError('never asked')])
        bmp = camera_feed.encode(picture('JPEG', (640, 360)), (392, 220))
        token = feed.link('camera.max', (392, 220), bmp)
        status, body, etag = await feed.serve(token)
        self.assertEqual((status, body), (200, bmp))
        self.assertEqual((await feed.serve(token, etag))[0], 304)
        self.assertEqual(self.fetched, [])

    async def test_the_number_of_links_is_bounded(self):
        feed, clock = self.feed([picture('JPEG', (64, 36))])
        tokens = []
        for _ in range(camera_feed.MAX_LINKS + 10):
            clock.now += 0.01
            tokens.append(feed.link('camera.max', (480, 480)))
        self.assertLessEqual(len(feed.links), camera_feed.MAX_LINKS)
        self.assertNotIn(tokens[0], feed.links)
        self.assertIn(tokens[-1], feed.links)
        self.assertTrue(all(re.fullmatch(r'[A-Za-z0-9_-]{24}', token) for token in tokens))

    @unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
    async def test_the_http_port(self):
        from aiohttp.test_utils import TestClient, TestServer
        feed, _ = self.feed([picture('JPEG', (1920, 1080))])
        token = feed.link('camera.max', (480, 480))
        async with TestClient(TestServer(camera_feed.web_app(feed))) as client:
            response = await client.get(f'/camera/{token}.bmp')
            body = await response.read()
            self.assertEqual((response.status, response.content_type, int(response.headers['Content-Length'])), (200, 'image/bmp', len(body)))
            etag = response.headers['ETag']
            self.assertEqual((await client.get(f'/camera/{token}.bmp', headers={'If-None-Match': etag})).status, 304)
            self.assertEqual((await client.get('/camera/abcdefghijklmnopqrstuvwx.bmp')).status, 404)
            self.assertEqual((await client.get('/api/inventory')).status, 404)
            self.assertEqual((await client.post(f'/camera/{token}.bmp')).status, 405)


def fake_ha(image=None):
    """Home Assistant with two current screens (a Guition and a CYD) and an old Guition."""
    class HA:
        online = True

        def __init__(self):
            self.registry, self.devices, self.states = [], [], {}
            for device, node, firmware, guition in (('d1', 'hall', '0.2.57', True), ('d2', 'desk', '0.2.57', False),
                                                    ('d3', 'attic', '0.2.56', True)):
                self.registry += [{'entity_id': f'text.{device}_tiles', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': device},
                                  {'entity_id': f'sensor.{device}_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': device},
                                  {'entity_id': f'sensor.{device}_fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': device}]
                if guition:
                    self.registry.append({'entity_id': f'select.{device}_type', 'platform': 'esphome', 'original_name': 'Guition screen type', 'device_id': device})
                self.devices.append({'id': device, 'name': node.title()})
                self.states.update({f'text.{device}_tiles': {'state': 'Synced'}, f'sensor.{device}_node': {'state': node},
                                    f'sensor.{device}_fw': {'state': firmware}})
            self.areas = []
            self.changed = asyncio.Event()
            self.log = []
            self.responses = set()

        async def call(self, action, data):
            self.log.append(('call', action, data))

        async def send(self, inbox, message, action=None, respond=False):
            self.log.append(('send', inbox, dict(message)))

        async def request(self, kind, **data):
            if kind == 'network':
                return {'adapters': [{'name': 'end0', 'default': True, 'ipv4': [{'address': '192.168.1.57'}]}]}
            raise ConnectionError(kind)

        async def camera_image(self, entity):
            self.log.append(('fetch', entity))
            if image is None:
                raise ConnectionError('500')
            return image

        async def media_image(self, entity):
            self.log.append(('fetch', entity))
            return picture('PNG', (300, 300))

        def media_picture(self, entity):
            return '/api/media_player_proxy/%s?token=a&cache=1' % entity if entity == 'media_player.sonos' else ''
    return HA()


@unittest.skipUnless(HAS_AIOHTTP and HAS_PIL, 'Run using .venv-portal/bin/python for server tests')
class App(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        camera_feed.base_url.__defaults__[0].clear()

    async def test_camera_alert_announcement_and_image_use_the_page_session(self):
        from page_delivery import Sender
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (640, 360)))
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            async def wire(message):
                ha.log.append(('send', 'text.d1_tiles', message))
                return {**{key: message[key] for key in ('session', 'seq', 'rev')},
                        'protocol': 2, 'status': 'Synced', 'applied': True}
            sender = Sender(wire)
            sender.protocol, sender.session, sender.confirmed = 2, 'a' * 16, 'b' * 16
            m.page_senders['text.d1_tiles'] = sender
            await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'camera': 'camera.front_door'})
            sends = [entry for entry in ha.log if entry[0] == 'send']
            self.assertEqual(len(sends), 2)
            self.assertEqual(sends[0][2]['u'], '')
            self.assertTrue(sends[1][2]['u'])
            for _, _, message in sends:
                self.assertEqual((message['v'], message['session'], message['rev']), (2, 'a' * 16, 'b' * 16))
            self.assertLess(ha.log.index(sends[0]), next(i for i, entry in enumerate(ha.log) if entry[0] == 'call'))

            ha.log.clear()
            await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'camera': 'camera.front_door', 'screen': 'hall'})
            self.assertEqual([entry[1] for entry in ha.log if entry[0] in ('send', 'call')],
                             ['text.d1_tiles', 'esphome.hall_show_alert', 'text.d1_tiles'])
            for entry in ha.log:
                if entry[0] == 'send':
                    self.assertEqual((entry[2]['v'], entry[2]['session'], entry[2]['rev']),
                                     (2, 'a' * 16, 'b' * 16))

    async def test_an_alert_with_a_camera(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (1920, 1080)))
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            await m.broadcast(BROADCAST_SHOW, {'title': 'Someone is at the door', 'camera': 'camera.front_door'})
            sends = [entry for entry in ha.log if entry[0] == 'send']
            calls = [entry for entry in ha.log if entry[0] == 'call']
            # Only the current Guition hears of the image: first announced, then the alert, then the link.
            self.assertEqual([target for _, target, _ in sends], ['text.d1_tiles', 'text.d1_tiles'])
            self.assertEqual(sends[0][2], {'v': 1, 'op': 'camera', 't': 'alert', 'e': 'camera.front_door', 'u': ''})
            self.assertLess(ha.log.index(sends[0]), ha.log.index(calls[0]))
            self.assertEqual(len(calls), 3, 'every current screen gets the alert itself')
            self.assertNotIn('camera', calls[0][2])
            url = sends[1][2]['u']
            self.assertRegex(url, r'^http://192\.168\.1\.57:8098/camera/[A-Za-z0-9_-]{24}\.bmp$')
            token = url.rsplit('/', 1)[1][:-4]
            self.assertEqual(m.camera.links[token].box, (392, 220))
            self.assertEqual((await m.camera.serve(token))[0], 200)
            # The alert's camera may be opened full screen without a tile.
            self.assertTrue(m.camera_allowed('text.d1_tiles', 'camera.front_door'))

    async def test_an_alert_picture_has_the_size_of_the_frame_the_screen_makes_for_it(self):
        # Firmware 0.2.103 lays its alert out for the picture's own proportions (screen_alert::layout): a standing
        # doorbell camera gets a picture at exactly the frame the Guition's card makes for 3:4, fetched once.
        import alert_layout
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (1080, 1440)))
            ha.states['sensor.d1_fw']['state'] = '0.2.103'
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            await m.broadcast(BROADCAST_SHOW, {'title': 'Someone is at the door', 'camera': 'camera.front_door'})
            sends = [entry for entry in ha.log if entry[0] == 'send']
            token = sends[1][2]['u'].rsplit('/', 1)[1][:-4]
            board = camera_feed.SHAPES['guition']
            card = alert_layout.layout(480, 480, board['alert']['title_line'], board['alert']['line'], True, board['dpi'],
                                       board['look'], 1080, 1440)
            self.assertEqual(m.camera.links[token].box, (card.image_w, card.image_h))
            status, body, _ = await m.camera.serve(token)
            from PIL import Image
            with Image.open(io.BytesIO(body)) as served:
                self.assertEqual(served.size, (card.image_w, card.image_h))
            self.assertEqual(len([entry for entry in ha.log if entry[0] == 'fetch']), 1, 'one snapshot for the alert')

    async def test_screens_of_different_sizes_get_one_snapshot_each_at_their_own_size(self):
        # A broadcast to a wall of screens: every size the alert needs is made once from the same snapshot, and each
        # screen gets its own link to its own size.
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (1080, 1440)))
            ha.states['sensor.d1_fw']['state'] = '0.2.103'
            ha.states['sensor.d3_fw']['state'] = '0.2.102'
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            await m.broadcast(BROADCAST_SHOW, {'title': 'Someone is at the door', 'camera': 'camera.front_door'})
            links = {inbox: message['u'] for _, inbox, message in (e for e in ha.log if e[0] == 'send') if message['u']}
            self.assertEqual(set(links), {'text.d1_tiles', 'text.d3_tiles'})
            served = {}
            for inbox, url in links.items():
                status, body, etag = await m.camera.serve(url.rsplit('/', 1)[1][:-4])
                self.assertEqual(status, 200)
                from PIL import Image
                with Image.open(io.BytesIO(body)) as image:
                    served[inbox] = image.size
            self.assertEqual(served['text.d3_tiles'], (165, 220), 'older firmware gets it fitted in its 16:9 frame')
            self.assertLess(served['text.d1_tiles'][0], served['text.d1_tiles'][1], 'the new firmware gets a standing picture')
            frames = m.camera.watch('camera.front_door').frames
            self.assertEqual(len(frames), 2)
            self.assertEqual(len({digest for digest, _ in frames.values()}), 1, 'both made from the same snapshot')
            self.assertEqual(len([entry for entry in ha.log if entry[0] == 'fetch']), 1, 'one snapshot for the whole wall')

    async def test_an_alert_with_a_camera_on_one_screen(self):
        # The event's `screen` (app 0.2.133): only the screen it names hears of the picture, gets the alert and its link,
        # though another screen could draw the picture as well.
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (1920, 1080)))
            ha.states['sensor.d3_fw']['state'] = '0.2.103'
            m = Manager(ha, Path(tmp) / 'screens.json')
            await m.broadcast(BROADCAST_SHOW, {'title': 'Someone is at the door', 'camera': 'camera.front_door', 'screen': 'attic'})
            self.assertEqual([entry[1] for entry in ha.log if entry[0] in ('send', 'call')],
                             ['text.d3_tiles', 'esphome.attic_show_alert', 'text.d3_tiles'])
            self.assertTrue([entry for entry in ha.log if entry[0] == 'send'][1][2]['u'])
            self.assertTrue(m.camera_allowed('text.d3_tiles', 'camera.front_door'))

    async def test_an_alert_whose_camera_has_no_image_still_goes_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(None)
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            with self.assertLogs('screen_manager', 'INFO') as logs:
                await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'camera': 'camera.front_door'})
            sends = [entry for entry in ha.log if entry[0] == 'send']
            self.assertEqual([message['u'] for _, _, message in sends], ['', ''])
            self.assertEqual(len([entry for entry in ha.log if entry[0] == 'call']), 3)
            self.assertTrue(any('(no image)' in line for line in logs.output), logs.output)

    async def test_an_unusable_camera_is_named_and_left_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (64, 36)))
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            with self.assertLogs('screen_manager', 'INFO') as logs:
                await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'camera': 'light.hall'})
            self.assertEqual([entry[0] for entry in ha.log], ['call'] * 3)
            self.assertTrue(any('unusable camera left empty' in line for line in logs.output), logs.output)

    async def test_a_screen_asks_for_a_camera_it_may_show(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (1920, 1080)))
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.max', 'name': ''}]}))
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'entity': 'camera.max'})
            (_, inbox, message), = [entry for entry in ha.log if entry[0] == 'send']
            self.assertEqual((inbox, message['op'], message['t'], message['e']), ('text.d1_tiles', 'camera', 'full', 'camera.max'))
            token = message['u'].rsplit('/', 1)[1][:-4]
            self.assertEqual(m.camera.links[token].box, (480, 480))
            ha.log.clear()
            # Not on its layout, a CYD, an old Guition, a light: no link at all.
            for request in ({'inbox': 'text.d1_tiles', 'entity': 'camera.garden'}, {'inbox': 'text.d2_tiles', 'entity': 'camera.max'},
                            {'inbox': 'text.d3_tiles', 'entity': 'camera.max'}, {'inbox': 'text.d1_tiles', 'entity': 'light.hall'},
                            {'inbox': 'text.unknown', 'entity': 'camera.max'}, 'nonsense'):
                await m.answer_camera(request)
            self.assertEqual([entry for entry in ha.log if entry[0] == 'send'], [])

    async def test_camera_tiles_only_on_a_board_that_draws_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            m.inventory = lambda: (m.screens(), [{'id': 'camera.max'}])
            m.write_layouts = lambda layouts: None
            m.notify = lambda: None
            # A board whose YAML says nothing about camera sizes (the CYD) has no room for them, whatever
            # its firmware: the message says so about the screen, not about a Guition (app 0.2.94).
            with self.assertRaisesRegex(ValueError, 'cannot show camera'):
                m.save('text.d2_tiles', {'title': 'Desk', 'tiles': [{'entity': 'camera.max', 'name': ''}]})
            # A CYD on old firmware hears the same, not "update first": an update doesn't make room for images.
            ha.states['sensor.d2_fw']['state'] = '0.2.54'
            m._screens_key = None
            with self.assertRaisesRegex(ValueError, 'cannot show camera'):
                m.save('text.d2_tiles', {'title': 'Desk', 'tiles': [{'entity': 'camera.max', 'name': ''}]})
            with self.assertRaisesRegex(ValueError, '0.2.57'):
                m.save('text.d3_tiles', {'title': 'Attic', 'tiles': [{'entity': 'camera.max', 'name': ''}]})
            m.save('text.d1_tiles', {'title': 'Hall', 'tiles': [{'entity': 'camera.max', 'name': ''}]})
            self.assertEqual(m.layouts['text.d1_tiles']['tiles'][0]['entity'], 'camera.max')

    async def test_home_assistant_queues_camera_requests(self):
        from aiohttp import WSMsgType

        class Message:
            type = WSMsgType.TEXT
            def __init__(self, data): self.data = data
            def json(self): return self.data

        class Socket:
            def __aiter__(self): return self._iterate()
            async def _iterate(self):
                yield Message({'type': 'event', 'event': {'event_type': 'esphome.screen_camera', 'data': {'inbox': 'text.d1_tiles', 'entity': 'camera.max'}}})
        ha = HomeAssistant(None, 'http://ha/api', 'token')
        ha.ws = Socket()
        with self.assertRaises(ConnectionError):
            await ha.read()
        self.assertEqual(ha.camera_requests.get_nowait(), {'inbox': 'text.d1_tiles', 'entity': 'camera.max'})


class PictureCards(unittest.TestCase):
    """A live camera that fills a 1x2 or 2x2 tile (app 0.3.8, firmware 0.3.3): fill or contain, name or nothing."""

    def test_fit_and_overlay_belong_to_the_live_picture_and_keep_no_defaults(self):
        tile = lambda options: validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.front_door', 'name': '', 'options': options}]})['tiles'][0]['options']
        self.assertEqual(tile({'display': 'live', 'size': 'tall', 'fit': 'contain', 'overlay': 'none'}),
                         {'display': 'live', 'size': 'tall', 'fit': 'contain', 'overlay': 'none'})
        self.assertEqual(tile({'display': 'live', 'size': 'tall', 'fit': 'fill', 'overlay': 'name'}), {'display': 'live', 'size': 'tall'})
        self.assertEqual(tile({'display': 'standard', 'fit': 'contain', 'overlay': 'none'}), {'display': 'standard'})
        for options in ({'display': 'live', 'fit': 'zoom'}, {'display': 'live', 'overlay': True}):
            with self.assertRaises(ValueError, msg=options):
                tile(options)
        from core import tile_options
        self.assertEqual(tile_options({'display': 'live', 'fit': 'contain', 'overlay': 'none'}), {'display': 'live', 'fit': 'contain', 'overlay': 'none'})
        # The page document carries them as the tile's appearance, both ways.
        from layout_migrations import migrate_legacy
        from page_layout import compile_tiles
        from core import Grid
        grid = Grid(2, 3)
        record = migrate_legacy({'title': 'Hall', 'tiles': [{'entity': 'camera.front_door', 'name': '', 'slot': 0,
                                                             'options': {'display': 'live', 'size': 'tall', 'fit': 'contain', 'overlay': 'none'}}]}, grid)
        appearance = record['layout']['pages'][0]['tiles'][0]['appearance']
        self.assertEqual((appearance['fit'], appearance['overlay']), ('contain', 'none'))
        self.assertEqual(compile_tiles(record['layout'], grid)[0]['options'], {'display': 'live', 'size': 'tall', 'fit': 'contain', 'overlay': 'none'})

    def test_the_app_prepares_each_picture_the_way_its_tile_asks(self):
        options = {'camera.front_door': {'display': 'live', 'size': 'tall', 'fit': 'contain'},
                   'camera.garden': {'display': 'live', 'size': 'square', 'overlay': 'none'},
                   'camera.hall': {'display': 'live'},
                   'media_player.sonos': {'display': 'cover', 'size': 'tall'}}
        entities = list(options)
        new = {'firmware': '0.3.3'}
        self.assertEqual(camera_feed.picture_modes(new, options.get, entities),
                         [('contain', True), ('fill', False), ('fill', False), ('fill', False)])
        # Firmware that draws a small square on a taller camera tile gets that square, as before.
        self.assertEqual(camera_feed.picture_modes({'firmware': '0.3.1'}, options.get, entities), [('fill', False)] * 4)

    def test_new_screens_get_their_live_pictures_in_8_bit_colour(self):
        import io, json, tile_art
        from PIL import Image
        self.assertTrue(camera_feed.compact_pictures({'firmware': '0.3.3'}))
        self.assertFalse(camera_feed.compact_pictures({'firmware': '0.3.1'}))
        source = Image.new('RGB', (1280, 720))
        for x in range(1280):
            source.paste((x % 256, (x * 3) % 256, 200), (x, 0, x + 1, 720))
        raw = io.BytesIO(); source.save(raw, 'JPEG')
        atlas = tile_art.parse(json.dumps([[0, 0, 448, 228, 12, 0]]), (480, 480), 1)
        wide = tile_art.encode([raw.getvalue()], [0xE7E7E7], atlas, [('fill', True)])
        small = tile_art.encode([raw.getvalue()], [0xE7E7E7], atlas, [('fill', True)], compact=True)
        # The BMP header says 24 and 8 bits per pixel, and the 8-bit one is about a third of the bytes.
        self.assertEqual((int.from_bytes(wide[28:30], 'little'), int.from_bytes(small[28:30], 'little')), (24, 8))
        self.assertLess(len(small), len(wide) * 0.36)
        with Image.open(io.BytesIO(small)) as image:
            self.assertEqual((image.size, image.mode), ((448, 228), 'P'))
        strip = camera_feed.encode_live([raw.getvalue()], 54, [0xFFFFFF], compact=True)
        self.assertEqual(int.from_bytes(strip[28:30], 'little'), 8)

    def test_contain_keeps_the_whole_picture_on_black_and_the_name_gets_its_shade(self):
        import io, tile_art
        from PIL import Image, ImageDraw
        source = Image.new('RGB', (1280, 720), (240, 240, 240))
        ImageDraw.Draw(source).rectangle([0, 0, 1279, 719], outline=(255, 0, 0), width=12)
        raw = io.BytesIO(); source.save(raw, 'PNG')
        atlas = tile_art.parse('[[0,0,200,300,0,0],[200,0,200,300,0,0]]', (480, 480), 2)
        out = tile_art.encode([raw.getvalue()] * 2, [0xE7E7E7] * 2, atlas, [('contain', False), ('fill', True)])
        with Image.open(io.BytesIO(out)) as image:
            image = image.convert('RGB')
            # Contain: black above and below a 200 x 113 picture whose red edge is all there.
            self.assertEqual(image.getpixel((100, 10)), (0, 0, 0))
            self.assertEqual(image.getpixel((100, 290)), (0, 0, 0))
            self.assertGreater(image.getpixel((1, 150))[0], 200)
            # Fill: cut at the sides, so no red at the left edge; the bottom darker than the top.
            self.assertLess(image.getpixel((201, 150))[0] - image.getpixel((201, 150))[1], 40)
            top, bottom = image.getpixel((300, 40)), image.getpixel((300, 298))
            self.assertLess(sum(bottom), sum(top) * 0.55)


class LiveTiles(unittest.TestCase):
    """A live picture on a camera tile (app 0.2.91, firmware 0.2.77): the page's tiles as one strip."""

    def test_the_live_display_and_its_pace_are_tile_settings(self):
        from core import LIVE_MIN_FIRMWARE, LIVE_REFRESH
        self.assertEqual((camera_feed.LIVE_MIN_FIRMWARE, camera_feed.LIVE_REFRESH), (LIVE_MIN_FIRMWARE, LIVE_REFRESH))
        layout = validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.front_door', 'name': '', 'options': {'display': 'live', 'refresh': 30}},
                                                             {'entity': 'image.doorbell', 'name': '', 'options': {'display': 'live'}}]})
        self.assertEqual(min_firmware(layout), LIVE_MIN_FIRMWARE)
        self.assertEqual(layout['tiles'][0]['options'], {'display': 'live', 'refresh': 30})
        # The icon again: the pace goes with the live display.
        plain = validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.front_door', 'name': '', 'options': {'display': 'standard', 'refresh': 30}}]})
        self.assertEqual(plain['tiles'][0]['options'], {'display': 'standard'})
        self.assertEqual(min_firmware(plain), CAMERA_MIN_FIRMWARE)
        for options in ({'display': 'live', 'refresh': 20}, {'display': 'live', 'refresh': '15'}, {'display': 'live', 'refresh': True}):
            with self.assertRaises(ValueError, msg=options):
                validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.front_door', 'name': '', 'options': options}]})
        with self.assertRaises(ValueError):
            validate_layout({'title': 'Hall', 'tiles': [{'entity': 'light.hall', 'name': '', 'options': {'display': 'live'}}]})
        # A tile event may ask for it too.
        from core import tile_options
        self.assertEqual(tile_options({'display': 'live', 'refresh': '30'}), {'display': 'live', 'refresh': 30})
        # The editor learns the choice from the capabilities.
        import ha_catalogue
        self.assertEqual(ha_catalogue.capabilities('camera.front_door', [], {}, {})['displays'], ['standard', 'live'])
        self.assertNotIn('live', ha_catalogue.capabilities('light.hall', [], {}, {})['displays'])

    def test_a_media_tile_may_show_its_cover_in_the_icons_place(self):
        from core import COVER_TILE_MIN_FIRMWARE, resolve_controls
        import ha_catalogue
        self.assertEqual(camera_feed.COVER_TILE_MIN_FIRMWARE, COVER_TILE_MIN_FIRMWARE)
        layout = validate_layout({'title': 'Hall', 'tiles': [{'entity': 'media_player.sonos', 'name': '', 'options': {'display': 'cover', 'size': 'wide'}}]})
        self.assertEqual(min_firmware(layout), COVER_TILE_MIN_FIRMWARE)
        # The cover is the standard layout with a picture: a wide tile keeps its controls.
        self.assertEqual(resolve_controls(layout['tiles'][0]), 'volume')
        self.assertIn('cover', ha_catalogue.capabilities('media_player.sonos', [], {}, {})['displays'])
        with self.assertRaises(ValueError):
            validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.front_door', 'name': '', 'options': {'display': 'cover'}}]})
        # A media player may be asked for in the strip; the request keeps its shape.
        self.assertEqual(camera_feed.live_request({'tiles': 'camera.front_door,media_player.sonos', 'size': '54', 'bg': 'FFFFFF,FFFFFF'}),
                         (['camera.front_door', 'media_player.sonos'], 54, [0xFFFFFF, 0xFFFFFF]))

    def test_which_screens_draw_live_pictures(self):
        self.assertTrue(camera_feed.can_show_live({'board': 'guition', 'firmware': '0.2.77'}))
        for screen in ({'board': 'guition', 'firmware': '0.2.76'}, {'board': 'cyd', 'firmware': '0.2.77'}, None):
            self.assertFalse(camera_feed.can_show_live(screen), screen)

    def test_the_request_names_the_tiles_their_size_and_their_grounds(self):
        self.assertEqual(camera_feed.live_request({'tiles': 'camera.front_door,image.doorbell', 'size': '54', 'bg': 'FFFFFF,fadadd'}),
                         (['camera.front_door', 'image.doorbell'], 54, [0xFFFFFF, 0xFADADD]))
        for bad in ({'tiles': 'camera.a', 'size': '54'}, {'tiles': 'camera.a,light.b', 'size': '54', 'bg': 'FFFFFF,FFFFFF'},
                    {'tiles': 'camera.a,camera.a', 'size': '54', 'bg': 'FFFFFF,FFFFFF'}, {'tiles': 'camera.a', 'size': '54', 'bg': 'FFFFFF,FFFFFF'},
                    {'tiles': 'camera.a', 'size': '8', 'bg': 'FFFFFF'}, {'tiles': 'camera.a', 'size': 'x', 'bg': 'FFFFFF'},
                    {'tiles': ','.join(f'camera.c{i}' for i in range(7)), 'size': '54', 'bg': ','.join(['FFFFFF'] * 7)}, {'tiles': '', 'size': '54', 'bg': ''}):
            self.assertIsNone(camera_feed.live_request(bad), bad)

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_the_strip_is_one_square_per_tile_with_rounded_corners_over_its_own_ground(self):
        from PIL import Image
        out = camera_feed.encode_live([picture('JPEG', (1920, 1080)), None, picture('PNG', (100, 100), 'RGBA')], 54, [0xFFFFFF, 0x1A1A1A, 0x00FF00])
        with Image.open(io.BytesIO(out)) as image:
            self.assertEqual((image.format, image.size, image.mode), ('BMP', (54, 162), 'RGB'))
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))     # the first square's corner: its ground
            self.assertEqual(image.getpixel((27, 27))[::2], (200, 90))    # its middle: the picture (JPEG, a shade off)
            self.assertEqual(image.getpixel((27, 54 + 27)), (26, 26, 26))  # no picture: a plain square of its ground
            self.assertEqual(image.getpixel((0, 108)), (0, 255, 0))       # the third square's corner: its ground

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_each_load_fetches_the_cameras_whose_pace_has_passed(self):
        clock = [1000.0]
        fetched = []

        async def fetch(entity):
            fetched.append((entity, clock[0]))
            return picture('JPEG', (640, 360))

        async def run():
            feed = camera_feed.CameraFeed(fetch, clock=lambda: clock[0])
            tiles, grounds, paces = ['camera.a', 'camera.b'], [0xFFFFFF, 0xFFFFFF], [15, 30]
            token = feed.link(','.join(tiles), (54, 54), live=(tiles, 54, grounds, paces))
            status, body, etag = await feed.serve(token)
            self.assertEqual(status, 200)
            self.assertEqual(sorted(e for e, _ in fetched), ['camera.a', 'camera.b'], 'the first load waits for both')
            # 15 s later the page loads again: only the 15 s camera is fetched again. The strip comes whole each
            # time, never a 304, whatever ETag the screen offers: ESPHome's http_request logs a 304 as an error (seen
            # on the bench Guition with a radar camera).
            clock[0] += 15
            again = await feed.serve(token, etag)
            self.assertEqual((again[0], again[2] == etag), (200, True))
            self.assertEqual([e for e, at in fetched if at == 1015.0], ['camera.a'])
            clock[0] += 15
            await feed.serve(token, etag)
            self.assertEqual(sorted(e for e, at in fetched if at == 1030.0), ['camera.a', 'camera.b'])
            # Nobody loading means nothing fetched.
            clock[0] += 60
            self.assertEqual(len([e for e, at in fetched if at > 1030.0]), 0)
        asyncio.run(run())

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_a_media_tile_in_the_strip_is_fetched_once_per_picture(self):
        clock = [1000.0]
        fetched, pictures = [], {'media_player.sonos': '/api/media_player_proxy/media_player.sonos?token=a&cache=1'}

        async def fetch(entity):
            fetched.append((entity, clock[0]))
            return picture('JPEG', (640, 360))

        async def fetch_cover(entity):
            fetched.append((entity, clock[0]))
            return picture('PNG', (300, 300))

        async def run():
            feed = camera_feed.CameraFeed(fetch, clock=lambda: clock[0], fetch_cover=fetch_cover, picture=lambda e: pictures.get(e, ''))
            tiles, grounds, paces = ['camera.a', 'media_player.sonos', 'media_player.radio'], [0xFFFFFF] * 3, [15, 0, 0]
            token = feed.link(','.join(tiles), (54, 54), live=(tiles, 54, grounds, paces))
            status, body, etag = await feed.serve(token)
            self.assertEqual(status, 200)
            from PIL import Image
            with Image.open(io.BytesIO(body)) as image:
                self.assertEqual(image.size, (54, 162))
                self.assertEqual(image.getpixel((27, 54 + 27))[::2], (200, 90), 'the cover in the second square')
                self.assertEqual(image.getpixel((27, 108 + 27)), (255, 255, 255), 'a radio without a picture: a plain square')
            found = await feed.live(tiles, 54, grounds, paces)
            self.assertEqual(found[2], ['camera.a', 'media_player.sonos', ''], 'the answer names the tiles with a picture')
            # Every 15 s the camera again, the cover not: its address did not change.
            for _ in range(3):
                clock[0] += 15
                await feed.serve(token)
            self.assertEqual(len([e for e, _ in fetched if e == 'media_player.sonos']), 1)
            self.assertEqual(len([e for e, _ in fetched if e == 'camera.a']), 4)
            # A new track: another address, fetched at the next load.
            pictures['media_player.sonos'] = '/api/media_player_proxy/media_player.sonos?token=a&cache=2'
            clock[0] += 15
            await feed.serve(token)
            self.assertEqual(len([e for e, _ in fetched if e == 'media_player.sonos']), 2)
        asyncio.run(run())


@unittest.skipUnless(HAS_AIOHTTP and HAS_PIL, 'Run using .venv-portal/bin/python for server tests')
class LiveApp(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        camera_feed.base_url.__defaults__[0].clear()

    async def test_a_screen_asks_for_the_live_tiles_of_its_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (1920, 1080)))
            ha.states['sensor.d1_fw']['state'] = '0.2.77'
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Hall', 'tiles': [
                {'entity': 'camera.max', 'name': '', 'options': {'display': 'live'}},
                {'entity': 'camera.garden', 'name': '', 'options': {'display': 'live', 'refresh': 30}},
                {'entity': 'camera.shed', 'name': ''}]}))
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'tiles': 'camera.max,camera.garden', 'size': '54', 'bg': 'FFFFFF,FADADD'})
            (_, inbox, message), = [entry for entry in ha.log if entry[0] == 'send']
            self.assertEqual((inbox, message['op'], message['t'], message['e']), ('text.d1_tiles', 'camera', 'live', 'camera.max,camera.garden'))
            token = message['u'].rsplit('/', 1)[1][:-4]
            self.assertEqual(m.camera.links[token].live, (['camera.max', 'camera.garden'], 54, [0xFFFFFF, 0xFADADD], [15, 30], {'compact': False}))
            ha.log.clear()
            # A tile that shows its icon, a camera off the layout, a screen on older firmware, a CYD: no strip.
            for request in ({'inbox': 'text.d1_tiles', 'tiles': 'camera.max,camera.shed', 'size': '54', 'bg': 'FFFFFF,FFFFFF'},
                            {'inbox': 'text.d1_tiles', 'tiles': 'camera.other', 'size': '54', 'bg': 'FFFFFF'},
                            {'inbox': 'text.d3_tiles', 'tiles': 'camera.max', 'size': '54', 'bg': 'FFFFFF'},
                            {'inbox': 'text.d2_tiles', 'tiles': 'camera.max', 'size': '54', 'bg': 'FFFFFF'}):
                with self.assertLogs('screen_manager', 'INFO') if request['inbox'] == 'text.d1_tiles' and 'shed' in request['tiles'] else contextlib.nullcontext():
                    await m.answer_camera(request)
            self.assertEqual([entry for entry in ha.log if entry[0] == 'send'], [])

    async def test_a_media_tile_asks_with_the_cameras_of_its_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (1920, 1080)))
            ha.states['sensor.d1_fw']['state'] = '0.2.78'
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Hall', 'tiles': [
                {'entity': 'camera.max', 'name': '', 'options': {'display': 'live'}},
                {'entity': 'media_player.sonos', 'name': '', 'options': {'display': 'cover', 'size': 'wide'}},
                {'entity': 'media_player.radio', 'name': '', 'options': {'display': 'cover'}},
                {'entity': 'media_player.tv', 'name': ''}]}))
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'tiles': 'camera.max,media_player.sonos,media_player.radio', 'size': '54', 'bg': 'FFFFFF,FFFFFF,FADADD'})
            (_, inbox, message), = [entry for entry in ha.log if entry[0] == 'send']
            self.assertEqual((message['t'], message['e']), ('live', 'camera.max,media_player.sonos,'), 'the radio has no picture')
            token = message['u'].rsplit('/', 1)[1][:-4]
            self.assertEqual(m.camera.links[token].live[3], [15, 0, 0], 'a cover has no pace')
            ha.log.clear()
            # A media tile that shows its icon is not in the strip.
            await m.answer_camera({'inbox': 'text.d1_tiles', 'tiles': 'camera.max,media_player.tv', 'size': '54', 'bg': 'FFFFFF,FFFFFF'})
            self.assertEqual([entry for entry in ha.log if entry[0] == 'send'], [])

    async def test_tall_artwork_is_bounded_and_reuses_the_live_image_endpoint(self):
        from PIL import Image
        import json
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (900, 600)))
            ha.states['sensor.d1_fw']['state'] = '0.2.103'
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Media', 'tiles': [
                {'entity': 'media_player.sonos', 'name': '', 'options': {'display': 'cover', 'size': 'wide'}}]}))
            request = {'inbox': 'text.d1_tiles', 'tiles': 'media_player.sonos,media_player.sonos',
                       'size': '54', 'bg': 'E6E6E6,FFFFFF',
                       'atlas': json.dumps([[16, 70, 220, 220, 20, 170], [260, 80, 54, 54, 9, 0]])}
            await m.answer_camera(request)
            message = [entry[2] for entry in ha.log if entry[0] == 'send'][-1]
            token = message['u'].rsplit('/', 1)[1][:-4]
            status, raw, tag = await m.camera.serve(token)
            self.assertEqual(status, 200)
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual(image.size, (314, 290))
                self.assertLess(image.getpixel((110, 180))[0], image.getpixel((285, 105))[0])
            # An ordinary duplicate on a different page does not revoke the cover.
            m.layouts['text.d1_tiles']['tiles'].append({'entity': 'media_player.sonos', 'name': 'Plain'})
            ha.log.clear()
            await m.answer_camera(request)
            self.assertTrue(any(entry[0] == 'send' for entry in ha.log))
            # Repeated sources are valid in an atlas, but never allocate twice per tile.
            self.assertEqual(len(m.camera.strips), 1)
            # Even a paired device cannot request images outside its native canvas.
            ha.log.clear()
            for bad in ('not json', '[[0,0,481,480,0,170]]', '[[0,0,220,220,0,170],[20,20,54,54,0,0]]'):
                await m.answer_camera({**request, 'atlas': bad})
            await m.answer_camera({**request, 'tiles': 'media_player.other,media_player.sonos'})
            self.assertEqual([entry for entry in ha.log if entry[0] == 'send'], [])

    async def test_a_camera_without_a_picture_keeps_its_icon(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(None)
            ha.states['sensor.d1_fw']['state'] = '0.2.77'
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.max', 'name': '', 'options': {'display': 'live'}}]}))
            with self.assertLogs('screen_manager', 'INFO') as logs:
                await m.answer_camera({'inbox': 'text.d1_tiles', 'tiles': 'camera.max', 'size': '54', 'bg': 'FFFFFF'})
            (_, _, message), = [entry for entry in ha.log if entry[0] == 'send']
            self.assertEqual((message['t'], message['e'], message['u']), ('live', 'camera.max', ''))
            self.assertIn('no image', logs.output[-1])


if __name__ == '__main__':
    unittest.main()
