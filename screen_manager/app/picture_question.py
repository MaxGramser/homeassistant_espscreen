"""The question a screen asks for a picture, read into one model (docs/PICTURES.md, "The question").

Every owner on a screen (the full view, an alert, an open card, the library, a tile, a plugin's card or screensaver) asks
in the same shape: its places, a source per place, how each is painted, and whether it may stream. This module reads
that shape (`q`, firmware with the feature `pictures`) and holds the limits every picture keeps; picture_legacy reads the
shapes of older firmware into the same model. Nothing here fetches or paints.
"""
from dataclasses import dataclass, field, replace
import json
import re

from core import SHAPES, board_of, screen_firmware, shape_of

# The largest picture any screen gets, whatever its glass (app 0.4.13, GitHub #68): at most this many pixels either way
# and this many bytes once the screen has decoded it to RGB565. The firmware caps the pictures it sizes itself with the
# same numbers (picture_store::MAX_SIDE and MAX_BYTES, tests/test_camera.py keeps them equal).
MAX_SIDE = 1024
MAX_BYTES = 1024 * 640 * 2
# A screen whose memory takes larger pictures says how large one may be (`cap`, its bytes, GitHub #183): a third of its
# picture store, 2 MB on the 32 MB of the P4 boards (picture_store::cap_for). None larger than this, whatever a screen says.
LARGE_SIDE = 2048
LARGE_BYTES = 4 * 1024 * 1024
# The most places one question may have: a page of an older screen's tiles (64), a plugin's card (8, MAX_PARTS).
MAX_PLACES = 64
# The formats a screen's decoder may take, best first in what it names: an 8-bit BMP on the picture's own palette
# (firmware 0.3.3+), a 24-bit BMP (every screen), a baseline JPEG (the hardware decoder of an ESP32-P4).
FORMATS = ('bmp8', 'bmp24', 'jpeg')
# How a picture fills its place: `cover` cuts it to the place, `contain` shows it whole on black, `within` whole on
# what lies under the place (its ground), `whole` whole on its own colour darkened, `auto` fills when the picture is about
# the place's shape and shows it `whole` otherwise (the photos of the screensaver), `shrink` sends the picture at its own
# proportions within the box (a full view's still, which the screen shows in the middle), `exact` stretches it to the
# box (an alert's frame made for those proportions), `saver` a cover over the screensaver's glass (filled on about square
# glass, else at one side on the cover's colour).
FITS = ('cover', 'contain', 'within', 'whole', 'auto', 'shrink', 'exact', 'saver')
SHADES = (0, 170)
TURNS = ('', 'left', 'right')
# Who asks. A tile of the layout, the full view, an open card, the screensaver, the library, and a plugin's tile, card
# or screensaver (`plugin`, the plugin's type key).
OWNERS = ('tile', 'view', 'card', 'saver', 'library', 'alert', 'plugin_tile', 'plugin_card', 'plugin_saver')
ENTITY = re.compile(r'[a-z0-9_]+\.[a-z0-9_]+')
COLOUR = re.compile(r'[0-9A-Fa-f]{6}')
CAMERA_DOMAINS = ('camera', 'image')
COVER_DOMAINS = ('media_player',)
# Home Assistant's own pictures a plugin tile or card of an entity may show (its entity_picture, as a map's markers).
HA_PICTURES = ('/api/image/serve/', '/api/image_proxy/', '/local/')
# The screensaver step's own picture (plugin API 0.14 named it saver:picture, 0.17 `step:`).
STEP = 'step:'
STEP_ALIASES = ('saver:picture',)
MAX_ADDRESS = 512


def valid_entity(entity, domains=None):
    return (isinstance(entity, str) and len(entity) <= 120 and ENTITY.fullmatch(entity) is not None and
            (domains is None or entity.split('.')[0] in domains))


@dataclass(frozen=True)
class Source:
    """What a picture is of (docs/PICTURES.md, "Sources"). `kind` and its `ref` (an entity, an index, an address), with
    the source's own options in `params` (a map's focus and move)."""
    kind: str
    ref: str = ''
    params: tuple = ()

    def param(self, name, default=''):
        return dict(self.params).get(name, default)

    @property
    def text(self):
        if self.kind in ('url', 'ha'):
            return self.ref
        if self.kind in ('photos', 'step'):
            return f'{self.kind}:'
        query = '&'.join(f'{k}={v}' for k, v in self.params)
        return f'{self.kind}:{self.ref}' + (f'?{query}' if query else '')


def source(text):
    """A Source from its text, or None for one that is not a source."""
    if not isinstance(text, str) or not text or len(text) > MAX_ADDRESS:
        return None
    if text in STEP_ALIASES or text == STEP:
        return Source('step')
    if text == 'photos:':
        return Source('photos')
    if text.startswith(('https://', 'http://')):
        return Source('url', text)
    if text.startswith('/'):
        path = text.split('?', 1)[0]
        if '..' in path or '//' in text[1:] or not path.startswith(HA_PICTURES):
            return None
        return Source('ha', text)
    kind, sep, rest = text.partition(':')
    if not sep:
        return None
    ref, _, query = rest.partition('?')
    params = []
    if query:
        for part in query.split('&'):
            name, eq, value = part.partition('=')
            if not eq or name not in ('focus', 'move') or len(value) > 120:
                return None
            params.append((name, value))
    if kind == 'tile' or kind == 'map':
        if not ref.isdigit() or len(ref) > 3 or int(ref) >= 256:
            return None
        if kind == 'tile' and params:
            return None
        return Source(kind, ref, tuple(params))
    if params:
        return None
    if kind == 'camera':
        return Source(kind, ref) if valid_entity(ref, CAMERA_DOMAINS) else None
    if kind == 'cover':
        return Source(kind, ref) if valid_entity(ref, COVER_DOMAINS) else None
    if kind == 'entity':
        return Source(kind, ref) if valid_entity(ref) else None
    if kind == 'vacuum':
        return Source(kind, ref) if valid_entity(ref, ('vacuum',)) else None
    if kind == 'library':
        entity, slash, token = ref.partition('/')
        if not slash or not valid_entity(entity, COVER_DOMAINS) or not re.fullmatch(r'[0-9]{1,10}', token):
            return None
        return Source(kind, ref)
    return None


@dataclass(frozen=True)
class Place:
    """Where a picture lands in the question's box: x, y, w, h in pixels, its corner radius and its shade (0 or 170, the
    dark band under words), how it fills (FITS), its ground (0xRRGGBB, behind its corners and around a whole picture)
    and its effects."""
    x: int
    y: int
    w: int
    h: int
    radius: int = 0
    shade: int = 0
    fit: str = 'cover'
    ground: int = 0
    fade: bool = False       # the shade under a camera's name, the bottom of the place
    dim: int = 0             # darkened by this many percent (the screensaver's 30)
    turn: str = ''
    mirror: bool = False
    move: int = 0            # cut this many percent larger on either side (a photo that moves slowly)


@dataclass(frozen=True)
class Owner:
    """Who asks: OWNERS, a tile's index (`index`), a plugin's type key (`key`, plugin:<plugin>.<type>), and the entity
    a plugin's card or step shows (`of`), whose Home Assistant pictures it may have."""
    kind: str
    index: int = -1
    key: str = ''
    of: str = ''


@dataclass(frozen=True)
class Question:
    owner: Owner
    sources: tuple            # one Source per place
    box: tuple                # (width, height) of the whole picture
    places: tuple             # Place per source, in their order (a later place lies over an earlier one)
    look: str = 'l'           # 'd' or 'l', the screen's look (a map is drawn in it)
    cap: tuple = (MAX_SIDE, MAX_BYTES)
    formats: tuple = ('bmp24',)
    pace: int = 0             # ms until the next picture of a source that changes by itself; 0 once
    live: tuple = ()          # (w, h) of a rectangle the screen can stream into; () when it cannot
    sound: bool = False
    number: int = 0           # the question's number, which its answer carries
    extra: dict = field(default_factory=dict, compare=False, hash=False)  # what an owner adds (a map's sheet)

    @property
    def dark(self):
        return self.look == 'd'

    @property
    def format(self):
        return self.formats[0] if self.formats else 'bmp24'

    def scaled(self, scale):
        """The question with its box and places at `scale` (below 1), as the screen scales a picture over the cap."""
        if scale >= 1:
            return self
        s = lambda n: max(1, int(n * scale))
        places = tuple(replace(p, x=int(p.x * scale), y=int(p.y * scale), w=s(p.w), h=s(p.h),
                               radius=min(int(p.radius * scale), min(s(p.w), s(p.h)) // 2)) for p in self.places)
        return replace(self, box=(s(self.box[0]), s(self.box[1])), places=places)


def cap_of(value):
    """(side, bytes) one picture may be for the screen that asked: the cap every screen takes, or the larger one its
    memory takes (`cap`, firmware 0.52.0+), never more than LARGE_BYTES."""
    try:
        wanted = int(value or 0)
    except (TypeError, ValueError):
        wanted = 0
    if wanted <= MAX_BYTES:
        return MAX_SIDE, MAX_BYTES
    return LARGE_SIDE, min(wanted, LARGE_BYTES)


def capped(size, bounds=None, cap=None):
    """`size` (width, height), or the largest size of its proportions within the picture caps and optional bounds."""
    width, height = size
    side, most = cap or (MAX_SIDE, MAX_BYTES)
    limits = [1.0, side / width, side / height, (most / (2 * width * height)) ** 0.5]
    if bounds:
        limits.extend((bounds[0] / width, bounds[1] / height))
    scale = min(limits)
    return (width, height) if scale >= 1 else (max(1, int(width * scale)), max(1, int(height * scale)))


def scale_for(size, cap):
    """The scale that brings a picture of `size` within the cap (1 when it fits), as picture_store::fit_scale."""
    width, height = size
    side, most = cap
    return min(1.0, side / width, side / height, (most / (2 * width * height)) ** 0.5)


# ----- what a screen can show -----
# The pixel boxes per board and view, for the board lying down, straight from the CAMERA_* substitutions of the board's
# own YAML (tools/generate_board_shapes.py writes them into boards.json): a new board that draws pictures is served
# without a line here. A board that is not in here draws no pictures, whichever way it hangs.
BOXES = {shape['board']: {view: tuple(box) for view, box in shape['camera'].items()}
         for shape in SHAPES.values() if shape.get('camera')}
MIN_FIRMWARE = (0, 2, 57)
# Firmware whose decoder reads 8-bit BMPs (app 0.3.8): a third of the bytes of 24-bit.
COMPACT_FIRMWARE = (0, 3, 3)
# Firmware whose download reads a 304 (picture_fetch, 0.49.0+): before, ESPHome's http_request logged one as a failure.
NOT_MODIFIED_FIRMWARE = (0, 49, 0)
# The feature a screen's hello names when it asks questions (`q`) and reads their answers (`t` "q").
FEATURE = 'pictures'


def draws_pictures(screen):
    """Whether a screen's board draws pictures and its firmware asks for them."""
    return bool(screen) and board_of(screen) in BOXES and (screen_firmware(screen) or (0, 0, 0)) >= MIN_FIRMWARE


def boxes(screen):
    """The pixel boxes for one screen's pictures (`full` the whole glass, `thumb` an alert's frame), or None when its
    board draws none. A screen built standing up has the canvas of the other side (core.shape_of)."""
    found = shape_of(screen).get('camera') if isinstance(screen, dict) else None
    if not found:
        return BOXES.get(board_of(screen))
    return {view: tuple(box) for view, box in found.items()}


def box(screen, view, cap=None):
    """One of them within the cap, or None on a screen whose board draws no pictures."""
    found = (boxes(screen) or {}).get(view)
    return capped(found, cap=cap) if found else None


# Firmware 0.2.103 lays its alert out again for the picture it gets, in that picture's own proportions
# (screen_alert::layout), so from there on the picture is sent at the size that layout gives it. Older firmware has a
# frame of one fixed size and gets the picture for that frame, as before.
ALERT_FIT_FIRMWARE = (0, 2, 103)


def alert_box(screen, picture):
    """The size to send the picture of an alert at, for one screen: the frame its alert card makes for a picture of
    `picture` (width, height) proportions on its glass (alert_layout, the firmware's own rule), so the picture fills
    that frame pixel for pixel. The frame for a camera's 16:9 (box 'thumb') when the picture is not known, the
    firmware is older, or the glass has no room for a picture of those proportions; None when the board draws none."""
    import alert_layout
    default = box(screen, 'thumb')
    if not default or not picture or not isinstance(screen, dict):
        return default
    if (screen_firmware(screen) or (0, 0, 0)) < ALERT_FIT_FIRMWARE:
        return default
    board = SHAPES.get(board_of(screen)) or {}
    lines, shape = board.get('alert'), shape_of(screen)
    if not lines or not shape.get('width') or not shape.get('height') or not board.get('dpi'):
        return default
    # The density and the look the screen reports (its "Screen layout") win over its board's, so an Override YAML that
    # changes DISPLAY_DPI or the look is followed. As the board was built, its own line heights hold.
    dpi, look = shape.get('dpi') or board['dpi'], shape.get('look') or board.get('look', 'standard')
    if (dpi, look) == (board['dpi'], board.get('look', 'standard')):
        title_line, line = lines['title_line'], lines['line']
    else:
        title_line, line = alert_layout.lines(dpi, look)
    card = alert_layout.layout(shape['width'], shape['height'], title_line, line, True, dpi, look, picture[0], picture[1])
    return capped((card.image_w, card.image_h), box(screen, 'full')) if card.image_w > 0 and card.image_h > 0 else default


def formats(screen):
    """The formats a screen of older firmware takes, best first (a newer one names its own in its question)."""
    return ('bmp8', 'bmp24') if (screen_firmware(screen) or (0, 0, 0)) >= COMPACT_FIRMWARE else ('bmp24',)


def serves_304(screen):
    return (screen_firmware(screen) or (0, 0, 0)) >= NOT_MODIFIED_FIRMWARE


# ----- the question as a screen asks it (`q`) -----
def _int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(value)
    return value


def parse(text, number, canvas):
    """A Question from the JSON text of `q` and its number (`n`), or None when it is not one this app answers. `canvas`
    (width, height) is the screen's glass; a picture is never larger than the largest the screen may take."""
    if not isinstance(text, str) or len(text) > 16384:
        return None
    try:
        q = json.loads(text)
        if not isinstance(q, dict):
            return None
        width, height = canvas
        if width <= 0 or height <= 0:
            return None
        owner = owner_of(q)
        if owner is None:
            return None
        cap = cap_of(q.get('cap'))
        box_w, box_h = (_int(n, 1, LARGE_SIDE) for n in q['box'])
        texts = q['src'] if isinstance(q.get('src'), list) else [q.get('src')]
        frames = q['at']
        if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_PLACES:
            return None
        if len(texts) == 1:
            texts = texts * len(frames)
        if len(texts) != len(frames):
            return None
        sources = tuple(source(t) for t in texts)
        if any(s is None for s in sources):
            return None
        # A tile's own picture and a map tile opened name the tile's entity in `for`: the tile they ask for must still
        # show that entity (the layout may have changed since), as an older screen's fields said (picture_legacy,
        # `tile:<i>?entity=`, `map:<i>?entity=`).
        if owner.kind in ('tile', 'view') and owner.of:
            sources = tuple(Source(s.kind, s.ref, (('entity', owner.of),) + s.params)
                            if s.kind in ('tile', 'map') and not s.param('entity') else s for s in sources)
        per = lambda name, default: (q.get(name) if isinstance(q.get(name), list) else [q.get(name, default)] * len(frames))
        fits, grounds, effects = per('fit', 'cover'), per('bg', '000000'), per('fx', {})
        if len(fits) != len(frames) or len(grounds) != len(frames) or len(effects) != len(frames):
            return None
        places = []
        for frame, fit, ground, fx in zip(frames, fits, grounds, effects):
            x, y, w, h, radius, shade = frame
            x, y = _int(x, 0, box_w - 1), _int(y, 0, box_h - 1)
            w, h = _int(w, 1, box_w - x), _int(h, 1, box_h - y)
            radius = _int(radius, 0, min(w, h) // 2)
            if shade not in SHADES or fit not in FITS or not isinstance(ground, str) or not COLOUR.fullmatch(ground):
                return None
            if not isinstance(fx, dict) or set(fx) - {'fade', 'dim', 'turn', 'mirror', 'move'}:
                return None
            turn = fx.get('turn', '')
            if turn not in TURNS:
                return None
            places.append(Place(x, y, w, h, radius, shade, fit, int(ground, 16), fade=bool(fx.get('fade')),
                                dim=_int(fx.get('dim', 0), 0, 90), turn=turn, mirror=bool(fx.get('mirror')),
                                move=_int(fx.get('move', 0), 0, 25)))
        named = [f for f in (q.get('fmt') or ['bmp24']) if f in FORMATS]
        live = ()
        if q.get('live') is not None:
            live = tuple(_int(n, 64, 4096) for n in q['live'])
            if len(live) != 2:
                return None
        return Question(owner, sources, (box_w, box_h), tuple(places),
                        look='d' if q.get('look') == 'd' else 'l', cap=cap, formats=tuple(named) or ('bmp24',),
                        pace=_int(q.get('pace', 0), 0, 3600000), live=live, sound=q.get('sound') == 1,
                        number=number)
    except (ValueError, TypeError, KeyError):
        return None


def owner_of(fields):
    """The Owner a question names: `o` the kind, `i` a tile's index, `p` a plugin's type key, `for` the entity a plugin's
    card or step shows. None for one this app does not know."""
    kind = fields.get('o')
    if kind not in OWNERS:
        return None
    index = -1
    if kind in ('tile', 'plugin_tile'):
        index = fields.get('i')
        if type(index) is not int or not 0 <= index < 256:
            return None
    key = fields.get('p', '') if kind.startswith('plugin') else ''
    if kind.startswith('plugin') and not re.fullmatch(r'plugin:[a-z0-9_]{1,40}\.[a-z0-9_]{1,40}', key or ''):
        return None
    of = fields.get('for', '') or ''
    if of and not valid_entity(of):
        return None
    return Owner(kind, index, key, of)


def answer(question, url, kind='q', entity='', meta=None):
    """The screen message a question is answered with: `t` "q" and its number for a question asked in this shape; an
    older shape's own `t`, `e` and `view` for picture_legacy."""
    message = {'v': 1, 'op': 'camera', 't': kind, 'e': entity, 'u': url}
    if kind == 'q':
        message['n'] = question.number
    if meta:
        message['m'] = meta
    return message
