"""Browser transport for firmware image requests, using the device image feed."""
import re
import camera_feed

# Firmware accepts HTTP image links. This virtual address is mapped to the
# authenticated ingress endpoint by the browser, never fetched over the network.
HOST = 'http://firmware-preview.invalid/'


async def answer(manager, data):
    if not isinstance(data, dict) or not isinstance(data.get('request'), dict) or not isinstance(data.get('shape'), dict):
        raise ValueError('An image request and preview shape are required.')
    shape, command = data['shape'], data['request']
    width, height = shape.get('width'), shape.get('height')
    if any(type(n) is not int or not 160 <= n <= 2560 for n in (width, height)):
        raise ValueError('Invalid preview image dimensions.')
    fields = command.get('data')
    if command.get('service') != 'esphome.screen_camera' or command.get('event') is not True or command.get('templates'):
        raise ValueError('Only firmware image events are accepted.')
    # `idx`: the tiles of a live strip by index (firmware 0.16.0+), which name a map's tile on the mockup; `dark`: the
    # look a map is drawn in (firmware 0.20.0+).
    # `cap`: the larger picture a screen's memory takes (firmware 0.52.0+); the preview sizes its own.
    allowed = {'inbox', 'entity', 'tiles', 'idx', 'size', 'bg', 'session', 'rev', 'view', 'atlas', 'dark', 'cap'}
    if (not isinstance(fields, dict) or set(fields) - allowed or
            any(not isinstance(v, str) or len(v) > 8192 for v in fields.values()) or
            not re.fullmatch(r'[0-9a-f]{16}', fields.get('session', '')) or
            not re.fullmatch(r'[0-9]{1,10}', fields.get('view', ''))):
        raise ValueError('Invalid firmware image request.')
    token = None
    entity = fields.get('entity', '')
    if 'tiles' in fields:
        view = 'live'
        entities = fields['tiles'].split(',')
        if any(e not in manager.ha.states for e in entities):
            raise ValueError('Unknown image entity.')
        atlas = None
        if 'atlas' in fields:
            atlas = camera_feed.tile_art.parse(fields['atlas'], (width, height), len(entities))
            if atlas is None:
                raise ValueError('Invalid image atlas.')
        parsed = camera_feed.live_request(fields, atlas=atlas is not None)
        if parsed is None:
            raise ValueError('Invalid image strip.')
        entities, size, grounds = parsed
        paces = [0 if camera_feed.cover_supported(e) or camera_feed.map_supported(e) else camera_feed.LIVE_REFRESH_DEFAULT
                 for e in entities]
        extra = {'compact': True, **({'atlas': atlas} if atlas else {})}
        # A map (app 0.4.33) is drawn by the renderer a screen gets, from the mockup's own tile (the page it compiled
        # last, firmware_preview), in the preview's look and at its pixels per inch.
        if atlas and any(camera_feed.map_supported(e) for e in entities):
            own = camera_feed.live_indexes(fields, entities) or []
            placed = manager.preview_tiles
            board = {'dpi': shape.get('dpi')} if isinstance(shape.get('dpi'), (int, float)) else None
            renders = []
            for n, e in enumerate(entities):
                tile = placed[own[n]] if n < len(own) and own[n] < len(placed) and placed[own[n]]['entity'] == e else None
                if camera_feed.map_supported(e):
                    tile = tile if tile and (tile.get('options') or {}).get('display') == 'map' else {'entity': e, 'options': {'display': 'map'}}
                    renders.append(manager.map_render(tile, board, camera_feed.live_dark(fields)))
                else:
                    renders.append(None)
            extra['renders'] = renders
        found = await manager.camera.live(entities, size, grounds, paces, **extra)
        entity = fields['tiles']
        if found:
            entity = ','.join(found[2])
            token = manager.camera.link(entity, atlas[:2] if atlas else (size, size), live=(entities, size, grounds, paces, extra))
    elif camera_feed.cover_supported(entity) and entity in manager.ha.states:
        view = 'cover'
        cover = camera_feed.cover_request(fields)
        if cover is None:
            raise ValueError('Invalid cover dimensions or background.')
        size, background = cover
        if await manager.camera.cover(entity, size, background):
            token = manager.camera.link(entity, (size, size), cover=cover)
    elif camera_feed.supported(entity) and entity in manager.ha.states:
        view = 'full'
        if await manager.camera.frame(entity, (width, height)):
            token = manager.camera.link(entity, (width, height))
    else:
        raise ValueError('Unknown image entity.')
    return {'op': 'camera', 't': view, 'e': entity,
            'u': HOST + token + '.bmp' if token else '',
            'session': fields['session'], 'rev': fields.get('rev', ''), 'view': int(fields['view'])}
