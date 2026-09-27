"""Firmware updates for paired screens: on demand, all at once, or nightly. One screen at a time."""
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import time
import changelog
from core import FIRMWARE_VERSION, SHAPES, board_of, firmware_target, parse_firmware
from i18n import Text, english, screen_t, shown, t

LOG = logging.getLogger('screen_manager')
NIGHT_HOURS = range(3, 6)

# Strict X.Y.Z, the one rule the feature gates follow too: an update goes by what the screen's sensor reports now.
parse_version = parse_firmware

def result_text(result):
    """A kept result's message: a Text from its key where it has one (app 0.2.90+), else the English it was kept in."""
    key, params = result.get('key'), result.get('params')
    if isinstance(key, str) and key:
        return Text(str(result.get('message', '')), key, params if isinstance(params, dict) else {})
    return result.get('message', '')

def shown_result(result):
    """A kept result as the editor shows it, its message in the editor's language."""
    if not isinstance(result, dict) or not isinstance(result.get('key'), str):
        return result
    return {**result, 'message': shown(result_text(result))}

class Updater:
    verify_timeout = 240
    settle_seconds = 60
    pause_seconds = 120
    poll_seconds = 5

    def __init__(self, manager, path):
        self.manager, self.path = manager, Path(path)
        self.auto, self.hosts, self.results, self.last_round = False, {}, {}, None
        self.task, self.current, self.queue, self.phase = None, None, [], None
        # What's new since a screen's firmware, for the Update badge (app 0.2.73).
        self.changelog = changelog.load()
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            if raw.get('version') != 1:
                raise ValueError('Unknown storage version for updates; data stays unchanged.')
            self.auto = raw.get('auto') is True
            self.hosts = {k: v for k, v in raw.get('hosts', {}).items() if isinstance(v, str)}
            self.results = {k: v for k, v in raw.get('results', {}).items() if isinstance(v, dict)}
            self.last_round = raw.get('last_round') if isinstance(raw.get('last_round'), str) else None

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        with open(temp, 'w', encoding='utf8') as handle:
            os.chmod(temp, 0o600)
            json.dump({'version': 1, 'auto': self.auto, 'hosts': self.hosts, 'results': self.results,
                       'last_round': self.last_round}, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self.path)

    def busy(self):
        return bool(self.task and not self.task.done())

    def screen(self, inbox):
        return self.manager.screen(inbox)

    def current_id(self, inbox):
        """The id a screen reports under now; firmware 0.2.34 gave the inbox entity a new id."""
        return getattr(self.manager, 'aliases', {}).get(inbox, inbox)

    def renamed(self, old, new):
        """A screen's inbox entity got a new id: its address, last result and place in a running round follow."""
        changed = False
        for store in (self.hosts, self.results):
            if old in store:
                if new not in store:
                    store[new] = store[old]
                del store[old]
                changed = True
        if changed:
            self.save()
        if self.current == old:
            self.current = new
        self.queue = [new if inbox == old else inbox for inbox in self.queue]
        return changed

    def forget(self, inbox):
        """A screen that was removed on purpose (app 0.2.112): its address and its last result go with it."""
        changed = False
        for store in (self.hosts, self.results):
            if store.pop(inbox, None) is not None:
                changed = True
        if changed:
            self.save()
        self.queue = [item for item in self.queue if item != inbox]
        return changed

    def resolve(self, screen, profiles=None):
        """Profile file and OTA address for a screen; None when the add-on cannot tell."""
        if profiles is None:
            profiles = self.manager.firmware.profile_names()
        profile = next((f for f, p in profiles.items() if screen.get('node') and p['node'] == screen['node']), None)
        if profile is None and screen.get('device'):
            # Screens on firmware before 0.2.17 do not report their node name yet.
            matches = [f for f, p in profiles.items() if p['friendly'] == screen['device']]
            profile = matches[0] if len(matches) == 1 else None
        return profile, screen.get('ip') or self.hosts.get(screen['id'])

    def language_due(self, screen):
        """True when a screen speaks another language than Settings -> Language & region says (app 0.2.90): its
        "Screen language" sensor, or English for firmware from before that sensor. A sensor without a state yet (the
        screen restarts) says nothing."""
        region = getattr(self.manager, 'region', None)
        if not region or (screen.get('language_sensor') and not screen.get('language')):
            return False
        return (screen.get('language') or 'en') != region.language()

    def speaks_region(self, screen):
        """Whether the screen says it speaks the language of Settings -> Language & region: what an update waits for."""
        region = getattr(self.manager, 'region', None)
        if not region:
            return True
        return (screen.get('language') if screen.get('language_sensor') else 'en') == region.language()

    def target_for(self, screen, profiles=None):
        """The firmware this screen is offered (app 0.3.21): its board's (core.firmware_target), so a fix for one board is
        no update for the others. The board is the one its profile builds, because that is what an update flashes;
        without a profile here, the board the screen reports."""
        if profiles is None:
            profiles = self.manager.firmware.profile_names()
        profile, _ = self.resolve(screen, profiles)
        package = (profiles.get(profile) or {}).get('package') if profile else None
        board = (SHAPES.get(package) or {}).get('board') if isinstance(package, str) else None
        return firmware_target(board or board_of(screen))

    def state_for(self, screen, profiles=None):
        if profiles is None:
            profiles = self.manager.firmware.profile_names()
        version = parse_version(screen.get('firmware'))
        language = self.language_due(screen)
        profile, host = self.resolve(screen, profiles)
        target = self.target_for(screen, profiles)
        if screen['id'] == self.current:
            state = 'running'
        elif screen['id'] in self.queue:
            state = 'queued'
        else:
            state = 'idle'
        return {'available': bool(version and version < parse_version(target)) or (bool(version) and language),
                'language': bool(version) and language, 'target': target,
                'profile': profile, 'host': host, 'state': state, 'phase': self.phase if state == 'running' else None,
                'result': shown_result(self.results.get(screen['id']))}

    def summary(self, screens=None, profiles=None):
        # The changelog goes with the full inventory only (app 0.2.78): this summary is in every live update of the page.
        # `target` is the shared version; what one screen is offered is its own `update.target` (app 0.3.21).
        return {'auto': self.auto, 'target': FIRMWARE_VERSION, 'busy': self.current,
                'pending': len(self.pending(screens, profiles)), 'last_round': self.last_round}

    def pending(self, screens=None, profiles=None):
        # Callers that already hold the inventory and profile list pass them in; the inventory
        # handler otherwise re-reads every ESPHome profile several times per request.
        if screens is None:
            screens = self.manager.screens()
        if profiles is None:
            profiles = self.manager.firmware.profile_names()
        return [s['id'] for s in screens
                if s['online'] and self.state_for(s, profiles)['available'] and all(self.resolve(s, profiles))]

    def set_auto(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError(t('addon.errors.updates.automatic'))
        self.auto = enabled
        self.save()

    def start(self, inbox, host=None):
        if self.busy():
            raise ValueError(t('addon.errors.updates.busy'))
        screen = self.screen(inbox)
        inbox = self.current_id(inbox)
        if not screen:
            raise ValueError(t('addon.errors.updates.unknown_screen'))
        if not screen['online']:
            raise ValueError(t('addon.errors.updates.offline'))
        if not self.state_for(screen)['available']:
            raise ValueError(t('addon.errors.updates.latest'))
        if host is not None:
            if not isinstance(host, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}', host.strip()):
                raise ValueError(t('addon.errors.updates.enter_ip'))
            self.hosts[inbox] = host.strip()
            self.save()
        profile, host = self.resolve(screen)
        if not profile:
            raise ValueError(t('addon.errors.updates.no_profile'))
        if not host:
            raise ValueError(t('addon.errors.updates.ip_unknown'))
        self.manager.preflight_update(inbox)
        self.launch([inbox])
        return self.state_for(screen)

    def start_all(self):
        if self.busy():
            raise ValueError(t('addon.errors.updates.busy'))
        pending = self.pending()
        if not pending:
            raise ValueError(t('addon.errors.updates.all_updated'))
        for inbox in pending:
            self.manager.preflight_update(inbox)
        self.launch(pending)
        return pending

    def launch(self, inboxes, automatic=False):
        # Mark the first screen busy right away so the page shows progress before the task runs.
        self.current, self.queue, self.phase = inboxes[0], inboxes[1:], 'install'
        self.task = asyncio.create_task(self.run_round(inboxes, automatic))

    def record(self, inbox, state, message, version=None):
        """A screen's last result. `message` keeps its key and params (a Text) next to the English, so the editor shows it
        in its own language and an app from before 0.2.90 still reads the English. `version` is the firmware the round
        went for, the screen's own target unless given."""
        if version is None:
            screen = self.screen(inbox)
            version = self.target_for(screen) if screen else FIRMWARE_VERSION
        result = {'time': time.time(), 'state': state, 'message': str(message), 'version': version}
        if isinstance(message, Text) and message.key:
            result.update(message=message.into('en'), key=message.key, params=message.params)
        self.results[self.current_id(inbox)] = result
        self.save()

    async def run_round(self, inboxes, automatic=False):
        """Update screens one by one; a failure ends the round so a bad build never reaches the next screen."""
        try:
            for index, inbox in enumerate(inboxes):
                inbox = self.current_id(inbox)
                self.current, self.queue = inbox, [self.current_id(i) for i in inboxes[index+1:]]
                outcome = await self.update_one(inbox)
                if outcome == 'failed':
                    if automatic:
                        # For whoever reads Home Assistant: in the screens' language, Home Assistant's own unless another was
                        # chosen (app 0.2.90).
                        await self.notify(screen_t('addon.notify.update_stopped', name=self.name(inbox),
                                                   reason=result_text(self.results[self.current_id(inbox)])))
                    break
                if self.queue and outcome == 'success':
                    await asyncio.sleep(self.pause_seconds)
        finally:
            self.current, self.queue, self.phase = None, [], None

    def name(self, inbox):
        screen = self.screen(inbox)
        return screen['name'] if screen else inbox

    async def update_one(self, inbox):
        screen = self.screen(inbox)
        if not screen or not screen['online']:
            self.record(inbox, 'skipped', english('addon.updates.offline'))
            return 'skipped'
        profile, host = self.resolve(screen)
        if not profile or not host:
            self.record(inbox, 'skipped', english('addon.updates.unknown_target'))
            return 'skipped'
        # Worked out before the build: the screen goes offline while it flashes, and this is what the build makes.
        target = self.target_for(screen)
        self.phase = 'install'
        try:
            # Recheck when a queued/nightly screen reaches the front of the
            # queue; its saved configuration can change while another builds.
            self.manager.preflight_update(inbox)
            self.manager.firmware.start({'file': profile, 'action': 'install', 'target': host})
            await self.manager.firmware.task
        except ValueError as error:
            # The sentence firmware.start refused with, kept with its key.
            self.record(inbox, 'failed', error.args[0] if len(error.args) == 1 else str(error))
            return 'failed'
        if self.manager.firmware.job.get('state') != 'success':
            self.record(inbox, 'failed', english('addon.updates.build_failed'))
            return 'failed'
        self.phase = 'verify'
        if not await self.wait_for_target(inbox, target):
            self.record(inbox, 'failed', english('addon.updates.no_report', version=target), target)
            return 'failed'
        self.phase = 'settle'
        await asyncio.sleep(self.settle_seconds)
        current = self.screen(inbox)
        if not current or not current['online']:
            self.record(inbox, 'failed', english('addon.updates.dropped_off'), target)
            return 'failed'
        self.record(inbox, 'success', english('addon.updates.updated', version=target), target)
        return 'success'

    async def wait_for_target(self, inbox, target=None):
        """Whether the screen reports the firmware the round flashed (`target`, its own by default) and the region's
        language within verify_timeout."""
        wanted = parse_version(target or self.target_for(self.screen(inbox) or {'id': inbox}))
        deadline = time.monotonic() + self.verify_timeout
        while time.monotonic() < deadline:
            screen = self.screen(inbox)
            version = parse_version(screen.get('firmware')) if screen else None
            if screen and screen['online'] and version and version >= wanted and self.speaks_region(screen):
                return True
            await asyncio.sleep(self.poll_seconds)
        return False

    async def notify(self, message):
        try:
            await self.manager.ha.request('call_service', domain='persistent_notification', service='create',
                                          service_data={'notification_id': 'esp_screens_update', 'title': 'Tessera', 'message': message})
        except Exception as error:
            LOG.warning('Notifying Home Assistant failed (%s)', type(error).__name__)

    def due(self, now):
        return self.auto and now.hour in NIGHT_HOURS and self.last_round != now.date().isoformat()

    async def run(self):
        while True:
            await asyncio.sleep(60)
            try:
                if self.busy() or not self.manager.ha.online:
                    continue
                now = datetime.now(getattr(self.manager.ha, 'time_zone', None) or timezone.utc)
                if not self.due(now):
                    continue
                self.last_round = now.date().isoformat()
                self.save()
                pending = self.pending()
                if pending:
                    LOG.info('Nightly firmware round: %d screen(s)', len(pending))
                    self.launch(pending, automatic=True)
            except Exception as error:
                LOG.warning('Nightly update check skipped (%s)', type(error).__name__)
