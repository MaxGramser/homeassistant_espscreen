"""The pictures of the editor's firmware preview (web/wasm, docs/EMULATOR_ARCHITECTURE.md): the real firmware in the
browser asks for its pictures as a screen does, and this app answers it the one way it answers every screen
(picture_service), with the preview as a screen of its own: its glass the mockup's, its tiles the page it compiled last.
The links are a virtual address the browser maps to the authenticated ingress endpoint, never fetched over the network.
"""
import re

import core
import picture_legacy
import picture_question

# Firmware accepts HTTP image links. This virtual address is mapped to the authenticated ingress endpoint by the
# browser (FirmwarePreview.vue), never fetched over the network.
HOST = 'http://firmware-preview.invalid/'
# The preview's inbox: the manager's layout_tiles and camera_allowed know it. Each layout a preview compiled is an inbox
# of its own, `firmware-preview:<revision>` (inbox_of), so two mockups on one page (the overview shows every screen)
# each have their own tiles; the manager keeps the last LAYOUTS of them.
INBOX = 'firmware-preview'
LAYOUTS = 16
REVISION = re.compile(r'[0-9a-f]{16}')
# What a question of the firmware carries (picture_question, picture_legacy), and nothing else.
FIELDS = {'inbox', 'entity', 'tiles', 'idx', 'size', 'bg', 'session', 'rev', 'view', 'atlas', 'dark', 'cap', 'src', 'fit',
          'turn', 'mirror', 'card', 'for', 'saver', 'lib', 'vmap', 'focus', 'move', 'q', 'n'}


def inbox_of(revision):
    """The inbox of the preview of the layout of `revision` (the `rev` of its questions); the plain preview without one."""
    return f'{INBOX}:{revision}' if isinstance(revision, str) and REVISION.fullmatch(revision) else INBOX


def is_preview(inbox):
    return isinstance(inbox, str) and (inbox == INBOX or inbox.startswith(INBOX + ':'))


def revision_of(inbox):
    return inbox.partition(':')[2] if is_preview(inbox) else ''


def screen_of(shape, inbox=INBOX):
    """The preview as a screen: its glass and density as the mockup draws it, the firmware of this app, and a picture of
    the whole glass for a full view."""
    width, height = shape['width'], shape['height']
    reported = {'width': width, 'height': height, 'columns': shape.get('columns') or 1,
                'camera': {'full': [width, height], 'thumb': [width, max(1, height // 2)]}}
    if isinstance(shape.get('dpi'), (int, float)):
        reported['dpi'] = shape['dpi']
    return {'id': inbox, 'name': 'the preview', 'online': True, 'shape': reported, 'firmware': core.FIRMWARE_VERSION}


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
    if (not isinstance(fields, dict) or set(fields) - FIELDS or
            any(not isinstance(v, str) or len(v) > 16384 for v in fields.values()) or
            not re.fullmatch(r'[0-9a-f]{16}', fields.get('session', ''))):
        raise ValueError('Invalid firmware image request.')
    inbox = inbox_of(fields.get('rev'))
    screen = screen_of(shape, inbox)
    if 'q' in fields:
        if not re.fullmatch(r'[0-9]{1,10}', fields.get('n', '')):
            raise ValueError('Invalid firmware image request.')
        question = picture_question.parse(fields['q'], int(fields['n']), (width, height))
        kind, entity = 'q', ''
    else:
        if not re.fullmatch(r'[0-9]{1,10}', fields.get('view', '')):
            raise ValueError('Invalid firmware image request.')
        legacy = picture_legacy.read(fields, screen, manager.sources.index_of(inbox))
        question, kind, entity = (legacy.question, legacy.kind, legacy.entity) if legacy else (None, '', '')
    if question is None:
        raise ValueError('Invalid firmware image request.')
    found = await manager.pictures.answer(inbox, screen, question, url_of=lambda token, suffix: f'{HOST}{token}.{suffix}')
    url = found.url if found is not None and not found.stream else ''
    listing = ','.join(found.shown) if found and kind == 'live' and len(question.places) > 1 and url else entity
    message = picture_question.answer(question, url, kind, listing, (found.meta or None) if found else None)
    message.update(session=fields['session'], rev=fields.get('rev', ''))
    if kind != 'q':
        message['view'] = int(fields['view'])
    return message
