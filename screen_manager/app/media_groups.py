"""Resolve a player's current group for native media controls."""
import re
import math

SERVICE = 'media_player.volume_mute'
EVENT = 'esphome.screen_media_groups'
GROUPING = 524288
PAGE_SIZE = 4


def supported(ha, entity):
    state = ha.states.get(entity, {})
    attrs = state.get('attributes') or {}
    features = attrs.get('supported_features', 0)
    return (isinstance(entity, str) and entity.startswith('media_player.') and
            type(features) is int and bool(features & GROUPING) and
            isinstance(attrs.get('group_members'), list))


def text(value, limit=80):
    """Bound UTF-8 bytes, as the device decoder does, and keep rows on one line."""
    return ' '.join(str(value).split()).encode()[:limit].decode(errors='ignore')


def snapshot(ha, fields):
    """Versioned, requested pages only. Never changes groups or playback."""
    if hasattr(ha, 'ws') and (ha.ws is None or ha.ws.closed):
        raise ConnectionError('Home Assistant is disconnected.')
    if not isinstance(fields, dict) or fields.get('schema') != '1':
        raise ValueError('Unsupported speaker view.')
    entity, selected = fields.get('entity'), fields.get('group', '')
    if not isinstance(entity, str) or not re.fullmatch(r'media_player\.[a-z0-9_]{1,107}', entity):
        raise ValueError('Invalid media player.')
    if not isinstance(selected, str) or (selected and not re.fullmatch(r'media_player\.[a-z0-9_]{1,107}', selected)):
        raise ValueError('Invalid player group.')
    try:
        page, gp, count = (int(fields.get(key, default)) for key, default in [('page', '0'), ('gp', '0'), ('count', '4')])
    except (ValueError, TypeError):
        raise ValueError('Invalid speaker page.') from None
    if min(page, gp) < 0 or max(page, gp) > 1024 or not 1 <= count <= PAGE_SIZE:
        raise ValueError('Invalid speaker page.')
    result = {'op': 'media_groups', 'schema': 1, 'e': entity, 'group': '', 'name': '',
              'gp': 0, 'group_pages': 1, 'page': 0, 'pages': 1, 'groups': [], 'speakers': []}
    if not supported(ha, entity):
        return result
    platform = ha.platform_of(entity)
    choices, seen = [], set()
    for candidate in sorted(ha.states):
        if not supported(ha, candidate) or ha.platform_of(candidate) != platform:
            continue
        # With no registry information only show this player's own group.
        if not platform and candidate != entity:
            continue
        try:
            group = members(ha, candidate)
        except ValueError:
            continue
        if any(ha.platform_of(member) != platform for member in group):
            continue
        signature = frozenset(group)
        if signature in seen:
            continue
        seen.add(signature)
        # HA's group_members puts the coordinator first; keep that order for rows.
        listed = ha.states[candidate]['attributes']['group_members']
        ordered = list(dict.fromkeys([*listed, candidate]))
        name = text(' + '.join(ha.states[e].get('attributes', {}).get('friendly_name') or e for e in ordered))
        choices.append({'e': ordered[0], 'n': name, 'members': ordered})
    choices.sort(key=lambda group: (group['n'].casefold(), group['e']))
    chosen = next((group for group in choices if selected and selected in group['members']), None)
    chosen = chosen or next((group for group in choices if entity in group['members']), None)
    if chosen is None:
        return result
    result.update(group=chosen['e'], name=chosen['n'])
    result['group_pages'] = max(1, math.ceil(len(choices) / count))
    result['gp'] = min(gp, result['group_pages'] - 1)
    result['groups'] = [{k: group[k] for k in ('e', 'n')} for group in choices[result['gp'] * count:][:count]]
    result['pages'] = max(1, math.ceil(len(chosen['members']) / count))
    result['page'] = min(page, result['pages'] - 1)
    for member in chosen['members'][result['page'] * count:][:count]:
        state = ha.states[member]
        attrs = state.get('attributes') or {}
        volume = attrs.get('volume_level')
        valid = type(volume) in (int, float) and math.isfinite(volume) and 0 <= volume <= 1
        features = attrs.get('supported_features', 0)
        result['speakers'].append({'e': member, 'n': text(attrs.get('friendly_name') or member),
            'v': round(volume * 100) if valid else -1, 'muted': attrs.get('is_volume_muted') is True,
            'enabled': valid and state.get('state') not in {'unavailable', 'unknown'} and type(features) is int and bool(features & 4)})
    return result


def preview_answer(ha, command):
    if (not isinstance(command, dict) or command.get('service') != EVENT or
            command.get('event') is not True or command.get('templates')):
        raise ValueError('A firmware speaker request is required.')
    fields = command.get('data')
    allowed = {'inbox', 'entity', 'group', 'schema', 'page', 'gp', 'count', 'session', 'rev', 'view'}
    if (not isinstance(fields, dict) or set(fields) - allowed or
            any(not isinstance(v, str) or len(v) > 160 for v in fields.values()) or
            any(not re.fullmatch(r'[0-9a-f]{16}', fields.get(key, '')) for key in ('session', 'rev')) or
            not re.fullmatch(r'[0-9]{1,10}', fields.get('view', ''))):
        raise ValueError('Invalid firmware speaker request.')
    return {**snapshot(ha, fields), 'session': fields['session'], 'rev': fields['rev'], 'view': int(fields['view'])}


def mute_template(entity):
    # ESPHome lets HA evaluate this at command time, after any regrouping.
    return "{{ (['" + entity + "'] + (state_attr('" + entity + "', 'group_members') or [])) | unique | list }}"


def members(ha, entity):
    group = (ha.states.get(entity, {}).get('attributes') or {}).get('group_members') or []
    if not isinstance(group, list):
        raise ValueError('The player has an invalid group.')
    result = []
    for member in [entity, *group]:
        if (not isinstance(member, str) or len(member) > 120 or
                not re.fullmatch(r'media_player\.[a-z0-9_]+', member) or member not in ha.states):
            raise ValueError('The player group contains an unknown media player.')
        if member not in result:
            result.append(member)
    return result


async def mute_data(ha, targets, muted):
    if type(muted) is not bool:
        raise ValueError('A mute state is required.')
    for entity in targets:
        if ha.states[entity].get('state') in {'unavailable', 'unknown'}:
            raise ValueError('A speaker in the group is unavailable.')
        actions = await ha.entity_actions(entity)
        if actions is None:
            raise ConnectionError('Home Assistant actions are not available.')
        if SERVICE not in actions:
            raise ValueError('A speaker in the group does not support mute.')
    return {'entity_id': targets[0] if len(targets) == 1 else targets, 'is_volume_muted': muted}


async def firmware_mute(ha, service, fields, templates):
    entity = fields.get('entity_id', '')
    if (service != SERVICE or set(fields) != {'entity_id', 'is_volume_muted'} or
            fields['is_volume_muted'] not in ('true', 'false') or
            templates != {'entity_id': mute_template(entity)}):
        raise ValueError('This templated preview action is not supported.')
    return await mute_data(ha, members(ha, entity), fields['is_volume_muted'] == 'true')
