"""Camera images on a Guition (app 0.2.66, firmware 0.2.57): the app fetches, sizes and serves the image on its own
port; the screen asks with esphome.screen_camera and downloads the link in a task beside its main loop (picture_fetch).
In the app every picture takes one way (docs/PICTURES.md): the question (picture_question, or picture_legacy for the
shapes of older firmware), its sources (picture_sources), the one painter (picture_paint), the links on the camera port
(picture_links) and the service between them (picture_service)."""
from firmware_sources import firmware_domains, runtime_source
from manager_fixtures import with_screen_grid, seed_layout
import asyncio
import contextlib
import importlib.util
import io
from pathlib import Path
import re
import socket
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import picture_legacy  # noqa: E402
import lan_address  # noqa: E402
import picture_links  # noqa: E402
import picture_paint  # noqa: E402
import picture_question as pq  # noqa: E402
import picture_service  # noqa: E402
import picture_sources  # noqa: E402
from picture_question import Owner, Place, Question, Source  # noqa: E402
from core import (ALERT_FIELDS, BROADCAST_SHOW, CAMERA_MIN_FIRMWARE, alert_camera, alert_reference, entity_id,  # noqa: E402
                  header_entity, min_firmware, screen_firmware, validate_layout, extras)

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
        self.assertEqual(pq.alert_box(guition, (1920, 1080)), (391, 220))
        square = pq.alert_box(guition, (720, 720))
        self.assertEqual(square[0], square[1])
        self.assertGreater(square[1], 220)
        # Older firmware has one frame for every picture; it gets the picture for that frame, as before.
        self.assertEqual(pq.alert_box({'board': 'guition', 'firmware_known': '0.2.102'}, (720, 720)), (392, 220))
        # A screen whose Override YAML changed its density reports it ("Screen layout"), and gets the frame of its card
        # at that density, with the fonts it was built with.
        import alert_layout
        denser = {**guition, 'shape': {'width': 480, 'height': 480, 'columns': 2, 'rows': 3, 'dpi': 200, 'look': 'standard'}}
        card = alert_layout.layout(480, 480, *alert_layout.lines(200, 'standard'), True, 200, 'standard', 1080, 1440)
        self.assertEqual(pq.alert_box(denser, (1080, 1440)), (card.image_w, card.image_h))
        self.assertNotEqual(pq.alert_box(denser, (1080, 1440)), pq.alert_box(guition, (1080, 1440)))
        # A board that states the density of its fonts (FONT_DPI, `font_dpi`) keeps those fonts at the other density.
        from unittest import mock
        with mock.patch.dict(pq.SHAPES, {'guition': {**pq.SHAPES['guition'], 'font_dpi': 170}}):
            card = alert_layout.layout(480, 480, *alert_layout.lines(170, 'standard'), True, 200, 'standard', 1080, 1440)
            self.assertEqual(pq.alert_box(denser, (1080, 1440)), (card.image_w, card.image_h))
        # No picture known, or a board without pictures.
        self.assertEqual(pq.alert_box(guition, None), (392, 220))
        self.assertIsNone(pq.alert_box({'board': 'cyd', 'firmware_known': '0.2.103'}, (720, 720)))
        # Never larger than the screen's own full-screen picture, which is what its board's memory is measured for.
        for board, shape in pq.SHAPES.items():
            if board != shape.get('board') or 'camera' not in shape:
                continue
            for way in ('landscape', 'portrait'):
                screen = {'board': board, 'orientation': way, 'firmware_known': '0.2.103'}
                full = pq.box(screen, 'full')
                for picture in ((1920, 1080), (720, 720), (1080, 1440), (2560, 1080), (1080, 1920)):
                    w, h = pq.alert_box(screen, picture)
                    self.assertLessEqual(w * h, full[0] * full[1], (board, way, picture))
                    self.assertLessEqual(w, full[0], (board, way, picture))
                    self.assertLessEqual(h, full[1], (board, way, picture))

    def test_every_picture_stays_within_one_cap_whatever_the_glass(self):
        # GitHub #68: a 10-inch glass asked for pictures of up to 2 MB, more than its store kept. The app and the
        # firmware cap every picture with the same two numbers, the firmware in picture_store.h.
        header = (ROOT / 'components/smart_display/picture_store.h').read_text()
        self.assertIn(f'constexpr int MAX_SIDE = {pq.MAX_SIDE};', header)
        self.assertEqual(eval(re.search(r'constexpr size_t MAX_BYTES = ([0-9 *]+);', header).group(1)), pq.MAX_BYTES)
        for board, shape in pq.SHAPES.items():
            if board != shape.get('board') or 'camera' not in shape:
                continue
            for way in ('landscape', 'portrait'):
                for view in ('full', 'thumb'):
                    w, h = pq.box({'board': board, 'orientation': way}, view)
                    self.assertLessEqual(max(w, h), pq.MAX_SIDE, (board, way, view))
                    self.assertLessEqual(w * h * 2, pq.MAX_BYTES, (board, way, view))
        # The 10-inch's full screen keeps its proportions; up to the 1024x600 glass every board keeps its own pixels.
        self.assertEqual(pq.box({'board': 'jc8012p4a1'}, 'full'), (1024, 640))
        self.assertEqual(pq.box({'board': 'jc1060p470'}, 'full'), (1024, 600))
        self.assertEqual(pq.box({'board': 'waveshare7'}, 'full'), (800, 480))
        self.assertEqual(pq.capped((2560, 1440)), (1024, 576))
        w, h = pq.capped((1248, 684))
        self.assertLessEqual(w * h * 2, pq.MAX_BYTES)
        self.assertAlmostEqual(w / h, 1248 / 684, places=2)

    def test_a_screen_with_the_memory_takes_its_glass_at_its_own_pixels(self):
        # GitHub #183: a screen whose picture store has the room (the 32 MB of the P4 boards) says how large one picture
        # may be (`cap`, picture_store::cap_for), and its full view, map and screensaver come at its own pixels. A
        # screen that says nothing, or less than the common cap, keeps that cap; nothing goes over PICTURE_LARGE_BYTES.
        header = (ROOT / 'components/smart_display/picture_store.h').read_text()
        self.assertIn(f'constexpr int LARGE_SIDE = {pq.LARGE_SIDE};', header)
        store = min(6 << 20, (32 << 20) // 5)  # runtime_tiles::pictures_kept on a P4 board
        cap = pq.cap_of(str(store // 3))
        self.assertEqual(pq.box({'board': 'jc8012p4a1'}, 'full', cap), (1280, 800))
        self.assertEqual(pq.box({'board': 'tab5'}, 'full', cap), (1280, 720))
        for value in (None, '', 'x', '1000', 1000, [], {}):
            self.assertEqual(pq.cap_of(value), (pq.MAX_SIDE, pq.MAX_BYTES))
            self.assertEqual(pq.box({'board': 'jc8012p4a1'}, 'full', pq.cap_of(value)), (1024, 640))
        self.assertEqual(pq.cap_of(str(64 << 20)), (pq.LARGE_SIDE, pq.LARGE_BYTES))
        # An older screen's full view names its cap as it always did, and gets its glass at its own pixels.
        legacy = picture_legacy.read({'entity': 'camera.max', 'cap': str(store // 3)}, {'board': 'jc8012p4a1', 'firmware': '0.52.0'})
        self.assertEqual((legacy.question.box, legacy.question.cap), ((1280, 800), cap))
        # The app's rhythm of the full view is the firmware's (camera_view::REFRESH_MS): it fetches just before each load.
        view = (ROOT / 'components/smart_display/camera_view.h').read_text()
        self.assertIn(f'constexpr uint32_t REFRESH_MS = {picture_legacy.FULL_VIEW_PACE};', view)
        self.assertEqual(legacy.question.pace, picture_legacy.FULL_VIEW_PACE)
        # The firmware names it to an older app only for a picture of the whole glass (the full view and the screensaver,
        # picture_question::legacy), never on a board of 8 MB.
        question = (ROOT / 'components/smart_display/picture_question.h').read_text()
        self.assertIn('const bool larger = q.cap > picture_store::MAX_BYTES;', question)
        legacy_fields = question[question.index('inline Fields legacy('):]
        legacy_fields = legacy_fields[legacy_fields.index('case Owner::VIEW:'):legacy_fields.index('case Owner::CARD:')]
        self.assertIn('if (larger) out.emplace_back("cap", std::to_string(q.cap));', legacy_fields)
        self.assertEqual(question.count('emplace_back("cap"'), 1)

    def test_the_jpeg_profile_is_one_rule_on_both_sides(self):
        # The JPEG a P4 takes (picture_jpeg.h) is what picture_paint.encode makes: whole MCUs of the same size, the same
        # mark on the APP15 segment that carries the shown size and the corners, the same most corners; and a live tile
        # lays over each of its frames the shade the app bakes into a still (live_view.h, picture_paint._flat).
        header = (ROOT / 'components/smart_display/picture_jpeg.h').read_text()
        self.assertIn(f'constexpr int MCU = {picture_paint.MCU};', header)
        self.assertIn(f'constexpr char NOTES_MARK[] = "{picture_paint.JPEG_SIZE.decode()}";', header)
        self.assertIn(f'constexpr int MAX_CORNERS = {picture_paint.MAX_CORNERS};', header)
        view = (ROOT / 'components/smart_display/live_view.h').read_text()
        self.assertIn(f'constexpr int FADE_PERCENT = {round(picture_paint.FADE_SHARE * 100)};', view)
        self.assertIn(f'constexpr int FADE_DEPTH = {picture_paint.FADE_DEPTH};', view)

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_the_jpeg_notes_lie_where_the_screen_reads_them(self):
        # picture_jpeg::jpeg_notes reads the segment at fixed places: FF EF at 2, its length at 4, the mark at 6, the
        # shown width and height at 10 and 12, the count of corners at 14 and eleven bytes a corner from 15 on (x, y, w,
        # h as two bytes each, the radius as one, the ground as RGB565 in two). The picture behind it is whole MCUs.
        from PIL import Image
        body = picture_paint.encode(Image.new('RGB', (226, 254), (10, 20, 30)), 'jpeg', ((2, 3, 40, 30, 8, 0xE73C),))
        self.assertEqual(body[:4], b'\xff\xd8\xff\xef')
        self.assertEqual(body[6:10], picture_paint.JPEG_SIZE)
        self.assertEqual((int.from_bytes(body[10:12], 'big'), int.from_bytes(body[12:14], 'big')), (226, 254))
        self.assertEqual(body[14], 1)
        self.assertEqual(body[15:26], bytes([0, 2, 0, 3, 0, 40, 0, 30, 8, 0xE7, 0x3C]))
        length = int.from_bytes(body[4:6], 'big')
        self.assertEqual(length, 2 + len(picture_paint.JPEG_SIZE) + 4 + 1 + 11)
        self.assertEqual(body[4 + length], 0xFF)  # the next marker starts right after the segment
        self.assertEqual(picture_paint.jpeg_notes(body), ((226, 254), ((2, 3, 40, 30, 8, 0xE73C),)))
        with Image.open(io.BytesIO(body)) as padded:
            self.assertEqual(padded.size, (240, 256))  # whole MCUs of picture_paint.MCU each way

    @unittest.skipUnless(HAS_PIL, 'needs Pillow')
    def test_a_turned_snapshot_is_measured_the_way_it_is_shown(self):
        from PIL import Image
        out = io.BytesIO()
        image = Image.new('RGB', (1440, 1080))
        exif = image.getexif()
        exif[0x0112] = 6  # turned a quarter: shown 1080 wide, 1440 high
        image.save(out, 'JPEG', exif=exif)
        self.assertEqual(picture_paint.size_of(out.getvalue()), (1080, 1440))
        self.assertEqual(picture_paint.size_of(picture('PNG', (640, 360))), (640, 360))

    def test_camera_and_image_tiles_need_the_camera_firmware(self):
        self.assertTrue(entity_id('camera.front_door') and entity_id('image.doorbell'))
        self.assertEqual(pq.MIN_FIRMWARE, CAMERA_MIN_FIRMWARE)
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
        self.assertTrue(pq.draws_pictures({'board': 'guition', 'firmware': '0.2.57'}))
        self.assertTrue(pq.draws_pictures({'board': 'guition', 'firmware': '0.3.0'}))
        for screen in ({'board': 'guition', 'firmware': '0.2.56'}, {'board': 'unknown', 'firmware': '0.2.57'},
                       {'board': 'guition', 'firmware': 'unknown'}, None, {}):
            self.assertFalse(pq.draws_pictures(screen), screen)
        supported = lambda entity: pq.valid_entity(entity, pq.CAMERA_DOMAINS)
        self.assertTrue(supported('camera.max') and supported('image.max_motion'))
        for value in ('light.kitchen', 'camera', 'Camera.Max', None, 42, 'camera.' + 'x' * 120):
            self.assertFalse(supported(value), value)

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
        self.assertEqual(pq.BOXES['guition'], {'full': (int(subs['CAMERA_FULL_W']), int(subs['CAMERA_FULL_H'])),
                                               'thumb': (392, 220)})

    def test_the_firmware_and_the_app_speak_the_same_words(self):
        self.assertIn('request.service = esphome::StringRef("esphome.screen_camera");', TILES)
        self.assertIn("event_type='esphome.screen_camera'", (ROOT / 'screen_manager/app/server.py').read_text())
        self.assertIn('if (op == "camera") {', TILES)
        self.assertLessEqual({'camera', 'image'}, firmware_domains())
        # The profile binds the three pictures (firmware 0.49.0+: downloaded beside the main loop, picture_fetch) and hands
        # finished ones to their cards on the main loop; the CYD has none, so it never opens a camera.
        for needle in ('picture_fetch::bind(picture_fetch::full(),', 'picture_fetch::bind(picture_fetch::thumb(),',
                       'picture_fetch::bind(picture_fetch::live(),', 'runtime_tiles::picture_done(picture_loader::Slot::FULL, ok, cached);',
                       'runtime_tiles::picture_done(picture_loader::Slot::THUMB, ok, cached);',
                       'runtime_tiles::picture_done(picture_loader::Slot::LIVE, ok, cached);',
                       'runtime_tiles::camera_full.load = ', 'runtime_tiles::camera_thumb.load = ', 'runtime_tiles::camera_live.load = ',
                       "- lambda: 'picture_fetch::tick(); runtime_tiles::live_tick();'", 'runtime_tiles::camera_tick();', 'runtime_tiles::alert_prepare();',
                       'runtime_tiles::alert_clear();', 'runtime_tiles::camera_close();', 'id: alert_image_frame'):
            self.assertIn(needle, PROFILE, needle)
        # Nothing of ESPHome's online_image is left: it downloaded in the main loop, a chunk a turn, each waiting for the
        # network, and a page of covers held the glass still for seconds (0.4.80).
        for gone in ('online_image:', 'http_request:', 'id(camera_image)', 'id(tile_image)', 'id(alert_image)', 'if (url != current) {'):
            self.assertNotIn(gone, PROFILE, gone)
        # A busy camera port leaves the rest of the app running.
        self.assertIn("except OSError as error:\n            # Everything else still works; only camera images stay away.", (ROOT / 'screen_manager/app/server.py').read_text())
        cyd = profiles.text('checkout/cyd.yaml')
        self.assertNotIn('picture_fetch::', cyd)
        self.assertNotIn('camera_full.load', cyd)
        # The add-on's port is published, and the Docker route passes it on with the host network.
        config = (ROOT / 'screen_manager/config.yaml').read_text()
        self.assertIn(f'{picture_links.PORT}/tcp: {picture_links.PORT}', config)

    def test_the_first_picture_waits_for_no_tick(self):
        # Firmware 0.2.73+: the camera asks when it opens and loads the link when it comes, not on the next 250 ms tick;
        # the spinner turns until the first picture or a note is there.
        opened = TILES.split('inline void camera_open(const std::string &entity, const std::string &name, int map_index, const std::string &focus) {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('camera_spinner = spinner_create(camera_root,', opened)
        # Opened, it says what it wants at once (one round of the picture route, firmware 0.52.0): the loader asks then.
        self.assertTrue(opened.rstrip().endswith('pictures_round();'))
        # pictures_awake: awake, or the screensaver's picture in standby (firmware 0.29.0+).
        want = TILES.split('inline void camera_want() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('if (!camera_root || !camera.open() || !pictures_awake()) return;', want)
        # The answer starts the download in the same round, not on the next tick.
        answer = TILES.split('inline void camera_answer(const std::string &view, const std::string &entity, const std::string &url, uint32_t number) {', 1)[1].split('\n}\n', 1)[0]
        self.assertTrue(answer.rstrip().endswith('pictures_round();'))
        # Never under a finger, and not while the pages turn: the round tells the loader whether it may load.
        round_ = TILES.split('inline void pictures_round() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('const bool pressed = input && lv_indev_get_state(input) == LV_INDEV_STATE_PRESSED;', round_)
        self.assertIn('loader.end(now, !pressed && camera_view::settled(now, last_turn_ms));', round_)
        note = TILES.split('inline void camera_note_text(const char *text) {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('lv_obj_delete(camera_spinner);', note)
        self.assertNotIn('Loading image', TILES)

    def test_the_full_screen_draws_a_copy_a_broken_download_cannot_take_away(self):
        # Firmware 0.13.0: a download that broke off halfway made online_image free the buffer the view still drew, and
        # every part of the glass drawn again after that (a tile below going unavailable) came out black. The view draws
        # the store's copy, which the store keeps while it is on the glass and lets go of once the view closes.
        # Every download goes into the store under its picture's key (picture_done, firmware 0.52.0); a 304 keeps what the
        # store has. The store takes the download's own buffer, never a copy of it (docs/PICTURES.md, "Memory"), and the
        # slot lets go of it, keeping its ETag; a 304 for a picture the store let go meanwhile is loaded whole.
        done = TILES.split('inline void picture_done(picture_loader::Slot slot, bool ok, bool cached) {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('if (pictures_kept() && cached && pictures.entry(key)) {\n      pictures.touch(key, now);', done)
        self.assertIn('pictures.adopt(key, taken, now)', done)
        self.assertIn('if (kept && hooks.hand_over) hooks.hand_over();', done)
        self.assertIn('if (!asked.empty() && !pictures.entry(asked) && !(held && held->data)) {', done)
        self.assertNotIn('memcpy', (ROOT / 'components/smart_display/picture_store.h').read_text())
        # A picture the store has no room for is drawn from the download, and says so in the log.
        self.assertIn('ESP_LOGW("picture", "no room to keep %s", key.c_str());', done)
        self.assertIn('if (!kept) { slot_key[s] = key; slot_at[s] = now; }', done)
        view = TILES.split('inline void view_done(picture_loader::Outcome outcome) {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('lv_image_dsc_t *src = picture_of(camera_key());', view)
        self.assertIn('camera_show(camera_root, camera_picture, src, outcome == picture_loader::Outcome::LOADED);', view)
        self.assertNotIn('camera_show(camera_root, camera_picture, camera_full.source()', TILES)
        shown = TILES.split('inline bool picture_shown(const lv_image_dsc_t *image) {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('on(camera_picture);', shown)
        self.assertIn('on(alert_picture);', shown)
        closed = TILES.split('inline void camera_close() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('loader.release(owners::VIEW);', closed)
        # Let go before the camera is forgotten, or the key would name no camera.
        self.assertLess(closed.index('loader.release('), closed.index('camera = ViewPicture{};'))


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class MediaFetchSecurity(unittest.IsolatedAsyncioTestCase):
    async def test_local_media_urls_must_be_the_entity_proxy_route(self):
        ha = HomeAssistant(None, 'http://ha/api', 'token')
        ha.states = {'media_player.office': {'attributes': {'entity_picture': '/api/states'}}}
        with self.assertRaisesRegex(ValueError, 'unsafe picture address'):
            await ha.media_image('media_player.office')

        ha.states['media_player.office']['attributes']['entity_picture'] = (
            '/api/media_player_proxy/media_player.office/../../states'
        )
        with self.assertRaisesRegex(ValueError, 'unsafe picture address'):
            await ha.media_image('media_player.office')

    async def test_remote_media_urls_cannot_target_private_hosts(self):
        ha = HomeAssistant(None, 'http://ha/api', 'token')
        for url in ('http://127.0.0.1/admin', 'http://169.254.169.254/latest/meta-data/'):
            ha.states = {'media_player.office': {'attributes': {'entity_picture': url}}}
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'unsafe picture address'):
                await ha.media_image('media_player.office')

    async def test_a_host_in_front_of_the_proxy_path_is_no_proxy(self):
        ha = HomeAssistant(None, 'http://ha/api', 'token')
        ha.states = {'media_player.office': {'attributes': {
            'entity_picture': '//elsewhere/api/media_player_proxy/media_player.office?token=abc'}}}
        with self.assertRaisesRegex(ValueError, 'unsafe picture address'):
            await ha.media_image('media_player.office')

    async def test_home_assistant_proxy_goes_first(self):
        session = RecordingSession()
        ha = HomeAssistant(session, 'http://ha/api', 'token')
        proxy = '/api/media_player_proxy/media_player.office?token=abc&cache=123'
        # A player whose picture lies elsewhere (Cast, HEOS, WiiM) hands out that address and Home Assistant's proxy
        # beside it: the picture comes through the proxy, a picture in the house too, with the token for the proxy only.
        for elsewhere in ('http://192.168.1.20/art.jpg', 'https://i.scdn.co/image/x'):
            ha.states = {'media_player.office': {'attributes': {'entity_picture': elsewhere, 'entity_picture_local': proxy}}}
            self.assertEqual(await ha.media_image('media_player.office'), b'picture')
            self.assertEqual(session.calls[-1], ('http://ha' + proxy, 'Bearer token', False))
        # A universal media player hands out its child's proxy as its picture and its own proxy beside it.
        own = '/api/media_player_proxy/media_player.living_room?token=def&cache=456'
        ha.states = {'media_player.living_room': {'attributes': {
            'entity_picture': '/api/media_player_proxy/media_player.sonos?token=abc&cache=123', 'entity_picture_local': own}}}
        self.assertEqual(await ha.media_image('media_player.living_room'), b'picture')
        self.assertEqual(session.calls[-1], ('http://ha' + own, 'Bearer token', False))
        # Without a proxy a picture on the internet comes as it is, without the token.
        ha.states = {'media_player.office': {'attributes': {'entity_picture': 'https://8.8.8.8/art.jpg'}}}
        self.assertEqual(await ha.media_image('media_player.office'), b'picture')
        self.assertEqual(session.calls[-1], ('https://8.8.8.8/art.jpg', None, False))

    async def test_a_name_is_looked_up_without_holding_the_app(self):
        answers = {'art.example.com': '93.184.216.34', 'nas.example.com': '192.168.1.20'}

        async def getaddrinfo(host, port, *args, **kwargs):
            await asyncio.sleep(0)
            if host not in answers:
                raise socket.gaierror('unknown')
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (answers[host], 0))]

        session = RecordingSession()
        ha = HomeAssistant(session, 'http://ha/api', 'token')
        with mock.patch.object(asyncio.get_running_loop(), 'getaddrinfo', getaddrinfo), \
                mock.patch.object(socket, 'getaddrinfo', side_effect=AssertionError('blocking lookup')):
            ha.states = {'media_player.office': {'attributes': {'entity_picture': 'https://art.example.com/x.jpg'}}}
            self.assertEqual(await ha.media_image('media_player.office'), b'picture')
            for host in ('nas.example.com', 'nowhere.example.com'):
                ha.states = {'media_player.office': {'attributes': {'entity_picture': f'http://{host}/x.jpg'}}}
                with self.subTest(host=host), self.assertRaisesRegex(ValueError, 'unsafe picture address'):
                    await ha.media_image('media_player.office')
        self.assertEqual(len(session.calls), 1)


class RecordingSession:
    """An aiohttp session that answers every GET with the same small body and keeps what it was asked."""

    def __init__(self):
        self.calls = []

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        self.calls.append((url, (headers or {}).get('Authorization'), allow_redirects))

        class Response:
            content_length = 7

            class content:
                @staticmethod
                async def iter_chunked(size):
                    yield b'picture'

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *error):
                return False
        return Response()


def still(raw, box):
    """A full view's still as the one painter makes it: the picture at its own proportions within the box (fit `shrink`),
    a 24-bit BMP, as every full view has always been sent."""
    question = Question(Owner('view'), (Source('camera', 'camera.max'),), box, (Place(0, 0, *box, fit='shrink'),))
    return picture_paint.paint(question, [raw], 'bmp24')


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
            bmp = still(raw, box)
            with Image.open(io.BytesIO(bmp)) as image:
                self.assertEqual((image.format, image.size, image.mode), ('BMP', size, 'RGB'))
            # What ESPHome's BMP decoder reads: 24 bits per pixel, no compression, rows padded to four bytes.
            self.assertEqual((bmp[:2], int.from_bytes(bmp[28:30], 'little'), int.from_bytes(bmp[30:34], 'little')), (b'BM', 24, 0))
            self.assertEqual(len(bmp), int.from_bytes(bmp[10:14], 'little') + size[1] * ((size[0] * 3 + 3) // 4 * 4))
        with self.assertRaises(Exception):
            still(b'not an image', (480, 480))

    def test_fit_keeps_proportions(self):
        self.assertEqual(picture_paint.fitted((1920, 1080), (480, 480)), (480, 270))
        self.assertEqual(picture_paint.fitted((1, 5000), (224, 126)), (1, 126))
        self.assertEqual(picture_paint.fitted((5000, 1), (224, 126)), (224, 1))


class Photos(unittest.IsolatedAsyncioTestCase):
    async def test_a_photo_at_the_internal_address_skips_the_certificate(self):
        # Under the Supervisor a media source's file comes from Home Assistant's own internal address, by the signature
        # resolve_media gave it, with no token: on https with the house's own certificate that certificate is not checked.
        class Session(RecordingSession):
            def __init__(self):
                super().__init__()
                self.options = []

            def get(self, url, headers=None, timeout=None, allow_redirects=True, **options):
                self.options.append(options)
                return super().get(url, headers, timeout, allow_redirects)

        session = Session()
        ha = HomeAssistant(session, 'http://supervisor/core/api', 'token')
        ha._internal_url = 'https://homeassistant.local:8123'
        self.assertEqual(await ha.media_file('/media/local/a.jpg?authSig=x'), b'picture')
        self.assertEqual(session.calls[-1], ('https://homeassistant.local:8123/media/local/a.jpg?authSig=x', None, False))
        self.assertEqual(session.options[-1], {'ssl': False})
        ha._internal_url = 'http://192.168.1.10:8123'
        await ha.media_file('/media/local/a.jpg?authSig=x')
        self.assertEqual(session.options[-1], {})
        # Through the API itself, with the app's token, the certificate stays checked.
        await ha.media_file('/api/image/serve/abc/512x512')
        self.assertEqual(session.calls[-1], ('http://supervisor/core/api/image/serve/abc/512x512', 'Bearer token', False))
        self.assertEqual(session.options[-1], {})


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


INBOX = 'text.d1_tiles'


class Rig:
    """The one picture service (picture_service) over a Manager of the test's own: one screen, its layout's tiles and
    what it may show, with the cameras' snapshots and the links on the test's clock. Nothing of Home Assistant."""

    def __init__(self, fetch=None, *, clock=None, sleep=None, fetch_cover=None, picture=None, tiles=(), firmware='0.3.3',
                 board='guition', allowed=True, saver=()):
        self.clock = clock or Clock()
        waits = {} if sleep is None else {'sleep': sleep}
        self.snapshots = picture_sources.Snapshots(fetch, clock=self.clock, fetch_cover=fetch_cover, picture=picture, **waits)
        self.links = picture_links.Links(clock=self.clock)
        self.sources = picture_sources.Sources(picture_sources.Providers.of(self), self.snapshots)
        self.service = picture_service.Service(self, self.sources, self.links)
        self.tiles, self.allowed, self.saver = list(tiles), allowed, set(saver)
        self.ha = types.SimpleNamespace(states={})
        self.rest_pools = {}
        self.player = {'id': INBOX, 'name': 'Hall', 'board': board, 'firmware': firmware, 'online': True}

    # What the service and the sources ask of the app's Manager.
    def screen(self, inbox):
        return self.player

    async def link_base(self, screen):
        return 'http://192.168.1.57:8098'

    def layout_tiles(self, inbox):
        return self.tiles

    def camera_allowed(self, inbox, entity):
        return self.allowed is True or entity in (self.allowed or ())

    def saver_entities(self, inbox):
        return self.saver

    def followed(self, entity):
        return entity

    # The test's own.
    def read(self, request):
        """The question an older screen's request is, as Manager.answer_camera reads it (picture_legacy)."""
        found = picture_legacy.read(request, self.player, self.sources.index_of(INBOX))
        return found.question if found else None

    async def answer(self, question):
        return await self.service.answer(INBOX, self.player, question)

    async def token(self, question):
        """The link's token of the service's answer, or None for an answer without a link."""
        found = await self.answer(question)
        return found.url.rsplit('/', 1)[1].split('.')[0] if found is not None and found.url else None

    def recipe(self, question):
        """A link that paints its picture again at every load, as the service gives a camera's (before any load)."""
        return self.links.add(recipe=picture_service.Recipe(INBOX, question))


@unittest.skipUnless(HAS_PIL, 'Pillow comes with ESPHome in the add-on image')
class Feed(unittest.IsolatedAsyncioTestCase):
    def feed(self, answers, **options):
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

        # The snapshots' waits (a fetch ahead's): recorded, and over when the test says so (wake), never in real seconds.
        self.sleeps = []

        async def sleep(delay):
            gate = asyncio.Event()
            self.sleeps.append((delay, gate))
            await gate.wait()
        return Rig(fetch, clock=clock, sleep=sleep, **options), clock

    async def wake(self):
        """The waits are over: the fetches ahead start."""
        for _, gate in self.sleeps:
            gate.set()
        self.sleeps.clear()
        await self.settle()

    async def settle(self):
        """Let the fetch a load started run before counting fetches: whether it already ran when serve() returns
        depends on whether serve() had to wait for anything itself."""
        for _ in range(5):
            await asyncio.sleep(0)

    async def test_links_serve_the_last_frame_and_answer_unchanged_images_with_304(self):
        rig, clock = self.feed([picture('JPEG', (1920, 1080))])
        token = await rig.token(rig.read({'entity': 'camera.max'}))
        status, bmp, etag, kind = await rig.links.serve(token)
        self.assertEqual((status, bmp[:2], kind), (200, b'BM', 'image/bmp'))
        # The ETag names what the picture shows (its source's snapshot) and how it is painted.
        self.assertRegex(etag, r'^"[0-9a-f]{16}"$')
        await self.settle()
        # The camera answered the same picture again: the screen keeps what it has.
        self.assertEqual(await rig.links.serve(token, etag), (304, None, etag, 'image/bmp'))
        self.assertEqual((await rig.links.serve('unknown'))[0], 404)
        # A link nobody used for LINK_SECONDS is gone; the screen asks for a new one.
        clock.now += picture_links.LINK_SECONDS + 1
        self.assertEqual((await rig.links.serve(token))[0], 404)

    async def test_each_load_gets_the_snapshot_fetched_just_before_it(self):
        # GitHub #183: a load sets the next fetch for just before the next load (its pace, less the time the camera
        # takes and a margin), so a picture is a fraction of a second old, not a whole pace. Before, a load got the
        # snapshot fetched at the load before it.
        first, second, third = picture('JPEG', (640, 360)), picture('PNG', (640, 360)), picture('BMP', (640, 360))
        rig, clock = self.feed([first, second, third])
        token = rig.recipe(rig.read({'entity': 'camera.max'}))
        _, one, tag_one, _ = await rig.links.serve(token)
        await self.settle()
        self.assertEqual(self.fetched, ['camera.max'], 'the first picture, waited for')
        self.assertEqual([round(delay, 2) for delay, _ in self.sleeps],
                         [picture_legacy.FULL_VIEW_PACE / 1000 - 0 - picture_sources.AHEAD_MARGIN], 'the next fetch, set for later')
        # Until just before the next load nothing is fetched; then the fetch ahead goes.
        clock.now += 3.5
        await self.wake()
        self.assertEqual(len(self.fetched), 2)
        clock.now += 0.5
        _, two, tag_two, _ = await rig.links.serve(token, tag_one)
        await self.settle()
        self.assertNotEqual(tag_two, tag_one, 'the snapshot of just now')
        self.assertEqual(len(self.fetched), 2, 'no second fetch for the same moment')
        # A slow camera: the load waits a moment for the fetch on its way, and two screens loading share that fetch.
        self.gate = asyncio.Event()
        clock.now += 3.5
        await self.wake()
        self.assertEqual(len(self.fetched), 3)
        loads = [asyncio.ensure_future(rig.links.serve(token, tag_two)) for _ in range(2)]
        await self.settle()
        self.gate.set()
        three = [await load for load in loads]
        self.assertEqual(len(self.fetched), 3)
        self.assertTrue(all(answer[2] not in (tag_one, tag_two) for answer in three), 'both got the new snapshot')

    async def test_a_tile_at_its_pace_is_fetched_just_before_its_load_and_the_quickest_tile_sets_it(self):
        rig, clock = self.feed([picture('JPEG', (640, 360)), picture('PNG', (640, 360)), picture('BMP', (640, 360))])
        await rig.snapshots.still('camera.drive', pace=15, wait=1)
        await self.settle()
        self.assertEqual([round(delay, 2) for delay, _ in self.sleeps], [15 - picture_sources.AHEAD_MARGIN])
        # A quicker tile of the same camera sets it sooner; a slower one changes nothing.
        await rig.snapshots.still('camera.drive', pace=5, wait=1)
        await rig.snapshots.still('camera.drive', pace=30, wait=1)
        await self.settle()
        pending = [round(delay, 2) for delay, gate in self.sleeps if not gate.is_set()]
        self.assertIn(5 - picture_sources.AHEAD_MARGIN, pending)
        self.assertEqual(len(self.fetched), 1)
        # Through the service: each tile at its own pace (its `refresh`, else TILE_PACE), the quickest tile's fetch ahead
        # kept for the camera they share.
        self.assertEqual(picture_sources.TILE_PACE, 15)
        rig.tiles = [{'entity': 'camera.yard', 'name': '', 'options': {'display': 'live', 'refresh': 5}},
                     {'entity': 'camera.yard', 'name': '', 'options': {'display': 'live'}}]
        for index in (0, 1):
            self.assertTrue(await rig.token(rig.read({'tiles': 'camera.yard', 'idx': str(index), 'size': '54', 'bg': 'FFFFFF'})))
        await self.settle()
        self.assertEqual(rig.snapshots.watches['camera.yard'].ahead_at - clock.now, 5 - picture_sources.AHEAD_MARGIN)

    async def test_a_camera_that_fails_is_asked_again_after_a_pause(self):
        rig, clock = self.feed([ConnectionError('500'), ConnectionError('500'), picture('JPEG', (640, 360))])
        token = rig.recipe(rig.read({'entity': 'camera.woonkamer_live'}))
        with self.assertLogs(picture_sources.LOG, 'INFO'):
            self.assertEqual((await rig.links.serve(token))[0], 503)
            self.assertEqual((await rig.links.serve(token))[0], 503)
            await self.settle()
            self.assertEqual(len(self.fetched), 1, 'no second try within the pause')
            clock.now += 5
            self.assertEqual((await rig.links.serve(token))[0], 503)
            await self.settle()
            self.assertEqual(len(self.fetched), 2)
            clock.now += 10
            self.assertEqual((await rig.links.serve(token))[0], 200)
            await self.settle()
        self.assertEqual(len(self.fetched), 3, 'the good picture; the next one waits for its moment')
        self.assertTrue(self.sleeps, 'a fetch ahead is set')

    async def test_a_camera_without_a_picture_is_answered_without_a_link(self):
        # A question is answered with what there is: a camera with no snapshot gets an empty link and no link is kept;
        # the screen asks again later (camera_view::ASK_AGAIN_MS).
        rig, clock = self.feed([ConnectionError('500')])
        with self.assertLogs(picture_sources.LOG, 'INFO'):
            found = await rig.answer(rig.read({'entity': 'camera.max'}))
        self.assertEqual((found.url, found.shown, found.problem), ('', ('',), ''))
        self.assertEqual(rig.links.links, {})

    async def test_an_alert_gets_a_snapshot_of_its_own_moment(self):
        first, second = picture('JPEG', (640, 360)), picture('PNG', (640, 360))
        rig, clock = self.feed([first, second])
        _, digest_first = await rig.snapshots.still('camera.front_door')
        await self.settle()
        self.assertEqual(len(self.fetched), 1)
        clock.now += 20
        # The bell rings 20 s later: the kept snapshot is not the moment, a new fetch is. The alert measures that one
        # (Manager.alert_images) and its pictures are made from it, fetched once.
        self.assertEqual(await rig.snapshots.size('camera.front_door'), (640, 360))
        _, digest_alert = await rig.snapshots.still('camera.front_door')
        await self.settle()
        self.assertEqual(len(self.fetched), 2)
        self.assertNotEqual(digest_alert, digest_first)

    async def test_an_alert_whose_camera_fails_gets_no_old_picture(self):
        rig, clock = self.feed([picture('JPEG', (640, 360)), ConnectionError('offline')])
        await rig.snapshots.still('camera.front_door')
        clock.now += 20
        with self.assertLogs(picture_sources.LOG, 'INFO'):
            self.assertIsNone(await rig.snapshots.still('camera.front_door', now=True))
        self.assertIsNone(await rig.snapshots.size('camera.front_door'))

    async def test_a_camera_nobody_loads_is_forgotten(self):
        rig, clock = self.feed([picture('JPEG', (64, 36))])
        await rig.snapshots.still('camera.max')
        self.assertIn('camera.max', rig.snapshots.watches)
        clock.now += picture_sources.WATCH_SECONDS + 1
        rig.snapshots.watch('camera.garden')
        self.assertNotIn('camera.max', rig.snapshots.watches)

    async def test_a_still_is_one_fixed_image(self):
        rig, _ = self.feed([RuntimeError('never asked')])
        bmp = still(picture('JPEG', (640, 360)), (392, 220))
        token = rig.links.add(still=bmp)
        status, body, etag, kind = await rig.links.serve(token)
        self.assertEqual((status, body, kind), (200, bmp, 'image/bmp'))
        self.assertEqual((await rig.links.serve(token, etag))[0], 304)
        self.assertEqual(self.fetched, [])
        # It stays loadable a while (an alert's picture), longer than a link that paints again.
        self.assertGreater(picture_links.STILL_SECONDS, picture_links.LINK_SECONDS)

    async def test_the_number_of_links_is_bounded(self):
        rig, clock = self.feed([picture('JPEG', (64, 36))])
        question = rig.read({'entity': 'camera.max'})
        tokens = []
        for _ in range(picture_links.MAX_LINKS + 10):
            clock.now += 0.01
            tokens.append(rig.recipe(question))
        self.assertLessEqual(len(rig.links.links), picture_links.MAX_LINKS)
        self.assertNotIn(tokens[0], rig.links)
        self.assertIn(tokens[-1], rig.links)
        self.assertTrue(all(re.fullmatch(r'[A-Za-z0-9_-]{24}', token) for token in tokens))

    @unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
    async def test_the_http_port(self):
        from aiohttp.test_utils import TestClient, TestServer
        from PIL import Image
        rig, _ = self.feed([picture('JPEG', (1920, 1080))])
        token = await rig.token(rig.read({'entity': 'camera.max'}))
        # A baseline JPEG for a screen whose decoder takes one (the ESP32-P4's), at its own suffix.
        jpeg = rig.links.add(still=picture_paint.encode(Image.new('RGB', (8, 8)), 'jpeg'), suffix='jpg')
        async with TestClient(TestServer(picture_links.web_app(rig.links))) as client:
            response = await client.get(f'/camera/{token}.bmp')
            body = await response.read()
            self.assertEqual((response.status, response.content_type, int(response.headers['Content-Length'])), (200, 'image/bmp', len(body)))
            etag = response.headers['ETag']
            self.assertEqual((await client.get(f'/camera/{token}.bmp', headers={'If-None-Match': etag})).status, 304)
            self.assertEqual((await client.get('/camera/abcdefghijklmnopqrstuvwx.bmp')).status, 404)
            self.assertEqual((await client.get('/api/inventory')).status, 404)
            self.assertEqual((await client.post(f'/camera/{token}.bmp')).status, 405)
            response = await client.get(f'/camera/{jpeg}.jpg')
            self.assertEqual((response.status, response.content_type), (200, 'image/jpeg'))
            # No stream without a stream source behind the port.
            self.assertEqual((await client.get(f'/camera/{token}.mjpeg')).status, 404)


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
        lan_address.base_url.__defaults__[0].clear()

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
            # A still made once, for the 16:9 frame of this firmware's alert card (392 x 220): the picture whole in it.
            self.assertIsNotNone(m.links.links[token].still)
            status, body, _, kind = await m.links.serve(token)
            self.assertEqual((status, kind), (200, 'image/bmp'))
            from PIL import Image
            with Image.open(io.BytesIO(body)) as served:
                self.assertEqual(served.size, (391, 220))
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
            board = pq.SHAPES['guition']
            card = alert_layout.layout(480, 480, board['alert']['title_line'], board['alert']['line'], True, board['dpi'],
                                       board['look'], 1080, 1440)
            status, body, _, _ = await m.links.serve(token)
            self.assertEqual(status, 200)
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
                status, body, etag, _ = await m.links.serve(url.rsplit('/', 1)[1][:-4])
                self.assertEqual(status, 200)
                from PIL import Image
                with Image.open(io.BytesIO(body)) as image:
                    served[inbox] = image.size
            self.assertEqual(served['text.d3_tiles'], (165, 220), 'older firmware gets it fitted in its 16:9 frame')
            self.assertLess(served['text.d1_tiles'][0], served['text.d1_tiles'][1], 'the new firmware gets a standing picture')
            # Each size painted once (the service keeps a painted picture by what it shows), both from one snapshot.
            painted = [key for key in m.pictures.kept if key[2][0].startswith('camera:camera.front_door:')]
            self.assertEqual(len(painted), 2)
            self.assertEqual(len({key[2] for key in painted}), 1, 'both made from the same snapshot')
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
            # A link that paints the camera again at every load, at the glass's box, the picture at its own proportions.
            question = m.links.links[token].recipe.question
            self.assertEqual((question.box, question.places[0].fit, question.sources), ((480, 480), 'shrink', (Source('camera', 'camera.max'),)))
            status, body, _, _ = await m.links.serve(token)
            from PIL import Image
            with Image.open(io.BytesIO(body)) as served:
                self.assertEqual((status, served.size), (200, (480, 270)))
            ha.log.clear()
            # A CYD, an old Guition, a light, a screen that is not there: no answer at all.
            for request in ({'inbox': 'text.d2_tiles', 'entity': 'camera.max'},
                            {'inbox': 'text.d3_tiles', 'entity': 'camera.max'}, {'inbox': 'text.d1_tiles', 'entity': 'light.hall'},
                            {'inbox': 'text.unknown', 'entity': 'camera.max'}, 'nonsense'):
                await m.answer_camera(request)
            self.assertEqual([entry for entry in ha.log if entry[0] in ('send', 'fetch')], [])
            # A camera that is not on its layout: refused, an answer without a link (the screen stops asking for a while).
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'entity': 'camera.garden'})
            self.assertEqual([entry[2] for entry in ha.log if entry[0] == 'send'],
                             [{'v': 1, 'op': 'camera', 't': 'full', 'e': 'camera.garden', 'u': ''}])
            self.assertNotIn(('fetch', 'camera.garden'), ha.log)

    async def test_a_screen_asks_a_question(self):
        # Firmware with the feature `pictures` asks for every picture in one shape (`q`, with its number `n`), and gets
        # the message every picture came in, with `t` "q" and that number (docs/PICTURES.md, "The question").
        import json
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (1920, 1080)))
            ha.states['sensor.d1_fw']['state'] = '0.60.0'
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Hall', 'tiles': [
                {'entity': 'camera.max', 'name': '', 'options': {'display': 'live', 'size': 'square'}},
                {'entity': 'camera.shed', 'name': ''}]}))
            q = {'o': 'tile', 'i': 0, 'src': 'tile:0', 'box': [236, 236], 'at': [[0, 0, 236, 236, 18, 0]], 'bg': '101010',
                 'fmt': ['bmp8', 'bmp24']}
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'q': json.dumps(q), 'n': '7'})
            (_, inbox, message), = [entry for entry in ha.log if entry[0] == 'send']
            self.assertEqual((inbox, message['op'], message['t'], message['n'], message['e']), ('text.d1_tiles', 'camera', 'q', 7, ''))
            status, raw, _, _ = await m.links.serve(message['u'].rsplit('/', 1)[1][:-4])
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual((status, image.size, image.mode), (200, (236, 236), 'P'))
            # A question that cannot be read, or without its number, gets no answer; one for a tile that shows no picture
            # is refused, with an answer without a link.
            ha.log.clear()
            for request in ({'q': 'nope', 'n': '8'}, {'q': json.dumps(q)}, {'q': json.dumps(q), 'n': 'x'},
                            {'q': json.dumps({**q, 'o': 'stranger'}), 'n': '8'}):
                await m.answer_camera({'inbox': 'text.d1_tiles', **request})
            self.assertEqual([entry for entry in ha.log if entry[0] == 'send'], [])
            await m.answer_camera({'inbox': 'text.d1_tiles', 'q': json.dumps({**q, 'i': 1, 'src': 'tile:1'}), 'n': '9'})
            (_, _, message), = [entry for entry in ha.log if entry[0] == 'send']
            self.assertEqual((message['t'], message['n'], message['u']), ('q', 9, ''))

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
    """A live camera that fills its card (1x2 and 2x2 from app 0.3.8 and firmware 0.3.3, every size from app 0.3.13 and
    firmware 0.3.7): fill or contain, name or nothing."""

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
        # (fit, fade) of a tile's picture: a camera's own choices where its firmware fills the card with it, else filled
        # and plain (picture_sources.camera_modes, what the source tells the painter).
        options = {'camera.front_door': {'display': 'live', 'size': 'tall', 'fit': 'contain'},
                   'camera.garden': {'display': 'live', 'size': 'square', 'overlay': 'none'},
                   'camera.hall': {'display': 'live'},
                   'media_player.sonos': {'display': 'cover', 'size': 'tall'}}
        modes = lambda firmware, of=options.get: [picture_sources.camera_modes(screen_firmware({'firmware': firmware}), of(entity))
                                                  for entity in options]
        self.assertEqual(modes('0.3.3'), [('contain', True), ('cover', False), ('cover', False), ('cover', False)])
        # Firmware that draws a small square on a taller camera tile gets that square, as before.
        self.assertEqual(modes('0.3.1'), [('cover', False)] * 4)
        # From firmware 0.3.7 a camera fills its card on every size, so the single tile gets its picture made for that.
        self.assertEqual(modes('0.3.7'), [('contain', True), ('cover', False), ('cover', True), ('cover', False)])
        # One camera on two tiles with choices of their own (firmware 0.16.0+): each place its own tile's.
        copies = [{'display': 'live', 'fit': 'contain'}, {'display': 'live', 'overlay': 'none'}]
        self.assertEqual([picture_sources.camera_modes((0, 16, 0), copy) for copy in copies], [('contain', True), ('cover', False)])
        self.assertEqual(picture_sources.camera_modes(None, copies[0]), ('cover', False), 'firmware unknown: filled and plain')

    def test_a_live_tile_may_refresh_every_5_to_30_seconds(self):
        tile = lambda options: validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.front_door', 'name': '', 'options': options}]})['tiles'][0]['options']
        for seconds in (5, 10, 15, 30):
            self.assertEqual(tile({'display': 'live', 'refresh': seconds})['refresh'], seconds)
        for seconds in (1, 4, 20, 60, '10'):
            with self.assertRaises(ValueError, msg=seconds):
                tile({'display': 'live', 'refresh': seconds})

    def test_new_screens_get_their_live_pictures_in_8_bit_colour(self):
        import io, json
        from PIL import Image
        self.assertEqual(pq.formats({'firmware': '0.3.3'}), ('bmp8', 'bmp24'))
        self.assertEqual(pq.formats({'firmware': '0.3.1'}), ('bmp24',))
        source = Image.new('RGB', (1280, 720))
        for x in range(1280):
            source.paste((x % 256, (x * 3) % 256, 200), (x, 0, x + 1, 720))
        raw = io.BytesIO(); source.save(raw, 'JPEG')
        atlas = picture_legacy.frames(json.dumps([[0, 0, 448, 228, 12, 0]]), (480, 480), 1)
        question = Question(Owner('tile', 0), (Source('tile', '0'),), atlas[:2],
                            tuple(Place(*frame, 'cover', 0xE7E7E7, fade=True) for frame in atlas[2]))
        wide = picture_paint.paint(question, [raw.getvalue()], 'bmp24')
        small = picture_paint.paint(question, [raw.getvalue()], 'bmp8')
        # The BMP header says 24 and 8 bits per pixel, and the 8-bit one is about a third of the bytes.
        self.assertEqual((int.from_bytes(wide[28:30], 'little'), int.from_bytes(small[28:30], 'little')), (24, 8))
        self.assertLess(len(small), len(wide) * 0.36)
        with Image.open(io.BytesIO(small)) as image:
            self.assertEqual((image.size, image.mode), ((448, 228), 'P'))
        # An older screen's strip asks in the formats of its firmware, and a new one's comes in 8 bits.
        strip = picture_legacy.read({'tiles': 'camera.a', 'idx': '0', 'size': '54', 'bg': 'FFFFFF'}, {'board': 'guition', 'firmware': '0.3.3'})
        self.assertEqual(strip.question.format, 'bmp8')
        self.assertEqual(int.from_bytes(picture_paint.paint(strip.question, [raw.getvalue()])[28:30], 'little'), 8)
        older = picture_legacy.read({'tiles': 'camera.a', 'idx': '0', 'size': '54', 'bg': 'FFFFFF'}, {'board': 'guition', 'firmware': '0.3.1'})
        self.assertEqual(older.question.formats, ('bmp24',))

    def test_contain_keeps_the_whole_picture_on_black_and_the_name_gets_its_shade(self):
        import io
        from PIL import Image, ImageDraw
        source = Image.new('RGB', (1280, 720), (240, 240, 240))
        ImageDraw.Draw(source).rectangle([0, 0, 1279, 719], outline=(255, 0, 0), width=12)
        raw = io.BytesIO(); source.save(raw, 'PNG')
        atlas = picture_legacy.frames('[[0,0,200,300,0,0],[200,0,200,300,0,0]]', (480, 480), 2)
        places = (Place(*atlas[2][0], 'contain', 0xE7E7E7), Place(*atlas[2][1], 'cover', 0xE7E7E7, fade=True))
        out = picture_paint.paint(Question(Owner('tile', 0), (Source('tile', '0'), Source('tile', '1')), atlas[:2], places),
                                  [raw.getvalue()] * 2, 'bmp24')
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
        from core import LIVE_MIN_FIRMWARE, LIVE_REFRESH, LIVE_REFRESH_DEFAULT
        import catalogue
        import live_stream
        # A tile's pace when it names none is the catalogue's default, the same for a still and a stream.
        self.assertEqual((picture_sources.TILE_PACE, live_stream.DEFAULT_PACE), (LIVE_REFRESH_DEFAULT, LIVE_REFRESH_DEFAULT))
        self.assertEqual(LIVE_REFRESH, tuple(catalogue.of_type('camera')['picture']['refresh']))
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

    def test_pictures_load_while_the_tiles_are_seen(self):
        """GitHub #161 (firmware 0.40.0): a dimmed screen without a screensaver still shows its tiles, so their pictures
        keep loading there. The rule itself is camera_view::tiles_seen (tests/test_camera_view.cpp); the firmware asks
        it everywhere a picture on the tiles loads, and the backlight goes by the same standby level."""
        waiting = TILES.split('inline bool tile_picture_waiting(const Widgets &w, const Tile &t) {', 1)[1].split('\n}', 1)[0]
        self.assertIn('!tiles_seen()', waiting)
        # A picture on the glass (a tile's own, a cover over a whole page) follows the tiles; one fetched ahead for a page
        # that is not shown waits for a screen in use.
        tiles = TILES.split('inline void card_picture_wants() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('const bool seen = tiles_seen() && !card_open() && !camera_root;', tiles)
        self.assertIn('const bool ahead = awake() && pictures_kept() && !prepare_busy() && pictures.size() < pictures.budget / 4 * 3;', tiles)
        page = tiles
        card = TILES.split('inline void card_cover_want() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('!tiles_seen()', card)
        self.assertNotIn('if (!awake()) return;', page + tiles + card)
        # Any screensaver covers the tiles, the clock (saver_root) as much as a camera or a cover (saver_camera).
        self.assertIn('camera_view::tiles_seen(awake(), saver_root || saver_camera, standby_level())', TILES)
        core = (ROOT / 'packages/core.yaml').read_text()
        self.assertIn('const int level = id(display_dimmed) ? runtime_tiles::standby_level() : settings.brightness;', core)
        self.assertNotIn('dim_level(', core)

    def test_a_media_tile_may_show_its_cover_in_the_icons_place(self):
        from core import COVER_TILE_MIN_FIRMWARE, resolve_controls
        import ha_catalogue
        layout = validate_layout({'title': 'Hall', 'tiles': [{'entity': 'media_player.sonos', 'name': '', 'options': {'display': 'cover', 'size': 'wide'}}]})
        self.assertEqual(min_firmware(layout), COVER_TILE_MIN_FIRMWARE)
        # The cover is the standard layout with a picture: a wide tile keeps its controls.
        self.assertEqual(resolve_controls(layout['tiles'][0]), 'volume')
        self.assertIn('cover', ha_catalogue.capabilities('media_player.sonos', [], {}, {})['displays'])
        with self.assertRaises(ValueError):
            validate_layout({'title': 'Hall', 'tiles': [{'entity': 'camera.front_door', 'name': '', 'options': {'display': 'cover'}}]})
        # A media player may be asked for in the strip; the request keeps its shape: a square per tile, its own ground.
        found = picture_legacy.read({'tiles': 'camera.front_door,media_player.sonos', 'size': '54', 'bg': 'FFFFFF,FFFFFF'},
                                    {'board': 'guition', 'firmware': '0.2.78'}, {'camera.front_door': 0, 'media_player.sonos': 1}.get)
        self.assertEqual((found.kind, found.entity), ('live', 'camera.front_door,media_player.sonos'))
        self.assertEqual([(s.kind, s.ref, s.param('entity')) for s in found.question.sources],
                         [('tile', '0', 'camera.front_door'), ('tile', '1', 'media_player.sonos')])
        self.assertEqual((found.question.box, [p.ground for p in found.question.places]), ((54, 108), [0xFFFFFF, 0xFFFFFF]))

    def test_which_screens_draw_live_pictures(self):
        # One question for every board that draws pictures: a screen's firmware asks only for what it draws (a strip
        # from 0.2.77), so the app asks no version of its own beyond the first that draws pictures at all.
        self.assertTrue(pq.draws_pictures({'board': 'guition', 'firmware': '0.2.77'}))
        self.assertTrue(pq.draws_pictures({'board': 'guition', 'firmware': '0.2.76'}))
        for screen in ({'board': 'guition', 'firmware': '0.2.56'}, {'board': 'cyd', 'firmware': '0.2.77'}, None):
            self.assertFalse(pq.draws_pictures(screen), screen)

    def test_the_request_names_the_tiles_their_size_and_their_grounds(self):
        guition = {'board': 'guition', 'firmware': '0.2.77'}
        index_of = {'camera.front_door': 0, 'image.doorbell': 1, 'camera.a': 2}.get

        def read(request):
            found = picture_legacy.read(request, guition, index_of)
            if found is None:
                return None
            q = found.question
            return [s.param('entity') for s in q.sources], q.box, [p.ground for p in q.places], [(p.x, p.y, p.w, p.h, p.radius) for p in q.places]
        self.assertEqual(read({'tiles': 'camera.front_door,image.doorbell', 'size': '54', 'bg': 'FFFFFF,fadadd'}),
                         (['camera.front_door', 'image.doorbell'], (54, 108), [0xFFFFFF, 0xFADADD],
                          [(0, 0, 54, 54, 9), (0, 54, 54, 54, 9)]))
        # One camera on two tiles of a page (firmware 0.16.0+, by index): a square each, in the list's order.
        self.assertEqual(read({'tiles': 'camera.a,camera.a', 'idx': '2,5', 'size': '54', 'bg': 'FFFFFF,fadadd'})[:3],
                         (['camera.a', 'camera.a'], (54, 108), [0xFFFFFF, 0xFADADD]))
        for bad in ({'tiles': 'camera.a', 'size': '54'}, {'tiles': 'camera.a,light.b', 'size': '54', 'bg': 'FFFFFF,FFFFFF'},
                    {'tiles': 'camera.a', 'size': '54', 'bg': 'FFFFFF,FFFFFF'},
                    {'tiles': 'camera.a', 'size': '8', 'bg': 'FFFFFF'}, {'tiles': 'camera.a', 'size': 'x', 'bg': 'FFFFFF'},
                    {'tiles': ','.join(f'camera.c{i}' for i in range(7)), 'size': '54', 'bg': ','.join(['FFFFFF'] * 7)}, {'tiles': '', 'size': '54', 'bg': ''},
                    # A tile the layout does not have as a pictured tile, by entity (before 0.16.0) or by a wrong index.
                    {'tiles': 'camera.other', 'size': '54', 'bg': 'FFFFFF'}, {'tiles': 'camera.a,camera.a', 'idx': '1', 'size': '54', 'bg': 'FFFFFF,FFFFFF'}):
            self.assertIsNone(read(bad), bad)

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_the_strip_is_one_square_per_tile_with_rounded_corners_over_its_own_ground(self):
        from PIL import Image
        found = picture_legacy.read({'tiles': 'camera.a,camera.b,image.c', 'idx': '0,1,2', 'size': '54', 'bg': 'FFFFFF,1A1A1A,00FF00'},
                                    {'board': 'guition', 'firmware': '0.2.77'})
        out = picture_paint.paint(found.question, [picture('JPEG', (1920, 1080)), None, picture('PNG', (100, 100), 'RGBA')])
        with Image.open(io.BytesIO(out)) as image:
            self.assertEqual((image.format, image.size, image.mode), ('BMP', (54, 162), 'RGB'))
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))     # the first square's corner: its ground
            self.assertEqual(image.getpixel((27, 27))[::2], (200, 90))    # its middle: the picture (JPEG, a shade off)
            self.assertEqual(image.getpixel((27, 54 + 27)), (26, 26, 26))  # no picture: a plain square of its ground
            self.assertEqual(image.getpixel((0, 108)), (0, 255, 0))       # the third square's corner: its ground

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_each_load_fetches_the_cameras_whose_pace_has_passed(self):
        fetched = []
        clock = Clock()

        async def fetch(entity):
            fetched.append((entity, clock.now))
            return picture('JPEG', (640, 360))

        async def never(delay):
            await asyncio.Event().wait()  # no fetch ahead in this test: only the loads fetch

        async def run(firmware):
            fetched.clear()
            clock.now = 1000.0
            rig = Rig(fetch, clock=clock, sleep=never, firmware=firmware, tiles=[
                {'entity': 'camera.a', 'name': '', 'options': {'display': 'live'}},
                {'entity': 'camera.b', 'name': '', 'options': {'display': 'live', 'refresh': 30}}])
            token = await rig.token(rig.read({'tiles': 'camera.a,camera.b', 'idx': '0,1', 'size': '54', 'bg': 'FFFFFF,FFFFFF'}))
            self.assertEqual(sorted(e for e, _ in fetched), ['camera.a', 'camera.b'], 'the first load waits for both')
            status, body, etag, _ = await rig.links.serve(token)
            self.assertEqual(status, 200)
            # 15 s later the page loads again: only the 15 s camera is fetched again.
            clock.now += 15
            again = await rig.links.serve(token, etag)
            self.assertEqual([e for e, at in fetched if at == 1015.0], ['camera.a'])
            clock.now += 15
            await rig.links.serve(token, etag)
            self.assertEqual(sorted(e for e, at in fetched if at == 1030.0), ['camera.a', 'camera.b'])
            # Nobody loading means nothing fetched.
            clock.now += 60
            self.assertEqual(len([e for e, at in fetched if at > 1030.0]), 0)
            return again, etag
        # The strip of firmware before 0.49.0 comes whole each time, never a 304, whatever ETag the screen offers:
        # ESPHome's http_request logged a 304 as an error (seen on the bench Guition with a radar camera).
        again, etag = asyncio.run(run('0.3.3'))
        self.assertEqual((again[0], again[2] == etag), (200, True))
        # A screen that downloads beside its main loop (picture_fetch, 0.49.0+) reads a 304: an unchanged picture is
        # not sent again.
        again, etag = asyncio.run(run('0.52.0'))
        self.assertEqual(again, (304, None, etag, 'image/bmp'))

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_a_media_tile_in_the_strip_is_fetched_once_per_picture(self):
        clock = Clock()
        fetched, pictures = [], {'media_player.sonos': '/api/media_player_proxy/media_player.sonos?token=a&cache=1'}

        async def fetch(entity):
            fetched.append((entity, clock.now))
            return picture('JPEG', (640, 360))

        async def fetch_cover(entity):
            fetched.append((entity, clock.now))
            return picture('PNG', (300, 300))

        async def never(delay):
            await asyncio.Event().wait()

        async def run():
            rig = Rig(fetch, clock=clock, sleep=never, fetch_cover=fetch_cover, picture=lambda e: pictures.get(e, ''), firmware='0.3.1', tiles=[
                {'entity': 'camera.a', 'name': '', 'options': {'display': 'live'}},
                {'entity': 'media_player.sonos', 'name': '', 'options': {'display': 'cover'}},
                {'entity': 'media_player.radio', 'name': '', 'options': {'display': 'cover'}}])
            question = rig.read({'tiles': 'camera.a,media_player.sonos,media_player.radio', 'idx': '0,1,2', 'size': '54',
                                 'bg': 'FFFFFF,FFFFFF,FFFFFF'})
            found = await rig.answer(question)
            self.assertEqual(found.shown, ('camera.a', 'media_player.sonos', ''), 'the answer names the tiles with a picture')
            token = found.url.rsplit('/', 1)[1][:-4]
            status, body, etag, _ = await rig.links.serve(token)
            self.assertEqual(status, 200)
            from PIL import Image
            with Image.open(io.BytesIO(body)) as image:
                self.assertEqual(image.size, (54, 162))
                self.assertEqual(image.getpixel((27, 54 + 27))[::2], (200, 90), 'the cover in the second square')
                self.assertEqual(image.getpixel((27, 108 + 27)), (255, 255, 255), 'a radio without a picture: a plain square')
            # Every 15 s the camera again, the cover not: its address did not change.
            for _ in range(3):
                clock.now += 15
                await rig.links.serve(token)
            self.assertEqual(len([e for e, _ in fetched if e == 'media_player.sonos']), 1)
            self.assertEqual(len([e for e, _ in fetched if e == 'camera.a']), 4)
            # A new track: another address, fetched at the next load.
            pictures['media_player.sonos'] = '/api/media_player_proxy/media_player.sonos?token=a&cache=2'
            clock.now += 15
            await rig.links.serve(token)
            self.assertEqual(len([e for e, _ in fetched if e == 'media_player.sonos']), 2)
        asyncio.run(run())


@unittest.skipUnless(HAS_AIOHTTP and HAS_PIL, 'Run using .venv-portal/bin/python for server tests')
class LiveApp(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        lan_address.base_url.__defaults__[0].clear()

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
            # A link that paints the strip again at each load: the page's tiles of those cameras (firmware before 0.16.0
            # names them by entity), a square each on its own ground, in 24 bits for this firmware.
            question = m.links.links[token].recipe.question
            self.assertEqual([(s.kind, s.ref, s.param('entity')) for s in question.sources],
                             [('tile', '0', 'camera.max'), ('tile', '1', 'camera.garden')])
            self.assertEqual((question.box, [p.ground for p in question.places], question.formats), ((54, 108), [0xFFFFFF, 0xFADADD], ('bmp24',)))
            # Each camera is fetched ahead at its own tile's pace: the default 15 s, and 30 s.
            now = time.monotonic()
            self.assertAlmostEqual(m.snapshots.watches['camera.max'].ahead_at - now, 15 - picture_sources.AHEAD_MARGIN, delta=1)
            self.assertAlmostEqual(m.snapshots.watches['camera.garden'].ahead_at - now, 30 - picture_sources.AHEAD_MARGIN, delta=1)
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
            # A cover has no pace: its picture is fetched when its address changes, and nothing is fetched ahead for it.
            now = time.monotonic()
            self.assertAlmostEqual(m.snapshots.watches['camera.max'].ahead_at - now, 15 - picture_sources.AHEAD_MARGIN, delta=1)
            self.assertIsNone(m.snapshots.watches['media_player.sonos'].ahead, 'a cover has no pace')
            ha.log.clear()
            # A media tile that shows its icon is not in the strip.
            await m.answer_camera({'inbox': 'text.d1_tiles', 'tiles': 'camera.max,media_player.tv', 'size': '54', 'bg': 'FFFFFF,FFFFFF'})
            self.assertEqual([entry for entry in ha.log if entry[0] == 'send'], [])

    async def test_a_screen_asks_for_each_tiles_picture_alone(self):
        """GitHub #183: a screen asks for every tile's picture on its own, as a page of one tile with one frame at the
        top left (tile_picture.h), so a new album cover sends no camera again and no picture is made smaller for another
        one on the page. The answer carries the question's number, which is how the screen finds the tile."""
        from PIL import Image
        import json
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (1920, 1080)))
            ha.states['sensor.d1_fw']['state'] = '0.51.0'
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Hall', 'tiles': [
                {'entity': 'camera.max', 'name': '', 'options': {'display': 'live', 'size': 'square', 'refresh': 5}},
                {'entity': 'camera.max', 'name': '', 'options': {'display': 'live', 'size': 'square', 'fit': 'contain'}},
                {'entity': 'media_player.sonos', 'name': '', 'options': {'display': 'cover', 'size': 'wide'}}]}))
            sent = []
            for index, (entity, frame) in enumerate([('camera.max', [0, 0, 236, 236, 18, 0]),
                                                     ('camera.max', [0, 0, 236, 236, 18, 0]),
                                                     ('media_player.sonos', [0, 0, 236, 112, 18, 170])]):
                ha.log.clear()
                await m.answer_camera({'inbox': 'text.d1_tiles', 'tiles': entity, 'idx': str(index), 'size': '54',
                                       'bg': '101010', 'dark': '1', 'view': str(40 + index), 'atlas': json.dumps([frame])})
                (_, _, message), = [entry for entry in ha.log if entry[0] == 'send']
                self.assertEqual((message['t'], message['e']), ('live', entity))
                token = message['u'].rsplit('/', 1)[1][:-4]
                status, raw, _, _ = await m.links.serve(token)
                self.assertEqual(status, 200)
                with Image.open(io.BytesIO(raw)) as image:
                    sent.append(image.convert('RGB'))
                    self.assertEqual(image.size, (frame[2], frame[3]), 'the frame exactly, whatever else the page holds')
            # A camera is fetched at the pace of its quickest tile (5 s); each tile loads at its own (the screen's rhythm),
            # and a cover has none.
            now = time.monotonic()
            self.assertAlmostEqual(m.snapshots.watches['camera.max'].ahead_at - now, 5 - picture_sources.AHEAD_MARGIN, delta=1)
            self.assertIsNone(m.snapshots.watches['media_player.sonos'].ahead)
            # Each tile is prepared as its own settings say: the same camera filled on one tile, whole on the other.
            self.assertNotEqual(sent[0].getpixel((118, 2)), sent[1].getpixel((118, 2)))
            # Every tile's last picture is kept for the load after its answer, one per place.
            self.assertEqual(len(m.pictures.kept), 3)

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
            status, raw, tag, _ = await m.links.serve(token)
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
            self.assertEqual(len(m.pictures.kept), 1)
            # Even a paired device cannot request images outside its native canvas.
            ha.log.clear()
            for bad in ('not json', '[[0,0,481,480,0,170]]', '[[0,0,220,220,0,170],[20,20,54,54,0,0]]'):
                await m.answer_camera({**request, 'atlas': bad})
            await m.answer_camera({**request, 'tiles': 'media_player.other,media_player.sonos'})
            self.assertEqual([entry for entry in ha.log if entry[0] == 'send'], [])

    async def test_each_copy_of_a_camera_gets_its_own_fit(self):
        # One camera on two pages and twice on one (firmware 0.16.0+, GitHub #83): the screen names each square's tile by
        # its index (`idx`), and each is made the way that tile asks.
        import json
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (900, 600)))
            ha.states['sensor.d1_fw']['state'] = '0.16.0'
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Hall', 'tiles': [
                {'entity': 'camera.max', 'name': '', 'slot': 0, 'options': {'display': 'live', 'fit': 'contain'}},
                {'entity': 'camera.max', 'name': '', 'slot': 6, 'options': {'display': 'live', 'overlay': 'none'}},
                {'entity': 'camera.max', 'name': '', 'slot': 7, 'options': {'display': 'live', 'fit': 'contain', 'overlay': 'none'}},
                {'entity': 'camera.max', 'name': '', 'slot': 12, 'options': {'display': 'live', 'fit': 'contain'}}]}))
            async def ask(tiles, frames, idx=None):
                ha.log.clear()
                request = {'inbox': 'text.d1_tiles', 'tiles': tiles, 'size': '54', 'bg': ','.join(['FFFFFF'] * len(tiles.split(','))),
                           'atlas': json.dumps(frames), **({'idx': idx} if idx is not None else {})}
                with self.assertLogs('screen_manager', 'INFO'):
                    await m.answer_camera(request)
                sent = [entry[2] for entry in ha.log if entry[0] == 'send']
                if not sent or not sent[0]['u']:
                    return None
                # How each place was painted: the last picture the service painted (or used again) for this answer.
                painted = next(reversed(m.pictures.kept))
                return [(place.fit, place.fade) for place in painted[1]]
            one, two = [[0, 0, 220, 140, 20, 0]], [[0, 0, 220, 140, 20, 0], [240, 0, 220, 140, 20, 0]]
            self.assertEqual(await ask('camera.max', one, '0'), [('contain', True)])
            self.assertEqual(await ask('camera.max,camera.max', two, '1,2'), [('cover', False), ('contain', False)])
            self.assertEqual(await ask('camera.max', one, '3'), [('contain', True)])
            # A screen without indexes (older firmware has an entity once) gets the entity's first live tile.
            self.assertEqual(await ask('camera.max,camera.max', two), [('contain', True), ('contain', True)])
            # An index that is not a pictured tile of that camera gets no picture: refused, an answer without a link.
            self.assertIsNone(await ask('camera.max', one, '9'))
            self.assertEqual([entry[2]['u'] for entry in ha.log if entry[0] == 'send'], [''])
            # Without an atlas two copies on one page are two squares of one strip.
            ha.log.clear()
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'tiles': 'camera.max,camera.max', 'idx': '1,2', 'size': '54', 'bg': 'FFFFFF,FADADD'})
            (_, _, message), = [entry for entry in ha.log if entry[0] == 'send']
            self.assertEqual(message['e'], 'camera.max,camera.max')
            screen = m.screen('text.d1_tiles')
            for idx in ('1,x', '1'):
                self.assertIsNone(picture_legacy.read({'tiles': 'camera.max,camera.max', 'idx': idx, 'size': '54', 'bg': 'FFFFFF,FFFFFF'}, screen), idx)

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
            self.assertIn(': none', logs.output[-1])


@unittest.skipUnless(HAS_AIOHTTP, 'aiohttp')
class PublishedPort(unittest.IsolatedAsyncioTestCase):
    """GitHub #84: an owner who publishes 8098 as 8099 on Home Assistant OS gets links on 8099."""

    def setUp(self):
        lan_address.base_url.__defaults__[0].clear()

    async def base(self, info, env):
        from unittest import mock

        class Response:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *exc):
                return False
            async def json(self):
                if isinstance(info, Exception):
                    raise info
                return info

        class Session:
            def __init__(self, *a, **k):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *exc):
                return False
            def get(self, url, **kwargs):
                assert url == 'http://supervisor/addons/self/info'
                return Response()

        async def request(kind, **data):
            return {'adapters': [{'default': True, 'ipv4': [{'address': '192.168.1.5'}]}]}

        with mock.patch.dict('os.environ', env, clear=True), mock.patch('aiohttp.ClientSession', Session):
            return await lan_address.base_url(request)

    async def test_the_link_carries_the_port_the_supervisor_published(self):
        info = {'result': 'ok', 'data': {'network': {'8098/tcp': 8099}}}
        self.assertEqual(await self.base(info, {'SUPERVISOR_TOKEN': 't'}), 'http://192.168.1.5:8099')

    async def test_8098_when_the_supervisor_says_nothing_usable(self):
        for info in ({'data': {'network': {'8098/tcp': None}}}, {'data': {}}, ConnectionError('x')):
            lan_address.base_url.__defaults__[0].clear()
            self.assertEqual(await self.base(info, {'SUPERVISOR_TOKEN': 't'}), 'http://192.168.1.5:8098')

    async def test_docker_keeps_its_own_setting(self):
        info = {'data': {'network': {'8098/tcp': 8099}}}
        self.assertEqual(await self.base(info, {}), 'http://192.168.1.5:8098')
        lan_address.base_url.__defaults__[0].clear()
        self.assertEqual(await self.base(info, {'SUPERVISOR_TOKEN': 't', 'SCREEN_CAMERA_PORT': '9000'}), 'http://192.168.1.5:9000')

    async def test_the_last_address_stands_while_home_assistant_does_not_say(self):
        """Discussion 105: the address is asked for again every ten minutes. A Home Assistant that did not answer that
        once gave a page's pictures an answer without a link, and a page of maps then stayed without its maps."""
        from unittest import mock
        self.assertEqual(await self.base({'data': {}}, {}), 'http://192.168.1.5:8098')

        async def silent(kind, **data):
            raise TimeoutError()

        with mock.patch.dict('os.environ', {}, clear=True), mock.patch('time.monotonic', return_value=time.monotonic() + 601):
            self.assertEqual(await lan_address.base_url(silent), 'http://192.168.1.5:8098')
        # Without an address from before there is none to give.
        lan_address.base_url.__defaults__[0].clear()
        with mock.patch.dict('os.environ', {}, clear=True):
            self.assertIsNone(await lan_address.base_url(silent))


class TwoNetworks(unittest.IsolatedAsyncioTestCase):
    """GitHub #276: a Home Assistant on two networks gave every screen its address on the default one, which a screen on
    the other network cannot reach, so it got no pictures. Each screen now gets the address on its own network."""

    ADAPTERS = {'adapters': [
        {'name': 'eth0', 'default': True, 'ipv4': [{'address': '192.168.1.5', 'network_prefix': 24}]},
        {'name': 'eth1', 'default': False, 'ipv4': [{'address': '10.0.50.2', 'network_prefix': 24}]},
        {'name': 'hassio', 'default': False, 'ipv4': [{'address': '172.30.32.1', 'network_prefix': 23}]}]}

    async def asyncSetUp(self):
        lan_address.base_url.__defaults__[0].clear()
        self.addCleanup(lan_address.base_url.__defaults__[0].clear)

    async def base(self, near, adapters=None, env=None):
        from unittest import mock

        async def request(kind, **data):
            return adapters or self.ADAPTERS
        with mock.patch.dict('os.environ', env or {}, clear=True):
            return await lan_address.base_url(request, near=near)

    async def test_each_screen_gets_the_address_on_its_own_network(self):
        self.assertEqual(await self.base('10.0.50.33'), 'http://10.0.50.2:8098')
        self.assertEqual(await self.base('192.168.1.40'), 'http://192.168.1.5:8098')

    async def test_a_screen_on_none_of_them_or_unknown_keeps_the_default(self):
        for near in ('10.9.0.7', None, '', 'not an address', 'fe80::1'):
            with self.subTest(near=near):
                self.assertEqual(await self.base(near), 'http://192.168.1.5:8098')

    async def test_an_adapter_without_a_prefix_is_never_matched(self):
        adapters = {'adapters': [{'default': True, 'ipv4': [{'address': '192.168.1.5'}]},
                                 {'default': False, 'ipv4': [{'address': '10.0.50.2'}]}]}
        self.assertEqual(await self.base('10.0.50.33', adapters), 'http://192.168.1.5:8098')

    async def test_the_setting_of_its_own_still_wins(self):
        self.assertEqual(await self.base('10.0.50.33', env={'SCREEN_CAMERA_URL': 'http://pictures:9000/'}), 'http://pictures:9000')

    async def test_the_manager_asks_for_the_screens_own_network(self):
        import server
        asked = []

        async def base_url(request, *args, near=None):
            asked.append(near)
            return 'http://x:8098'
        from unittest import mock
        manager = type('M', (), {'ha': type('HA', (), {'request': None})()})()
        with mock.patch.object(lan_address, 'base_url', base_url):
            await server.Manager.link_base(manager, {'ip': '10.0.50.33'})
            await server.Manager.link_base(manager, None)
        self.assertEqual(asked, ['10.0.50.33', None])


if __name__ == '__main__':
    unittest.main()
