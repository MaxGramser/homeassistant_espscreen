"""The questions of older firmware, read into the one question (docs/PICTURES.md, "Compatibility").

Before the feature `pictures` a screen asked each kind of picture in a shape of its own, all with the event
`esphome.screen_camera`: the full view (firmware 0.2.57), a media card's cover (0.2.64), a page's camera tiles as a
strip (0.2.77) and then as an atlas (0.3.1), a map (0.21.0), a player's library (0.24.0), the screensaver (0.29.0), each
tile alone (0.52.0), a plugin's places (plugin API 0.10, 0.13, 0.14) and a vacuum's map. Every one of them is read here
into a picture_question.Question with the `t` and `e` its answer goes back with, so the service answers all of them the
one way. Nothing of a screen that asks the new way comes through here.
"""
from dataclasses import dataclass
import json
import re

import core
import picture_question as pq
from picture_question import Owner, Place, Question

# A media card's cover (firmware 0.2.64): the smallest and largest it may ask for, in pixels; the corner a twelfth of
# its size, at least 4 px (media_card.h radius_for).
COVER_SIZES = (48, 320)
COVER_RADIUS_SHARE = 12
# A page's camera tiles as a strip of squares (firmware 0.2.77 to 0.3.0): a square's side, and a rounder corner.
LIVE_SIZES = (24, 160)
LIVE_RADIUS_SHARE = 6
LIVE_MAX_TILES = 6
# A full view's camera loads every four seconds (camera_view::REFRESH_MS), the screensaver's every fifteen.
FULL_VIEW_PACE = 4000
SAVER_PACE = 15000
# The screensaver's darkening in percent: the words over it always read.
SAVER_DIM = 30
# The photos of the screensaver are cut this much larger on either side when they move (picture_motion.h).
MOTION_OVERSCAN = 8
# The plugin pictures of one tile, card or screensaver (plugin_manifest.MAX_PICTURES, tile_picture::MAX_PARTS).
MAX_PLUGIN_PICTURES = 8
PLUGIN_FITS = ('cover', 'contain')


@dataclass(frozen=True)
class Legacy:
    """An older screen's question: the Question, and the `t` and `e` of its answer."""
    question: Question
    kind: str
    entity: str


def colour(text):
    return int(text, 16) if isinstance(text, str) and pq.COLOUR.fullmatch(text) else None


def frames(value, canvas, count, overlap=False):
    """(width, height, frames) of an atlas within `canvas`, or None: each frame x, y, width, height, corner radius and
    shade (0 or 170). Frames of different tiles never overlap; the places of one plugin tile may (`overlap`)."""
    if not isinstance(value, str) or len(value) > 8192 or not 1 <= count <= pq.MAX_PLACES:
        return None
    try:
        found = json.loads(value)
    except (ValueError, TypeError):
        return None
    if not isinstance(found, list) or len(found) != count:
        return None
    width, height = canvas
    if width <= 0 or height <= 0:
        return None
    checked, right, bottom = [], 0, 0
    for frame in found:
        if not isinstance(frame, list) or len(frame) != 6 or any(type(n) is not int for n in frame):
            return None
        x, y, w, h, radius, shade = frame
        if x < 0 or y < 0 or w < 1 or h < 1 or x + w > width or y + h > height:
            return None
        if not 0 <= radius <= min(w, h) // 2 or shade not in pq.SHADES:
            return None
        if not overlap and any(x < a + c and a < x + w and y < b + d and b < y + h for a, b, c, d, _, _ in checked):
            return None
        checked.append(tuple(frame))
        right, bottom = max(right, x + w), max(bottom, y + h)
    return right, bottom, tuple(checked)


def _number(request):
    try:
        return int(request.get('view') or 0)
    except (TypeError, ValueError):
        return 0


def _canvas(screen):
    shape = pq.shape_of(screen) if screen else {}
    return shape.get('width', 0), shape.get('height', 0)


def _dark(request):
    return 'd' if str(request.get('dark') or '') == '1' else 'l'


def _live(request):
    """(w, h) a P4 asked to stream into (`live` "WxH"), or ()."""
    found = re.fullmatch(r'(\d{2,4})x(\d{2,4})', str(request.get('live') or ''))
    if not found:
        return ()
    w, h = int(found[1]), int(found[2])
    return (w, h) if 64 <= w <= 4096 and 64 <= h <= 4096 else ()


def read(request, screen, index_of=None):
    """The Legacy of an older screen's request, or None when it is not one this app answers. `index_of(entity)` is the
    layout's index of a pictured tile of that entity, for firmware that named its tiles by entity alone (before 0.16.0)."""
    if not isinstance(request, dict) or not screen:
        return None
    entity = request.get('entity')
    if 'lib' in request:
        return _library(request, screen)
    if request.get('saver') in ('media', 'camera', 'photos'):
        return _saver(request, screen)
    if isinstance(request.get('tiles'), str) and core.plugin_tile(request['tiles']):
        return _plugin(request, screen)
    if 'tiles' in request:
        return _tiles(request, screen, index_of)
    if 'vmap' in request:
        return _vacuum(request, screen)
    if isinstance(entity, str) and (entity.startswith('person.') or entity == 'screen.map') and not request.get('size'):
        return _map(request, screen, index_of)
    if pq.valid_entity(entity, pq.COVER_DOMAINS):
        return _cover(request, screen)
    if pq.valid_entity(entity, pq.CAMERA_DOMAINS):
        return _camera(request, screen)
    return None


def _camera(request, screen):
    """A camera opened full screen (firmware 0.2.57): its still at the glass's box, within the screen's cap; a P4 names the
    room below its top bar (`live`) and may then stream, with the camera's sound (`sound`)."""
    entity = request['entity']
    cap = pq.cap_of(request.get('cap'))
    box = pq.box(screen, 'full', cap)
    if not box:
        return None
    live = _live(request) if entity.startswith('camera.') else ()
    q = Question(Owner('view'), (pq.Source('camera', entity),), box, (Place(0, 0, *box, fit='shrink'),), cap=cap,
                 formats=('bmp24',), pace=FULL_VIEW_PACE, live=live, sound=bool(live) and request.get('sound') == '1',
                 number=_number(request))
    return Legacy(q, 'full', entity)


def _cover(request, screen):
    """A media card's cover (firmware 0.2.64): a square of `size` pixels with rounded corners over `bg`."""
    try:
        size = int(request.get('size'))
    except (TypeError, ValueError):
        return None
    ground = colour(request.get('bg'))
    if not COVER_SIZES[0] <= size <= COVER_SIZES[1] or ground is None:
        return None
    entity = request['entity']
    place = Place(0, 0, size, size, max(4, size // COVER_RADIUS_SHARE), fit='cover', ground=ground)
    q = Question(Owner('card'), (pq.Source('cover', entity),), (size, size), (place,), formats=('bmp24',),
                 number=_number(request))
    return Legacy(q, 'cover', entity)


def _map(request, screen, index_of=None):
    """A map tile opened over the whole glass (firmware 0.21.0), drawn by the app at the glass's box in the screen's look:
    `idx` the tile, `focus` a person picked on it and `move` the map's own keys. A request without a tile's index gets the
    first map tile of its entity, and none when there is none; the tile must be one of that entity (Sources.may)."""
    entity = request['entity']
    try:
        index = int(request.get('idx'))
    except (TypeError, ValueError):
        index = -1
    if index < 0:
        index = index_of(entity) if index_of else -1
        if index is None or index < 0:
            return None
    cap = pq.cap_of(request.get('cap'))
    box = pq.box(screen, 'full', cap)
    if not box:
        return None
    params = []
    focus, move = request.get('focus'), request.get('move')
    if isinstance(focus, str) and focus and pq.valid_entity(focus):
        params.append(('focus', focus))
    if isinstance(move, str) and move and len(move) <= 40 and re.fullmatch(r'[0-9,+-]*', move):
        params.append(('move', move))
    source = pq.Source('map', str(index), (('entity', entity),) + tuple(params))
    q = Question(Owner('view', of=entity), (source,), box, (Place(0, 0, *box, fit='exact'),), look=_dark(request),
                 cap=cap, formats=pq.formats(screen), number=_number(request))
    return Legacy(q, 'full', entity)


def _saver(request, screen):
    """The screensaver's picture (firmware 0.29.0): the player's cover or a camera over the whole glass, darkened, or the
    photo of the photos step."""
    kind, entity = request['saver'], request.get('entity')
    cap = pq.cap_of(request.get('cap'))
    box = pq.box(screen, 'full', cap)
    if not box:
        return None
    if kind == 'photos':
        source, place, pace = pq.Source('photos'), Place(0, 0, *box, fit='auto', move=MOTION_OVERSCAN), 0
    elif kind == 'media':
        if not pq.valid_entity(entity, pq.COVER_DOMAINS):
            return None
        source, place, pace = pq.Source('cover', entity), Place(0, 0, *box, fit='saver', dim=SAVER_DIM), 0
    else:
        if not pq.valid_entity(entity, pq.CAMERA_DOMAINS):
            return None
        source, place, pace = pq.Source('camera', entity), Place(0, 0, *box, fit='cover', dim=SAVER_DIM), SAVER_PACE
    q = Question(Owner('saver'), (source,), box, (place,), cap=cap, formats=('bmp8',), pace=pace, number=_number(request))
    return Legacy(q, 'saver', entity if isinstance(entity, str) else '')


def _vacuum(request, screen):
    """A vacuum card's map (module vacuum_card), at exactly the box it asks for (`vmap` "WxH"), on `bg`, in the look."""
    found = re.fullmatch(r'(\d{2,4})x(\d{2,4})', str(request.get('vmap') or ''))
    ground, entity = colour(request.get('bg')), request.get('entity')
    if not found or ground is None or not pq.valid_entity(entity, ('vacuum',)):
        return None
    w, h = int(found[1]), int(found[2])
    if not (16 <= w <= pq.LARGE_SIDE and 16 <= h <= pq.LARGE_SIDE) or w * h * 2 > pq.LARGE_BYTES:
        return None
    q = Question(Owner('card'), (pq.Source('vacuum', entity),), (w, h), (Place(0, 0, w, h, fit='exact', ground=ground),),
                 look=_dark(request), cap=(pq.LARGE_SIDE, pq.LARGE_BYTES), formats=pq.formats(screen),
                 number=_number(request))
    return Legacy(q, 'vmap', entity)


def _library(request, screen):
    """A page of a player's library (firmware 0.24.0): one atlas of its covers, the items by their tokens (`lib`)."""
    entity = request.get('entity')
    if not pq.valid_entity(entity, pq.COVER_DOMAINS):
        return None
    tokens = str(request.get('lib') or '').split(',')
    if not tokens or not all(re.fullmatch(r'[0-9]{1,10}', t) for t in tokens):
        return None
    atlas = frames(request.get('atlas'), _canvas(screen), len(tokens))
    if atlas is None:
        return None
    ground = colour(str(request.get('bg') or '000000')) or 0
    places = tuple(Place(x, y, w, h, r, s, ground=ground) for x, y, w, h, r, s in atlas[2])
    sources = tuple(pq.Source('library', f'{entity}/{token}') for token in tokens)
    q = Question(Owner('library'), sources, atlas[:2], places, formats=pq.formats(screen), number=_number(request))
    return Legacy(q, 'lib', entity)


def _tiles(request, screen, index_of):
    """A page's pictured tiles (a camera, a cover, a favourite, a map, the covers of a player at rest): one tile alone
    (firmware 0.52.0), the tiles of a page in one atlas (0.3.1) or a strip of squares (0.2.77); a P4 names the card's
    size to stream a live tile into (`live`)."""
    tiles, grounds = request.get('tiles'), request.get('bg')
    if not isinstance(tiles, str) or not isinstance(grounds, str):
        return None
    entities, colours = tiles.split(','), grounds.split(',')
    try:
        size = int(request.get('size'))
    except (TypeError, ValueError):
        return None
    atlas_text = request.get('atlas')
    if not 1 <= len(entities) <= (pq.MAX_PLACES if atlas_text is not None else LIVE_MAX_TILES) or len(colours) != len(entities):
        return None
    if not LIVE_SIZES[0] <= size <= LIVE_SIZES[1] or any(colour(c) is None for c in colours):
        return None
    pictured = lambda e: pq.valid_entity(e, pq.CAMERA_DOMAINS + pq.COVER_DOMAINS) or e.startswith('person.') or e == 'screen.map'
    if not all(isinstance(e, str) and pictured(e) for e in entities):
        return None
    idx = request.get('idx')
    if isinstance(idx, str) and idx:
        parts = idx.split(',')
        if len(parts) != len(entities) or not all(p.isdigit() and len(p) <= 3 for p in parts):
            return None
        indexes = [int(p) for p in parts]
    else:
        indexes = [index_of(e) if index_of else -1 for e in entities]
        if any(i is None or i < 0 for i in indexes):
            return None
    sources = tuple(pq.Source('tile', str(i), (('entity', e),)) for i, e in zip(indexes, entities))
    if atlas_text is not None:
        atlas = frames(atlas_text, _canvas(screen), len(entities))
        if atlas is None:
            return None
        box = atlas[:2]
        places = tuple(Place(x, y, w, h, r, s, ground=colour(c)) for (x, y, w, h, r, s), c in zip(atlas[2], colours))
    else:
        radius = max(4, size // LIVE_RADIUS_SHARE)
        box = (size, size * len(entities))
        places = tuple(Place(0, n * size, size, size, radius, ground=colour(c)) for n, c in enumerate(colours))
    owner = Owner('tile', indexes[0]) if len(indexes) == 1 else Owner('tile', -1)
    live = _live(request) if len(entities) == 1 and entities[0].startswith('camera.') and isinstance(idx, str) and idx else ()
    q = Question(owner, sources, box, places, look=_dark(request), formats=pq.formats(screen), live=live,
                 sound=bool(live) and request.get('sound') == '1', number=_number(request))
    return Legacy(q, 'live', ','.join(entities))


def _plugin(request, screen):
    """A plugin's places (plugin API 0.10 a tile, 0.13 a card, 0.14 a screensaver): an atlas whose frames may lie over each
    other, an address per frame (`src`), how each fills (`fit`), turns (`turn`) and is reflected (`mirror`), on `bg`."""
    entity = request['tiles']
    idx, ground = request.get('idx'), colour(request.get('bg'))
    card, saver = request.get('card') == '1', request.get('saver') == '1'
    of = request.get('for') or ''
    if card and saver or ground is None:
        return None
    if (card or saver) and (not isinstance(of, str) or of and not core.plugin_entity(of)):
        return None
    if not (card or saver) and (not isinstance(idx, str) or not idx.isdigit() or len(idx) > 3):
        return None
    try:
        texts = json.loads(request.get('src') or '')
        fits = json.loads(request.get('fit') or '[]')
        turns = json.loads(request['turn']) if request.get('turn') else None
        mirrors = json.loads(request['mirror']) if request.get('mirror') else None
    except (ValueError, TypeError):
        return None
    if not isinstance(texts, list) or not 1 <= len(texts) <= MAX_PLUGIN_PICTURES or not isinstance(fits, list):
        return None
    fits = fits or ['cover'] * len(texts)
    turns = turns if turns is not None else [''] * len(texts)
    mirrors = mirrors if mirrors is not None else [0] * len(texts)
    if len(fits) != len(texts) or any(f not in PLUGIN_FITS for f in fits):
        return None
    if not isinstance(turns, list) or len(turns) != len(texts) or any(t not in pq.TURNS for t in turns):
        return None
    if not isinstance(mirrors, list) or len(mirrors) != len(texts) or any(m not in (0, 1) for m in mirrors):
        return None
    sources = tuple(pq.source(t) for t in texts)
    if any(s is None for s in sources):
        return None
    atlas = frames(request.get('atlas'), _canvas(screen), len(texts), overlap=True)
    if atlas is None:
        return None
    places = tuple(Place(x, y, w, h, r, 0, 'cover' if fit == 'cover' else 'within', ground, turn=turn, mirror=bool(mirror))
                   for (x, y, w, h, r, _s), fit, turn, mirror in zip(atlas[2], fits, turns, mirrors))
    if card:
        owner, kind = Owner('plugin_card', key=entity, of=of), 'pcard'
    elif saver:
        owner, kind = Owner('plugin_saver', key=entity, of=of), 'psaver'
    else:
        owner, kind = Owner('plugin_tile', int(idx), key=entity), 'live'
    q = Question(owner, sources, atlas[:2], places, look=_dark(request), formats=pq.formats(screen),
                 number=_number(request))
    return Legacy(q, kind, entity)
