"""What Home Assistant says an entity can do (app 0.2.67).

Home Assistant describes each action with the entities it works on: its `target`, filtered by domain, integration,
device class and supported features. Since 2025.12 it also answers `get_services_for_target` with the actions that fit
one entity. ESP Screens asks it instead of keeping lists of its own, so a device or an integration that brings an action
works without an update: a cover gets On / off because Home Assistant lists `cover.toggle` for it, a speaker that cannot
turn on and off doesn't. `local_actions` gives the same answer from the action descriptions for an older Home Assistant.

What stays ours is which action each of our widgets sends (INLINE, CONTROLS): a small slider on a light is `light.turn_on` with a
brightness, so it only fits a light for which Home Assistant offers that field.
"""
import re

import core
from core import attribute_word, state_word
import header_bar
import history_card
from i18n import t

# Screen widgets and the Home Assistant action behind them: (action, field or None). A widget fits an entity when Home
# Assistant lists one of its actions for it, and, where a field is named, offers that field for the entity.
TOGGLE = '{domain}.toggle'
INLINE = {
    'light': (('light.turn_on', 'brightness_pct'),),
    'fan': (('fan.set_percentage', None),),
    'cover': (('cover.set_cover_position', None),),
    'media_player': (('media_player.volume_set', None),),
    'number': (('number.set_value', None),),
    'input_number': (('input_number.set_value', None),),
}
CONTROLS = {
    'climate': {'setpoint': (('climate.set_temperature', None),), 'mode': (('climate.set_hvac_mode', None),)},
    'switch': {'toggle': (('switch.toggle', None),)},
    'input_boolean': {'toggle': (('input_boolean.toggle', None),)},
    'light': {'toggle': (('light.toggle', None),), 'brightness': INLINE['light']},
    'fan': {'toggle': (('fan.toggle', None),), 'speed': INLINE['fan']},
    'vacuum': {'buttons': tuple((action, None) for action in ('vacuum.start', 'vacuum.pause', 'vacuum.stop', 'vacuum.return_to_base', 'vacuum.turn_on'))},
    'cover': {'buttons': tuple((action, None) for action in ('cover.open_cover', 'cover.close_cover', 'cover.stop_cover')),
              'position': INLINE['cover'],
              'tilt': tuple((action, None) for action in ('cover.set_cover_tilt_position', 'cover.open_cover_tilt',
                                                         'cover.close_cover_tilt', 'cover.stop_cover_tilt'))},
    'media_player': {'volume': (('media_player.volume_set', None), ('media_player.volume_mute', None)),
                     'playback': tuple((action, None) for action in ('media_player.media_play_pause', 'media_player.media_play',
                                                                     'media_player.media_pause', 'media_player.media_next_track',
                                                                     'media_player.media_previous_track'))},
    'number': {'stepper': INLINE['number'], 'slider': INLINE['number']},
    'input_number': {'stepper': INLINE['input_number'], 'slider': INLINE['input_number']},
    'select': {'stepper': (('select.select_option', None),)},
    'input_select': {'stepper': (('input_select.select_option', None),)},
    'timer': {'buttons': (('timer.start', None), ('timer.cancel', None))},
    'scene': {'run': (('scene.turn_on', None),)},
    'script': {'run': (('script.turn_on', None),)},
    'button': {'run': (('button.press', None),)},
    'input_button': {'run': (('input_button.press', None),)},
}
# Weather forecast bits (WeatherEntityFeature): the forecast card draws days.
WEATHER_DAILY = 1


def _as_list(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _features(attributes):
    value = (attributes or {}).get('supported_features')
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def entity_filter_matches(entity_filter, entity_id, attributes, platform):
    """One `target.entity` filter of an action description, as Home Assistant applies it to an entity: every named
    condition must hold. A `supported_features` entry is a mask the entity must support completely, and any entry will
    do (the action's own required features)."""
    if not isinstance(entity_filter, dict):
        return False
    domain = entity_id.split('.', 1)[0]
    domains = _as_list(entity_filter.get('domain'))
    if domains and domain not in domains:
        return False
    integration = entity_filter.get('integration')
    if integration and integration != platform:
        return False
    classes = _as_list(entity_filter.get('device_class'))
    if classes and (attributes or {}).get('device_class') not in classes:
        return False
    masks = [mask for mask in _as_list(entity_filter.get('supported_features')) if isinstance(mask, int)]
    if masks and not any(_features(attributes) & mask == mask for mask in masks):
        return False
    return True


def target_matches(target, entity_id, attributes, platform):
    """Whether an action works on this entity. An action without a target is not an entity action; one whose target
    names no entity filter takes every entity (homeassistant.toggle)."""
    if not isinstance(target, dict):
        return False
    filters = target.get('entity')
    if filters is None or filters == []:
        return 'entity' not in target or filters == []
    return any(entity_filter_matches(item, entity_id, attributes, platform) for item in _as_list(filters))


def local_actions(services, entity_id, attributes, platform):
    """`get_services_for_target` for one entity, from the action descriptions: for a Home Assistant before 2025.12."""
    found = []
    for domain, actions in (services or {}).items():
        if not isinstance(actions, dict):
            continue
        for name, description in actions.items():
            if isinstance(description, dict) and 'target' in description and target_matches(description['target'], entity_id, attributes, platform):
                found.append(f'{domain}.{name}')
    return sorted(found)


def find_field(description, name):
    """A field of an action description, also inside a section (light.turn_on keeps some under `advanced_fields`)."""
    fields = (description or {}).get('fields') or {}
    if name in fields and isinstance(fields[name], dict):
        return fields[name]
    for value in fields.values():
        if isinstance(value, dict) and isinstance(value.get('fields'), dict) and name in value['fields']:
            return value['fields'][name]
    return None


def field_matches(field, attributes):
    """Whether Home Assistant offers a field for this entity: its `filter` names supported features (any one) or
    attribute values (any one); a field without a filter is always there."""
    field_filter = (field or {}).get('filter')
    if not isinstance(field_filter, dict) or not field_filter:
        return True
    features = [mask for mask in _as_list(field_filter.get('supported_features')) if isinstance(mask, int)]
    if features and any(_features(attributes) & mask for mask in features):
        return True
    for attribute, values in (field_filter.get('attribute') or {}).items():
        current = (attributes or {}).get(attribute)
        wanted = _as_list(values)
        if isinstance(current, (list, tuple)) and any(value in current for value in wanted):
            return True
        if not isinstance(current, (list, tuple)) and current in wanted:
            return True
    return False


def _fits(requirements, actions, attributes, services):
    for action, field in requirements:
        if action not in actions:
            continue
        if field is None:
            return True
        domain, name = action.split('.', 1)
        found = find_field(((services or {}).get(domain) or {}).get(name), field)
        if found is not None and field_matches(found, attributes):
            return True
    return False


def capabilities(entity_id, actions, state, services):
    """What the editor may offer for this entity, in Home Assistant's own terms: On / off, a small slider, which direct
    controls and which displays. `actions` are the actions Home Assistant lists for the entity."""
    domain = entity_id.split('.', 1)[0]
    attributes = (state or {}).get('attributes') or {}
    actions = set(actions or ())
    displays = ['standard', 'watch']
    if domain == 'sensor':
        # The graph draws numbers; a status sensor (a washing machine's programme) has none.
        if history_card.kind(entity_id, state) == 'line':
            displays.append('graph')
    elif domain == 'weather':
        features = attributes.get('supported_features')
        # An entity that reports no features yet (unavailable) keeps the forecast, as forecast_kinds does.
        if not isinstance(features, int) or isinstance(features, bool) or features & WEATHER_DAILY:
            displays.append('forecast')
    elif domain == 'sun':
        displays.append('sunpath')
    elif domain in ('camera', 'image'):
        # A live picture on the tile (app 0.2.91): the editor offers it on a board that draws images. A camera's state
        # ("Idle") makes no large value, and the layout refuses one (core.DISPLAYS, app 0.3.8).
        displays = ['standard', 'live']
    elif domain == 'media_player':
        # The album cover in the icon's place (app 0.2.92), a Guition again.
        displays.append('cover')
    controls = [key for key, requirements in CONTROLS.get(domain, {}).items()
                if _fits(requirements, actions, attributes, services)
                and not (domain == 'climate' and key == 'setpoint'
                         and isinstance(attributes.get('supported_features'), int)
                         and not attributes['supported_features'] & 1)]
    if domain == 'cover' and 'tilt' in controls:
        controls += [key + '_tilt' for key in ('buttons', 'position') if key in controls]
    if domain == 'climate' and 'setpoint' in controls and 'mode' in controls:
        controls.append('setpoint_mode')
    return {
        'toggle': TOGGLE.format(domain=domain) in actions,
        'inline': domain in INLINE and _fits(INLINE[domain], actions, attributes, services),
        'controls': controls,
        'displays': displays,
    }


def fields_for(description, attributes):
    """The fields of an action Home Assistant offers for this entity, in its own order, sections flattened."""
    found = []
    for key, field in ((description or {}).get('fields') or {}).items():
        if not isinstance(field, dict):
            continue
        if isinstance(field.get('fields'), dict) and 'selector' not in field:
            found += [(inner_key, inner) for inner_key, inner in field['fields'].items() if isinstance(inner, dict) and field_matches(inner, attributes)]
        elif field_matches(field, attributes):
            found.append((key, field))
    return found


def attribute_options(attributes, attribute):
    """The values an entity offers for one of its attributes, where a `state` selector asks for one: an effect from
    effect_list, a source from source_list, a fan mode from fan_modes, a speed from supported_speeds."""
    for key in (f'{attribute}_list', f'{attribute}s', f'available_{attribute}s', f'supported_{attribute}s'):
        values = (attributes or {}).get(key)
        if isinstance(values, list) and values and all(isinstance(value, (str, int, float)) and not isinstance(value, bool) for value in values):
            return [str(value) for value in values][:60]
    return None


def answers_only(description):
    """An action that must return data (weather.get_forecasts): a tap has nowhere to show it."""
    return ((description or {}).get('response') or {}).get('optional') is False


def field_choice(base, key, field, attributes, names):
    """One field for the editor: Home Assistant's name, description and selector, and for a `state` selector the values
    this entity has for that attribute."""
    selector = field.get('selector') or {}
    found = {'key': key, 'name': names.get(f'{base}.fields.{key}.name') or field.get('name') or key,
             'description': names.get(f'{base}.fields.{key}.description') or field.get('description') or '',
             'required': bool(field.get('required')), 'selector': selector}
    if 'example' in field:
        found['example'] = field['example']
    attribute = (selector.get('state') or {}).get('attribute') if isinstance(selector.get('state'), dict) else None
    options = attribute_options(attributes, attribute) if attribute else None
    if options:
        found['options'] = options
    return found


def action_choices(entity_id, actions, state, services, names, platform=None):
    """Perform action in the editor (app 0.2.67): every action Home Assistant offers for the entity, under the names and
    descriptions Home Assistant shows (frontend/get_translations, `services`), with the fields it offers for this entity.
    The entity's own domain comes first, then its integration's actions, then Home Assistant's general ones."""
    domain = entity_id.split('.', 1)[0]
    attributes = (state or {}).get('attributes') or {}
    names = names or {}
    found = []
    for action in sorted(actions or ()):
        action_domain, service = action.split('.', 1)
        description = ((services or {}).get(action_domain) or {}).get(service) or {}
        if answers_only(description):
            continue
        base = f'component.{action_domain}.services.{service}'
        found.append({
            'action': action,
            'name': names.get(f'{base}.name') or description.get('name') or action,
            'description': names.get(f'{base}.description') or description.get('description') or '',
            'fields': [field_choice(base, key, field, attributes, names) for key, field in fields_for(description, attributes)],
        })
    order = lambda item: (0 if item['action'].startswith(domain + '.') else 1 if platform and item['action'].startswith(platform + '.') else 2,
                          item['name'].casefold())
    return sorted(found, key=order)


def action_problem(entity_id, label, action, state, actions, services):
    """Why Home Assistant wouldn't take a tap's own action for this entity, as the sentence a save gets; None when it
    would, or while Home Assistant can't say."""
    name, data = action.get('action'), action.get('data') or {}
    if actions is None:
        return None
    if name not in actions:
        return t('addon.errors.home_assistant.action_not_offered', action=name, name=label)
    action_domain, service = name.split('.', 1)
    description = ((services or {}).get(action_domain) or {}).get(service)
    if description is None:
        return None
    if answers_only(description):
        return t('addon.errors.home_assistant.action_answers_only', action=name)
    fields = dict(fields_for(description, (state or {}).get('attributes') or {}))
    for key in data:
        if key not in fields:
            return t('addon.errors.home_assistant.no_such_field', field=key, action=name, name=label)
    for key, field in fields.items():
        if field.get('required') and key not in data:
            return t('addon.errors.home_assistant.field_needed', action=name, field=key)
    return None


def refusal(entity_id, name, key, value):
    """The sentence a save or a tile event gets for a setting Home Assistant doesn't support for this entity."""
    label = name or entity_id
    if key == 'tap':
        return t('addon.errors.home_assistant.no_on_off', name=label)
    if key == 'inline':
        return t('addon.errors.home_assistant.no_small_slider', name=label)
    if key == 'display' and value == 'graph':
        return t('addon.errors.home_assistant.no_graph', name=label)
    if key == 'display' and value == 'forecast':
        return t('addon.errors.home_assistant.no_forecast', name=label)
    return t('addon.errors.home_assistant.no_control', name=label)


def unsupported(tile, previous, caps):
    """The first setting of a tile that Home Assistant doesn't support and that isn't already saved like this, as
    (key, value), or None. Settings a screen already has stay, also when Home Assistant no longer supports them: they
    get a warning in the editor, and a save never fails on a tile nobody changed."""
    if caps is None:
        return None
    options, before = tile.get('options') or {}, (previous or {}).get('options') or {}
    checks = (
        ('tap', options.get('tap') == 'toggle' and not caps.get('toggle')),
        ('inline', options.get('inline') == 'slider' and not caps.get('inline')),
        ('controls', options.get('controls', 'none') != 'none' and options.get('controls') not in caps.get('controls', ())),
        ('display', options.get('display') in ('graph', 'forecast') and options.get('display') not in caps.get('displays', ())),
    )
    for key, refused in checks:
        if refused and (previous is None or before.get(key) != options.get(key)):
            return key, options.get(key)
    return None



# Domains whose tiles and cards show the raw state where no word of the screen's own fits (app 0.2.67): the app sends
# Home Assistant's word for it. The screen's own words (On, Off, Docked, a binary sensor's Open) stay as they are.
WORD_DOMAINS = frozenset(('cover', 'media_player', 'vacuum', 'select', 'input_select', 'sensor'))
WORD_BYTES = 32


def screen_word(entity_id, state, attributes, entry, words):
    """The word a tile shows for its state, where the screen would show the raw state: folded to the glyphs its fonts
    carry and short enough for a tile; None when Home Assistant has no other word."""
    domain = entity_id.split('.', 1)[0]
    if domain not in WORD_DOMAINS or (domain == 'sensor' and header_bar.numeric(state) is not None):
        return None
    word = state_word(entity_id, state, attributes, entry, words)
    if not word:
        return None
    word = header_bar.short(header_bar.clean_text(word), WORD_BYTES)
    return word if word and word != state else None


def chip_words(extra, entity_id, states, device, words):
    """A vacuum card's chips in Home Assistant's words where the screen has no short label of its own (app 0.2.67): a
    cleaning mode or mop intensity as the integration names the select's option, a suction level as it names the
    vacuum's fan speed. The screen's own labels ("Vac & mop", "Normal") stay; `extra` is changed in place."""
    if not isinstance(extra, dict) or not words:
        return extra
    entries = {item.get('entity_id'): item for item in device or () if isinstance(item, dict)}
    def relabel(row, word):
        if not isinstance(row, dict) or not isinstance(row.get('o'), list) or not isinstance(row.get('l'), list):
            return
        for index, value in enumerate(row['o'][:len(row['l'])]):
            found = None if value in core.VACUUM_LABELS else word(value)
            if found:
                row['l'][index] = header_bar.short(header_bar.clean_text(found), 24) or row['l'][index]
    for key in ('mode', 'water'):
        row = extra.get(key)
        select = row.get('e') if isinstance(row, dict) else None
        if isinstance(select, str):
            attributes = (states.get(select) or {}).get('attributes')
            relabel(row, lambda value: state_word(select, value, attributes, entries.get(select), words))
    attributes = (states.get(entity_id) or {}).get('attributes')
    relabel(extra.get('fan'), lambda value: attribute_word(entity_id, 'fan_speed', value, attributes, entries.get(entity_id), words))
    return extra


# ---- The second line of a tile (app 0.2.105, firmware 0.2.90+) ----
# A tile's second line is the line the screen works out itself, nothing at all, words of your own, or a value of
# the entity. That last list is Home Assistant's, not ours: its frontend translations name the attributes a person
# may see (`component.<domain>.entity_component._.state_attributes.<attr>.name`), in the language they are asked
# for, and the app already holds them for the screens' language and English (Manager.words_by_language). So a
# script offers Last triggered and Run mode, a player offers Artist, Album and Volume, and a scene - which Home
# Assistant names no attribute of - offers none, which is why words of your own exist.
SUBTITLE_BYTES = 64            # what the screen keeps of a finished line
SUBTITLE_NAME = re.compile(r'component\.([a-z_]+)\.entity_component\._\.state_attributes\.([a-z_0-9]+)\.name')
# Attributes every entity carries that are the tile's name, its icon or the screen's own business, never its
# second line. Home Assistant names them, so the rule that keeps them out is what they are used for here.
SUBTITLE_SKIP = frozenset(('friendly_name', 'icon', 'entity_picture', 'supported_features', 'device_class'))


def subtitle_attributes(entity_id, state, words):
    """[{'key', 'name'}] of the values of this entity a tile's second line may say: the attributes Home Assistant
    names, that this entity really has, and that are not already the tile's name or icon. Sorted by name, in the
    language `words` was asked for. Empty for an entity Home Assistant names no attribute of."""
    if not isinstance(entity_id, str) or not isinstance(words, dict) or not words:
        return []
    domain = entity_id.split('.', 1)[0]
    attributes = (state or {}).get('attributes') or {}
    found = {}
    for key, name in words.items():
        match = SUBTITLE_NAME.fullmatch(key)
        if not match or match[1] != domain:
            continue
        attribute = match[2]
        if attribute in SUBTITLE_SKIP or attribute not in attributes:
            continue
        value = attributes[attribute]
        # A list or a mapping is not a line on a tile; a value nobody can read is not worth offering.
        if isinstance(value, (list, tuple, dict)) or value is None:
            continue
        found[attribute] = str(name)
    return [{'key': key, 'name': found[key]} for key in sorted(found, key=lambda k: found[k].casefold())]


def subtitle_choice(tile):
    """('none'|'text'|'attr', value) of a tile's stored second line, or None when it is the line the screen works
    out itself. The stored form is one string beside the other tile options: "none", "text:<words>", "attr:<name>"."""
    choice = (tile.get('options') or {}).get('sub')
    if not isinstance(choice, str) or not choice or choice == 'auto':
        return None
    if choice == 'none':
        return ('none', '')
    for kind in ('text', 'attr'):
        if choice.startswith(kind + ':'):
            return (kind, choice[len(kind) + 1:])
    return None


def subtitle_message(tile, state):
    """What a tile's chosen second line adds to its state message: `s` for a finished line, `sm` for a moment in
    time. Empty when the tile says the line itself, says nothing, or says words of its own - the screen holds
    those three in the option and keeps drawing them while Home Assistant is away."""
    choice = subtitle_choice(tile)
    if not choice or choice[0] != 'attr':
        return {}
    value = ((state or {}).get('attributes') or {}).get(choice[1])
    if value is None or isinstance(value, (list, tuple, dict)):
        return {}
    # A value is written the way what it is asks for, not the way its name suggests: a moment in time goes as
    # seconds, so the screen says it in its own words and its own clock the way it already says when a script
    # last ran, instead of a second wording of the same thing over here. Anything else goes as the text it is,
    # and the screen writes no number of its own into a line it was handed.
    if isinstance(value, bool):
        return {'s': core.screen_t('screen.ha.on' if value else 'screen.ha.off')}
    if isinstance(value, str):
        moment = core.epoch(value)
        if moment:
            return {'sm': moment}
    return {'s': header_bar.short(header_bar.clean_text(str(value)), SUBTITLE_BYTES)}
