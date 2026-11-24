"""A plugin's own example of its tiles, for the editor's library (docs/EMULATOR_ARCHITECTURE.md, "Plugins").

The library shows a plugin's tile before it is on a page, at each size it can be, drawn by the plugin's own code in the
editor's preview. A tile nobody set up yet has nothing to say ("Choose a stop"), so there it is shown with the plugin's
own example instead: `preview.yaml` beside its manifest, the file its maker wrote for the plugins repository's bench
(its docs/PREVIEW.md): the tiles to show with their options, the answer of each fetch as the web service gives it, the
entities as Home Assistant has them, and moments written from now ("{now+4m}") so a countdown never runs out.

An example goes through the app's own shaping, as on a screen: the fetch's map, the entity's part, the bounds of the
message (Plugins.tile_message). Only where that reads the world is something else in hand: the answers of preview.yaml
for the web service, its states for Home Assistant. Nothing is asked of a web service or of Home Assistant for it.

Pure of the app's stores: plugins.py finds the file (a folder, or the plugin's commit on GitHub) and calls message().
"""
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

import plugin_fetch
import plugins

# A preview.yaml is text a maker wrote: larger than this is not one.
MAX_BYTES = 256 * 1024
ZONE = 'Europe/Amsterdam'
MOMENT = re.compile(r'\{(now|epoch)(?:([+-]\d+)([smhd]))?\}')
UNITS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}


def moments(value, zone, now):
    """preview.yaml's moments made from now: "{now+5m}" is the local time in five minutes as ISO text, "{epoch-2h}" two
    hours ago in seconds since 1970 (a number when it is the whole text)."""
    def at(match):
        return now + (int(match[2]) * UNITS[match[3]] if match[2] else 0)

    def word(match):
        moment = at(match)
        return str(int(moment)) if match[1] == 'epoch' else datetime.fromtimestamp(moment, ZoneInfo(zone)).strftime('%Y-%m-%dT%H:%M:%S')
    if isinstance(value, str):
        whole = MOMENT.fullmatch(value)
        if whole and whole[1] == 'epoch':
            return int(at(whole))
        return MOMENT.sub(word, value)
    if isinstance(value, list):
        return [moments(item, zone, now) for item in value]
    if isinstance(value, dict):
        return {key: moments(item, zone, now) for key, item in value.items()}
    return value


def read(text):
    """A preview.yaml as a mapping, or None when it is not one."""
    if not isinstance(text, (str, bytes)) or len(text) > MAX_BYTES:
        return None
    try:
        spec = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return spec if isinstance(spec, dict) else None


def example_of(spec, tile_id, span=None):
    """The example of one tile type: the first that is shown at this size (`sizes`, as "2x1"), else the first of the
    type; None when preview.yaml shows no tile of it."""
    examples = [item for item in spec.get('tiles') or [] if isinstance(item, dict) and item.get('tile') == tile_id]
    if not examples:
        return None
    return next((item for item in examples if span and span in (item.get('sizes') or [span])), examples[0])


class SampleFetcher:
    """Stands in for plugin_fetch.Fetcher: the answer of a fetch is the one preview.yaml gives for its id."""

    def __init__(self, answers):
        self.answers = answers

    async def get(self, plugin, manifest, fetch, values, secrets, **asked):
        return None, self.peek(plugin, fetch, values, secrets)

    def current(self, plugin, fetch, values, secrets, **asked):
        return None, self.peek(plugin, fetch, values, secrets)

    def peek(self, plugin, fetch, values, secrets, **asked):
        for read_ in fetch.get('reads') or ():
            name = f'{read_["option"]}.{read_["attribute"]}'
            if plugin_fetch.attribute_word(values.get(name), read_['decimals']) is None:
                raise plugin_fetch.FetchRefused(f'not filled in: {name}')
        data = self.answers.get(fetch['id'])
        if data is None:
            return None
        names = fetch.get('asked') or ()
        # One answer per value the screen asks with ("row=KL1234"): the one for the value given.
        if names and isinstance(data, dict) and data and all(
                isinstance(key, str) and '=' in key and key.split('=', 1)[0] in names for key in data):
            data = next((answer for key, answer in data.items()
                         if str(values.get(key.split('=', 1)[0], '')) == key.split('=', 1)[1]), None)
            if data is None:
                return None
        return {'data': data, 'error': None, 'stale': False}


class ExampleApp(plugins.Plugins):
    """The app's plugin side with one plugin and no world: tile_message, values_of, tile_data and state_part are the
    app's own; the states are preview.yaml's and the fetcher answers from it."""

    def __init__(self, entry, states, answers, zone):
        self.entry = entry
        self.manager = type('Manager', (), {})()
        self.manager.ha = type('HA', (), {'states': states, 'time_zone': zone})()
        self.fetcher = SampleFetcher(answers)

    def known(self, plugin, inbox=None):
        return self.entry if plugin == self.entry.id else None

    def secret_values(self, entry, inbox=None):
        return {}


async def message(entry, spec, index, tile, span=None, now=None):
    """The state message of a plugin tile as its plugin's example shows it, or None when the plugin has no example of
    that tile type. `tile`: the compiled tile of the layout (its entity, name and options); the example gives its
    plugin options, its entity and its data."""
    tile_id = tile['entity'].split('.', 1)[1]
    example = example_of(spec, tile_id, span)
    if example is None or entry.tile(tile_id) is None:
        return None
    zone = spec.get('time_zone') if isinstance(spec.get('time_zone'), str) else ZONE
    # Moments are written from the start of this minute: asked again within it, an example is the same message, so the
    # editor's firmware is told of a change once a minute and not at every refresh, while a countdown still never runs
    # out. The screen's own clock counts the seconds in between.
    now = time.time() // 60 * 60 if now is None else now
    states = {entity: {'entity_id': entity, 'state': str(state.get('state', '')), 'attributes': dict(state.get('attributes') or {}),
                       'last_updated': datetime.fromtimestamp(now - 60, ZoneInfo('UTC')).isoformat()}
              for entity, state in (moments(spec.get('states') or {}, zone, now)).items() if isinstance(state, dict)}
    answers = moments({**(spec.get('answers') or {}), **(example.get('answers') or {})}, zone, now)
    options = {**(tile.get('options') or {}), 'plugin': dict(example.get('options') or {})}
    if isinstance(example.get('entity'), str):
        options['plugin_entity'] = example['entity']
    app = ExampleApp(entry, states, answers if isinstance(answers, dict) else {}, zone)
    # A tile without a name of its own takes the example's ("Centraal Station"), as its maker shows it.
    name = tile.get('name') or (example['name'] if isinstance(example.get('name'), str) else '')
    shown = await app.tile_message(index, {**tile, 'name': name, 'options': options})
    if 'data' in example:   # what the screen gets, as it is: a state the map cannot reach (a "wait")
        shown['x'] = moments(example['data'], zone, now)
    return shown
