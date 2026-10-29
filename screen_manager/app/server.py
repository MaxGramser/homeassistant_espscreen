"""HA Ingress app. HA writes: text.set_value on discovered inboxes (or the screen_message action on firmware 0.2.33+), each screen's alert actions when an alert event for every screen fires, and one persistent notification when a nightly update stops."""
import asyncio
from collections import Counter, OrderedDict
import contextlib
import io
import ipaddress
import json
import logging
import os
import re
from pathlib import Path
import secrets
import socket
import time
from datetime import date, datetime, timedelta, timezone
import math
from urllib.parse import urlsplit
import automations
import calendar_feed
import doorbell
import durations
import picture_legacy
import lan_address
import picture_links
import picture_paint
import picture_question
import picture_service
import picture_sources
import camera_source
import live_stream
import claude_skill
import screen_video
import screen_hang
import screen_labels
import screen_saver
import saver_photos
import feedback
import reports
import build_server
from build_queue import BuildQueue
from firmware import Firmware
import ha_pairing
import catalogue
import ha_catalogue
import light_effects
import light_groups
import cover_groups
import media_library
import rest_mosaic
import vacuum_card
import speakers
import map_card
import energy_flow
import plugin_pictures
import map_tiles
import valetudo_map
import tile_icons
import text_tile
import template_service
from updates import Updater
import core
import entity_settings
import plugins

from aiohttp import ClientError, ClientSession, ClientTimeout, WSMsgType, web
from core import alarm_extras, lock_extras, ALERT_EVENT, board_of, BROADCAST_DISMISS, BROADCAST_EVENTS, BROADCAST_SHOW, BUILTIN, CAMERA_DOMAINS, entity_id, SETTINGS_BESIDE_BLOCK, TILE_EVENTS, TILE_RESULT_EVENT, layout_snapshot, match_screen, HEADER_MIN_FIRMWARE, NAME_TILE_SETTINGS, TRANSPORT_MIN_FIRMWARE, alert_action, alert_camera, alert_choice, alert_data, choice_service, ALERT_CHOICE_ACTION, ALERT_CHOICE_MIN_FIRMWARE, parse_firmware, alert_reference, alert_screen_choice, alert_screen_names, alert_service, alert_targets, backgrounds, builtin_name, controls_catalogue, device_prefixes, discover, discover_screens, encode, entity_slug, extras, media_cover, media_extras, forecast_kinds, header_items, inbox_prefix, message_action, min_firmware, name_clash, packets, revision, screen_items, state_message, validate_header, validate_layout, validate_settings
from core import ENERGY_TILE, MAP_TILE_MIN_FIRMWARE, WEATHER_WEEK, calibrate_entity, can_standby, dimmable, SETTING_ENTITIES, SETTING_RULES, STANDBY_KEYS, setting_action, setting_entities, setting_from_state, state_word
from core import BAR_CARDS_FEATURE, BOARD_KEYS, has_battery, has_module, is_key, drawn_controls, FAVORITE_KINDS, SCREENSAVER_MIN_FIRMWARE, short, plugin_tile
from core import (FIRMWARE_MAX_BAR_ITEMS, FIRMWARE_MAX_PAGES, FIRMWARE_MAX_TILES, Grid, page_target, PAGE_TILE_REPEAT_MIN_FIRMWARE, ENTITY_REPEAT_MIN_FIRMWARE, ROTATION_MIN_FIRMWARE, SHAPES, firmware_features, grid_of, orientation_at,
                  packed_slots, run_tile_event, screen_firmware, shape_of, turns_of, update_in_tessera, version_text)
import header_bar
import history_card
import i18n
from i18n import REQUEST_LANGUAGE, TRANSLATIONS, Region, english, screen_t, shown, t
from zoneinfo import ZoneInfo
from layout_store import LayoutStore, Conflict
from page_layout import (FORMAT as PAGE_FORMAT, LayoutError, compile_tiles, grid_of_record, screen_grid_of_record,
                         legacy_projection, legacy_edit, validate_document, bar_items, replace_tiles, CompiledLayouts, fingerprint)
from layout_migrations import migrate_legacy
import page_delivery
import page_service
import preview_images
import preview_events
from page_capabilities import CapabilityCache, identity as page_identity


def row_icon(eid, state, attrs, entry):
    """Codepoint of the icon Home Assistant shows for a row of a light's effects page, when the screen's fonts carry it."""
    return tile_icons.ha_icon(attrs) or tile_icons.default_glyph(eid, state, attrs, entry)

LOG = logging.getLogger('screen_manager')

REGISTRY_EVENTS = ('entity_registry_updated', 'device_registry_updated', 'area_registry_updated', 'floor_registry_updated')
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
PAGE_DELIVERY_WORDS = {'Saved, waiting for screen': 'saved', 'Applying': 'applying', 'Applied': 'applied'}


def status_text(status):
    """A screen's status for the editor: its protocol words in the editor's language, ours as they were made."""
    status = shown(status)
    if isinstance(status, str) and not isinstance(status, i18n.Text):
        if status.startswith('Session:'):
            return t('addon.status.screen.ready')
        if status in SCREEN_STATUS_WORDS:
            return t(f'addon.status.screen.{SCREEN_STATUS_WORDS[status]}')
        if status.startswith('Error: '):
            return t('addon.status.screen.error', reason=status[len('Error: '):])
    return status
FORECAST_SECONDS = 1800
# Home Assistant's Energy settings, which the energy card is drawn from (energy_flow.py): read again every five minutes,
# so a sensor added there reaches the card without a restart.
ENERGY_PREFS_SECONDS = 300
# A screen that answers its ping (firmware 0.2.49+) is asked with this timeout, so a busy screen never holds
# up the others. An answer that the screen lacks something repeats everything, after this many seconds right
# after a full send, doubling up to RESEND_GUARD_SECONDS while it keeps failing.
ANSWER_TIMEOUT_SECONDS = 5
ANSWER_RETRY_SECONDS = 30
SERVICE_EVENTS = ('service_registered', 'service_removed')
# A plugin on a screen asks the app something (docs/PLUGINS.md): the event its tessera::send() fires.
PLUGIN_EVENT = 'esphome.screen_plugin'

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

    @staticmethod
    async def _is_private_host(host):
        """Whether a host should be blocked for remote media requests; Home Assistant's own media proxies are allowed.
        A name is looked up through the event loop (app 0.4.15), so a slow DNS server holds up this picture only."""
        if not host or host == 'localhost':
            return True
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified
        except ValueError:
            try:
                for family, _, _, _, sockaddr in await asyncio.get_running_loop().getaddrinfo(host, None):
                    addr = sockaddr[0]
                    if addr and addr != 'localhost':
                        ip = ipaddress.ip_address(addr)
                        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                            return True
            except (socket.gaierror, OSError, TypeError, ValueError):
                return True
        return False

    @staticmethod
    async def _allow_media_url(url):
        """Only accept local Home Assistant routes or non-private remote URLs with a clear scheme."""
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        host = (parsed.hostname or '').lower()
        if not host:
            return False
        if parsed.hostname and host in ('localhost', '127.0.0.1', '::1'):
            return False
        if await HomeAssistant._is_private_host(host):
            return False
        return True

    def __init__(self, session, base, token):
        self.session, self.base, self.token = session, base.rstrip('/'), token
        self.ws = None
        self.next_id = 0
        self.pending = {}
        # The template tiles' render_template subscriptions (template_service.py): their id, and who takes their events.
        # `connection` grows with every websocket: a subscription lives as long as the websocket it was made on.
        self.template_subs = {}
        self.connection = 0
        self.states = {}
        self.registry, self.devices, self.areas, self.floors = [], [], [], []
        self.online = False
        self.changed = asyncio.Event()
        self.state_events = preview_events.Changes()
        # Entity ids the manager cares about; None wakes it for every state change.
        self.relevant = None
        # Entity ids whose state changed since the manager last looked; it only rebuilds those tiles.
        self.dirty = set()
        self.registry_changed = asyncio.Event()
        # A repair issue came or went (app 0.4.73): one may say Home Assistant ignored a screen's tap (ha_pairing.py).
        self.issues_changed = asyncio.Event()
        self.setting_events = []
        self.time_zone = None
        # The home's name in Home Assistant (get_config `location_name`): the energy card names the house with it, as
        # Home Assistant's own live power view does.
        self.location_name = ''
        # Home Assistant's unit system; a climate entity's temperature carries no unit of its own.
        self.units = {}
        # Home Assistant's own language (get_config), and the one the screens speak (Settings -> Language & region,
        # app 0.2.90), in which the words for states are fetched; the manager binds `language_of`.
        self.ha_language = None
        self.language_of = lambda: 'en'
        self.config_stale = False
        self.on_config = lambda: None
        # Home Assistant's time zone changed (a screen in a van that crosses one): the manager resyncs the
        # screens' clocks, which Home Assistant's ESPHome integration only tells a screen when it connects.
        self.on_time_zone = lambda: None
        # (event type, data) of alert events for every screen, for Manager.alert_loop.
        self.broadcasts = asyncio.Queue()
        # (event type, data) of tile events (app 0.2.51+), for Manager.tile_loop.
        self.tile_events = asyncio.Queue()
        # (event type, data) of the doorbell's events (esp_screens_doorbell, esp_screens_dismiss_doorbell) and of a screen's
        # report of a ring (esphome.screen_doorbell, docs/DOORBELL.md), for Manager.doorbell_loop.
        self.doorbell_events = asyncio.Queue()
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
        # A tap on a compact calendar event (calendar_feed.EVENT): {inbox, entity, i, c, s, e, day}, for
        # Manager.calendar_loop.
        self.calendar_requests = asyncio.Queue()
        # A player's library (firmware 0.24.0+): a folder a screen opens and an item it plays, for Manager.media_loop.
        self.media_requests = asyncio.Queue()
        # A plugin's question to the app (docs/PLUGINS.md, tessera::send): answered by Plugins.answer.
        self.plugin_requests = asyncio.Queue()
        # The widest features a media player reported (media_library.FeatureMemory), set by the manager: what the
        # editor offers for a player at rest (GitHub #88).
        self.widen = None

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
                callback = self.template_subs.get(data.get('id'))
                if callback is not None:
                    callback(event)
                elif event.get('event_type') == 'esphome.screen_setting':
                    self.setting_events.append(body)
                    self.changed.set()
                elif event.get('event_type') == 'esphome.screen_history':
                    self.history_requests.put_nowait(body)
                elif event.get('event_type') == 'esphome.screen_camera':
                    self.camera_requests.put_nowait(body)
                elif event.get('event_type') == light_effects.OPTIONS_EVENT:
                    self.options_requests.put_nowait(body)
                elif event.get('event_type') == calendar_feed.EVENT:
                    if self.calendar_requests.qsize() < 32:
                        self.calendar_requests.put_nowait(body)
                elif event.get('event_type') == PLUGIN_EVENT:
                    if self.plugin_requests.qsize() < 32:
                        self.plugin_requests.put_nowait(body)
                elif event.get('event_type') in (media_library.BROWSE_EVENT, media_library.PLAY_EVENT, speakers.SPEAKER_EVENT):
                    self.media_requests.put_nowait((event['event_type'], body))
                elif event.get('event_type') == 'state_changed':
                    eid = body.get('entity_id')
                    if body.get('new_state'):
                        self.states[eid] = body['new_state']
                    else:
                        self.states.pop(eid, None)
                    # Unsaved/virtual previews also follow entities not used by a physical screen.
                    self.state_events.notify(eid)
                    if self.relevant is None or eid in self.relevant:
                        self.dirty.add(eid)
                        self.changed.set()
                elif event.get('event_type') in REGISTRY_EVENTS:
                    self.registry_changed.set()
                elif event.get('event_type') == 'repairs_issue_registry_updated':
                    self.issues_changed.set()
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
                elif event.get('event_type') in (*doorbell.EVENTS, doorbell.EVENT):
                    self.doorbell_events.put_nowait((event['event_type'], body))
        raise ConnectionError('Home Assistant connection lost.')

    async def subscribe_template(self, template, callback):
        """A render_template subscription (a template tile, template_service.py): `callback(event)` takes each result
        Home Assistant sends ({"result": ...} or {"error": ..., "level": ...}); returns its id for unsubscribe_template."""
        if self.ws is None or self.ws.closed:
            raise ConnectionError("Home Assistant isn't connected.")
        # Registered before the request: the first result may come right behind the answer.
        key = self.next_id + 1
        self.template_subs[key] = callback
        try:
            await self.request('render_template', template=template, report_errors=True, strict=False, timeout=3)
        except Refused as error:
            self.template_subs.pop(key, None)
            raise template_service.Refused(error.detail) from None
        except BaseException:
            self.template_subs.pop(key, None)
            raise
        return key

    async def unsubscribe_template(self, key):
        if self.template_subs.pop(key, None) is not None:
            await self.request('unsubscribe_events', subscription=key)

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

    def display_precision(self, entity):
        """A sensor's display precision as Home Assistant's entity settings show it (entity-registry-settings-editor.ts):
        the one chosen there (`own`, None for Default), the one its integration suggests (`suggested`, what Default
        means), and whether it can be chosen at all: only an entity in the registry has settings."""
        entry = next((item for item in self.registry or [] if isinstance(item, dict) and item.get('entity_id') == entity), None)
        options = ((entry or {}).get('options') or {}).get('sensor') or {}
        whole = lambda value: value if type(value) is int and 0 <= value <= 6 else None
        return {'own': whole(options.get('display_precision')), 'suggested': whole(options.get('suggested_display_precision')),
                'editable': entry is not None}

    async def set_display_precision(self, entity, precision):
        """The display precision of a sensor, set in Home Assistant itself as its entity settings set it
        (config/entity_registry/update with the sensor's options): every dashboard, tile and top bar follows it. None is
        Default. The registry entry is changed here at once; Home Assistant's registry event brings the rest."""
        # Home Assistant replaces the sensor's options as a whole, so they go back as they are with only the precision
        # changed, as its dialog sends them (the integration's suggested precision stays).
        entry = next((item for item in self.registry or [] if isinstance(item, dict) and item.get('entity_id') == entity), None)
        options = {**(((entry or {}).get('options') or {}).get('sensor') or {}), 'display_precision': precision}
        answer = await self.request('config/entity_registry/update', entity_id=entity, options_domain='sensor', options=options)
        entry = (answer or {}).get('entity_entry') if isinstance(answer, dict) else None
        if isinstance(entry, dict):
            self.registry = [entry if isinstance(item, dict) and item.get('entity_id') == entity else item for item in self.registry or []]
        return self.display_precision(entity)

    async def registries(self):
        self.registry, self.devices, self.areas = await asyncio.gather(
            self.request('config/entity_registry/list'), self.request('config/device_registry/list'), self.request('config/area_registry/list'))
        # The floors, in Home Assistant's order (a vacuum card groups its rooms by them, as Home Assistant's own view does).
        try:
            self.floors = await self.request('config/floor_registry/list') or []
        except Exception:  # noqa: BLE001 - a Home Assistant without floors: the rooms stand in one group
            self.floors = []

    async def actions_blocked(self):
        """The devices that may not perform Home Assistant actions (app 0.4.63): the ESPHome integration keeps that off
        until someone turns on "Allow the device to perform Home Assistant actions", ignores the screen's taps meanwhile,
        and raises its own repair issue, service_calls_not_enabled-<the device's MAC>, at the first one it ignores. The
        editor shows the fix for those screens. Empty when Home Assistant does not say (an older one, no admin)."""
        try:
            data = await self.request('repairs/list_issues')
        except Exception:  # noqa: BLE001 - a missing answer only hides a hint
            return set()
        macs = {str(issue.get('issue_id', ''))[len('service_calls_not_enabled-'):].lower()
                for issue in (data or {}).get('issues', []) if isinstance(issue, dict) and issue.get('domain') == 'esphome'
                and str(issue.get('issue_id', '')).startswith('service_calls_not_enabled-')}
        return {device.get('id') for device in self.devices or [] if isinstance(device, dict)
                and any(isinstance(link, (list, tuple)) and len(link) == 2 and link[0] == 'mac' and str(link[1]).lower() in macs
                        for link in device.get('connections') or [])}

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
            zone = ZoneInfo(config.get('time_zone') or 'UTC')
            moved = isinstance(self.time_zone, ZoneInfo) and self.time_zone.key != zone.key
            self.time_zone = zone
            self.location_name = config.get('location_name') if isinstance(config.get('location_name'), str) else ''
            language = config.get('language')
            changed = isinstance(language, str) and language != self.ha_language
            self.ha_language = language if isinstance(language, str) else self.ha_language
            if changed:
                self.on_config()
            if moved:
                self.on_time_zone()
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
        # A media player at rest offers what it did while it played (GitHub #88): Home Assistant lists the actions of
        # the features it reports now, so the ones it reported before come from the action descriptions.
        wide = self.widen(entity_id, state) if self.widen else state
        widened = wide is not state
        key = (self.services_rev, id(self.registry), attributes.get('supported_features'), attributes.get('device_class'),
               (wide.get('attributes') or {}).get('supported_features'))
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
        if widened:
            actions = actions | frozenset(ha_catalogue.local_actions(self.services, entity_id, wide.get('attributes') or {}, self.platform_of(entity_id)))
        self.targets[entity_id] = (key, actions)
        return actions

    async def capabilities(self, entity_id):
        """What the editor may offer for one entity (ha_catalogue.capabilities), or None while Home Assistant can't say."""
        actions = await self.entity_actions(entity_id)
        if actions is None:
            return None
        state = self.states.get(entity_id)
        return ha_catalogue.capabilities(entity_id, actions, self.widen(entity_id, state) if self.widen else state, self.services)

    def ws_url(self):
        return ('ws://supervisor/core/websocket' if self.base == 'http://supervisor/core/api'
                else self.base.replace('http://', 'ws://').replace('https://', 'wss://') + '/websocket')

    @contextlib.asynccontextmanager
    async def websocket(self):
        """A websocket of its own, authenticated, for a conversation that has many answers (a live camera's WebRTC,
        camera_source.py): it ends with the conversation, and Home Assistant ends the session with it."""
        async with self.session.ws_connect(self.ws_url(), heartbeat=30, max_msg_size=4*1024*1024) as ws:
            await ws.receive_json(timeout=15)
            await ws.send_json({'type': 'auth', 'access_token': self.token})
            if (await ws.receive_json(timeout=15)).get('type') != 'auth_ok':
                raise ConnectionError('Home Assistant authentication failed.')
            yield ws

    def camera_streams(self, entity):
        """Whether a camera has a stream of its own (CameraEntityFeature.STREAM): an RTSP camera, not a snapshot one."""
        features = ((self.states.get(entity) or {}).get('attributes') or {}).get('supported_features') or 0
        try:
            return bool(int(features) & camera_source.STREAM_FEATURE)
        except (TypeError, ValueError):
            return False

    async def run(self):
        url = self.ws_url()
        while True:
            reader, connected = None, None
            try:
                async with self.session.ws_connect(url, heartbeat=30, max_msg_size=16*1024*1024) as ws:
                    self.ws = ws
                    self.connection += 1
                    self.template_subs = {}
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
                    await self.request('subscribe_events', event_type=calendar_feed.EVENT)
                    await self.request('subscribe_events', event_type=PLUGIN_EVENT)
                    await self.request('subscribe_events', event_type=media_library.BROWSE_EVENT)
                    await self.request('subscribe_events', event_type=media_library.PLAY_EVENT)
                    await self.request('subscribe_events', event_type=speakers.SPEAKER_EVENT)
                    await self.request('subscribe_events', event_type='repairs_issue_registry_updated')
                    for event_type in (*REGISTRY_EVENTS, *BROADCAST_EVENTS, ALERT_EVENT, *TILE_EVENTS, *SERVICE_EVENTS, *doorbell.EVENTS, doorbell.EVENT):
                        await self.request('subscribe_events', event_type=event_type)
                    self.states = {s['entity_id']: s for s in await self.request('get_states')}
                    await self.registries()
                    # The config first: its language decides the language of the words for states (app 0.2.90).
                    await self.request('subscribe_events', event_type='core_config_updated')
                    await self.read_config()
                    await self.refresh_services()
                    self.online = True
                    self.changed.set()
                    self.state_events.notify()
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

    async def call_service(self, domain, service, data):
        """One Home Assistant action by its domain and name, without an answer (media_player.play_media)."""
        await self.request('call_service', domain=domain, service=service, service_data=data)

    async def call_answer(self, domain, service, data):
        """One Home Assistant action that answers (media_player.browse_media): its response, per entity."""
        result = await self.request('call_service', domain=domain, service=service, service_data=data, return_response=True)
        return (result or {}).get('response') if isinstance(result, dict) else None

    # ----- pictures from Home Assistant (docs/PICTURES.md): one way to read them -----
    # The most bytes one picture may be, by what it is: a camera's snapshot or a player's cover, an entity's own picture
    # (a person's), a thumbnail of a player's library, a photo of the screensaver's folder.
    PICTURE_LIMITS = {'snapshot': 8 * 1024 * 1024, 'entity': 4 * 1024 * 1024, 'thumbnail': 2 * 1024 * 1024,
                      'photo': saver_photos.MAX_PHOTO_BYTES}

    async def picture_bytes(self, url, headers, kind, timeout=None, **options):
        """The bytes at `url`, never more than the limit of its `kind` (PICTURE_LIMITS), never through a redirect."""
        limit = self.PICTURE_LIMITS[kind]
        async with self.session.get(url, headers=headers, timeout=ClientTimeout(total=timeout or picture_sources.FETCH_SECONDS),
                                    allow_redirects=False, **options) as response:
            response.raise_for_status()
            if (response.content_length or 0) > limit:
                raise ValueError('picture too large')
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw += chunk
                if len(raw) > limit:
                    raise ValueError('picture too large')
            return bytes(raw)

    async def picture_address(self, address, allowed, what='picture'):
        """(url, headers) of a picture's address: a path of Home Assistant's own that `allowed(path)` takes, with the
        app's token, or a public address on the internet without it (never a private one, _allow_media_url). Any other
        address raises: never a redirect, never a path out of what is allowed (app 0.4.15, GitHub #77, thanks
        @EmanueleBenedettini)."""
        root = self.base[:-4] if self.base.endswith('/api') else self.base
        if address.startswith('/'):
            parsed = urlsplit(address)
            if parsed.netloc or '..' in parsed.path or address.startswith('//') or not allowed(parsed.path):
                raise ValueError(f'unsafe {what} address')
            return f'{root}{address}', {'Authorization': 'Bearer ' + self.token}
        if address.startswith(('http://', 'https://')):
            if not await self._allow_media_url(address):
                raise ValueError(f'unsafe {what} address')
            return address, {}
        raise ValueError(f'unknown {what} address')

    async def camera_image(self, entity):
        """The picture of a camera or image entity as Home Assistant hands it to its own frontend."""
        path = 'camera_proxy' if entity.startswith('camera.') else 'image_proxy'
        raw = await self.picture_bytes(f'{self.base}/{path}/{entity}', {'Authorization': 'Bearer ' + self.token}, 'snapshot')
        # A Valetudo robot's map camera hands out a placeholder with the map inside: the app draws that map, once per map.
        return await valetudo_map.prepared(raw)

    def media_picture(self, entity):
        """The address of a media player's cover as its state carries it right now (core.media_cover: Home Assistant's
        own proxy first), or '' without one."""
        return media_cover(self.states.get(entity, {}).get('attributes', {}))

    async def map_tile(self, z, x, y):
        """One vector tile of Home Assistant's own map (`map_tiles`, app 0.4.33): a zoom and two whole numbers, never a
        name or an entity, through Home Assistant, which fetches it from OpenStreetMap with its own identification."""
        if any(type(n) is not int for n in (z, x, y)) or not 0 <= z <= map_card.VECTOR_MAX_ZOOM or \
                not 0 <= x < (1 << z) or not 0 <= y < (1 << z):
            raise ValueError('a tile outside the map')
        async with self.session.get(f'{self.base}{map_tiles.PATH}/{z}/{x}/{y}.mvt',
                                    headers={'Authorization': 'Bearer ' + self.token},
                                    timeout=ClientTimeout(total=map_tiles.FETCH_SECONDS), allow_redirects=False) as response:
            response.raise_for_status()
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw += chunk
                if len(raw) > map_tiles.MAX_TILE_BYTES:
                    raise ValueError('tile too large')
            return bytes(raw)

    async def entity_picture(self, picture):
        """An entity's own picture (`entity_picture`: a person's for a marker on a map, app 0.4.36, and a plugin's place
        of an entity), from where Home Assistant's own frontend takes it: one of Home Assistant's own pictures
        (picture_question.HA_PICTURES), or a public address on the internet."""
        url, headers = await self.picture_address(picture, lambda path: path.startswith(picture_question.HA_PICTURES))
        return await self.picture_bytes(url, headers, 'entity')

    async def media_image(self, entity):
        """The cover of a media player (app 0.2.77): Home Assistant's proxy for that very player, which fetches the
        picture itself wherever it lies, or a public address on the internet (core.media_cover takes the proxy first)."""
        picture = self.media_picture(entity)
        if not picture:
            raise ValueError('no picture')
        url, headers = await self.picture_address(picture, lambda path: path == f'/api/media_player_proxy/{entity}')
        return await self.picture_bytes(url, headers, 'snapshot')

    async def media_file(self, address):
        """A photo of the screensaver's folder (saver_photos.py), at the address Home Assistant's own
        `media_source/resolve_media` named for it: a path of Home Assistant (/media/..., an integration's own view such as
        Immich's) with the app's token, or a public address on the internet."""
        url, headers = await self.picture_address(address, lambda path: True, 'photo')
        options = {}
        parsed = urlsplit(address)
        # Under the Supervisor its proxy passes /api/ alone, and a media source serves its files elsewhere
        # (/media/local/..., /immich/...): the photo comes from Home Assistant itself, at the internal address it names,
        # by the signature resolve_media gave the path (`authSig`), with no token of the app's.
        if address.startswith('/') and self.base == 'http://supervisor/core/api' and not parsed.path.startswith('/api/'):
            direct = await self.internal_url()
            if not direct or 'authSig=' not in (parsed.query or ''):
                raise ValueError('no way to Home Assistant for this photo')
            url, headers = f'{direct}{address}', {}
            # A home on https with its own certificate: the request carries no secret (the signature is the photo's own,
            # from Home Assistant), so the certificate is not checked here, as a browser in the house would need telling to.
            if direct.startswith('https://'):
                options['ssl'] = False
        return await self.picture_bytes(url, headers, 'photo', timeout=saver_photos.FETCH_SECONDS, **options)

    async def internal_url(self):
        """Home Assistant's own internal address (websocket network/url, its Network settings), without a trailing slash,
        or '' when it has none; asked once."""
        if getattr(self, '_internal_url', None) is None:
            try:
                urls = await self.request('network/url')
                self._internal_url = str((urls or {}).get('internal') or '').rstrip('/')
            except Exception:  # noqa: BLE001 - an older Home Assistant, or no rights: the proxy only
                self._internal_url = ''
        return self._internal_url

    async def browse_image(self, entity, picture):
        """A thumbnail of a player's library (app 0.4.42): Home Assistant's proxy for that player's library (Sonos, Music
        Assistant), or a public address on the internet (Spotify's)."""
        prefix = f'/api/media_player_proxy/{entity}/browse_media/'
        url, headers = await self.picture_address(picture, lambda path: path.startswith(prefix))
        return await self.picture_bytes(url, headers, 'thumbnail')

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

    async def esphome_entries(self):
        """Home Assistant's ESPHome integrations, by their entry id: the entry behind each screen."""
        entries = await self.request('config_entries/get', domain='esphome')
        return {entry['entry_id']: entry for entry in entries or [] if isinstance(entry, dict) and entry.get('entry_id')}

    async def reload_entry(self, entry_id):
        """Load one integration again, as its Reload in Home Assistant's menu does: an ESPHome screen connects anew."""
        await self.call_service('homeassistant', 'reload_config_entry', {'entry_id': entry_id})

    async def flows(self):
        """The config flows Home Assistant has under way, the devices under "Discovered" among them."""
        return [flow for flow in await self.request('config_entries/flow/progress') or [] if isinstance(flow, dict)]

    async def discovered_esphome(self):
        """The nodes of the ESPHome devices Home Assistant found on the network and has not paired yet (app 0.4.32): a
        screen that was just flashed shows up here once it is on the Wi-Fi, so New screen can say it arrived, or that it
        did not. By node, not by the title Home Assistant gives the device (app 0.4.73, ha_pairing.discovered_node)."""
        return {node for node in map(ha_pairing.discovered_node, await self.flows()) if node}

    async def flow(self, method, path, data=None):
        """One step of a config flow or an options flow, the way Home Assistant's own dialogs take it (app 0.4.73):
        `flow/<id>` answers a step of a discovered device, `options/flow` opens an integration's Configure dialog and
        `options/flow/<id>` answers it. Over REST with the same token; the websocket has no command for these, and
        Home Assistant lets only an administrator take them."""
        async with self.session.request(method.upper(), f'{self.base}/config/config_entries/{path}',
                                        headers={'Authorization': 'Bearer ' + self.token}, json=data,
                                        timeout=ClientTimeout(total=60)) as response:
            if response.status in (401, 403):
                raise Refused(t('addon.errors.allow_actions.not_allowed'))
            response.raise_for_status()
            answer = await response.json(content_type=None)
        return answer if isinstance(answer, dict) else {}

    async def delete_config_entry(self, entry_id):
        """Remove one integration with its device and its entities, the way Home Assistant's own Delete does
        (app 0.2.112). ESPHome answers `supports_remove_device: false`: one node is one entry, so the entry
        goes, not the device. Over REST with the same token; the websocket has no command for it."""
        async with self.session.delete(f'{self.base}/config/config_entries/entry/{entry_id}',
                                       headers={'Authorization': 'Bearer ' + self.token},
                                       timeout=ClientTimeout(total=60)) as response:
            if response.status in (401, 403):
                raise Refused(t('addon.errors.remove.not_allowed'))
            if response.status == 404:
                raise ValueError(t('addon.errors.remove.gone'))
            response.raise_for_status()
            answer = await response.json(content_type=None)
        return bool(isinstance(answer, dict) and answer.get('require_restart'))

    async def save_automation(self, automation_id, config):
        """Save one automation as Home Assistant's own editor does (automations.py): it writes automations.yaml and reloads
        the automations. Over REST with the same token; only an administrator may."""
        async with self.session.post(f'{self.base}/config/automation/config/{automation_id}',
                                     headers={'Authorization': 'Bearer ' + self.token}, json=config,
                                     timeout=ClientTimeout(total=60)) as response:
            if response.status in (401, 403):
                raise Refused(t('addon.errors.automations.not_allowed'))
            if response.status == 400:
                answer = await response.json(content_type=None)
                raise ValueError(t('addon.errors.automations.refused', reason=str((answer or {}).get('message', ''))[:200]))
            response.raise_for_status()

    async def delete_automation(self, automation_id):
        """Remove one automation, as Home Assistant's own editor does."""
        async with self.session.delete(f'{self.base}/config/automation/config/{automation_id}',
                                       headers={'Authorization': 'Bearer ' + self.token},
                                       timeout=ClientTimeout(total=60)) as response:
            if response.status in (401, 403):
                raise Refused(t('addon.errors.automations.not_allowed'))
            # One that is gone already answers 400, "Resource not found" (homeassistant/components/config/view.py).
            if response.status not in (400, 404):
                response.raise_for_status()

    async def remove_state(self, entity_id):
        """A state this app published itself (a screen's layout sensor), gone with the screen it described."""
        async with self.session.delete(f'{self.base}/states/{entity_id}',
                                       headers={'Authorization': 'Bearer ' + self.token}) as response:
            return response.status < 300

    async def forecast(self, entity, kind='daily'):
        # Forecasts left the weather attributes in HA 2024.4; ask the service instead.
        result = await self.request('call_service', domain='weather', service='get_forecasts',
                                    service_data={'type': kind}, target={'entity_id': entity}, return_response=True)
        forecast = ((result or {}).get('response') or {}).get(entity, {}).get('forecast', [])
        return forecast if isinstance(forecast, list) else []

    async def events(self, entities, start, end):
        """Every event of these calendars from `start` up to `end`, as Home Assistant's calendar.get_events answers
        (repeating events already written out), by calendar: {entity: [event]}."""
        result = await self.request('call_service', domain='calendar', service='get_events',
                                    service_data={'start_date_time': start.isoformat(), 'end_date_time': end.isoformat()},
                                    target={'entity_id': list(entities)}, return_response=True)
        response = (result or {}).get('response') or {}
        return {entity: (response.get(entity) or {}).get('events') or [] for entity in entities}

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
        # sent: per inbox what the screen holds ({'layout', 'header', 'states', 'rev'}); status: how the
        # delivery went, in English with its key (the editor shows it in its own language, app 0.2.90);
        # last: the last full send; pinged: the last keepalive ping.
        self.sent, self.status, self.last, self.pinged = {}, {}, {}, {}
        self.page_senders = {}
        self.page_capabilities = CapabilityCache(self.path.parent / 'page-capabilities.json')
        self._compiled_records, self._compiled_layouts = None, {}
        self._compiled_store_stamp = object()
        self._migration_metadata = None
        # (entity, hours) -> (monotonic, 24 samples); filled by history_loop, read by sync_one.
        self.histories = {}
        # Resolved values, not a second editable document. Dependencies let one
        # HA change refresh every affected page and leave unrelated bars alone.
        self.page_values = {}
        self.history_wake = asyncio.Event()
        self.forecasts = {}
        # The template tiles' results from Home Assistant (docs/TEXT_TILE.md).
        self.templates = template_service.TemplateService(ha)
        self.listeners = set()  # asyncio.Event per open /api/events stream
        self.firmware = Firmware(os.environ.get("ESPHOME_CONFIG", "/homeassistant/esphome"), self.path.parent)
        # The app's one build line (docs/BUILDS.md): updates, plugin builds, New screen and Firmware & USB wait in it.
        self.build_queue = self.firmware.builds = BuildQueue(self)
        # The build server builds go to first when it is on (build_server.py, docs/BUILDS.md "On a build server").
        self.build_server = self.firmware.server = build_server.BuildServer(self.path.parent, self.notify)
        # Plugins (docs/PLUGINS.md): which exist, which each screen runs, their files and their tiles' data.
        self.plugins = plugins.Plugins(self, self.path.parent, self.firmware.root)
        self.updates = Updater(self, self.path.parent / 'updates.json')
        # Does this screen work as you expect? One shared answer per board, with its own key (app 0.3.10).
        self.feedback = feedback.Feedback(self.path.parent / 'feedback.json')
        # My screen doesn't work right (app 0.4.91, reports.py): one troubleshooting report per screen, and the crashes
        # the app saw each screen reboot from.
        self.reports = reports.Reports(self, self.path.parent)
        # The names the editor shows instead of Home Assistant's (app 0.4.2).
        self.labels = screen_labels.ScreenLabels(self.path.parent / 'screen-labels.json')
        # Which way each screen is to hang, as the editor chose beside the mockup (app 0.4.85, firmware 0.53.0+).
        self.hangs = screen_hang.ScreenHang(self.path.parent / 'screen-hang.json')
        # Screens this app made, added to Home Assistant with their actions allowed once it finds them (app 0.4.73).
        self.pairing = ha_pairing.Pairing()
        self._pairing_trouble = None
        # What each screen shows in standby instead of its dimmed tiles (app 0.4.48, screen_saver.py), and the last message
        # each screen holds, by its session: a screen that starts a new session gets it again.
        self.savers = screen_saver.ScreenSavers(self.path.parent / 'screensavers.json')
        self.saver_sent = {}
        self.saver_shown = {}  # the player each screen's screensaver shows, by inbox
        # The photos step (app 0.4.89, saver_photos.py): a folder of Home Assistant's media, walked per screen.
        self.photos = saver_photos.Photos(lambda kind, **data: self.ha.request(kind, **data),
                                          lambda address: self.ha.media_file(address))
        self.photos.changed = lambda: self.ha.changed.set()
        # Settings -> Language & region (app 0.2.90): the language, clock and numbers of every screen.
        self.region = Region(self.path.parent / 'language.json', ha_language=lambda: getattr(self.ha, 'ha_language', None))
        self.ha.language_of = self.region.language
        self.firmware.language = self.region.language
        self.ha.on_config = self.language_changed
        self.ha.on_time_zone = self.time_zone_changed
        self._clock_resync = None
        self.set_screens()
        self.skill_dir = claude_skill.skill_dir()
        # Video in Home Assistant (Settings): the tessera_video integration, installed only on request (screen_video.py).
        self.videos = screen_video.Videos(screen_video.target())
        self._registry_source, self._registry_index = None, {}
        self._items_source, self._items = None, []
        self._screens_key, self._screens = None, []
        self._verified_screens_key, self._verified_screens = None, {}
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
        # Pictures (docs/PICTURES.md): the cameras' snapshots and the players' covers, once for every screen; the links on
        # the camera port; the rules and the getting of every source; and the service that answers every question. And
        # the cameras of recent alerts (entity -> monotonic time) that a screen may open full screen without a tile.
        self.snapshots = picture_sources.Snapshots(lambda entity: self.camera_snapshot(entity),
                                                   fetch_cover=lambda entity: self.ha.media_image(self.followed(entity)),
                                                   picture=lambda entity: self.ha.media_picture(self.followed(entity)))
        self.alert_cameras = {}
        # A camera live on a P4 (live_stream.py): its links and the sources behind them, on the camera port.
        self.live = live_stream.LiveFeed(lambda entity: self.ha.camera_image(entity), lambda: self.ha.websocket(),
                                       lambda entity: self.ha.camera_streams(entity), live_tiles=self.live_tiles_of,
                                       screen_name=self.name_of)
        self.links = picture_links.Links()
        self.sources = picture_sources.Sources(picture_sources.Providers.of(self), self.snapshots)
        self.pictures = picture_service.Service(self, self.sources, self.links, self.live)
        # The streets of the map cards (app 0.4.33): one tile source for every screen, through Home Assistant. And the
        # last maps drawn, by their mark, frame and look: a screen in dark mode and one in light mode each have their
        # own, and a page that loads again for its camera does not draw its map again.
        self.map_source = map_tiles.TileSource(lambda z, x, y: self.ha.map_tile(z, x, y))
        self.map_renders = OrderedDict()
        # A media player's library (app 0.4.42, firmware 0.24.0, media_library.py): the widest features each player
        # reported (GitHub #88), the numbers each screen's items go by, the folders read a moment ago, the players
        # that browse, the colours of each cover, the item this app started last on each player, and the thumbnails.
        self.players = media_library.FeatureMemory(self.path.parent / 'media-features.json',
                                                   platform_of=getattr(self.ha, 'platform_of', None))
        self.ha.widen = self.players.widened
        self.shelves, self.folders, self.browsable, self.browse_probes = {}, OrderedDict(), {}, {}
        self.grounds, self.ground_reads, self.started = OrderedDict(), {}, {}
        self.thumbnails = OrderedDict()
        # The covers a player at rest shows on its cover tile (rest_mosaic.py): its folder's covers (entity ->
        # (monotonic, [(thumbnail, title)])), the reads on their way, the players that showed them last and the turn.
        self.rest_pools, self.rest_reads, self.resting, self.rest_step = {}, {}, set(), None
        # Where a player plays (speakers.py): the speaker this app started each player's music on, which its card
        # follows, and the top of each player's library as far as it names accounts (entity -> (monotonic, ids)).
        self.outputs, self.accounts, self.account_probes = {}, {}, {}
        # The editor's firmware previews (preview_images): the tiles of each layout one compiled, by its revision (the
        # `rev` its questions carry), the last few kept, and the last one for a question without a known revision.
        self.preview_tiles, self.preview_layouts = [], OrderedDict()
        self.map_pictures = OrderedDict()
        self.map_hits = {}
        # The action behind an alert's button (app 0.2.91): node -> (key, action, data) of the alert on that screen.
        self.alert_actions = {}
        # The rings of doorbells and the last one nobody answered (doorbell.py, docs/DOORBELL.md).
        self.doorbells = doorbell.Doorbells()
        self.store = LayoutStore(self.path, self.record_grid)
        # An app from before Language & region (app 0.2.90): its screens keep the 24 hours they show, until Home Assistant
        # says every screen's own clock setting was 12 hours (resolve_clock_pin). A new install starts on Automatic, and
        # is stored right away so a restart never takes it for an old one.
        if not self.region.stored:
            if self.layouts:
                self.region.clock, self.region.pinned = '24', True
            self.region.save()

    @property
    def layouts(self):
        """Read-only compiled views for existing entity/card helpers, never saved."""
        if not hasattr(self, 'store'):
            return {}
        stamp, records = self.store.snapshot_since(self._compiled_store_stamp)
        if records is None:
            return self._compiled_layouts
        key = {inbox: (record['revision'], record.get('settings')) for inbox, record in records.items()
               if record['format'] == PAGE_FORMAT}
        if key != self._compiled_records:
            self._compiled_layouts = CompiledLayouts(records)
            self._compiled_records = key
        self._compiled_store_stamp = stamp
        return self._compiled_layouts

    def verified_grid(self, inbox):
        """Resolve the reported grid, then the installed profile or known board.

        Before fc953e8 (firmware 0.2.77), screens had no shape sensor and
        both shipped boards used 2x3. The first different grid, Waveshare
        4.3 in be66856, shipped after that sensor. An otherwise unidentified
        legacy screen therefore uses 2x3 once it appears in HA's registry.
        An absent screen still waits for discovery rather than being guessed.
        """
        screen = self._discovered(inbox)
        if screen is None:
            return None
        reported = self.reported_grid(inbox)
        if reported is not None:
            return reported
        profile = self.built_as(screen)
        if profile.get('package') and board_of({**screen, 'package': profile['package']}) in SHAPES:
            return self.grid_of(screen)
        if board_of(screen) in SHAPES:
            return self.grid_of(screen)
        return Grid(2, 3).with_ceilings(*self.ceilings(inbox))

    def screen_grids(self, inbox):
        """The grids a screen takes and keeps, each way its glass hangs (firmware 0.53.0+): what its hello said, or the last
        it said while it is offline (page_capabilities); None for a screen whose grid is the one it was built with."""
        sender = self.page_senders.get(inbox) if inbox else None
        return (getattr(sender, 'grids', None) or getattr(sender, 'last_grids', None)) if sender else None

    def turnable(self, inbox):
        """Whether ESP Screens may stand this screen up or lay it down (firmware 0.53.0+): it says the grids it takes,
        and its glass is not square (a square screen turns with its own Rotation setting and keeps its grid)."""
        if not self.screen_grids(inbox):
            return False
        # The glass of its board, which is known offline too (and during the start a turn makes); the shape it reported
        # for a board this app does not know.
        screen = self._discovered(inbox) or {}
        glass = SHAPES.get(board_of(screen)) or screen.get('shape') or {}
        return isinstance(glass.get('width'), int) and glass.get('width') != glass.get('height')

    def wanted_way(self, inbox):
        """The way a screen that takes grids is to hang, 'landscape' or 'portrait': the one the editor chose for it
        (screen_hang), else the way it hangs now. None for a screen that takes no other grid."""
        grids = self.screen_grids(inbox)
        if not grids:
            return None
        screen = self._discovered(inbox) or {}
        device = screen.get('device_id')
        # The profile is read only for a screen someone turned: it says whether the choice still counts (screen_hang).
        chosen = (self.hangs.get(device, self.built_as(screen).get('rotation'))
                  if self.hangs.has(device) and self.turnable(inbox) else None)
        return chosen or ('portrait' if grids['upright'] else 'landscape')

    def takes_grid(self, inbox, columns, rows, way=None):
        """Columns x rows as a Grid with this screen's ceilings when `way` of its glass (the way it is to hang when
        none is named, wanted_way) takes them, else None."""
        grids = self.screen_grids(inbox)
        if not grids or type(columns) is not int or type(rows) is not int:
            return None
        way = way or self.wanted_way(inbox)
        if not page_delivery.grid_takes(grids, way, columns, rows):
            return None
        return Grid(columns, rows, *self.ceilings(inbox))

    def chosen_grid(self, inbox, data):
        """The grid a save chooses for a screen that takes another (firmware 0.53.0+): its adaptation's target when the
        way the screen's glass hangs takes it, else None (the save is counted on the grid the screen is given)."""
        adaptation = data.get('adaptation') if isinstance(data, dict) else None
        target = adaptation.get('to') if isinstance(adaptation, dict) else None
        if not isinstance(target, dict):
            return None
        # Standing up or lying down as well (app 0.4.85): the grid of that way, on glass that turns.
        upright = adaptation.get('upright')
        if upright is not None and (type(upright) is not bool or not self.turnable(inbox)):
            return None
        way = None if upright is None else 'portrait' if upright else 'landscape'
        return self.takes_grid(inbox, target.get('columns'), target.get('rows'), way)

    def given_grid(self, inbox, record):
        """The grid a screen that takes another runs on once `record` (its saved layout) reached it: that layout's, when
        the screen takes it, else the one it keeps itself. None for a screen that takes no other grid. The record comes
        from the caller: the store asks this while it holds its lock (record_grid), so this never reads the store."""
        grids = self.screen_grids(inbox)
        if not grids:
            return None
        source = record.get('sourceGrid') if isinstance(record, dict) and record.get('format') == PAGE_FORMAT else None
        given = self.takes_grid(inbox, source['columns'], source['rows']) if isinstance(source, dict) else None
        if given is not None:
            return given
        way = grids[self.wanted_way(inbox)]
        return Grid(way['columns'], way['rows'], *self.ceilings(inbox))

    def record_grid(self, inbox, record=None):
        """The grid a saved layout of this screen is counted on: the one the screen is given (given_grid, firmware
        0.53.0+), else the one it reports, its profile builds or its board has (verified_grid). The store's grid_for."""
        return self.given_grid(inbox, record) or self.verified_grid(inbox)

    def layout_grid(self, inbox, screen):
        """The grid this screen's saved layout is counted on, for a tile event, its answer and the layout sensor: the one
        the screen is given (firmware 0.53.0+, offline too and before the layout reached it), else its own."""
        return self.record_grid(inbox, self.store.get(inbox)) or self.grid_of(screen)

    def ceilings(self, inbox):
        """The most pages, tiles and top-bar items a page this screen takes: what its hello said (firmware 0.34.0+,
        page_delivery.Sender), or the last it said while it is offline (page_capabilities), else the eight pages, 64 tiles
        and six items of any screen."""
        sender = self.page_senders.get(inbox) if inbox else None
        said = lambda name: getattr(sender, name, None) or getattr(sender, 'last_' + name, None)
        return (said('max_pages') or FIRMWARE_MAX_PAGES, said('max_tiles') or FIRMWARE_MAX_TILES,
                said('max_bar_items') or FIRMWARE_MAX_BAR_ITEMS)

    def doorbell_kind(self, screen):
        """What a ring does on this screen (docs/DOORBELL.md): `view`, the doorbell's camera live (its hello says `doorbell`,
        else a P4 that streams with the board's module), `picture`, the camera's alert with its picture, or `plain`, the alert
        alone (a board that draws no pictures)."""
        sender = self.page_senders.get(self.aliases.get(screen.get('id'), screen.get('id')))
        if sender is not None and getattr(sender, 'protocol', None) is not None:
            view = doorbell.FEATURE in (getattr(sender, 'features', None) or ())
        else:
            view = has_module(screen, 'doorbell') and self.live_camera(screen)
        return 'view' if view else 'picture' if board_of(screen) in picture_question.BOXES else 'plain'

    def name_of(self, inbox):
        """The name this app gives the screen of `inbox` (its own label, else Home Assistant's), or the inbox."""
        screen = self.screen(inbox)
        return (self.labels.get(screen.get('device_id')) or screen['name']) if screen else inbox

    def live_tiles_of(self, inbox):
        """How many live camera tiles the screen of `inbox` streams at once, from its hello (page_delivery.caps_of,
        firmware hw.h), or None while it is not connected or its firmware did not say."""
        sender = self.page_senders.get(self.aliases.get(inbox, inbox))
        if sender is None or getattr(sender, 'protocol', None) is None:
            return None
        return (getattr(sender, 'caps', None) or {}).get('live_tiles')

    def picture_turn_of(self, inbox):
        """How the screen of `inbox` takes its live pictures: turned as its glass is (90, 180 or 270, its hello's
        picture_turn), or 0 upright."""
        sender = self.page_senders.get(self.aliases.get(inbox, inbox))
        return (getattr(sender, 'caps', None) or {}).get('picture_turn') or 0 if sender is not None else 0

    def own_camera_of(self, inbox, screen, entity):
        """Whether `entity` is the screen of `inbox`'s own camera as Home Assistant shows it (Video in Home Assistant: the
        tessera_video camera on the screen's own device) and the screen draws a tile of it from the camera itself (its
        hello's own_camera, plugin API 0.22)."""
        sender = self.page_senders.get(self.aliases.get(inbox, inbox))
        if sender is None or not (getattr(sender, 'caps', None) or {}).get('own_camera'):
            return False
        item = self.registry_index().get(entity) or {}
        device = (screen or {}).get('device_id')
        if not device or item.get('platform') != screen_video.DOMAIN:
            return False
        if item.get('device_id') == device:
            return True
        # The camera on a device of its own beside the screen's, with the screen's MAC: Home Assistant kept the two
        # apart (seen on a reTerminal D1001, 2026-10-28), and it is the same screen.
        devices = {d.get('id'): d for d in getattr(self.ha, 'devices', None) or [] if isinstance(d, dict)}

        def macs(found):
            return {str(c[1]).lower() for c in (found or {}).get('connections') or []
                    if isinstance(c, (list, tuple)) and len(c) == 2 and c[0] == 'mac'}
        return bool(macs(devices.get(device)) & macs(devices.get(item.get('device_id'))))

    def live_camera(self, screen):
        """Whether this screen streams a camera live (live_stream.py): its hello while it is connected (`live`), else its
        board (a P4 that draws pictures). The editor offers Live for its camera tiles, as their default."""
        sender = self.page_senders.get(self.aliases.get(screen.get('id'), screen.get('id')))
        if sender is not None and getattr(sender, 'protocol', None) is not None:
            return live_stream.SCREEN_FEATURE in (getattr(sender, 'features', None) or ())
        shape = core.shape_of(screen) or {}
        return shape.get('chip') == 'ESP32-P4' and bool(shape.get('camera'))

    def caps_of_screen(self, screen):
        """The capability record of the screen's last hello (page_delivery.caps_of), or None until a hello in this run
        brought one (an older firmware's falls back on its features there)."""
        sender = self.page_senders.get(self.aliases.get(screen.get('id'), screen.get('id')))
        if sender is None or getattr(sender, 'protocol', None) is None:
            return None
        return dict(getattr(sender, 'caps', None) or {}) or None

    def has_battery(self, screen):
        """Whether this screen has a battery the top bar can show (core.has_battery): its Screen features or its hello
        while it is connected, else its board."""
        sender = self.page_senders.get(self.aliases.get(screen.get('id'), screen.get('id')))
        return has_battery(screen, getattr(sender, 'features', None) or ())

    def memory(self, inbox):
        """The memory this screen has for its tiles and what each tile costs (firmware 0.34.0+, tile_memory.h): the
        figures of its last hello or ping, `live` while it is connected; None when it never said."""
        sender = self.page_senders.get(inbox)
        live = getattr(sender, 'memory', None)
        memory = live or getattr(sender, 'last_memory', None)
        # Whether its tiles of the top bar count too (core.layout_cost): a screen that takes cards from its top bar.
        return {**memory, 'live': live is not None, 'bar_cards': BAR_CARDS_FEATURE in (getattr(sender, 'features', None) or ())} if memory else None

    def _discovered(self, inbox):
        """The screen as discovery sees it now, or None while it is not in Home Assistant's registry."""
        # Discovery is pure here: following renames can write storage, so it must
        # not run recursively from the store's migration callback.
        ha = self.ha
        items = self.screen_registry()
        key = (id(ha.registry), id(ha.devices), id(ha.areas), tuple(ha.states.get(item['entity_id'], {}).get('state') for item in items))
        if key != self._verified_screens_key:
            self._verified_screens_key = key
            self._verified_screens = {item['id']: item for item in discover_screens(items, ha.states, ha.devices, ha.areas)}
        return self._verified_screens.get(inbox)

    def reported_grid(self, inbox):
        """The grid the screen reports itself ("Screen layout", firmware 0.2.77+), or None when it says nothing.
        verified_grid takes this one first; only this one may move a saved layout to a new grid on its own."""
        shape = (self._discovered(inbox) or {}).get('shape')
        if isinstance(shape, dict) and all(type(shape.get(k)) is int and shape[k] > 0 for k in ('columns', 'rows')):
            return Grid(shape['columns'], shape['rows'], *self.ceilings(inbox))
        return None

    def refresh_page_records(self):
        """Online metadata completes pending migrations without a browser Save."""
        before = self.store.records()
        if not any(record['format'] != PAGE_FORMAT for record in before.values()): return before
        metadata = (self._screens_key, self.firmware.profile_names())
        if metadata == self._migration_metadata: return before
        self._migration_metadata = metadata
        after = self.store.retry_migrations()
        if before != after:
            self.ha.changed.set()
            self.notify()
        return after

    def page_sender(self, inbox, screen):
        if inbox not in self.page_senders:
            async def send(message):
                current = self.screen(inbox) or screen
                return await self.ha.send(inbox, message, message_action(current.get('node')), respond=True)
            self.page_senders[inbox] = page_delivery.Sender(send, screen.get('name') or inbox)
            self.page_capabilities.restore(inbox, screen, self.page_senders[inbox])
        sender = self.page_senders[inbox]
        marker = page_identity(screen)
        previous = getattr(sender, 'device_marker', None)
        if previous is not None and any(previous.get(key) != value for key, value in marker.items()):
            sender.disconnected()
            sender.last_protocol = None
            sender.last_tile_sizes = {'single', 'wide', 'full'}
            self.page_capabilities.restore(inbox, screen, sender)
        sender.device_marker = {**(previous or {}), **marker}
        return sender

    async def probe_pages(self, inbox, screen):
        """Learn capabilities before the first Save, once per device connection.

        A hello grants a delivery session, so do not send another while that
        session is in use. Firmware/node changes invalidate cached capability.
        """
        sender = self.page_sender(inbox, screen)
        if sender.protocol is None and self.answers(inbox, screen):
            # Only a screen without tiles is probed: its hello says so, and the screen asks for its first tiles.
            await sender.probe(empty=inbox not in self.layouts)
            self.page_capabilities.remember(inbox, screen, sender)
        return sender

    async def send_auxiliary(self, inbox, message, action, request):
        sender = self.page_senders.get(inbox)
        if sender and sender.protocol == 2:
            try: view = int(request.get('view', 0))
            except (ValueError, TypeError): return False
            return await sender.auxiliary({**message, 'view': view}, session=request.get('session'), revision=request.get('rev'))
        if request.get('session') or request.get('rev'):
            # A delayed v2 request must never fall through to an unscoped legacy
            # reply after disconnect, restart or a device replacement.
            return False
        await self.ha.send(inbox, message, action)
        return True

    def page_scope(self, inbox):
        """Bind unsolicited images to the configuration that requested them."""
        sender = self.page_senders.get(inbox)
        return {'session': sender.session, 'rev': sender.confirmed} if sender else {}

    def page_region(self, inbox=None):
        """What a layout's begin says besides its pages: the region, and for a screen that may be turned the way it is to
        hang (firmware 0.53.0+, "upright"), so a turn is another configuration and goes out even with the same grid."""
        region = {'keepalive': KEEPALIVE_SECONDS, 'clock_24h': self.region.clock_24h(),
                  'numbers': self.region.number_style(), 'group_min': self.region.group_min(),
                  'percent_space': self.region.percent_space()}
        if inbox and self.turnable(inbox):
            region['upright'] = self.wanted_way(inbox) == 'portrait'
        return region

    def preflight_update(self, inbox):
        return page_service.preflight_update(self, inbox=inbox)

    def preflight_pages(self, inbox, record):
        return page_service.preflight_pages(self, inbox=inbox, record=record)

    def preflight_profile(self, data):
        return page_service.preflight_profile(self, data=data)

    def save_pages(self, inbox, data):
        return page_service.save_pages(self, inbox=inbox, data=data)

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

    async def link_base(self, screen):
        """Where `screen` fetches this app's pictures: Home Assistant's address on the screen's own network (GitHub #276)."""
        return await lan_address.base_url(self.ha.request, near=(screen or {}).get('ip'))

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
        # Pending migrations belong to the same device too. A renamed inbox may
        # be the first opportunity to obtain its verified grid after an update.
        stored = (set(self.store.records()) | set(self.updates.hosts) | set(self.updates.results)) - set(current) - set(self.aliases)
        for new, device in current.items():
            olds = {old for old, seen in self._inbox_devices.items() if seen == device and old not in current}
            candidates = [old for old in stored if inbox_prefix(old) is not None]
            if candidates:
                prefixes = self.device_prefixes(device)
                olds |= {old for old in candidates if inbox_prefix(old) in prefixes}
            for old in sorted(olds - set(self.aliases)):
                self.rename_inbox(old, new)
        self._inbox_devices.update(current)

    def rename_inbox(self, old, new):
        """Move everything kept under an old inbox id to the id the same screen reports under now."""
        moved = []
        records = self.store.records()
        if old in records and new not in records:
            self.store.rename(old, new)
            moved.append('layout')
        elif old in records:
            LOG.warning('Screen %s already has a layout; the one stored under %s stays untouched', new, old)
        self.page_senders.pop(old, None)
        self.page_capabilities.forget(old)
        self.page_values.pop(old, None)
        if self.updates.renamed(old, new):
            moved.append('update history')
        for store in (self.sent, self.status, self.last, self.pinged):
            store.pop(old, None)
        self.aliases = {**{key: (new if value == old else value) for key, value in self.aliases.items()}, old: new}
        self._inbox_devices.pop(old, None)
        LOG.info('Screen %s now reports as %s%s', old, new, f"; moved its {' and '.join(moved)}" if moved else '')
        if moved:
            self.store.retry_migrations()
            self.history_wake.set()
            self.ha.changed.set()
            self.notify()

    def forget_inbox(self, inbox):
        """Everything this app kept for a screen that is gone for good: its layout with its settings, its update
        history, and what the sync loop remembered about it. The mirror of `rename_inbox` (app 0.2.112)."""
        self.store.forget(inbox)
        self.page_senders.pop(inbox, None)
        self.page_capabilities.forget(inbox)
        self.page_values.pop(inbox, None)
        self.updates.forget(inbox)
        for store in (self.sent, self.status, self.last, self.pinged, self.published, self.retry_at, self.retries):
            store.pop(inbox, None)
        self.aliases = {key: value for key, value in self.aliases.items() if inbox not in (key, value)}
        self._inbox_devices.pop(inbox, None)
        self._screens_key = None

    async def entry_of(self, screen, missing='addon.errors.remove.no_entry'):
        """The ESPHome integration behind a screen: the one entry of its Home Assistant device that ESPHome owns."""
        device = next((d for d in getattr(self.ha, 'devices', []) if d.get('id') == screen.get('device_id')), None)
        entries = await self.ha.esphome_entries()
        mine = [entry for entry in (device or {}).get('config_entries') or [] if entry in entries]
        if len(mine) != 1:
            raise ValueError(t(missing))
        return mine[0]

    async def allow_actions(self, inbox):
        """Let a screen perform Home Assistant actions (app 0.4.73): the switch in its ESPHome integration's Configure
        dialog, which Home Assistant leaves off for a new device. The editor's notice offers it when Home Assistant
        ignored a tap of this screen."""
        inbox = self.aliases.get(inbox, inbox)
        screen = self.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        entry = await self.entry_of(screen, 'addon.errors.allow_actions.no_entry')
        try:
            allowed = await ha_pairing.allow_actions(self.ha, entry)
        except Refused as error:
            raise ValueError(error.detail or t('addon.errors.allow_actions.failed')) from error
        except ClientError as error:
            raise ValueError(t('addon.errors.allow_actions.failed')) from error
        if not allowed:
            raise ValueError(t('addon.errors.allow_actions.failed'))
        LOG.info('%s may perform Home Assistant actions', screen['name'])
        return {'allowed': True, 'name': self.labels.get(screen.get('device_id')) or screen['name']}

    async def pair_screens(self):
        """One look of pairing_loop: the screens this app made (their profiles with the key New screen wrote), against
        what Home Assistant has and has found."""
        ours = {meta['node']: {'api_key': meta['api_key'], 'friendly': meta.get('friendly') or meta['node']}
                for meta in self.firmware.profile_names().values()
                if meta.get('screen') and meta.get('node') and ha_pairing.usable_key(meta.get('api_key'))}
        await self.pairing.run(self.ha, ours, self.screens())

    def video_status(self):
        """Settings, Video in Home Assistant: the integration's copy in Home Assistant's folder, whether Home Assistant
        runs it, and the screens with the video."""
        wanted, _ = screen_video.video_screens(self.plugins, self.screens()) if core.plugins_enabled() else ({}, set())
        return {**screen_video.status(self.videos.directory), 'loaded': self.videos.loaded,
                'screens': sorted(wanted.values()), 'entries': self.videos.entries}

    async def video_loop(self):
        """An entry of tessera_video for each screen with the video, once Home Assistant runs the integration."""
        while True:
            await asyncio.sleep(screen_video.INTERVAL)
            if not self.ha.online or not self.ha.registry or not core.plugins_enabled():
                continue
            try:
                await self.videos.sync(self.ha, *screen_video.video_screens(self.plugins, self.screens()))
            except (ClientError, ConnectionError, TimeoutError, OSError, ValueError, Refused) as error:
                LOG.debug('Video in Home Assistant waits (%s)', type(error).__name__)
            except Exception:   # a slip in one round never ends the app
                LOG.exception('Video in Home Assistant failed this round')

    async def pairing_loop(self):
        """Adds the screens this app made to Home Assistant as soon as it finds them on the network, and lets them
        perform actions (ha_pairing.py, app 0.4.73)."""
        told = getattr(self.ha, 'issues_changed', None) or asyncio.Event()
        while True:
            # A look every few seconds, and at once when Home Assistant reports that it ignored a screen's tap.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(told.wait(), ha_pairing.INTERVAL)
            if told.is_set():
                told.clear()
                self.pairing.issues_due = True
            if not self.ha.online or not self.ha.registry:
                continue
            try:
                await self.pair_screens()
                self._pairing_trouble = None
            except (ClientError, ConnectionError, TimeoutError, OSError, ValueError) as error:
                # Said once, not every five seconds while Home Assistant stays away.
                if self._pairing_trouble != type(error).__name__:
                    LOG.info('Adding new screens to Home Assistant waits (%s)', type(error).__name__)
                self._pairing_trouble = type(error).__name__
            except Exception:   # a slip in one round never ends the app: every loop under main()'s gather keeps going
                LOG.exception('Adding new screens to Home Assistant failed this round')

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
        profile, _ = self.updates.resolve(screen)
        # A build of this screen that runs keeps it until it ends; what only waits goes with the screen.
        if any(build.state == 'running' for build in self.build_queue.on_the_way(screen=inbox)
               + (self.build_queue.on_the_way(file=profile) if profile else [])):
            raise ValueError(t('addon.errors.updates.busy'))
        entry = await self.entry_of(screen)
        await self.ha.delete_config_entry(entry)
        LOG.info('Removed %s from Home Assistant', screen['name'])
        # From here Home Assistant no longer has the screen, so nothing below may stop the rest: what could not be
        # removed is named in the answer instead, and the page says so.
        for build in self.build_queue.line[:]:
            if build.screen == inbox or (profile and build.file == profile):
                self.build_queue.drop(build)
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
        self.plugins.forget_screen(inbox)
        self.labels.forget(screen.get('device_id'))
        self.hangs.forget(screen.get('device_id'))
        self.savers.forget(screen.get('device_id'))
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

    def feedback_board(self, screen, profiles=None):
        """The website's id for this screen's model (the keys of boards.yaml are the website's own), or None for a board
        this app doesn't ship: never a guess from a name or a resolution."""
        board = board_of({**screen, 'package': self.package_of(screen, profiles)})
        return board if board in BOARD_KEYS else None

    def feedback_versions(self, screen):
        """The versions an answer shares: the screen's firmware and this app, as the website takes them."""
        changelog = getattr(self.updates, 'changelog', None) or []
        return {'firmware_version': feedback.clean_version(version_text(self.firmware_version(screen['id'], screen))),
                'addon_version': feedback.clean_version(changelog[0].get('app') if changelog else None)}

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
        # A screen the editor stood up or laid down since (firmware 0.53.0+) hangs the way it was turned to.
        inbox = screen.get('id') if isinstance(screen, dict) else None
        if inbox and self.turnable(inbox):
            return self.wanted_way(inbox)
        return orientation_at(SHAPES.get(board_of(known), {}), self.built_as(screen, profiles).get('rotation'))

    def grid_of(self, screen):
        """The grid of a screen's pages (core.grid_of), with the board its profile builds from and the way it was built
        to hang filled in, so a save, an event and the message to the screen count the same cells whether the screen is
        online or not."""
        if isinstance(screen, dict) and not (screen.get('package') and screen.get('orientation') and 'built_grid' in screen):
            # The profiles once, not once per question: reading them stats every file in the ESPHome folder.
            profiles = self.firmware.profile_names()
            screen = {**screen, 'package': screen.get('package') or self.package_of(screen, profiles),
                      'orientation': screen.get('orientation') or self.orientation_of(screen, profiles),
                      'built_grid': screen.get('built_grid', self.built_as(screen, profiles).get('built_grid'))}
        return grid_of(screen).with_ceilings(*self.ceilings(screen.get('id') if isinstance(screen, dict) else None))

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
        previous = self.store.get(inbox)
        grid = self.record_grid(inbox, previous) or (screen_grid_of_record(previous) if previous and previous['format'] == PAGE_FORMAT else None)
        layout = validate_layout({**base, 'settings': settings}, grid=grid)
        if not previous:
            if grid is None: raise LayoutError(t('addon.errors.pages.source_grid'))
            record = migrate_legacy(base, grid)
            self.store.save(inbox, record['layout'], None, settings=settings, grid=grid)
        else:
            self.store.save_settings(inbox, settings)
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
            except Exception:   # one screen's request never ends the app
                LOG.exception('No options for %s', request.get('entity') if isinstance(request, dict) else '?')

    async def calendar_loop(self):
        """Answer a tap on a compact calendar event (calendar_feed.detail): its whole title, place and notes."""
        while True:
            request = await self.ha.calendar_requests.get()
            try:
                await self.answer_calendar(request)
            except Exception as error:   # one screen's request never ends the app
                LOG.info('No details of a calendar event (%s)', type(error).__name__)

    async def answer_calendar(self, request):
        """One screen's tap: a calendar card of its own layout (by its place `i` and its entity), the event by its
        calendar's place on the card and its minutes from the day the screen calls today."""
        if not isinstance(request, dict):
            return
        inbox = self.aliases.get(request.get('inbox'), request.get('inbox'))
        layout, screen = self.layouts.get(inbox), self.screen(inbox) if isinstance(inbox, str) else None
        if not layout or not screen or not screen.get('online'):
            return
        try:
            index, cal, start, end = (int(request.get(key)) for key in ('i', 'c', 's', 'e'))
            day = date.fromisoformat(str(request.get('day')))
        except (TypeError, ValueError):
            return
        tiles = layout['tiles']
        if not 0 <= index < len(tiles) or tiles[index]['entity'] != request.get('entity') or not tiles[index]['entity'].startswith('calendar.'):
            return
        tile = tiles[index]
        tz = getattr(self.ha, 'time_zone', None) or timezone.utc
        fetched = await self.calendar_events(tile)
        found = calendar_feed.detail(tile, fetched, tz, day, cal, start, end)
        action = self.transport(inbox, screen)
        if not action:
            return
        message = {'v': 1, 'op': 'calendar_event', 'c': cal, 's': start, 'e': end, **(found or {'x': 1})}
        await self.send_auxiliary(inbox, message, action, request)

    async def plugin_loop(self):
        """Answer the plugins on the screens (docs/PLUGINS.md): a Home Assistant command their manifest names."""
        while True:
            request = await self.ha.plugin_requests.get()
            try:
                await self.plugins.answer(request)
            except Exception as error:   # one plugin's question never stops the app
                LOG.info('A plugin question went unanswered (%s)', type(error).__name__)

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
        await self.send_auxiliary(inbox, light_effects.message(entity, page, all_pages), action, request)

    # ----- A media player's library (app 0.4.42, firmware 0.24.0+, media_library.py) -----
    def player_ground(self, entity, attrs):
        """The two colours of a player's cover ('RRGGBB,RRGGBB'), or None until they are read or when it has none. Read
        once per picture, from the same cover the screens load (picture_sources.Snapshots.cover); the screen gets them with the
        player's next state, so the card is whole before any picture comes."""
        mark = (media_extras(attrs) or {}).get('pic')
        if not mark:
            return None
        if mark in self.grounds:
            self.grounds.move_to_end(mark)
            return self.grounds[mark]
        if mark not in self.ground_reads:
            self.ground_reads[mark] = asyncio.ensure_future(self.read_ground(entity, mark))
        return None

    async def read_ground(self, entity, mark):
        colours = None
        try:
            raw = await self.snapshots.cover_raw(entity, picture_sources.FETCH_SECONDS)
            if raw:
                colours = await asyncio.get_running_loop().run_in_executor(None, media_library.ground_colours, raw)
        except Exception as error:
            LOG.info('No colours from the cover of %s (%s)', entity, type(error).__name__)
        finally:
            self.ground_reads.pop(mark, None)
        # '-': read, and nothing to speak of; the screen asks for the cover then without waiting any longer.
        self.grounds[mark] = colours or '-'
        while len(self.grounds) > 64:
            self.grounds.popitem(last=False)
        self.ha.dirty.add(entity)
        self.ha.changed.set()

    def player_browsable(self, entity, widest):
        """Whether a player's library opens. A player that says BROWSE_MEDIA does; Spotify at rest says nothing but
        answers the action all the same, so a player that does not say it is asked once (and again a while after a no)."""
        if widest & media_library.BROWSE_MEDIA:
            return True
        known = self.browsable.get(entity)
        if known and (known[1] or time.monotonic() - known[0] < media_library.BROWSABLE_SECONDS):
            return known[1]
        if entity not in self.browse_probes and getattr(self.ha, 'online', False):
            self.browse_probes[entity] = asyncio.ensure_future(self.probe_browse(entity))
        return bool(known and known[1])

    async def probe_browse(self, entity):
        found = False
        try:
            folder = await media_library.browse(self.ha.call_answer, entity)
            found = True
            self.folders[(entity, None)] = (time.monotonic(), folder)
        except Exception as error:
            LOG.info('The library of %s does not open (%s)', entity, type(error).__name__)
        finally:
            self.browse_probes.pop(entity, None)
        self.browsable[entity] = (time.monotonic(), found)
        if found:
            self.ha.dirty.add(entity)
            self.ha.changed.set()

    # ----- The covers of a player at rest (rest_mosaic.py) -----
    def rest_pool(self, entity, widest):
        """The covers a player at rest shows, [] until its folder is read; read again after POOL_SECONDS."""
        known = self.rest_pools.get(entity)
        if (not known or time.monotonic() - known[0] >= rest_mosaic.POOL_SECONDS) and entity not in self.rest_reads \
                and getattr(self.ha, 'online', False) and self.player_browsable(entity, widest):
            self.rest_reads[entity] = asyncio.ensure_future(self.read_rest_pool(entity))
        return known[1] if known else []

    async def read_rest_pool(self, entity):
        pool = None
        try:
            top = await self.read_folder(entity, None)
            folder = rest_mosaic.folder_for(top)
            pool = rest_mosaic.pool_of(await self.read_folder(entity, folder) if folder else top)
            # The first covers fetched at once: a library whose pictures this app may not fetch (a server's own address
            # in the house) gives no mosaic, rather than a dark card of empty squares.
            first = await asyncio.gather(*(self.thumbnail(entity, thumb, title) for thumb, title in pool[:rest_mosaic.MIN_COVERS]))
            if sum(raw is not None for raw in first) <= rest_mosaic.MIN_COVERS // 2:
                pool = []
        except Exception as error:
            LOG.info('No covers at rest for %s (%s)', entity, type(error).__name__)
        finally:
            self.rest_reads.pop(entity, None)
        before = self.rest_pools.get(entity)
        # A read that failed keeps the covers there were, and is tried again after the same while.
        self.rest_pools[entity] = (time.monotonic(), pool if pool is not None else (before[1] if before else []))
        if pool is not None and (not before or before[1] != pool):
            LOG.info('Covers at rest for %s: %d', entity, len(pool))
            self.ha.dirty.add(entity)
            self.ha.changed.set()

    def rest_render(self, entity, rows=rest_mosaic.ROWS):
        """A player's mosaic for the page's strip (picture_sources, a cover tile's source): its mark now, and the covers of this
        turn drawn into the card's frame, `rows` of them along its shorter side (rest_mosaic.rows_for)."""
        pool = (self.rest_pools.get(entity) or (0, []))[1]

        async def draw(width, height):
            columns, lines, *_ = rest_mosaic.grid_of(width, height, rows)
            order = rest_mosaic.shown(len(pool), columns * lines, rest_mosaic.step_at(time.time()))
            raws = await asyncio.gather(*(self.thumbnail(entity, pool[n][0], pool[n][1]) for n in order))
            return await asyncio.get_running_loop().run_in_executor(None, rest_mosaic.draw, list(raws), width, height, rows)
        return (lambda: rest_mosaic.mark(pool, rest_mosaic.step_at(time.time())), draw)

    def rest_turn(self, dirty):
        """Every ROTATE_SECONDS the players that show covers at rest are drawn again: one cover moves on."""
        step = rest_mosaic.step_at(time.time())
        if step != self.rest_step:
            self.rest_step = step
            if dirty is not None:
                dirty |= self.resting
            self.resting = set()
        return dirty

    # ----- Where a player plays (speakers.py) -----
    def platform_lookup(self, entity):
        lookup = getattr(self.ha, 'platform_of', None)
        return lookup(entity) if lookup else None

    def account_holders(self, entity):
        """The players whose library lists this player's account (a Sonos lists a linked Spotify account), by name. A
        player's library top is read once and again after BROWSABLE_SECONDS; until then it holds nothing."""
        if self.platform_lookup(entity) not in speakers.SOURCE_SPEAKERS:
            return []
        entry = (self.registry_index().get(entity) or {}).get('config_entry_id')
        if not entry:
            return []
        now, found = time.monotonic(), []
        for other, state in list(self.ha.states.items()):
            if not isinstance(other, str) or not other.startswith('media_player.') or other == entity or not isinstance(state, dict):
                continue
            if state.get('state') in ('unavailable', 'unknown'):
                continue
            if not self.players.widest(other, state.get('attributes') or {}) & media_library.BROWSE_MEDIA:
                continue
            known = self.accounts.get(other)
            if (not known or now - known[0] >= media_library.BROWSABLE_SECONDS) and other not in self.account_probes \
                    and getattr(self.ha, 'online', False):
                self.account_probes[other] = asyncio.ensure_future(self.probe_account(other))
            if known and speakers.holds_account(known[1], entry):
                found.append(other)
        return sorted(found, key=lambda e: speakers.name_of(e, self.ha.states).lower())

    async def probe_account(self, entity):
        ids = ()
        try:
            folder = await self.read_folder(entity, None)
            ids = tuple(item['id'] for item in folder['items'])
        except Exception as error:
            LOG.info('The library of %s does not open (%s)', entity, type(error).__name__)
        finally:
            self.account_probes.pop(entity, None)
        before = self.accounts.get(entity)
        self.accounts[entity] = (time.monotonic(), ids)
        if not before or before[1] != ids:
            # The players whose menu lists this one show it now.
            self.ha.dirty.update(tile['entity'] for layout in self.layouts.values() for tile in layout['tiles']
                                 if tile['entity'].startswith('media_player.'))
            self.ha.changed.set()

    def speaker_menu(self, entity):
        """A player's speaker menu and inputs (speakers.menu); a player that plays itself again is followed no more."""
        output = self.outputs.get(entity)
        found = speakers.menu(entity, self.ha.states, self.platform_lookup, self.account_holders(entity), output)
        if output and not found['target'] and (self.ha.states.get(entity) or {}).get('state') == 'playing':
            self.outputs.pop(entity, None)
        return found

    def followed(self, entity):
        """The player a card shows: the speaker it follows (speakers.target_of), or the player itself."""
        return speakers.target_of(entity, self.ha.states, self.outputs.get(entity)) or entity

    def following_states(self, entity, target):
        """The states with the player's own state replaced by the speaker it follows, under the player's name."""
        own, other = self.ha.states.get(entity) or {}, self.ha.states.get(target) or {}
        attrs = {**(other.get('attributes') or {})}
        name = (own.get('attributes') or {}).get('friendly_name')
        if name:
            attrs['friendly_name'] = name
        return {**self.ha.states, entity: {**other, 'entity_id': entity, 'attributes': attrs}}

    async def read_folder(self, entity, item):
        """A folder of a player, read again only after FOLDER_SECONDS: a screen asks for its pages one by one."""
        key = (entity, (item['type'], item['id']) if item else None)
        cached = self.folders.get(key)
        if cached and time.monotonic() - cached[0] < media_library.FOLDER_SECONDS:
            return cached[1]
        folder = await media_library.browse(self.ha.call_answer, entity, item)
        self.folders[key] = (time.monotonic(), folder)
        while len(self.folders) > 32:
            self.folders.popitem(last=False)
        self.browsable[entity] = (time.monotonic(), True)
        return folder

    async def spotify_route(self, entity, top=None):
        """How a favourite of this player plays a Spotify link (app 0.4.84): '' for a Spotify account itself, the account's
        config entry for a player whose library lists one (a Sonos), None for a player that plays no Spotify link. `top`
        is the library's top when it was just read."""
        if self.platform_lookup(entity) in speakers.SOURCE_SPEAKERS:
            return ''
        if top is None:
            try:
                top = await self.read_folder(entity, None)
            except (ClientError, ConnectionError, TimeoutError, OSError, ValueError):
                return None
        return media_library.spotify_entry(top['items'])

    async def spotify_card(self, kind, spotify_id):
        """(title, picture) of a Spotify item from Spotify's public oEmbed, without signing in. Not an official API: a
        favourite works without it, with the word of its kind for a name and the icon of its kind."""
        url = f'https://open.spotify.com/{kind}/{spotify_id}'
        try:
            async with self.ha.session.get(media_library.OEMBED, params={'url': url}, allow_redirects=False,
                                           timeout=ClientTimeout(total=media_library.OEMBED_SECONDS)) as response:
                response.raise_for_status()
                raw = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    raw += chunk
                    if len(raw) > media_library.OEMBED_BYTES:
                        raise ValueError('answer too large')
        except Exception as error:
            LOG.info('Spotify did not describe %s %s (%s)', kind, spotify_id, type(error).__name__)
            return None, None
        title, thumb = media_library.oembed_card(bytes(raw))
        if thumb and not await HomeAssistant._allow_media_url(thumb):
            thumb = None
        return title, thumb

    def player_request(self, request):
        """(inbox, screen, entity, action) of a library request from a screen with that player on its layout, or None."""
        if not isinstance(request, dict):
            return None
        inbox = self.aliases.get(request.get('inbox'), request.get('inbox'))
        entity = request.get('entity')
        layout, screen = self.layouts.get(inbox), self.screen(inbox) if isinstance(inbox, str) else None
        if not isinstance(entity, str) or not entity.startswith('media_player.') or not layout or not screen or not screen.get('online'):
            return None
        if entity not in {tile['entity'] for tile in layout['tiles']}:
            return None
        action = self.transport(inbox, screen)
        return (inbox, screen, entity, action) if action else None

    async def media_loop(self):
        """Answer the folders screens open and play what they tap, a few at a time."""
        limit = asyncio.Semaphore(4)

        async def answer(kind, request):
            async with limit:
                try:
                    if kind == media_library.BROWSE_EVENT:
                        await self.answer_browse(request)
                    elif kind == speakers.SPEAKER_EVENT:
                        await self.answer_speaker(request)
                    else:
                        await self.answer_play(request)
                except Exception as error:
                    LOG.warning('The library of %s did not answer (%s)', request.get('entity') if isinstance(request, dict) else '?', type(error).__name__)
        while True:
            kind, request = await self.ha.media_requests.get()
            asyncio.ensure_future(answer(kind, request))

    def media_token(self, value):
        try:
            token = int(value)
        except (TypeError, ValueError):
            return None
        return token if 0 <= token < 1 << 31 else None

    async def answer_browse(self, request):
        """One page of a folder: the top of the library (folder 0) or a folder a screen got a number for before."""
        found = self.player_request(request)
        token, page = self.media_token(request.get('folder')), self.media_token(request.get('page')) or 0
        if not found or token is None:
            return
        inbox, screen, entity, action = found
        shelf = self.shelves.setdefault(inbox, media_library.Shelf())
        item = shelf.get(entity, token) if token else None
        failed, folder = False, {'title': '', 'items': []}
        if token and (item is None or not item['expand']):
            failed = True
        else:
            try:
                folder = await self.read_folder(entity, item)
            except (ClientError, ConnectionError, TimeoutError, OSError, ValueError) as error:
                LOG.info('The library of %s did not open (%s)', entity, type(error).__name__)
                failed = True
        attrs = self.ha.states.get(entity, {}).get('attributes') or {}
        started = self.started.get(entity) if media_library.holds_media(self.ha.states.get(entity)) else None
        items = media_library.entries(folder, shelf, entity, attrs, started)
        all_pages = media_library.pages(items)
        await self.send_auxiliary(inbox, media_library.message(entity, token, folder['title'], page, all_pages, len(items), failed),
                                  action, request)

    async def answer_play(self, request):
        """Play what a screen tapped, on the speaker it chose (or where the player plays now)."""
        found = self.player_request(request)
        if not found:
            return
        inbox, screen, entity, action = found
        source = request.get('source') if isinstance(request.get('source'), str) and request.get('source') else None
        # A favourite's tile (firmware 0.24.0) names itself by its index: what it plays and its speaker are the tile's.
        if request.get('tile') not in (None, ''):
            index = self.media_token(request.get('tile'))
            tiles = self.layouts.get(inbox, {}).get('tiles', [])
            tile = tiles[index] if index is not None and index < len(tiles) else None
            options = (tile or {}).get('options') or {}
            if not tile or tile['entity'] != entity or options.get('display') != 'favorite':
                return
            item = media_library.favorite_item(options.get('play'))
            source = source or options.get('speaker')
            order = {'shuffle': options.get('shuffle'), 'repeat': options.get('repeat')}
        else:
            order = {}
            token = self.media_token(request.get('item'))
            item = self.shelves.get(inbox, media_library.Shelf()).get(entity, token) if token else None
        if item is None or not item['play']:
            return
        attrs = self.ha.states.get(entity, {}).get('attributes') or {}
        # The speaker by its row in the menu (speakers.py): a Spotify Connect device is a source of the player, a
        # speaker of its library plays the item itself, and without one it plays where the card says it does.
        menu = self.speaker_menu(entity)
        row = speakers.find(menu, source)
        where = entity
        if row is not None and row['source']:
            source = row['source']
        elif row is not None and row['entity']:
            where, source = row['entity'], None
        elif source is None and menu['target']:
            where = menu['target']
        elif source is not None and source not in (attrs.get('source_list') or []):
            LOG.info('%s on %s: no speaker %s', item['title'], entity, source)
            return
        outcome = await media_library.start(self.ha.states, self.ha.call_service, where, item, source, **order)
        if outcome == 'playing':
            if where != entity:
                self.outputs[entity] = where
            elif source is not None:
                self.outputs.pop(entity, None)
            self.started[entity] = (item['type'], item['id'])
            # Every favourite of this player says again whether it is the one that plays.
            self.ha.dirty.add(entity)
            self.ha.changed.set()
        LOG.info('%s on %s from %s: %s', item['title'], entity, screen['name'], outcome)

    async def answer_speaker(self, request):
        """A tap in a player's speaker menu (firmware with speakers.FEATURE): pick a speaker, join or leave the group, or
        set a speaker's volume, each through Home Assistant's own action (speakers.plan)."""
        found = self.player_request(request)
        if not found:
            return
        inbox, screen, entity, action = found
        op = request.get('op') if request.get('op') in ('pick', 'join', 'leave', 'volume') else None
        menu = self.speaker_menu(entity)
        row = speakers.find(menu, request.get('speaker'))
        steps, follow = speakers.plan(entity, menu, row, op, self.ha.states, self.media_token(request.get('volume')))
        for domain, service, data in steps:
            await self.ha.call_service(domain, service, data)
        if follow == '':
            self.outputs.pop(entity, None)
        elif follow:
            self.outputs[entity] = follow
        self.ha.dirty.add(entity)
        self.ha.changed.set()
        if steps or follow is not None:
            LOG.info('%s of %s from %s: %s', op, request.get('speaker'), entity, screen['name'])

    async def preview_picture(self, source, box=(512, 512)):
        """(etag, BMP) of a camera's or a player's picture for the editor's mockup, at its own proportions within `box`:
        prepared pixels only, never a Home Assistant token or address. None when there is none."""
        question = picture_question.Question(picture_question.Owner('view'), (source,), box,
                                             (picture_question.Place(0, 0, *box, fit='shrink'),), formats=('bmp24',))
        found = await self.pictures.picture('', None, question)
        return (found.etag, found.body) if found is not None and found.state == 'ok' else None

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
        # A tile's own entity, or a sensor an energy card on the layout opens from its circles (app 0.4.77).
        shown = {tile['entity'] for tile in layout['tiles']}
        summed = {}
        if ENERGY_TILE in shown:
            summed = energy_flow.sums(self.energy_prefs())
            shown |= set(energy_flow.related_entities(self.energy_prefs())) | set(summed)
        # An entity in a page's top bar opens its card as its tile does (core.BAR_CARDS_FEATURE, firmware 0.56.0).
        record = self.store.get(inbox)
        if record and record.get('format') == PAGE_FORMAT:
            shown |= {item['entity'] for page in record['layout']['pages'] for item in bar_items(page) if item['type'] == 'entity'}
        if entity not in shown:
            return
        what = 'line' if entity in summed else history_card.kind(entity, self.ha.states.get(entity))
        action = self.transport(inbox, screen)
        if what is None or not action:
            return
        # Its words in the language of this screen's firmware (app 0.2.90).
        token = i18n.SCREEN.set(i18n.screen_context(screen))
        try:
            await self.send_auxiliary(inbox, await self.card_history(entity, hours, what), action, request)
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
        summed = energy_flow.sums(self.energy_prefs()).get(entity)
        if summed:
            return await self.summed_history(entity, summed, hours, start, end, tz)
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

    async def summed_history(self, key, entities, hours, start, end, tz):
        """An energy source with several power sensors, as Home Assistant's "Power sources" graph shows it: their sum in
        W (power-sources-graph-data.ts), from the hourly statistics for a day or a week, from the changes for an hour."""
        scales = [energy_flow.scale(self.ha.states.get(e)) for e in entities]
        if hours > 1:
            rows = [[{**row, 'mean': row['mean'] * k} for row in await self.ha.statistic_rows(e, hours)
                     if isinstance(row.get('mean'), (int, float))] for e, k in zip(entities, scales)]
            summed = energy_flow.summed_rows(rows)
            if summed:
                means, extreme = history_card.statistic_changes(summed, 3600)
                return history_card.line(key, hours, means, start, end, tz, None, 'W', extreme)
        series = []
        for e, k in zip(entities, scales):
            changes = [(moment, header_bar.numeric(value)) for moment, value in await self.ha.state_changes(e, hours)]
            series.append([(moment, None if value is None else value * k) for moment, value in changes])
        return history_card.line(key, hours, energy_flow.summed_changes(series), start, end, tz, None, 'W')

    def registry_index(self):
        """Entity registry by id (display precision, entity category); rebuilt only when HA delivers a new registry."""
        registry = getattr(self.ha, 'registry', [])
        if self._registry_source is not registry:
            self._registry_source, self._registry_index = registry, {item['entity_id']: item for item in registry}
        return self._registry_index

    def device_has(self, entity, what):
        """Whether the device of `entity` has `what` a control may need of it (catalogue `needs: device`): a vacuum's map
        (an image or camera entity on it) or its routines (buttons that run something)."""
        if not entity.startswith('vacuum.'):
            return True
        device = self.device_entries(entity)
        if what == 'map':
            return vacuum_card.map_entity(entity, device, self.ha.states) is not None
        if what == 'routines':
            return bool(vacuum_card.routines(entity, device, self.ha.states, getattr(self.ha, 'state_words', None), self.device_name_of(entity)))
        return True

    def vacuum_block(self, entity, device=None):
        """The `vc` block of a vacuum (vacuum_card.payload): its map, its rooms, its routines and why it stopped."""
        return vacuum_card.payload(entity, self.ha.states, device if device is not None else self.device_entries(entity), self.registry_index(),
                                   getattr(self.ha, 'areas', None), getattr(self.ha, 'floors', None), getattr(self.ha, 'state_words', None),
                                   self.device_name_of(entity), lambda icon: tile_icons.GLYPHS.get(icon[4:]) if icon.startswith('mdi:') else None)

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

    def related_entities(self, tile, inbox=None):
        """Entities a card reads besides its own: a vacuum's cleaning mode and water selects and its battery sensor, a
        cover's battery sensor, the entities a plugin tile's entity options chose. `inbox`: the screen it is on, whose
        own plugin of that id says what its options are."""
        from core import cover_related, vacuum_related
        # A plugin tile that belongs to an entity (docs/PLUGINS.md) is sent again when that entity changes, and when one
        # its entity options chose does (plugin API 0.15).
        if plugin_tile(tile['entity']):
            plugin, tile_id = plugin_tile(tile['entity'])
            entry = self.plugins.known(plugin, inbox)
            kind = entry.tile(tile_id) if entry else None
            options = tile.get('options') or {}
            chosen = self.plugins.values_of(entry, kind, options.get('plugin')) if kind else {}
            entity = options.get('plugin_entity')
            return tuple(dict.fromkeys((([entity] if entity else []) + list(self.plugins.option_entities(kind, chosen)))))
        if tile['entity'].startswith('vacuum.'):
            device = self.device_entries(tile['entity'])
            return tuple(dict.fromkeys((*vacuum_related(tile['entity'], device, self.ha.states).values(),
                                        *vacuum_card.related(tile['entity'], device, self.ha.states))))
        if tile['entity'].startswith('cover.'):
            # Its device's battery, and a group's covers (its page, firmware 0.57.0).
            return (tuple(cover_related(tile['entity'], self.device_entries(tile['entity']), self.ha.states).values()) +
                    tuple(cover_groups.cover_ids(tile['entity'], self.ha.states)))
        # A map (app 0.4.33) is drawn from everyone on it and the zones around them: a move or a zone's edit reaches
        # its movement mark only through this.
        if (tile.get('options') or {}).get('display') == 'map':
            # The map tile following everyone reads every person and tracker: one that gets a place joins the map.
            everyone = tile['entity'] == map_card.MAP_TILE and map_card.options_of(tile)['follow'] == 'everyone'
            followed = (tuple(e for e in self.ha.states if isinstance(e, str) and e.split('.')[0] in ('person', 'device_tracker'))
                        if everyone else tuple(map_card.shown(tile, self.ha.states)))
            return tuple(e for e in followed if e != tile['entity']) + tuple(e for e in self.ha.states if isinstance(e, str) and e.startswith('zone.'))
        # The energy card (app 0.4.77) reads every sensor of the Energy settings.
        if tile['entity'] == ENERGY_TILE:
            return tuple(energy_flow.related_entities(self.energy_prefs()))
        # A calendar card (firmware 0.56.0) follows every calendar it shows.
        if tile['entity'].startswith('calendar.'):
            return tuple(calendar_feed.calendars_of(tile)[1:])
        if tile['entity'].startswith('media_player.'):
            # The speakers of its menu: who it groups with, the speakers that play its library, and the one it follows.
            entity = tile['entity']
            related = set(speakers.group_mates(entity, self.ha.states, self.platform_lookup)) | set(self.account_holders(entity))
            output = self.outputs.get(entity)
            if output:
                related |= set(speakers.members(output, self.ha.states))
            return tuple(sorted(related - {entity}))
        if tile['entity'].startswith('light.'):
            # The selects and numbers of its device (effects page), and a group's lamps (lamp page, app 0.3.16).
            return (tuple(light_effects.related(tile['entity'], self.device_entries(tile['entity']), self.ha.states)) +
                    tuple(light_groups.lamp_ids(tile['entity'], self.ha.states)))
        return ()

    def device_name_of(self, entity):
        """The name of the entity's device as Home Assistant shows it (the user's name first), or None."""
        device = self.registry_index().get(entity, {}).get('device_id')
        for item in getattr(self.ha, 'devices', None) or ():
            if isinstance(item, dict) and item.get('id') == device:
                return item.get('name_by_user') or item.get('name')
        return None

    def header_message(self, layout, features=None, cards=None):
        """`features`: the screen's hello (page_delivery.Sender.features); None for this app's own firmware (the preview).
        `cards`: which tile's card each entity's item opens (core.bar_cards)."""
        return header_bar.message(layout, self.ha.states, self.registry_index(), getattr(self.ha, 'units', {}), getattr(self.ha, 'time_zone', None),
                                  getattr(self.ha, 'state_words', None), features, cards)

    def needs_firmware(self, inbox, layout, screen=None):
        """Version string the screen must run first, or None when the layout can be sent."""
        needed=min_firmware(layout)
        if needed and not ((self.firmware_version(inbox, screen) or (0,0,0)) >= needed):
            return '.'.join(str(part) for part in needed)
        # A template tile: a screen whose hello names text_card (module text_card, a full-tier build) draws it.
        sender = self.page_senders.get(inbox)
        if sender is not None and getattr(sender, 'features', None) is not None and text_tile.unsupported(layout.get('tiles', []), sender.features):
            return text_tile.FIRMWARE
        return None

    def save(self, inbox, data):
        if isinstance(data, dict) and data.get('format') == PAGE_FORMAT:
            return self.save_pages(inbox, data)
        screens, entities = self.inventory()
        # A page opened before a screen's inbox got a new id still saves to the right screen.
        inbox = self.aliases.get(inbox, inbox)
        screen=next((s for s in screens if s['id']==inbox), None)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        # Every position on the grid of this screen's pages: two by three on the first boards, whatever a newer
        # screen reports or its profile builds from (Manager.grid_of).
        # With the pages its firmware takes: eight from 0.18.0, as many as 64 tiles fill before.
        # A screen that takes another grid is counted on the one its saved layout gives it (firmware 0.53.0+).
        given = self.given_grid(inbox, self.store.get(inbox))
        grid = (given or self.grid_of(screen)).for_firmware(self.firmware_version(inbox, screen))
        layout = validate_layout(data, grid=grid)
        # A CYD has no memory for camera images, whatever its firmware; say so before asking for an update.
        if any(t['entity'].split('.')[0] in CAMERA_DOMAINS for t in layout['tiles']) and board_of(screen) not in picture_question.BOXES:
            raise ValueError(t('addon.errors.layout.camera_unsupported'))
        # A map is a picture too (app 0.4.33).
        if any((t.get('options') or {}).get('display') == 'map' for t in layout['tiles']) and board_of(screen) not in picture_question.BOXES:
            raise ValueError(t('addon.errors.layout.map_unsupported'))
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
        # A page from before an option existed sends its tiles without it. It never sends an entity twice (a navigation
        # tile from firmware 0.2.65, any entity from 0.16.0), so a copy keeps exactly what it was sent with.
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
        if any(t['entity'] not in known and not plugin_tile(t['entity']) for t in layout['tiles']):
            raise ValueError(t('addon.errors.layout.entity_gone'))
        if any(item['type'] == 'entity' and item['entity'] not in known and item['entity'] not in self.ha.states for item in header_items(layout)):
            raise ValueError(t('addon.errors.top_bar.entity_gone'))
        # The screen takes the layout in one message of at most 4096 bytes, which lists every tile's entity id: 48 tiles
        # with long ids can pass every rule above and still never reach the screen (app 0.2.78).
        try:
            encode(self.layout_message(inbox, layout, screen))
        except ValueError:
            raise ValueError(t('addon.errors.layout.ids_too_long')) from None
        previous = self.store.get(inbox)
        if previous:
            if previous['format'] != PAGE_FORMAT:
                raise LayoutError(t('addon.errors.pages.migration_pending'))
            document = legacy_edit(previous, layout)
        else:
            document = migrate_legacy(layout, grid)['layout']
        self.store.save(inbox, document, previous['revision'] if previous else None, settings=layout.get('settings'), grid=given)
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
        if isinstance(data, dict) and data.get('format') == PAGE_FORMAT:
            grid = self.chosen_grid(inbox, data) or self.layout_grid(inbox, screen)
            document = validate_document(data.get('layout'), grid)
            layout = {'title': document['title'], 'tiles': compile_tiles(document, grid)}
        else:
            layout = validate_layout(data, grid=self.layout_grid(inbox, screen) if screen else None)
        # An entity may stand on several tiles (firmware 0.16.0+): a setting one of its tiles already has passes.
        before = {}
        for tile in self.layouts.get(inbox, {}).get('tiles', []):
            before.setdefault(tile['entity'], []).append(tile)
        for tile in layout['tiles']:
            copies = before.get(tile['entity'], [])
            if tile['entity'] in BUILTIN or not tile.get('options') or any(copy.get('options') == tile['options'] for copy in copies):
                continue
            previous = copies[0] if copies else None
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

    def time_zone_changed(self):
        """Home Assistant moved to another time zone. Its ESPHome integration reads the zone once, when it connects to a
        screen, and answers every later time request with that one, so a screen would keep the old hour until Home
        Assistant restarts. Each screen's integration is loaded again, and the screen takes the new zone as it connects."""
        if self._clock_resync is None or self._clock_resync.done():
            self._clock_resync = asyncio.get_running_loop().create_task(self.resync_clocks())

    async def resync_clocks(self):
        zone = getattr(self.ha.time_zone, 'key', self.ha.time_zone)
        for screen in self.screens():
            try:
                entry = await self.entry_of(screen)
                await self.ha.reload_entry(entry)
                LOG.info('%s follows Home Assistant to the time zone %s', screen['name'], zone)
            except (ValueError, ConnectionError, TimeoutError, ClientError) as error:
                LOG.warning('%s keeps its time zone until it reconnects: %s', screen['name'], error)

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

    def builds(self, screens, profiles=None):
        """What is being built for each screen right now, whoever asked for it (the build line, docs/BUILDS.md): one record
        per screen, so the editor tracks every build in one place (its store, `buildOf`) and shows it wherever it fits.
        `by` is what the build is: `update` (the firmware update, its phase in `phase`), `plugins` (a plugin build,
        `plugins` names what it adds; an update brings them too when the two were asked together) or `install` (New screen,
        Firmware & USB). `state` is `queued` (with its turn, `place`) or `running`; `stage` is ESPHome's step of the build
        that runs now, the same the update's progress reads. `id` is the build's own, which the firmware answer
        (api/firmware `builds`) names with its outcome once it ended. A YAML check builds nothing and has no record; a
        screen with nothing on the way has none either."""
        if profiles is None:
            profiles = self.firmware.profile_names()
        line = self.build_queue
        out = {}
        for screen in screens:
            inbox = screen['id']
            profile, _ = self.updates.resolve(screen, profiles)
            build = next((b for b in line.on_the_way() if b.by != 'check' and (b.screen == inbox or (profile and b.file == profile))), None)
            if build is None:
                continue
            view = line.view(build)
            record = {'id': build.id, 'by': build.by, 'state': view['state'], 'file': build.file or profile,
                      'stage': view.get('stage') if view['state'] == 'running' else None}
            if build.by == 'update':
                record['phase'] = build.phase if view['state'] == 'running' else None
            if build.plugins['add'] or build.by == 'plugins':
                record['plugins'] = list(build.plugins['add'])
            if view['state'] == 'queued':
                record['place'] = view['place']
            # On the build server (build_server.py): its name and step, or why it builds here after all.
            record.update({key: view[key] for key in ('where', 'server', 'remote', 'fallback') if view.get(key)})
            out[inbox] = record
        return out

    def pending_profiles(self, screens, profiles):
        """ESP Screens profiles without a paired screen: flashed but not yet added in Home Assistant, or not flashed yet.

        Pairing happens in Home Assistant itself, outside this page; the sidebar shows these so nobody wonders
        where the freshly flashed screen went. Until Home Assistant has answered once after a start, no paired screen is
        known yet: every profile would look like one waiting, and its Remove would take a paired screen's YAML, so none
        is listed until then (app 0.4.32)."""
        if not self.ha.online and not getattr(self.ha, 'registry', None):
            return []
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

        Cached per (registry, layouts, the lamps of the light groups and the covers of the cover groups on them): the first
        two are replaced as whole objects when they change; a group's members live in its state."""
        groups = tuple((tile['entity'], tuple(light_groups.lamp_ids(tile['entity'], self.ha.states) or cover_groups.cover_ids(tile['entity'], self.ha.states)))
                       for layout in self.layouts.values() for tile in layout['tiles'] if tile['entity'].startswith(('light.', 'cover.')))
        # The speakers a player's menu lists change with what this app started and the libraries it read.
        media = (tuple(sorted(self.outputs.items())), tuple(sorted(e for e, known in self.accounts.items() if known[1])))
        savers = tuple(sorted(e for choice in self.savers.choices.values() for e in screen_saver.entities(choice, self.ha.states)))
        key = (id(getattr(self.ha, 'registry', [])), id(self.layouts), groups, media, savers, id(self.energy_prefs()))
        if key != self._watched_key:
            watched = {tile['entity'] for layout in self.layouts.values() for tile in layout['tiles']}
            watched |= {item['entity'] for record in self.store.records().values() if record['format'] == PAGE_FORMAT
                        for page in record['layout']['pages'] for item in bar_items(page) if item['type'] == 'entity'}
            watched |= {item['entity_id'] for item in self.screen_registry()}
            watched |= {eid for inbox, layout in self.layouts.items() for tile in layout['tiles'] for eid in self.related_entities(tile, inbox)}
            watched |= {eid for device in self.setting_index().values() for eid in device.values()}
            watched |= set(savers)
            self._watched_key, self._watched = key, watched
        return set(self._watched)

    def energy_prefs(self):
        """Home Assistant's Energy settings as last read (energy/get_prefs), {} before the first answer."""
        entry = self.forecasts.get('energy/get_prefs')
        return entry[1] if entry and isinstance(entry[1], dict) else {}

    async def cached(self, store, key, ttl, fetch):
        entry=store.get(key)
        if not entry or time.monotonic()-entry[0]>ttl:
            try: value=await fetch()
            except Exception: value=[]
            entry=(time.monotonic(),value);store[key]=entry
        return entry[1]

    def calendar_due(self, tile):
        """A calendar card's events are a few minutes old: it is sent again with fresh ones."""
        entry = self.forecasts.get(('calendar', self.calendar_key(tile)))
        return not entry or time.monotonic() - entry[0] > calendar_feed.SECONDS

    def calendar_key(self, tile):
        """What a card's events depend on: its calendars, their last change in Home Assistant (an edit or an event's
        start or end fetches again at once), how far it looks and today."""
        calendars = calendar_feed.calendars_of(tile)
        changed = tuple((self.ha.states.get(e) or {}).get('last_updated', '') for e in calendars)
        tz = getattr(self.ha, 'time_zone', None) or timezone.utc
        return (tuple(calendars), changed, calendar_feed.ahead_of(tile), datetime.now(tz).date().isoformat())

    async def calendar_events(self, tile):
        """Home Assistant's events of a calendar card's calendars over its window, by calendar, a few minutes old at most."""
        tz = getattr(self.ha, 'time_zone', None) or timezone.utc
        start, end = calendar_feed.window(datetime.now(tz).date(), calendar_feed.ahead_of(tile))
        calendars = calendar_feed.calendars_of(tile)
        async def fetch():
            if not hasattr(self.ha, 'events'):
                return {}
            begin = datetime.combine(start, datetime.min.time(), tzinfo=tz)
            return await self.ha.events(calendars, begin, datetime.combine(end, datetime.min.time(), tzinfo=tz))
        fetched = await self.cached(self.forecasts, ('calendar', self.calendar_key(tile)), calendar_feed.SECONDS, fetch)
        return fetched if isinstance(fetched, dict) else {}

    async def calendar_extras(self, tile, features=None, caps=None):
        """The `x.cal` of a calendar tile: Home Assistant's events of its calendars, filtered and packed for the screen.
        `features` and `caps`: the screen's hello, for compact events and the count it keeps (calendar_feed.keeps); None
        for the editor's preview, which gets every event whole."""
        tz = getattr(self.ha, 'time_zone', None) or timezone.utc
        fetched = await self.calendar_events(tile)
        compact = features is not None and calendar_feed.FEATURE in features
        return calendar_feed.card(tile, fetched, self.ha.states, self.registry_index(), tz, datetime.now(tz),
                                  compact=compact, most=calendar_feed.keeps(features, caps))

    def forecast_due(self, entity):
        entry = self.forecasts.get(entity)
        hourly = self.forecasts.get((entity, 'hourly'))
        return not entry or not hourly or time.monotonic() - min(entry[0], hourly[0]) > FORECAST_SECONDS

    def text_caps(self, inbox):
        """(bytes, tiles) of a screen's template tiles (text_tile.budget_of): what its hello's caps say, else the defaults."""
        sender = self.page_senders.get(inbox) if inbox else None
        return text_tile.budget_of(None, getattr(sender, 'caps', None))

    async def sync_templates(self):
        """Home Assistant renders the template of every template tile on a screen, and of the editor's last preview."""
        if not hasattr(self.ha, 'subscribe_template'):
            return
        wanted = set()
        for inbox, layout in self.layouts.items():
            wanted |= template_service.wanted_templates([layout.get('tiles', [])], self.text_caps(inbox)[1])
        wanted |= template_service.wanted_templates([self.preview_tiles])
        try:
            await self.templates.sync(wanted)
        except Exception as error:
            LOG.warning('Template tiles were not brought up to date (%s)', type(error).__name__)

    def text_message(self, index, tile, inbox=None):
        """A template tile's state message: its rows as Home Assistant last rendered them (`x.md`, text_tile.py), none
        while Home Assistant has not answered yet."""
        template = (tile.get('options') or {}).get(text_tile.OPTION)
        result = self.templates.result(template) if isinstance(template, str) else None
        block = result.block(self.text_caps(inbox)[0]) if result else None
        if not isinstance(template, str):
            block = text_tile.block('')
        return state_message(index, tile, self.ha.states, {'md': block} if block else None)

    async def tile_message(self, index, tile, lamps=False, features=None, inbox=None):
        """The state message of one tile: state, options, extras, and the history the background task holds. `lamps`:
        the screen takes a light group's lamps (its hello said `group_lamps`, firmware 0.3.9+). `features`: the other
        flags its hello said (page_delivery), None where the screen's hello is not known. `inbox`: the screen it goes to."""
        # A plugin's tile (docs/PLUGINS.md): no entity behind it; its options and the data of its fetch, from the plugin of
        # that id this screen runs.
        if plugin_tile(tile['entity']):
            return await self.plugins.tile_message(index, tile, inbox=inbox)
        if tile['entity'] == text_tile.TEXT_TILE:
            return self.text_message(index, tile, inbox)
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
        # A player's speakers and inputs (speakers.py), to a screen that draws them; a player that plays on a speaker of
        # its library through this app shows that speaker, under its own name.
        menu=None
        states=self.ha.states
        if tile['entity'].startswith('media_player.') and (features is None or speakers.FEATURE in features):
            menu=self.speaker_menu(tile['entity'])
            if menu['target']:
                states=self.following_states(tile['entity'],menu['target'])
        # A favourite (app 0.4.42) is named after what it plays until it is given a name of its own.
        options=tile.get('options') or {}
        favorite=tile['entity'].startswith('media_player.') and options.get('display')=='favorite'
        if favorite and not tile.get('name') and isinstance(options.get('play'),dict):
            tile={**tile,'name':options['play'].get('title') or ''}
        # A light's effects page (app 0.2.83) names the device's selects and numbers as Home Assistant does, with its icons.
        light=tile['entity'].startswith('light.')
        if tile['entity'] == ENERGY_TILE and hasattr(self.ha, 'request'):
            async def prefs():
                try:
                    return await self.ha.request('energy/get_prefs')
                except Refused:
                    return {}  # no Energy settings yet: the card says where to add them
            await self.cached(self.forecasts, 'energy/get_prefs', ENERGY_PREFS_SECONDS, prefs)
            # Home Assistant away is no answer: asked again with the next message rather than in five minutes.
            if not isinstance(self.forecasts['energy/get_prefs'][1], dict):
                self.forecasts.pop('energy/get_prefs', None)
        # A screen that draws the weather card's week (its hello says weather_week) takes seven days and 48 hours.
        week=features is not None and WEATHER_WEEK in features
        extra=extras(tile,states,forecast,getattr(self.ha,'time_zone',None),hourly,device=device,energy=self.energy_prefs() if tile['entity'] == ENERGY_TILE else None,
                     home_name=getattr(self.ha,'location_name','') if tile['entity'] == ENERGY_TILE else '',
                     entries=self.registry_index() if light or (tile.get('options') or {}).get('display') == 'map' else None,words=getattr(self.ha,'state_words',None) if light else None,
                     icon_of=row_icon if light else None,device_name=self.device_name_of(tile['entity']) if light else None,week=week)
        if tile['entity'].startswith('vacuum.'):
            ha_catalogue.chip_words(extra,tile['entity'],self.ha.states,device,getattr(self.ha,'state_words',None))
            # The card of the module (vacuum_card.py): its map, its rooms, its routines and why it stopped, to a screen
            # that draws them (its hello says vacuum_card).
            if features is not None and vacuum_card.FEATURE in features:
                card=self.vacuum_block(tile['entity'],device)
                if card:
                    extra={**(extra or {}),'vc':card}
                    # The map read ahead, so the card that opens only waits for its own size (vacuum_map_warm).
                    if isinstance(card.get('map'),dict):
                        self.snapshots.vacuum_warm(card['map']['e'],card['map']['m'])
        if tile['entity'].startswith('calendar.'):
            sender = self.page_senders.get(inbox) if inbox else None
            extra = {**(extra or {}), 'cal': await self.calendar_extras(tile, features, getattr(sender, 'caps', None))}
        message=state_message(index,tile,states,extra,
                              precision=header_bar.precision_of(entry) if tile['entity'].startswith('sensor.') else None,entry=entry,
                              units=getattr(self.ha,'units',None),week=week)
        # A media player at rest keeps the controls it had while it played (GitHub #88): what it draws is cut to the
        # widest features it reported, and the screen fades what it lacks right now.
        player=tile['entity'].startswith('media_player.')
        attributes=states.get(tile['entity'],{}).get('attributes') or {}
        # A card that follows a speaker draws the speaker's keys, and leaves the player's own memory as it was.
        following=bool(menu and menu['target'])
        widest=(media_library.features_of(attributes) if following else self.players.note(tile['entity'],attributes)) if player else 0
        if self.players.dirty:
            self.players.save()
        if player and widest!=message['a'].get('supported_features',0):
            reported=message['a'].get('supported_features')
            message['a']['supported_features']=widest
            drawn_controls(message, features)
            if reported is None: message['a'].pop('supported_features')
            else: message['a']['supported_features']=reported
        else:
            drawn_controls(message, features)
        # A camera tile set to Live: pace 0 to a screen that streams, the default pace to any other (live_stream.live_pace).
        live_stream.live_pace(message, tile, features)
        # The speaker, shuffle, repeat, the cover's colours and the library (firmware 0.24.0+): to a screen that draws
        # them, and to the editor's preview, which runs the newest firmware.
        if player and (features is None or media_library.FEATURE in features):
            more=media_library.player_extras(attributes,widest,self.player_ground(tile['entity'],attributes),
                                             self.player_browsable(tile['entity'],widest))
            if menu is not None:
                # The menu's rows replace source_list: a Sonos's inputs go behind their own key, never in the pill.
                more.pop('so',None);more.pop('sl',None)
                more.update(speakers.extras(menu))
            if more:
                message.setdefault('x',{}).update(more)
            # A favourite (firmware 0.24.0): what it plays, on which speaker, and whether it plays now.
            if favorite:
                play=options.get('play') or {}
                state_now=states.get(tile['entity'],{}).get('state')
                started=self.started.get(tile['entity']) if media_library.holds_media(states.get(tile['entity'])) else None
                word=screen_t(f"addon.screen.media.{play.get('class') or 'music'}") if (play.get('class') or 'music') in FAVORITE_KINDS else ''
                message.setdefault('x',{}).update(media_library.favorite_extras(play,options.get('speaker'),attributes if state_now in ('playing','paused') else {},started,word))
            # A cover tile of a player at rest: the covers of its library, as a mosaic the screen asks for by its mark.
            if rest_mosaic.wants(options):
                pool=self.rest_pool(tile['entity'],widest) if rest_mosaic.at_rest(states.get(tile['entity'])) else []
                if pool:
                    message.setdefault('x',{})['pic']=rest_mosaic.mark(pool,rest_mosaic.step_at(time.time()))
                    self.resting.add(tile['entity'])
        # Home Assistant's word where the screen would show the raw state (firmware 0.2.58+ shows it).
        state=states.get(tile['entity'],{})
        word=ha_catalogue.screen_word(tile['entity'],message['state'],state.get('attributes'),entry,getattr(self.ha,'state_words',None))
        if word:
            message.setdefault('x',{})['w']=word
        # A light group's lamps for its lamp page (app 0.3.16), to a screen that takes them.
        if lamps and light:
            members=light_groups.lamps(tile['entity'],self.ha.states)
            if members:
                message.setdefault('x',{})['lamps']=members
        # A cover group's covers for its page (firmware 0.57.0), to a screen whose hello says group_covers.
        if features and cover_groups.FEATURE in features and tile['entity'].startswith('cover.'):
            members=cover_groups.covers(tile['entity'],self.ha.states)
            if members:
                message.setdefault('x',{})['covers']=members
        if tile['entity'].startswith('alarm_control_panel.'):
            for key,value in alarm_extras(state,entry).items():
                message.setdefault('x',{})[key]=value
        if tile['entity'].startswith('lock.'):
            for key,value in lock_extras(entry).items():
                message.setdefault('x',{})[key]=value
        # A remote's keypad (firmware 0.22.0): what its integration takes for each key, read from Home Assistant.
        if tile['entity'].startswith('remote.'):
            keys=catalogue.remote_keypad((entry or {}).get('platform'))
            if keys:
                message.setdefault('x',{})['keys']=keys
        # A second line set to a value of this entity (app 0.2.105): the finished line, or seconds for a moment in
        # time. The other three settings live in the option itself, so the screen keeps drawing them without us.
        for key,value in ha_catalogue.subtitle_message(tile,state,getattr(self.ha,'units',None),entry,getattr(self.ha,'state_words',None)).items():
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

    async def sync_pages(self, inbox, record, screen, dirty=None, force=False, context=None):
        return await page_service.sync_pages(self, inbox=inbox, record=record, screen=screen, dirty=dirty, force=force, context=context)

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
            record = self.store.get(inbox)
            if record and record['format'] == PAGE_FORMAT:
                sender = await self.probe_pages(inbox, screen)
                if sender.protocol == 2:
                    return await self.sync_pages(inbox, record, screen, dirty, force, context)
                try:
                    layout = self.layouts.legacy(inbox)
                except LayoutError:
                    self.status[inbox] = 'Update screen to use the new titlebar and layout'
                    return False
            return await self._sync_one(inbox, layout, force, screen, dirty, context)
        finally:
            i18n.SCREEN.reset(token)

    async def sync_pending_legacy(self, inbox, screen, sender, dirty):
        """Keep a readable pending record working on verified old firmware.

        This recovery boundary is used only while migration is pending. It
        neither changes the original payload nor guesses an unreadable layout.
        New firmware deliberately has no legacy decoder.
        """
        record = self.store.get(inbox)
        if sender.protocol != 1 or not record or record['format'] != 'legacy-v1': return False
        grid = self.verified_grid(inbox)
        if grid is None: return False
        try:
            layout = validate_layout(json.loads(record['payload']), stored=True, grid=grid)
        except (ValueError, TypeError, KeyError, AttributeError):
            return False
        force = time.monotonic() - self.last.get(inbox, 0) >= KEEPALIVE_SECONDS
        return await self.sync_one(inbox, layout, force=force, screen=screen, dirty=dirty)

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
                # This route has no hello, so none of the screen's own items (firmware 0.38.0) either.
                header_msg = self.header_message(layout, frozenset())
            else:
                header_msg = previous['header']
        states = []
        for i, tile in enumerate(tiles):
            reuse = not full and i < len(previous['states']) and tile['entity'] not in dirty and dirty.isdisjoint(self.related_entities(tile, inbox))
            if reuse and tile['entity'].startswith('weather.') and self.forecast_due(tile['entity']):
                reuse = False
            if reuse and tile['entity'].startswith('calendar.') and self.calendar_due(tile):
                reuse = False
            # A screen on this route has no hello, and none of the flags a newer option needs.
            states.append(previous['states'][i] if reuse else await self.tile_message(i, tile, features=frozenset(), inbox=inbox))
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
        if sent.get('protocol') == 2:
            await self.page_senders[inbox].ping()
            self.pinged[inbox] = time.monotonic()
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
                for sender in self.page_senders.values(): sender.disconnected()
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
            dirty = self.rest_turn(self.take_dirty())
            if self.region.pinned and self.resolve_clock_pin():
                self.language_changed()
            screens_key = self._screens_key
            screens = self.screens()
            self.refresh_page_records()
            changed = self._screens_key != screens_key
            self.ha.relevant = self.watched_entities()
            await self.sync_templates()
            # A setting changed on a screen that owns them: the editor shows it.
            settings_key = self.settings_states_key()
            if settings_key != self._settings_key:
                self._settings_key, changed = settings_key, True
            for screen in screens:
                inbox = screen['id']
                before = self.status.get(inbox)
                if not screen['online']:
                    self.sent.pop(inbox, None)
                    if inbox in self.page_senders: self.page_senders[inbox].disconnected()
                    self.status[inbox] = english('addon.status.offline')
                    changed = changed or self.status[inbox] != before
                    continue
                try:
                    if inbox not in self.layouts:
                        sender = self.page_senders.get(inbox)
                        previous_protocol = sender.protocol if sender else None
                        sender = await self.probe_pages(inbox, screen)
                        changed = changed or previous_protocol != sender.protocol
                        changed = await self.sync_pending_legacy(inbox, screen, sender, dirty) or changed
                        continue
                    now = time.monotonic()
                    pings = self.supports_ping(inbox, screen)
                    # The screen says it lost the layout (restart, mismatched ping, a state that never came).
                    if inbox in self.sent and screen['status'] in RESEND_STATES and now - self.last.get(inbox, 0) >= RESEND_GUARD_SECONDS:
                        self.sent.pop(inbox)
                        if inbox in self.page_senders: self.page_senders[inbox].disconnected()
                    # An answer said so right after a full send; its wait is over (firmware 0.2.49+).
                    if inbox in self.retry_at and now >= self.retry_at[inbox]:
                        del self.retry_at[inbox]
                        self.sent.pop(inbox, None)
                    force = now - self.last.get(inbox, 0) >= (FULL_REPEAT_SECONDS if pings else KEEPALIVE_SECONDS)
                    if await self.sync_one(inbox, self.layouts[inbox], force, screen, dirty):
                        changed = True
                    await self.sync_saver(inbox, screen)
                    if pings and inbox in self.sent and now - self.pinged.get(inbox, 0) >= KEEPALIVE_SECONDS:
                        await self.ping(inbox, screen)
                except Exception as error:
                    self.sent.pop(inbox, None)
                    if inbox in self.page_senders: self.page_senders[inbox].disconnected()
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

    def layout_tiles(self, inbox):
        """The tiles of a screen's saved layout; for a firmware preview of the editor (preview_images.inbox_of), the tiles
        of the layout it compiled, by its revision, or of the last one compiled."""
        if preview_images.is_preview(inbox):
            return self.preview_layouts.get(preview_images.revision_of(inbox), self.preview_tiles)
        return self.layouts.get(inbox, {}).get('tiles', [])

    def camera_allowed(self, inbox, entity):
        """A camera on the screen's own layout, or one a recent alert showed; for the editor's preview any entity Home
        Assistant has."""
        if preview_images.is_preview(inbox):
            return entity in self.ha.states
        seen = self.alert_cameras.get(entity)
        if seen is not None and time.monotonic() - seen < picture_links.STILL_SECONDS:
            return True
        if entity in self.saver_entities(inbox):
            return True
        return entity in {tile['entity'] for tile in self.layout_tiles(inbox)}

    def saver_entities(self, inbox):
        """The player and camera a screen's screensaver follows (app 0.4.48)."""
        device = (self.screen(inbox) or {}).get('device_id')
        return screen_saver.entities(self.savers.get(device), self.ha.states) if device else set()

    def saver_message(self, screen):
        """What this screen's screensaver shows now (screen_saver.message), for a board that draws pictures or not."""
        choice = self.savers.get(screen.get('device_id')) if screen.get('device_id') else dict(screen_saver.DEFAULT)
        pictures = bool(picture_question.box(screen, 'full'))
        # A screen whose screensaver has keys (firmware 0.33.0+) also shows a player paused a short while ago.
        sender = self.page_senders.get(screen.get('id'))
        keys = screen_saver.KEYS_FEATURE in (getattr(sender, 'features', None) or ())
        # The player it shows keeps the glass for a while after a pause (screen_saver.HELD_SECONDS).
        row = screen_saver.ITEMS_FEATURE in (getattr(sender, 'features', None) or ())
        # A player whose cover could not be fetched gives way to the next step (GitHub #229).
        broken = {entity for entity in screen_saver.players(choice) if self.snapshots.cover_broken(entity)}
        # A face other than the digital clock, for a screen whose hello says it draws them (module clock_faces).
        faces = screen_saver.FACES_FEATURE in (getattr(sender, 'features', None) or ())
        # The photos step (app 0.4.89): only for a screen whose hello names it, and only while it may show.
        photos = None
        if pictures and screen_saver.PHOTOS_FEATURE in (getattr(sender, 'features', None) or ()):
            wanted = choice.get('show') and 'photos' not in choice.get('off', ()) and choice['photos'].get('source')
            photos = self.photos.state(screen.get('id'), choice['photos']) if wanted else {'ready': False}
            if not wanted:
                self.photos.forget(screen.get('id'))
        message = screen_saver.message(choice, self.ha.states, pictures, short, media_extras, self.player_ground, keys,
                                       held=self.saver_shown.get(screen.get('id'), ''), bar=self.saver_item if row else None,
                                       broken=broken, faces=faces, photos=photos, plugins=self.saver_plugins(screen, choice))
        # A plugin's face or step gets its options with the manifest's defaults, as a plugin tile does (plugin API 0.14).
        if 'pf' in message and core.plugins_enabled():
            message['pf']['o'] = self.plugins.saver_values(screen.get('id'), message['pf']['p'], message['pf']['o'])
        return message

    def saver_plugins(self, screen, choice):
        """The plugins' faces and steps a screen's screensaver may show (plugin API 0.14), or None for a screen without
        any: {'faces': {key: step}, 'steps': {key: what the step draws from, None while it has nothing}}."""
        return self.plugins.saver_plugins(screen, choice, self.ha.states) if core.plugins_enabled() else None

    def saver_item(self, item):
        """One of the clock's entity items as the top bar sends it (header_bar.entity_item)."""
        return header_bar.entity_item(item, self.ha.states, self.registry_index(), getattr(self.ha, 'units', {}),
                                      getattr(self.ha, 'time_zone', None), getattr(self.ha, 'state_words', None))[0]

    async def sync_saver(self, inbox, screen):
        """Tell a screen that takes a screensaver (its hello lists it, firmware 0.29.0+) what it shows now, whenever that
        changes and once in every new session. A small message in the screen's session, as a camera's answer is. Only
        once the screen holds a layout: before it confirmed one (a saved layout that waits for its grid to be adapted,
        say) the screen refuses a message without a revision, and its refusal would stand in place of the real status."""
        sender = self.page_senders.get(inbox)
        if not sender or sender.protocol != 2 or not sender.confirmed \
                or screen_saver.FEATURE not in (getattr(sender, 'features', None) or ()):
            return
        message = self.saver_message(screen)
        key = (sender.session, json.dumps(message, sort_keys=True))
        if self.saver_sent.get(inbox) == key:
            return
        try:
            delivered = await sender.auxiliary(message, session=sender.session, revision=sender.confirmed)
        except Exception as error:
            # Tried again on the next pass; the tiles' own delivery is no business of the screensaver. A message whose
            # answer did not come may have reached the screen all the same, so the next pass sends what is right then,
            # also when that is the word sent before it (GitHub #229): the screen keeps a word it already has.
            self.saver_sent.pop(inbox, None)
            LOG.info('Screensaver for %s not delivered (%s)', screen.get('name', inbox), type(error).__name__)
            return
        if delivered:
            self.saver_sent[inbox] = key
            self.saver_shown[inbox] = message.get('e', '') if message['k'] == 'media' else ''
            LOG.info('Screensaver on %s: %s', screen.get('name', inbox), message['k'] or 'dark')

    # ----- pictures (docs/PICTURES.md): every question a screen asks, answered by one service -----
    async def answer_camera(self, request):
        """One screen's question for a picture: the new shape (`q` with its number `n`, firmware with the feature
        `pictures`) or a shape of older firmware (picture_legacy), answered by the one service (picture_service)."""
        if not isinstance(request, dict):
            return
        inbox = self.aliases.get(request.get('inbox'), request.get('inbox'))
        screen = self.screen(inbox) if isinstance(inbox, str) else None
        if not screen or not screen.get('online') or not picture_question.draws_pictures(screen):
            return
        action = self.transport(inbox, screen)
        if not action:
            return
        if 'q' in request:
            try:
                number = int(request.get('n'))
            except (TypeError, ValueError):
                return
            shape = picture_question.shape_of(screen)
            question = picture_question.parse(request['q'], number, (shape.get('width', 0), shape.get('height', 0)))
            if question is None:
                LOG.info('A picture question from %s that cannot be read', screen['name'])
                return
            kind, entity = 'q', ''
        else:
            legacy = picture_legacy.read(request, screen, self.sources.index_of(inbox))
            if legacy is None:
                # A shape this app does not answer, or tiles that are not pictured tiles of the screen's layout.
                LOG.info('A picture request from %s that cannot be read: %s', screen['name'],
                         str(request.get('tiles') or request.get('entity') or '?')[:120])
                return
            question, kind, entity = legacy.question, legacy.kind, legacy.entity
        answer = await self.pictures.answer(inbox, screen, question)
        if answer is None:
            return  # on its way: the screen asks again (camera_view::ASK_AGAIN_MS)
        # An older screen's page of tiles reads which of them got a picture from the answer: '' where one got none.
        listing = ','.join(answer.shown) if kind == 'live' and len(question.places) > 1 and answer.url else entity
        message = picture_question.answer(question, answer.url, kind, listing, answer.meta or None)
        await self.send_auxiliary(inbox, message, action, request)
        what = ', '.join(source.text for source in dict.fromkeys(question.sources))
        LOG.info('Picture of %s on %s%s', what, screen['name'], ' (stream)' if answer.stream else '' if answer.url else ': none')
        if kind == 'saver' and not answer.url and question.sources[0].kind == 'cover':
            # The cover did not come: a pass right away, which gives the glass to the next step (cover_broken).
            self.ha.changed.set()

    async def camera_snapshot(self, entity):
        """A camera's picture of now: the newest frame of its stream while one runs for a screen (one source per camera
        for stills and streams, docs/PICTURES.md), else Home Assistant's snapshot."""
        frame = await self.live.latest(entity)
        return frame if frame is not None else await self.ha.camera_image(entity)

    def saver_choice(self, screen):
        """What a screen's screensaver shows, as chosen for its device (screen_saver)."""
        return self.savers.get(screen.get('device_id')) if (screen or {}).get('device_id') else dict(screen_saver.DEFAULT)

    def plugin_saver_kind(self, inbox, key):
        """The manifest's screensaver of a plugin key (plugin:<plugin>.<saver>) on this screen, or {}."""
        return (self.plugins.saver_kinds(inbox).get(key, (None, None))[1]) or {}

    def plugin_place(self, inbox, screen, question):
        """(manifest entry, the manifest's tile, card or screensaver, of_entity) of a plugin's question: of_entity says
        whether its card or step shows an entity whose Home Assistant pictures it may have (None for a tile: its manifest
        says). (None, None, False) for a plugin or place this screen does not run."""
        owner = question.owner
        placed = self.layouts.get(inbox, {}).get('tiles', [])
        if owner.kind == 'plugin_saver':
            entry, kind = self.plugins.saver_kinds(inbox).get(owner.key, (None, None))
            chosen = ((self.saver_choice(screen).get('plugins') or {}).get(owner.key) or {}).get('entity', '')
            return entry, kind, bool(owner.of) and owner.of == chosen
        parts = core.plugin_tile(owner.key)
        if not parts:
            return None, None, False
        if owner.kind == 'plugin_card':
            entry = self.plugins.known(parts[0], inbox) if self.plugins.store.get(inbox, parts[0]) else None
            of = bool(owner.of) and any(owner.of in (t['entity'], (t.get('options') or {}).get('plugin_entity')) for t in placed)
            return entry, (entry.card(parts[1]) if entry else None), of
        if not (0 <= owner.index < len(placed) and placed[owner.index]['entity'] == owner.key):
            return None, None, False
        entry = self.plugins.known(parts[0], inbox)
        return entry, (entry.tile(parts[1]) if entry else None), None

    def plugin_picture_refused(self, inbox, screen, question, source):
        """Why a plugin's place may not show `source`, as a sentence for the log; None when it may (plugin_pictures)."""
        entry, kind, of = self.plugin_place(inbox, screen, question)
        return plugin_pictures.refused_source(source, len(question.sources), entry.manifest if entry else None, kind, of)

    async def plugin_picture(self, inbox, screen, question, source):
        """The bytes of a plugin place's address (`url`, `ha`) or of its entity's own picture (`entity`), or None."""
        entry, kind, of = self.plugin_place(inbox, screen, question)
        if not entry:
            return None
        if source.kind == 'entity':
            picture = ((self.ha.states.get(source.ref) or {}).get('attributes') or {}).get('entity_picture') or ''
            try:
                return await self.ha.entity_picture(picture) if picture else None
            except Exception as error:  # noqa: BLE001 - an entity without a picture that can be had
                LOG.info('No picture for %s (%s)', source.ref, type(error).__name__)
                return None
        return await self.plugins.pictures.fetch(source.text, entry.manifest, kind, of)

    async def map_meta(self, mark, width, height, focus):
        """What a map opened over the whole glass brings beside its picture: where its markers are, the one a finger
        picked, and that one's card. Pixels and words, never a place."""
        sheet = {'h': self.map_hits.get((mark, width, height), [])[:16], 'f': focus}
        if focus:
            sheet['c'] = await self.map_sheet(focus)
        return sheet

    async def photo_loop(self):
        """A pass when a screen's next photo is due (the passes otherwise follow Home Assistant's changes)."""
        while True:
            await asyncio.sleep(2)
            if self.photos.due():
                self.ha.changed.set()

    async def saver_picture(self, inbox, screen, kind):
        """The picture of the step a plugin's screensaver face draws (its address `step:`): the cover of the
        player the music step shows, or the photo of the photos step; None while there is none."""
        if kind.get('step') == 'photos':
            return self.photos.raw(inbox)
        if kind.get('step') == 'media':
            entity = self.saver_shown.get(inbox, '')
            if entity:
                return await self.snapshots.cover_raw(entity)
        return None

    async def thumbnail(self, entity, url, title=''):
        """A picture of a player's library, fetched once and kept a while (the library's covers and the favourites'); None
        when it does not come, and the next ask tries again."""
        if url not in self.thumbnails:
            try:
                raw = await self.ha.browse_image(entity, url)
            except Exception as error:
                LOG.info('No picture for %s (%s)', title or entity, type(error).__name__)
                return None
            self.thumbnails[url] = raw
            while len(self.thumbnails) > 96:
                self.thumbnails.popitem(last=False)
        self.thumbnails.move_to_end(url)
        return self.thumbnails[url]

    async def map_sheet(self, entity):
        """The card of a person or tracker picked on a full map, as Home Assistant's own map shows a selected one
        (hui-map-overview.ts): its state since when, its battery where it reports one, and the changes of the last day
        newest first, each with its time. Rows as the effects page draws them (an icon, a name, a value at the right),
        with Home Assistant's own icon and word for each state, in the screens' language and clock."""
        state = self.ha.states.get(entity) or {}
        a = state.get('attributes') or {}
        entry = self.registry_index().get(entity)
        words = getattr(self.ha, 'state_words', None)
        tz = getattr(self.ha, 'time_zone', None) or timezone.utc
        word = lambda value: state_word(entity, value, a, entry, words) or str(value or '')
        clock = lambda moment: i18n.screen_clock(moment.hour, moment.minute)
        # Home Assistant's icon for a person or tracker in that state (a person at home, one away), else a marker.
        icon = lambda value: tile_icons.default_glyph(entity, value, a, entry) or tile_icons.GLYPHS['map-marker']
        now = datetime.now(timezone.utc)
        since = ''
        try:
            moment = datetime.fromisoformat(str(state.get('last_changed', '')).replace('Z', '+00:00'))
            if now - moment < timedelta(hours=24):
                since = screen_t('addon.screen.map.since_time', time=clock(moment.astimezone(tz)))
        except (ValueError, TypeError):
            pass
        rows = [[icon(state.get('state')), word(state.get('state'))[:40], since[:24]]]
        battery = a.get('battery_level', a.get('battery'))
        if isinstance(battery, (int, float)) and not isinstance(battery, bool):
            level = max(10, min(100, round(battery / 10) * 10))
            glyph = tile_icons.GLYPHS.get('battery' if level == 100 else f'battery-{level}') or tile_icons.GLYPHS['battery']
            rows.append([glyph, screen_t('addon.screen.map.battery'), f'{round(battery)}{i18n.unit_suffix("%")}'])
        try:
            changes = await self.ha.state_changes(entity, 24)
        except Exception as error:
            LOG.info('No history for %s on the map (%s)', entity, type(error).__name__)
            changes = []
        activity, previous = [], None
        # The state the day began with is no change; a moment without a place (unavailable) is none either.
        for moment, value in changes:
            if value in ('unavailable', 'unknown', None):
                continue
            if previous is not None and value != previous:
                activity.append([icon(value), word(value)[:40], clock(datetime.fromtimestamp(moment, tz))])
            previous = value
        name = a.get('friendly_name') or entity.split('.', 1)[1]
        return {'t': str(name)[:60], 'r': (rows + activity[::-1])[:8]}

    # The maps kept drawn: a page's maps in both looks and the page before it.
    MAP_RENDERS_KEPT = 12

    def map_render(self, tile, shape, dark, full=False, focus=None, move=None):
        """(mark, draw) of one saved map tile for CameraFeed.live: the mark is its movement mark and the look, `draw`
        reads Home Assistant's states and asks for the streets when it runs. A drawn card is kept by mark, frame and
        look, so two screens in different looks each keep their own, and one whose streets did not all come is not."""
        board = map_card.Board(shape)
        # The screen's look, unless the card keeps one of its own (`look`, app 0.4.36).
        dark = map_card.dark_for(tile, dark)
        look = 'd' if dark else 'l'

        def mark():
            # Without streets to be had it is another picture, so the one with streets replaces it when they come back.
            streets = '' if self.map_source.available() or not map_card.wants_streets(tile) else '-'
            moved = '@%d,%s,%s' % move if move else ''
            return f'{map_card.fingerprint(tile, self.ha.states, self.registry_index())}{look}{streets}{"f" if full else ""}{focus or ""}{moved}'

        async def draw(width, height):
            key = (mark(), width, height, board.scale, board.label)
            if key in self.map_renders:
                self.map_renders.move_to_end(key)
                self.map_hits[key[:3]] = self.map_renders[key].info.get('hits', [])
                return self.map_renders[key]
            registry = self.registry_index()
            view = map_card.view_for(tile, self.ha.states, (width, height), board, registry, full, focus, move)
            wanted = view.tiles() if map_card.wants_streets(tile) else []
            streets = await self.map_source.tiles(wanted)
            photos = await self.map_photos(map_card.pictures_wanted(tile, self.ha.states, registry))
            image = await asyncio.get_running_loop().run_in_executor(
                None, lambda: map_card.render_tile(tile, self.ha.states, (width, height), board, dark, streets, registry, photos, full, focus, move))
            # Where its markers are, for a full view's finger (answer_map_full): kept as long as the picture is.
            self.map_hits[key[:3]] = image.info.get('hits', [])
            while len(self.map_hits) > self.MAP_RENDERS_KEPT:
                self.map_hits.pop(next(iter(self.map_hits)))
            if self.map_source.available() and len(streets) < len(wanted):
                image.info['provisional'] = True
            else:
                self.map_renders[key] = image
                while len(self.map_renders) > self.MAP_RENDERS_KEPT:
                    self.map_renders.popitem(last=False)
            return image
        return mark, draw

    # The pictures of people kept for their markers, by address: a new picture is a new address.
    MAP_PHOTOS_KEPT = 32

    async def map_photos(self, wanted):
        """{entity: picture} for the markers that show one (app 0.4.36), fetched through Home Assistant as its own map
        does and kept by address. One that cannot be had leaves that marker with its initials."""
        from PIL import Image
        out = {}
        for entity, address in wanted.items():
            if address not in self.map_pictures:
                try:
                    raw = await self.ha.entity_picture(address)
                    picture = Image.open(io.BytesIO(raw))
                    picture.draft('RGB', (256, 256))
                    picture = picture.convert('RGB')
                    picture.thumbnail((256, 256))
                except Exception as error:
                    LOG.info('No picture for %s on the map (%s)', entity, type(error).__name__)
                    picture = None
                self.map_pictures[address] = picture
                while len(self.map_pictures) > self.MAP_PHOTOS_KEPT:
                    self.map_pictures.popitem(last=False)
            if self.map_pictures.get(address) is not None:
                out[entity] = self.map_pictures[address]
        return out

    async def alert_images(self, camera, screens):
        """The picture of an alert's camera at that moment, on every screen that draws it."""
        self.alert_cameras[camera] = time.monotonic()
        for old in [entity for entity, moment in self.alert_cameras.items() if time.monotonic() - moment > picture_links.STILL_SECONDS]:
            del self.alert_cameras[old]
        # One snapshot of this moment for every screen, measured once: each screen's alert card makes a frame for a
        # picture of its proportions (firmware 0.2.103+), and the picture goes out at exactly that frame's size, made
        # from the same snapshot (picture_question.alert_box). Grouped by that size, not by the board: two screens of the
        # same board hang different ways when one was built standing up. Screens whose board draws no picture at all
        # fall out here, as they always did.
        drawn = [screen for screen in screens if picture_question.box(screen, 'thumb')]
        scopes = {screen['id']: self.page_scope(screen['id']) for screen in drawn}
        picture = await self.snapshots.size(camera) if drawn else None
        groups = {}
        for screen in drawn:
            # And by the address the screen fetches from: a Home Assistant on two networks has one for each (#276).
            groups.setdefault((picture_question.alert_box(screen, picture), await self.link_base(screen)), []).append(screen)

        async def send(key, group):
            box, base = key
            # A box made for this picture's proportions is filled exactly; the 16:9 frame of older firmware gets the
            # picture fitted inside it, as before.
            exact = picture is not None and box != picture_question.box(group[0], 'thumb')
            question = picture_question.Question(
                picture_question.Owner('alert'), (picture_question.Source('camera', camera),), box,
                (picture_question.Place(0, 0, *box, fit='exact' if exact else 'shrink'),), formats=('bmp24',))
            found = await self.pictures.picture(group[0]['id'], group[0], question) if picture and base else None
            url = f'{base}/camera/{self.links.add(still=found.body)}.bmp' if found and found.state == 'ok' else ''
            if not base:
                LOG.warning('Camera images: no address for this app on the LAN; set SCREEN_CAMERA_URL')
            message = {'v': 1, 'op': 'camera', 't': 'alert', 'e': camera, 'u': url}
            results = await asyncio.gather(*(self.send_auxiliary(screen['id'], message, self.transport(screen['id'], screen), scopes.get(screen['id'], {})) for screen in group),
                                           return_exceptions=True)
            failed = sum(isinstance(result, BaseException) for result in results)
            LOG.info('Alert image of %s: %d of %d screens%s', camera, len(group) - failed, len(group), '' if url else ' (no image)')

        # Every size at once, so no screen waits for another board's picture to be made. Each reads the snapshot
        # measured above, so every screen shows the same moment.
        await asyncio.gather(*(send(key, group) for key, group in groups.items()))

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
        # The second button and the buttons' colours (firmware 0.3.3+) and what the second button does (app 0.3.8).
        choice, bad = alert_choice(data) if event_type == BROADCAST_SHOW else ({}, [])
        unusable += bad
        button2, usable = alert_action(data, 'button2_action', 'button2_data') if event_type == BROADCAST_SHOW else (None, True)
        if not usable:
            unusable.append('button2_action')
        if button2 and not choice.get('button2_text'):
            LOG.warning('%s: button2_action without button2_text, no second button', event_type)
            button2 = None
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
        viewers = [screen for screen in ready if camera and picture_question.draws_pictures(screen) and self.transport(screen['id'], screen)]
        if viewers:
            pending = {'v': 1, 'op': 'camera', 't': 'alert', 'e': camera, 'u': ''}
            scopes = {screen['id']: self.page_scope(screen['id']) for screen in viewers}
            await asyncio.gather(*(self.send_auxiliary(screen['id'], pending, self.transport(screen['id'], screen), scopes[screen['id']]) for screen in viewers),
                                 return_exceptions=True)
        # An alert with a choice goes as show_alert_choice to a screen that has it, and as show_alert, with one button, to
        # an older one, which the log names.
        choice_min = parse_firmware(ALERT_CHOICE_MIN_FIRMWARE)
        chooses = {screen['node'] for screen in ready if choice and (screen_firmware(screen) or (0, 0, 0)) >= choice_min}
        older = [screen['name'] for screen in ready if choice and screen['node'] not in chooses]
        if older:
            LOG.warning('%s: %s show one button (the second button needs firmware %s)', event_type, ', '.join(older), ALERT_CHOICE_MIN_FIRMWARE)
        calls = [self.ha.call(alert_service(screen['node'], ALERT_CHOICE_ACTION), choice_service(service_data, choice))
                 if screen['node'] in chooses else self.ha.call(alert_service(screen['node'], action), service_data) for screen in ready]
        results = await asyncio.gather(*calls, return_exceptions=True)
        failed = [(screen, type(result).__name__) for screen, result in zip(ready, results) if isinstance(result, BaseException)]
        notes = [f"{screen['name']} {reason}" for screen, reason in skipped + failed]
        LOG.info('%s: %d of %d screens%s%s', event_type, len(ready) - len(failed), len(ready) + len(skipped),
                 f' for {names}' if names else '', f" (not: {'; '.join(notes)})" if notes else '')
        shown = [screen for screen, result in zip(ready, results) if not isinstance(result, BaseException)]
        # The button's action waits on every screen that shows this alert; a dismissal forgets it everywhere.
        for screen in ready:
            self.alert_actions.pop(screen['node'], None)
        if (button or button2) and shown:
            key = secrets.token_hex(4)
            for screen in shown:
                # Only a screen that draws the second button can press it.
                self.alert_actions[screen['node']] = (key, {'ok': button, 'button2': button2 if screen['node'] in chooses else None})
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
        # Firmware 0.2.65+ takes a navigation tile on several pages, 0.16.0+ any entity on several tiles; an older
        # screen keeps one per page a navigation tile goes to, and one of everything else.
        firmware = self.firmware_version(inbox, screen) or (0, 0, 0)
        for _ in range(3):
            # check_supported waits on Home Assistant for the capabilities of the entity. A save of the editor's that lands
            # meanwhile makes a new revision, and a layout laid over the one before it would undo that save without a
            # word: start again from what is there now. Two saves in a row within one wait is as rare as it gets.
            before = self.store.get(inbox)   # a copy of the record as stored: a save meanwhile shows as another one
            layout, tile = run_tile_event(self.layouts.get(inbox) or {'title': screen['name'], 'tiles': []}, TILE_EVENTS[event_type], data,
                                          firmware >= PAGE_TILE_REPEAT_MIN_FIRMWARE, self.layout_grid(inbox, screen).for_firmware(firmware),
                                          firmware >= ENTITY_REPEAT_MIN_FIRMWARE)
            await self.check_supported(inbox, layout)
            if self.store.get(inbox) == before:
                break
        record = self.store.get(inbox)
        if record and record['format'] == PAGE_FORMAT:
            self.save_pages(inbox, {'format': PAGE_FORMAT, 'revision': record['revision'], 'layout': replace_tiles(record, layout)})
        else:
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
                    inbox = self.aliases.get(screen['id'], screen['id'])
                    answer.update(page=self.layout_grid(inbox, screen).page_of(tile['slot']) + 1, slot=tile['slot'])
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
            snapshot = layout_snapshot(screen, layout, self.layout_grid(inbox, screen).for_firmware(self.firmware_version(inbox, screen)))
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

    def doorbell_screens(self):
        """The screens a ring goes to: online, reachable, and their hello said `doorbell` (module doorbell, a P4)."""
        out = []
        for screen in self.screens():
            sender = self.page_senders.get(screen['id'])
            if screen.get('online') and sender and doorbell.FEATURE in (getattr(sender, 'features', ()) or ()) and self.transport(screen['id'], screen):
                out.append(screen)
        return out

    async def doorbell_send(self, screens, message):
        """`message` to each of `screens`, or `message(screen)` for a message of each one's own: how many took it."""
        results = await asyncio.gather(*(self.send_auxiliary(screen['id'], message(screen) if callable(message) else message,
                                                             self.transport(screen['id'], screen), self.page_scope(screen['id']))
                                         for screen in screens), return_exceptions=True)
        return sum(1 for result in results if result is True)

    async def doorbell_link(self, screen, camera):
        """The stream of `camera` for the ring's view on `screen`, made as the event comes: the screen opens it at once,
        where asking for one took 1.3 s of a ring's 1.54 s to its first picture (docs/PLATFORM_PLAN.md 4.9). Its room
        comes with the screen's first open (?room=WxH). None without an address for this app on its network."""
        base = await self.link_base(screen)
        if not base:
            return None
        sound = bool((self.caps_of_screen(screen) or {}).get('speaker'))
        token = self.live.link(camera, None, sound=sound, screen=screen['id'], turn=self.picture_turn_of(screen['id']))
        return f'{base}/camera/{token}.mjpeg'

    async def doorbell_show(self, data):
        """esp_screens_doorbell (docs/DOORBELL.md): the doorbell's camera on the screens the event names, every screen
        without a name. A screen that draws a doorbell opens the camera live with its sound and a chime; any other gets
        the camera's alert. What the reply of Events, Try it shows: sent (views), alerts, skipped, failed, unknown."""
        camera, title, timeout, unusable = doorbell.request(data)
        if camera is None:
            LOG.warning('%s: no camera (camera.<name>), nothing sent', doorbell.SHOW)
            return {'sent': 0, 'alerts': 0, 'skipped': 0, 'failed': 0, 'unusable': unusable}
        door, door_unusable = doorbell.door_of(data)
        sound, sound_unusable = doorbell.sound_of(data)
        chime, chime_unusable = doorbell.sound_of(data, 'chime')
        keep, keep_unusable = doorbell.keep_of(data)
        unusable = unusable + door_unusable + sound_unusable + chime_unusable + keep_unusable
        if door and door.get('lock'):
            blocked = doorbell.door_blocked(door['lock'], self.ha.states, self.registry_index().get(door['lock']))
            if blocked:
                LOG.warning('%s: %s %s, so the view has no door key', doorbell.SHOW, door['lock'], blocked)
                door = None
        paired = self.screens()
        wanted, usable = alert_screen_names(data)
        if not usable:
            LOG.warning('%s: unusable screen, sent to no screen', doorbell.SHOW)
            return {'sent': 0, 'alerts': 0, 'skipped': 0, 'failed': 0, 'unusable': unusable + ['screen']}
        screens, unknown = alert_screen_choice(paired, wanted) if wanted else (paired, [])
        if unknown:
            LOG.warning('%s: no screen called %s', doorbell.SHOW, ', '.join(unknown))
        views = [screen for screen in self.doorbell_screens() if screen['id'] in {s['id'] for s in screens}]
        others = [screen for screen in screens if screen not in views and screen.get('node')]
        name = title or doorbell.name_of(camera, self.device_name_of(camera), self.ha.states)
        # The screens may open this camera now (camera_allowed), as after an alert with its picture.
        self.alert_cameras[camera] = time.monotonic()
        key = self.doorbells.start(camera, name, timeout, [screen['id'] for screen in views], [screen['node'] for screen in others],
                                   door, [screen.get('node') for screen in views if screen.get('node')], sound, chime, keep)
        links = dict(zip((screen['id'] for screen in views),
                         await asyncio.gather(*(self.doorbell_link(screen, camera) for screen in views))))
        if any(links.values()):
            self.live.warm(camera)  # its first picture on its way before the first screen opens its link
        state = self.doorbell_lock_state(door)
        sent = await self.doorbell_send(views, lambda screen: self.doorbells.message(key, door_state=state,
                                                                                  link=links.get(screen['id']))) if views else 0
        if door and door.get('lock') and views:
            asyncio.ensure_future(self.doorbell_follow_lock(key))
        alerts = {'sent': 0, 'skipped': 0, 'failed': 0}
        if others:
            alerts = await self.broadcast(BROADCAST_SHOW, {'title': name, 'icon': doorbell.ALERT_ICON, 'camera': camera,
                                                           'timeout': timeout, 'screen': [screen['node'] for screen in others]})
        LOG.info('%s: %s on %d screens with its view, %d with its alert', doorbell.SHOW, camera, sent, alerts.get('sent', 0))
        asyncio.ensure_future(self.doorbell_unanswered(key, timeout))
        result = {'sent': sent, 'alerts': alerts.get('sent', 0), 'skipped': alerts.get('skipped', 0) + len(views) - sent,
                  'failed': alerts.get('failed', 0), 'unusable': unusable}
        if wanted:
            result['unknown'] = unknown
        return result

    async def doorbell_close(self, key, views, alerts):
        """A ring ends: its view closes on `views` (inboxes), its alert on `alerts` (nodes)."""
        screens = [screen for screen in self.screens() if screen['id'] in set(views) and self.transport(screen['id'], screen)]
        self.doorbells.gone(key, [screen.get('node') for screen in self.screens() if screen['id'] in set(views)])
        closed = await self.doorbell_send(screens, self.doorbells.message(key, close=True)) if screens else 0
        if alerts:
            await self.broadcast(BROADCAST_DISMISS, {'screen': list(alerts)})
        return closed

    async def doorbell_dismiss(self, data):
        """esp_screens_dismiss_doorbell: every ring nobody answered yet closes on every screen."""
        for key in self.doorbells.open():
            views, alerts = self.doorbells.answered(key)
            closed = await self.doorbell_close(key, views, alerts)
            LOG.info('%s: closed on %d screens', doorbell.DISMISS, closed)
        self.ha.changed.set()

    async def doorbell_unanswered(self, key, timeout):
        """Nobody answered the ring before its timeout: it is the missed ring, which the top bars of those screens show."""
        await asyncio.sleep(timeout + doorbell.MISSED_GRACE)
        if self.doorbells.unanswered(key):
            LOG.info('Doorbell ring missed: it shows in the top bars')
            self.ha.changed.set()
            ring = self.doorbells.ring(key) or {}
            await self.doorbell_fire(doorbell.MISSED, {'camera': ring.get('camera'), 'title': ring.get('name')})

    async def doorbell_fire(self, event_type, data):
        """The app's own event of a ring (doorbell.ANSWERED, MISSED), once, for an automation that follows it."""
        try:
            await self.ha.fire(event_type, data)
        except Exception as error:
            LOG.warning('%s was not fired (%s)', event_type, type(error).__name__)

    def doorbell_lock_state(self, door):
        """The state of a ring's lock as Home Assistant has it, '' without one."""
        lock = (door or {}).get('lock')
        return str((self.ha.states.get(lock) or {}).get('state') or '') if lock else ''

    def doorbell_view_screens(self, key):
        """The screens whose view of ring `key` still shows."""
        nodes = set(self.doorbells.showing(key))
        return [screen for screen in self.doorbell_screens() if screen.get('node') in nodes]

    async def doorbell_follow_lock(self, key):
        """While ring `key` shows on a screen, every new state of its lock goes to those screens' door key."""
        ring = self.doorbells.ring(key)
        changes = getattr(self.ha, 'state_events', None)
        if ring is None or ring.get('following') or changes is None:
            return
        lock, sent = ring['door']['lock'], self.doorbell_lock_state(ring['door'])
        ring['following'] = True
        wake = asyncio.Event()
        changes.listeners[wake] = frozenset({lock})
        try:
            while self.doorbells.showing(key):
                try:
                    await asyncio.wait_for(wake.wait(), 5)
                except asyncio.TimeoutError:
                    continue
                wake.clear()
                state = self.doorbell_lock_state(ring['door'])
                if state != sent:
                    sent = state
                    await self.doorbell_send(self.doorbell_view_screens(key), self.doorbells.door_message(key, state))
        finally:
            changes.listeners.pop(wake, None)
            ring['following'] = False

    async def doorbell_open_door(self, key, node):
        """A second tap on the door key of ring `key` on screen `node`: the ring's lock unlocks, or its action runs, once."""
        door = self.doorbells.door_press(key, node)
        if door is None:
            LOG.warning('Doorbell door from %s: no door of a ring that shows there, nothing performed', node)
            return
        action, fields = ('lock.unlock', {'entity_id': door['lock']}) if door.get('lock') else (door['action'], door['data'])
        try:
            await self.ha.call(action, fields)
            LOG.info('Doorbell door on %s: %s performed', node, action)
        except Exception as error:
            LOG.warning('Doorbell door on %s: %s failed (%s)', node, action, type(error).__name__)

    async def doorbell_report(self, data):
        """A screen says how a ring ended there (esphome.screen_doorbell): answered or closed closes it on the others,
        seen takes a missed ring out of the top bars, door opens the ring's door."""
        if not isinstance(data, dict):
            return
        action, key, node = data.get('action'), data.get('key'), data.get('screen')
        if action == doorbell.DOOR and isinstance(key, str):
            await self.doorbell_open_door(key, node)
            return
        if action in ('closed', 'missed') and isinstance(key, str):
            self.doorbells.gone(key, [node])
        if action in doorbell.ANSWERS and isinstance(key, str):
            had_missed = self.doorbells.missed is not None
            first = not (self.doorbells.ring(key) or {'answered': True})['answered']
            views, alerts = self.doorbells.answered(key)
            if first:
                ring = self.doorbells.ring(key)
                await self.doorbell_fire(doorbell.ANSWERED, {'camera': ring['camera'], 'title': ring['name'], 'screen': node})
            others = [screen['id'] for screen in self.screens() if screen['id'] in set(views) and screen.get('node') != node]
            if others or alerts:
                closed = await self.doorbell_close(key, others, alerts)
                LOG.info('Doorbell ring %s on %s: closed on %d other screens', action, node, closed)
            if had_missed and self.doorbells.missed is None:
                self.ha.changed.set()
        elif action == 'seen':
            # The missed ring opened again from the top bar: its door key gets its lock's state and follows it again.
            if isinstance(key, str) and (self.doorbells.ring(key) or {}).get('door'):
                self.doorbells.back(key, node)
                ring = self.doorbells.ring(key)
                if ring['door'].get('lock'):
                    await self.doorbell_send(self.doorbell_view_screens(key), self.doorbells.door_message(key, self.doorbell_lock_state(ring['door'])))
                    asyncio.ensure_future(self.doorbell_follow_lock(key))
            if self.doorbells.seen():
                self.ha.changed.set()

    async def doorbell_loop(self):
        """Rings and the screens' reports of them, in arrival order."""
        queue = getattr(self.ha, 'doorbell_events', None)
        while queue is not None:
            kind, data = await queue.get()
            try:
                handler = {doorbell.SHOW: self.doorbell_show, doorbell.DISMISS: self.doorbell_dismiss}.get(kind, self.doorbell_report)
                await handler(data)
            except Exception as error:
                LOG.warning('Doorbell %s failed (%s)', kind, type(error).__name__)

    async def alert_ended(self, data):
        """A screen reports how its alert ended (esphome.screen_alert). The button performs the action the alert
        came with, once for the alert however many screens showed it; any other ending forgets it on that screen."""
        node = data.get('screen') if isinstance(data, dict) else None
        pending = self.alert_actions.pop(node, None) if isinstance(node, str) else None
        if pending is None:
            return
        key, buttons = pending
        for other in [n for n, (k, _) in self.alert_actions.items() if k == key]:
            del self.alert_actions[other]
        chosen = buttons.get(data.get('action')) if isinstance(data.get('action'), str) else None
        if not chosen:
            return
        action, fields = chosen
        which = 'Alert button' if data.get('action') == 'ok' else 'Alert second button'
        try:
            await self.ha.call(action, fields)
            LOG.info('%s on %s: %s performed', which, node, action)
        except Exception as error:
            LOG.warning('%s on %s: %s failed (%s)', which, node, action, type(error).__name__)

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
        allowed = {'127.0.0.1', '::1'} if development else {'172.30.32.2'}
        if request.remote not in allowed:
            raise web.HTTPForbidden(text=t('addon.errors.open_through_ha'))
        if request.method not in {'GET', 'HEAD'} and request.headers.get('X-Screen-CSRF') != csrf:
            raise web.HTTPForbidden(text=t('addon.errors.refresh_page'))
        try:
            response = await handler(request)
        except Conflict as error:
            return web.json_response({'error': str(error), 'conflict': True}, status=409)
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
        except (TypeError, KeyError) as error:
            # Input the handler could not read, or a slip of the app's own that looks just like it: the page gets the
            # one sentence either way, and the log the traceback, so a bug is not taken for bad input.
            LOG.warning('%s %s: %s (%s)', request.method, request.path, type(error).__name__, error, exc_info=True)
            return web.json_response({'error': t('addon.errors.invalid_input')}, status=400)
        if response.prepared:
            return response  # streamed (SSE) responses set their headers before prepare()
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # The LVGL preview compiles the bundled WASM module. Allow that narrowly;
        # JavaScript eval and inline scripts remain disallowed.
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'"
        return response

    # A layout of 48 tiles with actions on their taps passes 16 KB, the limit from the twenty-tile days; the largest the
    # rules allow stays under about 75 KB (app 0.2.78). The YAML override keeps its own 12 KB limit (firmware.py).
    # Named editor features. An experiment can sit behind SCREEN_EDITOR_ENV=development here and never changes
    # authentication or firmware capabilities; taller tiles left that stage in 0.3.1.
    # Plugins (docs/PLUGINS.md), on in every app since 0.4.87 (core.plugins_enabled).
    editor_features = {'tall_tiles': True, 'plugins': core.plugins_enabled()}
    app = web.Application(middlewares=[guard], client_max_size=128*1024)
    static = Path(__file__).parent / 'static'

    async def cache_assets(request, response):
        """The built script, styles and fonts under /assets/ never change under their name (Vite names each file after a
        hash of its content), so a browser keeps them instead of fetching about 310 KB on every open (app 0.2.78).
        `private`: behind ingress the request carries Home Assistant's session. index.html and api/ stay no-store."""
        if request.path.startswith('/assets/') and response.status in (200, 304):
            response.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
        # A plugin's picture is asked for under its commit (plugins.image_url), so it too can be kept: a day.
        elif request.path.startswith('/api/plugins/') and request.path.endswith('/image') and response.status == 200:
            response.headers['Cache-Control'] = 'private, max-age=86400'
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
            # The editor's own name for the screen (app 0.4.2); `ha_name` is what Home Assistant calls it.
            screen['ha_name'] = screen['name']
            screen['name'] = manager.labels.get(screen.get('device_id')) or screen['name']
            # A screen without tiles yet: the title the screen itself shows without one, in its language (app 0.2.90).
            screen['layout'] = manager.layouts.get(screen['id'], {'title': screen_t('screen.status.home'), 'tiles': []})
            record = manager.store.get(screen['id'])
            screen['page_document'] = ({**record, 'migrationRevision': fingerprint(record['payload']),
                                       'migrationError': t(record['migrationError'] if record.get('migrationError') in
                                                           ('addon.errors.pages.source_grid', 'addon.errors.pages.migration_unreadable')
                                                           else 'addon.errors.pages.migration_unreadable')}
                                       if record and record['format'] == 'legacy-v1' else record)
            sender = manager.page_sender(screen['id'], screen)
            source = manager.record_grid(screen['id'], record)
            screen['source_grid'] = {'columns': source.columns, 'rows': source.rows} if source else None
            # The grids it takes each way its glass hangs (firmware 0.53.0+): the editor offers them beside the mockup,
            # and which way it is to hang on glass that turns ('landscape' or 'portrait', None on square glass).
            screen['grids'] = manager.screen_grids(screen['id'])
            screen['hang'] = manager.wanted_way(screen['id']) if manager.turnable(screen['id']) else None
            screen['tile_sizes'] = sorted(sender.tile_sizes if sender.protocol is not None else sender.last_tile_sizes) if sender else ['single', 'wide', 'full']
            screen['page_capability'] = ('offline' if not screen.get('online') or not sender or sender.protocol is None
                                         else 'ready' if sender.protocol == 2 else 'update_screen')
            screen['page_last_capability'] = ('ready' if sender and sender.last_protocol == 2
                                              else 'update_screen' if sender and sender.last_protocol == 1 else None)
            screen['page_delivery'] = sender.phase if sender else 'waiting'
            screen['page_saved_revision'] = record.get('revision') if record else None
            screen['page_applied_revision'] = manager.sent.get(screen['id'], {}).get('saved_revision')
            screen['settings'] = manager.settings_view(screen)
            # The screensaver (app 0.4.48): the choice, whether this screen's firmware takes one, whether its board
            # draws pictures (else the clock alone) and whether it goes into standby at all.
            screen['screensaver'] = {**manager.savers.get(screen.get('device_id')),
                                     'ready': (manager.firmware_version(screen['id'], screen) or (0, 0, 0)) >= SCREENSAVER_MIN_FIRMWARE,
                                     'pictures': bool(picture_question.box(screen, 'full')), 'standby': can_standby(screen),
                                     # The clock's faces where the board has their module (docs/MODULES.md).
                                     'faces': has_module(screen, screen_saver.MODULE),
                                     # The photos step where the screen's firmware takes it (app 0.4.89); `photos` is the
                                     # choice's own folder, pace, order and fit.
                                     'photos_step': screen_saver.PHOTOS_FEATURE in (getattr(manager.page_senders.get(screen['id']), 'features', None) or ())}
            # The delivery and our own word for a screen that reports nothing, in the editor's language (app 0.2.90).
            status = manager.status.get(screen['id'])
            word = PAGE_DELIVERY_WORDS.get(status) if isinstance(status, str) else None
            screen['delivery'] = t(f'addon.status.{word}') if word else shown(status) if status else t('addon.status.first_tiles')
            # The layout went out and the screen says it holds it: nothing to report, so the editor shows no
            # delivery line at all (app 0.2.108); anything else is worth a line.
            screen['in_sync'] = ((status == 'Applied' and screen['page_saved_revision'] == screen['page_applied_revision'])
                                 or (bool(status) and getattr(status, 'key', None) == 'addon.status.sent'
                                     and shown(screen.get('status')) == 'Synced'))
            screen['status'] = status_text(screen.get('status'))
            screen['update'] = manager.updates.state_for(screen, profiles)
            # The API key its YAML carries (app 0.2.132), so it can be copied again after pairing: Home Assistant asks
            # for it again when the integration is removed and re-added, or the screen is paired with another HA.
            profile, _ = manager.updates.resolve(screen, profiles)
            screen['api_key'] = (profiles.get(profile) or {}).get('api_key') if profile else None
            # Its last image against its slot on a 4 MB board: what the editor says is left for a plugin (PLUGINS.md).
            screen['firmware_image'] = manager.firmware.image_room(profile, screen.get('flash')) if profile else None
            # What this screen looks like: what it reported itself, else the board package its profile builds
            # from (the YAML), else its board. The editor draws its mockup and places tiles on this grid.
            screen['package'] = manager.package_of(screen, profiles)
            # The board too: a screen that says nothing about itself is known by the YAML its profile builds from.
            screen['board'] = board_of(screen)
            # A screen with 4 MB of flash that still has ESPHome's partition table (app 0.4.82): the editor says to update
            # it in Tessera, which moves the table; ESPHome Device Builder's update does not fit its slot.
            screen['update_in_tessera'] = update_in_tessera(screen)
            # And which way it was built to hang (app 0.2.107), for the same reason: a screen standing up has another
            # canvas and another grid, and while it is offline only its own YAML says so.
            screen['orientation'] = manager.orientation_of(screen, profiles)
            # And the grid it was built with, when its own YAML chose one (app 0.4.31 rows, app 0.4.85 columns and rows).
            screen['built_grid'] = manager.built_as(screen, profiles).get('built_grid')
            screen['shape'] = shape_of(screen)
            # A screen that takes another grid runs on the one its saved layout gives it, offline too (firmware 0.53.0+):
            # the mockup shows that grid, not the one the screen reported before the layout reached it.
            if screen['grids'] and source:
                screen['shape'] = {**screen['shape'], 'columns': source.columns, 'rows': source.rows}
                # And the way it is to hang, before it turned: the other way round, the canvas is the other way round.
                if screen['hang'] and (screen['hang'] == 'portrait') != screen['grids']['upright']:
                    screen['shape'] = {**screen['shape'], 'width': screen['shape']['height'], 'height': screen['shape']['width']}
            # And whether it has a battery for the top bar (firmware 0.41.0): what its hello said, else its board.
            screen['battery'] = manager.has_battery(screen)
            screen['live_camera'] = manager.live_camera(screen)
            # What its hardware can do, from its last hello (firmware hw.h): the editor marks a live camera beyond its
            # live tiles at once (caps.live_tiles) as one that shows a picture every 15 seconds.
            screen['caps'] = manager.caps_of_screen(screen)
            # The Dock (docs/MODULES.md): the editor offers "Show in Dock" on a page of a board that has it.
            screen['dock'] = has_module(screen, 'dock')
            # A vacuum's larger tile (docs/VACUUM.md, "A larger tile"): its map, rooms and routines on a board with the
            # vacuum card's module; the editor offers them there only, and a screen whose hello lacks vacuum_tile gets
            # the keys (catalogue screen else).
            screen['vacuum_tile'] = has_module(screen, 'vacuum_card')
            # The template tile (docs/TEXT_TILE.md): only a board with the module text_card draws it.
            screen['text_tiles'] = has_module(screen, text_tile.FEATURE)
            # A light's presets (docs/LIGHT_PRESETS.md): only a board with the module light_presets draws them.
            screen['light_presets'] = has_module(screen, 'light_presets')
            # Whether the board draws pictures (camera tiles, an alert's snapshot, an album cover): the boards with
            # memory for them say so with their camera sizes (boards.json); the firmware that draws them is a
            # separate question the editor asks by version, so an older screen still learns what an update brings.
            screen['pictures'] = board_of(screen) in picture_question.BOXES
            screen['alert_action'] = alert_service(screen.get('node'))
            screen['dismiss_action'] = alert_service(screen.get('node'), 'dismiss_alert')
            screen['doorbell'] = manager.doorbell_kind(screen)
            # What the editor may offer this screen, by the firmware the app's own checks go by (app 0.2.78) and the
            # grid of its pages: an offline screen keeps its tiles, and the editor needn't know the version rules.
            version = manager.firmware_version(screen['id'], screen)
            screen['firmware_known'] = version_text(version)
            screen.update(firmware_features(version, manager.grid_of(screen)))
            # The memory it has for its tiles and what each costs (firmware 0.34.0+): the editor shows how full it is.
            screen['memory'] = manager.memory(screen['id'])
            # The items a page's top bar takes (firmware 0.34.0+ says more on a board with room): the editor's limit.
            screen['bar_limit'] = manager.grid_of(screen).bar_items
            # Does it work as you expect (app 0.3.10): only for a board the website knows, and never the key.
            board, device = (screen['board'] if screen['board'] in BOARD_KEYS else None), screen.get('device_id')
            if board and device and not manager.feedback.readonly:
                if screen.get('online'):
                    manager.feedback.seen_usable(device)
                screen['feedback'] = {**manager.feedback.view(device), 'board': board,
                                      'model': (SHAPES.get(board, {}).get('catalog') or {}).get('model'),
                                      'versions': manager.feedback_versions(screen), 'privacy': feedback.PRIVACY_URL}
            else:
                screen['feedback'] = None
            # How a plugin it runs works for you (docs/PLUGINS.md, "Likes, ratings and counting"): the stars card.
            screen['plugin_ask'] = manager.plugins.ask_card(screen) if editor_features['plugins'] else None
        return {'csrf': csrf, 'connected': manager.ha.online, 'screens': screens,
                'editor_features': editor_features,
                'pending': manager.pending_profiles(screens, profiles),
                'updates': manager.updates.summary(screens, profiles),
                # The app's build line (docs/BUILDS.md): every build that runs, waits or ended last, and per screen the one
                # on its way (Manager.builds), from one look at the line, so the editor has one source for every build.
                'line': manager.build_queue.payload(),
                'builds': manager.builds(screens, profiles),
                # The build server: paired or not, there or not, on or off, what it builds (build_server.py).
                'build_server': manager.build_server.view(),
                # What this app shares about plugins (plugin_likes.py): the likes' yes, counting, whether cards ask.
                'plugin_sharing': manager.plugins.liker.view() if editor_features['plugins'] else None,
                # The live streams of every screen together against the most the app serves (live_stream.py): the
                # camera card says them, so whoever adds a ninth knows why it shows its stills.
                'live_streams': manager.live.usage(),
                'language': manager.region.view()}
    async def seen_pending(payload):
        """Marks each screen that waits for pairing that Home Assistant has found on the network (`seen`); the rest is
        not on the Wi-Fi (yet). Nothing is marked while Home Assistant cannot be asked."""
        if not payload.get('pending'):
            return payload
        try:
            names = await asyncio.wait_for(manager.ha.discovered_esphome(), 4)
        except Exception:  # noqa: BLE001 - the list is a help, never a reason for the inventory to fail
            return payload
        for entry in payload['pending']:
            entry['seen'] = str(entry.get('node') or '').lower() in names
            # This app adds it itself (app 0.4.73): `adding` while it does, `failed` when Home Assistant asked something
            # only the person can answer.
            entry['pairing'] = manager.pairing.state.get(entry.get('node'))
        return payload
    async def inventory(request):
        if request.query.get('light') == '1':
            # The page polls the light form; entities, backgrounds and icons (~100 KB) only on demand.
            return web.json_response(await seen_pending(light_payload()))
        screens, entities = manager.inventory()
        payload = await seen_pending(light_payload(screens))
        # A screen whose taps Home Assistant ignores because it may not perform actions (app 0.4.63): the editor says how
        # to allow them.
        blocked = await manager.ha.actions_blocked() if hasattr(manager.ha, 'actions_blocked') else set()
        for screen in payload['screens']:
            if screen.get('device_id') in blocked:
                screen['actions_blocked'] = True
        payload['entities'] = entities
        # The device trackers a map card can show beside its person (app 0.4.35): no tiles of their own.
        payload['trackers'] = map_card.trackers(manager.ha.states)
        # Labels and help in the editor's language (app 0.2.90); ids and keys stay as they are.
        payload['backgrounds'] = backgrounds()
        payload['controls'] = controls_catalogue()
        payload['icons'] = tile_icons.editor()
        payload['alerts'] = alert_reference()
        # The doorbell's event, and the doorbells this Home Assistant has, for the wizard to offer first (docs/DOORBELL.md).
        payload['doorbell'] = {**doorbell.reference(), 'suggestions': doorbell.suggestions(manager.ha.states, manager.registry_index(), manager.device_entries)}
        # What's new for the Update badge: here only, not in every live update (app 0.2.78).
        payload['changelog'] = manager.updates.changelog
        payload['claude_skill'] = claude_skill.status(manager.skill_dir)
        payload['video'] = manager.video_status()
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
    async def import_document(request):
        """Validate an export into a draft; importing never saves or sends it."""
        if 'inbox' in request.match_info and manager.screen(request.match_info['inbox']) is None:
            raise LayoutError(t('addon.errors.not_paired'))
        data = await request.json()
        if not isinstance(data, dict) or set(data) != {'document', 'sourceGrid'}:
            raise LayoutError(t('addon.errors.layout.invalid'))
        source = data['document']
        if not isinstance(source, dict): raise LayoutError(t('addon.errors.layout.invalid'))
        if source.get('esp_screens_layout') == 2:
            if set(source) - {'esp_screens_layout', 'sourceGrid', 'layout', 'editor'}:
                raise LayoutError(t('addon.errors.layout.invalid'))
            grid = grid_of_record(source)
            record = {'format': PAGE_FORMAT, 'sourceGrid': source['sourceGrid'],
                      'layout': validate_document(source.get('layout'), grid), 'revision': ''}
            if 'editor' in source:
                editor = source['editor']
                if not isinstance(editor, dict) or set(editor) != {'positions'}:
                    raise LayoutError(t('addon.errors.pages.workspace_refs'))
                record['workspace'] = LayoutStore._workspace({'revision': '', 'positions': editor['positions']},
                                                              {page['id'] for page in record['layout']['pages']})
        else:
            if source.get('esp_screens_layout', 1) != 1: raise LayoutError(t('addon.errors.layout.invalid'))
            # Old exports omitted their source grid. The editor asks the user
            # to confirm it explicitly before crossing this migration boundary.
            grid = grid_of_record({'sourceGrid': data['sourceGrid']})
            record = {**migrate_legacy({key: value for key, value in source.items() if key != 'esp_screens_layout'}, grid), 'revision': ''}
        return web.json_response(record)

    async def start_fresh(request):
        data = await request.json()
        if not isinstance(data, dict) or set(data) != {'revision'}:
            raise LayoutError(t('addon.errors.pages.fields'))
        inbox = manager.aliases.get(request.match_info['inbox'], request.match_info['inbox'])
        screen = manager.screen(inbox)
        if not screen: raise LayoutError(t('addon.errors.pages.source_grid'))
        record = manager.store.start_fresh(inbox, data['revision'], screen_t('screen.status.home'))
        manager.ha.changed.set()
        manager.notify()
        return web.json_response(record)

    async def dismiss_migration(request):
        data = await request.json()
        if not isinstance(data, dict) or set(data) != {'revision'}:
            raise LayoutError(t('addon.errors.pages.fields'))
        inbox = manager.aliases.get(request.match_info['inbox'], request.match_info['inbox'])
        record = manager.store.dismiss_migration(inbox, data['revision'])
        manager.notify()
        return web.json_response(record)

    async def save_workspace(request):
        data = await request.json()
        if not isinstance(data, dict) or set(data) != {'revision', 'workspace'}:
            raise LayoutError(t('addon.errors.pages.workspace_refs'))
        inbox = manager.aliases.get(request.match_info['inbox'], request.match_info['inbox'])
        workspace = manager.store.save_workspace(inbox, data['revision'], data['workspace'])
        manager.notify()
        return web.json_response(workspace)
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
                    # A ping the page hears (a comment it would not), so it knows a stream gone silent is dead
                    # (web/src/stores/inventory.ts SILENT_MS); an older page's onmessage never sees it.
                    await response.write(b'event: ping\ndata: {}\n\n')
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            manager.listeners.discard(wake)
        return response
    async def save(request):
        data = await request.json()
        inbox = manager.aliases.get(request.match_info['inbox'], request.match_info['inbox'])
        if manager.screen(inbox) is None: raise LayoutError(t('addon.errors.not_paired'))
        if not isinstance(data, dict) or data.get('format') != PAGE_FORMAT:
            raise LayoutError(t('addon.errors.editor_reload'))
        await manager.check_supported(request.match_info['inbox'], data)
        record = manager.save(request.match_info['inbox'], data)
        return web.json_response({'saved': True, **({'document': record} if record else {})})
    async def allow_actions(request):
        """Let a screen perform Home Assistant actions (app 0.4.73), the editor's notice for a screen whose taps Home
        Assistant ignored."""
        return web.json_response(await manager.allow_actions(request.match_info['inbox']))
    async def remove_screen(request):
        """Remove a screen for good (app 0.2.112): out of Home Assistant, out of the ESPHome folder and out of
        this app. Everything the sidebar's own warning names before it asks."""
        return web.json_response(await manager.remove_screen(request.match_info['inbox']))
    async def rename_screen(request):
        """Give a screen its own name in this app (app 0.4.2); an empty one gives Home Assistant's back."""
        data = await request.json()
        screen = manager.screen(request.match_info['inbox'])
        if screen is None or not screen.get('device_id'):
            raise ValueError(t('addon.errors.not_paired'))
        if not isinstance(data, dict) or not isinstance(data.get('name'), str):
            raise ValueError(t('addon.errors.pages.fields'))
        label = manager.labels.set(screen['device_id'], data['name'])
        manager.notify()
        return web.json_response({'name': label or screen['name']})
    async def browse_photos(request):
        """One level of Home Assistant's media sources for the photos step's folder (app 0.4.89): the folders in it and
        how many photos it holds right there."""
        content_id = request.query.get('id', '')
        if content_id and not screen_saver.MEDIA_SOURCE.fullmatch(content_id):
            return web.json_response({'error': t('addon.errors.pages.fields')}, status=400)
        try:
            return web.json_response(await manager.photos.browse(content_id))
        except Exception as error:  # noqa: BLE001 - Home Assistant could not browse it
            LOG.info('Photos folder cannot be browsed (%s)', type(error).__name__)
            return web.json_response({'id': content_id, 'title': '', 'folders': [], 'photos': 0, 'failed': True})

    async def change_screensaver(request):
        """The screensaver of one screen (app 0.4.48): the whole choice at once; the screen hears of it on the next pass."""
        data = await request.json()
        screen = manager.screen(request.match_info['inbox'])
        if screen is None or not screen.get('device_id'):
            raise ValueError(t('addon.errors.not_paired'))
        try:
            choice = manager.savers.set(screen['device_id'], data.get('screensaver') if isinstance(data, dict) else None)
        except ValueError as error:
            raise ValueError(t('addon.errors.pages.fields')) from error
        manager.ha.changed.set()
        manager.notify()
        return web.json_response({'screensaver': choice})
    async def capabilities(request):
        """What Home Assistant says each entity can do, for the tile settings (app 0.2.67). Unknown is null: the editor
        then offers what it always offered."""
        entities = list(dict.fromkeys(request.query.getall('entity', [])))[:40]
        lookup = getattr(manager.ha, 'capabilities', None)
        async def one(entity):
            try:
                found = await lookup(entity) if lookup else None
                # What a control needs of the entity's device (a vacuum's map, its routines) the app finds there itself.
                if isinstance(found, dict) and isinstance(found.get('controls'), list):
                    domain = entity.split('.', 1)[0]
                    found['controls'] = [key for key in found['controls'] if catalogue.device_holds(domain, key, entity, manager.device_has)]
                return found
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
    async def light_choices(request):
        """A light's presets (docs/LIGHT_PRESETS.md): the effects and the settings of its device (light_effects.choices)
        a preset may set, with every choice of each."""
        entity = request.query.get('entity', '')
        if not entity.startswith('light.') or entity not in manager.ha.states:
            return web.json_response({'effects': [], 'rows': []})
        return web.json_response(light_effects.choices(entity, manager.device_entries(entity), manager.ha.states, manager.registry_index(),
                                                       getattr(manager.ha, 'state_words', None), manager.device_name_of(entity)))
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
    async def display_precision(request):
        """A sensor's display precision (Home Assistant's entity setting, app dev): GET reads it, PUT {entity, precision}
        sets it in Home Assistant, precision 0-6 or null for Default. The value on every tile, meter and top bar item of
        the sensor follows Home Assistant's setting, as on its own dashboards."""
        data = await request.json() if request.method == 'PUT' else dict(request.query)
        entity = data.get('entity', '') if isinstance(data, dict) else ''
        ha = manager.ha
        if not entity_id(entity) or not entity.startswith('sensor.') or not hasattr(ha, 'display_precision'):
            raise ValueError(t('addon.errors.layout.invalid_setting', setting='entity'))
        # Home Assistant's dialog labels each choice with the state as it is now, unrounded: it travels with the answer.
        now = lambda answer: {**answer, 'state': (ha.states.get(entity) or {}).get('state')}
        if request.method == 'GET':
            return web.json_response(now(ha.display_precision(entity)))
        precision = data.get('precision')
        if precision is not None and (type(precision) is not int or not 0 <= precision <= 6):
            raise ValueError(t('addon.errors.layout.invalid_setting', setting='precision'))
        if not ha.display_precision(entity)['editable']:
            raise ValueError(t('addon.errors.display_precision_unregistered'))
        return web.json_response(now(await ha.set_display_precision(entity, precision)))
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
        return web.json_response(manager.updates.start(request.match_info['inbox'], data.get('host'), data.get('reinstall') is True))
    async def update_all(request):
        # `reinstall`: Reinstall all from dev, every screen again with the newest dev (dev channel only).
        data = await request.json() if request.can_read_body else {}
        return web.json_response({'started': manager.updates.start_all(isinstance(data, dict) and data.get('reinstall') is True)})
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
                      'options':t.get('options',{}),
                      # Which tile: an entity may be on several (firmware 0.16.0+); a key has no slot, its place instead.
                      'slot':t.get('slot',-1),**({'in':t['in'],'key':t['key']} if is_key(t) else {})} for i,t in enumerate(layout['tiles'])]})
    preview_history_slots = asyncio.Semaphore(3)
    async def preview_history(request):
        """Read-only recorder data, sharing the screen detail-card cache."""
        entity = request.query.get('entity', '')
        try: hours = int(request.query.get('hours', '24'))
        except ValueError: hours = 0
        if (entity not in manager.ha.states or not entity.startswith('sensor.') or
                hours not in history_card.RANGES or history_card.kind(entity, manager.ha.states[entity]) != 'line'):
            return web.json_response({'history': None})
        async with preview_history_slots:
            return web.json_response({'history': await manager.card_history(entity, hours, 'line')})

    async def media_art_preview(request):
        # The browser receives only prepared pixels, never HA tokens or source URLs.
        entity = request.query.get('entity', '')
        if not picture_question.valid_entity(entity, picture_question.COVER_DOMAINS) or entity not in manager.ha.states:
            raise web.HTTPNotFound()
        result = await manager.preview_picture(picture_question.Source('cover', entity))
        if result is None:
            raise web.HTTPNotFound()
        tag, body = result
        headers = {'ETag': tag, 'Cache-Control': 'private, max-age=30'}
        if request.headers.get('If-None-Match') == tag:
            return web.Response(status=304, headers=headers)
        return web.Response(body=body, content_type='image/bmp', headers=headers)

    async def media_browse(request):
        """A folder of a player's library for the editor's favourite (app 0.4.42): the top (no folder) or a folder by the
        number it was given; each item with what a favourite stores of it and a link to its prepared picture."""
        entity = request.query.get('entity', '')
        if not entity.startswith('media_player.') or entity not in manager.ha.states:
            raise web.HTTPNotFound()
        shelf = manager.shelves.setdefault('', media_library.Shelf())
        token = manager.media_token(request.query.get('folder') or 0)
        item = shelf.get(entity, token) if token else None
        if token and (item is None or not item['expand']):
            raise web.HTTPNotFound()
        try:
            folder = await manager.read_folder(entity, item)
        except (ClientError, ConnectionError, TimeoutError, OSError, ValueError) as error:
            name = manager.ha.states.get(entity, {}).get('attributes', {}).get('friendly_name') or entity
            return web.json_response({'error': t('addon.errors.media.browse', name=name), 'detail': type(error).__name__}, status=502)
        items = []
        for raw in folder['items']:
            number = shelf.token(entity, raw)
            items.append({'item': number, 'title': raw['title'], 'play': raw['play'], 'expand': raw['expand'], 'icon': raw['icon'],
                          'picture': f'api/media/picture?entity={entity}&item={number}' if raw['thumb'] else None,
                          'favorite': media_library.favorite_of(raw) if raw['play'] else None})
        answer = {'title': folder['title'], 'folder': token or 0, 'items': items}
        # A player that plays a Spotify link (app 0.4.84): the editor offers a field for one, knowing no brand itself.
        if not token and await manager.spotify_route(entity, folder) is not None:
            answer['spotify_link'] = True
        return web.json_response(answer)

    async def media_link(request):
        """A Spotify link or URI as one item of the library (app 0.4.84), in the shape media_browse gives an item: its
        title and picture from Spotify's oEmbed, its id and type as Home Assistant's media browser sends them for this
        player."""
        entity = request.query.get('entity', '')
        if not entity.startswith('media_player.') or entity not in manager.ha.states:
            raise web.HTTPNotFound()
        text = request.query.get('link', '')
        if media_library.spotify_short(text):
            return web.json_response({'error': t('addon.errors.media.link_short')}, status=400)
        found = media_library.spotify_link(text)
        if not found:
            return web.json_response({'error': t('addon.errors.media.link_invalid')}, status=400)
        entry = await manager.spotify_route(entity)
        if entry is None:
            name = manager.ha.states.get(entity, {}).get('attributes', {}).get('friendly_name') or entity
            return web.json_response({'error': t('addon.errors.media.link_player', name=name)}, status=400)
        kind, spotify_id = found
        title, thumb = await manager.spotify_card(kind, spotify_id)
        raw = media_library.spotify_item(kind, spotify_id, entry or None, title or t(f'addon.screen.media.{media_library.SPOTIFY_KINDS[kind]}'), thumb)
        number = manager.shelves.setdefault('', media_library.Shelf()).token(entity, raw)
        return web.json_response({'item': number, 'title': raw['title'], 'play': True, 'expand': False, 'icon': raw['icon'],
                                  'picture': f'api/media/picture?entity={entity}&item={number}' if raw['thumb'] else None,
                                  'favorite': media_library.favorite_of(raw)})

    async def media_picture(request):
        """An item's picture for the editor, prepared: an item of the library it browsed, or what a saved favourite
        plays. Never an address of the browser's choosing."""
        entity = request.query.get('entity', '')
        url = None
        token = manager.media_token(request.query.get('item'))
        if token:
            url = (manager.shelves.get('', media_library.Shelf()).get(entity, token) or {}).get('thumb')
        elif request.query.get('url'):
            wanted = request.query['url']
            saved = {((tile.get('options') or {}).get('play') or {}).get('thumb') for layout in manager.layouts.values()
                     for tile in layout.get('tiles', []) if tile['entity'] == entity}
            url = wanted if wanted in saved else None
        if not url:
            raise web.HTTPNotFound()
        if url not in manager.thumbnails:
            try:
                manager.thumbnails[url] = await manager.ha.browse_image(entity, url)
            except Exception:
                raise web.HTTPNotFound() from None
            while len(manager.thumbnails) > 96:
                manager.thumbnails.popitem(last=False)
        body = await asyncio.get_running_loop().run_in_executor(None, media_library.preview_jpeg, manager.thumbnails[url])
        return web.Response(body=body, content_type='image/jpeg', headers={'Cache-Control': 'private, max-age=3600'})

    async def camera_preview(request):
        # A camera that fills a taller card on the mockup (app 0.3.8): prepared pixels only, as for a cover.
        entity = request.query.get('entity', '')
        if not picture_question.valid_entity(entity, picture_question.CAMERA_DOMAINS) or entity not in manager.ha.states:
            raise web.HTTPNotFound()
        result = await manager.preview_picture(picture_question.Source('camera', entity))
        if result is None:
            raise web.HTTPNotFound()
        tag, body = result
        headers = {'ETag': tag, 'Cache-Control': 'private, max-age=30'}
        if request.headers.get('If-None-Match') == tag:
            return web.Response(status=304, headers=headers)
        return web.Response(body=body, content_type='image/bmp', headers=headers)

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
                                    precision=header_bar.precision_of(entry) if eid.startswith('sensor.') else None,
                                    units=getattr(manager.ha, 'units', None))
            attributes = dict(message['a'])
            # A light group's lamps (light_groups.lamp_ids): the editor reads its presets lamp by lamp, as the screen does.
            if eid.startswith('light.'):
                members = light_groups.lamp_ids(eid, manager.ha.states)
                if members:
                    attributes['entity_id'] = list(members)
            if eid.startswith('media_player.'):
                # What the player reported at its widest (GitHub #88): the editor draws a player at rest with its keys.
                attributes['supported_features'] = manager.players.widest(eid, state.get('attributes'))
                # The speakers a favourite may play on (app 0.4.42).
                sources = state.get('attributes', {}).get('source_list')
                if isinstance(sources, list):
                    attributes['source_list'] = [str(s) for s in sources if isinstance(s, str)][:media_library.SOURCES]
                # The speakers of its menu (speakers.py): what a favourite may play on, a Sonos for Spotify included.
                attributes['speakers'] = [row['name'] for row in manager.speaker_menu(eid)['rows']]
                for key in ('media_title', 'media_artist', 'media_album_name', 'media_duration', 'media_position'):
                    value = state.get('attributes', {}).get(key)
                    if isinstance(value, (str, int, float)):
                        attributes[key] = value
                attributes['artwork_mark'] = (media_extras(state.get('attributes', {})) or {}).get('pic', '')
            if eid.startswith('automation.') and isinstance(state.get('attributes', {}).get('current'), int):
                # How many runs go on right now: a tile set to run its actions is coloured while they do.
                attributes['current'] = state['attributes']['current']
            # A duration in hours and minutes as the screens write it (durations.py), else Home Assistant's word.
            word = (durations.text(message['state'], (state.get('attributes') or {}).get('unit_of_measurement'), i18n.screen_language())
                    if eid.startswith('sensor.') and durations.is_duration(state.get('attributes')) else None)
            result[eid] = {'state': message['state'], 'a': attributes,
                           'word': word or state_word(eid, state.get('state'), state.get('attributes'), entry, getattr(manager.ha, 'state_words', None)),
                           # A tile's second line set to one of its values, written as the screen gets it (ha_catalogue).
                           'sub': ha_catalogue.subtitle_lines(eid, state, getattr(manager.ha, 'units', None), entry,
                                                              getattr(manager.ha, 'state_words', None))}
        return web.json_response({'states': result})
    async def firmware_preview(request):
        """The device's normal packets, for an unsaved layout. No device registration or HA actions."""
        from core import Grid, PREVIEW_CEILINGS
        data = await request.json()
        if not isinstance(data, dict) or not isinstance(data.get('shape'), dict):
            raise ValueError('A preview shape is required.')
        shape = data['shape']
        columns, rows = shape.get('columns'), shape.get('rows')
        if any(type(n) is not int or n < 1 or n > 8 for n in (columns, rows)) or columns * rows > 64:
            raise ValueError('Invalid preview grid.')
        record = {'format': PAGE_FORMAT, 'sourceGrid': {'columns': columns, 'rows': rows},
                  'layout': validate_document(data.get('layout'), Grid(columns, rows, *PREVIEW_CEILINGS))}
        tiles = compile_tiles(record['layout'], grid_of_record(record))
        # The map tiles of the page on the mockup are drawn from these (preview_images), as a screen's from its saved ones.
        manager.preview_tiles = tiles
        # A template tile of the preview is rendered now, not at the sync loop's next pass.
        if any(tile.get('entity') == text_tile.TEXT_TILE for tile in tiles):
            await manager.sync_templates()
        values = [await manager.tile_message(index, tile, lamps=True) for index, tile in enumerate(tiles)]
        bars = [manager.header_message({'header': {'items': bar_items(page)}})['items']
                for page in record['layout']['pages']]
        region = manager.page_region()
        begin, initial_tiles, initial_bars, states = page_delivery.prepare('', record, region, values, bars)
        revision = page_delivery.configuration(record, region)
        manager.preview_layouts[revision] = tiles
        manager.preview_layouts.move_to_end(revision)
        while len(manager.preview_layouts) > preview_images.LAYOUTS:
            manager.preview_layouts.popitem(last=False)
        return web.json_response({'revision': revision,
            'configuration': [begin, *initial_bars, *initial_tiles, {'op': 'commit'}],
            'values': [*states, *[page_delivery.page_message(page, index, items, initial=False)
                for index, (page, items) in enumerate(zip(record['layout']['pages'], bars))]]})

    async def firmware_preview_image(request):
        return web.json_response(await preview_images.answer(manager, await request.json()))

    async def firmware_preview_events(request):
        return await preview_events.stream(manager.ha.state_events, request)

    async def firmware_preview_pixels(request):
        status, body, tag, kind = await manager.links.serve(request.match_info['token'])
        return web.Response(status=status, body=body, content_type=kind or 'image/bmp',
                            headers={'Cache-Control': 'no-store', **({'ETag': tag} if tag else {})})

    async def firmware_preview_action(request):
        """Relay the firmware's ESPHome service request through this manager's HA connection."""
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError('A firmware command is required.')
        service, fields = data.get('service'), data.get('data')
        if not isinstance(service, str) or len(service) > 120 or not re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', service):
            raise ValueError('Invalid Home Assistant action.')
        if data.get('event') or data.get('templates'):
            raise ValueError('Preview event requests and templated actions are not supported yet.')
        if not isinstance(fields, dict) or len(fields) > 32 or any(
                not isinstance(k, str) or not re.fullmatch(r'[a-z0-9_]{1,64}', k) or
                not isinstance(v, str) or len(v) > 4096 for k, v in fields.items()):
            raise ValueError('Invalid Home Assistant action data.')
        target = fields.get('entity_id')
        if not entity_id(target) or target not in manager.ha.states:
            raise ValueError('The command must target an existing Home Assistant entity.')
        # Keep this endpoint scoped to entity controls, not arbitrary HA administration.
        actions = await manager.ha.entity_actions(target)
        if actions is None:
            raise ConnectionError('Home Assistant actions are not available yet.')
        if service not in actions:
            raise ValueError('Home Assistant does not offer this action for that entity.')
        await asyncio.wait_for(manager.ha.call(service, fields), timeout=5)
        return web.json_response({'success': True})

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
    async def test_doorbell(request):
        """Events, Doorbell, Try it: one ring to one screen or to every screen, as esp_screens_doorbell sends it."""
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError(t('addon.errors.alerts.invalid'))
        # The wizard's own fields as the automation it builds would send them, its screens by name too.
        data = dict(body.get('data')) if isinstance(body.get('data'), dict) else {}
        if body.get('screen') not in (None, '', 'all'):
            screen = manager.screen(str(body.get('screen')))
            if screen is None or not screen.get('node'):
                raise ValueError(t('addon.errors.unknown_screen'))
            data['screen'] = screen['node']
        return web.json_response(await manager.doorbell_show(data))
    async def list_automations(request):
        """Events: the automations this app put into Home Assistant (automations.py), for the wizard's list."""
        return web.json_response({'automations': automations.listed(manager.ha.states, request.query.get('kind') or None)})
    async def save_automation(request):
        """Events, Add to Home Assistant: the wizard's automation into Home Assistant, a new one or one of ours again."""
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError(t('addon.errors.alerts.invalid'))
        kind = str(body.get('kind', ''))
        automation_id = body.get('id') or automations.new_id(kind)
        if automations.kind_of(automation_id) != kind:
            raise ValueError(t('addon.errors.automations.not_ours'))
        try:
            config = automations.checked(kind, body.get('config'))
        except ValueError as error:
            raise ValueError(t('addon.errors.automations.invalid', part=str(error))) from None
        await manager.ha.save_automation(automation_id, config)
        LOG.info('Events: automation %s saved in Home Assistant (%s)', automation_id, config['alias'])
        return web.json_response({'id': automation_id, 'path': f'/config/automation/edit/{automation_id}'})
    async def delete_automation(request):
        """Events: remove one of the automations this app put into Home Assistant, never another."""
        automation_id = request.match_info['id']
        if not automations.kind_of(automation_id):
            raise ValueError(t('addon.errors.automations.not_ours'))
        await manager.ha.delete_automation(automation_id)
        LOG.info('Events: automation %s removed from Home Assistant', automation_id)
        return web.json_response({'removed': automation_id})
    async def install_claude_skill(request):
        """Settings → Claude → Install: writes the skill into Home Assistant's configuration folder, only on request."""
        return web.json_response(claude_skill.install(manager.skill_dir))
    async def install_video(request):
        """Settings, Video in Home Assistant, Install: writes tessera_video into Home Assistant's configuration folder,
        only on request. Home Assistant loads it at its next start (restart_for_video)."""
        return web.json_response({**screen_video.install(manager.videos.directory), **{
            k: v for k, v in manager.video_status().items() if k in ('loaded', 'screens', 'entries')}})
    async def restart_for_video(request):
        """Settings, Video in Home Assistant, Restart Home Assistant: as its own Restart does (homeassistant.restart,
        which checks the configuration first and refuses to restart a broken one)."""
        if not screen_video.status(manager.videos.directory)['installed']:
            raise web.HTTPConflict(text=t('addon.errors.video.not_installed'))
        try:
            await manager.ha.call_service('homeassistant', 'restart', {})
        except (ConnectionError, TimeoutError, ClientError):
            pass    # Home Assistant may close the connection before it answers: it is restarting
        LOG.info('Home Assistant restarts to load Tessera video')
        return web.json_response({'restarting': True})
    async def download_claude_skill(request):
        """Settings → Claude → Download: the same skill as a zip for claude.ai; writes nothing."""
        return web.Response(body=claude_skill.archive(), content_type='application/zip',
                            headers={'Content-Disposition': f'attachment; filename="{claude_skill.NAME}.zip"'})
    async def firmware_status(request):
        # New screen asks what is taken while the name is typed, so a clash is said before anything is written. The build
        # line itself goes with the live inventory (`line`); this answer has ESPHome's job and the log of what runs now.
        status = manager.firmware.status()
        # A profile of a paired screen carries the address its Update goes to (updates.resolve: the screen's IP address,
        # else the one kept from before), so Firmware & USB fills it in; none when two screens claim the profile.
        profiles, addresses = manager.firmware.profile_names(), {}
        for screen in manager.screens():
            profile, host = manager.updates.resolve(screen, profiles)
            if profile:
                addresses.setdefault(profile, []).append(host)
        for profile in status['profiles']:
            matches = addresses.get(profile['file'], [])
            if len(matches) == 1 and matches[0]:
                profile['host'] = matches[0]
        return web.json_response({**status, 'taken': manager.taken_names()})
    async def firmware_start(request):
        """Firmware & USB and the YAML check: one ESPHome action, which waits its turn in the build line. The answer is
        that build (BuildQueue.view), followed by its `id` in the firmware answer's `builds`."""
        data = await request.json()
        manager.preflight_profile(data)
        return web.json_response(manager.build_queue.view(manager.build_queue.attended(data)))
    async def firmware_build_log(request):
        """The log of one build of the line, also after the next one started (BuildQueue.log)."""
        try:
            number = int(request.match_info['build'])
        except ValueError:
            raise ValueError(t('addon.errors.firmware.build_gone')) from None
        return web.json_response(manager.build_queue.log(number))
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
    async def firmware_wifi(request):
        """New screen → Wi-Fi: another network or password in ESPHome's secrets.yaml (app 0.4.32), for a screen that did
        not come online. Every screen builds with these two lines, so each takes them at its next update."""
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError(t('addon.errors.firmware.wifi_needed'))
        manager.firmware.change_wifi(data)
        return web.json_response(manager.firmware.wifi_status())
    async def firmware_download(request):
        """New screen and Firmware & USB → Download: the factory image this app just built, for ESPHome Web on
        the owner's own computer. Like the profile it came from, it holds the Wi-Fi password and the screen's keys."""
        path, name = manager.firmware.image(request.match_info['file'])
        return web.FileResponse(path, headers={'Content-Type': 'application/octet-stream',
                                               'Content-Disposition': f'attachment; filename="{name}"'})
    async def firmware_files(request):
        """A screen's menu → Download screen files: its YAML, Override YAML and the secrets they use, as a zip, to
        build the screen with ESPHome on your own computer."""
        body, name = manager.firmware.files(request.match_info['file'])
        return web.Response(body=body, content_type='application/zip', headers={'Content-Disposition': f'attachment; filename="{name}"'})
    async def firmware_forget(request):
        """A screen that never got its firmware (GitHub #114, app 0.4.32): New screen wrote its profile, the build was
        cancelled or failed, and the sidebar kept it waiting. Only such a profile goes, one no paired screen builds from;
        a paired screen leaves through its own Remove, which takes it out of Home Assistant too."""
        file = request.match_info['file']
        waiting = {p['file'] for p in manager.pending_profiles(manager.screens(), manager.firmware.profile_names())}
        if file not in waiting:
            raise LayoutError(t('addon.errors.firmware.profile_missing'))
        return web.json_response({'removed': await manager.firmware.delete_profile(file)})
    async def firmware_flashed(request):
        """New screen and Firmware & USB → This computer (browser): the page wrote the image it downloaded onto a
        screen over Web Serial, so the screen list nudges pairing as for one flashed from Home Assistant's own USB port."""
        return web.json_response(manager.firmware.flashed(request.match_info['file']))
    # The answers that are still waiting after a restart try again (feedback.py); a request never runs past shutdown.
    FEEDBACK_ERRORS = {'outcome': 'addon.errors.feedback.invalid', 'issues': 'addon.errors.feedback.invalid',
                       'comment': 'addon.errors.feedback.comment', 'board': 'addon.errors.feedback.unknown_board',
                       'deleting': 'addon.errors.feedback.deleting', 'storage': 'addon.errors.feedback.storage',
                       'revision': 'addon.errors.feedback.invalid', 'action': 'addon.errors.invalid_input'}
    async def feedback_start(app):
        manager.feedback.start()
        manager.reports.watch()
    app.on_startup.append(feedback_start)
    # ---- My screen doesn't work right (reports.py, app 0.4.91) ----
    def report_screen(request):
        screen = manager.screen(request.match_info['inbox'])
        if screen is None:
            raise ValueError(t('addon.errors.unknown_screen'))
        return screen
    async def report_status(request):
        screen = report_screen(request)
        return web.json_response(manager.reports.status(screen['id'], screen))
    async def report_start(request):
        screen = report_screen(request)
        data = await request.json()
        depth = data.get('depth', 'basic') if isinstance(data, dict) else 'basic'
        return web.json_response({'id': manager.reports.start(screen['id'], screen, depth)}, status=202)
    async def report_view(request):
        return web.json_response(manager.reports.get(request.match_info['id']).view())
    async def report_file(request):
        text = manager.reports.file(request.match_info['id'], request.match_info['name'])
        return web.Response(text=text, content_type='text/plain', charset='utf-8', headers={'Cache-Control': 'no-store'})
    async def report_zip(request):
        id = request.match_info['id']
        return web.Response(body=manager.reports.zip_bytes(id), content_type='application/zip',
                            headers={'Content-Disposition': f'attachment; filename="{manager.reports.filename(id)}"', 'Cache-Control': 'no-store'})
    async def report_send(request):
        report = manager.reports.get(request.match_info['id'])
        screen = manager.screen(report.inbox)
        if screen is None:
            raise ValueError(t('addon.errors.unknown_screen'))
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError(t('addon.errors.invalid_input'))
        try:
            result = await manager.reports.send(report.id, data.get('consent'), data.get('note'), data.get('email'),
                                                data.get('remember_email') is True, screen)
        except ValueError as error:
            if str(error) in ('note', 'email'):
                raise ValueError(t(f'addon.errors.report.{error}')) from None
            raise
        return web.json_response(result)
    async def report_delete(request):
        manager.reports.delete(request.match_info['id'])
        return web.Response(status=204)
    app.router.add_get('/api/screens/{inbox}/report', report_status)
    app.router.add_post('/api/screens/{inbox}/report', report_start)
    app.router.add_get('/api/reports/{id}.zip', report_zip)
    app.router.add_get('/api/reports/{id}', report_view)
    app.router.add_get('/api/reports/{id}/files/{name}', report_file)
    app.router.add_post('/api/reports/{id}/send', report_send)
    app.router.add_delete('/api/reports/{id}', report_delete)
    async def feedback_action(request):
        """The owner's choice on the feedback card: answer, later, never, cancel, retry or delete. The page names the
        screen; the key, the revision and the model are this app's own, for a screen paired with this Home Assistant."""
        screen = manager.screen(request.match_info['inbox'])
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError(t('addon.errors.invalid_input'))
        board, device = manager.feedback_board(screen, manager.firmware.profile_names()), screen.get('device_id')
        if not board or not device:
            raise ValueError(t('addon.errors.feedback.unknown_board'))
        action, store = data.get('action'), manager.feedback
        try:
            if store.readonly:
                raise ValueError('storage')
            if action == 'answer':
                await store.answer(device, board, data.get('outcome'), data.get('issues'), data.get('comment'),
                                   manager.feedback_versions(screen))
            elif action == 'later':
                store.later(device)
            elif action == 'never':
                store.never(device)
            elif action == 'cancel':
                await store.cancel(device)
            elif action == 'retry':
                await store.retry(device)
            elif action == 'delete':
                await store.delete(device)
            else:
                raise ValueError('action')
        except ValueError as error:
            raise ValueError(t(FEEDBACK_ERRORS.get(str(error), 'addon.errors.invalid_input'))) from None
        return web.json_response({'feedback': store.view(device)})
    # ---- The build server (build_server.py, docs/BUILDS.md "On a build server") ----
    def build_server_refused(error):
        return ValueError(t(f'addon.errors.build_server.{error.args[0]}'))
    async def build_server_start(app):
        manager.build_server.start()
    app.on_startup.append(build_server_start)
    async def build_server_view(request):
        return web.json_response(manager.build_server.view())
    async def build_server_preview(request):
        """The server at an address: its name, its ESPHome and its fingerprint, for the person to compare."""
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError(t('addon.errors.invalid_input'))
        try:
            return web.json_response(await manager.build_server.preview(data.get('host'), data.get('port')))
        except build_server.Refused as error:
            raise build_server_refused(error) from None
    async def build_server_pair(request):
        """Ask the previewed server to let this app in, with the one-time key a headless server prints."""
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError(t('addon.errors.invalid_input'))
        try:
            return web.json_response(await manager.build_server.pair(data.get('host'), data.get('port'), data.get('key')))
        except build_server.Refused as error:
            raise build_server_refused(error) from None
    async def build_server_change(request):
        """On or off: whether builds go to the server first."""
        data = await request.json()
        if not isinstance(data, dict) or not isinstance(data.get('enabled'), bool):
            raise ValueError(t('addon.errors.invalid_input'))
        try:
            return web.json_response(manager.build_server.set_enabled(data['enabled']))
        except build_server.Refused as error:
            raise build_server_refused(error) from None
    async def build_server_forget(request):
        return web.json_response(await manager.build_server.forget())
    app.router.add_get('/api/build-server', build_server_view)
    app.router.add_post('/api/build-server/preview', build_server_preview)
    app.router.add_post('/api/build-server/pair', build_server_pair)
    app.router.add_put('/api/build-server', build_server_change)
    app.router.add_delete('/api/build-server', build_server_forget)
    async def shutdown(app):
        await manager.build_server.stop()
        await manager.build_queue.close()
        task = manager.firmware.task
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError): await task
        await manager.feedback.close()
        await manager.reports.close()
    app.on_cleanup.append(shutdown)
    app.router.add_get('/api/screens/{inbox}/inspect', inspector)
    app.router.add_post('/api/screens/{inbox}/update', update_screen)
    app.router.add_post('/api/updates/run', update_all)
    app.router.add_put('/api/updates', update_settings)
    app.router.add_put('/api/language', change_language)
    app.router.add_get('/api/firmware', firmware_status)
    app.router.add_post('/api/firmware/jobs', firmware_start)
    app.router.add_get('/api/firmware/builds/{build}/log', firmware_build_log)
    app.router.add_get('/api/firmware/profiles/{file}/override', firmware_override)
    app.router.add_put('/api/firmware/profiles/{file}/override', firmware_override_save)
    app.router.add_get('/api/firmware/profiles/{file}/download', firmware_download)
    app.router.add_get('/api/firmware/profiles/{file}/files', firmware_files)
    app.router.add_post('/api/firmware/profiles/{file}/flashed', firmware_flashed)
    app.router.add_delete('/api/firmware/profiles/{file}', firmware_forget)
    app.router.add_post('/api/firmware/profiles', firmware_create)
    app.router.add_put('/api/firmware/wifi', firmware_wifi)
    # Plugins (docs/PLUGINS.md): only where they are on (core.plugins_enabled), so an app without them has none of these routes.
    if editor_features['plugins']:
        async def plugins_list(request):
            await manager.plugins.refresh_index(force=request.query.get('refresh') == '1')
            await manager.plugins.refresh_links(force=request.query.get('refresh') == '1')
            await manager.plugins.refresh_likes()
            return web.json_response(manager.plugins.payload(REQUEST_LANGUAGE.get()))

        async def plugins_apply(request):
            result = await manager.plugins.apply(request.match_info['inbox'], await request.json())
            manager.notify()
            return web.json_response(result)

        async def plugins_file(request):
            return web.json_response(manager.plugins.file_for(request.match_info['inbox']))

        async def plugins_secret(request):
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError(t('addon.errors.plugins.request'))
            return web.json_response(manager.plugins.set_secret(request.match_info['plugin'], request.match_info['input'],
                                                                data.get('value')))

        # The tile's options as they are kept (plugin API 0.12: typed, a list as a list), in a body so no type is lost on
        # the way; `screen`: the screen the inspector shows, whose own plugin of that id answers; `search`: what the
        # person typed in a searched list.
        async def plugin_body(request):
            data = await request.json()
            if not isinstance(data, dict) or not isinstance(data.get('options', {}), dict):
                raise ValueError(t('addon.errors.plugins.request'))
            screen = data.get('screen')
            return data.get('options') or {}, screen if isinstance(screen, str) and screen else None, data

        async def plugins_choices(request):
            options, screen, data = await plugin_body(request)
            return web.json_response(await manager.plugins.choices(request.match_info['plugin'], request.match_info['fetch'],
                                                                   options, screen, data.get('search') or ''))

        async def plugins_plan(request):
            return web.json_response(manager.plugins.plan(request.match_info['inbox'], await request.json(),
                                                          REQUEST_LANGUAGE.get()))

        async def plugins_like(request):
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError(t('addon.errors.plugins.request'))
            return web.json_response(await manager.plugins.like(request.match_info['plugin'], data.get('like') is True,
                                                                data.get('consent') is True))

        app.router.add_get('/api/plugins', plugins_list)
        app.router.add_post('/api/screens/{inbox}/plugins', plugins_apply)
        app.router.add_get('/api/screens/{inbox}/plugins/file', plugins_file)
        app.router.add_put('/api/plugins/{plugin}/secrets/{input}', plugins_secret)
        app.router.add_post('/api/plugins/{plugin}/choices/{fetch}', plugins_choices)
        app.router.add_post('/api/screens/{inbox}/plugins/plan', plugins_plan)
        app.router.add_put('/api/plugins/{plugin}/like', plugins_like)

        # Stars for a plugin a screen runs, the stars card's Later and Never, and counting (plugin_likes.py).
        async def plugins_rate(request):
            data = await request.json()
            stars = data.get('stars') if isinstance(data, dict) else 'no'
            if not (stars is None or (isinstance(stars, int) and not isinstance(stars, bool) and 1 <= stars <= 5)):
                raise ValueError(t('addon.errors.plugins.request'))
            screen = data.get('screen') if isinstance(data.get('screen'), str) else None
            result = await manager.plugins.rate(request.match_info['plugin'], stars, screen)
            manager.notify()
            return web.json_response(result)

        async def plugins_ask(request):
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError(t('addon.errors.plugins.request'))
            result = manager.plugins.card_answer(request.match_info['plugin'], data.get('action'))
            manager.notify()
            return web.json_response({'likes': result})

        async def plugins_counting(request):
            data = await request.json()
            if not isinstance(data, dict) or not isinstance(data.get('on'), bool):
                raise ValueError(t('addon.errors.plugins.request'))
            result = await manager.plugins.set_counting(data['on'])
            manager.notify()
            return web.json_response({'likes': result})

        app.router.add_put('/api/plugins/{plugin}/rating', plugins_rate)
        app.router.add_post('/api/plugins/{plugin}/ask', plugins_ask)
        app.router.add_put('/api/plugins/counting', plugins_counting)

        async def plugins_counting_start(app):
            manager.plugins.counting_task = asyncio.create_task(manager.plugins.counting())

        async def plugins_counting_stop(app):
            task = getattr(manager.plugins, 'counting_task', None)
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        app.on_startup.append(plugins_counting_start)
        app.on_cleanup.append(plugins_counting_stop)

        async def plugins_preview(request):
            options, screen, data = await plugin_body(request)
            entity = data.get('entity') if isinstance(data.get('entity'), str) else None
            return web.json_response(await manager.plugins.preview(request.match_info['plugin'], request.match_info['tile'], options,
                                                                   screen, entity))
        app.router.add_post('/api/plugins/{plugin}/preview/{tile}', plugins_preview)

        async def plugins_image(request):
            # A plugin's picture for the Plugins page (store.png), served by the app: the editor shows no picture of
            # another address (its img-src is 'self').
            body = await manager.plugins.store_image(request.match_info['plugin'])
            if body is None:
                raise web.HTTPNotFound()
            return web.Response(body=body, content_type='image/png')
        app.router.add_get('/api/plugins/{plugin}/image', plugins_image)

        async def plugins_link(request):
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError(t('addon.errors.plugins.request'))
            entry = await manager.plugins.resolve_link(data.get('url'), data.get('branch'), data.get('folder'))
            return web.json_response(manager.plugins.editor_plugin(entry, REQUEST_LANGUAGE.get()))
        app.router.add_post('/api/plugins/link', plugins_link)

        async def plugins_forget(request):
            manager.plugins.forget_link(request.match_info['plugin'])
            return web.json_response({'ok': True})
        app.router.add_delete('/api/plugins/{plugin}/link', plugins_forget)

        async def plugins_settings(request):
            return web.json_response(manager.plugins.settings_for(request.match_info['inbox'], REQUEST_LANGUAGE.get()))

        async def plugins_settings_events(request):
            language = REQUEST_LANGUAGE.get()
            return await entity_settings.stream(manager, request,
                lambda: manager.plugins.settings_for(request.match_info['inbox'], language))

        async def plugins_setting(request):
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError(t('addon.errors.plugins.request'))
            result = await manager.plugins.set_setting(request.match_info['inbox'], data.get('entity'), data.get('value'))
            return web.json_response(result)
        app.router.add_get('/api/screens/{inbox}/plugins/settings', plugins_settings)
        app.router.add_get('/api/screens/{inbox}/plugins/settings/events', plugins_settings_events)
        app.router.add_post('/api/screens/{inbox}/plugins/settings', plugins_setting)
    # A board's extras under Screen settings (docs/SETTINGS.md, "A board's own settings"): for every screen, plugins or not.
    async def extras(request):
        return web.json_response(entity_settings.extras_for(manager, request.match_info['inbox'], REQUEST_LANGUAGE.get()))

    async def extras_events(request):
        language = REQUEST_LANGUAGE.get()
        return await entity_settings.stream(manager, request,
            lambda: entity_settings.extras_for(manager, request.match_info['inbox'], language))

    async def extra(request):
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError(t('addon.errors.extras.request'))
        return web.json_response(await entity_settings.set_extra(manager, request.match_info['inbox'], data.get('entity'),
                                                                 data.get('value')))
    async def calendar_preview(request):
        """A calendar card as the screen would get it, for the editor (firmware 0.56.0): its events after the tile's
        filters, every place its calendars' events name, most used first, for the place filter's choices, and the
        calendars that take new events (Home Assistant's CREATE_EVENT), which "Status and booking" can book on."""
        data = await request.json()
        tile = data.get('tile') if isinstance(data, dict) else None
        if not isinstance(tile, dict) or not str(tile.get('entity', '')).startswith('calendar.'):
            raise ValueError(t('addon.errors.invalid_input'))
        try:
            options = calendar_feed.validate(tile.get('options') or {})
        except ValueError:
            options = {}
        tile = {'entity': tile['entity'], 'options': options}
        card = await manager.calendar_extras(tile)
        every = await manager.calendar_extras({'entity': tile['entity'], 'options': {k: v for k, v in options.items() if k in ('calendars', 'ahead')}})
        places = Counter(row[5] for row in every['e'] if row[5])
        bookable = [entity for entity, state in manager.ha.states.items() if entity.startswith('calendar.') and
                    isinstance(((state or {}).get('attributes') or {}).get('supported_features'), int) and
                    state['attributes']['supported_features'] & calendar_feed.CREATE_EVENT]
        return web.json_response({'cal': card, 'places': [place for place, _ in places.most_common(24)], 'bookable': sorted(bookable)})
    app.router.add_post('/api/calendar/preview', calendar_preview)

    async def text_preview(request):
        """A template tile as a screen would get it, for the editor's inspector (docs/TEXT_TILE.md): Home Assistant's
        rendering of the template once, its rows by the same text_tile.block the screens get, and the bytes they take
        of the screen's budget. The template runs with this app's token, as the tile's own subscription does."""
        data = await request.json()
        template = data.get('template') if isinstance(data, dict) else None
        try:
            template = text_tile.validate(template)
        except ValueError:
            raise ValueError(t('addon.errors.layout.text_template')) from None
        inbox = data.get('inbox') if isinstance(data.get('inbox'), str) else None
        budget = manager.text_caps(inbox)[0]
        if not manager.ha.online:
            raise ConnectionError(t('addon.errors.ha_unreachable'))
        result = await manager.templates.preview(template)
        block = result.block(budget)
        return web.json_response({'md': block, 'text': result.text, 'error': result.error, 'listeners': result.listeners,
                                  'bytes': text_tile.size(block), 'budget': budget})
    app.router.add_post('/api/text/preview', text_preview)

    async def text_entity(request):
        """One entity as the template editor completes it: its state, its attributes and the states it may take
        (text_tile.entity_facts). The template itself reads any of them with the app's token, so the editor may too."""
        entity = request.query.get('entity', '')
        if not entity_id(entity):
            raise ValueError(t('addon.errors.invalid_input'))
        if entity not in manager.ha.states:
            raise web.HTTPNotFound()
        return web.json_response(text_tile.entity_facts(manager.ha.states[entity]))
    app.router.add_get('/api/text/entity', text_entity)

    def vacuum_of(request):
        entity = request.query.get('entity', '')
        if not entity.startswith('vacuum.') or entity not in manager.ha.states:
            raise ValueError(t('addon.errors.invalid_input'))
        return entity, manager.vacuum_block(entity) or {}

    async def vacuum_preview(request):
        """A vacuum's tile as a screen with the card's module gets it, for the editor's mockup: whether it has a map, its
        rooms (name and icon, in Home Assistant's order) and its routines."""
        entity, card = vacuum_of(request)
        rooms = [[row[1], str(row[2] or '')] for row in card.get('rooms') or ()]
        # The cleaning mode's kinds, one letter per option (core.vacuum_extras 'r'), and the one in use.
        extras = core.vacuum_extras({'entity': entity}, manager.ha.states, manager.device_entries(entity)) or {}
        mode = extras.get('mode') or {}
        current = mode.get('o', []).index(mode['s']) if mode.get('s') in mode.get('o', []) else -1
        return web.json_response({'modes': mode.get('r', ''), 'mode': current, 'map': isinstance(card.get('map'), dict), 'mark': (card.get('map') or {}).get('m', ''),
                                  'rooms': rooms, 'routines': [row[1] for row in card.get('rt') or ()], 'unmapped': bool(card.get('unmapped'))})

    async def vacuum_map_picture(request):
        """The robot's map as the screen draws it (vacuum_map.py), at the size and on the colour the mockup asks for."""
        import vacuum_map
        _, card = vacuum_of(request)
        found = card.get('map') if isinstance(card.get('map'), dict) else None
        drawing = await manager.snapshots.vacuum(found['e'], found['m']) if found else None
        if drawing is None:
            raise web.HTTPNotFound()
        try:
            size = (max(16, min(1600, int(request.query.get('w', 0)))), max(16, min(1600, int(request.query.get('h', 0)))))
            ground = int(request.query.get('ground', 'FFFFFF'), 16) & 0xFFFFFF
        except ValueError:
            raise ValueError(t('addon.errors.invalid_input')) from None
        dark = request.query.get('dark') == '1'

        def draw():
            from PIL import Image
            with Image.open(io.BytesIO(vacuum_map.render(drawing[0], size, ground, dark))) as image:
                out = io.BytesIO()
                image.save(out, 'PNG')
                return out.getvalue()
        body = await asyncio.get_running_loop().run_in_executor(None, draw)
        return web.Response(body=body, content_type='image/png', headers={'Cache-Control': 'max-age=60'})
    app.router.add_get('/api/vacuum/preview', vacuum_preview)
    app.router.add_get('/api/vacuum/map', vacuum_map_picture)
    app.router.add_get('/api/screens/{inbox}/extras', extras)
    app.router.add_get('/api/screens/{inbox}/extras/events', extras_events)
    app.router.add_post('/api/screens/{inbox}/extras', extra)
    app.router.add_get('/', index)
    app.router.add_get('/api/inventory', inventory)
    app.router.add_get('/api/capabilities', capabilities)
    app.router.add_get('/api/states', states)
    app.router.add_get('/api/history-preview', preview_history)
    app.router.add_get('/api/media-art', media_art_preview)
    app.router.add_get('/api/camera-preview', camera_preview)
    app.router.add_get('/api/media/browse', media_browse)
    app.router.add_get('/api/media/picture', media_picture)
    app.router.add_get('/api/media/link', media_link)
    app.router.add_post('/api/firmware-preview', firmware_preview)
    app.router.add_post('/api/firmware-preview/import', import_document)
    app.router.add_post('/api/firmware-preview/action', firmware_preview_action)
    app.router.add_post('/api/firmware-preview/image', firmware_preview_image)
    app.router.add_get('/api/firmware-preview/events', firmware_preview_events)
    app.router.add_get(r'/api/firmware-preview/images/{token:[A-Za-z0-9_-]{16,64}}.bmp', firmware_preview_pixels)
    app.router.add_post('/api/screens/{inbox}/identify', identify)
    app.router.add_post('/api/screens/{inbox}/calibrate', calibrate)
    app.router.add_post('/api/alerts/test', test_alert)
    app.router.add_post('/api/doorbell/test', test_doorbell)
    app.router.add_get('/api/automations', list_automations)
    app.router.add_post('/api/automations', save_automation)
    app.router.add_delete('/api/automations/{id}', delete_automation)
    app.router.add_get('/api/entity-actions', entity_actions)
    app.router.add_get('/api/light-choices', light_choices)
    app.router.add_get('/api/entity-subtitle', entity_subtitle)
    app.router.add_get('/api/display-precision', display_precision)
    app.router.add_put('/api/display-precision', display_precision)
    app.router.add_post('/api/header-preview', header_preview)
    app.router.add_post('/api/claude-skill', install_claude_skill)
    app.router.add_get('/api/claude-skill.zip', download_claude_skill)
    app.router.add_post('/api/video', install_video)
    app.router.add_post('/api/video/restart', restart_for_video)
    app.router.add_get('/api/events', events)
    app.router.add_put('/api/screens/{inbox}', save)
    app.router.add_post('/api/screens/{inbox}/import', import_document)
    app.router.add_post('/api/screens/{inbox}/migration/dismiss', dismiss_migration)
    app.router.add_post('/api/screens/{inbox}/migration/reset', start_fresh)
    app.router.add_put('/api/screens/{inbox}/workspace', save_workspace)
    app.router.add_delete('/api/screens/{inbox}', remove_screen)
    app.router.add_post('/api/screens/{inbox}/allow-actions', allow_actions)
    app.router.add_put('/api/screens/{inbox}/name', rename_screen)
    app.router.add_put('/api/screens/{inbox}/settings', change_settings)
    app.router.add_put('/api/screens/{inbox}/screensaver', change_screensaver)
    app.router.add_get('/api/screensaver/photos', browse_photos)
    app.router.add_post('/api/screens/{inbox}/feedback', feedback_action)
    app.router.add_static('/assets/', static / 'assets')
    return app

async def addon_self(session):
    """This app's slug and version from the Supervisor (/addons/self/info, which needs no role), (None, None) without a
    Supervisor."""
    token = os.environ.get('SUPERVISOR_TOKEN', '')
    if not token:
        return None, None
    try:
        async with session.get('http://supervisor/addons/self/info', headers={'Authorization': f'Bearer {token}'},
                               timeout=ClientTimeout(total=10)) as response:
            info = await response.json()
        data = info.get('data') or {}
        slug, version = data.get('slug'), data.get('version')
        return (slug if isinstance(slug, str) else None), (version if isinstance(version, str) else None)
    except Exception as error:
        LOG.info('Reading the app slug failed (%s)', type(error).__name__)
        return None, None

async def main():
    development = os.environ.get('SCREEN_DEV') == '1'
    token = os.environ.get('SUPERVISOR_TOKEN', '')
    if development and os.environ.get('HA_TOKEN_FILE'):
        token = Path(os.environ['HA_TOKEN_FILE']).read_text().strip()
    if not token:
        raise SystemExit('No Home Assistant access. Start the app via Supervisor.')
    async with ClientSession(timeout=ClientTimeout(total=20)) as session:
        # The branch the screens build from (docs/RELEASING.md, "Testing dev"): dev for an app added from the `#dev` URL,
        # or for the image GitHub builds from dev (docs/DOCKER.md, "Testing dev").
        slug, version = await addon_self(session)
        core.set_channel(core.start_channel(slug))
        core.set_version(version)
        LOG.info('App %s %s, channel %s, screens build from %s', slug or 'without a Supervisor', version or '',
                 core.channel() or 'none', core.ref() if core.channel() else 'the ref they have')
        ha = HomeAssistant(session, os.environ.get('HA_API', 'http://supervisor/core/api'), token)
        manager = Manager(ha, Path(os.environ.get('SCREEN_DATA', '/data')) / 'screens.json')
        # Every screen's YAML on what this app builds from, before anything can build it (core.ref): after an update of
        # the app its screens build its new release, whoever starts the build.
        moved = manager.firmware.follow_release()
        if moved:
            LOG.info('Screens now build from %s: %s', core.ref(), ', '.join(moved))
        # handle_signals: SIGTERM (the Supervisor stopping the app, `docker stop`) and SIGINT end the app through the
        # cleanup below, which also stops a running build, instead of waiting ten seconds for SIGKILL (app 0.2.78).
        runner = web.AppRunner(create_app(manager, development), access_log=None, handle_signals=True)
        await runner.setup()
        await web.TCPSite(runner, '127.0.0.1' if development else '0.0.0.0', 8099).start()
        # Camera images for the screens: their own port on the LAN, not the ingress page (docs/CAMERA.md).
        cameras = web.AppRunner(picture_links.web_app(manager.links, manager.live), access_log=None)
        await cameras.setup()
        try:
            await web.TCPSite(cameras, '0.0.0.0', picture_links.port()).start()
        except OSError as error:
            # Everything else still works; only camera images stay away.
            LOG.error('Camera images are off: port %d is not available (%s)', picture_links.port(), error)
        try:
            await asyncio.gather(ha.run(), manager.run(), manager.history_loop(), manager.updates.run(),
                                 manager.alert_loop(), manager.doorbell_loop(), manager.tile_loop(), manager.card_history_loop(), manager.camera_loop(), manager.card_options_loop(), manager.calendar_loop(),
                                 manager.media_loop(), manager.pairing_loop(), manager.photo_loop(), manager.video_loop(),
                                 *([manager.plugins.loop(), manager.plugin_loop()] if core.plugins_enabled() else []))
        finally:
            await cameras.cleanup()
            await runner.cleanup()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    # The signal arrives as GracefulExit once everything is cleaned up, as in aiohttp's own run_app: a normal stop.
    with contextlib.suppress(web.GracefulExit):
        asyncio.run(main())
