"""The screensaver (app 0.4.48, firmware 0.29.0): what a screen shows when Auto standby dims it, instead of its tiles.

Each screen has its own choice, kept per Home Assistant device as the screen's label is (screen_labels.py), so it
outlives a renamed inbox and leaves the layouts' storage alone: a media player (or a few, tried in their order, app
0.4.54), a camera optionally gated by a movement sensor, and the order the screen tries them in, with the clock as a step
of its own. This app decides which step is available right now (a player that plays and has a cover, a camera Home
Assistant has with recent movement when a sensor is configured, the clock always) and tells the screen in one small
message whenever that
changes. The screen asks for its picture the way a camera's full view does, and the app makes one picture of the whole
glass (camera_feed.encode_saver): a camera filling it, a cover filling it or beside its own colour, all a little darker
for the words over it. Nothing on it takes a tap, so the first touch only wakes the screen.

A board without pictures (the CYD and the other boards without PSRAM) shows the clock; its editor offers nothing else."""
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone

LOG = logging.getLogger(__name__)

FEATURE = 'screensaver'
# A screen whose screensaver has keys for its player (firmware 0.33.0+, app 0.4.55): play or pause and the volume. Its
# hello lists it. For such a screen a paused player still counts, after every player that plays, so the key that
# paused it can start it again; the message then carries the player's state and what Home Assistant says it can do.
KEYS_FEATURE = 'saver_keys'
# How long a paused player keeps the screensaver. A speaker stays "paused" in Home Assistant for days, and the camera
# or the clock after it would never show again.
PAUSED_SECONDS = 600
# The player on the glass that is paused keeps the glass this long, also while another one plays: pause is pressed on
# the screensaver itself, and its play key must still be there for the finger that pressed it. After that a player that
# plays goes first again.
HELD_SECONDS = 120
KINDS = ('media', 'camera', 'clock')
PICTURE_KINDS = frozenset(('media', 'camera'))
# `weather` (app 0.4.52): whose temperature the clock shows under the time. 'auto' takes Home Assistant's first weather
# entity that reports one, '' shows none, and a weather entity of your choice is that one.
# `more` (app 0.4.54): the players the music step tries after `media`, in their order. The step shows the first of them
# that plays with a cover: a speaker's own music first, say, and the poster of what the television under it plays next.
DEFAULT = {'show': False, 'media': '', 'camera': '', 'binary_sensor': '', 'order': list(KINDS), 'off': [],
           'weather': 'auto', 'more': []}
MORE_PLAYERS = 3
MOTION_SECONDS = 60
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
    result = {**DEFAULT, 'order': list(DEFAULT['order']), 'off': [], 'more': []}
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
    sensor = value.get('binary_sensor', '')
    if not isinstance(sensor, str) or (sensor and (len(sensor) > 120 or not ENTITY.fullmatch(sensor)
                                                    or sensor.split('.')[0] != 'binary_sensor')):
        raise ValueError('screensaver binary_sensor')
    result['binary_sensor'] = sensor
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
    if 'order' in value:
        order = value['order']
        if not isinstance(order, list) or sorted(order) != sorted(KINDS):
            raise ValueError('screensaver order')
        result['order'] = list(order)
    if 'off' in value:
        off = value['off']
        if not isinstance(off, list) or any(kind not in KINDS for kind in off) or len(set(off)) != len(off):
            raise ValueError('screensaver off')
        result['off'] = [kind for kind in result['order'] if kind in off]
    return result


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


def _motion_detected(choice, states, now=None):
    """Whether the selected binary sensor is on or has been off for at most one minute."""
    entity = choice.get('binary_sensor')
    if not entity:
        return True
    state = states.get(entity) or {}
    value = state.get('state')
    if value == 'on':
        return True
    if value != 'off':
        return False
    try:
        moment = datetime.fromisoformat(str(state.get('last_changed')).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    age = (time.time() if now is None else now) - moment.timestamp()
    return 0 <= age <= MOTION_SECONDS


def player(choice, states, keys=False, now=None, held=''):
    """The player the music step shows now, or '' for none: the first of its players that plays with a cover. On a
    screen with keys (KEYS_FEATURE) a player paused a short while ago counts after those, the first of them in the
    order, with the cover Home Assistant still has for it. `held` is the player the screen shows: paused just now, it
    stays before every other (HELD_SECONDS)."""
    now = time.time() if now is None else now
    if keys and held in players(choice) and _has_cover(states.get(held), PAUSED) and _paused_lately(states.get(held), now, HELD_SECONDS):
        return held
    found = next((entity for entity in players(choice) if _has_cover(states.get(entity))), '')
    if found or not keys:
        return found
    return next((entity for entity in players(choice)
                 if _has_cover(states.get(entity), PAUSED) and _paused_lately(states.get(entity), now)), '')


def entities(choice, states=None):
    """The entities a choice follows; with the states, also the weather entity its clock reads."""
    found = set(players(choice)) | ({choice['camera']} if choice.get('camera') else set())
    if choice.get('binary_sensor'):
        found.add(choice['binary_sensor'])
    weather = weather_entity(choice, states) if states is not None and choice.get('show') else ''
    return found | ({weather} if weather else set())


def available(kind, choice, states, pictures, keys=False, now=None, held=''):
    """Whether a step can show now: one of its players plays with a cover, a camera Home Assistant has, the clock
    always. The two pictures need a board that draws them."""
    if kind == 'clock':
        return True
    if not pictures:
        return False
    if kind == 'media':
        return bool(player(choice, states, keys, now, held))
    if kind == 'camera':
        return (bool(choice.get(kind)) and (states.get(choice[kind]) or {}).get('state', '') not in GONE
                and _motion_detected(choice, states, now))
    return False


def pick(choice, states, pictures, keys=False, now=None, held=''):
    """The first step of the order that is on and available, or '' for none (standby shows the dimmed tiles as before)."""
    if not choice or not choice.get('show'):
        return ''
    for kind in choice.get('order', KINDS):
        if kind not in choice.get('off', ()) and available(kind, choice, states, pictures, keys, now, held):
            return kind
    return ''


def message(choice, states, pictures, short, media_extras, ground=None, keys=False, now=None, held=''):
    """The screen message for what the screensaver shows now. `short(text, n)` cuts a text the way every message does,
    `media_extras(attrs)` is the media card's (core.media_extras), `ground(entity, attrs)` the cover's colours, `keys`
    whether the screen's screensaver has keys (KEYS_FEATURE), `held` the player it shows now."""
    kind = pick(choice, states, pictures, keys, now, held)
    result = {'op': 'saver', 'k': kind}
    if kind == 'clock':
        # The outside temperature under the time (app 0.4.52, firmware 0.31.0+); older firmware reads past it.
        degrees = temperature(choice, states)
        if degrees:
            result['w'] = degrees
    if kind not in PICTURE_KINDS:
        return result
    entity = player(choice, states, keys, now, held) if kind == 'media' else choice[kind]
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
    return result


class ScreenSavers:
    """Every screen's choice, by its Home Assistant device, in one small file beside the layouts."""

    def __init__(self, path):
        self.path = path
        self.choices = {}
        try:
            data = json.loads(path.read_text())
            saved = data.get('screens') if isinstance(data, dict) and data.get('version') == 1 else None
        except (OSError, ValueError):
            saved = None
        for device, choice in (saved or {}).items():
            try:
                self.choices[str(device)] = validate(choice)
            except ValueError:
                LOG.warning('A screensaver choice was not readable and starts over')

    def get(self, device):
        choice = self.choices.get(device) or DEFAULT
        return {**DEFAULT, **choice, 'order': list(choice['order']), 'off': list(choice['off']),
                'more': list(choice.get('more') or ())}

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
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as handle:
                temporary = handle.name
                json.dump({'version': 1, 'screens': self.choices}, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            LOG.warning('Could not keep the screensavers (%s)', type(error).__name__)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
