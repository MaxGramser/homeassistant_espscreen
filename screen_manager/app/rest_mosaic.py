"""A player at rest shows its library: the covers of a folder of its library as a mosaic over its `cover` tile.

A player's `cover` tile is a picture over the whole card while it plays, its name and state on top: on every size
(firmware of the picture system; two rows or more since 0.3.1, the cover in the icon's place on one row before). While
nothing plays, Home Assistant gives no picture and the card was an empty block. Now this app gives the tile a picture of
its own then: the covers of a folder of the player's library, side by side, darkened as much as the firmware asks for a
cover (tile_picture SHADE), and every ROTATE_SECONDS one of them moves on to the next of the folder. The tile asks for
its picture by a mark (`pic`), as it does for a cover, and the page's strip is drawn here (picture_sources, a cover tile
at rest): two covers along the card's shorter side on a taller card, one on a card of one row (rows_for).

- What is at rest: a state without a song (idle, on, off, standby, a pause with nothing in it) and no picture of the
  player's own. A player that plays without a picture (a radio stream) keeps its card: the mosaic never stands for
  what plays.
- Which folder: the first of the library's top that holds songs (Spotify's "Liked songs", newest first), else albums,
  else playlists, else the top's own items. Home Assistant's titles and pictures, nothing of a brand.
- The covers keep their own shape: square, all one size, two along the card's shorter side, as many along the longer
  one as fill it, and what reaches past the card is cut off at both ends, never squeezed (cover, not a mosaic of
  stretched cells).
- The folder is read again after POOL_SECONDS; its covers are told apart by their picture, so a folder of songs of one
  album shows that album once.
"""
import hashlib
import io
import math

import core

# The states of a player that has nothing to show: Home Assistant's own words (MediaPlayerState).
REST_STATES = ('idle', 'on', 'off', 'standby')
# The folders a mosaic takes, by what they hold (Home Assistant's children_media_class), in this order.
HOLDS = ('track', 'album', 'playlist')
ROWS = 2                 # covers along the shorter side of a card two rows or more high (one row: one, rows_for)
MIN_COVERS = 4           # a folder with fewer distinct covers gives no mosaic
POOL = 48                # covers a mosaic moves through at most: what Home Assistant gives of a folder
ROTATE_SECONDS = 60      # one cover moves on this often
POOL_SECONDS = 1800      # a folder read once serves this long


def rows_of(size):
    """The rows a tile's size takes: 2 for tall and square, a span's own, 1 for the rest."""
    if size in ('tall', 'square'):
        return 2
    span = core.span_of(size)
    return span[1] if span else 1


def wants(options):
    """Whether a tile shows a mosaic at rest: a player's `cover` tile, whose picture fills the card on every size."""
    return (options or {}).get('display') == 'cover'


def rows_for(options):
    """The covers along the card's shorter side: one on a card of one row, a strip of covers as high as the card;
    ROWS on a taller one. A screen whose firmware still puts the cover in the icon's place gets one cover there."""
    return 1 if rows_of((options or {}).get('size')) == 1 else ROWS


def at_rest(state):
    """Whether a player has nothing to show: no song, and no picture of its own."""
    state = state or {}
    attrs = state.get('attributes') or {}
    if core.media_cover(attrs):
        return False
    word = state.get('state')
    return word in REST_STATES or (word == 'paused' and not (attrs.get('media_content_id') or attrs.get('media_title')))


def folder_for(top):
    """The folder of a library's top (media_library.folder_of) a mosaic takes, or None to take the top's own items."""
    items = (top or {}).get('items') or []
    for kind in HOLDS:
        for item in items:
            if item.get('expand') and item.get('holds') == kind:
                return item
    return None


def pool_of(folder):
    """The covers of a folder, in its order, each picture once: [(thumbnail, title)]."""
    seen, pool = set(), []
    for item in (folder or {}).get('items') or []:
        thumb = item.get('thumb')
        if thumb and thumb not in seen:
            seen.add(thumb)
            pool.append((thumb, item.get('title') or ''))
        if len(pool) == POOL:
            break
    return pool if len(pool) >= MIN_COVERS else []


def step_at(now):
    """The moment's turn: one more every ROTATE_SECONDS."""
    return int(now // ROTATE_SECONDS)


def mark(pool, step):
    """The mark of a mosaic (`pic`, 16 characters at most): it changes with the folder's covers and with every turn."""
    digest = hashlib.sha1(('\n'.join(thumb for thumb, _ in pool) + f'\n{step}').encode()).hexdigest()
    return 'rest' + digest[:10]


def grid_of(width, height, rows=ROWS):
    """(columns, rows, side, left, top) of the covers over a card: square sides, `rows` along the shorter side, as many
    along the longer one as cover it, and the whole centred on the card, so what reaches past it is cut off evenly."""
    side = max(1, min(width, height) // rows)
    columns, lines = max(1, math.ceil(width / side)), max(1, math.ceil(height / side))
    return columns, lines, side, (columns * side - width) // 2, (lines * side - height) // 2


def stride_of(cells):
    """The step from one cover that moves on to the next: a jump through the mosaic that reaches every cell once, so
    the change is somewhere else every time and never runs along a row."""
    for stride in range(max(1, round(cells * 0.618)), cells + 1):
        if math.gcd(stride, cells) == 1:
            return stride
    return 1


def shown(count, cells, step):
    """Which cover of the folder (its index) each cell shows at this turn. Turn t moves the cell t x stride (of the
    cells) on to cover t + cells; before its first turn a cell shows the cover of that turn, t. So the cover that goes
    is always the one longest on the card, the card shows covers step to step + cells - 1, and while the folder holds
    as many covers as the card has cells none shows twice. A smaller folder keeps still, its covers spread out."""
    inverse = pow(stride_of(cells), -1, cells)
    result = []
    for cell in range(cells):
        first = cell * inverse % cells        # the first turn this cell moves on
        turn = step if count > cells else 0
        last = first + cells * ((turn - 1 - first) // cells)   # its last turn so far; one round back before its first
        result.append((last + cells) % count)
    return result


def draw(pictures, width, height, rows=ROWS):
    """The mosaic as a picture of `width` x `height`: `pictures` (bytes, or None for one that did not come), one per
    cell in reading order, each cut square from its middle and scaled, never stretched."""
    from PIL import Image, ImageOps
    columns, lines, side, left, top = grid_of(width, height, rows)
    whole = Image.new('RGB', (columns * side, lines * side))
    for n in range(columns * lines):
        raw = pictures[n % len(pictures)] if pictures else None
        if raw is None:
            continue
        try:
            with Image.open(io.BytesIO(raw)) as source:
                source.draft('RGB', (side * 2, side * 2))
                cover = ImageOps.fit(source.convert('RGB'), (side, side), method=Image.Resampling.LANCZOS)
        except (OSError, ValueError):
            continue
        whole.paste(cover, ((n % columns) * side, (n // columns) * side))
    return whole.crop((left, top, left + width, top + height))
