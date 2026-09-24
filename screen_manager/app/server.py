"""HA Ingress app. HA writes: text.set_value on discovered inboxes (or the screen_message action on firmware 0.2.33+), each screen's alert actions when an alert event for every screen fires, and one persistent notification when a nightly update stops."""
import asyncio
from collections import Counter
import contextlib
import json
import logging
import os
from pathlib import Path
import secrets
import ssl
import time
from datetime import datetime, timedelta, timezone
import math
import camera_feed
import claude_skill
from firmware import Firmware
import ha_catalogue
import light_effects
import tile_icons
from updates import Updater

from aiohttp import ClientConnectorCertificateError, ClientError, ClientSession, ClientTimeout, WSMsgType, web
from core import ALERT_EVENT, board_of, BROADCAST_EVENTS, BROADCAST_SHOW, BUILTIN, CAMERA_DOMAINS, entity_id, SETTINGS_BESIDE_BLOCK, TILE_EVENTS, TILE_RESULT_EVENT, layout_snapshot, match_screen, HEADER_MIN_FIRMWARE, NAME_TILE_SETTINGS, TRANSPORT_MIN_FIRMWARE, alert_action, alert_camera, alert_data, alert_reference, alert_screen_choice, alert_screen_names, alert_service, alert_targets, backgrounds, builtin_name, controls_catalogue, device_prefixes, discover, discover_screens, encode, entity_slug, extras, forecast_kinds, header_items, inbox_prefix, message_action, min_firmware, name_clash, packets, revision, screen_items, state_message, validate_header, validate_layout, validate_settings
from core import calibrate_entity, can_standby, dimmable, SETTING_ENTITIES, SETTING_RULES, STANDBY_KEYS, setting_action, setting_entities, setting_from_state, state_word
from core import (PAGE_TILE_REPEAT_MIN_FIRMWARE, ROTATION_MIN_FIRMWARE, SHAPES, firmware_features, grid_of, orientation_at,
                  packed_slots, run_tile_event, screen_firmware, shape_of, turns_of, version_text)
import header_bar
import history_card
import i18n
from i18n import REQUEST_LANGUAGE, TRANSLATIONS, Region, english, screen_t, shown, t
from zoneinfo import ZoneInfo


def row_icon(eid, state, attrs, entry):
    """Codepoint of the icon Home Assistant shows for a row of a light's effects page, when the screen's fonts carry it."""
    return tile_icons.ha_icon(attrs) or tile_icons.default_glyph(eid, state, attrs, entry)

LOG = logging.getLogger('screen_manager')

REGISTRY_EVENTS = ('entity_registry_updated', 'device_registry_updated', 'area_registry_updated')
# Keepalive cadence. Firmware 0.2.33+ gets a small ping carrying the layout revision; every
# layout message declares this number, so the firmware sizes its feed watchdog from it
# (firmware 0.2.22+). Firmware before 0.2.33 still gets the whole layout every round.
KEEPALIVE_SECONDS = 120
# Safety net for screens that answer every ping: everything again once an hour.
FULL_REPEAT_SECONDS = 3600
# Sensor history is refreshed in a background task, never inside the sync loop.
HISTORY_SECONDS = 300
# Inbox states after which a screen needs the whole layout again: a restart, a ping that
# did not match, or a tile state that never arrived. Guarded so a slow batch cannot loop.
# Firmware built before the English translation still reports the Dutch originals, so both
# forms are recognised until every board has been reflashed.
RESEND_STATES = frozenset({
    'Ready for tile configuration', 'Resend needed', 'Loading tiles',
    'Klaar voor tegelconfiguratie', 'Indeling opnieuw nodig', 'Tegels laden',
})
RESEND_GUARD_SECONDS = 120
# What a screen reports stays English, the app reads it (protocol); the editor shows it in its own language (app 0.2.90).
SCREEN_STATUS_WORDS = {'Synced': 'synced', 'Loading tiles': 'loading_tiles', 'Layout received': 'layout_received',
                       'Resend needed': 'resend_needed', 'Ready for tile configuration': 'ready'}


def status_text(status):
    """A screen's status for the editor: its protocol words in the editor's language, ours as they were made."""
    status = shown(status)
    if isinstance(status, str) and not isinstance(status, i18n.Text):
        if status in SCREEN_STATUS_WORDS:
            return t(f'addon.status.screen.{SCREEN_STATUS_WORDS[status]}')
        if status.startswith('Error: '):
            return t('addon.status.screen.error', reason=status[len('Error: '):])
    return status
FORECAST_SECONDS = 1800
# A screen that answers its ping (firmware 0.2.49+) is asked with this timeout, so a busy screen never holds
# up the others. An answer that the screen lacks something repeats everything, after this many seconds right
# after a full send, doubling up to RESEND_GUARD_SECONDS while it keeps failing.
ANSWER_TIMEOUT_SECONDS = 5
ANSWER_RETRY_SECONDS = 30
SERVICE_EVENTS = ('service_registered', 'service_removed')

def samples(events, begin, span):
    """24 values, one per bucket: the last known value at the end of each bucket (None until the first)."""
    events.sort(key=lambda pair: pair[0])
    position, value, out = 0, None, []
    for bucket in range(24):
        boundary = begin + (bucket + 1) * span / 24
        while position < len(events) and events[position][0] <= boundary:
            value = events[position][1]
            position += 1
        out.append(value)
    return out

class Refused(ConnectionError):
    """Home Assistant answered a command with an error; `detail` is its own message."""
    def __init__(self, detail=''):
        super().__init__('Home Assistant refused the command.')
        self.detail = detail


def rounded(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return round(value, 3) if math.isfinite(value) else None

class HomeAssistant:
    registry_interval = 600

    def __init__(self, session, base, token, tls=True):
        self.session, self.base, self.token = session, base.rstrip('/'), token
        # How requests to Home Assistant check its certificate on https (ha_tls, docs/DOCKER.md): only these requests,
        # never a picture from elsewhere.
        self.tls = tls
        self.ws = None
        self.next_id = 0
        self.pending = {}
        self.states = {}
        self.registry, self.devices, self.areas = [], [], []
        self.online = False
        self.changed = asyncio.Event()
        # Entity ids the manager cares about; None wakes it for every state change.
        self.relevant = None
        # Entity ids whose state changed since the manager last looked; it only rebuilds those tiles.
        self.dirty = set()
        self.registry_changed = asyncio.Event()
        self.setting_events = []
        self.time_zone = None
        # Home Assistant's unit system; a climate entity's temperature carries no unit of its own.
        self.units = {}
        # Home Assistant's own language (get_config), and the one the screens speak (Settings -> Language & region,
        # app 0.2.90), in which the words for states are fetched; the manager binds `language_of`.
        self.ha_language = None
        self.language_of = lambda: 'en'
        self.config_stale = False
        self.on_config = lambda: None
        # (event type, data) of alert events for every screen, for Manager.alert_loop.
        self.broadcasts = asyncio.Queue()
        # (event type, data) of tile events (app 0.2.51+), for Manager.tile_loop.
        self.tile_events = asyncio.Queue()
        # ESPHome actions that can answer (`esphome.<node>_screen_message` of firmware 0.2.49+), from Home
        # Assistant's own list; refreshed when a device registers its actions again.
        self.responses = set()
        self.services_changed = asyncio.Event()
        # Every action Home Assistant describes (get_services), which the editor's choices per entity follow (app
        # 0.2.67); `services_rev` counts the refreshes. `targets` keeps Home Assistant's answer per entity, and
        # `target_lookup` stays None until it is known whether Home Assistant answers get_services_for_target (2025.12+).
        self.services, self.services_rev, self.targets, self.target_lookup = {}, 0, {}, None
        # Home Assistant's own names and descriptions of actions and their fields (frontend/get_translations), for Perform
        # action (app 0.2.67); `get_services` has carried no translated names since 2025.10. Per language (app 0.2.90): the
        # screens' one first, an editor in another language asks for its own (service_names_in).
        self.service_names, self.service_names_by_language = {}, {}
        # Home Assistant's words for states (frontend/get_translations `entity_component` and `entity`), which a tile shows
        # where it would show the raw state (app 0.2.67): per language, the screens' and English (app 0.2.90), so a screen
        # whose firmware predates the languages keeps English words (state_words).
        self.words_by_language = {}
        self.esphome_services = False
        self._platforms_source, self._platforms = None, {}
        # History a detail card asks for when it opens (firmware 0.2.51+): {inbox, entity, hours}, for Manager.card_history_loop.
        self.history_requests = asyncio.Queue()
        # A camera a screen opens full screen (firmware 0.2.57+): {inbox, entity}, for Manager.camera_loop.
        self.camera_requests = asyncio.Queue()
        # The names a light's picker lists (firmware 0.2.70+): {inbox, entity, page}, for Manager.card_options_loop.
        self.options_requests = asyncio.Queue()

    async def request(self, kind, **data):
        if self.ws is None or self.ws.closed:
            raise ConnectionError("Home Assistant isn't connected.")
        self.next_id += 1
        key = self.next_id
        future = asyncio.get_running_loop().create_future()
        self.pending[key] = future
        try:
            await self.ws.send_json({'id': key, 'type': kind, **data})
            return await asyncio.wait_for(future, 15)
        finally:
            self.pending.pop(key, None)

    async def read(self):
        async for msg in self.ws:
            if msg.type != WSMsgType.TEXT:
                continue
            data = msg.json()
            if data.get('type') == 'result':
                future = self.pending.get(data.get('id'))
                if future and not future.done():
                    if data.get('success'):
                        future.set_result(data.get('result'))
                    else:
                        error = data.get('error') if isinstance(data.get('error'), dict) else {}
                        future.set_exception(Refused(str(error.get('message') or '')))
            elif data.get('type') == 'event':
                event = data.get('event', {})
                body = event.get('data', {})
                if event.get('event_type') == 'esphome.screen_setting':
                    self.setting_events.append(body)
                    self.changed.set()
                elif event.get('event_type') == 'esphome.screen_history':
                    self.history_requests.put_nowait(body)
                elif event.get('event_type') == 'esphome.screen_camera':
                    self.camera_requests.put_nowait(body)
                elif event.get('event_type') == light_effects.OPTIONS_EVENT:
                    self.options_requests.put_nowait(body)
                elif event.get('event_type') == 'state_changed':
                    eid = body.get('entity_id')
                    if body.get('new_state'):
                        self.states[eid] = body['new_state']
                    else:
                        self.states.pop(eid, None)
                    if self.relevant is None or eid in self.relevant:
                        self.dirty.add(eid)
                        self.changed.set()
                elif event.get('event_type') in REGISTRY_EVENTS:
                    self.registry_changed.set()
                elif event.get('event_type') == 'core_config_updated':
                    # Settings -> System -> General in Home Assistant, such as its language (app 0.2.90).
                    self.config_stale = True
                    self.services_changed.set()
                elif event.get('event_type') in SERVICE_EVENTS:
                    # Every action counts for what the editor offers (app 0.2.67); a screen's own actions also decide
                    # how the app talks to it.
                    self.esphome_services |= body.get('domain') == 'esphome'
                    self.services_changed.set()
                elif event.get('event_type') in BROADCAST_EVENTS or event.get('event_type') == ALERT_EVENT:
                    # Queued, not handled here: the calls wait for results this reader has to deliver. A screen's own
                    # report of an alert's end (app 0.2.91) goes the same way: the button may have an action behind it.
                    self.broadcasts.put_nowait((event['event_type'], body))
                elif event.get('event_type') in TILE_EVENTS:
                    self.tile_events.put_nowait((event['event_type'], body))
        raise ConnectionError('Home Assistant connection lost.')

    def describe_close(self, connected):
        """Why and after how long the websocket ended; helps explain unexpected reconnects in the log."""
        if connected is None:
            return ''
        ws = self.ws
        reason = ws.exception() if ws is not None else None
        return ' after %d s, close code %s%s' % (time.monotonic() - connected, ws.close_code if ws is not None else None,
                                            f', {type(reason).__name__}' if reason else '')

    @property
    def state_words(self):
        """Home Assistant's words for states in the language of the screen being written for (i18n.SCREEN), else in the
        screens' language."""
        context = i18n.SCREEN.get()
        language = context.get('language') if context else None
        words = self.words_by_language
        return words.get(language) or words.get(self.language_of()) or words.get('*') or {}

    @state_words.setter
    def state_words(self, words):
        """One set of words for every language (tests, a Home Assistant that answers in one language only)."""
        self.words_by_language = {'*': dict(words or {})}

    async def registries(self):
        self.registry, self.devices, self.areas = await asyncio.gather(
            self.request('config/entity_registry/list'), self.request('config/device_registry/list'), self.request('config/area_registry/list'))

    async def fetch_services(self):
        """Every action Home Assistant describes: which ESPHome actions answer (Home Assistant lists `response` for an
        action that can return one), and the descriptions the editor's choices per entity follow (app 0.2.67)."""
        services = await self.request('get_services') or {}
        esphome = services.get('esphome', {})
        self.responses = {f'esphome.{name}' for name, spec in esphome.items() if isinstance(spec, dict) and spec.get('response')}
        if isinstance(services, dict):
            self.services, self.services_rev, self.targets = services, self.services_rev + 1, {}
        try:
            language = self.language_of()
            names = await self.request('frontend/get_translations', language=language, category='services')
            if isinstance((names or {}).get('resources'), dict):
                self.service_names = names['resources']
                self.service_names_by_language = {language: names['resources']}
            by_language = {}
            for code in dict.fromkeys((language, 'en')):
                words = {}
                for category in ('entity_component', 'entity'):
                    found = await self.request('frontend/get_translations', language=code, category=category)
                    if isinstance((found or {}).get('resources'), dict):
                        words.update(found['resources'])
                if words:
                    by_language[code] = words
            if by_language:
                self.words_by_language = by_language
            icons = {}
            for category in ('entity_component', 'entity'):
                found = await self.request('frontend/get_icons', category=category)
                if isinstance((found or {}).get('resources'), dict):
                    icons[category] = found['resources']
            if icons:
                tile_icons.use_ha_icons(icons)
        except (Refused, TimeoutError) as error:
            # The editor then shows the names services.yaml still carries, and tiles keep their raw states.
            LOG.info('No action names or state words from Home Assistant (%s)', type(error).__name__)

    async def service_names_in(self, language):
        """Home Assistant's names of actions in `language` (the editor's), fetched once per language; the screens' own
        when Home Assistant doesn't answer."""
        if language == self.language_of() or not self.service_names_by_language:
            return self.service_names
        if language not in self.service_names_by_language:
            try:
                names = await self.request('frontend/get_translations', language=language, category='services')
                self.service_names_by_language[language] = (names or {}).get('resources') or self.service_names
            except (Refused, TimeoutError, ConnectionError):
                return self.service_names
        return self.service_names_by_language[language]

    async def read_config(self):
        """Units, time zone and language from Home Assistant's core config; again when someone changes them there."""
        self.config_stale = False
        try:
            config = await self.request('get_config')
            self.units = config.get('unit_system') or {}
            self.time_zone = ZoneInfo(config.get('time_zone') or 'UTC')
            language = config.get('language')
            changed = isinstance(language, str) and language != self.ha_language
            self.ha_language = language if isinstance(language, str) else self.ha_language
            if changed:
                self.on_config()
        except (Refused, TimeoutError, ConnectionError, ValueError, TypeError, AttributeError, KeyError):
            self.time_zone = self.time_zone or timezone.utc

    async def refresh_services(self):
        """fetch_services for the connection loop: a list that cannot be read only means no answers are asked for."""
        try:
            await self.fetch_services()
        except (ConnectionError, TimeoutError, OSError, ValueError, TypeError, AttributeError) as error:
            LOG.warning('Reading the actions from Home Assistant failed (%s); screens are not asked for answers', type(error).__name__)
            self.responses = set()

    def platform_of(self, entity_id):
        """The integration behind an entity, from the entity registry (an action can be meant for one integration)."""
        registry = self.registry
        if self._platforms_source is not registry:
            self._platforms_source = registry
            self._platforms = {item.get('entity_id'): item.get('platform') for item in registry if isinstance(item, dict)}
        return self._platforms.get(entity_id)

    async def entity_actions(self, entity_id):
        """The actions Home Assistant offers for one entity, or None while that is unknown (no action list yet, or no
        state). Home Assistant 2025.12+ answers get_services_for_target itself; an older one gets the same answer from the
        action descriptions."""
        state = self.states.get(entity_id)
        if state is None or not self.services:
            return None
        attributes = state.get('attributes') or {}
        key = (self.services_rev, id(self.registry), attributes.get('supported_features'), attributes.get('device_class'))
        cached = self.targets.get(entity_id)
        if cached and cached[0] == key:
            return cached[1]
        actions = None
        if self.target_lookup is not False:
            try:
                answer = await self.request('get_services_for_target', target={'entity_id': [entity_id]}, expand_group=False)
                if isinstance(answer, list):
                    actions, self.target_lookup = frozenset(answer), True
            except Refused as error:
                if 'unknown command' in (error.detail or '').lower():
                    self.target_lookup = False
            except (ConnectionError, TimeoutError):
                pass
        if actions is None:
            actions = frozenset(ha_catalogue.local_actions(self.services, entity_id, attributes, self.platform_of(entity_id)))
        self.targets[entity_id] = (key, actions)
        return actions

    async def capabilities(self, entity_id):
        """What the editor may offer for one entity (ha_catalogue.capabilities), or None while Home Assistant can't say."""
        actions = await self.entity_actions(entity_id)
        if actions is None:
            return None
        return ha_catalogue.capabilities(entity_id, actions, self.states.get(entity_id), self.services)

    async def run(self):
        url = ('ws://supervisor/core/websocket' if self.base == 'http://supervisor/core/api'
               else self.base.replace('http://', 'ws://').replace('https://', 'wss://') + '/websocket')
        while True:
            reader, connected = None, None
            try:
                async with self.session.ws_connect(url, heartbeat=30, max_msg_size=16*1024*1024, ssl=self.tls) as ws:
                    self.ws = ws
                    await ws.receive_json(timeout=15)
                    await ws.send_json({'type': 'auth', 'access_token': self.token})
                    if (await ws.receive_json(timeout=15)).get('type') != 'auth_ok':
                        raise ConnectionError('Home Assistant authentication failed.')
                    reader = asyncio.create_task(self.read())
                    await self.request('subscribe_events', event_type='state_changed')
                    await self.request('subscribe_events', event_type='esphome.screen_setting')
                    await self.request('subscribe_events', event_type='esphome.screen_history')
                    await self.request('subscribe_events', event_type='esphome.screen_camera')
                    await self.request('subscribe_events', event_type=light_effects.OPTIONS_EVENT)
                    for event_type in (*REGISTRY_EVENTS, *BROADCAST_EVENTS, ALERT_EVENT, *TILE_EVENTS, *SERVICE_EVENTS):
                        await self.request('subscribe_events', event_type=event_type)
                    self.states = {s['entity_id']: s for s in await self.request('get_states')}
                    await self.registries()
                    # The config first: its language decides the language of the words for states (app 0.2.90).
                    await self.request('subscribe_events', event_type='core_config_updated')
                    await self.read_config()
                    await self.refresh_services()
                    self.online = True
                    self.changed.set()
                    connected = time.monotonic()
                    LOG.info('Home Assistant connected')
                    # Refresh the registry when HA reports a change (debounced), with a slow
                    # fallback; a full fetch is about 1 MB of JSON and used to run every 30 s.
                    fetched = time.monotonic()
                    while True:
                        waiters = [asyncio.ensure_future(self.registry_changed.wait()), asyncio.ensure_future(self.services_changed.wait())]
                        try:
                            done, _ = await asyncio.wait([reader, *waiters], timeout=30, return_when=asyncio.FIRST_COMPLETED)
                        finally:
                            for waiter in waiters:
                                waiter.cancel()
                        if reader in done:
                            await reader
                        if self.services_changed.is_set():
                            # A screen that reconnects registers its actions one after the other.
                            await asyncio.sleep(1)
                            self.services_changed.clear()
                            if self.config_stale:
                                await self.read_config()
                            await self.refresh_services()
                            if self.esphome_services:
                                self.esphome_services = False
                                self.changed.set()
                        if self.registry_changed.is_set():
                            await asyncio.sleep(1)
                            self.registry_changed.clear()
                        elif time.monotonic() - fetched < self.registry_interval:
                            continue
                        await self.registries()
                        fetched = time.monotonic()
                        self.changed.set()
            except ClientConnectorCertificateError as error:
                # A self-signed certificate never passes by waiting; say what to set.
                LOG.warning('Home Assistant temporarily unavailable (%s: %s). Its certificate is not trusted: set HA_CA_FILE '
                            'to that certificate, or HA_VERIFY_SSL to "0" (docs/DOCKER.md)', type(error).__name__,
                            error.certificate_error)
            except (ConnectionError, TimeoutError, OSError, ValueError) as error:
                LOG.warning('Home Assistant temporarily unavailable (%s)%s', type(error).__name__, self.describe_close(connected))
            except Exception as error:
                LOG.warning('Restarting connection (%s)%s', type(error).__name__, self.describe_close(connected))
            finally:
                if self.online:
                    LOG.info('Home Assistant connection closed%s', self.describe_close(connected))
                self.online = False
                self.ws = None
                if reader:
                    reader.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await reader
                for future in self.pending.values():
                    if not future.done():
                        future.set_exception(ConnectionError('Connection lost.'))
            await asyncio.sleep(5)

    async def send(self, inbox, message, action=None, respond=False):
        """One message to a screen: as one ESPHome action call (firmware 0.2.33+), else as text chunks.

        `respond`: wait for the screen's answer (firmware 0.2.49+), at most ANSWER_TIMEOUT_SECONDS, and return it
        (`status`, `rev`), or None when the answer carries nothing usable."""
        if action:
            domain, service = action.split('.', 1)
            data = {'domain': domain, 'service': service, 'service_data': {'message': encode(message)}}
            if not respond:
                await self.request('call_service', **data)
                return None
            result = await asyncio.wait_for(self.request('call_service', **data, return_response=True), ANSWER_TIMEOUT_SECONDS)
            response = (result or {}).get('response') if isinstance(result, dict) else None
            return response if isinstance(response, dict) else None
        for packet in packets(message):
            await self.request('call_service', domain='text', service='set_value',
                               service_data={'entity_id': inbox, 'value': packet})

    async def call(self, action, data):
        """One Home Assistant action, such as a screen's esphome.<node>_show_alert."""
        domain, service = action.split('.', 1)
        await self.request('call_service', domain=domain, service=service, service_data=data)

    async def camera_image(self, entity):
        """The picture of a camera or image entity as Home Assistant hands it to its own frontend."""
        path = 'camera_proxy' if entity.startswith('camera.') else 'image_proxy'
        async with self.session.get(f'{self.base}/{path}/{entity}', headers={'Authorization': 'Bearer ' + self.token},
                                    timeout=ClientTimeout(total=camera_feed.FETCH_SECONDS), ssl=self.tls) as response:
            response.raise_for_status()
            if (response.content_length or 0) > camera_feed.MAX_SNAPSHOT_BYTES:
                raise ValueError('image too large')
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw += chunk
                if len(raw) > camera_feed.MAX_SNAPSHOT_BYTES:
                    raise ValueError('image too large')
            return bytes(raw)

    def media_picture(self, entity):
        """The address of a media player's cover as its state carries it right now, or '' without one."""
        attrs = self.states.get(entity, {}).get('attributes', {})
        picture = attrs.get('entity_picture') or attrs.get('entity_picture_local')
        return picture if isinstance(picture, str) and picture else ''

    async def media_image(self, entity):
        """The cover of a media player (app 0.2.77), fetched where its state points: Home Assistant's own proxy
        with this app's token (`/api/media_player_proxy/...`), or a picture on the internet as it is."""
        picture = self.media_picture(entity)
        if not picture:
            raise ValueError('no picture')
        root = self.base[:-4] if self.base.endswith('/api') else self.base
        if picture.startswith('/'):
            url, headers, tls = f'{root}{picture}', {'Authorization': 'Bearer ' + self.token}, self.tls
        elif picture.startswith(('http://', 'https://')):
            url, headers, tls = picture, {}, True
        else:
            raise ValueError('unknown picture address')
        async with self.session.get(url, headers=headers, timeout=ClientTimeout(total=camera_feed.FETCH_SECONDS), ssl=tls) as response:
            response.raise_for_status()
            if (response.content_length or 0) > camera_feed.MAX_SNAPSHOT_BYTES:
                raise ValueError('picture too large')
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw += chunk
                if len(raw) > camera_feed.MAX_SNAPSHOT_BYTES:
                    raise ValueError('picture too large')
            return bytes(raw)

    async def fire(self, event_type, data):
        """One Home Assistant event of our own, such as the answer to a tile event."""
        await self.request('fire_event', event_type=event_type, event_data=data)

    async def set_state(self, entity_id, state, attributes):
        """A state this app publishes itself (the layout sensors). Home Assistant's websocket has no
        command for that, so this goes over the REST API with the same token."""
        async with self.session.post(f'{self.base}/states/{entity_id}',
                                     headers={'Authorization': 'Bearer ' + self.token},
                                     json={'state': state, 'attributes': attributes}, ssl=self.tls) as response:
            response.raise_for_status()

    async def esphome_entries(self):
        """Home Assistant's ESPHome integrations, by their entry id: the entry behind each screen."""
        entries = await self.request('config_entries/get', domain='esphome')
        return {entry['entry_id']: entry for entry in entries or [] if isinstance(entry, dict) and entry.get('entry_id')}

    async def delete_config_entry(self, entry_id):
        """Remove one integration with its device and its entities, the way Home Assistant's own Delete does
        (app 0.2.112). ESPHome answers `supports_remove_device: false`: one node is one entry, so the entry
        goes, not the device. Over REST with the same token; the websocket has no command for it."""
        async with self.session.delete(f'{self.base}/config/config_entries/entry/{entry_id}',
                                       headers={'Authorization': 'Bearer ' + self.token},
                                       timeout=ClientTimeout(total=60), ssl=self.tls) as response:
            if response.status in (401, 403):
                raise Refused(t('addon.errors.remove.not_allowed'))
            if response.status == 404:
                raise ValueError(t('addon.errors.remove.gone'))
            response.raise_for_status()
            answer = await response.json(content_type=None)
        return bool(isinstance(answer, dict) and answer.get('require_restart'))

    async def remove_state(self, entity_id):
        """A state this app published itself (a screen's layout sensor), gone with the screen it described."""
        async with self.session.delete(f'{self.base}/states/{entity_id}',
                                       headers={'Authorization': 'Bearer ' + self.token}, ssl=self.tls) as response:
            return response.status < 300

    async def forecast(self, entity, kind='daily'):
        # Forecasts left the weather attributes in HA 2024.4; ask the service instead.
        result = await self.request('call_service', domain='weather', service='get_forecasts',
                                    service_data={'type': kind}, target={'entity_id': entity}, return_response=True)
        forecast = ((result or {}).get('response') or {}).get(entity, {}).get('forecast', [])
        return forecast if isinstance(forecast, list) else []

    async def statistics(self, entities, hours):
        """24 samples per entity from the recorder's statistics, all entities in one request.

        Hourly means for a day, five-minute means below that; a sum-only sensor (energy) gives its
        state. Entities without statistics (no state class) are absent and fall back to `history`."""
        period = 'hour' if hours >= 24 else '5minute'
        start = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.request('recorder/statistics_during_period', start_time=start.isoformat(),
                                    statistic_ids=sorted(entities), period=period, types=['mean', 'state'])
        begin, span, found = start.timestamp(), hours * 3600, {}
        for entity, rows in (result or {}).items():
            if entity not in entities or not isinstance(rows, list):
                continue
            events = []
            for row in rows:
                moment = row.get('start') if isinstance(row, dict) else None
                if not isinstance(moment, (int, float)):
                    continue
                if moment > 1e11:  # milliseconds since HA 2023.9
                    moment /= 1000
                events.append((moment, rounded(row.get('mean') if row.get('mean') is not None else row.get('state'))))
            found[entity] = samples(events, begin, span)
        return found

    async def state_changes(self, entity, hours):
        """(unix time, state) of every change in the last `hours`, beginning with the state at the start (REST history)."""
        start = (datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        async with self.session.get(self.base+'/history/period/'+start,
                params={'filter_entity_id':entity,'minimal_response':'','no_attributes':''},
                headers={'Authorization':'Bearer '+self.token}, ssl=self.tls) as response:
            response.raise_for_status()
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw)>2*1024*1024: raise ValueError('History too large.')
            rows=json.loads(raw)
        changes=[]
        for row in rows[0] if rows else []:
            try:
                timestamp=datetime.fromisoformat(row.get('last_changed',row.get('last_updated','')).replace('Z','+00:00')).timestamp()
            except (ValueError,TypeError,AttributeError): continue
            changes.append((timestamp,row.get('state')))
        return changes

    async def history(self, entity, hours):
        begin=(datetime.now(timezone.utc)-timedelta(hours=hours)).timestamp()
        return samples([(timestamp,rounded(state)) for timestamp,state in await self.state_changes(entity,hours)], begin, hours*3600)

    async def statistic_rows(self, entity, hours):
        """The recorder's hourly statistics rows of one entity over the last `hours` (mean, min, max, state), from the
        hour the range begins in; empty for an entity without statistics."""
        start = datetime.now(timezone.utc) - timedelta(hours=hours + 1)
        result = await self.request('recorder/statistics_during_period', start_time=start.isoformat(), statistic_ids=[entity],
                                    period='hour', types=['mean', 'min', 'max', 'state'])
        rows = (result or {}).get(entity) if isinstance(result, dict) else None
        return rows if isinstance(rows, list) else []

class Manager:
    def __init__(self, ha, path):
        self.ha, self.path = ha, Path(path)
        # sent: per inbox what the screen holds ({'layout', 'header', 'states', 'rev'}); status: how the
        # delivery went, in English with its key (the editor shows it in its own language, app 0.2.90);
        # last: the last full send; pinged: the last keepalive ping.
        self.layouts, self.sent, self.status, self.last, self.pinged = {}, {}, {}, {}, {}
        # (entity, hours) -> (monotonic, 24 samples); filled by history_loop, read by sync_one.
        self.histories = {}
        self.history_wake = asyncio.Event()
        self.forecasts = {}
        self.listeners = set()  # asyncio.Event per open /api/events stream
        self.firmware = Firmware(os.environ.get("ESPHOME_CONFIG", "/homeassistant/esphome"), self.path.parent)
        self.updates = Updater(self, self.path.parent / 'updates.json')
        # Settings -> Language & region (app 0.2.90): the language, clock and numbers of every screen.
        self.region = Region(self.path.parent / 'language.json', ha_language=lambda: getattr(self.ha, 'ha_language', None))
        self.ha.language_of = self.region.language
        self.firmware.language = self.region.language
        self.ha.on_config = self.language_changed
        self.set_screens()
        self.skill_dir = claude_skill.skill_dir()
        self._registry_source, self._registry_index = None, {}
        self._items_source, self._items = None, []
        self._screens_key, self._screens = None, []
        self._watched_key, self._watched = None, set()
        self._seen_registry = None
        # Inbox entity ids seen this run with their Home Assistant device, and old inbox ids that a screen
        # now reports under a new id (see follow_renamed_inboxes); the updater follows a screen through them.
        self._inbox_devices, self.aliases = {}, {}
        # The layout snapshot each screen's sensor already carries, so it is only written when it changes.
        self.published = {}
        self._prefix_source, self._prefixes = None, {}
        # Screens that own their settings (firmware 0.2.49+): {device_id: {key: entity_id}}, per registry.
        self._settings_source, self._settings_index, self._settings_key = None, {}, None
        # Screens whose panel is one you calibrate (app 0.2.117): {device_id: entity_id of Calibrate touch}.
        self._calibrate_index = {}
        # Answers (firmware 0.2.49+): when to send everything again after one said the screen lacks something,
        # how often that failed in a row, and actions Home Assistant refused to answer for.
        self.retry_at, self.retries, self.no_answers = {}, {}, set()
        # History for detail cards (firmware 0.2.51+): (entity, hours) -> (monotonic, message), and the fetches under way.
        self.card_histories, self.card_history_fetches = {}, {}
        # Camera images (firmware 0.2.57+): the feed behind the camera port, and the cameras of recent alerts
        # (entity -> monotonic time) that a screen may open full screen without a tile.
        self.camera = camera_feed.CameraFeed(lambda entity: self.ha.camera_image(entity),
                                             fetch_cover=lambda entity: self.ha.media_image(entity),
                                             picture=lambda entity: self.ha.media_picture(entity))
        self.alert_cameras = {}
        # The action behind an alert's button (app 0.2.91): node -> (key, action, data) of the alert on that screen.
        self.alert_actions = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            # Versioned persistent data. Never silently overwrite an unknown schema.
            if raw.get('version') != 1 or not isinstance(raw.get('screens'), dict):
                raise ValueError('Unknown storage version; data stays unchanged.')
            # Loaded leniently: a tile setting this version doesn't know (saved by a newer one) never stops the app.
            self.layouts = {key: validate_layout(value, stored=True, grid=None) for key, value in raw['screens'].items()}
        # An app from before Language & region (app 0.2.90): its screens keep the 24 hours they show, until Home Assistant
        # says every screen's own clock setting was 12 hours (resolve_clock_pin). A new install starts on Automatic, and
        # is stored right away so a restart never takes it for an old one.
        if not self.region.stored:
            if self.layouts:
                self.region.clock, self.region.pinned = '24', True
            self.region.save()

    def resolve_clock_pin(self):
        """The pinned 24 hours of an app from before Language & region become 12 when every screen's own "24-hour clock"
        switch (firmware before 0.2.76) was off; they stay 24 when one was on or none is left. Waits while a switch has no
        state yet (a screen restarts). True when the clock changed."""
        if not self.region.pinned or not self.ha.online or not getattr(self.ha, 'registry', None):
            return False
        switches = [item['entity_id'] for item in self.ha.registry if item.get('platform') == 'esphome'
                    and item.get('original_name') == '24-hour clock' and not item.get('disabled_by')]
        states = [self.ha.states.get(entity, {}).get('state') for entity in switches]
        if any(state not in ('on', 'off') for state in states):
            return False
        self.region.pinned = False
        twelve = bool(states) and all(state == 'off' for state in states)
        if twelve:
            self.region.clock = '12'
        self.region.save()
        return twelve

    def set_screens(self):
        """What the app writes for the screens follows Settings -> Language & region (i18n.SCREENS)."""
        region = self.region
        i18n.set_screens(region.language(), region.number_style(), region.clock_24h(), region.group_min(), region.percent_space())

    def inventory(self):
        """(screens, every tile/top-bar entity): the full walk over the registry, for the editor and saving."""
        return discover(self.ha.registry, self.ha.states, self.ha.devices, self.ha.areas)

    def screen_registry(self):
        """The few registry entries that describe screens; rebuilt only when HA delivers a new registry."""
        registry = getattr(self.ha, 'registry', [])
        if self._items_source is not registry:
            self._items_source, self._items = registry, screen_items(registry)
        return self._items

    def screens(self):
        """The paired screens, cached until the registry or one of the screens' own diagnostics changes.

        Costs a handful of dictionary lookups per screen instead of a walk over every entity in
        Home Assistant, so the sync loop can run it on every wake."""
        ha = self.ha
        items = self.screen_registry()
        key = (id(ha.registry), id(ha.devices), id(ha.areas), tuple(ha.states.get(item['entity_id'], {}).get('state') for item in items))
        if key != self._screens_key:
            self._screens_key, self._screens = key, discover_screens(items, ha.states, ha.devices, ha.areas)
            self.follow_renamed_inboxes(items)
        return [dict(screen) for screen in self._screens]

    def screen(self, inbox):
        screens = self.screens()
        inbox = self.aliases.get(inbox, inbox)
        return next((s for s in screens if s['id'] == inbox), None)

    def device_prefixes(self, device):
        registry = getattr(self.ha, 'registry', [])
        if self._prefix_source is not registry:
            self._prefix_source, self._prefixes = registry, {}
        if device not in self._prefixes:
            self._prefixes[device] = device_prefixes(registry, device)
        return self._prefixes[device]

    def taken_names(self):
        """The names the screens this app knows already carry (app 0.2.123): `nodes` their ESPHome names, which Home
        Assistant turns into `esphome.<node>_...` actions, and `prefixes` the starts Home Assistant gave their entity
        ids, which an automation types as `switch.<screen>_...`. A new screen may take neither (core.name_clash)."""
        nodes, prefixes = set(), set()
        for meta in self.firmware.profile_names().values():
            if meta.get('node'):
                nodes.add(str(meta['node']).lower())
            if meta.get('friendly'):
                prefixes.add(entity_slug(meta['friendly']))
        for screen in self.screens():
            if screen.get('node'):
                nodes.add(str(screen['node']).lower())
            if screen.get('device_id'):
                prefixes |= set(self.device_prefixes(screen['device_id']))
            for name in (screen.get('device'), screen.get('name')):
                if name:
                    prefixes.add(entity_slug(name))
        return {'nodes': sorted(nodes), 'prefixes': sorted(name for name in prefixes if name)}

    def follow_renamed_inboxes(self, items):
        """Keep a screen's layout and update history when its inbox entity gets a new entity id.

        Firmware 0.2.34 renamed the inbox from "Tegelinstellingen" to "Tile settings". Home Assistant then
        removes the old entity and registers the renamed one under a new id, which would orphan the layout
        stored under the old id. The screen is recognised by its device: an inbox this run saw on the same
        device, or (after a restart) a stored inbox id that carries one of the device's entity id prefixes."""
        current = {item['entity_id']: item.get('device_id') for item in items
                   if item.get('platform') == 'esphome' and item['entity_id'].startswith('text.') and item.get('device_id')
                   and item.get('original_name') in NAME_TILE_SETTINGS and not item.get('disabled_by')}
        stored = (set(self.layouts) | set(self.updates.hosts) | set(self.updates.results)) - set(current) - set(self.aliases)
        for new, device in current.items():
            olds = {old for old, seen in self._inbox_devices.items() if seen == device and old not in current}
            candidates = [old for old in stored if inbox_prefix(old) is not None]
            if candidates:
                prefixes = self.device_prefixes(device)
                olds |= {old for old in candidates if inbox_prefix(old) in prefixes}
            for old in sorted(olds - set(self.aliases)):
                self.rename_inbox(old, new)
        self._inbox_devices.update(current)

    def write_layouts(self, layouts):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        with open(temp, 'w', encoding='utf8') as handle:
            os.chmod(temp, 0o600)
            json.dump({'version': 1, 'screens': layouts}, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self.path)

    def rename_inbox(self, old, new):
        """Move everything kept under an old inbox id to the id the same screen reports under now."""
        moved = []
        if old in self.layouts and new not in self.layouts:
            layouts = {(new if key == old else key): value for key, value in self.layouts.items()}
            self.write_layouts(layouts)
            self.layouts = layouts
            moved.append('layout')
        elif old in self.layouts:
            LOG.warning('Screen %s already has a layout; the one stored under %s stays untouched', new, old)
        if self.updates.renamed(old, new):
            moved.append('update history')
        for store in (self.sent, self.status, self.last, self.pinged):
            store.pop(old, None)
        self.aliases = {**{key: (new if value == old else value) for key, value in self.aliases.items()}, old: new}
        self._inbox_devices.pop(old, None)
        LOG.info('Screen %s now reports as %s%s', old, new, f"; moved its {' and '.join(moved)}" if moved else '')
        if moved:
            self.history_wake.set()
            self.ha.changed.set()
            self.notify()

    def forget_inbox(self, inbox):
        """Everything this app kept for a screen that is gone for good: its layout with its settings, its update
        history, and what the sync loop remembered about it. The mirror of `rename_inbox` (app 0.2.112)."""
        if inbox in self.layouts:
            layouts = {key: value for key, value in self.layouts.items() if key != inbox}
            self.write_layouts(layouts)
            self.layouts = layouts
        self.updates.forget(inbox)
        for store in (self.sent, self.status, self.last, self.pinged, self.published, self.retry_at, self.retries):
            store.pop(inbox, None)
        self.aliases = {key: value for key, value in self.aliases.items() if inbox not in (key, value)}
        self._inbox_devices.pop(inbox, None)
        self._screens_key = None

    async def entry_of(self, screen):
        """The ESPHome integration behind a screen: the one entry of its Home Assistant device that ESPHome owns."""
        device = next((d for d in getattr(self.ha, 'devices', []) if d.get('id') == screen.get('device_id')), None)
        entries = await self.ha.esphome_entries()
        mine = [entry for entry in (device or {}).get('config_entries') or [] if entry in entries]
        if len(mine) != 1:
            raise ValueError(t('addon.errors.remove.no_entry'))
        return mine[0]

    def layout_sensors(self, screen):
        """The layout sensors this app published for a screen (publish_layouts), so they go with it.

        By its node name, and by the name they carry: a screen that is offline says no node, and that is exactly
        the screen somebody removes."""
        node = screen.get('node')
        found = {'sensor.esp_screens_' + node.replace('-', '_')} if node else set()
        title = f"{screen['name']} tiles"
        found |= {entity for entity, state in getattr(self.ha, 'states', {}).items()
                  if entity.startswith('sensor.esp_screens_') and (state.get('attributes') or {}).get('friendly_name') == title}
        return sorted(found)

    async def remove_screen(self, inbox):
        """Remove a screen for good (app 0.2.112): out of Home Assistant, its own YAML out of the ESPHome folder,
        and everything this app kept for it. The mirror of New screen.

        Home Assistant goes first: while it refuses, nothing here is lost. A screen that is still running
        announces itself to Home Assistant again, which is what the page says before it asks."""
        inbox = self.aliases.get(inbox, inbox)
        screen = self.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        if self.updates.busy():
            raise ValueError(t('addon.errors.updates.busy'))
        entry = await self.entry_of(screen)
        profile, _ = self.updates.resolve(screen)
        await self.ha.delete_config_entry(entry)
        LOG.info('Removed %s from Home Assistant', screen['name'])
        # From here Home Assistant no longer has the screen, so nothing below may stop the rest: what could not be
        # removed is named in the answer instead, and the page says so.
        left = []
        if profile:
            try:
                await self.firmware.delete_profile(profile)
            except (OSError, ValueError) as error:
                LOG.warning('The profile %s of %s stays (%s)', profile, screen['name'], error)
                left.append(profile)
                profile = None
        for sensor in self.layout_sensors(screen):
            with contextlib.suppress(ClientError, ConnectionError, TimeoutError, OSError):
                await self.ha.remove_state(sensor)
        self.forget_inbox(inbox)
        # The registry again at once, so the screen leaves the page now instead of when Home Assistant's own
        # event arrives; the editor opens another screen as soon as it does.
        with contextlib.suppress(ConnectionError, TimeoutError, OSError, ValueError):
            await self.ha.registries()
        self.ha.changed.set()
        self.notify()
        return {'removed': True, 'name': screen['name'], 'profile': profile, 'kept': left}

    def built_as(self, screen, profiles=None):
        """What the YAML of this screen's profile says about it (firmware.profile_meta), or {}: the one thing that
        knows a screen while the screen itself says nothing (offline, or firmware from before the shape sensor)."""
        profile, _ = self.updates.resolve(screen, profiles)
        profiles = profiles if profiles is not None else self.firmware.profile_names()
        return (profiles.get(profile) or {}) if profile else {}

    def package_of(self, screen, profiles=None):
        """The board package the screen's profile builds from ("packages/waveshare43.yaml"), or None: what a screen looks
        like while it says nothing itself (offline, or firmware from before the shape sensor)."""
        return self.built_as(screen, profiles).get('package')

    def orientation_of(self, screen, profiles=None):
        """Which way this screen was built to hang, 'landscape' or 'portrait' (app 0.2.107): the LVGL_ROTATION its own
        profile says, read on the board that profile builds from. A screen that is online reports its canvas and its
        grid itself and needs none of this; an offline one gets the grid it was actually built with, so its editor
        places tiles where the screen has cells."""
        known = {**screen, 'package': screen.get('package') or self.package_of(screen, profiles)} if isinstance(screen, dict) else screen
        return orientation_at(SHAPES.get(board_of(known), {}), self.built_as(screen, profiles).get('rotation'))

    def grid_of(self, screen):
        """The grid of a screen's pages (core.grid_of), with the board its profile builds from and the way it was built
        to hang filled in, so a save, an event and the message to the screen count the same cells whether the screen is
        online or not."""
        if isinstance(screen, dict) and not (screen.get('package') and screen.get('orientation')):
            # The profiles once, not once per question: reading them stats every file in the ESPHome folder.
            profiles = self.firmware.profile_names()
            screen = {**screen, 'package': screen.get('package') or self.package_of(screen, profiles),
                      'orientation': screen.get('orientation') or self.orientation_of(screen, profiles)}
        return grid_of(screen)

    def turns(self, screen):
        """The angles this screen may be turned to (core.turns_of): none on firmware that cannot turn (before 0.2.80,
        unless the screen is a Guition, which turned since 0.2.9, or already offers the Rotation entity), else the
        half turn on any glass and the quarter turns as well on a square one."""
        version = self.firmware_version(screen.get('id'), screen) or (0, 0, 0)
        entities = self.setting_entities(screen) or {}
        if board_of(screen) != 'guition' and version < ROTATION_MIN_FIRMWARE and 'rotation' not in entities:
            return ()
        return turns_of(shape_of(screen))

    def firmware_version(self, inbox, screen=None):
        """The firmware a screen's features go by: its sensor, or while that has no version (offline, restarting) the
        one Home Assistant's device registry kept (app 0.2.78); None when neither says (core.screen_firmware)."""
        if screen is None:
            screen = self.screen(inbox) or {}
        return screen_firmware(screen)

    def supports_twenty(self, inbox):
        version=self.firmware_version(inbox)
        return bool(version) and version >= (0,2,7)

    def supports_header(self, inbox, screen=None):
        return (self.firmware_version(inbox, screen) or (0, 0, 0)) >= HEADER_MIN_FIRMWARE

    def supports_ping(self, inbox, screen=None):
        """Firmware 0.2.33+ answers a keepalive ping with its layout revision."""
        return (self.firmware_version(inbox, screen) or (0, 0, 0)) >= TRANSPORT_MIN_FIRMWARE

    def transport(self, inbox, screen=None):
        """The ESPHome action that takes a whole message (firmware 0.2.33+), or None for the text inbox."""
        if screen is None:
            screen = self.screen(inbox) or {}
        return message_action(screen.get('node')) if self.supports_ping(inbox, screen) else None

    # ----- Screen settings: owned by the screen (firmware 0.2.49+), else stored with the layout -----
    def setting_index(self):
        """{device_id: {key: entity_id}} for every screen that owns its settings; rebuilt per registry.

        The same walk indexes each device's Calibrate touch button (app 0.2.117), because both answer the same
        question from the same place: what this screen's device actually offers in Home Assistant."""
        registry = getattr(self.ha, 'registry', [])
        if self._settings_source is not registry:
            by_device = {}
            for item in registry:
                if item.get('platform') == 'esphome' and item.get('device_id'):
                    by_device.setdefault(item['device_id'], []).append(item)
            index, calibrate = {}, {}
            for device, items in by_device.items():
                entities = setting_entities(items)
                if entities is not None:
                    index[device] = entities
                button = calibrate_entity(items)
                if button:
                    calibrate[device] = button
            self._settings_source, self._settings_index, self._calibrate_index = registry, index, calibrate
        return self._settings_index

    def setting_entities(self, screen):
        """{key: entity_id} when this screen owns its settings, else None (they travel in the layout message)."""
        device = (screen or {}).get('device_id')
        return self.setting_index().get(device) if device else None

    def calibrate_button(self, screen):
        """This screen's Calibrate touch button, or None when its panel has no calibration wizard."""
        device = (screen or {}).get('device_id')
        self.setting_index()  # the same walk fills the calibrate index
        return self._calibrate_index.get(device) if device else None

    def settings_view(self, screen):
        """What the editor shows under Screen settings.

        `owner` is 'screen' when the screen's own entities hold the settings, else 'layout'. `keys` are the
        settings this screen has, `unavailable` the ones Home Assistant cannot read or change right now (the
        screen is offline, or the entity is disabled); their value is None, not a default that could differ
        from what the screen has."""
        inbox = self.aliases.get(screen['id'], screen['id'])
        turns = self.turns(screen)
        # A backlight without levels (app 0.2.105): the normal brightness is not a setting there, and the two that
        # are left mean lit or dark. `switches` names them so the panel draws the switch the screen draws.
        dims = dimmable(screen)
        switches = [] if dims else ['standby_brightness', 'night_brightness']
        # A screen that cannot go dark (app 0.2.106) has no standby and no night: those settings are not there, on
        # the screen, in Home Assistant or here, and the editor drops a group that has no rows left.
        dark = can_standby(screen)
        # Whether this screen's panel is one you calibrate (app 0.2.117): it has the button the screen's own settings
        # page has the row for, and pressing it starts the same wizard. Home Assistant says so, so a board that gets
        # the wizard later needs nothing here.
        calibrate = bool(self.calibrate_button(screen))
        keys = [key for key in SETTING_RULES if key != 'show_clock' and (key != 'rotation' or turns)
                and (dims or key != 'brightness') and (dark or key not in STANDBY_KEYS)]
        entities = self.setting_entities(screen)
        if entities is None:
            try:
                values = validate_settings(self.layouts.get(inbox, {}).get('settings', {}))
            except ValueError:
                values = validate_settings({})
            if (self.firmware_version(inbox, screen) or (0, 0, 0)) < (0, 2, 44):
                keys = [key for key in keys if key not in ('auto_home', 'auto_home_seconds')]
            # Dark mode, the page buttons and the home key came after the screens took over their settings: firmware
            # that gets them with the layout lacks them.
            keys = [key for key in keys if key not in ('dark_mode', 'page_buttons', 'home_button')]
            return {'owner': 'layout', 'values': values, 'keys': keys, 'unavailable': [], 'rotations': list(turns),
                    'switches': switches, 'calibrate': calibrate}
        # Only the settings this screen has an entity for: one added in later firmware stays out of the panel.
        keys = [key for key in keys if key in entities]
        values = {key: setting_from_state(key, self.ha.states.get(entities[key])) for key in keys}
        # `rotations` are the angles this screen's glass allows (app 0.2.94): the editor offers those and no others.
        return {'owner': 'screen', 'values': values, 'keys': keys, 'unavailable': [key for key in keys if values[key] is None],
                'rotations': list(turns), 'switches': switches, 'calibrate': calibrate}

    def settings_states_key(self):
        """The states of every setting entity, so the sync loop notices a change the editor should show."""
        states = self.ha.states
        return tuple((entity, states.get(entity, {}).get('state')) for device in self.setting_index().values()
                     for entity in device.values())

    def store_settings(self, inbox, settings, screen=None, on_screen=False):
        """Settings of a screen that does not own them, kept with its layout.

        `on_screen`: the screen reported them itself. The layout message it holds is then brought in step
        without sending it back, which could undo a change it made after reporting this one; its revision
        stays, so the next ping still matches."""
        base = self.layouts.get(inbox) or {'title': (screen or {}).get('name') or screen_t('screen.status.home'), 'tiles': []}
        layout = validate_layout({**base, 'settings': settings}, grid=self.grid_of(screen) if screen else None)
        updated = {**self.layouts, inbox: layout}
        self.write_layouts(updated)
        self.layouts = updated
        if on_screen and inbox in self.sent:
            self.sent[inbox] = {**self.sent[inbox], 'layout': self.layout_message(inbox, layout, screen or self.screen(inbox) or {})}
        self.notify()

    def check_turn(self, screen, angle):
        """Refuse a turn this screen cannot make: any turn on firmware that cannot turn, a quarter turn on glass that
        is not square (Manager.turns). 0 is always fine."""
        if not angle:
            return
        turns = self.turns(screen)
        if not turns:
            raise ValueError(t('addon.errors.settings.rotation', version=version_text(ROTATION_MIN_FIRMWARE)))
        if angle not in turns:
            raise ValueError(t('addon.errors.settings.rotation_quarter'))

    def screen_setting_event(self, event):
        """A screen reported a setting that changed on it (its settings page, one of its entities).

        A screen that owns its settings needs nothing here: its entities carry the change. Older firmware gets
        it kept with the layout, without the layout being sent back."""
        inbox = self.aliases.get(event.get('inbox'), event.get('inbox'))
        if inbox not in self.layouts:
            return
        screen = self.screen(inbox)
        if screen is not None and self.setting_entities(screen) is not None:
            return
        key, value = event.get('key'), event.get('value')
        stored = validate_settings(self.layouts[inbox].get('settings', {}))
        if key not in stored or key == 'show_clock':
            return
        settings = dict(stored)
        settings[key] = value == '1' if type(stored[key]) is bool else int(value)
        if key == 'brightness':
            for dim in ('standby_brightness', 'night_brightness'):
                settings[dim] = min(settings[dim], settings[key])
        settings = validate_settings(settings)
        # A screen reporting what it already has (an automation setting the same value on every light change).
        if settings != stored:
            self.store_settings(inbox, settings, screen, on_screen=True)

    async def change_settings(self, inbox, changes):
        """Settings from the editor: on the screen itself when it owns them, else kept with its layout, which the
        sync loop then sends. Returns the settings as the editor shows them afterwards."""
        inbox = self.aliases.get(inbox, inbox)
        screen = self.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        view = self.settings_view(screen)
        if not isinstance(changes, dict) or not changes or set(changes) - set(view['keys']):
            raise ValueError(t('addon.errors.settings.unknown'))
        if view['owner'] == 'screen' and not screen.get('online'):
            raise ValueError(t('addon.errors.settings.offline'))
        # The entities' names, as Home Assistant shows them (the firmware names them in English).
        missing = [SETTING_ENTITIES[key][1] for key in changes if key in view['unavailable']]
        if missing:
            raise ValueError(t('addon.errors.settings.unavailable', names=', '.join(missing)))
        # A setting Home Assistant cannot read (its entity is off) is checked at its default.
        wanted = {**{key: value for key, value in view['values'].items() if value is not None}, **changes}
        if 'brightness' in changes and type(changes['brightness']) is int:
            # A lower brightness pulls both dim levels down with it, as on the screen.
            for dim in ('standby_brightness', 'night_brightness'):
                if dim not in changes:
                    wanted[dim] = min(wanted.get(dim, SETTING_RULES[dim][0]), changes['brightness'])
        merged = validate_settings(wanted)
        self.check_turn(screen, merged['rotation'])
        if view['owner'] == 'layout':
            self.store_settings(inbox, merged, screen)
            self.ha.changed.set()
            return self.settings_view(screen)
        entities = self.setting_entities(screen)
        # Brightness first: the screen keeps both dim levels at or below it.
        for key in sorted(changes, key=lambda key: (key != 'brightness', list(SETTING_RULES).index(key))):
            if merged[key] != view['values'][key]:
                await self.ha.call(*setting_action(key, entities[key], merged[key]))
        return self.settings_view(screen)

    # ----- Answers from the screen (firmware 0.2.49+) -----
    def answers(self, inbox, screen):
        """True when the screen's message action can answer, so a ping learns at once what the screen holds."""
        action = self.transport(inbox, screen)
        return bool(action) and action in getattr(self.ha, 'responses', ()) and action not in self.no_answers

    def answered(self, inbox, screen, answer):
        """Act on a screen's answer to a ping: everything again when it lacks the layout or a tile, or refused one."""
        status = answer.get('status') if isinstance(answer, dict) else None
        if not isinstance(status, str):
            return
        if status not in RESEND_STATES and not status.startswith('Error'):
            self.retries.pop(inbox, None)
            return
        failures = self.retries.get(inbox, 0)
        due = self.last.get(inbox, 0) + min(RESEND_GUARD_SECONDS, ANSWER_RETRY_SECONDS * 2 ** failures)
        name = (screen or {}).get('name') or inbox
        if time.monotonic() >= due:
            LOG.info('%s answered "%s"; sending everything again', name, status)
            self.retries[inbox] = failures + 1
            self.retry_at.pop(inbox, None)
            self.sent.pop(inbox, None)
            self.ha.changed.set()
        elif inbox not in self.retry_at:
            LOG.info('%s answered "%s"; sending everything again in %d s', name, status, max(1, round(due - time.monotonic())))
            self.retries[inbox] = failures + 1
            self.retry_at[inbox] = due

    # ----- The names a light's picker lists (app 0.2.83, firmware 0.2.70+) -----
    async def card_options_loop(self):
        """Answer a screen that opens a picker on a light's effects page: the effects of the light, or the options of a
        select on its device, one page per message."""
        while True:
            request = await self.ha.options_requests.get()
            try:
                await self.answer_options(request)
            except (ClientError, ConnectionError, TimeoutError, OSError, ValueError) as error:
                LOG.info('No options for %s (%s)', request.get('entity') if isinstance(request, dict) else '?', type(error).__name__)

    async def answer_options(self, request):
        """One screen's request: a light on its own layout, or a select on that light's device; a page it asked for."""
        if not isinstance(request, dict):
            return
        inbox = self.aliases.get(request.get('inbox'), request.get('inbox'))
        entity = request.get('entity')
        try:
            page = int(request.get('page') or 0)
        except (TypeError, ValueError):
            page = 0
        layout, screen = self.layouts.get(inbox), self.screen(inbox) if isinstance(inbox, str) else None
        if not isinstance(entity, str) or not layout or not screen or not screen.get('online'):
            return
        names = light_effects.options_for(entity, self.ha.states, [tile['entity'] for tile in layout['tiles']], self.device_entries)
        action = self.transport(inbox, screen)
        if names is None or not action:
            return
        all_pages = light_effects.pages(names)
        await self.ha.send(inbox, light_effects.message(entity, page, all_pages), action)

    # ----- History on a detail card (firmware 0.2.51+) -----
    async def card_history_loop(self):
        """Answer the history a screen asks for when a card opens, a few at a time."""
        limit = asyncio.Semaphore(3)

        async def answer(request):
            async with limit:
                try:
                    await self.answer_history(request)
                except (ClientError, ConnectionError, TimeoutError, OSError, ValueError) as error:
                    # Nothing is sent or kept: the card says it has no history and asks again.
                    LOG.info('No history for %s (%s)', request.get('entity'), type(error).__name__)
                except Exception as error:
                    LOG.warning('History for %s was not sent (%s)', request.get('entity') if isinstance(request, dict) else '?', type(error).__name__)
        while True:
            request = await self.ha.history_requests.get()
            asyncio.ensure_future(answer(request))

    async def answer_history(self, request):
        """One screen's request: an entity on its own layout, a range the card offers, a screen that takes whole messages."""
        if not isinstance(request, dict):
            return
        inbox = self.aliases.get(request.get('inbox'), request.get('inbox'))
        entity = request.get('entity')
        try:
            hours = int(request.get('hours'))
        except (TypeError, ValueError):
            return
        layout, screen = self.layouts.get(inbox), self.screen(inbox) if isinstance(inbox, str) else None
        if hours not in history_card.RANGES or not layout or not screen or not screen.get('online'):
            return
        if entity not in {tile['entity'] for tile in layout['tiles']}:
            return
        what = history_card.kind(entity, self.ha.states.get(entity))
        action = self.transport(inbox, screen)
        if what is None or not action:
            return
        # Its words in the language of this screen's firmware (app 0.2.90).
        token = i18n.SCREEN.set(i18n.screen_context(screen))
        try:
            await self.ha.send(inbox, await self.card_history(entity, hours, what), action)
        finally:
            i18n.SCREEN.reset(token)

    async def card_history(self, entity, hours, what):
        """The history message, from a short cache; screens asking at the same time share one fetch, per language."""
        context = i18n.SCREEN.get() or {}
        key = (entity, hours, context.get('language'), bool(context.get('legacy')))
        cached = self.card_histories.get(key)
        if cached and time.monotonic() - cached[0] < history_card.CACHE_SECONDS[hours]:
            return cached[1]
        fetch = self.card_history_fetches.get(key)
        if fetch is None:
            fetch = asyncio.ensure_future(self.build_card_history(entity, hours, what))
            self.card_history_fetches[key] = fetch
            fetch.add_done_callback(lambda _: self.card_history_fetches.pop(key, None))
        message = await asyncio.shield(fetch)
        self.card_histories[key] = (time.monotonic(), message)
        for old in [k for k, (moment, _) in self.card_histories.items() if time.monotonic() - moment > 3600]:
            del self.card_histories[old]
        return message

    async def build_card_history(self, entity, hours, what):
        """Numbers from the recorder's hourly statistics for a day or a week (the exact changes for an hour, or for an
        entity without statistics); states from their changes. A fetch that fails raises, so nothing is kept."""
        start, end = history_card.window(hours)
        tz = getattr(self.ha, 'time_zone', None)
        attrs = (self.ha.states.get(entity) or {}).get('attributes') or {}
        if what == 'timeline':
            return history_card.timeline(entity, hours, await self.ha.state_changes(entity, hours), start, end, tz, attrs,
                                         entry=self.registry_index().get(entity), translations=getattr(self.ha, 'state_words', None))
        entry, unit = self.registry_index().get(entity), attrs.get('unit_of_measurement') or ''
        rows = await self.ha.statistic_rows(entity, hours) if hours > 1 else []
        if rows:
            means, extreme = history_card.statistic_changes(rows, 3600)
            return history_card.line(entity, hours, means, start, end, tz, entry, unit, extreme)
        changes = [(moment, header_bar.numeric(value)) for moment, value in await self.ha.state_changes(entity, hours)]
        return history_card.line(entity, hours, changes, start, end, tz, entry, unit)

    def registry_index(self):
        """Entity registry by id (display precision, entity category); rebuilt only when HA delivers a new registry."""
        registry = getattr(self.ha, 'registry', [])
        if self._registry_source is not registry:
            self._registry_source, self._registry_index = registry, {item['entity_id']: item for item in registry}
        return self._registry_index

    def device_entries(self, entity):
        """Registry entries on the device of `entity` (itself included); the index follows the registry object."""
        registry = getattr(self.ha, 'registry', [])
        if getattr(self, '_devices_source', None) is not registry:
            by_device = {}
            for item in registry:
                if item.get('device_id'):
                    by_device.setdefault(item['device_id'], []).append(item)
            self._devices_source, self._by_device = registry, by_device
        device = self.registry_index().get(entity, {}).get('device_id')
        return self._by_device.get(device, []) if device else []

    def related_entities(self, tile):
        """Entities a card reads besides its own: a vacuum's cleaning mode and water selects and its battery sensor, a
        cover's battery sensor."""
        from core import cover_related, vacuum_related
        if tile['entity'].startswith('vacuum.'):
            return tuple(vacuum_related(tile['entity'], self.device_entries(tile['entity']), self.ha.states).values())
        if tile['entity'].startswith('cover.'):
            return tuple(cover_related(tile['entity'], self.device_entries(tile['entity']), self.ha.states).values())
        if tile['entity'].startswith('light.'):
            return light_effects.related(tile['entity'], self.device_entries(tile['entity']), self.ha.states)
        return ()

    def device_name_of(self, entity):
        """The name of the entity's device as Home Assistant shows it (the user's name first), or None."""
        device = self.registry_index().get(entity, {}).get('device_id')
        for item in getattr(self.ha, 'devices', None) or ():
            if isinstance(item, dict) and item.get('id') == device:
                return item.get('name_by_user') or item.get('name')
        return None

    def header_message(self, layout):
        return header_bar.message(layout, self.ha.states, self.registry_index(), getattr(self.ha, 'units', {}), getattr(self.ha, 'time_zone', None),
                                  getattr(self.ha, 'state_words', None))

    def needs_firmware(self, inbox, layout, screen=None):
        """Version string the screen must run first, or None when the layout can be sent."""
        needed=min_firmware(layout)
        if needed and not ((self.firmware_version(inbox, screen) or (0,0,0)) >= needed):
            return '.'.join(str(part) for part in needed)
        return None

    def save(self, inbox, data):
        screens, entities = self.inventory()
        # A page opened before a screen's inbox got a new id still saves to the right screen.
        inbox = self.aliases.get(inbox, inbox)
        screen=next((s for s in screens if s['id']==inbox), None)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        # Every position on the grid of this screen's pages: two by three on the first boards, whatever a newer
        # screen reports or its profile builds from (Manager.grid_of).
        grid = self.grid_of(screen)
        layout = validate_layout(data, grid=grid)
        # A CYD has no memory for camera images, whatever its firmware; say so before asking for an update.
        if any(t['entity'].split('.')[0] in CAMERA_DOMAINS for t in layout['tiles']) and board_of(screen) not in camera_feed.BOXES:
            raise ValueError(t('addon.errors.layout.camera_unsupported'))
        needed = self.needs_firmware(inbox, layout, screen)
        if needed:
            raise ValueError(t('addon.errors.layout.firmware_first', version=needed))
        # Settings change through their own call (change_settings). A page from before app 0.2.57 still sends them
        # with the tiles: a screen that owns its settings ignores them, so a stale form never undoes a change
        # made on the screen; other screens keep taking them, as before.
        if self.setting_entities(screen) is not None:
            layout.pop('settings', None)
        # A still-open older UI may save tiles without the new optional settings or top bar.
        if 'settings' not in layout and 'settings' in self.layouts.get(inbox, {}):
            layout['settings'] = self.layouts[inbox]['settings'].copy()
        if 'header' not in layout and 'header' in self.layouts.get(inbox, {}):
            layout['header'] = self.layouts[inbox]['header']
        # Firmware before the top bar only knows show_clock; it follows the clock item.
        if 'header' in layout and 'settings' in layout:
            layout['settings']['show_clock'] = any(item['type'] == 'clock' for item in layout['header']['items'])
        if 'settings' in layout and 'swipe_pages' not in data.get('settings',{}):
            layout['settings']['swipe_pages']=self.layouts.get(inbox,{}).get('settings',{}).get('swipe_pages',False)
        if 'settings' in layout and 'rotation' not in data.get('settings',{}):
            layout['settings']['rotation']=self.layouts.get(inbox,{}).get('settings',{}).get('rotation',0)
        self.check_turn(screen, layout.get('settings', {}).get('rotation', 0))
        # A page from before an option existed sends its tiles without it. It never sends a navigation tile twice
        # (firmware 0.2.65+), so a copy keeps exactly what it was sent with.
        old_list = self.layouts.get(inbox,{}).get('tiles',[])
        old_counts, new_counts = Counter(t['entity'] for t in old_list), Counter(t['entity'] for t in layout['tiles'])
        old_tiles = {t['entity']:t for t in old_list if old_counts[t['entity']] == 1 and new_counts[t['entity']] == 1}
        for tile in layout['tiles']:
            old_options=old_tiles.get(tile['entity'],{}).get('options',{})
            for key in ('background', 'icon', 'controls'):
                if 'options' in tile and key not in tile['options'] and key in old_options:
                    tile['options'][key]=old_options[key]
            if 'options' not in tile and 'options' in old_tiles.get(tile['entity'],{}):
                tile['options'] = old_tiles[tile['entity']]['options'].copy()
        # Restored options can widen a tile: an editor without positions packs again with
        # the real widths, and explicit positions are checked once more for overlap.
        if not any(isinstance(t, dict) and 'slot' in t for t in data.get('tiles', [])):
            for tile, slot in zip(layout['tiles'], packed_slots(layout['tiles'], grid)):
                tile['slot'] = slot
        layout = validate_layout(layout, grid=grid)
        known = {e['id'] for e in entities} | set(BUILTIN)
        if any(t['entity'] not in known for t in layout['tiles']):
            raise ValueError(t('addon.errors.layout.entity_gone'))
        if any(item['type'] == 'entity' and item['entity'] not in known and item['entity'] not in self.ha.states for item in header_items(layout)):
            raise ValueError(t('addon.errors.top_bar.entity_gone'))
        # The screen takes the layout in one message of at most 4096 bytes, which lists every tile's entity id: 48 tiles
        # with long ids can pass every rule above and still never reach the screen (app 0.2.78).
        try:
            encode(self.layout_message(inbox, layout, screen))
        except ValueError:
            raise ValueError(t('addon.errors.layout.ids_too_long')) from None
        updated = {**self.layouts, inbox: layout}
        self.write_layouts(updated)
        self.layouts = updated
        self.sent.pop(inbox, None)
        self.status[inbox] = english('addon.status.saved')
        self.history_wake.set()
        self.ha.changed.set()
        self.notify()

    async def check_supported(self, inbox, data):
        """Refuse a tile setting Home Assistant doesn't support for its entity, before saving (app 0.2.67): On / off on a
        speaker that can't turn on and off, a small slider on a light without brightness. A setting a tile already has
        stays, and nothing is refused while Home Assistant can't say."""
        capabilities = getattr(self.ha, 'capabilities', None)
        if capabilities is None:
            return
        inbox = self.aliases.get(inbox, inbox)
        screen = self.screen(inbox)
        layout = validate_layout(data, grid=self.grid_of(screen) if screen else None)
        before = {tile['entity']: tile for tile in self.layouts.get(inbox, {}).get('tiles', [])}
        for tile in layout['tiles']:
            previous = before.get(tile['entity'])
            if tile['entity'] in BUILTIN or not tile.get('options') or (previous or {}).get('options') == tile['options']:
                continue
            name = tile.get('name') or self.ha.states.get(tile['entity'], {}).get('attributes', {}).get('friendly_name') or tile['entity']
            found = ha_catalogue.unsupported(tile, previous, await capabilities(tile['entity']))
            if found:
                raise ValueError(ha_catalogue.refusal(tile['entity'], name, *found))
            # Perform action (app 0.2.67): an action Home Assistant offers for the entity, with its required fields.
            action = tile['options'].get('action')
            if tile['options'].get('tap') == 'action' and action != ((previous or {}).get('options') or {}).get('action'):
                problem = ha_catalogue.action_problem(tile['entity'], name, action, self.ha.states.get(tile['entity']),
                                                      await self.ha.entity_actions(tile['entity']), self.ha.services)
                if problem:
                    raise ValueError(problem)

    def notify(self):
        for listener in self.listeners:
            listener.set()

    # ----- Language & region (app 0.2.90) -----
    def language_changed(self):
        """The screens' language may have changed (Settings -> Language & region, or Home Assistant's own): the words for
        states come again in it, every screen gets all its messages anew, and each screen's YAML gets the language its
        next firmware update builds in, which makes that update show."""
        self.resolve_clock_pin()
        self.set_screens()
        self.ha.services_changed.set()
        self.sent.clear()
        self.write_languages()
        self.ha.changed.set()
        self.notify()

    def write_languages(self):
        """Every paired screen's YAML says the language of its next build (the LANGUAGE substitution)."""
        language, profiles = self.region.language(), self.firmware.profile_names()
        for screen in self.screens():
            profile, _ = self.updates.resolve(screen, profiles)
            if not profile:
                continue
            try:
                if self.firmware.set_language(profile, language):
                    LOG.info('%s builds in %s from its next update', profile, language)
            except (OSError, ValueError) as error:
                LOG.warning('Could not write the language into %s (%s)', profile, error)

    def pending_profiles(self, screens, profiles):
        """ESP Screens profiles without a paired screen: flashed but not yet added in Home Assistant, or not flashed yet.

        Pairing happens in Home Assistant itself, outside this page; the sidebar shows these so nobody wonders
        where the freshly flashed screen went."""
        nodes = {s.get('node') for s in screens}
        devices = {s.get('device') for s in screens}
        installed = getattr(self.firmware, 'installed', set())
        downloaded = getattr(self.firmware, 'downloaded', set())
        return [{'file': file, 'node': meta['node'], 'friendly': meta.get('friendly') or meta['node'] or file,
                 'installed': file in installed, 'downloaded': file in downloaded, 'api_key': meta.get('api_key')}
                for file, meta in profiles.items()
                if meta.get('screen') and meta.get('node') not in nodes and (meta.get('friendly') or None) not in devices]

    def watched_entities(self):
        """Entities whose state changes matter: tiles on any layout plus the screens' own diagnostics.

        Cached per (registry, layouts): both are replaced as whole objects when they change."""
        key = (id(getattr(self.ha, 'registry', [])), id(self.layouts))
        if key != self._watched_key:
            watched = {tile['entity'] for layout in self.layouts.values() for tile in layout['tiles']}
            watched |= {item['entity'] for layout in self.layouts.values() for item in header_items(layout) if item['type'] == 'entity'}
            watched |= {item['entity_id'] for item in self.screen_registry()}
            watched |= {eid for layout in self.layouts.values() for tile in layout['tiles'] for eid in self.related_entities(tile)}
            watched |= {eid for device in self.setting_index().values() for eid in device.values()}
            self._watched_key, self._watched = key, watched
        return set(self._watched)

    async def cached(self, store, key, ttl, fetch):
        entry=store.get(key)
        if not entry or time.monotonic()-entry[0]>ttl:
            try: value=await fetch()
            except Exception: value=[]
            entry=(time.monotonic(),value);store[key]=entry
        return entry[1]

    def forecast_due(self, entity):
        entry = self.forecasts.get(entity)
        hourly = self.forecasts.get((entity, 'hourly'))
        return not entry or not hourly or time.monotonic() - min(entry[0], hourly[0]) > FORECAST_SECONDS

    async def tile_message(self, index, tile):
        """The state message of one tile: state, options, extras, and the history the background task holds."""
        forecast=hourly=None
        if tile['entity'].startswith('weather.') and hasattr(self.ha,'forecast'):
            entity = tile['entity']
            # Only the forecasts the entity offers: asking Buienradar for hourly ones logged an error in Home
            # Assistant every half hour. What it lacks is kept as empty, so the cache still counts its age.
            kinds = forecast_kinds(self.ha.states.get(entity, {}).get('attributes', {}))
            async def nothing():
                return []
            forecast=await self.cached(self.forecasts, entity, FORECAST_SECONDS, (lambda: self.ha.forecast(entity)) if 'daily' in kinds else nothing)
            # Hourly forecasts feed the weather card's next-hours strip (0.2.23+); refreshed every half hour.
            hourly=await self.cached(self.forecasts, (entity,'hourly'), FORECAST_SECONDS, (lambda: self.ha.forecast(entity,'hourly')) if 'hourly' in kinds else nothing)
        # A vacuum's card also reads selects and the battery sensor of its device (app 0.2.46), a cover's card its battery (0.2.58).
        device=self.device_entries(tile['entity']) if tile['entity'].startswith(('vacuum.', 'cover.', 'light.')) else None
        entry=self.registry_index().get(tile['entity'])
        # A light's effects page (app 0.2.83) names the device's selects and numbers as Home Assistant does, with its icons.
        light=tile['entity'].startswith('light.')
        extra=extras(tile,self.ha.states,forecast,getattr(self.ha,'time_zone',None),hourly,device=device,
                     entries=self.registry_index() if light else None,words=getattr(self.ha,'state_words',None) if light else None,
                     icon_of=row_icon if light else None,device_name=self.device_name_of(tile['entity']) if light else None)
        if tile['entity'].startswith('vacuum.'):
            ha_catalogue.chip_words(extra,tile['entity'],self.ha.states,device,getattr(self.ha,'state_words',None))
        message=state_message(index,tile,self.ha.states,extra,
                              precision=header_bar.precision_of(entry) if tile['entity'].startswith('sensor.') else None,entry=entry)
        # Home Assistant's word where the screen would show the raw state (firmware 0.2.58+ shows it).
        state=self.ha.states.get(tile['entity'],{})
        word=ha_catalogue.screen_word(tile['entity'],message['state'],state.get('attributes'),entry,getattr(self.ha,'state_words',None))
        if word:
            message.setdefault('x',{})['w']=word
        # A second line set to a value of this entity (app 0.2.105): the finished line, or seconds for a moment in
        # time. The other three settings live in the option itself, so the screen keeps drawing them without us.
        for key,value in ha_catalogue.subtitle_message(tile,state).items():
            message.setdefault('x',{})[key]=value
        if tile['entity'].startswith('sensor.') and hasattr(self.ha,'history'):
            hours=tile.get('options',{}).get('history_hours',24)
            entry=self.histories.get((tile['entity'],hours))
            if entry is not None:
                message['history']={'hours':hours,'values':entry[1]}
            else:
                self.history_wake.set()
        return message

    def layout_message(self, inbox, layout, screen):
        tiles = layout['tiles']
        # Grid positions (firmware 0.2.26+; older firmware ignores them and packs the entities in order). A layout
        # made on another grid than the one the screen reports (the screen was flashed as another board and kept
        # its name) goes out packed in order, so every tile still lands in a cell that exists.
        slots = [t['slot'] for t in tiles]
        if isinstance(screen.get('shape'), dict) and not self.grid_of(screen).holds(tiles):
            slots = self.grid_of(screen).pack(tiles)
        message = {'v': 1, 'op': 'layout', 'inbox': inbox, 'title': layout['title'], 'entities': [t['entity'] for t in tiles],
                   'slots': slots, 'keepalive': KEEPALIVE_SECONDS}
        if 'pages' in layout:
            message['pages'] = layout['pages']
        # A title of its own for a page (firmware 0.2.90+, app 0.2.105): one entry per page, an empty one meaning
        # the screen's own title. Left out when no page has one, so nothing travels for the screens that never
        # set one; older firmware ignores the key and every page keeps the screen's title as before.
        if layout.get('page_titles'):
            message['page_titles'] = layout['page_titles']
        # A screen that owns its settings (firmware 0.2.49+) gets none: they would overwrite what changed on it.
        if 'settings' in layout and self.setting_entities(screen) is None:
            # `settings` is the fixed eleven-key block older firmware insists on; everything added
            # later travels as its own key, which firmware that predates it simply ignores.
            message['settings'] = {k:v for k,v in layout['settings'].items() if k not in SETTINGS_BESIDE_BLOCK}
            message['swipe_pages'] = layout['settings'].get('swipe_pages',False)
            message['auto_home'] = layout['settings'].get('auto_home',True)
            message['auto_home_seconds'] = layout['settings'].get('auto_home_seconds',120)
            if self.turns(screen):
                message['rotation'] = layout['settings'].get('rotation',0)
        # The clock and the number format of Settings -> Language & region (app 0.2.90), the same on every screen; firmware
        # before 0.2.76 ignores both and keeps a clock setting of its own.
        message['clock_24h'] = self.region.clock_24h()
        message['numbers'] = self.region.number_style()
        # From 1234 or 12.345 on, and the space before "%" of the language (firmware 0.2.76+, app 0.2.90).
        message['group_min'] = self.region.group_min()
        message['percent_space'] = self.region.percent_space()
        if 'settings' in message:
            message['settings']['clock_24h'] = message['clock_24h']
        # The revision the screen echoes on every ping (firmware 0.2.33+; older firmware ignores it).
        message['rev'] = revision(message)
        return message

    async def sync_one(self, inbox, layout, force=False, screen=None, dirty=None):
        """Send the screen what it lacks; True when something went out.

        `dirty` is the set of entity ids whose state changed since the last pass: only their tiles
        (and the top bar, when it shows one of them) are rebuilt, the other messages are reused as
        sent. None rebuilds every message and sends the differences; `force` sends everything."""
        if screen is None:
            screen = self.screen(inbox) or {}
        # The words go in the language this screen's firmware speaks, which is the old one until its update (app 0.2.90).
        context = i18n.screen_context(screen)
        token = i18n.SCREEN.set(context)
        try:
            return await self._sync_one(inbox, layout, force, screen, dirty, context)
        finally:
            i18n.SCREEN.reset(token)

    async def _sync_one(self, inbox, layout, force, screen, dirty, context):
        needed = self.needs_firmware(inbox, layout, screen)
        if needed:
            self.status[inbox]=english('addon.status.firmware_needed', version=needed)
            return False
        tiles = layout['tiles']
        layout_msg = self.layout_message(inbox, layout, screen)
        try:
            encode(layout_msg)
        except ValueError:
            # Saved by an app before 0.2.78, which didn't check this: nothing to retry until the layout changes.
            self.status[inbox] = english('addon.status.too_large')
            return False
        previous = self.sent.get(inbox)
        # A screen that now speaks another language (an update, or its sensor reporting after a restart) gets every
        # message written anew.
        full = force or not previous or previous['layout'] != layout_msg or dirty is None or previous.get('context') != context
        # The top bar right after the layout (firmware 0.2.32+; older firmware draws the clock of show_clock).
        header_msg = None
        if self.supports_header(inbox, screen):
            bar = {item['entity'] for item in header_items(layout) if item['type'] == 'entity'}
            if full or previous['header'] is None or bar & dirty:
                header_msg = self.header_message(layout)
            else:
                header_msg = previous['header']
        states = []
        for i, tile in enumerate(tiles):
            reuse = not full and i < len(previous['states']) and tile['entity'] not in dirty and dirty.isdisjoint(self.related_entities(tile))
            if reuse and tile['entity'].startswith('weather.') and self.forecast_due(tile['entity']):
                reuse = False
            states.append(previous['states'][i] if reuse else await self.tile_message(i, tile))
        outgoing = []
        if force or not previous or layout_msg != previous['layout']:
            outgoing.append(layout_msg)
        if header_msg is not None and (force or not previous or header_msg != previous['header']):
            outgoing.append(header_msg)
        for i, message in enumerate(states):
            if force or not previous or i >= len(previous['states']) or message != previous['states'][i]:
                outgoing.append(message)
        action = self.transport(inbox, screen)
        for message in outgoing:
            # Save during transmission aborts the old batch, then starts a full new layout.
            if self.layouts.get(inbox) != layout:
                self.sent.pop(inbox, None)
                return True
            await self.ha.send(inbox, message, action)
        # `rev` is the revision of the layout message the screen holds: a layout brought in step without being
        # sent (settings the screen reported itself, see store_settings) keeps the one it had.
        sent_layout = any(message is layout_msg for message in outgoing)
        rev = layout_msg['rev'] if sent_layout or not previous else previous.get('rev', layout_msg['rev'])
        self.sent[inbox] = {'layout': layout_msg, 'header': header_msg, 'states': states, 'rev': rev, 'context': context}
        # The hourly timer follows a real full transmission; any message refreshes the screen's
        # feed window, so the ping timer follows whatever went out (a rebuild without differences,
        # after a registry refresh, must not postpone the ping).
        if force or not previous:
            self.last[inbox] = time.monotonic()
        if outgoing:
            self.pinged[inbox] = time.monotonic()
        self.status[inbox] = english('addon.status.sent')
        # A screen that answers confirms a new layout at once: a ping after the batch says whether it holds
        # the layout and every tile, or which part is missing (firmware 0.2.49+).
        if sent_layout and self.answers(inbox, screen):
            await self.ping(inbox, screen)
        return bool(outgoing)

    async def ping(self, inbox, screen):
        """Keepalive for firmware 0.2.33+: the layout revision only; the screen asks for the rest itself. A screen
        that can answer (firmware 0.2.49+) is asked to, so a missing layout or tile is sent again right away."""
        sent = self.sent.get(inbox)
        if not sent:
            return
        message = {'v': 1, 'op': 'ping', 'rev': sent['rev'], 'keepalive': KEEPALIVE_SECONDS}
        action = self.transport(inbox, screen)
        if not self.answers(inbox, screen):
            await self.ha.send(inbox, message, action)
            self.pinged[inbox] = time.monotonic()
            return
        try:
            answer = await self.ha.send(inbox, message, action, respond=True)
        except TimeoutError:
            # Busy or gone: the text inbox and the next ping still tell.
            LOG.info('%s did not answer its ping within %d s', (screen or {}).get('name') or inbox, ANSWER_TIMEOUT_SECONDS)
            answer = None
        except Refused as error:
            if 'response' not in error.detail.lower():
                raise
            # Home Assistant listed an answer but will not give one: ask this screen no more, ping it as before.
            LOG.warning('Home Assistant gives no answer for %s (%s); pinging it without', action, error.detail)
            self.no_answers.add(action)
            await self.ha.send(inbox, message, action)
            answer = None
        self.pinged[inbox] = time.monotonic()
        self.answered(inbox, screen, answer)

    def take_dirty(self):
        """Entity ids that changed since the last pass, or None when everything must be rebuilt."""
        dirty = getattr(self.ha, 'dirty', None)
        if dirty is None:
            return None
        self.ha.dirty = set()
        registry = getattr(self.ha, 'registry', None)
        if registry is not self._seen_registry:
            # A new registry can change names and display precision: rebuild everything once.
            self._seen_registry = registry
            return None
        return dirty

    async def run(self):
        while True:
            try:
                await asyncio.wait_for(self.ha.changed.wait(), timeout=20)
            except TimeoutError:
                pass
            self.ha.changed.clear()
            await asyncio.sleep(0.25)
            if not self.ha.online:
                self.sent.clear()
                # States made over the REST API are gone once Home Assistant restarts: publish them again.
                self.published.clear()
                self.notify()
                continue
            for event in getattr(self.ha,'setting_events',[])[:]:
                try:
                    self.screen_setting_event(event)
                except (ValueError, TypeError, AttributeError) as error:
                    LOG.warning('A setting %s reported by %s was not kept (%s)', event.get('key') if isinstance(event, dict) else '?',
                                event.get('inbox') if isinstance(event, dict) else '?', error)
            if hasattr(self.ha,'setting_events'): self.ha.setting_events.clear()
            dirty = self.take_dirty()
            if self.region.pinned and self.resolve_clock_pin():
                self.language_changed()
            screens_key = self._screens_key
            screens = self.screens()
            changed = self._screens_key != screens_key
            self.ha.relevant = self.watched_entities()
            # A setting changed on a screen that owns them: the editor shows it.
            settings_key = self.settings_states_key()
            if settings_key != self._settings_key:
                self._settings_key, changed = settings_key, True
            for screen in screens:
                inbox = screen['id']
                before = self.status.get(inbox)
                if not screen['online']:
                    self.sent.pop(inbox, None)
                    self.status[inbox] = english('addon.status.offline')
                    changed = changed or self.status[inbox] != before
                    continue
                if inbox not in self.layouts:
                    continue
                try:
                    now = time.monotonic()
                    pings = self.supports_ping(inbox, screen)
                    # The screen says it lost the layout (restart, mismatched ping, a state that never came).
                    if inbox in self.sent and screen['status'] in RESEND_STATES and now - self.last.get(inbox, 0) >= RESEND_GUARD_SECONDS:
                        self.sent.pop(inbox)
                    # An answer said so right after a full send; its wait is over (firmware 0.2.49+).
                    if inbox in self.retry_at and now >= self.retry_at[inbox]:
                        del self.retry_at[inbox]
                        self.sent.pop(inbox, None)
                    force = now - self.last.get(inbox, 0) >= (FULL_REPEAT_SECONDS if pings else KEEPALIVE_SECONDS)
                    if await self.sync_one(inbox, self.layouts[inbox], force, screen, dirty):
                        changed = True
                    if pings and inbox in self.sent and now - self.pinged.get(inbox, 0) >= KEEPALIVE_SECONDS:
                        await self.ping(inbox, screen)
                except Exception as error:
                    self.sent.pop(inbox, None)
                    self.status[inbox] = english('addon.status.retrying')
                    LOG.warning('Retrying screen sync (%s)', type(error).__name__)
                    await asyncio.sleep(1)
                changed = changed or self.status.get(inbox) != before
            await self.publish_layouts()
            if changed:
                self.notify()

    def history_keys(self):
        """(entity, hours) of every sensor tile on any screen."""
        return {(tile['entity'], tile.get('options', {}).get('history_hours', 24))
                for layout in self.layouts.values() for tile in layout['tiles'] if tile['entity'].startswith('sensor.')}

    async def refresh_histories(self):
        """Fetch the histories that are missing or older than HISTORY_SECONDS: one statistics request per
        window for all sensors at once, the REST history only for sensors without statistics. Changed
        values mark their entity dirty so the sync loop resends just those tiles."""
        wanted = self.history_keys()
        for key in [key for key in self.histories if key not in wanted]:
            del self.histories[key]
        now = time.monotonic()
        due = [key for key in wanted if key not in self.histories or now - self.histories[key][0] >= HISTORY_SECONDS]
        if not due:
            return
        found = {}
        if hasattr(self.ha, 'statistics'):
            for hours in sorted({hours for _, hours in due}):
                entities = {entity for entity, h in due if h == hours}
                try:
                    found.update({(entity, hours): values for entity, values in (await self.ha.statistics(entities, hours)).items()})
                except Exception as error:
                    LOG.warning('Fetching statistics failed (%s); falling back to per-sensor history', type(error).__name__)
        changed = set()
        for key in due:
            values = found.get(key)
            if values is None:
                try:
                    values = await self.ha.history(*key)
                except Exception:
                    values = []
            old = self.histories.get(key)
            self.histories[key] = (time.monotonic(), values)
            if old is None or old[1] != values:
                changed.add(key[0])
        if changed:
            dirty = getattr(self.ha, 'dirty', None)
            if dirty is not None:
                dirty.update(changed)
            self.ha.changed.set()

    async def history_loop(self):
        """Background refresh of sensor histories, so the sync loop never waits for Home Assistant's database."""
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.history_wake.wait(), 30)
            self.history_wake.clear()
            if not self.ha.online or not hasattr(self.ha, 'history'):
                continue
            try:
                await self.refresh_histories()
            except Exception as error:
                LOG.warning('Refreshing history failed (%s)', type(error).__name__)

    # ----- Camera images (firmware 0.2.57+) -----
    async def camera_loop(self):
        """Answer the cameras screens open full screen, a few at a time."""
        limit = asyncio.Semaphore(4)

        async def answer(request):
            async with limit:
                try:
                    await self.answer_camera(request)
                except Exception as error:
                    LOG.warning('Camera for %s was not sent (%s)', request.get('entity') if isinstance(request, dict) else '?', type(error).__name__)
        queue = getattr(self.ha, 'camera_requests', None)
        while queue is not None:
            request = await queue.get()
            asyncio.ensure_future(answer(request))

    def camera_allowed(self, inbox, entity):
        """A camera on the screen's own layout, or one a recent alert showed."""
        seen = self.alert_cameras.get(entity)
        if seen is not None and time.monotonic() - seen < camera_feed.STILL_SECONDS:
            return True
        return entity in {tile['entity'] for tile in self.layouts.get(inbox, {}).get('tiles', [])}

    async def camera_message(self, entity, view, screen, still=None, box=None):
        """The screen message for one camera view: a link to its image, or an empty link when there is none. The size
        is the one this screen's glass asks for, which on a board that is not square differs between a screen built
        lying down and one built standing up (camera_feed.box)."""
        url = ''
        base = await camera_feed.base_url(self.ha.request)
        box = box or camera_feed.box(screen, view)
        if not base:
            LOG.warning('Camera images: no address for this app on the LAN; set SCREEN_CAMERA_URL')
        elif box:
            if view == 'thumb':
                token = self.camera.link(entity, box, still) if still else None
            else:
                token = self.camera.link(entity, box) if await self.camera.frame(entity, box) else None
            url = f'{base}/camera/{token}.bmp' if token else ''
        return {'v': 1, 'op': 'camera', 't': 'alert' if view == 'thumb' else 'full', 'e': entity, 'u': url}

    async def answer_camera(self, request):
        """One screen's request: a camera it may show, on a screen that draws camera images."""
        if not isinstance(request, dict):
            return
        inbox = self.aliases.get(request.get('inbox'), request.get('inbox'))
        entity = request.get('entity')
        screen = self.screen(inbox) if isinstance(inbox, str) else None
        # The live pictures of a page's camera tiles (app 0.2.91, firmware 0.2.77+): one strip for all of them.
        if 'tiles' in request:
            await self.answer_live(inbox, screen, request)
            return
        # A media player's cover (app 0.2.77, firmware 0.2.64+) comes the same way, at the size the card asks for.
        cover = camera_feed.cover_request(request) if camera_feed.cover_supported(entity) else None
        if cover:
            if not camera_feed.can_show_cover(screen) or not screen.get('online'):
                return
        elif not camera_feed.supported(entity) or not camera_feed.can_show(screen) or not screen.get('online'):
            return
        action = self.transport(inbox, screen)
        if not action or not self.camera_allowed(inbox, entity):
            return
        message = await self.cover_message(entity, *cover) if cover else await self.camera_message(entity, 'full', screen)
        await self.ha.send(inbox, message, action)
        LOG.info('%s %s on %s%s', 'Cover of' if cover else 'Camera', entity, screen['name'], '' if message['u'] else ': no image')

    async def answer_live(self, inbox, screen, request):
        """The strip for a page's live camera tiles: every tile the screen names must be a camera tile of its layout
        set to a live picture; the pace of each comes from that tile's own setting."""
        live = camera_feed.live_request(request)
        if not live or not camera_feed.can_show_live(screen) or not screen.get('online'):
            return
        action = self.transport(inbox, screen)
        if not action:
            return
        entities, size, grounds = live
        tiles = {tile['entity']: tile.get('options') or {} for tile in self.layouts.get(inbox, {}).get('tiles', [])}
        # A camera tile set to a live picture, or a media tile set to its cover (app 0.2.92).
        wanted = {'live', 'cover'}
        if any(entity not in tiles or tiles[entity].get('display') not in wanted
               or (tiles[entity].get('display') == 'cover') != camera_feed.cover_supported(entity) for entity in entities):
            LOG.info('Live pictures for %s: not the pictured tiles of %s', ', '.join(entities), screen['name'])
            return
        paces = [tiles[entity].get('refresh', camera_feed.LIVE_REFRESH[0]) if tiles[entity].get('display') == 'live' else 0 for entity in entities]
        url, listing = '', ','.join(entities)
        base = await camera_feed.base_url(self.ha.request)
        if base:
            found = await self.camera.live(entities, size, grounds, paces)
            if found:
                listing = ','.join(found[2])
                token = self.camera.link(listing, (size, size), live=(entities, size, grounds, paces))
                url = f'{base}/camera/{token}.bmp'
        else:
            LOG.warning('Live pictures: no address for this app on the LAN; set SCREEN_CAMERA_URL')
        await self.ha.send(inbox, {'v': 1, 'op': 'camera', 't': 'live', 'e': listing, 'u': url}, action)
        LOG.info('Live pictures of %s on %s%s', ', '.join(entities), screen['name'], '' if url else ': no image')

    async def cover_message(self, entity, size, background):
        """The screen message with a link to a media player's cover at `size` with `background` behind the corners,
        or an empty link when the player shows no picture (the card keeps its placeholder)."""
        url = ''
        base = await camera_feed.base_url(self.ha.request)
        if base:
            token = self.camera.link(entity, (size, size), cover=(size, background)) if await self.camera.cover(entity, size, background) else None
            url = f'{base}/camera/{token}.bmp' if token else ''
        else:
            LOG.warning('Covers: no address for this app on the LAN; set SCREEN_CAMERA_URL')
        return {'v': 1, 'op': 'camera', 't': 'cover', 'e': entity, 'u': url}

    async def alert_images(self, camera, screens):
        """The picture of an alert's camera at that moment, on every screen that draws it."""
        self.alert_cameras[camera] = time.monotonic()
        for old in [entity for entity, moment in self.alert_cameras.items() if time.monotonic() - moment > camera_feed.STILL_SECONDS]:
            del self.alert_cameras[old]
        # One snapshot of this moment for every screen, measured once: each screen's alert card makes a frame for a
        # picture of its proportions (firmware 0.2.103+), and the picture goes out at exactly that frame's size, made
        # from the same snapshot (camera_feed.alert_box). Grouped by that size, not by the board: two screens of the
        # same board hang different ways when one was built standing up. Screens whose board draws no picture at all
        # fall out here, as they always did.
        drawn = [screen for screen in screens if camera_feed.box(screen, 'thumb')]
        picture = await self.camera.snapshot_size(camera) if drawn else None
        groups = {}
        for screen in drawn:
            groups.setdefault(camera_feed.alert_box(screen, picture), []).append(screen)
        async def send(box, group):
            # A box made for this picture's proportions is filled exactly; the 16:9 frame of older firmware gets the
            # picture fitted inside it, as before.
            exact = picture is not None and box != camera_feed.box(group[0], 'thumb')
            found = await self.camera.frame(camera, box, fresh=False, exact=exact) if picture else None
            message = await self.camera_message(camera, 'thumb', group[0], found[1] if found else None, box)
            results = await asyncio.gather(*(self.ha.send(screen['id'], message, self.transport(screen['id'], screen)) for screen in group),
                                           return_exceptions=True)
            failed = sum(isinstance(result, BaseException) for result in results)
            LOG.info('Alert image of %s: %d of %d screens%s', camera, len(group) - failed, len(group), '' if message['u'] else ' (no image)')

        # Every size at once, so no screen waits for another board's picture to be made. Each frame() reads the same
        # snapshot before its first await, so every screen shows the same moment.
        await asyncio.gather(*(send(box, group) for box, group in groups.items()))

    async def broadcast(self, event_type, data):
        """An alert event for every screen, or for the screens its `screen` names (app 0.2.133): the matching action on each
        screen that can show it, all at once."""
        action = BROADCAST_EVENTS[event_type]
        service_data, unusable = alert_data(data) if action == 'show_alert' else ({}, [])
        camera, usable = alert_camera(data) if event_type == BROADCAST_SHOW else ('', True)
        if not usable:
            unusable.append('camera')
        button, usable = alert_action(data) if event_type == BROADCAST_SHOW else (None, True)
        if not usable:
            unusable.append('action')
        if unusable:
            LOG.warning('%s: unusable %s left empty', event_type, ', '.join(unusable))
        # One screen or a few (app 0.2.133): the event's `screen` narrows it down. A name that matches nothing, or a field
        # that is no name at all, sends nothing: an alert meant for the hall never lands on every screen instead.
        paired = self.screens()
        screens, names = paired, None
        wanted, usable = alert_screen_names(data)
        if not usable:
            LOG.warning('%s: unusable screen, sent to no screen', event_type)
            return {'sent': 0, 'skipped': 0, 'failed': 0, 'unknown': []}
        if wanted:
            screens, unknown = alert_screen_choice(paired, wanted)
            names = ', '.join(wanted)
            if unknown:
                known = ', '.join(sorted(filter(None, (screen.get('node') for screen in paired)))) or 'none paired'
                LOG.warning('%s: no screen called %s (screens: %s)', event_type, ', '.join(unknown), known)
            if not screens:
                return {'sent': 0, 'skipped': 0, 'failed': 0, 'unknown': unknown}
        ready, skipped = alert_targets(screens)
        # A screen that draws the image hears about it before the alert, so the card opens with room for it.
        viewers = [screen for screen in ready if camera and camera_feed.can_show(screen) and self.transport(screen['id'], screen)]
        if viewers:
            pending = {'v': 1, 'op': 'camera', 't': 'alert', 'e': camera, 'u': ''}
            await asyncio.gather(*(self.ha.send(screen['id'], pending, self.transport(screen['id'], screen)) for screen in viewers),
                                 return_exceptions=True)
        results = await asyncio.gather(*(self.ha.call(alert_service(screen['node'], action), service_data) for screen in ready),
                                       return_exceptions=True)
        failed = [(screen, type(result).__name__) for screen, result in zip(ready, results) if isinstance(result, BaseException)]
        notes = [f"{screen['name']} {reason}" for screen, reason in skipped + failed]
        LOG.info('%s: %d of %d screens%s%s', event_type, len(ready) - len(failed), len(ready) + len(skipped),
                 f' for {names}' if names else '', f" (not: {'; '.join(notes)})" if notes else '')
        shown = [screen for screen, result in zip(ready, results) if not isinstance(result, BaseException)]
        # The button's action waits on every screen that shows this alert; a dismissal forgets it everywhere.
        for screen in ready:
            self.alert_actions.pop(screen['node'], None)
        if button and shown:
            key = secrets.token_hex(4)
            for screen in shown:
                self.alert_actions[screen['node']] = (key, *button)
        if viewers and any(screen in shown for screen in viewers):
            await self.alert_images(camera, [screen for screen in viewers if screen in shown])
        result = {'sent': len(ready) - len(failed), 'skipped': len(skipped), 'failed': len(failed)}
        if wanted:
            result['unknown'] = unknown
        return result

    async def tile_event(self, event_type, data):
        """One tile event: the screen it names, the changed layout, saved and pushed like the editor does. Returns the
        screen and the tile the event acted on (None for an order)."""
        screen = match_screen(self.screens(), data.get('screen'), self.layouts)
        inbox = self.aliases.get(screen['id'], screen['id'])
        # Firmware 0.2.65+ takes a navigation tile on several pages; an older screen keeps one per page it goes to.
        repeat = (self.firmware_version(inbox, screen) or (0, 0, 0)) >= PAGE_TILE_REPEAT_MIN_FIRMWARE
        layout, tile = run_tile_event(self.layouts.get(inbox) or {'title': screen['name'], 'tiles': []}, TILE_EVENTS[event_type], data, repeat,
                                      self.grid_of(screen))
        await self.check_supported(inbox, layout)
        self.save(inbox, layout)
        return screen, tile

    async def tile_loop(self):
        """Tile events (app 0.2.51+) in arrival order, apart from the sync loop, which can be busy for a
        while. Every event gets an answer, so whoever fired it knows what happened."""
        queue = getattr(self.ha, 'tile_events', None)
        while queue is not None:
            event_type, data = await queue.get()
            answer = {'event': event_type, 'screen': data.get('screen') or '', 'entity': data.get('entity') or ''}
            try:
                screen, tile = await self.tile_event(event_type, data)
                answer.update(ok=True, screen=screen['name'])
                if tile is not None and 'slot' in tile:
                    # Which tile it was, which matters for a navigation tile that is on several pages (app 0.2.78).
                    answer.update(page=self.grid_of(screen).page_of(tile['slot']) + 1, slot=tile['slot'])
                LOG.info('%s: %s on %s', event_type, answer['entity'] or 'order', screen['name'])
                await self.publish_layouts()
            except Exception as error:
                answer.update(ok=False, error=str(error) if isinstance(error, ValueError) else type(error).__name__)
                LOG.warning('%s refused: %s', event_type, answer['error'])
            try:
                await self.ha.fire(TILE_RESULT_EVENT, answer)
            except Exception as error:
                LOG.warning('%s: no answer sent (%s)', event_type, type(error).__name__)

    async def publish_layouts(self):
        """Each screen's layout as a sensor in Home Assistant, so an assistant can read what is where.
        Published again after every change and after a reconnect; a state made this way is gone once
        Home Assistant restarts."""
        for screen in self.screens():
            inbox = self.aliases.get(screen['id'], screen['id'])
            layout, node = self.layouts.get(inbox), screen.get('node')
            if not layout or not node:
                continue
            snapshot = layout_snapshot(screen, layout, self.grid_of(screen))
            if self.published.get(inbox) == snapshot:
                continue
            try:
                await self.ha.set_state('sensor.esp_screens_' + node.replace('-', '_'), len(snapshot['tiles']),
                                        {'friendly_name': f"{screen['name']} tiles", 'icon': 'mdi:view-dashboard-outline', **snapshot})
                self.published[inbox] = snapshot
            except Exception as error:
                LOG.warning('Publishing the layout of %s failed (%s)', screen['name'], type(error).__name__)

    async def alert_loop(self):
        """Alert events for every screen, in arrival order and apart from the sync loop, which can be busy for a while."""
        queue = getattr(self.ha, 'broadcasts', None)
        while queue is not None:
            event_type, data = await queue.get()
            try:
                if event_type == ALERT_EVENT:
                    await self.alert_ended(data)
                else:
                    await self.broadcast(event_type, data)
            except Exception as error:
                LOG.warning('%s failed (%s)', event_type, type(error).__name__)

    async def alert_ended(self, data):
        """A screen reports how its alert ended (esphome.screen_alert). The button performs the action the alert
        came with, once for the alert however many screens showed it; any other ending forgets it on that screen."""
        node = data.get('screen') if isinstance(data, dict) else None
        pending = self.alert_actions.pop(node, None) if isinstance(node, str) else None
        if pending is None:
            return
        key, action, fields = pending
        for other in [n for n, (k, _, _) in self.alert_actions.items() if k == key]:
            del self.alert_actions[other]
        if data.get('action') != 'ok':
            return
        try:
            await self.ha.call(action, fields)
            LOG.info('Alert button on %s: %s performed', node, action)
        except Exception as error:
            LOG.warning('Alert button on %s: %s failed (%s)', node, action, type(error).__name__)

def create_app(manager, development=False):
    csrf = secrets.token_urlsafe(32)
    @web.middleware
    async def guard(request, handler):
        # The editor's language for the messages this request answers with (app 0.2.90). An EventSource sends no headers of
        # its own, so the live updates (/api/events) carry it in the address.
        REQUEST_LANGUAGE.set(TRANSLATIONS.resolve(request.headers.get('X-ESP-Screens-Language') or request.query.get('language') or 'en'))
        # Docker's health check asks the app itself whether it is up, from inside the container (issue #23). It is the
        # one address the app answers besides Home Assistant's, it says nothing but "ok", and it changes nothing.
        if request.path == '/health' and request.method in {'GET', 'HEAD'}:
            return web.Response(text='ok\n', content_type='text/plain', headers={'Cache-Control': 'no-store'})
        allowed = {'127.0.0.1', '::1', *ingress_from()} if development else {'172.30.32.2'}
        if request.remote not in allowed:
            raise web.HTTPForbidden(text=t('addon.errors.open_through_ha'))
        if request.method not in {'GET', 'HEAD'} and request.headers.get('X-Screen-CSRF') != csrf:
            raise web.HTTPForbidden(text=t('addon.errors.refresh_page'))
        try:
            response = await handler(request)
        except ValueError as error:
            return web.json_response({'error': str(error)}, status=400)
        # Home Assistant said no, or can't be reached (Identify, Try it, a setting): a sentence the page shows, never a
        # bare 500 with a traceback in the log (app 0.2.78). Refused is a ConnectionError, so it comes first.
        except Refused as error:
            return web.json_response({'error': t('addon.errors.ha_refused', reason=error.detail or t('addon.errors.no_reason'))}, status=400)
        except (ConnectionError, TimeoutError):
            return web.json_response({'error': t('addon.errors.ha_unreachable')}, status=503)
        except web.HTTPRequestEntityTooLarge:
            return web.json_response({'error': t('addon.errors.too_large')}, status=413)
        except (TypeError, KeyError):
            return web.json_response({'error': t('addon.errors.invalid_input')}, status=400)
        if response.prepared:
            return response  # streamed (SSE) responses set their headers before prepare()
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'"
        return response

    # A layout of 48 tiles with actions on their taps passes 16 KB, the limit from the twenty-tile days; the largest the
    # rules allow stays under about 75 KB (app 0.2.78). The YAML override keeps its own 12 KB limit (firmware.py).
    app = web.Application(middlewares=[guard], client_max_size=128*1024)
    static = Path(__file__).parent / 'static'

    async def cache_assets(request, response):
        """The built script, styles and fonts under /assets/ never change under their name (Vite names each file after a
        hash of its content), so a browser keeps them instead of fetching about 310 KB on every open (app 0.2.78).
        `private`: behind ingress the request carries Home Assistant's session. index.html and api/ stay no-store."""
        if request.path.startswith('/assets/') and response.status in (200, 304):
            response.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
    app.on_response_prepare.append(cache_assets)

    # The page is the Vite build of web/ (npm run build writes it here): index.html names its script and styles
    # by a hash of their content, so a browser that keeps old copies anyway (Safari did after an update) never
    # runs an old script against a new page.
    page = (static / 'index.html').read_text()
    async def index(request):
        # SCREEN_DEV reads the file every time, so a fresh `npm run build` shows up without a restart.
        return web.Response(text=(static / 'index.html').read_text() if development else page, content_type='text/html')
    def light_payload(screens=None):
        """Screens and update status: everything that changes while the page is open."""
        if screens is None:
            screens = manager.screens()
        profiles = manager.firmware.profile_names()
        for screen in screens:
            # A screen without tiles yet: the title the screen itself shows without one, in its language (app 0.2.90).
            screen['layout'] = manager.layouts.get(screen['id'], {'title': screen_t('screen.status.home'), 'tiles': []})
            screen['settings'] = manager.settings_view(screen)
            # The delivery and our own word for a screen that reports nothing, in the editor's language (app 0.2.90).
            status = manager.status.get(screen['id'])
            screen['delivery'] = shown(status) if status else t('addon.status.first_tiles')
            # The layout went out and the screen says it holds it: nothing to report, so the editor shows no
            # delivery line at all (app 0.2.108); anything else is worth a line.
            screen['in_sync'] = bool(status) and getattr(status, 'key', None) == 'addon.status.sent' and shown(screen.get('status')) == 'Synced'
            screen['status'] = status_text(screen.get('status'))
            screen['update'] = manager.updates.state_for(screen, profiles)
            # The API key its YAML carries (app 0.2.132), so it can be copied again after pairing: Home Assistant asks
            # for it again when the integration is removed and re-added, or the screen is paired with another HA.
            profile, _ = manager.updates.resolve(screen, profiles)
            screen['api_key'] = (profiles.get(profile) or {}).get('api_key') if profile else None
            # What this screen looks like: what it reported itself, else the board package its profile builds
            # from (the YAML), else its board. The editor draws its mockup and places tiles on this grid.
            screen['package'] = manager.package_of(screen, profiles)
            # The board too: a screen that says nothing about itself is known by the YAML its profile builds from.
            screen['board'] = board_of(screen)
            # And which way it was built to hang (app 0.2.107), for the same reason: a screen standing up has another
            # canvas and another grid, and while it is offline only its own YAML says so.
            screen['orientation'] = manager.orientation_of(screen, profiles)
            screen['shape'] = shape_of(screen)
            # Whether the board draws pictures (camera tiles, an alert's snapshot, an album cover): the boards with
            # memory for them say so with their camera sizes (boards.json); the firmware that draws them is a
            # separate question the editor asks by version, so an older screen still learns what an update brings.
            screen['pictures'] = board_of(screen) in camera_feed.BOXES
            screen['alert_action'] = alert_service(screen.get('node'))
            screen['dismiss_action'] = alert_service(screen.get('node'), 'dismiss_alert')
            # What the editor may offer this screen, by the firmware the app's own checks go by (app 0.2.78) and the
            # grid of its pages: an offline screen keeps its tiles, and the editor needn't know the version rules.
            version = manager.firmware_version(screen['id'], screen)
            screen['firmware_known'] = version_text(version)
            screen.update(firmware_features(version, manager.grid_of(screen)))
        return {'csrf': csrf, 'connected': manager.ha.online, 'screens': screens,
                'pending': manager.pending_profiles(screens, profiles),
                'updates': manager.updates.summary(screens, profiles),
                'language': manager.region.view()}
    async def inventory(request):
        if request.query.get('light') == '1':
            # The page polls the light form; entities, backgrounds and icons (~100 KB) only on demand.
            return web.json_response(light_payload())
        screens, entities = manager.inventory()
        payload = light_payload(screens)
        payload['entities'] = entities
        # Labels and help in the editor's language (app 0.2.90); ids and keys stay as they are.
        payload['backgrounds'] = backgrounds()
        payload['controls'] = controls_catalogue()
        payload['icons'] = tile_icons.editor()
        payload['alerts'] = alert_reference()
        # What's new for the Update badge: here only, not in every live update (app 0.2.78).
        payload['changelog'] = manager.updates.changelog
        payload['claude_skill'] = claude_skill.status(manager.skill_dir)
        # The name in the editor's language for the library, and as the screens show it for the mockup (app 0.2.90).
        payload['builtin'] = [{'id': key, 'name': builtin_name(key, t), 'screen_name': builtin_name(key),
                               'device': t('addon.labels.built_into_screen'), 'area': '', 'state': 'ok'} for key in BUILTIN]
        payload['header'] = {**header_bar.catalogue(), 'suggestions': {
            screen['id']: header_bar.suggestions(screen, entities, manager.ha.states, manager.registry_index()) for screen in payload['screens']}}
        return web.json_response(payload)
    async def header_preview(request):
        """The top bar as a screen would draw it right now, so the editor shows unsaved changes live."""
        data = await request.json()
        header = validate_header(data.get('header') if isinstance(data, dict) else None)
        return web.json_response({'items': header_bar.preview(header, manager.ha.states, manager.registry_index(),
                                                              getattr(manager.ha, 'units', {}), getattr(manager.ha, 'time_zone', None),
                                                              getattr(manager.ha, 'state_words', None))})
    async def events(request):
        """Server-sent events: pushes the light inventory whenever it changes, so the page need not poll."""
        response = web.StreamResponse(headers={'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store',
                                               'X-Accel-Buffering': 'no', 'X-Content-Type-Options': 'nosniff'})
        await response.prepare(request)
        wake, sent = asyncio.Event(), None
        wake.set()  # first event goes out right away
        manager.listeners.add(wake)
        try:
            while True:
                # Sync results are pushed at once; updater phases are picked up by the 3 s check.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(wake.wait(), 3)
                wake.clear()
                body = json.dumps(light_payload(), ensure_ascii=False)
                if body != sent:
                    await response.write(f'data: {body}\n\n'.encode())
                    sent = body
                else:
                    await response.write(b': keepalive\n\n')
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            manager.listeners.discard(wake)
        return response
    async def save(request):
        data = await request.json()
        await manager.check_supported(request.match_info['inbox'], data)
        manager.save(request.match_info['inbox'], data)
        return web.json_response({'saved': True})
    async def remove_screen(request):
        """Remove a screen for good (app 0.2.112): out of Home Assistant, out of the ESPHome folder and out of
        this app. Everything the sidebar's own warning names before it asks."""
        return web.json_response(await manager.remove_screen(request.match_info['inbox']))
    async def capabilities(request):
        """What Home Assistant says each entity can do, for the tile settings (app 0.2.67). Unknown is null: the editor
        then offers what it always offered."""
        entities = list(dict.fromkeys(request.query.getall('entity', [])))[:40]
        lookup = getattr(manager.ha, 'capabilities', None)
        async def one(entity):
            try:
                return await lookup(entity) if lookup else None
            except Exception as error:
                LOG.info('No capabilities for %s (%s)', entity, type(error).__name__)
                return None
        found = await asyncio.gather(*(one(entity) for entity in entities))
        return web.json_response({'capabilities': dict(zip(entities, found))})
    async def entity_actions(request):
        """Perform action (app 0.2.67): the actions Home Assistant offers for one entity, with its names and the fields it
        offers for that entity. Null while Home Assistant can't say."""
        entity = request.query.get('entity', '')
        ha = manager.ha
        actions = await ha.entity_actions(entity) if entity_id(entity) and hasattr(ha, 'entity_actions') else None
        if actions is None:
            return web.json_response({'actions': None})
        # Home Assistant's names in the editor's own language (app 0.2.90).
        names = await ha.service_names_in(REQUEST_LANGUAGE.get()) if hasattr(ha, 'service_names_in') else getattr(ha, 'service_names', {})
        return web.json_response({'actions': ha_catalogue.action_choices(entity, actions, ha.states.get(entity), ha.services,
                                                                         names, ha.platform_of(entity))})
    async def entity_subtitle(request):
        """The second line of a tile (app 0.2.105): the values of one entity it may say. The list is Home Assistant's
        own - the attributes its frontend translations name - in the editor's language, so nothing here is a list we
        keep. An entity Home Assistant names no attribute of answers an empty list, and the editor then offers only
        the line the screen works out itself, nothing at all, or words of your own."""
        entity = request.query.get('entity', '')
        ha = manager.ha
        if not entity_id(entity):
            return web.json_response({'values': []})
        language = REQUEST_LANGUAGE.get()
        words = getattr(ha, 'words_by_language', {}) or {}
        named = words.get(language) or words.get('en') or words.get('*') or ha.state_words or {}
        return web.json_response({'values': ha_catalogue.subtitle_attributes(entity, ha.states.get(entity), named)})
    async def change_language(request):
        """Settings -> Language & region (app 0.2.90): the language, clock and number format of every screen."""
        data = await request.json()
        before = (manager.region.language(), manager.region.clock_24h(), manager.region.number_style())
        manager.region.change({key: data[key] for key in ('setting', 'clock', 'numbers') if isinstance(data, dict) and key in data})
        if before != (manager.region.language(), manager.region.clock_24h(), manager.region.number_style()):
            manager.language_changed()
        return web.json_response({'language': manager.region.view()})
    async def change_settings(request):
        """Screen settings apply one change at a time, like the settings page on the screen (app 0.2.57)."""
        data = await request.json()
        try:
            view = await manager.change_settings(request.match_info['inbox'], data.get('settings') if isinstance(data, dict) else None)
        except Refused as error:
            raise ValueError(t('addon.errors.ha_refused_change', reason=error.detail or t('addon.errors.no_reason'))) from error
        except (ConnectionError, TimeoutError) as error:
            raise ValueError(t('addon.errors.ha_unreachable')) from error
        return web.json_response(view)
    async def update_screen(request):
        data = await request.json() if request.can_read_body else {}
        return web.json_response(manager.updates.start(request.match_info['inbox'], data.get('host')))
    async def update_all(request):
        return web.json_response({'started': manager.updates.start_all()})
    async def update_settings(request):
        manager.updates.set_auto((await request.json()).get('auto'))
        return web.json_response(manager.updates.summary())
    async def inspector(request):
        screen=manager.screen(request.match_info['inbox'])
        inbox=manager.aliases.get(request.match_info['inbox'], request.match_info['inbox'])
        if screen is None: raise ValueError(t('addon.errors.unknown_screen'))
        layout=manager.layouts.get(inbox,{'tiles':[]})
        return web.json_response({'screen':{**screen, 'status':status_text(screen.get('status'))},
            'delivery':shown(manager.status.get(inbox)), 'layout':layout,
            'tiles':[{'entity':t['entity'],'state':manager.ha.states.get(t['entity'],{}).get('state'),
                      # Home Assistant's word for the state, as its own pages show it ("Heat/Cool", app 0.2.67).
                      'word':state_word(t['entity'],manager.ha.states.get(t['entity'],{}).get('state'),manager.ha.states.get(t['entity'],{}).get('attributes'),
                                        manager.registry_index().get(t['entity']),getattr(manager.ha,'state_words',None)),
                      'attributes':state_message(i,t,manager.ha.states)['a'],
                      'options':t.get('options',{})} for i,t in enumerate(layout['tiles'])]})
    async def states(request):
        """Live values for the editor's mockup (app 0.2.73): the state, Home Assistant's word and the attributes a
        card shows, for the tiles on the page, saved or not. At most sixty entities per request."""
        index = manager.registry_index()
        result = {}
        for eid in request.query.getall('entity', [])[:60]:
            if not isinstance(eid, str) or eid not in manager.ha.states:
                continue
            state = manager.ha.states.get(eid, {})
            entry = index.get(eid)
            message = state_message(0, {'entity': eid, 'name': ''}, manager.ha.states,
                                    precision=header_bar.precision_of(entry) if eid.startswith('sensor.') else None)
            result[eid] = {'state': message['state'], 'a': message['a'],
                           'word': state_word(eid, state.get('state'), state.get('attributes'), entry, getattr(manager.ha, 'state_words', None))}
        return web.json_response({'states': result})
    def one_alert_target(inbox):
        screen = manager.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.unknown_screen'))
        ready, skipped = alert_targets([screen])
        if not ready:
            raise ValueError(t('addon.errors.alerts.cannot_show', name=screen['name'],
                               reason=skipped[0][1] if skipped else t('addon.errors.alerts.not_ready')))
        return ready[0]
    async def identify(request):
        """Identify (app 0.2.73): the screen shows a short card and blinks its backlight, so you know which one it is. The
        card speaks the language of the screen's firmware (app 0.2.90)."""
        screen = one_alert_target(request.match_info['inbox'])
        token = i18n.SCREEN.set(i18n.screen_context(screen))
        try:
            data, _ = alert_data({'title': screen_t('addon.screen.identify.title', name=screen['name']),
                                  'subtitle': screen_t('addon.screen.identify.subtitle'), 'icon': 'bell-ring',
                                  'color': 'blue', 'button_text': screen_t('screen.alert.ok'), 'timeout': 8, 'flash': True})
        finally:
            i18n.SCREEN.reset(token)
        await manager.ha.call(alert_service(screen['node']), data)
        return web.json_response({'ok': True})
    async def calibrate(request):
        """Screen settings → Calibrate touch (app 0.2.117): the screen starts its calibration wizard, the same one it
        runs the first time it is switched on and the same one its own settings page starts. Nothing is measured here:
        the person has to stand in front of the glass and tap the five crosses."""
        screen = manager.screen(request.match_info['inbox'])
        if screen is None:
            raise ValueError(t('addon.errors.unknown_screen'))
        button = manager.calibrate_button(screen)
        if not button:
            raise ValueError(t('addon.errors.calibrate.no_wizard', name=screen['name']))
        if not screen.get('online'):
            raise ValueError(t('addon.errors.calibrate.offline', name=screen['name']))
        await manager.ha.call('button.press', {'entity_id': button})
        return web.json_response({'ok': True})
    async def test_alert(request):
        """Alerts → Try it (app 0.2.73): one alert to one screen or to every screen, with the fields an automation sends."""
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError(t('addon.errors.alerts.invalid'))
        data = body.get('data') if isinstance(body.get('data'), dict) else {}
        if body.get('screen') == 'all':
            return web.json_response(await manager.broadcast(BROADCAST_SHOW, data))
        screen = one_alert_target(str(body.get('screen', '')))
        service, unusable = alert_data(data)
        await manager.ha.call(alert_service(screen['node']), service)
        return web.json_response({'sent': 1, 'failed': 0, 'skipped': 0, 'unusable': unusable})
    async def install_claude_skill(request):
        """Settings → Claude → Install: writes the skill into Home Assistant's configuration folder, only on request."""
        return web.json_response(claude_skill.install(manager.skill_dir))
    async def download_claude_skill(request):
        """Settings → Claude → Download: the same skill as a zip for claude.ai; writes nothing."""
        return web.Response(body=claude_skill.archive(), content_type='application/zip',
                            headers={'Content-Disposition': f'attachment; filename="{claude_skill.NAME}.zip"'})
    async def firmware_status(request):
        # New screen asks what is taken while the name is typed, so a clash is said before anything is written.
        return web.json_response({**manager.firmware.status(), 'taken': manager.taken_names()})
    async def firmware_start(request): return web.json_response(manager.firmware.start(await request.json()))
    async def firmware_override(request):
        return web.json_response(manager.firmware.override(request.match_info['file']))
    async def firmware_override_save(request):
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError(t('addon.errors.firmware.override_invalid'))
        return web.json_response(manager.firmware.save_override(request.match_info['file'], data.get('content')))
    async def firmware_create(request):
        # Profile, missing wifi secrets and (with a USB port or the download) the build and flash in one request; the
        # screen speaks the language of Settings -> Language & region from its first build (app 0.2.90).
        data = await request.json()
        if isinstance(data, dict):
            data['language'] = manager.region.language()
            clash = name_clash(data.get('name'), data.get('friendly_name'), manager.taken_names())
            if clash:
                raise ValueError(clash)
        return web.json_response(manager.firmware.install(data))
    async def firmware_download(request):
        """New screen and Firmware & USB → Download: the factory image this app just built, for ESPHome Web on
        the owner's own computer. Like the profile it came from, it holds the Wi-Fi password and the screen's keys."""
        path, name = manager.firmware.image(request.match_info['file'])
        return web.FileResponse(path, headers={'Content-Type': 'application/octet-stream',
                                               'Content-Disposition': f'attachment; filename="{name}"'})
    async def shutdown(app):
        for task in (manager.updates.task, manager.firmware.task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError): await task
    app.on_cleanup.append(shutdown)
    app.router.add_get('/api/screens/{inbox}/inspect', inspector)
    app.router.add_post('/api/screens/{inbox}/update', update_screen)
    app.router.add_post('/api/updates/run', update_all)
    app.router.add_put('/api/updates', update_settings)
    app.router.add_put('/api/language', change_language)
    app.router.add_get('/api/firmware', firmware_status)
    app.router.add_post('/api/firmware/jobs', firmware_start)
    app.router.add_get('/api/firmware/profiles/{file}/override', firmware_override)
    app.router.add_put('/api/firmware/profiles/{file}/override', firmware_override_save)
    app.router.add_get('/api/firmware/profiles/{file}/download', firmware_download)
    app.router.add_post('/api/firmware/profiles', firmware_create)
    app.router.add_get('/', index)
    app.router.add_get('/api/inventory', inventory)
    app.router.add_get('/api/capabilities', capabilities)
    app.router.add_get('/api/states', states)
    app.router.add_post('/api/screens/{inbox}/identify', identify)
    app.router.add_post('/api/screens/{inbox}/calibrate', calibrate)
    app.router.add_post('/api/alerts/test', test_alert)
    app.router.add_get('/api/entity-actions', entity_actions)
    app.router.add_get('/api/entity-subtitle', entity_subtitle)
    app.router.add_post('/api/header-preview', header_preview)
    app.router.add_post('/api/claude-skill', install_claude_skill)
    app.router.add_get('/api/claude-skill.zip', download_claude_skill)
    app.router.add_get('/api/events', events)
    app.router.add_put('/api/screens/{inbox}', save)
    app.router.add_delete('/api/screens/{inbox}', remove_screen)
    app.router.add_put('/api/screens/{inbox}/settings', change_settings)
    app.router.add_static('/assets/', static / 'assets')
    return app

def ha_tls(environ=os.environ):
    """How requests to Home Assistant check its certificate when HA_API is https (Docker, docs/DOCKER.md).
    The default is the system's list, which a self-signed certificate is not on. HA_CA_FILE trusts that certificate (or
    the CA that signed it) for Home Assistant; HA_VERIFY_SSL "0" checks nothing, the last resort for a certificate
    that doesn't name the address in HA_API."""
    if environ.get('HA_VERIFY_SSL', '').strip().lower() in {'0', 'false', 'no', 'off'}:
        return False
    cafile = environ.get('HA_CA_FILE', '').strip()
    if not cafile:
        return True
    context = ssl.create_default_context(cafile=cafile)
    # Python 3.13 made the default strict, which turns down many self-signed certificates made years ago.
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context

def ingress_from(environ=os.environ):
    """Home Assistant's own address when it runs on another machine than this container (Docker, docs/DOCKER.md): its
    sidebar panel then opens the page over the network, and only from there."""
    return {address.strip() for address in environ.get('SCREEN_INGRESS_FROM', '').split(',') if address.strip()}

async def main():
    development = os.environ.get('SCREEN_DEV') == '1'
    token = os.environ.get('SUPERVISOR_TOKEN', '')
    if development and os.environ.get('HA_TOKEN_FILE'):
        token = Path(os.environ['HA_TOKEN_FILE']).read_text().strip()
    if not token:
        raise SystemExit('No Home Assistant access. Start the app via Supervisor.')
    async with ClientSession(timeout=ClientTimeout(total=20)) as session:
        ha = HomeAssistant(session, os.environ.get('HA_API', 'http://supervisor/core/api'), token, ha_tls())
        manager = Manager(ha, Path(os.environ.get('SCREEN_DATA', '/data')) / 'screens.json')
        # handle_signals: SIGTERM (the Supervisor stopping the app, `docker stop`) and SIGINT end the app through the
        # cleanup below, which also stops a running build, instead of waiting ten seconds for SIGKILL (app 0.2.78).
        runner = web.AppRunner(create_app(manager, development), access_log=None, handle_signals=True)
        await runner.setup()
        await web.TCPSite(runner, '127.0.0.1' if development and not ingress_from() else '0.0.0.0', 8099).start()
        # Camera images for the screens: their own port on the LAN, not the ingress page (docs/CAMERA.md).
        cameras = web.AppRunner(camera_feed.web_app(manager.camera), access_log=None)
        await cameras.setup()
        try:
            await web.TCPSite(cameras, '0.0.0.0', camera_feed.port()).start()
        except OSError as error:
            # Everything else still works; only camera images stay away.
            LOG.error('Camera images are off: port %d is not available (%s)', camera_feed.port(), error)
        try:
            await asyncio.gather(ha.run(), manager.run(), manager.history_loop(), manager.updates.run(),
                                 manager.alert_loop(), manager.tile_loop(), manager.card_history_loop(), manager.camera_loop(), manager.card_options_loop())
        finally:
            await cameras.cleanup()
            await runner.cleanup()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    # The signal arrives as GracefulExit once everything is cleaned up, as in aiohttp's own run_app: a normal stop.
    with contextlib.suppress(web.GracefulExit):
        asyncio.run(main())
