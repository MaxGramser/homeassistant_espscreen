"""A map on a person tile (app 0.4.33, firmware 0.20.0, docs/MAP.md): the app reads Home Assistant's vector tiles, draws
the card in the screen's own colours and sends it in the page's picture strip; the screen gets pixels, never a place."""
from manager_fixtures import with_screen_grid, seed_layout
import asyncio
import gzip
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import camera_feed  # noqa: E402
import map_card  # noqa: E402
import map_tiles  # noqa: E402
import vector_tiles  # noqa: E402
from core import MAP_OPTIONS, min_firmware, screen_options, extras, validate_layout  # noqa: E402

HAS_PIL = importlib.util.find_spec('PIL') is not None
HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None


# ----- A vector tile, written the way the specification says, so the reader is tested against the format -----

def varint(n):
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def field(number, wire, payload):
    key = varint(number << 3 | wire)
    return key + (varint(len(payload)) + payload if wire == 2 else varint(payload))


def zigzag(n):
    return (n << 1) ^ (n >> 31)


def commands(parts, close):
    out, x, y = [], 0, 0
    for part in parts:
        out.append(1 | 1 << 3)
        out += [zigzag(part[0][0] - x), zigzag(part[0][1] - y)]
        x, y = part[0]
        rest = part[1:]
        out.append(2 | len(rest) << 3)
        for px, py in rest:
            out += [zigzag(px - x), zigzag(py - y)]
            x, y = px, py
        if close:
            out.append(7 | 1 << 3)
    return out


def layer(name, features, extent=4096):
    """features: (geometry type, {key: string value}, parts)"""
    keys, values, body = [], [], b''
    for kind, tags, parts in features:
        tag_ids = []
        for key, value in tags.items():
            if key not in keys:
                keys.append(key)
            if value not in values:
                values.append(value)
            tag_ids += [keys.index(key), values.index(value)]
        packed = lambda items: b''.join(varint(i) for i in items)
        feature = field(2, 2, packed(tag_ids)) + field(3, 0, kind) + field(4, 2, packed(commands(parts, kind == 3)))
        body += field(2, 2, feature)
    body += b''.join(field(3, 2, key.encode()) for key in keys)
    body += b''.join(field(4, 2, field(1, 2, value.encode())) for value in values)
    return field(3, 2, field(15, 0, 2) + field(1, 2, name.encode()) + body + field(5, 0, extent))


SQUARE = [(0, 0), (4096, 0), (4096, 4096), (0, 4096)]
TILE = (layer('water_polygons', [(3, {'kind': 'water'}, [[(1000, 1000), (3000, 1000), (3000, 3000), (1000, 3000)]])]) +
        layer('streets', [(2, {'kind': 'primary'}, [[(0, 2048), (4096, 2048)]]),
                          (2, {'kind': 'footway'}, [[(2048, 0), (2048, 4096)]])]) +
        layer('addresses', [(1, {'housenumber': '12'}, [[(10, 10)]])]))


class VectorTiles(unittest.TestCase):
    def test_reads_the_layers_it_is_asked_for_gzipped_or_not(self):
        for raw in (TILE, gzip.compress(TILE)):
            tile = vector_tiles.decode(raw, map_card.LAYERS)
            self.assertEqual(sorted(tile), ['streets', 'water_polygons'], 'a layer the card does not draw is skipped')
            extent, streets = tile['streets']
            self.assertEqual(extent, 4096)
            self.assertEqual([f.tags['kind'] for f in streets], ['primary', 'footway'])
            self.assertEqual(streets[0].parts, [[(0, 2048), (4096, 2048)]])
            water, = tile['water_polygons'][1]
            self.assertEqual(water.kind, vector_tiles.POLYGON)
            self.assertEqual(water.parts[0][0], water.parts[0][-1], 'a closed ring ends where it starts')

    def test_refuses_what_is_not_a_tile(self):
        with self.assertRaises(Exception):
            vector_tiles.decode(b'\x1a\xff\xff\xff\xff\x0f')


# ----- What the card shows -----

def zone(entity, name, lat, lon, radius, **extra):
    return entity, {'state': '0', 'attributes': {'friendly_name': name, 'latitude': lat, 'longitude': lon, 'radius': radius, **extra}}


def person(entity, name, state, lat=None, lon=None):
    attributes = {'friendly_name': name}
    if lat is not None:
        attributes.update(latitude=lat, longitude=lon, gps_accuracy=10)
    return entity, {'state': state, 'attributes': attributes}


STATES = dict([
    zone('zone.home', 'Home', 52.3587, 4.8682, 90),
    zone('zone.office', 'Office', 52.3760, 4.8978, 140),
    zone('zone.away', 'Away', 40.0, -3.0, 500, passive=True),
    person('person.alex', 'Alex Morgan', 'home', 52.35878, 4.86835),
    person('person.sam', 'Sam', 'Office', 52.37590, 4.89800),
    person('person.jo', 'Jo', 'unknown'),
    person('device_tracker.car', 'Car', 'not_home', 52.3700, 4.8900),
    person('device_tracker.router_phone', 'Phone on the router', 'home'),
])


class Card(unittest.TestCase):
    def test_zones_and_people(self):
        zones = map_card.zones_of(STATES)
        self.assertEqual([z.entity for z in zones], ['zone.home', 'zone.office'], 'home first; a passive zone is no place')
        # Colours in the order Home Assistant made the entities, the home zone apart (entity-map-colors.ts).
        registry = {e: {'entity_id': e, 'created_at': n} for n, e in enumerate(['zone.home', 'person.sam', 'zone.office', 'person.alex'])}
        alex, sam, jo = map_card.people_of(['person.alex', 'person.sam', 'person.jo'], STATES, registry)
        self.assertEqual((sam.colour, alex.colour), (0, 2))
        self.assertEqual(jo.colour, map_card.colour_of('person.jo', {}), 'without an entry: the hash Home Assistant falls back on')
        self.assertFalse(jo.placed)
        self.assertEqual(map_card.zone_of(alex, zones).entity, 'zone.home')
        # Initials as Home Assistant's map writes them: the first letter of each word, at most three.
        self.assertEqual(map_card.initials('Alex Morgan'), 'AM')
        self.assertEqual(map_card.initials('sam'), 's')
        self.assertEqual(map_card.initials('Anne Marie de Vries'), 'AMd')

    def test_where_home_assistant_puts_someone(self):
        # A person without a place of their own but in a zone stands in its middle (get_entity_location.ts).
        states = {**STATES, 'person.jo': {'state': 'Office', 'attributes': {'friendly_name': 'Jo', 'in_zones': ['zone.away', 'zone.office']}}}
        self.assertEqual(map_card.locate('person.jo', states), (52.3760, 4.8978, 0.0, True), 'the first zone that is on the map')
        self.assertIsNone(map_card.locate('device_tracker.router_phone', states))
        self.assertEqual(map_card.locate('device_tracker.car', states)[:2], (52.37, 4.89))

    def test_everyone_is_home_assistants_show_all(self):
        states = {**STATES, 'person.sam': {**STATES['person.sam'], 'attributes': {**STATES['person.sam']['attributes'], 'source': 'device_tracker.car'}},
                  'device_tracker.tag': person('device_tracker.tag', 'Bag tag', 'not_home', 52.36, 4.88)[1]}
        registry = {'device_tracker.tag': {'entity_id': 'device_tracker.tag', 'hidden_by': 'user'}}
        # People first, then trackers; not the car Sam already follows, not the hidden tag, not who has no place.
        self.assertEqual(map_card.everyone(states, registry), ['person.alex', 'person.sam'])
        self.assertEqual(map_card.everyone(states), ['person.alex', 'person.sam', 'device_tracker.tag'])

    def test_everyone_stays_inside_the_card_clear_of_its_name(self):
        people = map_card.people_of(['person.alex', 'person.sam'], STATES)
        zones = map_card.zones_of(STATES)
        for size in ((218, 118), (448, 248), (448, 400)):
            view = map_card.frame_view('everyone', 'neighbourhood', people, zones, size, people[0], (16, 44))
            for p in people:
                x, y = view.point(p.lat, p.lon)
                self.assertTrue(0 <= x <= size[0] and 16 <= y <= size[1] - 44, (size, p.name, x, y))

    def test_fixed_views_sit_on_home_or_on_the_person(self):
        people = map_card.people_of(['person.sam', 'person.alex'], STATES)
        zones = map_card.zones_of(STATES)
        home = map_card.frame_view('home', 'street', people, zones, (300, 200))
        self.assertEqual((round(home.lat, 4), round(home.lon, 4)), (52.3587, 4.8682))
        self.assertEqual(home.zoom, map_card.DISTANCES['street'])
        own = map_card.frame_view('person', 'town', people, zones, (300, 200), people[0])
        self.assertEqual((own.lat, own.lon, own.zoom), (people[0].lat, people[0].lon, map_card.DISTANCES['town']))
        # Nobody placed: the card sits on home.
        nobody = map_card.people_of(['person.jo'], STATES)
        self.assertEqual(map_card.frame_view('everyone', 'town', nobody, zones, (300, 200)).lat, 52.3587)

    def test_a_view_asks_for_the_tiles_under_it_at_zoom_14_at_most(self):
        view = map_card.View(52.3587, 4.8682, 16.5, (448, 400))
        tiles = view.tiles()
        self.assertTrue(tiles and all(z == 14 for z, _, _ in tiles))
        self.assertLessEqual(len(tiles), 4)
        self.assertEqual(map_card.View(52.3587, 4.8682, 12.3, (448, 400)).tile_zoom, 12)

    def test_the_screens_keys_zoom_round_the_middle_and_move_it(self):
        self.assertEqual(map_card.move_of('1,12.50,-3.00'), (1, 12.5, -3.0))
        self.assertEqual(map_card.move_of('40,0,0'), (map_card.MOVE_ZOOM_STEPS[1], 0.0, 0.0))
        for word in (None, '', 'x', '1,2', '1,nan,0', '1,inf,0'):
            self.assertIsNone(map_card.move_of(word))
        view = map_card.View(52.37, 4.89, 14.0, (480, 320))
        middle = lambda v: (v.left + v.width / 2, v.top + v.height / 2)
        closer = map_card.moved(view, (1, 0.0, 0.0))
        self.assertEqual(closer.zoom, 15.0)
        self.assertAlmostEqual(middle(closer)[0], middle(view)[0] * 2, places=6)
        # A move is in pixels of the framed zoom: the same place at every zoom.
        aside = map_card.moved(view, (0, 59.0, -20.0))
        self.assertAlmostEqual(aside.left - view.left, 59.0, places=6)
        self.assertAlmostEqual(aside.top - view.top, -20.0, places=6)
        both = map_card.moved(view, (2, 59.0, -20.0))
        self.assertAlmostEqual(middle(both)[0], middle(aside)[0] * 4, places=6)
        self.assertIs(map_card.moved(view, None), view)

    def test_the_mark_follows_moves_not_drift(self):
        tile = {'entity': 'person.alex', 'name': '', 'options': {'display': 'map', 'map': ['person.sam']}}
        mark = map_card.fingerprint(tile, STATES)
        self.assertRegex(mark, r'^[0-9a-f]{12}$')
        self.assertNotIn('52', mark.replace(mark, ''), 'no place in the mark')
        moved = dict(STATES)
        moved['person.sam'] = person('person.sam', 'Sam', 'Office', 52.37591, 4.89801)[1]
        self.assertEqual(map_card.fingerprint(tile, moved), mark, 'a metre of drift is no new picture')
        moved['person.sam'] = person('person.sam', 'Sam', 'not_home', 52.3659, 4.8831)[1]
        self.assertNotEqual(map_card.fingerprint(tile, moved), mark)
        # The card's own choices and name are part of what it draws.
        for options in ({'framing': 'home'}, {'distance': 'street', 'framing': 'person'}, {'overlay': 'none'}):
            other = {**tile, 'options': {**tile['options'], **options}}
            self.assertNotEqual(map_card.fingerprint(other, STATES), mark, options)
        self.assertNotEqual(map_card.fingerprint({**tile, 'name': 'Family'}, STATES), mark)
        zones = dict(STATES)
        zones['zone.office'] = zone('zone.office', 'Office', 52.3760, 4.8978, 200)[1]
        self.assertNotEqual(map_card.fingerprint(tile, zones), mark, 'a zone drawn larger is a new picture')

    def test_the_add_on_carries_the_screens_font(self):
        # The add-on's image is built from screen_manager/ alone (0.4.33 crashed at start looking outside it).
        for name in ('Roboto-400.ttf', 'Roboto-500.ttf', 'Roboto-OFL.txt'):
            self.assertEqual((ROOT / 'screen_manager/app/fonts' / name).read_bytes(), (ROOT / 'fonts' / name).read_bytes(), name)
        self.assertEqual(map_card.FONT_DIRS, (ROOT / 'screen_manager/app/fonts',))

    def test_the_board_sizes_what_is_drawn(self):
        shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        guition, waveshare = map_card.Board(shapes['guition']), map_card.Board(shapes['waveshare43'])
        self.assertEqual((guition.scale, guition.label), (1.0, 18))
        self.assertGreater(waveshare.scale, 1.2)
        self.assertEqual(waveshare.label, shapes['waveshare43']['fonts']['label'])
        self.assertEqual(map_card.Board(None).label, 18)


@unittest.skipUnless(HAS_PIL, 'Pillow')
class Drawing(unittest.TestCase):
    def tile(self, **options):
        return {'entity': 'person.alex', 'name': 'Family', 'options': {'display': 'map', 'map': ['person.sam'], **options}}

    def test_a_card_is_exactly_its_frame_in_either_look(self):
        board = map_card.Board(None)
        tile = self.tile()
        view = map_card.view_for(tile, STATES, (218, 118), board)
        streets = {key: vector_tiles.decode(TILE, map_card.LAYERS) for key in view.tiles()}
        light = map_card.render_tile(tile, STATES, (218, 118), board, False, streets)
        dark = map_card.render_tile(tile, STATES, (218, 118), board, True, streets)
        self.assertEqual((light.size, dark.size, light.mode), ((218, 118), (218, 118), 'RGB'))
        # The ground is the screen's own: light land in the light look, dark in the dark one.
        self.assertGreater(sum(light.getpixel((5, 60))), 600)
        self.assertLess(sum(dark.getpixel((5, 60))), 150)
        # The name's pill in the card's colour at the bottom left.
        self.assertEqual(light.getpixel((14, 118 - 8 - 14)), (255, 255, 255))

    def test_markers_sit_on_their_place_and_a_focused_one_exactly(self):
        people = map_card.people_of(['person.alex', 'device_tracker.car', 'person.sam'], STATES)
        # Far enough apart on the glass: each exactly on its coordinate.
        view = map_card.View(52.3675, 4.884, 13.5, (480, 480))
        hits = []
        map_card.draw_people(map_card.Canvas((480, 480), (0, 0, 0)), view, people, map_card.LIGHT, 1.0, 30, hits=hits)
        for entity, x, y, _ in hits:
            p = next(p for p in people if p.entity == entity)
            self.assertLessEqual(max(abs(x - view.point(p.lat, p.lon)[0]), abs(y - view.point(p.lat, p.lon)[1])), 0.5, entity)
        # On a small card they would cover each other: fanned out, each still to be seen. Opened on one, that one is
        # exactly on its coordinate whoever lies on it.
        # (The upper half: the lower one lies under the focused one's card.)
        small = map_card.View(52.345, 4.884, 11.5, (300, 300))
        for focus in ('person.sam', 'device_tracker.car'):
            hits = []
            map_card.draw_people(map_card.Canvas((300, 300), (0, 0, 0)), small, people, map_card.LIGHT, 1.0, 30, focus=focus, hits=hits)
            x, y = next((h[1], h[2]) for h in hits if h[0] == focus)
            p = next(p for p in people if p.entity == focus)
            ex, ey = small.point(p.lat, p.lon)
            self.assertLessEqual(max(abs(x - ex), abs(y - ey)), 0.5, focus)
            spots = [(h[1], h[2]) for h in hits]
            self.assertEqual(len(set(spots)), len(spots), 'no two markers on one spot')

    def test_a_photo_in_the_marker(self):
        from PIL import Image
        board = map_card.Board(None)
        tile = {'entity': 'person.alex', 'name': '', 'options': {'display': 'map', 'overlay': 'none'}}
        photo = Image.new('RGB', (64, 64), (200, 30, 90))
        with_photo = map_card.render_tile(tile, STATES, (220, 140), board, False, {}, None, {'person.alex': photo})
        plain = map_card.render_tile(tile, STATES, (220, 140), board, False, {}, None, {})
        # The marker sits in the middle of a single person's card.
        self.assertGreater(with_photo.getpixel((110, 70))[0], 150)
        self.assertLess(abs(with_photo.getpixel((110, 70))[1] - 30), 40)
        self.assertNotEqual(with_photo.getpixel((110, 70)), plain.getpixel((110, 70)))

    def test_without_streets_or_a_name_it_still_draws(self):
        board = map_card.Board(None)
        image = map_card.render_tile(self.tile(overlay='none'), STATES, (160, 100), board, False, {})
        self.assertEqual(image.size, (160, 100))
        nobody = {'entity': 'person.jo', 'name': '', 'options': {'display': 'map'}}
        self.assertEqual(map_card.render_tile(nobody, STATES, (160, 100), board, True, {}).size, (160, 100))


# ----- What is saved, and what a screen gets -----

class Layout(unittest.TestCase):
    def save(self, options, entity='person.alex'):
        return validate_layout({'title': 'Home', 'tiles': [{'entity': entity, 'name': '', 'options': options}]})['tiles'][0]

    def test_a_map_keeps_its_choices_and_no_defaults(self):
        tile = self.save({'display': 'map', 'map': ['person.sam'], 'framing': 'home', 'distance': 'street', 'overlay': 'none'})
        self.assertEqual(tile['options'], {'display': 'map', 'map': ['person.sam'], 'framing': 'home', 'distance': 'street', 'overlay': 'none'})
        tile = self.save({'display': 'map', 'map': [], 'framing': MAP_OPTIONS['framing'][0], 'distance': MAP_OPTIONS['distance'][0], 'overlay': 'name'})
        self.assertEqual(tile['options'], {'display': 'map'}, 'defaults and an empty list are not stored')
        # Another display drops what only a map keeps.
        self.assertEqual(self.save({'display': 'standard', 'map': ['person.sam'], 'framing': 'home'})['options'], {'display': 'standard'})
        self.assertEqual(min_firmware({'tiles': [tile]}), (0, 20, 0))

    def test_a_tracker_rides_along(self):
        # A phone, a car or a tag (app 0.4.35): any device tracker Home Assistant reports a place for.
        tile = self.save({'display': 'map', 'map': ['device_tracker.car', 'person.sam']})
        self.assertEqual(tile['options']['map'], ['device_tracker.car', 'person.sam'])
        self.assertEqual([item['id'] for item in map_card.trackers(STATES)], ['device_tracker.car'],
                         'a tracker that only knows home or away has no place to draw')
        mark = map_card.fingerprint(tile, STATES)
        moved = {**STATES, 'device_tracker.car': person('device_tracker.car', 'Car', 'not_home', 52.3800, 4.9000)[1]}
        self.assertNotEqual(map_card.fingerprint(tile, moved), mark, 'the car drove off: a new picture')

    def test_the_map_tile_follows_everyone_or_whom_it_lists(self):
        tile = self.save({'framing': 'home', 'look': 'dark', 'markers': 'initials'}, entity='screen.map')
        self.assertEqual(tile['options'], {'display': 'map', 'framing': 'home', 'look': 'dark', 'markers': 'initials'})
        self.assertEqual(min_firmware({'tiles': [tile]}), (0, 21, 0))
        self.assertEqual(map_card.shown(tile, STATES), ['person.alex', 'person.sam', 'device_tracker.car'])
        chosen = self.save({'follow': 'chosen', 'map': ['device_tracker.car']}, entity='screen.map')
        self.assertEqual(map_card.shown(chosen, STATES), ['device_tracker.car'])
        self.assertEqual(len(self.save({'follow': 'chosen', 'map': [f'person.p{n}' for n in range(8)]}, entity='screen.map')['options']['map']), 8)
        # Chosen with nobody yet: a map of the zones until someone is added.
        self.assertEqual(map_card.shown(self.save({'follow': 'chosen'}, entity='screen.map'), STATES), [])
        # A person's map follows that person: no follow to choose.
        self.assertNotIn('follow', self.save({'display': 'map', 'follow': 'chosen', 'map': ['person.sam']})['options'])
        # The screen gets the map's mark with the built-in card.
        from core import state_message
        message = state_message(0, tile, STATES, extras(tile, STATES))
        self.assertEqual(message['o']['display'], 'map')
        self.assertEqual(list(message['x']), ['mk'])

    def test_how_a_map_looks_is_its_own(self):
        tile = self.save({'display': 'map', 'look': 'light', 'streets': 'hide', 'markers': 'initials', 'zones': 'hide', 'names': 'never'})
        self.assertFalse(map_card.dark_for(tile, True), 'a light card stays light on a dark screen')
        self.assertTrue(map_card.dark_for(self.save({'display': 'map'}), True))
        self.assertFalse(map_card.wants_streets(tile))
        self.assertEqual(map_card.pictures_wanted(tile, {**STATES, 'person.alex': {**STATES['person.alex'], 'attributes': {
            **STATES['person.alex']['attributes'], 'entity_picture': '/api/image/serve/abc/512x512'}}}), {})
        self.assertNotEqual(map_card.fingerprint(tile, STATES), map_card.fingerprint(self.save({'display': 'map'}), STATES))

    def test_who_rides_along_is_checked(self):
        for bad in ({'framing': 'nowhere'}, {'distance': 'moon'}, {'map': 'person.sam'}, {'map': ['person.alex']},
                    {'map': ['person.sam', 'person.sam']}, {'map': ['light.hall']}, {'map': [f'person.p{n}' for n in range(8)]}):
            with self.assertRaises(ValueError, msg=bad):
                self.save({'display': 'map', **bad})
        with self.assertRaises(ValueError):
            self.save({'display': 'map'}, entity='sensor.temperature')

    def test_the_screen_gets_the_mark_and_never_a_place(self):
        tile = self.save({'display': 'map', 'map': ['person.sam'], 'framing': 'home'})
        options = screen_options(tile, STATES['person.alex']['attributes'], 'home')
        self.assertEqual({k: v for k, v in options.items() if k != 'icon'}, {'display': 'map'})
        extra = extras(tile, STATES)
        self.assertEqual(list(extra), ['mk'])
        self.assertEqual(extra['mk'], map_card.fingerprint(tile, STATES))
        self.assertNotIn('52.', json.dumps([options, extra]))


# ----- The streets through Home Assistant -----

class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Source(unittest.IsolatedAsyncioTestCase):
    async def test_tiles_are_asked_once_and_kept(self):
        asked = []

        async def fetch(z, x, y):
            asked.append((z, x, y))
            return gzip.compress(TILE)
        source = map_tiles.TileSource(fetch, Clock())
        first = await source.tiles([(14, 8414, 5384), (14, 8415, 5384)])
        again = await source.tiles([(14, 8414, 5384)])
        self.assertEqual(len(first), 2)
        self.assertEqual(asked, [(14, 8414, 5384), (14, 8415, 5384)])
        self.assertIs(again[(14, 8414, 5384)], first[(14, 8414, 5384)])
        # A tile outside the map is never asked for.
        self.assertEqual(await source.tiles([(15, 0, 0), (14, -1, 0)]), {})
        self.assertEqual(len(asked), 2)

    async def test_a_home_assistant_without_tiles_is_left_alone_for_a_while(self):
        asked, clock = [], Clock()

        async def fetch(z, x, y):
            asked.append((z, x, y))
            raise ConnectionError('404')
        source = map_tiles.TileSource(fetch, clock)
        with self.assertLogs('map_tiles', 'INFO'):
            self.assertEqual(await source.tiles([(14, 1, 1)]), {})
        self.assertFalse(source.available())
        self.assertEqual(await source.tiles([(14, 1, 1)]), {})
        self.assertEqual(len(asked), 1)
        clock.now += map_tiles.COOLDOWN
        self.assertTrue(source.available())


@unittest.skipUnless(HAS_PIL and HAS_AIOHTTP, 'Pillow and aiohttp')
class Screens(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        camera_feed.base_url.__defaults__[0].clear()

    async def test_a_screen_gets_its_map_in_its_own_look(self):
        from test_camera import fake_ha, picture
        from server import Manager
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha(picture('JPEG', (900, 600)))
            ha.states.update(STATES)
            ha.states['sensor.d1_fw']['state'] = '0.20.0'
            ha.states['sensor.d3_fw']['state'] = '0.19.0'

            async def map_tile(z, x, y):
                ha.log.append(('tile', (z, x, y)))
                return TILE
            ha.map_tile = map_tile
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            layout = validate_layout({'title': 'Home', 'tiles': [
                {'entity': 'person.alex', 'name': 'Family', 'options': {'display': 'map', 'map': ['person.sam']}},
                {'entity': 'camera.max', 'name': '', 'options': {'display': 'live'}},
                {'entity': 'person.sam', 'name': ''}]})
            seed_layout(m, 'text.d1_tiles', layout)
            seed_layout(m, 'text.d3_tiles', layout)
            frames = json.dumps([[0, 0, 218, 118, 14, 0], [230, 0, 218, 118, 14, 0]])

            async def ask(dark, tiles='person.alex,camera.max', idx='0,1', inbox='text.d1_tiles'):
                ha.log.clear()
                await m.answer_camera({'inbox': inbox, 'tiles': tiles, 'idx': idx, 'size': '54', 'bg': ','.join(['E7E7E7'] * len(tiles.split(','))),
                                       'atlas': frames if ',' in tiles else json.dumps([[0, 0, 218, 118, 14, 0]]), 'dark': dark})
                sent = [entry[2] for entry in ha.log if entry[0] == 'send']
                if not sent or not sent[0]['u']:
                    return None
                status, raw, _ = await m.camera.serve(sent[0]['u'].rsplit('/', 1)[1][:-4])
                self.assertEqual((status, sent[0]['e']), (200, tiles))
                with Image.open(io.BytesIO(raw)) as image:
                    return image.convert('RGB')
            with self.assertLogs('screen_manager', 'INFO'):
                light = await ask('0')
            self.assertTrue(any(entry[0] == 'tile' for entry in ha.log), 'the streets come from Home Assistant')
            with self.assertLogs('screen_manager', 'INFO'):
                dark = await ask('1')
            self.assertEqual(light.size, (448, 118))
            self.assertGreater(sum(light.getpixel((6, 50))), 3 * sum(dark.getpixel((6, 50))), 'each look its own map')
            self.assertEqual(len(m.map_renders), 2, 'a map kept per look')
            # Asked again in the same look: drawn from what is kept, the streets not asked again.
            with self.assertLogs('screen_manager', 'INFO'):
                await ask('0')
            self.assertFalse(any(entry[0] == 'tile' for entry in ha.log))
            # A person on the page who is not a map tile, and a screen that cannot draw one yet: nothing.
            for tiles, idx, inbox in (('person.sam', '2', 'text.d1_tiles'), ('person.alex', '0', 'text.d3_tiles')):
                with self.assertLogs('screen_manager', 'INFO'):
                    self.assertIsNone(await ask('0', tiles, idx, inbox))

    async def test_a_markers_picture_comes_only_from_home_assistant_or_the_internet(self):
        from test_camera import RecordingSession
        from server import HomeAssistant
        session = RecordingSession()
        ha = HomeAssistant(session, 'http://ha/api', 'token')
        self.assertEqual(await ha.entity_picture('/api/image/serve/abc123/512x512'), b'picture')
        self.assertEqual(session.calls[-1], ('http://ha/api/image/serve/abc123/512x512', 'Bearer token', False))
        for bad in ('/api/states', '/api/image/serve/../../states', '//elsewhere/api/image/serve/x', 'http://127.0.0.1/me.jpg', 'file:///etc/passwd'):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, 'picture address'):
                await ha.entity_picture(bad)

    async def test_the_map_tile_on_a_screen(self):
        from test_camera import fake_ha, picture
        from server import Manager
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            ha.states.update(STATES)
            ha.states['person.alex']['attributes']['entity_picture'] = '/api/image/serve/alex/512x512'
            ha.states['sensor.d1_fw']['state'] = '0.21.0'

            async def map_tile(z, x, y):
                return TILE

            async def entity_picture(address):
                ha.log.append(('picture', address))
                return picture('PNG', (80, 80))
            ha.map_tile, ha.entity_picture = map_tile, entity_picture
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Home', 'tiles': [
                {'entity': 'screen.map', 'name': '', 'options': {'size': 'wide'}}]}))
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'tiles': 'screen.map', 'idx': '0', 'size': '54', 'bg': 'E7E7E7',
                                       'atlas': json.dumps([[0, 0, 448, 118, 14, 0]]), 'dark': '0'})
            sent = [entry[2] for entry in ha.log if entry[0] == 'send']
            self.assertEqual(sent[0]['e'], 'screen.map')
            self.assertIn(('picture', '/api/image/serve/alex/512x512'), ha.log, 'a photo in the marker, as Home Assistant shows it')
            status, raw, _ = await m.camera.serve(sent[0]['u'].rsplit('/', 1)[1][:-4])
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual((status, image.size), (200, (448, 118)))

    async def test_a_tap_opens_the_map_over_the_whole_glass(self):
        from test_camera import fake_ha
        from server import Manager
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            ha.states.update(STATES)
            ha.states['sensor.d1_fw']['state'] = '0.21.0'

            async def map_tile(z, x, y):
                return TILE
            ha.map_tile = map_tile
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Home', 'tiles': [
                {'entity': 'person.alex', 'name': 'Family', 'options': {'display': 'map', 'map': ['person.sam']}},
                {'entity': 'screen.map', 'name': '', 'options': {'follow': 'chosen', 'map': ['device_tracker.car']}}]}))
            for entity, idx in (('person.alex', '0'), ('screen.map', '1')):
                ha.log.clear()
                with self.assertLogs('screen_manager', 'INFO'):
                    await m.answer_camera({'inbox': 'text.d1_tiles', 'entity': entity, 'idx': idx, 'dark': '1'})
                message, = [entry[2] for entry in ha.log if entry[0] == 'send']
                self.assertEqual((message['t'], message['e']), ('full', entity))
                status, raw, _ = await m.camera.serve(message['u'].rsplit('/', 1)[1][:-4])
                with Image.open(io.BytesIO(raw)) as image:
                    # As large as the board takes a camera, in the screen's look: dark.
                    self.assertEqual((status, image.size), (200, camera_feed.box(m.screen('text.d1_tiles'), 'full')))
                    self.assertLess(sum(image.convert('RGB').getpixel((10, 240))), 150)
            # A finger on Sam (firmware 0.21.0+): Sam's card, as Home Assistant shows a selected person, and every marker's
            # place on the picture for the next finger. Pixels and words, never a place.
            import time as clock
            now = clock.time()

            async def state_changes(entity, hours):
                return [(now - 20000, 'home'), (now - 9000, 'not_home'), (now - 3600, 'unavailable'), (now - 1800, 'Office')]
            ha.state_changes = state_changes
            ha.log.clear()
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'entity': 'person.alex', 'idx': '0', 'focus': 'person.sam'})
            message, = [entry[2] for entry in ha.log if entry[0] == 'send']
            sheet = message['m']
            self.assertEqual(sheet['f'], 'person.sam')
            self.assertEqual({hit[0] for hit in sheet['h']} >= {'person.sam'}, True)
            self.assertEqual(sheet['c']['t'], 'Sam')
            # Rows as the effects page draws them: the state now, then the day's changes newest first (it began at home).
            self.assertEqual([row[1] for row in sheet['c']['r']], ['Office', 'Office', 'not_home'])
            self.assertTrue(all(len(row) == 3 and row[0] for row in sheet['c']['r']), 'an icon, a name, a value')
            self.assertNotIn('52.', json.dumps(sheet))
            # Someone who is not on that map is no focus.
            ha.log.clear()
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'entity': 'person.alex', 'idx': '0', 'focus': 'person.jo'})
            message, = [entry[2] for entry in ha.log if entry[0] == 'send']
            self.assertEqual((message['m']['f'], 'c' in message['m']), ('', False))
            # A person's own tile tapped (firmware 0.21.0+): that person's map, opened on them.
            seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Home', 'tiles': [{'entity': 'person.sam', 'name': ''}]}))
            ha.log.clear()
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'entity': 'person.sam', 'idx': '0', 'focus': 'person.sam'})
            message, = [entry[2] for entry in ha.log if entry[0] == 'send']
            self.assertEqual((message['t'], message['m']['f'], message['m']['c']['t']), ('full', 'person.sam', 'Sam'))
            # A person who has no map tile on the screen gets none.
            ha.log.clear()
            with self.assertLogs('screen_manager', 'INFO'):
                await m.answer_camera({'inbox': 'text.d1_tiles', 'entity': 'person.sam'})
            self.assertEqual([entry for entry in ha.log if entry[0] == 'send'], [])

    async def test_a_screen_without_pictures_cannot_save_a_map(self):
        from test_camera import fake_ha
        from server import Manager
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            ha.states.update(STATES)
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            with self.assertRaisesRegex(ValueError, 'map'):
                m.save('text.d2_tiles', {'title': 'Desk', 'tiles': [
                    {'entity': 'person.alex', 'name': '', 'options': {'display': 'map'}}]})


if __name__ == '__main__':
    unittest.main()
