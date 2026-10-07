"""A map card: where the people of a person tile are, drawn by the add-on as the card's picture.

The screen never sees a coordinate. The add-on reads the people and zones from Home Assistant, reads the streets from
Home Assistant's own vector tiles (vector_tiles.py) and draws the whole frame at exactly the size the screen asks for,
in the screen's own colours. The screen places that picture like a live camera's.

How the card frames its people (`framing`):
- `everyone`: the smallest view that holds everyone on the card with a place, and the zone each of them stands in.
- `home`: the home zone in the middle at a fixed distance. Who is outside the view is a small chip on its edge,
  pointing the way.
- `person`: the tile's own person in the middle at a fixed distance, the others as on `home`.

`distance` is how far a fixed view reaches: street, neighbourhood, town or region.

The look is calm on purpose: the streets are a quiet ground in the screen's greys, water and green a soft tint of the
screen's own palette, and the only strong colours on the card are the people and their zones.
"""
import math
import re
from pathlib import Path

TILE_PX = 256
# Home Assistant's proxy serves no vector tile past zoom 14; a closer view draws the zoom-14 tile larger, as MapLibre
# does. Vectors stay sharp at any scale, so this costs nothing but detail no card has room for anyway.
VECTOR_MAX_ZOOM = 14
MIN_ZOOM, MAX_ZOOM = 3.0, 17.5
MAX_LATITUDE = 85.05112878
EARTH_METRES = 6371000.0

FRAMINGS = ('everyone', 'home', 'person')
DISTANCES = {'street': 16.5, 'neighbourhood': 15.0, 'town': 13.0, 'region': 10.5}
DEFAULT_DISTANCE = 'neighbourhood'
# Room kept around everyone on `everyone`, as a share of the frame on each side.
FIT_PADDING = 0.14
# One person alone, or everyone on one spot, is shown at this distance: a fit around one point has no size.
SINGLE_ZOOM = 15.0

# The layers of Home Assistant's Shortbread tiles the card draws; every other layer is skipped while decoding.
LAYERS = frozenset(('ocean', 'water_polygons', 'water_lines', 'land', 'buildings', 'streets', 'place_labels'))


# ----- Where things are -----

def world(lat, lon, zoom):
    """Web Mercator pixels of a place at `zoom`, 256 per tile as every web map."""
    lat = max(-MAX_LATITUDE, min(MAX_LATITUDE, lat))
    size = TILE_PX * 2 ** zoom
    x = (lon + 180.0) / 360.0 * size
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * size
    return x, y


def metres_between(lat1, lon1, lat2, lon2):
    """Great-circle distance, good enough for zones and a scale."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_METRES * math.asin(min(1.0, math.sqrt(a)))


def metres_per_pixel(lat, zoom):
    return 2 * math.pi * EARTH_METRES * math.cos(math.radians(lat)) / (TILE_PX * 2 ** zoom)


class View:
    """What the frame shows: a middle, a zoom that need not be whole, and the frame's size in pixels."""

    def __init__(self, lat, lon, zoom, size):
        self.lat, self.lon = lat, lon
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self.width, self.height = size
        cx, cy = world(lat, lon, self.zoom)
        self.left, self.top = cx - self.width / 2.0, cy - self.height / 2.0

    def point(self, lat, lon):
        x, y = world(lat, lon, self.zoom)
        return x - self.left, y - self.top

    def inside(self, lat, lon, margin=0):
        x, y = self.point(lat, lon)
        return margin <= x <= self.width - margin and margin <= y <= self.height - margin

    @property
    def tile_zoom(self):
        return max(0, min(VECTOR_MAX_ZOOM, int(math.floor(self.zoom))))

    def tiles(self):
        """(zoom, x, y) of every vector tile under the frame."""
        tz = self.tile_zoom
        scale = 2 ** (self.zoom - tz)
        span = TILE_PX * scale
        count = 2 ** tz
        x0, x1 = int(math.floor(self.left / span)), int(math.floor((self.left + self.width) / span))
        y0, y1 = int(math.floor(self.top / span)), int(math.floor((self.top + self.height) / span))
        return [(tz, x % count, y) for y in range(max(0, y0), min(count - 1, y1) + 1) for x in range(x0, x1 + 1)]

    def tile_origin(self, tz, tx, ty):
        """Where tile (tz, tx, ty) starts on the frame, and how many frame pixels one tile pixel is."""
        scale = 2 ** (self.zoom - tz)
        span = TILE_PX * scale
        # A tile that wraps round the date line is drawn where the frame needs it.
        count = 2 ** tz
        column = tx
        while column * span + span < self.left:
            column += count
        while column * span > self.left + self.width:
            column -= count
        return column * span - self.left, ty * span - self.top, scale


# ----- Who and what is on the card -----

class Zone:
    __slots__ = ('entity', 'name', 'lat', 'lon', 'radius', 'icon', 'home')

    def __init__(self, entity, name, lat, lon, radius, icon=None):
        self.entity, self.name, self.lat, self.lon, self.radius, self.icon = entity, name, lat, lon, radius, icon
        self.home = entity == 'zone.home'


class Person:
    """Someone or something on the map: a person or a device tracker, where Home Assistant puts it (`locate`), with the
    colour Home Assistant gives it on every map and its picture when it has one."""
    __slots__ = ('entity', 'name', 'state', 'lat', 'lon', 'accuracy', 'colour', 'picture', 'zone_only')

    def __init__(self, entity, name, state, lat=None, lon=None, accuracy=0, colour=0, picture=None, zone_only=False):
        self.entity, self.name, self.state = entity, name, state
        self.lat, self.lon, self.accuracy, self.colour, self.picture = lat, lon, accuracy, colour, picture
        self.zone_only = zone_only

    @property
    def placed(self):
        return self.lat is not None and self.lon is not None


def zones_of(states):
    """The zones Home Assistant has a place for, the home zone first; a passive zone is no place on a map, as on Home
    Assistant's own (ha-map.ts draws one only when asked to)."""
    found = []
    for entity, state in states.items():
        if not isinstance(entity, str) or not entity.startswith('zone.'):
            continue
        a = (state or {}).get('attributes') or {}
        lat, lon = _number(a.get('latitude')), _number(a.get('longitude'))
        if lat is None or lon is None or a.get('passive'):
            continue
        found.append(Zone(entity, a.get('friendly_name') or entity.split('.', 1)[1], lat, lon,
                          _number(a.get('radius')) or 100.0, a.get('icon')))
    return sorted(found, key=lambda z: (not z.home, z.name))


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def locate(entity, states):
    """(lat, lon, accuracy, zone_only) as Home Assistant's frontend places an entity (get_entity_location.ts): its own
    latitude and longitude, else, for a person, the first zone of `in_zones` that is on the map; None without either."""
    state = states.get(entity) or {}
    a = state.get('attributes') or {}
    lat, lon = _number(a.get('latitude')), _number(a.get('longitude'))
    if lat is not None and lon is not None:
        return lat, lon, _number(a.get('gps_accuracy')) or 0.0, False
    if not entity.startswith('person.'):
        return None
    for zone in a.get('in_zones') or ():
        z = (states.get(zone) or {}).get('attributes') or {}
        zlat, zlon = _number(z.get('latitude')), _number(z.get('longitude'))
        if zlat is not None and zlon is not None and not z.get('passive'):
            return zlat, zlon, 0.0, True
    return None


COLOUR_DOMAINS = ('zone', 'person', 'device_tracker')


def colour_order(registry):
    """{entity: index} as Home Assistant hands out map colours (entity-map-colors.ts): zones, people and trackers in the
    order they were made, the home zone apart, so someone has the same colour on every map."""
    entries = [e for e in (registry or {}).values()
               if isinstance(e, dict) and str(e.get('entity_id', '')).split('.')[0] in COLOUR_DOMAINS
               and e.get('entity_id') != 'zone.home']
    entries.sort(key=lambda e: (float(e.get('created_at') or 0), str(e.get('id') or e['entity_id'])))
    return {e['entity_id']: n for n, e in enumerate(entries)}


def colour_of(entity, order):
    """An entity's colour slot: its place in Home Assistant's order, else the hash Home Assistant falls back on."""
    if entity in order:
        return order[entity]
    value = 5381
    for char in entity:
        value = (value * 33 + ord(char)) % 2147483647
    return value


def people_of(entities, states, registry=None):
    """The people and trackers on the card, in the card's order, each where Home Assistant puts it and in its colour."""
    order = colour_order(registry)
    out = []
    for entity in entities:
        state = states.get(entity) or {}
        a = state.get('attributes') or {}
        found = locate(entity, states)
        lat, lon, accuracy, zone_only = found if found else (None, None, 0.0, False)
        out.append(Person(entity, a.get('friendly_name') or entity.split('.', 1)[1], state.get('state'), lat, lon,
                          accuracy, colour_of(entity, order), a.get('entity_picture') or None, zone_only))
    return out


def everyone(states, registry=None):
    """Everyone Home Assistant knows the place of, as its map card's show_all (hui-map-card.ts): every person and every
    device tracker with a place, but not a tracker a person already follows (its `source`) or one hidden in the
    registry. People first, then trackers, each by name; at most EVERYONE_MAX."""
    registry = registry or {}
    sources = {(s.get('attributes') or {}).get('source') for e, s in states.items() if isinstance(e, str) and e.startswith('person.')}
    found = []
    for entity in states:
        if not isinstance(entity, str) or entity.split('.')[0] not in ('person', 'device_tracker'):
            continue
        if entity in sources or (registry.get(entity) or {}).get('hidden_by') or locate(entity, states) is None:
            continue
        name = ((states[entity] or {}).get('attributes') or {}).get('friendly_name') or entity
        found.append((not entity.startswith('person.'), str(name).lower(), entity))
    return [entity for _, _, entity in sorted(found)][:EVERYONE_MAX]


EVERYONE_MAX = 12


def trackers(states):
    """The device trackers that can ride along on a map (app 0.4.35): those Home Assistant reports a place for, a
    phone, a car or a tag, by name. A tracker that only knows home or away has no place to draw."""
    found = []
    for entity, state in states.items():
        if not isinstance(entity, str) or not entity.startswith('device_tracker.'):
            continue
        a = (state or {}).get('attributes') or {}
        if a.get('latitude') is None or a.get('longitude') is None:
            continue
        found.append({'id': entity, 'name': a.get('friendly_name') or entity.split('.', 1)[1], 'state': state.get('state')})
    return sorted(found, key=lambda item: item['name'].lower())


def home_of(zones):
    return next((z for z in zones if z.home), None)


def zone_of(person, zones):
    """The zone a person stands in, the smallest when zones overlap."""
    if not person.placed:
        return None
    inside = [z for z in zones if metres_between(z.lat, z.lon, person.lat, person.lon) <= z.radius]
    return min(inside, key=lambda z: z.radius) if inside else None


def fit(points, size, reserve=(0, 0), margin=0):
    """The middle and zoom that hold every (lat, lon) in `points` in a frame of `size`, clear of the `reserve`d
    pixels at its top and bottom (the attribution above, the tile's name below) and `margin` from every edge (half a
    marker, so a marker at the edge of the fit is whole)."""
    xs, ys = zip(*(world(lat, lon, 0) for lat, lon in points))
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    top, bottom = reserve[0] + margin, reserve[1] + margin
    width, height = max(1, size[0] - 2 * margin), max(1, size[1] - top - bottom)
    if x1 - x0 < 1e-9 and y1 - y0 < 1e-9:
        zoom = SINGLE_ZOOM
    else:
        zoom = min(math.log2(width * (1 - 2 * FIT_PADDING) / max(x1 - x0, 1e-12)),
                   math.log2(height * (1 - 2 * FIT_PADDING) / max(y1 - y0, 1e-12)))
        zoom = min(zoom, SINGLE_ZOOM + 1.5)
    # Back from world pixels at zoom 0 to a place.
    # The middle of the free band goes in the middle of that band, so the frame's middle moves by half the difference.
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2 + (bottom - top) / 2 / 2 ** zoom
    lon = mx / TILE_PX * 360.0 - 180.0
    n = math.pi - 2 * math.pi * my / TILE_PX
    lat = math.degrees(math.atan(math.sinh(n)))
    return lat, lon, zoom


def frame_view(framing, distance, people, zones, size, own=None, reserve=(0, 0), margin=0):
    """The view a card shows, and the people that fall outside it."""
    zoom = DISTANCES.get(distance, DISTANCES[DEFAULT_DISTANCE])
    placed = [p for p in people if p.placed]
    home = home_of(zones)
    if framing == 'home' and home:
        view = View(home.lat, home.lon, zoom, size)
    elif framing == 'person' and own is not None and own.placed:
        view = View(own.lat, own.lon, zoom, size)
    elif placed:
        points = [(p.lat, p.lon) for p in placed]
        # The zone someone stands in stays whole on the card, so its ring does not run off the edge.
        for p in placed:
            z = zone_of(p, zones)
            if z:
                d = z.radius / 111320.0
                w = d / max(0.01, math.cos(math.radians(z.lat)))
                points += [(z.lat + d, z.lon + w), (z.lat - d, z.lon - w)]
        lat, lon, fitted = fit(points, size, reserve, margin)
        view = View(lat, lon, fitted, size)
    elif home:
        view = View(home.lat, home.lon, zoom, size)
    else:
        view = View(0.0, 0.0, MIN_ZOOM, size)
    return view


# ----- The look -----
# The screen's own roles (components/smart_display/theme.h) where the card has one: the ground is PAGE_SOFT, the ink
# INK, the accent ACCENT, the halo CARD. The map's own tints (water, green, streets) are mixed from those, so light and
# dark stay one family with the rest of the screen.

def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _rgb(value):
    return ((value >> 16) & 255, (value >> 8) & 255, value & 255)


# The greys are pure (red, green and blue alike): the glass shows 16-bit colour (RGB565), which cuts red and blue to five
# bits and green to six, so a warm grey such as E8E7E4 comes out pink there; a pure grey stays grey.
LIGHT = {
    'land': 0xF2F2F2, 'green': 0xE1EDDF, 'water': 0xCFE3EE, 'water_line': 0xB9D6E6, 'building': 0xE6E6E6,
    'road': 0xFFFFFF, 'road_case': 0xDBDBDB, 'major': 0xFFFFFF, 'major_case': 0xCECECE, 'path': 0xE1E1E1,
    'rail': 0xCCCCCC, 'place': 0x898989, 'halo': 0xFFFFFF, 'ink': 0x1B1B1B, 'muted': 0x616161, 'card': 0xFFFFFF,
    'accent': 0x009FE3, 'zone_fill': 0x009FE3, 'zone_alpha': 30, 'zone_edge': 0x009FE3, 'shadow': 0x000000,
    'shadow_alpha': 60,
}
DARK = {
    'land': 0x1A1A1A, 'green': 0x1B251D, 'water': 0x0F2533, 'water_line': 0x0F2533, 'building': 0x1F1F1F,
    'road': 0x272727, 'road_case': 0x272727, 'major': 0x323232, 'major_case': 0x323232, 'path': 0x212121,
    'rail': 0x2A2A2A, 'place': 0x8A8A8A, 'halo': 0x1A1A1A, 'ink': 0xDADADA, 'muted': 0x999999, 'card': 0x1A1A1A,
    'accent': 0x0A93D2, 'zone_fill': 0x0A93D2, 'zone_alpha': 44, 'zone_edge': 0x2AA9E6, 'shadow': 0x000000,
    'shadow_alpha': 120,
}
# The people's colours, the tile palette's strong half (theme.h, the colour a tile paints its icon with), in the
# order Home Assistant hands out a map colour: the first person on the card is blue, the next orange, and so on.
PEOPLE = (0x009FE3, 0xEF7D14, 0x3C9A4A, 0x8E5CC9, 0xD9468F, 0x13897B, 0xD93A30, 0xC99A00)

# The widths of a street by kind, in pixels at a 170 dpi screen, at zoom 13, 15 and 17; between those they follow
# the zoom, as a real map's do. A kind absent from a zoom band is not drawn there.
STREETS = (
    # kinds, widths at (13, 15, 17), major (a darker edge)
    (('motorway', 'trunk'), (2.4, 5.0, 11.0), True),
    (('primary', 'secondary'), (1.8, 4.2, 10.0), True),
    (('tertiary',), (1.0, 3.2, 8.5), True),
    (('residential', 'unclassified', 'living_street'), (0.0, 2.0, 6.5), False),
    (('service', 'pedestrian'), (0.0, 0.9, 3.4), False),
)
PATHS = ('footway', 'cycleway', 'path', 'steps', 'track', 'bridleway')
RAILS = ('rail', 'light_rail', 'subway', 'narrow_gauge')
GREEN = frozenset(('park', 'forest', 'wood', 'grass', 'meadow', 'garden', 'village_green', 'recreation_ground',
                   'playground', 'cemetery', 'grave_yard', 'heath', 'scrub', 'grassland', 'nature_reserve',
                   'golf_course', 'allotments', 'orchard', 'vineyard', 'pitch'))
PLACES = {'capital': 11.0, 'state_capital': 11.0, 'city': 11.0, 'town': 12.5, 'village': 13.5, 'suburb': 13.5,
          'quarter': 14.5, 'neighbourhood': 15.5}

# The add-on's own copy of the screens' Roboto (screen_manager/app/fonts, the image is built from screen_manager/ alone;
# tests/test_map_card.py keeps it equal to fonts/), so a name on a map is in the face the screen writes names in.
FONT_DIRS = (Path(__file__).resolve().parent / 'fonts',)
_FONTS = {}


def font(size, weight=500):
    from PIL import ImageFont
    key = (round(size), weight)
    if key not in _FONTS:
        for folder in FONT_DIRS:
            path = folder / ('Roboto-%d.ttf' % weight)
            if path.exists():
                _FONTS[key] = ImageFont.truetype(str(path), key[0])
                break
        else:
            _FONTS[key] = ImageFont.load_default()
    return _FONTS[key]


def _width_at(widths, zoom):
    stops = (13.0, 15.0, 17.0)
    if zoom <= stops[0]:
        return widths[0] * 2 ** (zoom - stops[0]) if widths[0] else 0.0
    for i in range(2):
        if zoom <= stops[i + 1]:
            t = (zoom - stops[i]) / (stops[i + 1] - stops[i])
            a, b = widths[i], widths[i + 1]
            return a + (b - a) * t
    return widths[2] * 2 ** (zoom - stops[2])


# ----- Drawing -----

SUPERSAMPLE = 3


class Canvas:
    """A frame drawn three times as large and scaled down at the end: Pillow draws without anti-aliasing."""

    def __init__(self, size, colour):
        from PIL import Image
        self.width, self.height = size
        self.s = SUPERSAMPLE
        self.image = Image.new('RGB', (self.width * self.s, self.height * self.s), colour)

    def finish(self):
        from PIL import Image
        return self.image.resize((self.width, self.height), Image.Resampling.LANCZOS)


def _parts(view, tiles, layer):
    """(feature, [[(x, y) on the supersampled canvas]]) of one layer over every tile."""
    s = SUPERSAMPLE
    for (tz, tx, ty), decoded in tiles.items():
        if layer not in decoded:
            continue
        extent, features = decoded[layer]
        ox, oy, scale = view.tile_origin(tz, tx, ty)
        k = TILE_PX * scale / extent * s
        bx, by = ox * s, oy * s
        for feature in features:
            yield feature, [[(bx + x * k, by + y * k) for x, y in part] for part in feature.parts]


def _area(ring):
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))


def _fill(canvas, view, tiles, layer, colour, keep=None):
    """Every polygon of a layer in one colour: outer rings filled, holes cut, through one mask per layer."""
    from PIL import Image, ImageDraw
    mask = Image.new('L', canvas.image.size)
    draw = ImageDraw.Draw(mask)
    touched = False
    for feature, parts in _parts(view, tiles, layer):
        if feature.kind != 3 or (keep and not keep(feature)):
            continue
        # Outer rings wind one way and holes the other (a positive area here is an outer ring, y pointing down).
        for ring in parts:
            if len(ring) >= 3 and _area(ring) > 0:
                draw.polygon(ring, fill=255)
                touched = True
        for ring in parts:
            if len(ring) >= 3 and _area(ring) < 0:
                draw.polygon(ring, fill=0)
    if touched:
        canvas.image.paste(colour, mask=mask)


def _stroke(draw, parts, width):
    if width <= 0:
        return
    w = max(1, round(width))
    for line in parts:
        if len(line) >= 2:
            draw.line(line, fill=None, width=w, joint='curve')


def draw_basemap(canvas, view, tiles, look, dpi_scale=1.0):
    from PIL import ImageDraw
    s = SUPERSAMPLE
    zoom = view.zoom
    _fill(canvas, view, tiles, 'land', _rgb(look['green']), lambda f: f.tags.get('kind') in GREEN)
    _fill(canvas, view, tiles, 'ocean', _rgb(look['water']))
    _fill(canvas, view, tiles, 'water_polygons', _rgb(look['water']))
    draw = ImageDraw.Draw(canvas.image)
    # Rivers and canals too narrow to be a polygon.
    water_width = {'river': (1.2, 3.0, 7.0), 'canal': (0.0, 2.2, 5.0), 'stream': (0.0, 0.8, 2.0)}
    for kind, widths in water_width.items():
        w = _width_at(widths, zoom) * dpi_scale * s
        if w > 0.4 * s:
            parts = [p for f, ps in _parts(view, tiles, 'water_lines') if f.tags.get('kind') == kind for p in ps]
            draw = ImageDraw.Draw(canvas.image)
            for line in parts:
                if len(line) >= 2:
                    draw.line(line, fill=_rgb(look['water']), width=max(1, round(w)), joint='curve')
    if zoom >= 14.5:
        _fill(canvas, view, tiles, 'buildings', _rgb(look['building']))
    draw = ImageDraw.Draw(canvas.image)
    streets = [(f, ps) for f, ps in _parts(view, tiles, 'streets') if not f.tags.get('tunnel')]
    # Paths first and faint, then rail, then streets from small to large: casings of all, then the fills.
    if zoom >= 15.5:
        w = max(0.6, 0.35 * (zoom - 14)) * dpi_scale * s
        for f, ps in streets:
            if f.tags.get('kind') in PATHS:
                for line in ps:
                    if len(line) >= 2:
                        draw.line(line, fill=_rgb(look['path']), width=max(1, round(w)))
    if zoom >= 12:
        w = max(0.7, 0.3 * (zoom - 11)) * dpi_scale * s
        for f, ps in streets:
            if f.tags.get('kind') in RAILS and not f.tags.get('service'):
                for line in ps:
                    if len(line) >= 2:
                        draw.line(line, fill=_rgb(look['rail']), width=max(1, round(w)))
    layers = []
    for kinds, widths, major in reversed(STREETS):
        w = _width_at(widths, zoom) * dpi_scale
        if w < 0.5:
            continue
        parts = [p for f, ps in streets if f.tags.get('kind') in kinds for p in ps]
        layers.append((parts, w * s, major))
    edge = 1.0 * dpi_scale * s
    for parts, w, major in layers:
        colour = _rgb(look['major_case'] if major else look['road_case'])
        for line in parts:
            if len(line) >= 2:
                draw.line(line, fill=colour, width=max(1, round(w + 2 * edge)), joint='curve')
    for parts, w, major in layers:
        colour = _rgb(look['major'] if major else look['road'])
        for line in parts:
            if len(line) >= 2:
                draw.line(line, fill=colour, width=max(1, round(w)), joint='curve')


def draw_places(canvas, view, tiles, look, dpi_scale, avoid):
    """A few names of towns and quarters, quiet and never over a person or a zone."""
    from PIL import ImageDraw
    s = SUPERSAMPLE
    draw = ImageDraw.Draw(canvas.image)
    size = 11.5 * dpi_scale * s
    face = font(size, 500)
    taken = list(avoid)
    shown = 0
    candidates = []
    for f, parts in _parts(view, tiles, 'place_labels'):
        kind, name = f.tags.get('kind'), f.tags.get('name')
        if not name or kind not in PLACES or not parts or not parts[0]:
            continue
        # A kind reads at its own zooms: a city from afar, a quarter up close.
        if not (PLACES[kind] - 2.0 <= view.zoom <= PLACES[kind] + 2.5):
            continue
        x, y = parts[0][0]
        candidates.append((-(f.tags.get('population') or 0), PLACES[kind], name, x, y))
    seen = set()
    for _, _, name, x, y in sorted(candidates):
        # A place's name is in every tile it lies near: once is enough.
        if name in seen:
            continue
        seen.add(name)
        box = draw.textbbox((x, y), name, font=face, anchor='mm')
        pad = 4 * s
        box = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
        if box[0] < 6 * s or box[1] < 6 * s or box[2] > canvas.width * s - 6 * s or box[3] > canvas.height * s - 6 * s:
            continue
        if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in taken):
            continue
        draw.text((x, y), name, font=face, anchor='mm', fill=_rgb(look['place']),
                  stroke_width=round(2 * s * dpi_scale), stroke_fill=_rgb(look['halo']))
        taken.append(box)
        shown += 1
        if shown >= 2:
            break


def draw_zones(canvas, view, zones, look, dpi_scale, marker, occupied=()):
    from PIL import Image, ImageDraw
    s = SUPERSAMPLE
    overlay = Image.new('RGBA', canvas.image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    boxes = []
    for z in zones:
        x, y = view.point(z.lat, z.lon)
        r = z.radius / metres_per_pixel(z.lat, view.zoom)
        # A zone smaller than a marker is a marker's business when someone is in it, and otherwise still a place:
        # a small ring, so a school or an office stays findable from afar.
        if r < marker / 2 and z.entity in occupied:
            continue
        r = max(r, 5 * dpi_scale)
        if x + r < 0 or y + r < 0 or x - r > canvas.width or y - r > canvas.height:
            continue
        X, Y, R = x * s, y * s, r * s
        # A zone that fills the card is a tint, not a slab: its fill fades as it grows past the card.
        alpha = round(look['zone_alpha'] * min(1.0, 0.45 * min(canvas.width, canvas.height) / max(r, 1)))
        draw.ellipse((X - R, Y - R, X + R, Y + R), fill=_rgb(look['zone_fill']) + (max(8, alpha),),
                     outline=_rgb(look['zone_edge']) + (200,), width=max(1, round(1.3 * dpi_scale * s)))
        boxes.append((X - R, Y - R, X + R, Y + R))
    canvas.image.paste(Image.alpha_composite(canvas.image.convert('RGBA'), overlay).convert('RGB'))
    return boxes


def initials(name):
    """The letters in a marker, as Home Assistant's map writes them (ha-map.ts): the first letter of each word of the
    name, at most three."""
    return ''.join(part[:1] for part in str(name or '').split(' ') if part)[:3] or '?'


def _spread(people, points, gap, focus=None):
    """Markers that would lie on top of each other on the glass (closer than `gap`) fanned out round their middle, so
    each stays to be seen; everyone else exactly on their place. The one a finger picked (`focus`) never moves: it
    stays exactly on its coordinate, and whoever lies on it makes room round it."""
    out = list(points)
    done = set()
    for i in range(len(out)):
        if i in done:
            continue
        group, grown = [i], True
        while grown:
            grown = False
            for j in range(len(out)):
                if j not in group and j not in done and any(math.hypot(out[j][0] - out[k][0], out[j][1] - out[k][1]) < gap for k in group):
                    group.append(j)
                    grown = True
        done.update(group)
        if len(group) < 2:
            continue
        pinned = next((j for j in group if people[j].entity == focus), None)
        if pinned is not None:
            cx, cy = out[pinned]
            others = [j for j in group if j != pinned]
            for n, j in enumerate(others):
                angle = -math.pi / 2 + 2 * math.pi * n / len(others)
                out[j] = (cx + gap * 1.05 * math.cos(angle), cy + gap * 1.05 * math.sin(angle))
            continue
        cx = sum(out[j][0] for j in group) / len(group)
        cy = sum(out[j][1] for j in group) / len(group)
        r = gap * (0.58 if len(group) == 2 else 0.55 / math.sin(math.pi / len(group)))
        for n, j in enumerate(group):
            angle = -math.pi / 2 + 2 * math.pi * n / len(group)
            out[j] = (cx + r * math.cos(angle), cy + r * math.sin(angle))
    return out


def draw_people(canvas, view, people, look, dpi_scale, marker, names=False, photos=None, focus=None, hits=None):
    """A disc per person, Home Assistant's own marker (ha-entity-marker.ts): a ring in the person's colour around their
    picture when they have one (`photos`), else around their initials on the card's colour. Where Home Assistant
    reports how sure it is of a place and that is wider than the marker, a faint circle in the same colour says so.
    Who is outside the view is a small chip at the edge that points the way."""
    from PIL import Image, ImageDraw, ImageFilter
    s = SUPERSAMPLE
    photos = photos or {}
    placed = [p for p in people if p.placed]
    edge_margin = marker * 0.5 + 4 * dpi_scale
    inside = [p for p in placed if view.inside(p.lat, p.lon, -marker * 0.2)]
    outside = [p for p in placed if p not in inside]
    # Where Home Assistant puts them, from north to south, so a marker further down lies over one above it as pins on a
    # map do; only markers that would cover each other fan out (_spread), and the focused one never moves.
    inside.sort(key=lambda p: -p.lat)
    spots = _spread(inside, [view.point(p.lat, p.lon) for p in inside], marker * 0.9, focus)
    chips = []
    for p in outside:
        x, y = view.point(p.lat, p.lon)
        cx, cy = canvas.width / 2, canvas.height / 2
        dx, dy = x - cx, y - cy
        t = min((cx - edge_margin) / abs(dx) if dx else 1e9, (cy - edge_margin) / abs(dy) if dy else 1e9)
        chips.append((p, (cx + dx * t, cy + dy * t), math.atan2(dy, dx)))
    accuracy = Image.new('RGBA', canvas.image.size, (0, 0, 0, 0))
    ad = ImageDraw.Draw(accuracy)
    drawn = False
    for p in inside:
        r = p.accuracy / metres_per_pixel(p.lat, view.zoom) if p.accuracy else 0
        if r > marker * 0.75 and not p.zone_only:
            x, y = view.point(p.lat, p.lon)
            colour = PEOPLE_RGB[p.colour % len(PEOPLE_RGB)]
            ad.ellipse((x * s - r * s, y * s - r * s, x * s + r * s, y * s + r * s), fill=colour + (26,),
                       outline=colour + (110,), width=max(1, round(1.0 * dpi_scale * s)))
            drawn = True
    if drawn:
        canvas.image.paste(Image.alpha_composite(canvas.image.convert('RGBA'), accuracy).convert('RGB'))
    shadow = Image.new('L', canvas.image.size)
    sd = ImageDraw.Draw(shadow)
    # The one a finger picked on the full view (focus) is a size larger, so the eye finds it at once.
    shown = [(p, x, y, marker * (1.3 if p.entity == focus else 1.0)) for p, (x, y) in zip(inside, spots)
             # Under the card the screen lays over a focused view's bottom, a marker would only peek out.
             if not (focus and y > canvas.height * (1 - SHEET_SHARE) - marker * 0.3)]
    if focus:
        chips = [(p, (x, y), a) for p, (x, y), a in chips if y < canvas.height * (1 - SHEET_SHARE) - marker * 0.3]
    discs = shown + [(p, x, y, marker * 0.72) for p, (x, y), _ in chips]
    # Where each marker is on the picture, for the screen to know which one a finger is on: pixels, never a place.
    if hits is not None:
        hits.extend([p.entity, round(x), round(y), round(max(d / 2, marker * 0.6))] for p, x, y, d in discs)
    for p, x, y, d in discs:
        R = d / 2 * s
        oy = 1.2 * dpi_scale * s
        sd.ellipse((x * s - R, y * s - R + oy, x * s + R, y * s + R + oy), fill=look['shadow_alpha'])
    shadow = shadow.filter(ImageFilter.GaussianBlur(2.2 * dpi_scale * s))
    canvas.image.paste(_rgb(look['shadow']), mask=shadow)
    draw = ImageDraw.Draw(canvas.image)
    boxes, taken = [], []
    for p, (x, y), angle in chips:
        # The arrow first, so the disc sits on its root.
        d = marker * 0.72
        tip = d / 2 + 5 * dpi_scale
        ax, ay = x + math.cos(angle) * tip, y + math.sin(angle) * tip
        side = 4.5 * dpi_scale
        bx, by = x + math.cos(angle) * (d / 2 - 1), y + math.sin(angle) * (d / 2 - 1)
        nx, ny = -math.sin(angle) * side, math.cos(angle) * side
        draw.polygon([(ax * s, ay * s), ((bx + nx) * s, (by + ny) * s), ((bx - nx) * s, (by - ny) * s)],
                     fill=PEOPLE_RGB[p.colour % len(PEOPLE_RGB)])
    for p, x, y, d in discs:
        colour = PEOPLE_RGB[p.colour % len(PEOPLE_RGB)]
        R, ring = d / 2 * s, max(2, round(0.12 * d * s))
        draw.ellipse((x * s - R, y * s - R, x * s + R, y * s + R), fill=colour)
        r = R - ring
        picture = photos.get(p.entity)
        if picture is not None:
            side = max(2, round(2 * r))
            from PIL import ImageOps
            face_image = ImageOps.fit(picture.convert('RGB'), (side, side), method=Image.Resampling.LANCZOS)
            mask = Image.new('L', (side, side))
            ImageDraw.Draw(mask).ellipse((0, 0, side - 1, side - 1), fill=255)
            canvas.image.paste(face_image, (round(x * s - side / 2), round(y * s - side / 2)), mask)
        else:
            draw.ellipse((x * s - r, y * s - r, x * s + r, y * s + r), fill=_rgb(look['card']))
            letters = initials(p.name)
            face = font(d * (0.40 if len(letters) < 3 else 0.31) * s, 500)
            draw.text((x * s, y * s + 0.5 * s), letters, font=face, anchor='mm', fill=_rgb(look['ink']))
        boxes.append((x * s - R, y * s - R, x * s + R, y * s + R))
    if names:
        # The first name beside each marker, on the card's colour, where it does not cover another marker.
        face = font(12.5 * dpi_scale * s, 500)
        for p, x, y, d in shown:
            text = (p.name or '').split(' ')[0]
            w = draw.textlength(text, font=face)
            h, pad = 19 * dpi_scale * s, 7 * dpi_scale * s
            left = x * s + d / 2 * s + 3 * dpi_scale * s
            if left + w + 2 * pad > canvas.width * s - 4 * s:
                left = x * s - d / 2 * s - 3 * dpi_scale * s - w - 2 * pad
            box = (left, y * s - h / 2, left + w + 2 * pad, y * s + h / 2)
            if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in boxes + taken):
                continue
            draw.rounded_rectangle(box, radius=h / 2, fill=_rgb(look['card']))
            draw.text((left + pad, y * s), text, font=face, anchor='lm', fill=_rgb(look['ink']))
            taken.append(box)
    return boxes


PEOPLE_RGB = [_rgb(c) for c in PEOPLE]
ATTRIBUTION = '© OpenStreetMap'


# The full view's top bar (runtime_tiles.h camera_open: a 40 px key 8 px down on a 170 dpi board, 60 and 16 on a large one).
BAR = 60


def draw_attribution(canvas, look, dpi_scale, bottom=False):
    from PIL import ImageDraw
    s = SUPERSAMPLE
    draw = ImageDraw.Draw(canvas.image)
    face = font(9.5 * dpi_scale * s, 400)
    x, y = canvas.width * s - 7 * dpi_scale * s, (canvas.height - 6 * dpi_scale) * s if bottom else 6 * dpi_scale * s
    draw.text((x, y), ATTRIBUTION, font=face, anchor='rd' if bottom else 'ra', fill=_rgb(look['muted']),
              stroke_width=round(1.6 * s * dpi_scale), stroke_fill=_rgb(look['halo']))


def marker_size(size, dpi_scale):
    """A marker is a finger's width on a big card and a little less on a small one."""
    short = min(size)
    return max(22.0, min(34.0, short * 0.2)) * dpi_scale if short < 170 * dpi_scale else 34.0 * dpi_scale


def render(size, people, zones, tiles, framing='everyone', distance=DEFAULT_DISTANCE, dark=False, dpi_scale=1.0,
           own=None, names=None, name=None, label_px=None, inset=None, photos=None, show_zones=True, full=False, focus=None,
           move=None):
    """The card's picture: the streets, the zones, the people and the tile's name, in the look asked for.

    `tiles` are the decoded vector tiles of `view_for` ({} draws a plain ground without streets); `name` goes on a pill at
    the bottom left in the card's own colours, `label_px` high as the screen writes a tile's name (its FONT_LABEL_SIZE).
    `names`: None puts first names beside the markers where the card has room for them, True and False always and never.
    `photos` has a picture per entity that shows one in its marker. `full`: the view over the whole glass a tap opens,
    under the screen's own top bar (its round back key and the name), so the top keeps clear of people and the
    attribution goes to the bottom. `move`: the full view moved by the screen's keys (`moved`)."""
    look = DARK if dark else LIGHT
    label_px = label_px or 18 * dpi_scale
    inset = inset if inset is not None else 8 * dpi_scale
    pill_h = round(label_px * 1.55)
    marker = marker_size(size, dpi_scale)
    shown_zones = zones if show_zones else []
    keep = (BAR * dpi_scale, 16 * dpi_scale) if full else reserve(dpi_scale, pill_h, inset, bool(name))
    view = focus_view(focus, people, size, dpi_scale) or frame_view(framing, distance, people, zones, size, own, keep, marker * 0.6)
    view = moved(view, move)
    canvas = Canvas(size, _rgb(look['land']))
    if tiles:
        draw_basemap(canvas, view, tiles, look, dpi_scale)
    occupied = {z.entity for z in (zone_of(p, zones) for p in people) if z}
    zone_boxes = draw_zones(canvas, view, shown_zones, look, dpi_scale, marker, occupied)
    if names is None:
        names = min(size) >= 200 * dpi_scale
    hits = []
    people_boxes = draw_people(canvas, view, people, look, dpi_scale, marker, names, photos, focus, hits)
    if tiles and min(size) >= 150 * dpi_scale:
        draw_places(canvas, view, tiles, look, dpi_scale, people_boxes + zone_boxes)
    if tiles:
        draw_attribution(canvas, look, dpi_scale, bottom=full)
    if name:
        draw_name(canvas, name, look, label_px, pill_h, inset)
    image = canvas.finish()
    image.info['hits'] = hits
    return image, view


# A full view moved by the screen's own keys (dev): whole zoom steps from the framed view, within these.
MOVE_ZOOM_STEPS = (-8, 5)


def move_of(value):
    """(steps, x, y) of a full view's `move` ("1,12.50,-3.00"), or None for the view as framed or a word not one."""
    if not isinstance(value, str) or not value or len(value) > 48:
        return None
    try:
        steps, x, y = value.split(',')
        steps, x, y = int(steps), float(x), float(y)
    except ValueError:
        return None
    if not all(math.isfinite(n) and abs(n) <= 1e7 for n in (x, y)):
        return None
    return max(MOVE_ZOOM_STEPS[0], min(MOVE_ZOOM_STEPS[1], steps)), round(x, 2), round(y, 2)


def moved(view, move):
    """The view moved by the screen's keys: `move` (steps, x, y) is whole zoom steps from `view` around its middle,
    and that middle moved by x, y pixels at the zoom of `view`, so a step out and back in lands on the same place."""
    if not move:
        return view
    steps, dx, dy = move
    out = View(view.lat, view.lon, view.zoom + steps, (view.width, view.height))
    f = 2 ** (out.zoom - view.zoom)
    cx, cy = view.left + view.width / 2.0 + dx, view.top + view.height / 2.0 + dy
    out.left, out.top = cx * f - view.width / 2.0, cy * f - view.height / 2.0
    return out


# A marker picked on the full view: closer in, in the middle of what the card over the bottom leaves free.
FOCUS_ZOOM = 16.0
SHEET_SHARE = 0.5


def focus_view(focus, people, size, dpi_scale):
    """The full view around the one a finger picked: that person or tracker in the middle of the map above the card the
    screen lays over the bottom, closer in, as Home Assistant's map focuses an entity."""
    picked = next((p for p in people if p.entity == focus and p.placed), None) if focus else None
    if picked is None:
        return None
    view = View(picked.lat, picked.lon, FOCUS_ZOOM, size)
    top, free = BAR * dpi_scale, size[1] * (1 - SHEET_SHARE) - BAR * dpi_scale
    view.top += size[1] / 2 - (top + free / 2)
    return view


def reserve(dpi_scale, pill_h, inset, named):
    """The rows a fit keeps free: the attribution's line at the top, the name's pill at the bottom."""
    return 16 * dpi_scale, (pill_h + inset + 4 * dpi_scale) if named else 8 * dpi_scale


def draw_name(canvas, name, look, label_px, pill_h, inset):
    """The tile's name on a pill at the bottom left, as legible on streets as on a card: ink on the card's colour."""
    from PIL import ImageDraw
    s = SUPERSAMPLE
    draw = ImageDraw.Draw(canvas.image)
    face = font(label_px * s, 500)
    pad = pill_h * 0.42
    room = canvas.width - 2 * inset - 2 * pad
    text = name
    while text and draw.textlength(text, font=face) > room * s:
        text = text[:-1]
    if text != name:
        text = text.rstrip()[:-1] + '…' if len(text) > 1 else text
    width = draw.textlength(text, font=face) / s
    x, y = inset, canvas.height - inset - pill_h
    draw.rounded_rectangle((x * s, y * s, (x + width + 2 * pad) * s, (y + pill_h) * s), radius=pill_h / 2 * s,
                           fill=_rgb(look['card']))
    draw.text(((x + pad) * s, (y + pill_h / 2) * s), text, font=face, anchor='lm', fill=_rgb(look['ink']))


# ----- A map tile of a layout -----

MAP_TILE = 'screen.map'
# Places go into the mark on a grid of about this many metres, so a phone's drift does not ask for a new picture.
MARK_METRES = 25
MARK_DEGREES = MARK_METRES / 111320.0
# Every choice of a map and its default, the first of the catalogue's (catalogue/person.yaml `map`).
CHOICES = {'framing': FRAMINGS, 'distance': tuple(DISTANCES), 'overlay': ('name', 'none'), 'follow': ('everyone', 'chosen'),
           'markers': ('photo', 'initials'), 'names': ('auto', 'always', 'never'), 'zones': ('show', 'hide'),
           'streets': ('show', 'hide'), 'look': ('auto', 'light', 'dark')}
DEFAULTS = {'framing': 'everyone', 'distance': DEFAULT_DISTANCE, 'overlay': 'name', 'follow': 'everyone',
            'markers': 'photo', 'names': 'auto', 'zones': 'show', 'streets': 'show', 'look': 'auto'}


def options_of(tile):
    """Every choice of a map tile, a stored one or its default."""
    options = tile.get('options') or {}
    return {key: options.get(key) if options.get(key) in CHOICES[key] else DEFAULTS[key] for key in CHOICES}


def shown(tile, states=None, registry=None):
    """Everyone on the card, in its order. A person's map: the person first, then who rides along. The map tile: everyone
    Home Assistant knows the place of (as its own map card's show_all), or the people and trackers chosen."""
    chosen = [e for e in (tile.get('options') or {}).get('map') or () if isinstance(e, str)]
    if tile['entity'] == MAP_TILE:
        if options_of(tile)['follow'] == 'everyone':
            return everyone(states or {}, registry)
        out = []
    else:
        out = [tile['entity']]
    for entity in chosen:
        if entity not in out:
            out.append(entity)
    return out


def name_of(tile, states):
    """The tile's name as the screen would write it: its own, else Home Assistant's, else the map's."""
    if tile.get('name'):
        return tile['name']
    if tile['entity'] == MAP_TILE:
        return ''
    attributes = (states.get(tile['entity']) or {}).get('attributes') or {}
    return attributes.get('friendly_name') or tile['entity'].split('.', 1)[1]


def dark_for(tile, dark):
    """The look a card is drawn in: the screen's, or the one the card keeps whatever the screen does."""
    look = options_of(tile)['look']
    return dark if look == 'auto' else look == 'dark'


def fingerprint(tile, states, registry=None):
    """The movement mark: a short hash of all a card is drawn from (its choices and name, who is on it and where on a
    grid of MARK_METRES, their states, names, pictures and colours, the zones), never a place itself. The screen asks for
    a new picture when it changes and never otherwise."""
    import hashlib
    import json
    options = options_of(tile)
    order = colour_order(registry)
    people = []
    for entity in shown(tile, states, registry):
        state = states.get(entity) or {}
        a = state.get('attributes') or {}
        found = locate(entity, states)
        cell = (round(found[0] / MARK_DEGREES), round(found[1] / MARK_DEGREES), round((found[2] or 0) / 50)) if found else None
        people.append((entity, state.get('state'), a.get('friendly_name'), a.get('entity_picture'), cell, colour_of(entity, order)))
    zones = [(z.entity, z.name, round(z.lat, 5), round(z.lon, 5), round(z.radius)) for z in zones_of(states)]
    what = [sorted(options.items()), (tile.get('options') or {}).get('map') or [],
            name_of(tile, states) if options['overlay'] == 'name' else '', people, zones]
    return hashlib.sha1(json.dumps(what, sort_keys=True, default=str).encode()).hexdigest()[:12]


class Board:
    """What a screen's board says about drawing a card: its pixels per inch against the 170 of the 4-inch Guition every
    size here is written for, the size its tile names are in and the inset of a card's contents."""

    def __init__(self, shape=None):
        shape = shape or {}
        self.scale = max(0.6, min(2.0, float(shape.get('dpi') or 170) / 170.0))
        self.label = int((shape.get('fonts') or {}).get('label') or round(18 * self.scale))
        self.inset = round(((shape.get('spacing') or {}).get('tile_pad') or 12) * 0.7)


def _card(tile, states, registry):
    options = options_of(tile)
    people = people_of(shown(tile, states, registry), states, registry)
    return options, people, zones_of(states)


def view_for(tile, states, size, board, registry=None, full=False, focus=None, move=None):
    """The view a map tile shows at `size`: what its tiles are asked for with (View.tiles)."""
    return moved(_framed(tile, states, size, board, registry, full, focus), move if full else None)


def _framed(tile, states, size, board, registry, full, focus):
    options, people, zones = _card(tile, states, registry)
    focused = focus_view(focus, people, size, board.scale) if full else None
    if focused:
        return focused
    pill_h = round(board.label * 1.55)
    own = people[0] if people else None
    keep = (BAR * board.scale, 16 * board.scale) if full else \
        reserve(board.scale, pill_h, board.inset, options['overlay'] == 'name' and bool(name_of(tile, states)))
    return frame_view(options['framing'], options['distance'], people, zones, size, own, keep, marker_size(size, board.scale) * 0.6)


def wants_streets(tile):
    return options_of(tile)['streets'] == 'show'


def pictures_wanted(tile, states, registry=None):
    """{entity: picture address} of everyone on the card who shows a picture in their marker."""
    if options_of(tile)['markers'] != 'photo':
        return {}
    out = {}
    for entity in shown(tile, states, registry):
        picture = ((states.get(entity) or {}).get('attributes') or {}).get('entity_picture')
        if isinstance(picture, str) and picture:
            out[entity] = picture
    return out


def render_tile(tile, states, size, board, dark=False, tiles=None, registry=None, photos=None, full=False, focus=None, move=None):
    """The picture of one map tile of a layout at exactly `size`, in the look `dark_for` gives it; `full` the view over
    the whole glass a tap on it opens, where the screen writes the name in its top bar."""
    options, people, zones = _card(tile, states, registry)
    names = {'auto': True if full else None, 'always': True, 'never': False}[options['names']]
    name = name_of(tile, states) if options['overlay'] == 'name' and not full else None
    image, _ = render(size, people, zones, (tiles or {}) if options['streets'] == 'show' else {}, options['framing'],
                      options['distance'], dark_for(tile, dark), board.scale, people[0] if people else None, names,
                      name or None, board.label, board.inset, photos, options['zones'] == 'show', full, focus if full else None,
                      move if full else None)
    return image
