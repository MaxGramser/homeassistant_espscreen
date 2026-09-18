"""HA Ingress app. HA writes: text.set_value on discovered inboxes (or the screen_message action on firmware 0.2.33+), each screen's alert actions when an alert event for every screen fires, and one persistent notification when a nightly update stops."""
import asyncio
from collections import Counter
import contextlib
import json
import logging
import os
from pathlib import Path
import secrets
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

from aiohttp import ClientError, ClientSession, ClientTimeout, WSMsgType, web
from core import BROADCAST_EVENTS, BROADCAST_SHOW, BUILTIN, CAMERA_DOMAINS, entity_id, SETTINGS_BESIDE_BLOCK, TILE_EVENTS, TILE_RESULT_EVENT, layout_snapshot, match_screen, HEADER_MIN_FIRMWARE, NAME_TILE_SETTINGS, TILE_BACKGROUNDS, TRANSPORT_MIN_FIRMWARE, alert_camera, alert_data, alert_reference, alert_service, alert_targets, controls_catalogue, device_prefixes, discover, discover_screens, encode, extras, forecast_kinds, header_items, inbox_prefix, message_action, min_firmware, packets, revision, screen_items, state_message, validate_header, validate_layout, validate_settings
from core import SETTING_ENTITIES, SETTING_RULES, setting_action, setting_entities, setting_from_state, state_word
from core import PAGE_TILE_REPEAT_MIN_FIRMWARE, SLOTS_PER_PAGE, firmware_features, packed_slots, run_tile_event, screen_firmware, version_text
import header_bar
import history_card
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

    def __init__(self, session, base, token):
        self.session, self.base, self.token = session, base.rstrip('/'), token
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
        # Home Assistant's own names and descriptions of actions and their fields (frontend/get_translations, English
        # like the editor), for Perform action (app 0.2.67). `get_services` has carried no translated names since 2025.10.
        self.service_names = {}
        # Home Assistant's words for states (frontend/get_translations `entity_component` and `entity`, English), which a
        # tile shows where it would show the raw state (app 0.2.67).
        self.state_words = {}
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
                elif event.get('event_type') in SERVICE_EVENTS:
                    # Every action counts for what the editor offers (app 0.2.67); a screen's own actions also decide
                    # how the app talks to it.
                    self.esphome_services |= body.get('domain') == 'esphome'
                    self.services_changed.set()
                elif event.get('event_type') in BROADCAST_EVENTS:
                    # Queued, not handled here: the calls wait for results this reader has to deliver.
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
            names = await self.request('frontend/get_translations', language='en', category='services')
            if isinstance((names or {}).get('resources'), dict):
                self.service_names = names['resources']
            words = {}
            for category in ('entity_component', 'entity'):
                found = await self.request('frontend/get_translations', language='en', category=category)
                if isinstance((found or {}).get('resources'), dict):
                    words.update(found['resources'])
            if words:
                self.state_words = words
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
                async with self.session.ws_connect(url, heartbeat=30, max_msg_size=16*1024*1024) as ws:
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
                    for event_type in (*REGISTRY_EVENTS, *BROADCAST_EVENTS, *TILE_EVENTS, *SERVICE_EVENTS):
                        await self.request('subscribe_events', event_type=event_type)
                    self.states = {s['entity_id']: s for s in await self.request('get_states')}
                    await self.registries()
                    await self.refresh_services()
                    try:
                        config = await self.request('get_config')
                        self.units = config.get('unit_system') or {}
                        self.time_zone = ZoneInfo(config.get('time_zone') or 'UTC')
                    except Exception:
                        self.time_zone = timezone.utc
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
                                    timeout=ClientTimeout(total=camera_feed.FETCH_SECONDS)) as response:
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
            url, headers = f'{root}{picture}', {'Authorization': 'Bearer ' + self.token}
        elif picture.startswith(('http://', 'https://')):
            url, headers = picture, {}
        else:
            raise ValueError('unknown picture address')
        async with self.session.get(url, headers=headers, timeout=ClientTimeout(total=camera_feed.FETCH_SECONDS)) as response:
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
                                     json={'state': state, 'attributes': attributes}) as response:
            response.raise_for_status()

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
                headers={'Authorization':'Bearer '+self.token}) as response:
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
        # sent: per inbox what the screen holds ({'layout', 'header', 'states', 'rev'}); last: the
        # last full send; pinged: the last keepalive ping.
        self.layouts, self.sent, self.status, self.last, self.pinged = {}, {}, {}, {}, {}
        # (entity, hours) -> (monotonic, 24 samples); filled by history_loop, read by sync_one.
        self.histories = {}
        self.history_wake = asyncio.Event()
        self.forecasts = {}
        self.listeners = set()  # asyncio.Event per open /api/events stream
        self.firmware = Firmware(os.environ.get("ESPHOME_CONFIG", "/homeassistant/esphome"), self.path.parent)
        self.updates = Updater(self, self.path.parent / 'updates.json')
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
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            # Versioned persistent data. Never silently overwrite an unknown schema.
            if raw.get('version') != 1 or not isinstance(raw.get('screens'), dict):
                raise ValueError('Unknown storage version; data stays unchanged.')
            # Loaded leniently: a tile setting this version doesn't know (saved by a newer one) never stops the app.
            self.layouts = {key: validate_layout(value, stored=True) for key, value in raw['screens'].items()}

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
        """{device_id: {key: entity_id}} for every screen that owns its settings; rebuilt per registry."""
        registry = getattr(self.ha, 'registry', [])
        if self._settings_source is not registry:
            by_device = {}
            for item in registry:
                if item.get('platform') == 'esphome' and item.get('device_id'):
                    by_device.setdefault(item['device_id'], []).append(item)
            index = {}
            for device, items in by_device.items():
                entities = setting_entities(items)
                if entities is not None:
                    index[device] = entities
            self._settings_source, self._settings_index = registry, index
        return self._settings_index

    def setting_entities(self, screen):
        """{key: entity_id} when this screen owns its settings, else None (they travel in the layout message)."""
        device = (screen or {}).get('device_id')
        return self.setting_index().get(device) if device else None

    def settings_view(self, screen):
        """What the editor shows under Screen settings.

        `owner` is 'screen' when the screen's own entities hold the settings, else 'layout'. `keys` are the
        settings this screen has, `unavailable` the ones Home Assistant cannot read or change right now (the
        screen is offline, or the entity is disabled); their value is None, not a default that could differ
        from what the screen has."""
        inbox = self.aliases.get(screen['id'], screen['id'])
        keys = [key for key in SETTING_RULES if key != 'show_clock' and (key != 'rotation' or screen.get('board') in ('guition', 'jc8012p4a1'))]
        entities = self.setting_entities(screen)
        if entities is None:
            try:
                values = validate_settings(self.layouts.get(inbox, {}).get('settings', {}))
            except ValueError:
                values = validate_settings({})
            if (self.firmware_version(inbox, screen) or (0, 0, 0)) < (0, 2, 44):
                keys = [key for key in keys if key not in ('auto_home', 'auto_home_seconds')]
            # Dark mode and the page buttons came after the screens took over their settings: firmware that gets them
            # with the layout lacks them.
            keys = [key for key in keys if key not in ('dark_mode', 'page_buttons')]
            return {'owner': 'layout', 'values': values, 'keys': keys, 'unavailable': []}
        # Only the settings this screen has an entity for: one added in later firmware stays out of the panel.
        keys = [key for key in keys if key in entities]
        values = {key: setting_from_state(key, self.ha.states.get(entities[key])) for key in keys}
        return {'owner': 'screen', 'values': values, 'keys': keys, 'unavailable': [key for key in keys if values[key] is None]}

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
        base = self.layouts.get(inbox) or {'title': (screen or {}).get('name') or 'Home', 'tiles': []}
        layout = validate_layout({**base, 'settings': settings})
        updated = {**self.layouts, inbox: layout}
        self.write_layouts(updated)
        self.layouts = updated
        if on_screen and inbox in self.sent:
            self.sent[inbox] = {**self.sent[inbox], 'layout': self.layout_message(inbox, layout, screen or self.screen(inbox) or {})}
        self.notify()

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
            raise ValueError("This isn't a paired ESP screen. Refresh the overview.")
        view = self.settings_view(screen)
        if not isinstance(changes, dict) or not changes or set(changes) - set(view['keys']):
            raise ValueError('Unknown screen settings; refresh the management page.')
        if view['owner'] == 'screen' and not screen.get('online'):
            raise ValueError('This screen is offline. You can change its settings once it is back.')
        missing = [SETTING_ENTITIES[key][1] for key in changes if key in view['unavailable']]
        if missing:
            raise ValueError(f"{', '.join(missing)} can't be changed now: the entity is off in Home Assistant, or the screen is restarting.")
        # A setting Home Assistant cannot read (its entity is off) is checked at its default.
        wanted = {**{key: value for key, value in view['values'].items() if value is not None}, **changes}
        if 'brightness' in changes and type(changes['brightness']) is int:
            # A lower brightness pulls both dim levels down with it, as on the screen.
            for dim in ('standby_brightness', 'night_brightness'):
                if dim not in changes:
                    wanted[dim] = min(wanted.get(dim, SETTING_RULES[dim][0]), changes['brightness'])
        merged = validate_settings(wanted)
        if merged['rotation'] and screen.get('board') not in ('guition', 'jc8012p4a1'):
            raise ValueError('Rotation requires a Guition with firmware 0.2.9 or newer.')
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
        await self.ha.send(inbox, await self.card_history(entity, hours, what), action)

    async def card_history(self, entity, hours, what):
        """The history message, from a short cache; screens asking at the same time share one fetch."""
        key = (entity, hours)
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
            raise ValueError("This isn't a paired ESP screen. Refresh the overview.")
        layout = validate_layout(data)
        # A CYD has no memory for camera images, whatever its firmware; say so before asking for an update.
        if any(t['entity'].split('.')[0] in CAMERA_DOMAINS for t in layout['tiles']) and screen.get('board') not in camera_feed.BOXES:
            raise ValueError('Camera images need a Guition screen.')
        needed = self.needs_firmware(inbox, layout, screen)
        if needed:
            raise ValueError(f"Install screen firmware {needed} or newer first for these tiles.")
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
        if layout.get('settings',{}).get('rotation',0) and screen.get('board') not in ('guition', 'jc8012p4a1'):
            raise ValueError('Rotation requires a Guition with firmware 0.2.9 or newer.')
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
            for tile, slot in zip(layout['tiles'], packed_slots(layout['tiles'])):
                tile['slot'] = slot
        layout = validate_layout(layout)
        known = {e['id'] for e in entities} | set(BUILTIN)
        if any(t['entity'] not in known for t in layout['tiles']):
            raise ValueError('A chosen entity no longer exists. Look up the new entity.')
        if any(item['type'] == 'entity' and item['entity'] not in known and item['entity'] not in self.ha.states for item in header_items(layout)):
            raise ValueError('An entity in the top bar no longer exists. Choose a different one.')
        # The screen takes the layout in one message of at most 4096 bytes, which lists every tile's entity id: 48 tiles
        # with long ids can pass every rule above and still never reach the screen (app 0.2.78).
        try:
            encode(self.layout_message(inbox, layout, screen))
        except ValueError:
            raise ValueError("These tiles' entity IDs are too long together to fit in one message to the screen; "
                             "remove a few tiles.") from None
        updated = {**self.layouts, inbox: layout}
        self.write_layouts(updated)
        self.layouts = updated
        self.sent.pop(inbox, None)
        self.status[inbox] = 'Saved; waiting for sync'
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
        layout = validate_layout(data)
        inbox = self.aliases.get(inbox, inbox)
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
        # Grid positions (firmware 0.2.26+; older firmware ignores them and packs the entities in order).
        message = {'v': 1, 'op': 'layout', 'inbox': inbox, 'title': layout['title'], 'entities': [t['entity'] for t in tiles],
                   'slots': [t['slot'] for t in tiles], 'keepalive': KEEPALIVE_SECONDS}
        if 'pages' in layout:
            message['pages'] = layout['pages']
        # A screen that owns its settings (firmware 0.2.49+) gets none: they would overwrite what changed on it.
        if 'settings' in layout and self.setting_entities(screen) is None:
            # `settings` is the fixed eleven-key block older firmware insists on; everything added
            # later travels as its own key, which firmware that predates it simply ignores.
            message['settings'] = {k:v for k,v in layout['settings'].items() if k not in SETTINGS_BESIDE_BLOCK}
            message['swipe_pages'] = layout['settings'].get('swipe_pages',False)
            message['auto_home'] = layout['settings'].get('auto_home',True)
            message['auto_home_seconds'] = layout['settings'].get('auto_home_seconds',120)
            if screen.get('board') in ('guition', 'jc8012p4a1'):
                message['rotation'] = layout['settings'].get('rotation',0)
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
        needed = self.needs_firmware(inbox, layout, screen)
        if needed:
            self.status[inbox]=f"Layout saved; firmware {needed}+ needed for these tiles"
            return False
        tiles = layout['tiles']
        layout_msg = self.layout_message(inbox, layout, screen)
        try:
            encode(layout_msg)
        except ValueError:
            # Saved by an app before 0.2.78, which didn't check this: nothing to retry until the layout changes.
            self.status[inbox] = 'Layout saved; too large for one message to the screen, remove a few tiles'
            return False
        previous = self.sent.get(inbox)
        full = force or not previous or previous['layout'] != layout_msg or dirty is None
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
        self.sent[inbox] = {'layout': layout_msg, 'header': header_msg, 'states': states, 'rev': rev}
        # The hourly timer follows a real full transmission; any message refreshes the screen's
        # feed window, so the ping timer follows whatever went out (a rebuild without differences,
        # after a registry refresh, must not postpone the ping).
        if force or not previous:
            self.last[inbox] = time.monotonic()
        if outgoing:
            self.pinged[inbox] = time.monotonic()
        self.status[inbox] = 'Sent to Home Assistant'
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
                    self.status[inbox] = 'Screen offline; changes saved'
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
                    self.status[inbox] = 'Sending failed; retrying automatically'
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

    async def camera_message(self, entity, view, board, still=None):
        """The screen message for one camera view: a link to its image, or an empty link when there is none."""
        url = ''
        base = await camera_feed.base_url(self.ha.request)
        if base:
            box = camera_feed.BOXES[board][view]
            if view == 'thumb':
                token = self.camera.link(entity, box, still) if still else None
            else:
                token = self.camera.link(entity, box) if await self.camera.frame(entity, box) else None
            url = f'{base}/camera/{token}.bmp' if token else ''
        else:
            LOG.warning('Camera images: no address for this app on the LAN; set SCREEN_CAMERA_URL')
        return {'v': 1, 'op': 'camera', 't': 'alert' if view == 'thumb' else 'full', 'e': entity, 'u': url}

    async def answer_camera(self, request):
        """One screen's request: a camera it may show, on a screen that draws camera images."""
        if not isinstance(request, dict):
            return
        inbox = self.aliases.get(request.get('inbox'), request.get('inbox'))
        entity = request.get('entity')
        screen = self.screen(inbox) if isinstance(inbox, str) else None
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
        message = await self.cover_message(entity, *cover) if cover else await self.camera_message(entity, 'full', screen['board'])
        await self.ha.send(inbox, message, action)
        LOG.info('%s %s on %s%s', 'Cover of' if cover else 'Camera', entity, screen['name'], '' if message['u'] else ': no image')

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
        boards = {}
        for screen in screens:
            boards.setdefault(screen['board'], []).append(screen)
        for board, group in boards.items():
            found = await self.camera.frame(camera, camera_feed.BOXES[board]['thumb'], fresh=False, now=True)
            message = await self.camera_message(camera, 'thumb', board, found[1] if found else None)
            results = await asyncio.gather(*(self.ha.send(screen['id'], message, self.transport(screen['id'], screen)) for screen in group),
                                           return_exceptions=True)
            failed = sum(isinstance(result, BaseException) for result in results)
            LOG.info('Alert image of %s: %d of %d screens%s', camera, len(group) - failed, len(group), '' if message['u'] else ' (no image)')

    async def broadcast(self, event_type, data):
        """An alert event for every screen: the matching action on each screen that can show it, all at once."""
        action = BROADCAST_EVENTS[event_type]
        service_data, unusable = alert_data(data) if action == 'show_alert' else ({}, [])
        camera, usable = alert_camera(data) if event_type == BROADCAST_SHOW else ('', True)
        if not usable:
            unusable.append('camera')
        if unusable:
            LOG.warning('%s: unusable %s left empty', event_type, ', '.join(unusable))
        ready, skipped = alert_targets(self.screens())
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
        LOG.info('%s: %d of %d screens%s', event_type, len(ready) - len(failed), len(ready) + len(skipped),
                 f" (not: {'; '.join(notes)})" if notes else '')
        shown = [screen for screen, result in zip(ready, results) if not isinstance(result, BaseException)]
        if viewers and any(screen in shown for screen in viewers):
            await self.alert_images(camera, [screen for screen in viewers if screen in shown])
        return {'sent': len(ready) - len(failed), 'skipped': len(skipped), 'failed': len(failed)}

    async def tile_event(self, event_type, data):
        """One tile event: the screen it names, the changed layout, saved and pushed like the editor does. Returns the
        screen and the tile the event acted on (None for an order)."""
        screen = match_screen(self.screens(), data.get('screen'), self.layouts)
        inbox = self.aliases.get(screen['id'], screen['id'])
        # Firmware 0.2.65+ takes a navigation tile on several pages; an older screen keeps one per page it goes to.
        repeat = (self.firmware_version(inbox, screen) or (0, 0, 0)) >= PAGE_TILE_REPEAT_MIN_FIRMWARE
        layout, tile = run_tile_event(self.layouts.get(inbox) or {'title': screen['name'], 'tiles': []}, TILE_EVENTS[event_type], data, repeat)
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
                    answer.update(page=tile['slot'] // SLOTS_PER_PAGE + 1, slot=tile['slot'])
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
            snapshot = layout_snapshot(screen, layout)
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
                await self.broadcast(event_type, data)
            except Exception as error:
                LOG.warning('%s failed (%s)', event_type, type(error).__name__)

def create_app(manager, development=False):
    csrf = secrets.token_urlsafe(32)
    @web.middleware
    async def guard(request, handler):
        allowed = {'127.0.0.1', '::1'} if development else {'172.30.32.2'}
        if request.remote not in allowed:
            raise web.HTTPForbidden(text='Open this page through Home Assistant.')
        if request.method not in {'GET', 'HEAD'} and request.headers.get('X-Screen-CSRF') != csrf:
            raise web.HTTPForbidden(text='Refresh this page and try again.')
        try:
            response = await handler(request)
        except ValueError as error:
            return web.json_response({'error': str(error)}, status=400)
        # Home Assistant said no, or can't be reached (Identify, Try it, a setting): a sentence the page shows, never a
        # bare 500 with a traceback in the log (app 0.2.78). Refused is a ConnectionError, so it comes first.
        except Refused as error:
            return web.json_response({'error': f"Home Assistant didn't take it: {error.detail or 'no reason given'}."}, status=400)
        except (ConnectionError, TimeoutError):
            return web.json_response({'error': "Home Assistant isn't reachable right now. Try again in a moment."}, status=503)
        except web.HTTPRequestEntityTooLarge:
            return web.json_response({'error': 'That request is too large.'}, status=413)
        except (TypeError, KeyError):
            return web.json_response({'error': 'Invalid input. Check the name, board, and chosen tiles.'}, status=400)
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
            screen['layout'] = manager.layouts.get(screen['id'], {'title': 'Home', 'tiles': []})
            screen['settings'] = manager.settings_view(screen)
            screen['delivery'] = manager.status.get(screen['id'], 'Choose your first tiles')
            screen['update'] = manager.updates.state_for(screen, profiles)
            screen['alert_action'] = alert_service(screen.get('node'))
            screen['dismiss_action'] = alert_service(screen.get('node'), 'dismiss_alert')
            # What the editor may offer this screen, by the firmware the app's own checks go by (app 0.2.78): an offline
            # screen keeps its 48 tiles, and the editor needn't know the version rules.
            version = manager.firmware_version(screen['id'], screen)
            screen['firmware_known'] = version_text(version)
            screen.update(firmware_features(version))
        return {'csrf': csrf, 'connected': manager.ha.online, 'screens': screens,
                'pending': manager.pending_profiles(screens, profiles),
                'updates': manager.updates.summary(screens, profiles)}
    async def inventory(request):
        if request.query.get('light') == '1':
            # The page polls the light form; entities, backgrounds and icons (~100 KB) only on demand.
            return web.json_response(light_payload())
        screens, entities = manager.inventory()
        payload = light_payload(screens)
        payload['entities'] = entities
        payload['backgrounds'] = TILE_BACKGROUNDS
        payload['controls'] = controls_catalogue()
        payload['icons'] = tile_icons.editor()
        payload['alerts'] = alert_reference()
        # What's new for the Update badge: here only, not in every live update (app 0.2.78).
        payload['changelog'] = manager.updates.changelog
        payload['claude_skill'] = claude_skill.status(manager.skill_dir)
        payload['builtin'] = [{'id': key, 'name': name, 'device': 'Built into the screen', 'area': '', 'state': 'ok'} for key, name in BUILTIN.items()]
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
        return web.json_response({'actions': ha_catalogue.action_choices(entity, actions, ha.states.get(entity), ha.services,
                                                                         getattr(ha, 'service_names', {}), ha.platform_of(entity))})
    async def change_settings(request):
        """Screen settings apply one change at a time, like the settings page on the screen (app 0.2.57)."""
        data = await request.json()
        try:
            view = await manager.change_settings(request.match_info['inbox'], data.get('settings') if isinstance(data, dict) else None)
        except Refused as error:
            raise ValueError(f"Home Assistant didn't take the change: {error.detail or 'no reason given'}.") from error
        except (ConnectionError, TimeoutError) as error:
            raise ValueError("Home Assistant isn't reachable right now. Try again in a moment.") from error
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
        if screen is None: raise ValueError('Unknown screen.')
        layout=manager.layouts.get(inbox,{'tiles':[]})
        return web.json_response({'screen':screen,
            'delivery':manager.status.get(inbox), 'layout':layout,
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
            raise ValueError('Unknown screen.')
        ready, skipped = alert_targets([screen])
        if not ready:
            raise ValueError(f"{screen['name']} can't show an alert: {skipped[0][1] if skipped else 'not ready'}.")
        return ready[0]
    async def identify(request):
        """Identify (app 0.2.73): the screen shows a short card and blinks its backlight, so you know which one it is."""
        screen = one_alert_target(request.match_info['inbox'])
        data, _ = alert_data({'title': f"This is {screen['name']}", 'subtitle': 'Identify, from ESP Screens', 'icon': 'bell-ring',
                              'color': 'blue', 'button_text': 'OK', 'timeout': 8, 'flash': True})
        await manager.ha.call(alert_service(screen['node']), data)
        return web.json_response({'ok': True})
    async def test_alert(request):
        """Alerts → Try it (app 0.2.73): one alert to one screen or to every screen, with the fields an automation sends."""
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Invalid alert.')
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
    async def firmware_status(request): return web.json_response(manager.firmware.status())
    async def firmware_start(request): return web.json_response(manager.firmware.start(await request.json()))
    async def firmware_override(request):
        return web.json_response(manager.firmware.override(request.match_info['file']))
    async def firmware_override_save(request):
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError('Invalid override data.')
        return web.json_response(manager.firmware.save_override(request.match_info['file'], data.get('content')))
    async def firmware_create(request):
        # Profile, missing wifi secrets and (with a USB port or the download) the build and flash in one request.
        return web.json_response(manager.firmware.install(await request.json()))
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
    app.router.add_post('/api/alerts/test', test_alert)
    app.router.add_get('/api/entity-actions', entity_actions)
    app.router.add_post('/api/header-preview', header_preview)
    app.router.add_post('/api/claude-skill', install_claude_skill)
    app.router.add_get('/api/claude-skill.zip', download_claude_skill)
    app.router.add_get('/api/events', events)
    app.router.add_put('/api/screens/{inbox}', save)
    app.router.add_put('/api/screens/{inbox}/settings', change_settings)
    app.router.add_static('/assets/', static / 'assets')
    return app

async def main():
    development = os.environ.get('SCREEN_DEV') == '1'
    token = os.environ.get('SUPERVISOR_TOKEN', '')
    if development and os.environ.get('HA_TOKEN_FILE'):
        token = Path(os.environ['HA_TOKEN_FILE']).read_text().strip()
    if not token:
        raise SystemExit('No Home Assistant access. Start the app via Supervisor.')
    async with ClientSession(timeout=ClientTimeout(total=20)) as session:
        ha = HomeAssistant(session, os.environ.get('HA_API', 'http://supervisor/core/api'), token)
        manager = Manager(ha, Path(os.environ.get('SCREEN_DATA', '/data')) / 'screens.json')
        # handle_signals: SIGTERM (the Supervisor stopping the app, `docker stop`) and SIGINT end the app through the
        # cleanup below, which also stops a running build, instead of waiting ten seconds for SIGKILL (app 0.2.78).
        runner = web.AppRunner(create_app(manager, development), access_log=None, handle_signals=True)
        await runner.setup()
        await web.TCPSite(runner, '127.0.0.1' if development else '0.0.0.0', 8099).start()
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
