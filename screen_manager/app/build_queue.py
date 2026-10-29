"""The app's one build slot and the line in front of it (docs/BUILDS.md).

ESPHome builds one firmware at a time here (Firmware.start), and everything that builds goes through this line: a
firmware update (one screen, Update all, the nightly round), a plugin build, New screen, and Firmware & USB with its
YAML check. Nothing is refused because something else builds; it waits its turn, and the page says so.

A build is what was asked for one profile, with the steps of its kind (`run`): an update installs, waits for the screen
and may go over a bridge, a plugin build installs and then settles its plugins, Firmware & USB runs one ESPHome action.
The build keeps the slot until all of its steps are done, so nothing else starts between two steps of an update.

- Order: as asked, except that what a person follows on the page (`attended`: New screen, Firmware & USB, the YAML
  check) goes before the updates and plugin builds that wait. A build that runs is never stopped for another.
- One build per screen: what is asked for a profile that already waits joins that build (`join`): a plugin build and an
  update of one screen are one build, since an update builds the screen's plugins file too. A build that runs takes
  nothing more (it may have read its YAML already); what is asked meanwhile waits for a build after it.
- Every build has an id, and the last ones that ended stay (`ENDED`) with their outcome and their log, so whoever
  follows one (the page, a test) reads how it ended, also when the next build started at once. The line goes to the
  page with every live answer (`payload`, the inventory's `line`), and every change of it asks for one (`_changed`).
- A round (Update all, the nightly round) is several builds that belong together: one that fails ends the ones of its
  round that still wait, so a bad build never reaches the next screen. A build someone asked for apart as well (a
  screen's own Update, a plugin) no longer counts in the round, so it is never left out for another screen's failure.
"""
import asyncio
import collections
import itertools
import logging
import time

from i18n import shown, t

LOG = logging.getLogger('screen_manager')

# The kinds of build, as the page names them (Manager.builds `by`): an update joins anything of its screen that waits,
# since it builds the same profile and does more.
KINDS = ('update', 'plugins', 'install', 'check')
WAITING, RUNNING = 'queued', 'running'
ENDS = ('success', 'failed', 'skipped', 'interrupted')


class Round:
    """Builds that belong together (Update all, the nightly round): one that fails ends the rest of its round."""

    def __init__(self, automatic=False):
        self.automatic, self.builds = automatic, []

    async def wait(self):
        for build in list(self.builds):
            await build.done.wait()


class Build:
    """One build in the line: the profile it builds, what asked for it and its steps (`run`, a coroutine function that
    gets the build and returns how it ended: 'success', 'failed' or 'skipped')."""

    def __init__(self, number, by, file, run, screen=None, action='install', target='', attended=False, round=None,
                 plugins=None):
        if by not in KINDS:
            raise ValueError(by)
        self.id, self.by, self.file, self.run = number, by, file, run
        self.screen, self.action, self.target, self.attended, self.round = screen, action, target, attended, round
        # What the build brings for the screen's plugins (Plugins.apply): settled once it ends (`ends`).
        self.plugins = {'add': list((plugins or {}).get('add') or []), 'remove': list((plugins or {}).get('remove') or [])}
        # Starts from an empty build folder (Plugins.apply: a plugin's parts changed). ESPHome writes a file a component
        # adds to the build folder and never takes it away again; it wipes the folder only when a component is gone. So
        # a part that needs what an earlier build put a placeholder for (Screen camera's video and the empty esp_h264 of
        # its JPEG-only builds) would find the placeholder.
        self.fresh = bool((plugins or {}).get('fresh'))
        self.state, self.phase, self.reason = WAITING, None, None
        self.asked, self.started, self.finished = time.time(), None, None
        # Whether the profile itself went onto the screen (an install of `file` that succeeded, not its bridge's): what a
        # plugin build's outcome follows, also when an update's check afterwards fails.
        self.installed = False
        self.stepped = False  # whether it ran an ESPHome step: then the firmware's job and log are its own
        self.logs, self.memory = [], None
        # Where its compile ran (build_server.py): 'server' or 'here' after a fallback (its reason in `fallback`), None for
        # a build that never asked the server.
        self.where, self.server, self.fallback = None, None, None
        self.ends = []      # called with the build once it ended, whatever the outcome
        self.done = asyncio.Event()

    def join(self, other):
        """What is asked for this profile while this build waits joins it. An update brings what a plugin build brings
        and more, so the build becomes the update: its steps, its round."""
        if other.by == 'update' and self.by != 'update':
            self.by, self.run, self.screen = 'update', other.run, other.screen or self.screen
        # The round that asked waits for this build now. It counts in a round only while everything asked for it came
        # with that round: what someone asked apart is never left out because another screen of the round failed.
        if other.round:
            other.round.builds = [self if build is other else build for build in other.round.builds]
        if self.round is not other.round:
            self.round = None
        for key in ('add', 'remove'):
            self.plugins[key] = sorted(set(self.plugins[key]) | set(other.plugins[key]))
        self.fresh = self.fresh or other.fresh
        # A plugin taken off now is no longer added, and the other way round.
        self.plugins['add'] = [p for p in self.plugins['add'] if p not in other.plugins['remove']]
        self.plugins['remove'] = [p for p in self.plugins['remove'] if p not in other.plugins['add']]
        self.ends += [end for end in other.ends if end not in self.ends]


class BuildQueue:
    ENDED = 8

    def __init__(self, manager):
        self.manager = manager
        self.line, self.running, self.worker = [], None, None
        self.ended = collections.deque(maxlen=self.ENDED)
        self._numbers = itertools.count(1)

    @property
    def firmware(self):
        return self.manager.firmware

    # ---- asking ----
    def add(self, by, file, run, *, screen=None, action='install', target='', attended=False, round=None, plugins=None,
            join=True):
        """A build for `file`; the one that already waits for it when the two are one build (see the module). Returns the
        build that will do it."""
        build = Build(next(self._numbers), by, file, run, screen, action, target, attended, round, plugins)
        if round is not None:
            round.builds.append(build)
        waiting = self.waiting(file) if join and file and not attended else None
        if waiting:
            waiting.join(build)
            build = waiting
        elif attended:
            # After the other builds a person follows, before the updates and plugin builds that wait.
            at = next((i for i, other in enumerate(self.line) if not other.attended), len(self.line))
            self.line.insert(at, build)
        else:
            self.line.append(build)
        self._wake()
        return build

    def attended(self, data, by=None):
        """One ESPHome action that a person follows on the page (New screen, Firmware & USB, the YAML check), checked
        before it waits so a wrong address or port is said at once."""
        self.firmware.check(data)
        kind = by or ('check' if data.get('action') == 'validate' else 'install')
        same = next((b for b in self.line if b.attended and b.file == data['file'] and b.action == data['action']
                     and b.target == (data.get('target') or '')), None)
        if same:
            return same   # asked twice (a second click): it waits once
        request = {'file': data['file'], 'action': data['action'], **({'target': data['target']} if data.get('target') else {})}

        async def run(build):
            return 'success' if await self.step(request) else 'failed'
        return self.add(kind, data['file'], run, action=data['action'], target=data.get('target') or '', attended=True)

    # ---- what there is ----
    def on_the_way(self, file=None, screen=None, by=None):
        """The builds that run or wait, running first, for a profile, a screen and/or a kind."""
        builds = ([self.running] if self.running else []) + list(self.line)
        return [b for b in builds if (file is None or b.file == file) and (screen is None or b.screen == screen)
                and (by is None or b.by == by)]

    def waiting(self, file):
        """The build that waits for this profile and takes what more is asked for it: never one a person follows."""
        return next((b for b in self.line if b.file == file and not b.attended), None)

    def find(self, number):
        return next((b for b in [*self.on_the_way(), *self.ended] if b.id == number), None)

    def busy(self):
        return bool(self.running or self.line)

    def place(self, build):
        """Which turn a waiting build has: 1 is the next to run."""
        return self.line.index(build) + 1 if build in self.line else 0

    # ---- what changes ----
    def drop(self, build, state='skipped', reason=None):
        """A build that waits leaves the line without running (the rest of a round that failed, a screen that went)."""
        if build in self.line:
            self.line.remove(build)
            build.reason = reason
            self._end(build, state)

    def drop_screen(self, screen):
        for build in [b for b in self.line if b.screen == screen]:
            self.drop(build)

    def renamed(self, old, new):
        for build in self.on_the_way():
            if build.screen == old:
                build.screen = new

    async def step(self, data):
        """One ESPHome action of the build that runs, in the app's build slot. True when it succeeded; a refusal
        (ValueError: a file that went, a wrong address) is the caller's. An install of the build's own profile that
        succeeds is what `installed` says."""
        firmware = self.firmware
        if self.running:
            self.running.stepped = True
        firmware.start(data)
        await firmware.task
        ok = (getattr(firmware, 'job', None) or {}).get('state') == 'success'
        if ok and self.running and data.get('action') == 'install' and data.get('file') == self.running.file:
            self.running.installed = True
        return ok

    # ---- the worker ----
    def _wake(self):
        if self.line and self.running is None and (self.worker is None or self.worker.done()):
            # The first build runs from this moment, so the page never sees it wait for nothing.
            self._begin(self.line.pop(0))
            self.worker = asyncio.get_running_loop().create_task(self._work())
        self._changed()

    def _begin(self, build):
        self.running, build.state, build.started = build, RUNNING, time.time()

    async def _work(self):
        while self.running:
            build = self.running
            state = 'failed'
            try:
                if build.fresh and build.file:
                    await self.firmware.clean_build(build.file)
                state = await build.run(build) or 'success'
            except asyncio.CancelledError:
                state = 'interrupted'
                raise
            except ValueError as error:
                # Refused at its turn: the profile went, an address is no longer right.
                build.reason = error.args[0] if len(error.args) == 1 else str(error)
            except Exception as error:   # a step that broke must not stop the line
                LOG.exception('Build %s of %s broke', build.id, build.file)
                build.reason = type(error).__name__
            finally:
                self.running = None
                self._end(build, state if state in ENDS else 'failed')
            if state == 'failed' and build.round:
                for other in [b for b in self.line if b.round is build.round]:
                    self.drop(other)
            if self.line:
                self._begin(self.line.pop(0))
                self._changed()

    def _end(self, build, state):
        """A build ended: its outcome and log are kept, whoever waits for it is told, the page hears of it. Whatever goes
        wrong here, the build counts as ended (`done`), so nothing waits for it for ever."""
        build.state, build.finished = state, time.time()
        try:
            if build.stepped:
                # Its last step's log and the memory that build had (build_memory): why it was slow, or why it stopped.
                build.logs = list(getattr(self.firmware, 'logs', None) or [])
                job = getattr(self.firmware, 'job', None) or {}
                build.memory = job.get('memory')
                build.where, build.server, build.fallback = job.get('where'), job.get('server'), job.get('fallback')
            self.ended.append(build)
            for end in build.ends:
                try:
                    end(build)
                except Exception:   # one that breaks leaves the others and the line going
                    LOG.exception('After build %s of %s', build.id, build.file)
        finally:
            build.done.set()
            self._changed()

    def changed(self):
        """Something the page shows of the line changed (also ESPHome's step of the build that runs: Firmware)."""
        self._changed()

    def _changed(self):
        notify = getattr(self.manager, 'notify', None)
        if notify:
            notify()
        changed = getattr(getattr(self.manager, 'ha', None), 'changed', None)
        if changed is not None:
            changed.set()

    async def idle(self):
        """Until nothing runs or waits (tests, shutdown)."""
        while self.worker and not self.worker.done():
            await asyncio.shield(self.worker)

    async def close(self):
        """The app stops: what waits is dropped, what runs is stopped (its ESPHome with it)."""
        for build in list(self.line):
            self.drop(build, 'interrupted')
        if self.worker and not self.worker.done():
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass

    # ---- for the page ----
    def view(self, build):
        """A build as the page follows it. While it runs, the ESPHome step it is at (`stage`) and the memory it has."""
        out = {'id': build.id, 'by': build.by, 'file': build.file, 'screen': build.screen, 'action': build.action,
               'target': build.target, 'state': build.state, 'asked': build.asked, 'started': build.started,
               'finished': build.finished, 'phase': build.phase, 'plugins': list(build.plugins['add'])}
        if build.state == WAITING:
            out['place'] = self.place(build)
            # Who builds now: what the page says the build waits for.
            out['after'] = self.running.file if self.running else None
        job = getattr(self.firmware, 'job', None) or {}
        if build.state == RUNNING and build.stepped and job.get('state') == 'running':
            # On the build server: its name and the step it is at (`remote`: bundle, send, queued, build, fetch), or the
            # reason it builds here after all (`fallback`).
            out.update(stage=job.get('stage'), memory=job.get('memory'), where=job.get('where'), server=job.get('server'),
                       remote=job.get('remote'), fallback=job.get('fallback'))
        elif build.state in ENDS:
            out.update(reason=shown(build.reason) if build.reason else None, memory=build.memory, where=build.where,
                       server=build.server, fallback=build.fallback)
        return out

    def payload(self):
        """What runs, what waits (in order) and what ended last (newest first), without logs."""
        return [self.view(build) for build in [*self.on_the_way(), *reversed(self.ended)]]

    def log(self, number):
        """The log of one build: the lines ESPHome writes now for the one that runs, the kept ones for one that ended."""
        build = self.find(number)
        if build is None:
            raise ValueError(t('addon.errors.firmware.build_gone'))
        lines = (list(self.firmware.logs) if build.stepped else []) if build.state == RUNNING else build.logs
        return {'build': self.view(build), 'logs': lines}
