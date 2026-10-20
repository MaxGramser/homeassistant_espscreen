"""The screensaver (app 0.4.48, firmware 0.29.0): what a screen shows when Auto standby dims it, instead of its tiles.

Each screen has its own choice, kept per Home Assistant device as the screen's label is (screen_labels.py), so it
outlives a renamed inbox and leaves the layouts' storage alone: a media player (or a few, tried in their order, app
0.4.54), a camera and the order the screen tries them in, with the clock as a step of its own. This app decides which
step is available right now (a player that plays and has a cover, a camera Home Assistant has, the clock always) and tells the screen in one small message whenever that
changes. The screen asks for its picture the way a camera's full view does, and the app makes one picture of the whole
glass (picture_paint, the fit `saver`): a camera filling it, a cover filling it or beside its own colour, all a little darker
for the words over it. Nothing on it takes a tap, so the first touch only wakes the screen.

A board without pictures (the CYD and the other boards without PSRAM) shows the clock; its editor offers nothing else."""
import logging
import re
import time
from datetime import datetime, timezone

import atomic
import core

LOG = logging.getLogger(__name__)

FEATURE = 'screensaver'
# A screen whose screensaver has keys for its player (firmware 0.33.0+, app 0.4.55): play or pause and the volume. Its
# hello lists it. For such a screen a paused player still counts, after every player that plays, so the key that
# paused it can start it again; the message then carries the player's state and what Home Assistant says it can do.
KEYS_FEATURE = 'saver_keys'
# A screen that draws the clock's row of entities (firmware 0.50.0+, app 0.4.81): `wi` in the message.
ITEMS_FEATURE = 'saver_items'
# A screen whose clock has faces beside the digital one (module clock_faces, boards with 8 MB of flash or more): `cf` in
# the message. Its hello lists it; any other screen shows the digital clock whatever face is chosen.
FACES_FEATURE = 'clock_faces'
MODULE = 'clock_faces'
# How long a paused player keeps the screensaver. A speaker stays "paused" in Home Assistant for days, and the camera
# or the clock after it would never show again.
PAUSED_SECONDS = 600
# The player on the glass that is paused keeps the glass this long, also while another one plays: pause is pressed on
# the screensaver itself, and its play key must still be there for the finger that pressed it. After that a player that
# plays goes first again.
HELD_SECONDS = 120
# A screen that shows photos from a folder of Home Assistant's media (app 0.4.89): Immich, a folder under /media, Synology
# Photos, any media source. Its hello lists it; the step is offered and sent only to such a screen.
PHOTOS_FEATURE = 'saver_photos'
KINDS = ('media', 'photos', 'camera', 'clock')
PICTURE_KINDS = frozenset(('media', 'photos', 'camera'))
# The steps of a plugin (plugin API 0.14, docs/PLUGINS.md "A screensaver"): a face of a step above, or a step of its own
# in the order (`plugin:<plugin>.<saver>`). At most PLUGIN_STEPS steps of plugins, and their options in `plugins`.
PLUGIN_KEY = re.compile(r'^plugin:([a-z][a-z0-9_]{0,31})\.([a-z][a-z0-9_]{0,31})$')
PLUGIN_STEPS = 4
PLUGIN_SETTINGS = 8
# The wire name of the photos step's picture: what the screen asks the app for (no Home Assistant entity of its own).
PHOTOS_ENTITY = 'saver.photos'
# `photos` (app 0.4.89): the media source folder the photos come from, how many seconds each stands, in what order they
# come, and how one fills the glass: `auto` fills it with a photo about its shape and shows a photo of another shape whole
# on its own colour, `fill` always cuts, `whole` never does.
PHOTO_EVERY = (30, 60, 300, 900, 3600)
PHOTO_ORDERS = ('shuffle', 'in_order')
PHOTO_FITS = ('auto', 'fill', 'whole')
# `motion` (app 0.4.89): `slow` cuts a photo that fills the glass a little larger, and the screen moves it a pixel at a
# time (picture_motion.h), where that larger photo fits the screen's picture memory.
PHOTO_MOTIONS = ('still', 'slow')
PHOTOS_DEFAULT = {'source': '', 'every': 60, 'order': 'shuffle', 'fit': 'auto', 'motion': 'still'}
MEDIA_SOURCE = re.compile(r'^media-source://[^\s]{1,500}$')
# `weather` (app 0.4.52): whose temperature the clock shows under the time. 'auto' takes Home Assistant's first weather
# entity that reports one, '' shows none, and a weather entity of your choice is that one.
# `more` (app 0.4.54): the players the music step tries after `media`, in their order. The step shows the first of them
# that plays with a cover: a speaker's own music first, say, and the poster of what the television under it plays next.
# `items` (app 0.4.81): entities the clock shows beside the temperature, in one centred row: the top bar's entity items,
# each with its state or its icon alone (content `state` or `icon`, with the icon `auto`, `none` or a named one).
# `face` (clock_faces): the clock's face, `digital` (every screen), `glass`, `classic` or `bauhaus`; `numerals` the numbers
# on Glass (0, 4 or 12), `seconds` its seconds hand, `look` dark, light or the screen's own (`auto`).
FACES = ('digital', 'glass', 'classic', 'bauhaus')
LOOKS = ('dark', 'light', 'auto')
NUMERALS = (0, 4, 12)
# `media_face`, `photos_face` (plugin API 0.14): a plugin's face for that step, '' for the screen's own; `face` takes a
# plugin's face of the clock as well. `plugins`: per plugin face or step its options as the editor set them and the entity
# it belongs to (a step of a plugin of an entity), {key: {'options': {...}, 'entity': ''}}.
DEFAULT = {'show': False, 'media': '', 'camera': '', 'order': list(KINDS), 'off': [], 'weather': 'auto', 'more': [],
           'items': [], 'face': 'digital', 'numerals': 4, 'seconds': True, 'look': 'dark', 'photos': dict(PHOTOS_DEFAULT),
           'media_face': '', 'photos_face': '', 'plugins': {}}
ITEMS_MAX = 4
MORE_PLAYERS = 3
ENTITY = re.compile(r'[a-z0-9_]+\.[a-z0-9_]+')
DOMAINS = {'media': ('media_player',), 'camera': ('camera', 'image')}
# What a player does while its cover counts: playing, as Home Assistant's own media card shows its art.
PLAYING = frozenset(('playing',))
PAUSED = frozenset(('paused',))
GONE = frozenset(('', 'unavailable', 'unknown'))


def validate(value):
    """A clean copy of a screensaver choice, or ValueError. Every field is optional; the default fills the rest."""
    if not isinstance(value, dict) or set(value) - set(DEFAULT):
        raise ValueError('screensaver fields')
    result = {**DEFAULT, 'order': list(DEFAULT['order']), 'off': [], 'more': [], 'items': [],
              'photos': dict(PHOTOS_DEFAULT), 'plugins': {}}
    if 'show' in value:
        if not isinstance(value['show'], bool):
            raise ValueError('screensaver show')
        result['show'] = value['show']
    for kind in ('media', 'camera'):
        entity = value.get(kind, '')
        if not isinstance(entity, str) or (entity and (len(entity) > 120 or not ENTITY.fullmatch(entity)
                                                        or entity.split('.')[0] not in DOMAINS[kind])):
            raise ValueError(f'screensaver {kind}')
        result[kind] = entity
    if 'more' in value:
        more = value['more']
        if not isinstance(more, list) or len(more) > MORE_PLAYERS or len(set(more)) != len(more) or any(
                not isinstance(entity, str) or len(entity) > 120 or not ENTITY.fullmatch(entity)
                or entity.split('.')[0] not in DOMAINS['media'] or entity == result['media'] for entity in more):
            raise ValueError('screensaver more')
        result['more'] = list(more)
    if 'weather' in value:
        weather = value['weather']
        if not isinstance(weather, str) or (weather not in ('auto', '') and (
                len(weather) > 120 or not ENTITY.fullmatch(weather) or weather.split('.')[0] != 'weather')):
            raise ValueError('screensaver weather')
        result['weather'] = weather
    if 'items' in value:
        result['items'] = valid_items(value['items'])
    for name, allowed in (('face', FACES), ('look', LOOKS), ('numerals', NUMERALS)):
        if name in value:
            if isinstance(value[name], bool) or (value[name] not in allowed and not (name == 'face' and plugin_key(value[name]))):
                raise ValueError(f'screensaver {name}')
            result[name] = value[name]
    for name in ('media_face', 'photos_face'):
        if name in value:
            if value[name] != '' and not plugin_key(value[name]):
                raise ValueError(f'screensaver {name}')
            result[name] = value[name]
    if 'photos' in value:
        result['photos'] = valid_photos(value['photos'])
    if 'plugins' in value:
        result['plugins'] = valid_plugins(value['plugins'])
    if 'seconds' in value:
        if not isinstance(value['seconds'], bool):
            raise ValueError('screensaver seconds')
        result['seconds'] = value['seconds']
    if 'order' in value:
        result['order'] = valid_order(value['order'])
    if 'off' in value:
        off = value['off']
        if not isinstance(off, list) or any(kind not in result['order'] for kind in off) or len(set(off)) != len(off):
            raise ValueError('screensaver off')
        result['off'] = [kind for kind in result['order'] if kind in off]
    return result


def plugin_key(value):
    """(plugin, saver) for a plugin's face or step (`plugin:<plugin>.<saver>`), else None."""
    match = PLUGIN_KEY.match(value) if isinstance(value, str) else None
    return (match.group(1), match.group(2)) if match else None


def valid_order(order):
    """The order of the steps: every step of the screen once, in any order, and at most PLUGIN_STEPS steps of plugins.
    An order saved before the photos (app 0.4.88 and older) gets them right after the music, where a person who chose
    no folder never sees them."""
    if not isinstance(order, list) or len(set(map(str, order))) != len(order):
        raise ValueError('screensaver order')
    core_steps = [kind for kind in order if kind in KINDS]
    plugins = [kind for kind in order if plugin_key(kind)]
    if len(core_steps) + len(plugins) != len(order) or len(plugins) > PLUGIN_STEPS:
        raise ValueError('screensaver order')
    if 'photos' not in core_steps and sorted(core_steps) == sorted(('media', 'camera', 'clock')):
        order = list(order)
        order.insert(order.index('media') + 1, 'photos')
        core_steps.append('photos')
    if sorted(core_steps) != sorted(KINDS):
        raise ValueError('screensaver order')
    return list(order)


def valid_photos(value):
    """The photos step: a media source folder ('' for none yet), its pace, order and fit."""
    if not isinstance(value, dict) or set(value) - set(PHOTOS_DEFAULT):
        raise ValueError('screensaver photos')
    result = dict(PHOTOS_DEFAULT)
    source = value.get('source', '')
    if not isinstance(source, str) or (source and not MEDIA_SOURCE.fullmatch(source)):
        raise ValueError('screensaver photos')
    result['source'] = source
    for name, allowed in (('every', PHOTO_EVERY), ('order', PHOTO_ORDERS), ('fit', PHOTO_FITS), ('motion', PHOTO_MOTIONS)):
        if name in value:
            if isinstance(value[name], bool) or value[name] not in allowed:
                raise ValueError('screensaver photos')
            result[name] = value[name]
    return result


def valid_plugins(value):
    """Per plugin face or step its options (core.plugin_options' shape; whether they fit the plugin is its manifest's,
    checked where the plugin is known) and the entity it belongs to."""
    if not isinstance(value, dict) or len(value) > PLUGIN_SETTINGS:
        raise ValueError('screensaver plugins')
    result = {}
    for key, setting in value.items():
        if not plugin_key(key) or not isinstance(setting, dict) or set(setting) - {'options', 'entity'}:
            raise ValueError('screensaver plugins')
        options = setting.get('options', {})
        entity = setting.get('entity', '')
        if not core.plugin_options(options) or (entity and not core.plugin_entity(entity)):
            raise ValueError('screensaver plugins')
        result[key] = {'options': dict(options), 'entity': entity}
    return result


def valid_items(items):
    """The clock's entity items, checked as the top bar checks its own (core.validate_header): entity items only, shown
    always, with their state or their icon."""
    if not isinstance(items, list) or len(items) > ITEMS_MAX:
        raise ValueError('screensaver items')
    if any(not isinstance(item, dict) or item.get('type', 'entity') != 'entity' or item.get('show', 'always') != 'always'
           or item.get('content', 'state') not in ('state', 'icon') for item in items):
        raise ValueError('screensaver items')
    try:
        return core.validate_header({'items': [{**item, 'type': 'entity'} for item in items]}, ITEMS_MAX)['items']
    except ValueError:
        raise ValueError('screensaver items') from None


def _degrees(state):
    """A weather entity's temperature as a number, or None. Home Assistant gives it in the unit system it is set to."""
    value = ((state or {}).get('attributes') or {}).get('temperature')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or abs(value) > 999:
        return None
    return value


def weather_entity(choice, states):
    """The weather entity whose temperature the clock shows, or '' for none: the one chosen, or with 'auto' the forecast
    Home Assistant sets up for its home (Met.no's `weather.forecast_<home>`) and else the first weather entity by its id,
    of those that report a temperature right now."""
    wanted = (choice or {}).get('weather', 'auto')
    if wanted != 'auto':
        return wanted
    found = [entity for entity in states if entity.startswith('weather.') and _degrees(states[entity]) is not None]
    return min(found, key=lambda entity: (not entity.startswith('weather.forecast_'), entity), default='')


def temperature(choice, states):
    """The outside temperature as the clock shows it, whole degrees and the sign alone ("21°"), or '' without one. The
    number is Home Assistant's own, so Celsius or Fahrenheit as it is set there."""
    entity = weather_entity(choice, states)
    value = _degrees(states.get(entity)) if entity else None
    if value is None or (states.get(entity) or {}).get('state', '') in GONE:
        return ''
    return f'{round(value) or 0}°'


def players(choice):
    """The players of the music step in the order it tries them: the first one, then `more`."""
    return [entity for entity in (choice.get('media'), *(choice.get('more') or ())) if entity]


def _has_cover(state, words=PLAYING):
    attrs = (state or {}).get('attributes') or {}
    return (state or {}).get('state') in words and any(isinstance(attrs.get(name), str) and attrs.get(name)
                                                       for name in ('entity_picture_local', 'entity_picture'))


def _paused_lately(state, now, seconds=PAUSED_SECONDS):
    """Whether a player was paused at most `seconds` ago, by Home Assistant's last_changed."""
    try:
        moment = datetime.fromisoformat(str((state or {}).get('last_changed')).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return now - moment.timestamp() < seconds


def player(choice, states, keys=False, now=None, held='', broken=()):
    """The player the music step shows now, or '' for none: the first of its players that plays with a cover. On a
    screen with keys (KEYS_FEATURE) a player paused a short while ago counts after those, the first of them in the
    order, with the cover Home Assistant still has for it. `held` is the player the screen shows: paused just now, it
    stays before every other (HELD_SECONDS). A player in `broken` has a cover that could not be fetched
    (picture_sources.Snapshots.cover_broken) and counts as one without a cover: the glass would stay black where it never comes."""
    now = time.time() if now is None else now
    tried = [entity for entity in players(choice) if entity not in broken]
    if keys and held in tried and _has_cover(states.get(held), PAUSED) and _paused_lately(states.get(held), now, HELD_SECONDS):
        return held
    found = next((entity for entity in tried if _has_cover(states.get(entity))), '')
    if found or not keys:
        return found
    return next((entity for entity in tried
                 if _has_cover(states.get(entity), PAUSED) and _paused_lately(states.get(entity), now)), '')


def entities(choice, states=None):
    """The entities a choice follows; with the states, also the weather entity its clock reads."""
    found = set(players(choice)) | ({choice['camera']} if choice.get('camera') else set())
    weather = weather_entity(choice, states) if states is not None and choice.get('show') else ''
    shown = {item['entity'] for item in choice.get('items') or ()} if choice.get('show') else set()
    # The entities of plugin steps and faces (a weather radar of a weather entity): followed as a tile's are.
    owned = {setting['entity'] for setting in (choice.get('plugins') or {}).values() if setting.get('entity')} \
        if choice.get('show') else set()
    return found | ({weather} if weather else set()) | shown | owned


def available(kind, choice, states, pictures, keys=False, now=None, held='', broken=(), photos=None, plugins=None):
    """Whether a step can show now: one of its players plays with a cover that can be fetched, a photo of its folder is
    ready, a camera Home Assistant has, the clock always, and a plugin's step when the screen has the plugin and the
    plugin has something to show (`plugins['steps'][key]` is not None). The pictures need a board that draws them."""
    if kind == 'clock':
        return True
    if plugin_key(kind):
        return bool(plugins) and (plugins.get('faces') or {}).get(kind) == 'own' \
            and (plugins.get('steps') or {}).get(kind) is not None
    if not pictures:
        return False
    if kind == 'media':
        return bool(player(choice, states, keys, now, held, broken))
    if kind == 'photos':
        return bool(photos) and bool(photos.get('ready')) and bool((choice.get('photos') or {}).get('source'))
    return bool(choice.get(kind)) and (states.get(choice[kind]) or {}).get('state', '') not in GONE


def pick(choice, states, pictures, keys=False, now=None, held='', broken=(), photos=None, plugins=None):
    """The first step of the order that is on and available, or '' for none (standby shows the dimmed tiles as before).
    A step the screen does not take (photos to a screen whose hello lacks them) is passed over: `photos` is None then."""
    if not choice or not choice.get('show'):
        return ''
    for kind in choice.get('order', KINDS):
        if kind not in choice.get('off', ()) and available(kind, choice, states, pictures, keys, now, held, broken,
                                                           photos, plugins):
            return kind
    return ''


def face_of(kind, choice, plugins):
    """The plugin face a core step shows on this screen, or '' for the screen's own: the face chosen for it, when the
    screen has that plugin's face (its hello). A plugin that left the screen leaves the screen's own face, never a black
    glass."""
    chosen = {'clock': choice.get('face', ''), 'media': choice.get('media_face', ''),
              'photos': choice.get('photos_face', '')}.get(kind, '')
    return chosen if plugin_key(chosen) and plugins and (plugins.get('faces') or {}).get(chosen) == kind else ''


def face(choice):
    """The clock's face as the screen reads it (`cf`), or None for the digital clock."""
    if choice.get('face', 'digital') not in FACES[1:]:
        return None
    return {'f': choice['face'], 'n': choice.get('numerals', 4), 's': 1 if choice.get('seconds', True) else 0,
            'l': choice.get('look', 'dark')}


def message(choice, states, pictures, short, media_extras, ground=None, keys=False, now=None, held='', bar=None, broken=(),
            faces=False, photos=None, plugins=None):
    """The screen message for what the screensaver shows now. `short(text, n)` cuts a text the way every message does,
    `media_extras(attrs)` is the media card's (core.media_extras), `ground(entity, attrs)` the cover's colours, `keys`
    whether the screen's screensaver has keys (KEYS_FEATURE), `held` the player it shows now, `bar(item)` the top bar's
    wire item for one of the clock's entity items (header_bar.entity_item), or None for a screen that takes none,
    `broken` the players whose cover could not be fetched (player), `faces` whether the screen draws the clock's faces
    (FACES_FEATURE), `photos` the photos step of this screen ({'ready', 'mark', 'index', 'count', 'album'}, None for a
    screen without it), `plugins` its plugins' savers ({'faces': {key: step}, 'steps': {key: data or None}}, None for a
    screen without them).

    A plugin's face or step adds `pf`: the face (`p`), its options (`o`) and what it draws from (`x`, the step's
    contract in docs/PLUGINS.md "A screensaver"), which the screen hands the plugin as it is."""
    kind = pick(choice, states, pictures, keys, now, held, broken, photos, plugins)
    if plugin_key(kind):
        setting = (choice.get('plugins') or {}).get(kind) or {}
        return {'op': 'saver', 'k': 'plugin',
                'pf': {'p': kind, 'o': dict(setting.get('options') or {}), 'x': plugins['steps'][kind]}}
    result = {'op': 'saver', 'k': kind}
    own = face_of(kind, choice, plugins) if kind else ''
    if kind == 'clock':
        # The outside temperature under the time (app 0.4.52, firmware 0.31.0+); older firmware reads past it.
        degrees = temperature(choice, states)
        if degrees:
            result['w'] = degrees
        # The row of entities (app 0.4.81, firmware 0.50.0+): `wi` is the whole row, the temperature first, the way the
        # top bar sends its items. Firmware before it reads `w` alone and shows the temperature.
        row = []
        if bar and choice.get('items'):
            row = [{'k': 'text', 't': degrees}] if degrees else []
            # One ink on the black glass: an entity's colour stays home.
            row += [{key: value for key, value in bar(item).items() if key != 'c'} for item in choice['items']]
            if row:
                result['wi'] = row
        # The clock's face (clock_faces): only to a screen that draws them; older firmware and lite boards read past it.
        chosen = face(choice) if faces and not own else None
        if chosen:
            result['cf'] = chosen
        if own:
            result['pf'] = plugin_face(own, choice, clock_contract(degrees, row[1:] if degrees and row else row))
        return result
    if kind == 'photos':
        # One picture of the folder after the other (saver_photos.py): its mark changes with the photo, and the screen
        # loads the next under the one that stands, as a player's next cover.
        result['e'] = PHOTOS_ENTITY
        result['n'] = ''
        result['x'] = {'pic': photos.get('mark', '')}
        # It moves slowly (picture_motion.h): the screen moves a photo larger than its glass; one that came at the glass's
        # size stands still.
        if (choice.get('photos') or {}).get('motion') == 'slow':
            result['x']['mv'] = 1
        if own:
            result['pf'] = plugin_face(own, choice, photos_contract(photos))
        return result
    if kind not in PICTURE_KINDS:
        return result
    entity = player(choice, states, keys, now, held, broken) if kind == 'media' else choice[kind]
    state = states.get(entity) or {}
    attrs = state.get('attributes') or {}
    result['e'] = entity
    name = attrs.get('friendly_name')
    result['n'] = short(name, 60) if isinstance(name, str) and name.strip() else entity.split('.', 1)[1]
    if kind == 'media':
        title = attrs.get('media_title')
        if isinstance(title, str) and title.strip():
            result['t'] = short(title.strip(), 80)
        # The words and the marks the picture is made from; where the track is changes all the time and shows nowhere.
        extras = media_extras(attrs) or {}
        result['x'] = {key: extras[key] for key in ('artist', 'album', 'pic') if key in extras}
        colours = ground(entity, attrs) if ground else None
        if colours:
            result['x']['g'] = colours
        if keys:
            # For the keys (firmware 0.33.0+): what the play key shows, and which keys this player has.
            result['s'] = state.get('state', '')
            features = attrs.get('supported_features')
            result['f'] = features if isinstance(features, int) and not isinstance(features, bool) and features >= 0 else 0
            # Muted (volume down held on the screen, or from anywhere else): the key shows it and the next tap undoes it.
            if attrs.get('is_volume_muted') is True:
                result['m'] = 1
        if own:
            result['pf'] = plugin_face(own, choice, media_contract(entity, state, result, extras, colours))
    return result


def plugin_face(key, choice, contract):
    """`pf` of a plugin's face of a core step: the face, its options and the step's contract."""
    setting = (choice.get('plugins') or {}).get(key) or {}
    return {'p': key, 'o': dict(setting.get('options') or {}), 'x': contract}


# ---- What a plugin's face draws from (docs/PLUGINS.md, "A screensaver"). Names in full words: the contract of plugin
# API 0.14. A field may be added later; none is renamed or taken away.
def _number(value, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    if (low is not None and value < low) or (high is not None and value > high):
        return None
    return value


def media_contract(entity, state, said, extras, colours):
    """The music step: the player on the glass, what it plays and what it can do. `picture` is 'saver:picture' while it
    has a cover, the address a face gives ui::set_picture for it; `colour` the cover's own colour ('#rrggbb')."""
    attrs = (state or {}).get('attributes') or {}
    features = attrs.get('supported_features')
    volume = _number(attrs.get('volume_level'), 0, 1)
    out = {'entity': entity, 'name': said.get('n', ''), 'title': said.get('t', ''),
           'artist': extras.get('artist', ''), 'album': extras.get('album', ''),
           'state': (state or {}).get('state', ''),
           'features': features if isinstance(features, int) and not isinstance(features, bool) and features >= 0 else 0,
           'muted': attrs.get('is_volume_muted') is True,
           'picture': 'saver:picture' if extras.get('pic') else '', 'mark': extras.get('pic', '')}
    if volume is not None:
        out['volume'] = round(volume, 3)
    for key, name in (('duration', 'dur'), ('position', 'pos'), ('position_at', 'at')):
        if name in extras:
            out[key] = extras[name]
    if colours and colours != '-':
        out['colour'] = '#' + colours.split(',')[0].lower()
    return out


def clock_contract(degrees, row):
    """The clock step: the outside temperature as the clock shows it ('21°', '' for none) and the entities of its row,
    each with its icon (a codepoint of Tessera's set, 0 for none) and its words, or `since` (seconds since 1970) for one
    that says how long ago something was."""
    items = []
    for item in row or ():
        entry = {'icon': item.get('i', 0) if isinstance(item.get('i'), int) else 0, 'text': item.get('t', '')}
        if item.get('k') == 'ago' and isinstance(item.get('e'), int):
            entry['since'] = item['e']
        items.append(entry)
    return {'temperature': degrees or '', 'items': items}


def photos_contract(photos):
    """The photos step: the photo on the glass ('saver:picture') and where it stands in its folder."""
    return {'picture': 'saver:picture', 'mark': photos.get('mark', ''), 'index': photos.get('index', 0),
            'count': photos.get('count', 0), 'album': photos.get('album', '')}


class ScreenSavers:
    """Every screen's choice, by its Home Assistant device, in one small file beside the layouts."""

    def __init__(self, path):
        self.path = path
        self.choices = {}
        data = atomic.read_json(path, 1)
        saved = data.get('screens') if data else None
        for device, choice in (saved or {}).items():
            try:
                self.choices[str(device)] = validate(choice)
            except ValueError:
                LOG.warning('A screensaver choice was not readable and starts over')

    def get(self, device):
        choice = self.choices.get(device) or DEFAULT
        return {**DEFAULT, **choice, 'order': list(choice['order']), 'off': list(choice['off']),
                'more': list(choice.get('more') or ()), 'items': [dict(item) for item in choice.get('items') or ()],
                'photos': dict(choice.get('photos') or PHOTOS_DEFAULT),
                'plugins': {key: {'options': dict(value['options']), 'entity': value['entity']}
                            for key, value in (choice.get('plugins') or {}).items()}}

    def set(self, device, value):
        choice = validate(value)
        if choice == DEFAULT:
            self.choices.pop(device, None)
        else:
            self.choices[device] = choice
        self._save()
        return self.get(device)

    def forget(self, device):
        if device and self.choices.pop(device, None) is not None:
            self._save()

    def _save(self):
        try:
            atomic.write_json(self.path, {'version': 1, 'screens': self.choices})
        except OSError as error:
            LOG.warning('Could not keep the screensavers (%s)', type(error).__name__)
