"""A media player's library on a screen (app 0.4.42, firmware 0.24.0): its folders, their covers, and a tap that plays.

Home Assistant is the source of everything here. The library is what `media_player.browse_media` answers, the action
and not the websocket command: the websocket refuses a player that reports no BROWSE_MEDIA at that moment, and Spotify
reports nothing but SELECT_SOURCE while it plays nowhere, which is exactly when someone opens the library to start
something. The action has no such check (media_player/services.py) and answers at rest too.

A screen never holds a content id. It asks for a folder by a short number (a token) and gets its items with numbers of
their own; this app keeps what each number stands for, per screen, and plays it when the screen taps one. That keeps
the messages small (a Spotify id is 38 characters) and leaves the two steps of a start from rest here, where they can
wait for Home Assistant:

1. A player that reports no PLAY_MEDIA cannot be told to play (Home Assistant refuses `play_media`); a Spotify Connect
   account at rest is one. Choosing a speaker (`select_source`) wakes it: Spotify moves playback there, the integration
   reads its state again at once, and from then on it reports PLAY_MEDIA.
2. Then `play_media`, with the item's own content type and id, exactly as Home Assistant's media browser sends them.

Everything a player names is Home Assistant's: the folder titles (Spotify's are English, Home Assistant does not
translate them), the items, their classes and their thumbnails. Home Assistant hands out at most 48 items per folder
for Spotify (BROWSE_LIMIT) and says nothing of the rest; a screen shows what it gets, never more than LIMIT.
"""
import asyncio
import colorsys
import hashlib
import io
import json
import logging
import re
import time
from collections import OrderedDict

import catalogue
import core

LOG = logging.getLogger(__name__)

# The name a screen's hello lists when its firmware draws all of this (firmware 0.24.0+): the speaker, shuffle and
# repeat of a player, its cover's colours, the library and its covers. An older screen gets none of it.
FEATURE = 'media_library'
BROWSE_EVENT = 'esphome.screen_browse'
PLAY_EVENT = 'esphome.screen_play'
LIMIT = 48              # items a folder shows at most: what Home Assistant gives for Spotify, and the screen's pager
TITLE_LIMIT = 48        # bytes of a title, as a select's option
PAGE_BYTES = 3000       # the items of one message; a message to a screen is at most 4096 bytes
SOURCES = 16            # speakers a screen lists, as a select's options
SOURCE_LIMIT = 48
FOLDER_SECONDS = 60     # a folder read once serves the pages a screen asks for after it
BROWSABLE_SECONDS = 900  # a player that would not browse is asked again after this long
START_SECONDS = 8       # how long a start from rest waits for the player to take play_media
MAX_TOKENS = 4000       # numbers a screen's items get before the oldest are forgotten

BROWSE_MEDIA = catalogue.bits('media_player', 'BROWSE_MEDIA')
PLAY_MEDIA = catalogue.bits('media_player', 'PLAY_MEDIA')
NEXT_TRACK = catalogue.bits('media_player', 'NEXT_TRACK')
SELECT_SOURCE = catalogue.bits('media_player', 'SELECT_SOURCE')
SHUFFLE_SET = catalogue.bits('media_player', 'SHUFFLE_SET')
REPEAT_SET = catalogue.bits('media_player', 'REPEAT_SET')
# A favourite's own shuffle and repeat (app 0.4.84), as Home Assistant's shuffle_set and repeat_set take them; without
# one the player keeps its own.
SHUFFLES = {'on': True, 'off': False}
REPEATS = ('off', 'all', 'one')
# What a shuffled start skips to: Spotify starts a context at its first track whatever its shuffle says, so the first
# song heard is a shuffled one only after one skip. A single song has nothing to skip to.
SKIPS = ('playlist', 'album', 'artist', 'podcast')
SETTLE_SECONDS = 1.5    # for a player to take what it was given, before its shuffle and again before a skip

# What an item says it can do, as the screen reads it.
CAN_PLAY, CAN_EXPAND, PICTURED, PLAYING = 1, 2, 4, 8

# The icon of an item without a picture, by Home Assistant's media class (MediaClass); a folder takes the class of what
# it holds (children_media_class), so Spotify's "Playlists" folder shows a playlist. Codepoints of tile_icons.GLYPHS.
CLASS_ICONS = {
    'album': 'F0025', 'playlist': 'F0CB8', 'artist': 'F0803', 'contributing_artist': 'F0803', 'composer': 'F0803',
    'track': 'F0387', 'music': 'F075A', 'genre': 'F075A', 'podcast': 'F0994', 'episode': 'F0994',
    'channel': 'F0439', 'tv_show': 'F0502', 'season': 'F0502', 'movie': 'F0FCE', 'video': 'F0FCE', 'game': 'F0297',
    'directory': 'F024B', 'app': 'F024B', 'apps': 'F024B', 'url': 'F0387',
}
FOLDER_ICON = 'F024B'


def short(value, limit):
    """A text the screen can draw (core.short), cut to `limit` bytes of UTF-8 without breaking a character."""
    return core.short(str(value if value is not None else '').strip(), limit)


def icon_of(item):
    """The icon an item shows where it has no picture."""
    kind = item.get('media_class')
    if kind == 'directory' and item.get('children_media_class'):
        kind = item['children_media_class']
    return CLASS_ICONS.get(kind, FOLDER_ICON)


def features_of(attrs):
    value = (attrs or {}).get('supported_features')
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


# ---- what a player can do: the widest it ever said (GitHub #88) ----

class FeatureMemory:
    """The widest set of features each media player reported, kept across restarts.

    Spotify reports only SELECT_SOURCE while it plays nowhere (spotify/media_player.py: supported_features), so whatever
    reads the features at that moment finds no play, pause or next: the editor did not offer the playback keys on the
    tile (GitHub #88) and the screen drew none. A player keeps the features it showed once, and one whose integration
    says in its source what it reports while it plays (catalogue.playing_features: Spotify's SUPPORT_SPOTIFY) has those
    from the start; the screen draws what it has now and fades the rest, and the editor offers both."""

    def __init__(self, path=None, platform_of=None):
        self.path, self.seen, self.dirty = path, {}, False
        self.platform_of = platform_of
        if path is not None:
            try:
                data = json.loads(path.read_text())
                self.seen = {k: v for k, v in (data.get('players') or {}).items() if isinstance(k, str) and isinstance(v, int)}
            except (OSError, ValueError, AttributeError):
                self.seen = {}

    def playing(self, entity):
        """What the player's integration reports while it plays, from Home Assistant's source; 0 when it says nothing."""
        platform = self.platform_of(entity) if self.platform_of else None
        return catalogue.playing_features('media_player', platform) if platform else 0

    def note(self, entity, attrs):
        """Remember what a player reports now; returns the widest it may report."""
        if not isinstance(entity, str) or not entity.startswith('media_player.'):
            return features_of(attrs)
        now = features_of(attrs)
        seen = self.seen.get(entity, 0) | now
        if seen != self.seen.get(entity, 0):
            self.seen[entity] = seen
            self.dirty = True
        return seen | self.playing(entity)

    def widest(self, entity, attrs):
        return features_of(attrs) | self.seen.get(entity, 0) | self.playing(entity)

    def widened(self, entity, state):
        """The state with the player's widest features, for what the editor offers; anything else as it is."""
        if not isinstance(state, dict) or not isinstance(entity, str) or not entity.startswith('media_player.'):
            return state
        attrs = state.get('attributes') or {}
        widest = self.note(entity, attrs)
        if widest == features_of(attrs):
            return state
        return {**state, 'attributes': {**attrs, 'supported_features': widest}}

    def save(self):
        if not self.dirty or self.path is None:
            return
        self.dirty = False
        try:
            self.path.write_text(json.dumps({'players': self.seen}, sort_keys=True))
        except OSError as error:
            LOG.info('The players\' features were not saved (%s)', type(error).__name__)


# ---- what a screen gets with a player's state ----

def player_extras(attrs, widest=0, ground=None, browsable=False):
    """The media card's extras of firmware 0.24.0: the speaker it plays on (`so`) and the ones it may (`sl`), shuffle
    (`sh`) and repeat (`rp`), the features it reported before (`mf`, only when wider than now), the two colours of its
    cover (`g`, the card's ground) and whether its library opens (`lb`)."""
    result = {}
    source = attrs.get('source')
    if isinstance(source, str) and source.strip():
        result['so'] = short(source, SOURCE_LIMIT)
    sources = attrs.get('source_list')
    if isinstance(sources, list):
        names = [short(s, SOURCE_LIMIT) for s in sources if isinstance(s, str) and s.strip()][:SOURCES]
        if names:
            result['sl'] = names
    if isinstance(attrs.get('shuffle'), bool):
        result['sh'] = 1 if attrs['shuffle'] else 0
    if attrs.get('repeat') in ('off', 'all', 'one'):
        result['rp'] = attrs['repeat']
    if widest and widest != features_of(attrs):
        result['mf'] = widest
    if ground:
        result['g'] = ground
    if browsable:
        result['lb'] = 1
    return result


# How light the card's ground is: dark, so white words and keys read on it in both looks.
GROUND_LIGHTNESS = 0.17


def ground_colours(raw):
    """The card's ground from a cover: one dark colour of its own, sent twice as 'RRGGBB,RRGGBB' (top, bottom), or
    None for a cover with no colour to speak of (black and white, greys), which keeps the card's neutral ground.

    The cover goes down to 64 pixels and six colours; the one that is most coloured and least dark leads, set to a low
    lightness (0.17) with its colour held under 60 % so white text reads on it. One colour, not a gradient: every
    screen draws 16-bit colour without dithering, and a gradient between two dark colours has only a handful of steps
    in it, which showed as broad bands across the card (GitHub #135). A firmware from 0.24.0 draws the same colour at
    both ends as one flat ground, and the cover's rounded corners, filled with that colour, match the ground behind
    them. Measured on the design study's covers: Daft Punk's Random Access Memories gives 1F3338, Tame Impala's
    The Slow Rush 461511."""
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as source:
        source.draft('RGB', (128, 128))
        image = source.convert('RGB').resize((64, 64))
    quantized = image.quantize(6, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()[:18]
    counts = {index: count for count, index in quantized.getcolors()}
    scored = []
    for index in range(len(palette) // 3):
        if counts.get(index, 0) < 64 * 64 // 50:
            continue  # a speck of colour does not set the ground
        r, g, b = (palette[index * 3 + n] / 255 for n in range(3))
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        scored.append((s * (0.3 + l), h, s))
    scored.sort(reverse=True)
    if not scored or scored[0][2] < 0.12:
        return None
    _, hue, saturation = scored[0]
    r, g, b = colorsys.hls_to_rgb(hue, GROUND_LIGHTNESS, min(0.6, saturation))
    colour = '%02X%02X%02X' % (round(r * 255), round(g * 255), round(b * 255))
    return f'{colour},{colour}'


# ---- the library itself ----

def item_of(raw):
    """One child of a folder as this app keeps it, or None for what a screen cannot use."""
    if not isinstance(raw, dict):
        return None
    content_id, content_type = raw.get('media_content_id'), raw.get('media_content_type')
    if not isinstance(content_id, str) or not isinstance(content_type, str):
        return None
    title = short(raw.get('title'), TITLE_LIMIT)
    if not title:
        return None
    play, expand = raw.get('can_play') is True, raw.get('can_expand') is True
    if not play and not expand:
        return None
    thumbnail = raw.get('thumbnail')
    if isinstance(thumbnail, str) and thumbnail.startswith('/'):
        # Home Assistant's own proxy for a player's library (Sonos, Music Assistant): this app fetches it with its own
        # token, so a signature in the address is left out and never stored or shown.
        thumbnail = re.sub(r'[?&](token|authSig)=[^&]*', '', thumbnail)
    return {'title': title, 'id': content_id, 'type': content_type, 'play': play, 'expand': expand,
            'thumb': thumbnail if isinstance(thumbnail, str) and thumbnail else None, 'icon': icon_of(raw),
            'class': raw.get('media_class') if isinstance(raw.get('media_class'), str) else ''}


def folder_of(answer):
    """Home Assistant's answer for one folder ({title, children, ...}) as {title, items}, the first LIMIT children."""
    if not isinstance(answer, dict):
        raise ValueError('no folder')
    items = []
    for raw in answer.get('children') or []:
        item = item_of(raw)
        if item:
            items.append(item)
        if len(items) == LIMIT:
            break
    return {'title': short(answer.get('title'), TITLE_LIMIT), 'items': items}


class Shelf:
    """The numbers one screen's items go by: a folder or an item of a player is the same number every time it comes
    back, so a screen that kept a page of covers finds the same picture under it."""

    def __init__(self, limit=MAX_TOKENS):
        self.limit = limit
        self.by_key = OrderedDict()   # (entity, type, id) -> token
        self.by_token = {}            # token -> (entity, item)
        self.next = 1

    def token(self, entity, item):
        key = (entity, item['type'], item['id'])
        token = self.by_key.get(key)
        if token is None:
            token = self.next
            self.next += 1
            self.by_key[key] = token
            while len(self.by_key) > self.limit:
                _, old = self.by_key.popitem(last=False)
                self.by_token.pop(old, None)
        else:
            self.by_key.move_to_end(key)
        self.by_token[token] = (entity, item)
        return token

    def get(self, entity, token):
        """The item behind a number of this player, or None."""
        found = self.by_token.get(token)
        return found[1] if found and found[0] == entity else None


def holds_media(state):
    """Whether a player has something to play or pause: playing, or paused with a song. A start Spotify took and then
    dropped leaves it paused with nothing (a single song, September 2026), and nothing of it is marked as playing."""
    state = state or {}
    attrs = state.get('attributes') or {}
    return state.get('state') == 'playing' or (state.get('state') == 'paused' and bool(attrs.get('media_content_id') or attrs.get('media_title')))


def playing_now(item, attrs, started=None):
    """Whether this item is what the player plays now: the one this app started last, while that still plays, or an
    album or playlist whose name the player reports. Spotify names no playlist it does not own since February 2026, so
    a playlist of Spotify's own is marked only when this app started it."""
    if not item['play'] or not isinstance(attrs, dict):
        return False
    if started is not None and started == (item['type'], item['id']):
        return True
    title = item['title']
    if item['class'] == 'album':
        return attrs.get('media_album_name') == title
    if item['class'] == 'playlist':
        return attrs.get('media_playlist') == title
    return False


def entries(folder, shelf, entity, attrs=None, started=None):
    """The folder's items as a screen reads them: [token, title, flags, icon]."""
    out = []
    for item in folder['items']:
        flags = (CAN_PLAY if item['play'] else 0) | (CAN_EXPAND if item['expand'] else 0) | (PICTURED if item['thumb'] else 0)
        if playing_now(item, attrs, started):
            flags |= PLAYING
        out.append([shelf.token(entity, item), item['title'], flags, item['icon']])
    return out


def pages(items):
    """The items in pages that fit a message, in their order."""
    result, page, size = [], [], 0
    for item in items:
        cost = len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode()) + 1
        if page and size + cost > PAGE_BYTES:
            result.append(page)
            page, size = [], 0
        page.append(item)
        size += cost
    if page or not result:
        result.append(page)
    return result


def message(entity, folder, title, page, all_pages, count, failed=False):
    """One page of a folder, as the screen parses it (`op: browse`): the player, the folder's number as asked, its title,
    this page and how many, how many items in all, and the items."""
    page = max(0, min(int(page), len(all_pages) - 1))
    result = {'v': 1, 'op': 'browse', 'e': entity, 'f': folder, 't': title, 'i': page, 'n': len(all_pages), 'c': count,
              'k': all_pages[page]}
    if failed:
        result['x'] = 1
    return result


async def browse(call, entity, item=None):
    """One folder of a player through Home Assistant's action (`call(domain, service, data)` returns its response);
    `item` None is the top of the library."""
    data = {'entity_id': entity}
    if item is not None:
        data.update(media_content_type=item['type'], media_content_id=item['id'])
    answer = await call('media_player', 'browse_media', data)
    if not isinstance(answer, dict):
        raise ValueError('no answer')
    return folder_of(answer.get(entity) if entity in answer else answer)


async def start(states, call, entity, item, source=None, wait=START_SECONDS, sleep=asyncio.sleep, clock=time.monotonic,
                shuffle=None, repeat=None):
    """Play an item on a player: first the speaker it should play on, when one is chosen or the player must be woken, and
    then the item once the player takes it (see the module's notes), and then a favourite's own shuffle and repeat (app
    0.4.84). Returns what happened, for the log."""
    attrs = (states.get(entity) or {}).get('attributes') or {}
    if source and source != attrs.get('source'):
        if not features_of(attrs) & SELECT_SOURCE:
            return 'no speakers'
        await call('media_player', 'select_source', {'entity_id': entity, 'source': source})
    if not features_of((states.get(entity) or {}).get('attributes')) & PLAY_MEDIA:
        if not source:
            return 'no speaker'
        until = clock() + wait
        while not features_of((states.get(entity) or {}).get('attributes')) & PLAY_MEDIA:
            if clock() >= until:
                return 'not woken'
            await sleep(0.25)
    await call('media_player', 'play_media', {'entity_id': entity, 'media_content_type': item['type'], 'media_content_id': item['id']})
    if shuffle in SHUFFLES or repeat in REPEATS:
        await arrange(states, call, entity, item, shuffle, repeat, wait, sleep, clock)
    return 'playing'


async def arrange(states, call, entity, item, shuffle, repeat, wait=START_SECONDS, sleep=asyncio.sleep, clock=time.monotonic):
    """A favourite's shuffle and repeat, set once the player plays what it was given: a new queue may reset them (a
    Sonos), and Spotify takes them on what plays. With shuffle on, one skip makes the first song a shuffled one (SKIPS).
    A player without the action keeps its own."""
    await sleep(SETTLE_SECONDS)
    until = clock() + wait
    while (states.get(entity) or {}).get('state') != 'playing' and clock() < until:
        await sleep(0.25)
    features = features_of((states.get(entity) or {}).get('attributes'))
    if shuffle in SHUFFLES and features & SHUFFLE_SET:
        await call('media_player', 'shuffle_set', {'entity_id': entity, 'shuffle': SHUFFLES[shuffle]})
    if repeat in REPEATS and features & REPEAT_SET:
        await call('media_player', 'repeat_set', {'entity_id': entity, 'repeat': repeat})
    if shuffle == 'on' and features & SHUFFLE_SET and item.get('class') in SKIPS and features & NEXT_TRACK:
        await sleep(SETTLE_SECONDS)
        await call('media_player', 'media_next_track', {'entity_id': entity})


# ---- a favourite: one item of the library on a tile of its own (app 0.4.42, firmware 0.24.0) ----

def favorite_item(play):
    """A favourite's stored `play` as an item start() takes, or None."""
    if not isinstance(play, dict) or not play.get('id') or not play.get('type'):
        return None
    return {'id': play['id'], 'type': play['type'], 'title': play.get('title') or '', 'thumb': play.get('thumb'),
            'icon': CLASS_ICONS.get(play.get('class') or '', FOLDER_ICON), 'class': play.get('class') or '', 'play': True, 'expand': False}


def favorite_extras(play, speaker, attrs, started, word):
    """What a favourite's tile says (firmware 0.24.0): the kind of thing it plays in the screens' language (`fk`), the
    speaker it plays on when one is chosen (`fo`), whether it plays now (`fp`), a mark of its picture (`fm`, the screen
    asks for the picture by it) and the icon of its kind (`fi`, where it has no picture)."""
    item = favorite_item(play)
    if item is None:
        return {}
    result = {'fi': item['icon']}
    if word:
        result['fk'] = short(word, 24)
    if isinstance(speaker, str) and speaker.strip():
        result['fo'] = short(speaker, SOURCE_LIMIT)
    if playing_now(item, attrs, started):
        result['fp'] = 1
    if item['thumb']:
        result['fm'] = hashlib.sha1(item['thumb'].encode()).hexdigest()[:10]
    return result


def favorite_of(item):
    """What a favourite stores of an item it plays (core.validate_favorite)."""
    play = {'id': item['id'], 'type': item['type'], 'title': item['title']}
    if item.get('thumb'):
        play['thumb'] = item['thumb']
    if item.get('class'):
        play['class'] = item['class']
    return play


# ---- a favourite from a Spotify link (app 0.4.84) ----
#
# Home Assistant's library of a Spotify account holds at most 48 items a folder and none of what Spotify makes itself
# (Discover Weekly, Release Radar, Daily Mix): Spotify withholds those playlists from new developer apps since November
# 2024, but plays them. A link from Spotify's own app (Share > Copy link) becomes the same favourite an item of the
# library is, with the content id and type Home Assistant's media browser would send for that player: a bare URI for
# the Spotify account itself (spotify/media_player.py strips `spotify://` from the type), and the account's address
# around it for a player whose library lists the account (sonos/media_player.py: spotify_uri_from_media_browser_url).

# Spotify's word for a kind of thing -> Home Assistant's media class (FAVORITE_KINDS).
SPOTIFY_KINDS = {'playlist': 'playlist', 'album': 'album', 'artist': 'artist', 'track': 'track', 'show': 'podcast', 'episode': 'episode'}
_KIND = '(' + '|'.join(SPOTIFY_KINDS) + ')'
SPOTIFY_LINK = re.compile(r'(?:https?://)?open\.spotify\.com/(?:intl-[a-z]{2}(?:-[a-z]{2,4})?/|embed/)?' + _KIND +
                          r'/([0-9A-Za-z]{22})(?:[/?#].*)?', re.IGNORECASE)
SPOTIFY_URI = re.compile(r'spotify:' + _KIND + r':([0-9A-Za-z]{22})')
# A short link only says where to go next; following it would mean a redirect to any host, so it is refused.
SPOTIFY_SHORT = re.compile(r'(?:https?://)?(?:spotify\.link|spoti\.fi)/\S*', re.IGNORECASE)
SPOTIFY_PREFIX = 'spotify://'
OEMBED = 'https://open.spotify.com/oembed'
OEMBED_SECONDS = 8
OEMBED_BYTES = 64 * 1024


def spotify_link(text):
    """(kind, id) of a Spotify link or URI as Spotify's app copies it, or None."""
    text = (text or '').strip()
    found = SPOTIFY_LINK.fullmatch(text) or SPOTIFY_URI.fullmatch(text)
    return (found.group(1).lower(), found.group(2)) if found else None


def spotify_short(text):
    """Whether this is a short spotify.link address, which names nothing until it is followed."""
    return bool(SPOTIFY_SHORT.fullmatch((text or '').strip()))


def spotify_entry(items):
    """The account a player's library top lists (a Sonos lists `spotify://<config entry>`), or None. The first, in Home
    Assistant's order, where it lists more than one."""
    for item in items or ():
        content_id = item.get('id') if isinstance(item, dict) else None
        if isinstance(content_id, str) and content_id.startswith(SPOTIFY_PREFIX) and \
                re.fullmatch(r'[^/:]+', content_id[len(SPOTIFY_PREFIX):]):
            return content_id[len(SPOTIFY_PREFIX):]
    return None


def spotify_item(kind, spotify_id, entry=None, title='', thumb=None):
    """The item a favourite of a Spotify link plays, as item_of keeps one: for the account itself (`entry` None) or for a
    player that lists the account with that entry."""
    uri = f'spotify:{kind}:{spotify_id}'
    return {'title': short(title, TITLE_LIMIT), 'id': f'{SPOTIFY_PREFIX}{entry}/{uri}' if entry else uri,
            'type': SPOTIFY_PREFIX + kind, 'play': True, 'expand': False, 'thumb': thumb,
            'icon': CLASS_ICONS[SPOTIFY_KINDS[kind]], 'class': SPOTIFY_KINDS[kind]}


def oembed_card(raw):
    """(title, picture address) of Spotify's oEmbed answer; None for what it lacks."""
    try:
        answer = json.loads(raw)
    except (TypeError, ValueError):
        return None, None
    if not isinstance(answer, dict):
        return None, None
    title, thumb = answer.get('title'), answer.get('thumbnail_url')
    return (title.strip() if isinstance(title, str) and title.strip() else None,
            thumb if isinstance(thumb, str) and thumb.startswith('https://') else None)


def preview_jpeg(raw, side=256):
    """A picture for the editor: at most `side` pixels, JPEG."""
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(raw)) as source:
        source.draft('RGB', (side * 2, side * 2))
        image = ImageOps.exif_transpose(source).convert('RGB')
        image.thumbnail((side, side), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, 'JPEG', quality=85)
        return out.getvalue()
