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
from core import FIRMWARE_VERSION, SHAPES, board_of, channel, firmware_target, parse_firmware
from i18n import Text, english, screen_t, shown, t

LOG = logging.getLogger('screen_manager')
NIGHT_HOURS = range(3, 6)
# What a screen with 4 MB of flash says about its partition table in its "Screen flash" sensor (components/flash_layout)
# that this app acts on: it has the wide one, it is ready to take it, or it is ready after one more update (it runs
# from its second slot, and ESPHome replaces the table of a screen in its first). Any other word, and no word at all,
# is a screen that keeps the table it has. docs/FLASH_LAYOUT.md.
SLOT_WORDS = ('wide', 'widen', 'widen_next')

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
    # The partition table of a board with 4 MB of flash (app 0.4.56). How long a screen gets to say its word after a
    # restart: its features sensor speaks every minute. And for a screen on its bridge, which Home Assistant cannot
    # see: how often the steps are tried, how long a restart gets, and how long until a round that did not finish is
    # tried again. A firmware is on trial for a minute after an update (ESPHome's rollback): the screen says "widen"
    # only once it is confirmed, and the bridge gets that minute too (bridge_trial).
    word_timeout = 240
    bridge_attempts = 6
    bridge_pause = 20
    bridge_trial = 75
    bridge_retry = 300

    def __init__(self, manager, path):
        self.manager, self.path = manager, Path(path)
        self.auto, self.hosts, self.results, self.last_round = False, {}, {}, None
        self.task, self.current, self.queue, self.phase = None, None, [], None
        # Screens this app left on their bridge (app 0.4.56): {inbox: {'profile', 'host', 'since'}}, finished by the
        # next round however it ended, also after a restart of the app.
        self.bridging, self.bridge_tried = {}, 0.0
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
            self.bridging = {k: v for k, v in raw.get('bridging', {}).items()
                             if isinstance(v, dict) and isinstance(v.get('profile'), str) and isinstance(v.get('host'), str)}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        with open(temp, 'w', encoding='utf8') as handle:
            os.chmod(temp, 0o600)
            # 'bridging' only while a screen is on its bridge, so the file reads as before for an older app.
            json.dump({'version': 1, 'auto': self.auto, 'hosts': self.hosts, 'results': self.results,
                       'last_round': self.last_round, **({'bridging': self.bridging} if self.bridging else {})},
                      handle, ensure_ascii=False)
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
        for store in (self.hosts, self.results, self.bridging):
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
        for store in (self.hosts, self.results, self.bridging):
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
        # `target` is the shared version; what one screen is offered is its own `update.target` (app 0.3.21). `channel`
        # is the branch the screens build from, when the app was added from this repository (docs/RELEASING.md).
        return {'auto': self.auto, 'target': FIRMWARE_VERSION, 'busy': self.current,
                'pending': len(self.pending(screens, profiles)), 'last_round': self.last_round, 'channel': channel()}

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

    def start(self, inbox, host=None, reinstall=False):
        """Update one screen. `reinstall` builds and installs it again although it runs this firmware already: on the
        dev channel only, where the firmware number stays the same from one commit to the next (docs/RELEASING.md,
        "Testing dev"), so the newest dev is never an update by its number."""
        if reinstall and channel() != 'dev':
            raise ValueError(t('addon.errors.updates.reinstall_dev'))
        if self.busy():
            raise ValueError(t('addon.errors.updates.busy'))
        screen = self.screen(inbox)
        inbox = self.current_id(inbox)
        if not screen:
            raise ValueError(t('addon.errors.updates.unknown_screen'))
        if not screen['online']:
            raise ValueError(t('addon.errors.updates.offline'))
        if not reinstall and not self.state_for(screen)['available']:
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
        # A screen this app left on its bridge is away for Home Assistant, and still this app's to finish.
        note = self.bridging.get(self.current_id(inbox))
        if note and screen and screen['online'] and parse_version(screen.get('firmware')):
            # It runs a screen's firmware again (installed by hand, or the last step did land): nothing to finish.
            await self.close_bridge(inbox, note['profile'])
            note = None
        if not note and (not screen or not screen['online']):
            self.record(inbox, 'skipped', english('addon.updates.offline'))
            return 'skipped'
        profile, host = (note['profile'], note['host']) if note else self.resolve(screen)
        if not profile or not host:
            self.record(inbox, 'skipped', english('addon.updates.unknown_target'))
            return 'skipped'
        # Worked out before the build: the screen goes offline while it flashes, and this is what the build makes.
        target = self.target_for(screen) if screen else FIRMWARE_VERSION
        firmware = self.manager.firmware
        wide = self.takes_wide_table(profile)
        self.phase = 'install'
        try:
            # Recheck when a queued/nightly screen reaches the front of the
            # queue; its saved configuration can change while another builds.
            self.manager.preflight_update(inbox)
            if wide:
                installed = await self.install_wide(inbox, profile, host)
            else:
                installed = await self.job(profile, 'install', host)
        except ValueError as error:
            # The sentence firmware.start refused with, kept with its key.
            self.record(inbox, 'failed', error.args[0] if len(error.args) == 1 else str(error))
            return 'failed'
        if not installed:
            # A build the machine had no memory for says so (build_memory, app 0.4.65), the rest points at the log.
            memory = (firmware.job or {}).get('memory') or {}
            if memory.get('reason') == 'out':
                free = f'{memory["free_mb"] / 1024:.1f} GB' if memory.get('free_mb') is not None else '?'
                self.record(inbox, 'failed', english('addon.updates.build_memory', free=free,
                                                     need=f'{memory.get("need_mb", 0) / 1024:.1f} GB'))
            elif memory.get('reason') == 'limit':
                self.record(inbox, 'failed', english('addon.updates.build_memory_limit'))
            else:
                self.record(inbox, 'failed', english('addon.updates.build_failed'))
            return 'failed'
        self.phase = 'verify'
        if not await self.wait_for_target(inbox, target):
            self.record(inbox, 'failed', english('addon.updates.no_report', version=target), target)
            return 'failed'
        if wide:
            try:
                back = await self.widen(inbox, profile, host)
            except ValueError as error:
                LOG.warning('%s keeps the partition table it has (%s)', profile, error)
                back = True
            if not back:
                self.record(inbox, 'failed', english('addon.updates.dropped_off'), target)
                return 'failed'
        self.phase = 'settle'
        await asyncio.sleep(self.settle_seconds)
        current = self.screen(inbox)
        if not current or not current['online']:
            self.record(inbox, 'failed', english('addon.updates.dropped_off'), target)
            return 'failed'
        if self.current_id(inbox) in self.bridging:
            await self.close_bridge(inbox, profile)
        self.record(inbox, 'success', english('addon.updates.updated', version=target), target)
        return 'success'

    # ---- the partition table of a board with 4 MB of flash (app 0.4.56, docs/FLASH_LAYOUT.md)
    async def job(self, profile, action, host=''):
        """One ESPHome job for a profile, waited for. True when it succeeded; a refusal (ValueError) is the caller's."""
        firmware = self.manager.firmware
        firmware.start({'file': profile, 'action': action, **({'target': host} if host else {})})
        await firmware.task
        return firmware.job.get('state') == 'success'

    def takes_wide_table(self, profile):
        """Whether this profile's board builds for the wide partition table (boards.json `wide_slots`)."""
        check = getattr(self.manager.firmware, 'wide_slots', None)
        return bool(check and check(profile))

    def slot_word(self, inbox):
        """What the screen says about its partition table now, when it is one of SLOT_WORDS, else None: firmware from
        before the sensor, a table of its owner's own, a firmware ESPHome has not confirmed yet, or a screen that is
        restarting."""
        word = (self.screen(inbox) or {}).get('flash')
        return word if word in SLOT_WORDS else None

    async def wait_for_word(self, inbox, wanted=SLOT_WORDS):
        """The screen's word about its table once it is one of `wanted`, or None when word_timeout passes without."""
        wanted = (wanted,) if isinstance(wanted, str) else wanted
        deadline = time.monotonic() + self.word_timeout
        while True:
            screen = self.screen(inbox)
            word = self.slot_word(inbox) if screen and screen['online'] else None
            if word in wanted:
                return word
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(self.poll_seconds)

    async def send_table(self, inbox, profile, host):
        """The wide table to a screen that says "widen", from the build just made. True when the screen is back and
        says "wide"."""
        LOG.info('%s: sending the wide partition table', profile)
        if not await self.job(profile, 'widen', host):
            return False
        return await self.wait_for_word(inbox, 'wide') == 'wide'

    async def install_wide(self, inbox, profile, host):
        """Build and install the firmware of a board whose flash takes the wide table. True when it is on the screen.

        A screen that already says "widen" gets the table first, from the firmware it runs. A screen that still has
        ESPHome's table and no way to change it (firmware from before the component) cannot take a firmware larger than that
        table's slot: it goes over its bridge. Anything else installs as every screen does."""
        firmware = self.manager.firmware
        if not await self.job(profile, 'build'):
            return False
        note = self.bridging.get(self.current_id(inbox))
        if note:
            return await self.over_bridge(inbox, profile, host, started=True)
        word = self.slot_word(inbox)
        if word == 'widen':
            if not await self.send_table(inbox, profile, host):
                return False
        elif word != 'wide' and (firmware.image_size(profile) or 0) > firmware.NARROW_SLOT:
            return await self.over_bridge(inbox, profile, host)
        return await self.job(profile, 'install', host)

    async def widen(self, inbox, profile, host):
        """After an update: the wide table for a screen that still has ESPHome's and says it is ready. False only when
        the screen was sent the table and did not come back; a screen that says nothing keeps what it has."""
        word = await self.wait_for_word(inbox)
        if word == 'widen_next':
            # It runs from its second slot: the same firmware once more puts it in its first.
            if not await self.job(profile, 'install', host):
                LOG.warning('%s: the second install before the partition table failed; it keeps its table for now', profile)
                return True
            word = await self.wait_for_word(inbox, 'widen')
        if word == 'widen':
            return await self.send_table(inbox, profile, host)
        return True

    async def over_bridge(self, inbox, profile, host, started=False):
        """The firmware of `profile`, already built and too large for the slot the screen has, by way of its bridge:
        the bridge, the wide table, the firmware. True when the firmware is on the screen.

        Home Assistant cannot see a screen on its bridge, so each step goes by what ESPHome's upload answers, and the
        screen itself refuses what it cannot take without writing anything: a firmware too large for its slot, a table
        before the bridge runs. On a slow flash chip it may also refuse the table while the bridge runs from its
        second slot; installing the bridge once more moves it to the first. After an install the bridge gets the
        minute ESPHome takes to confirm a new firmware, because a restart before that goes back to the one before.
        The note in `bridging` stays until update_one has seen the screen back in Home Assistant with its firmware
        and through its settle time: a restart in a new firmware's first minute puts the firmware from before back
        (ESPHome's rollback), and from before is the bridge here. So a round that stops anywhere is picked up again
        (`started`), from whatever step the screen is at."""
        firmware = self.manager.firmware
        inbox = self.current_id(inbox)
        bridge = firmware.bridge(profile)
        if not await self.job(bridge, 'build'):
            return False
        if not started:
            LOG.info('%s: its firmware no longer fits the partition table it has; going over its bridge', profile)
            self.bridging[inbox] = {'profile': profile, 'host': host, 'since': time.time()}
            self.save()
            if not await self.job(bridge, 'install', host):
                # Nothing on the screen changed: it still runs what it ran.
                await self.close_bridge(inbox, profile)
                return False
            await asyncio.sleep(self.bridge_trial)
        for attempt in range(self.bridge_attempts):
            # A round picked up again does not know how far the last one came: the firmware fits once the table is wide.
            if (started or attempt) and await self.job(profile, 'install', host):
                return True
            if await self.job(bridge, 'widen', host):
                await asyncio.sleep(self.bridge_pause)
                if await self.job(profile, 'install', host):
                    return True
            if await self.job(bridge, 'install', host):
                await asyncio.sleep(self.bridge_trial)
        return False

    async def close_bridge(self, inbox, profile):
        """The screen runs its own firmware again: its note and its bridge go."""
        if self.bridging.pop(self.current_id(inbox), None) is not None:
            self.save()
        try:
            await self.manager.firmware.drop_bridge(profile)
        except (OSError, ValueError) as error:
            LOG.warning('Could not remove the bridge of %s (%s)', profile, error)

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
                # A screen left on its bridge is finished first, whatever the hour and with or without the nightly round.
                waiting = [inbox for inbox in self.bridging if self.screen(inbox)]
                if waiting and time.monotonic() - self.bridge_tried >= self.bridge_retry:
                    self.bridge_tried = time.monotonic()
                    LOG.info('Finishing the update of %d screen(s) on their bridge', len(waiting))
                    self.launch(waiting, automatic=True)
                    continue
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
