"""Where a media player plays, on a screen: the rows of its speaker menu and the inputs it may switch to.

Everything here is what Home Assistant says, read in the meaning Home Assistant gives it:

* `source` and `source_list` are a player's input source (media_player's docs). Sonos lists its TV input and its
  favourites there, a TV its HDMI ports. The screen offers those behind an input key, never as speakers.
  The one exception is an integration whose sources are the devices it plays on, as Home Assistant's Spotify
  integration documents for Spotify Connect (SOURCE_SPEAKERS): those names are speakers.
* A player that reports GROUPING plays together with others of its own integration (`media_player.join`,
  `media_player.unjoin`); `group_members` says who plays with it now. Home Assistant's own media dialog offers the
  players of the same integration that report GROUPING, and so does the menu.
* A speaker whose library holds a player's account plays that player's library: Home Assistant's Sonos integration
  lists a Spotify account in every Sonos's library once Spotify is linked (the folder's id is the account's
  config entry), and `play_media` on the Sonos plays a Spotify item. When Home Assistant lists it, it plays.

A Spotify tile that plays on such a speaker follows it (the target): Spotify does not report what a Sonos plays
through its own Spotify service, so the card shows the speaker's state and its keys act on the speaker until the
player plays itself again.
"""
import catalogue
import core

# The name a screen's hello lists when its firmware draws the rows below: a mark, a key and a volume per speaker,
# the inputs behind their own key, and a target its media keys act on.
FEATURE = 'speaker_groups'
SPEAKER_EVENT = 'esphome.screen_speaker'
# Integrations whose source_list names the devices they play on (Spotify Connect), as their docs say.
SOURCE_SPEAKERS = ('spotify', 'spotifyplus')
ROWS = 16              # rows a menu lists at most
NAME_LIMIT = 48        # bytes of a name
GROUPING = catalogue.bits('media_player', 'GROUPING')
VOLUME_SET = catalogue.bits('media_player', 'VOLUME_SET')
PLAY_MEDIA = catalogue.bits('media_player', 'PLAY_MEDIA')
# A row's flags as the screen reads them: plays here (ticked, or in the group), and has a key to join or leave.
ON, GROUPS = 1, 2
ACTIVE = ('playing', 'paused')
GONE = ('unavailable', 'unknown', 'off')


def short(value, limit=NAME_LIMIT):
    return core.short(str(value if value is not None else '').strip(), limit)


def features(state):
    value = ((state or {}).get('attributes') or {}).get('supported_features')
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def has_group_members(state):
    """Whether Home Assistant reports this player as a pre-existing group."""
    found = ((state or {}).get('attributes') or {}).get('group_members')
    return isinstance(found, list) and any(isinstance(e, str) for e in found)


def name_of(entity, states):
    """The name Home Assistant shows for a player."""
    state = states.get(entity) or {}
    return short((state.get('attributes') or {}).get('friendly_name') or entity.split('.', 1)[-1])


def members(entity, states):
    """Who plays with a player now, itself first: Home Assistant's group_members, or the player alone."""
    found = ((states.get(entity) or {}).get('attributes') or {}).get('group_members')
    found = [e for e in found if isinstance(e, str)] if isinstance(found, list) else []
    return [entity] + [e for e in found if e != entity]


def volume_of(entity, states):
    """A player's volume as the screen shows it, 0 to 100, or -1 for a player that sets none."""
    state = states.get(entity) or {}
    level = (state.get('attributes') or {}).get('volume_level')
    if not features(state) & VOLUME_SET or not isinstance(level, (int, float)) or isinstance(level, bool):
        return -1
    return max(0, min(100, round(level * 100)))


def group_mates(entity, states, platform_of):
    """The players `entity` may play together with: those of its own integration that report GROUPING."""
    platform = platform_of(entity)
    if not platform or not features(states.get(entity)) & GROUPING:
        return []
    return [e for e, state in states.items()
            if isinstance(e, str) and e.startswith('media_player.') and e != entity and platform_of(e) == platform
            and features(state) & GROUPING and not has_group_members(state) and (state or {}).get('state') not in GONE[:2]]


def holds_account(root_ids, entry_id):
    """Whether a player's library top lists the account behind `entry_id` (a config entry of the player's integration)."""
    if not entry_id:
        return False
    entry = str(entry_id).lower()
    return any(isinstance(i, str) and i.lower().rstrip('/').endswith(entry) for i in root_ids or ())


def target_of(entity, states, output):
    """The speaker a player's card follows: the one this app started its music on, until the player itself plays again
    or the speaker is gone; None otherwise."""
    if not output or output == entity:
        return None
    # Paused is what this app leaves the player in when it moves the music: only playing again takes the card back.
    if (states.get(entity) or {}).get('state') == 'playing':
        return None
    if (states.get(output) or {}).get('state') in GONE:
        return None
    return output


def menu(entity, states, platform_of, holders=(), output=None):
    """The speaker menu and the inputs of a player.

    Returns {'rows': [{name, source, entity, on, groups, volume}], 'inputs': [names], 'input': name or None,
    'target': entity or None, 'pill': the words of the pill}. `holders` are the players whose library holds this
    player's account (in the order to list them), `output` the speaker this app last started its music on."""
    state = states.get(entity) or {}
    attrs = state.get('attributes') or {}
    platform = platform_of(entity)
    sources = [short(s) for s in attrs.get('source_list') or [] if isinstance(s, str) and s.strip()]
    source = short(attrs.get('source')) or None
    rows, inputs = [], []
    target = target_of(entity, states, output)

    def row(name, source=None, entity=None, on=False, groups=False, volume=-1, plays=False):
        # One row per name: a Spotify Connect device that is also a speaker of its own is one speaker.
        found = next((r for r in rows if r['name'] == name), None)
        if found is None:
            found = {'name': name, 'source': None, 'entity': None, 'on': False, 'groups': False, 'volume': -1, 'plays': False}
            rows.append(found)
        found['plays'] = found['plays'] or plays
        found['source'] = found['source'] or source
        found['entity'] = found['entity'] or entity
        found['on'] = found['on'] or on
        found['groups'] = found['groups'] or groups
        found['volume'] = max(found['volume'], volume)

    if platform in SOURCE_SPEAKERS:
        for name in sources:
            row(name, source=name, on=not target and name == source)
    else:
        inputs = sources
    # A player that groups: itself and those it may play with, the ones with it now ticked, each with its volume.
    mates = group_mates(entity, states, platform_of)
    if mates:
        now = members(entity, states)
        order = now + sorted((e for e in mates if e not in now), key=lambda e: name_of(e, states).lower())
        for other in order:
            if other != entity and other not in mates:
                continue
            on = other in now
            row(name_of(other, states), entity=other, on=on, groups=True, volume=volume_of(other, states) if on else -1)
    # Existing speaker entities can also be playback destinations, even when they belong to another integration and
    # cannot be joined dynamically. A non-empty group_members marks a pre-existing group; the HA media-player
    # device_class identifies speaker entities such as Google Cast and Music Assistant players.
    destinations = [e for e, item in states.items()
                    if isinstance(e, str) and e.startswith('media_player.') and e != entity and e not in holders
                    and (item or {}).get('state') not in GONE[:2]
                    and (((item or {}).get('attributes') or {}).get('device_class') == 'speaker' or has_group_members(item))]
    destinations.sort(key=lambda e: (not has_group_members(states.get(e)), name_of(e, states).lower()))
    for other in destinations:
        if any(r['entity'] == other for r in rows):
            continue
        on = bool(target and other in members(target, states))
        row(name_of(other, states), entity=other, on=on, groups=False,
            volume=volume_of(other, states) if on else -1, plays=True)
    # Speakers that play this player's library: the one it follows and those with it are ticked, and they group
    # among themselves. Before anything plays on one, every speaker that groups shows its plus all the same: the first
    # one starts the music there, the next ones join it.
    with_target = members(target, states) if target else []
    lead_mates = set(group_mates(target, states, platform_of)) if target else set()
    for other in holders:
        if other == entity or (states.get(other) or {}).get('state') in GONE[:2]:
            continue
        on = other in with_target
        groups = ((other == target or other in lead_mates) if target else
                  bool(features(states.get(other)) & GROUPING) and not has_group_members(states.get(other)))
        row(name_of(other, states), entity=other, on=on, groups=groups, volume=volume_of(other, states) if on else -1, plays=True)
    rows = rows[:ROWS]
    if target:
        pill = name_of(target, states) + (f' + {len(with_target) - 1}' if len(with_target) > 1 else '')
    elif mates:
        together = len(members(entity, states))
        pill = name_of(entity, states) + (f' + {together - 1}' if together > 1 else '')
    else:
        pill = source if platform in SOURCE_SPEAKERS and source else ''
    return {'rows': rows, 'inputs': inputs[:ROWS], 'input': source if inputs else None, 'target': target, 'pill': short(pill)}


def extras(found):
    """The menu as a screen of FEATURE reads it with the player's state: the pill's words (`so`), the rows' names
    (`sl`), flags (`sf`) and volumes (`sv`), the inputs (`in`) and the one in use (`ic`), and the speaker the card
    follows (`ct`)."""
    result = {}
    if found['pill']:
        result['so'] = found['pill']
    if found['rows']:
        result['sl'] = [r['name'] for r in found['rows']]
        result['sf'] = [(ON if r['on'] else 0) | (GROUPS if r['groups'] else 0) for r in found['rows']]
        if any(r['volume'] >= 0 for r in found['rows']):
            result['sv'] = [r['volume'] for r in found['rows']]
    if found['inputs']:
        result['in'] = found['inputs']
        if found['input']:
            result['ic'] = found['input']
    if found['target']:
        result['ct'] = found['target']
    return result


def find(found, name):
    """The row of a menu by its name, or None."""
    return next((r for r in found['rows'] if r['name'] == name), None) if isinstance(name, str) else None


def plan(entity, found, row, op, states, volume=None):
    """What a tap in the menu asks of Home Assistant: a list of (domain, service, data), and the speaker the player
    follows afterwards ('' to forget it, None to keep it as it is)."""
    if row is None:
        return [], None
    other = row['entity']
    lead = found['target'] or entity
    if op == 'volume' and other and isinstance(volume, int):
        return [('media_player', 'volume_set', {'entity_id': other, 'volume_level': max(0, min(100, volume)) / 100})], None
    if op == 'leave' and other and row['on'] and row['groups']:
        # The last one left keeps playing: a group of one has nothing to leave.
        together = members(lead, states)
        if len(together) < 2:
            return [], None
        follow = None
        if other == found['target']:
            follow = next((e for e in together if e != other), '')
        return [('media_player', 'unjoin', {'entity_id': other})], follow
    if op in ('join', 'pick') and other and row['groups'] and not row['on'] and not (row['plays'] and not found['target']):
        return [('media_player', 'join', {'entity_id': lead, 'group_members': [other]})], None
    if op == 'join' and row['plays'] and not found['target']:
        op = 'pick'   # the first speaker of a library: the music starts there, the next ones join it
    if op != 'pick' or row['on']:
        return [], None
    if row['source']:
        # A Spotify Connect device: Spotify moves the music there, and the card follows the player again.
        return [('media_player', 'select_source', {'entity_id': entity, 'source': row['source']})], ''
    if other:
        # A speaker that plays this player's library: what plays now goes there, and the card follows it.
        attrs = (states.get(entity) or {}).get('attributes') or {}
        playing = (states.get(entity) or {}).get('state') == 'playing' and isinstance(attrs.get('media_content_id'), str)
        steps = []
        if playing:
            steps = [('media_player', 'play_media', {'entity_id': other, 'media_content_type': attrs.get('media_content_type') or 'music',
                                                     'media_content_id': attrs['media_content_id']}),
                     ('media_player', 'media_pause', {'entity_id': entity})]
        return steps, other
    return [], None
