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
- The slot is ESPHome's, not the build's (docs/BUILDS.md, "Building ahead"). A build gives it up while it only waits
  (`handoff`: its screen restarts and is checked, or it waits for its turn to install in a round) and the next build
  compiles meanwhile; its next ESPHome step takes the slot back before anything that waits in the line (`step`,
  `reacquire`). A build that waits beside the line still counts as running for its screen (`aside`).
"""
import asyncio
import collections
import contextvars
import itertools
import logging
import time

from i18n import shown, t

LOG = logging.getLogger('screen_manager')

# The kinds of build, as the page names them (Manager.builds `by`): an update joins anything of its screen that waits,
# since it builds the same profile and does more.
KINDS = ('update', 'plugins', 'icons', 'install', 'check')
WAITING, RUNNING = 'queued', 'running'
# 'retry': it ended without saying anything about its firmware and goes once more at the end of the line (Updater).
ENDS = ('success', 'failed', 'skipped', 'interrupted', 'retry')
# The build whose steps run in this task (BuildQueue._run): a step asks the slot for this build, also after it gave it up.
CURRENT = contextvars.ContextVar('build', default=None)


class Round:
    """Builds that belong together (Update all, the nightly round): one that fails ends the rest of its round."""

    def __init__(self, automatic=False):
        self.automatic, self.builds = automatic, []

    async def wait(self):
        """Until every build of the round ended, also one that joined it later (a screen once more, Updater.run_build)."""
        while not all(build.done.is_set() for build in self.builds):
            await next(build for build in self.builds if not build.done.is_set()).done.wait()


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
        # Brings the icons the screen's plugins file was just written with (screen_icons.py).
        self.icons = by == 'icons'
        self.state, self.phase, self.reason = WAITING, None, None
        self.asked, self.started, self.finished = time.time(), None, None
        # Whether the profile itself went onto the screen (an install of `file` that succeeded, not its bridge's): what a
        # plugin build's outcome follows, also when an update's check afterwards fails.
        self.installed = False
        self.stepped = False  # whether it ran an ESPHome step: then the firmware's job and log are its own
        self.logs, self.memory = [], None
        # The ESPHome step it got to (compile, upload); whether its screen said after it that it runs what was built
        # (True, False, or None when it could not tell); whether a download that did not come was tried once more.
        self.stage, self.verified, self.retried = None, None, False
        # Its try in a round: 2 is the screen once more at the end of the line after a failure that said nothing about
        # its firmware (Updater.run_build); a second such failure is a failure.
        self.attempt = 1
        # It ended while it waited beside the line: its last log and job are its own snapshot, not the slot's.
        self.ended_aside = False
        self.log = None     # the key of its log kept on disk (build_logs.py), from its first ESPHome step
        # Where its compile ran (build_server.py): 'server' or 'here' after a fallback (its reason in `fallback`), None for
        # a build that never asked the server.
        self.where, self.server, self.fallback = None, None, None
        self.ends = []      # called with the build once it ended, whatever the outcome
        self.done = asyncio.Event()
        # The slot: given up while the build only waits (`yielded`, BuildQueue.handoff), given back (`granted`).
        self.yielded, self.granted = asyncio.Event(), asyncio.Event()

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
        self.icons = self.icons or other.icons
        # A plugin taken off now is no longer added, and the other way round.
        self.plugins['add'] = [p for p in self.plugins['add'] if p not in other.plugins['remove']]
        self.plugins['remove'] = [p for p in self.plugins['remove'] if p not in other.plugins['add']]
        self.ends += [end for end in other.ends if end not in self.ends]


class BuildQueue:
    ENDED = 8
    # The lines a build keeps in memory, of all its steps together (the whole log is on disk, build_logs.py).
    LOG_LINES = 600

    def __init__(self, manager):
        self.manager = manager
        self.line, self.running, self.worker = [], None, None
        # Builds that started and gave the slot up while they wait (`aside`), the ones of them that want it back
        # (`returning`, before the line), and each started build's task.
        self.aside, self.returning, self.tasks = [], collections.deque(), {}
        self._wanted = None   # set when something new wants the slot while the worker waits for builds aside
        self._first = None    # the build _wake began, for the worker it starts
        # While the build files are cleaned up (build_files.py) nothing starts: what is asked waits until `release`.
        self.held = False
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
        # The revision the browser read from the chip on the cable goes with it (Firmware.start, docs/CHIP_REVISIONS.md).
        if data.get('chip_revision') is not None:
            request['chip_revision'] = data['chip_revision']

        async def run(build):
            return 'success' if await self.step(request) else 'failed'
        return self.add(kind, data['file'], run, action=data['action'], target=data.get('target') or '', attended=True)

    # ---- what there is ----
    def on_the_way(self, file=None, screen=None, by=None):
        """The builds that run or wait, running first, for a profile, a screen and/or a kind."""
        builds = ([self.running] if self.running else []) + [b for b in self.aside if b is not self.running] + list(self.line)
        return [b for b in builds if (file is None or b.file == file) and (screen is None or b.screen == screen)
                and (by is None or b.by == by)]

    def waiting(self, file):
        """The build that waits for this profile and takes what more is asked for it: never one a person follows."""
        return next((b for b in self.line if b.file == file and not b.attended), None)

    def find(self, number):
        return next((b for b in [*self.on_the_way(), *self.ended] if b.id == number), None)

    def busy(self):
        return bool(self.running or self.line or self.tasks)

    def hold(self):
        """Nothing starts until `release` (the build files are being cleaned up); what is asked meanwhile waits."""
        self.held = True

    def release(self):
        self.held = False
        self._wake()

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
        build = CURRENT.get() or self.running
        if build is not None and build is not self.running and build in self.tasks:
            await self.reacquire(build)   # it gave the slot up while it waited: back before the line
        new_log = build is not None and build.log is None
        if build is not None:
            self._keep_log(build)   # before start: what start writes first is the build's too
        try:
            firmware.start(data)
        except ValueError:
            # Refused before anything ran (a file that went, a wrong address): no step, no log of its own.
            self._detach_log(build, discard=new_log)
            raise
        if build is not None:
            build.stepped = True
        try:
            await firmware.task
        finally:
            if build is not None:
                # Every step's lines, in order: a build made ahead keeps its compile log as well as its upload's.
                build.logs = (build.logs + list(getattr(firmware, 'logs', None) or []))[-self.LOG_LINES:]
        ok = (getattr(firmware, 'job', None) or {}).get('state') == 'success'
        if ok and build is not None and data.get('action') in ('install', 'upload') and data.get('file') == build.file:
            build.installed = True
        return ok

    def handoff(self, build=None):
        """The build gives the slot up while it only waits (its screen restarts and is checked, or it waits for its turn
        to install in a round): the next build compiles meanwhile. What it wrote is kept with it; its next step takes the
        slot back (`step`)."""
        build = build or CURRENT.get()
        if build is None or self.running is not build:
            return
        self._snapshot(build)
        self._detach_log(build)
        if build not in self.aside:
            self.aside.append(build)
        self.running = None
        build.granted.clear()
        build.yielded.set()
        self._changed()

    async def reacquire(self, build):
        """The slot back for a build that gave it up, before anything that waits in the line: as soon as the build that
        holds it now gives it up or ends (an install a person follows holds it through its whole job)."""
        if self.running is build:
            return
        build.granted.clear()
        if build not in self.returning:
            self.returning.append(build)
        self._poke()
        await build.granted.wait()
        if build in self.aside:
            self.aside.remove(build)
        if build.log:   # its log goes on in the same file
            logs, tee = getattr(self.manager, 'build_logs', None), getattr(self.firmware, 'logs', None)
            if logs is not None and hasattr(tee, 'sink'):
                key = build.log
                tee.sink = lambda line: logs.line(key, line)
        self._changed()

    def _detach_log(self, build, discard=False):
        """The slot's log no longer goes to the build's file; a file just started for a step that never ran goes."""
        tee = getattr(self.firmware, 'logs', None)
        if getattr(tee, 'sink', None) is not None:
            tee.sink = None
        logs = getattr(self.manager, 'build_logs', None)
        if discard and build is not None and build.log and logs is not None:
            logs.discard(build.log)
            build.log = None

    def _snapshot(self, build):
        """What the build's last ESPHome step left (its job: memory, where it built, the step it got to), kept with it
        before another build's step replaces it. Its lines are kept by `step` as each step ends."""
        if not build.stepped:
            return
        job = getattr(self.firmware, 'job', None) or {}
        build.memory = job.get('memory')
        build.where, build.server, build.fallback = job.get('where'), job.get('server'), job.get('fallback')
        build.stage = job.get('stage')

    def _keep_log(self, build):
        """The build's log goes to disk from its first ESPHome step on (build_logs.py), every line as it comes."""
        logs = getattr(self.manager, 'build_logs', None)
        tee = getattr(self.firmware, 'logs', None)
        if logs is None:
            return
        if build.log is not None:
            if hasattr(tee, 'sink') and tee.sink is None:
                key = build.log
                tee.sink = lambda line: logs.line(key, line)
            return
        try:
            build.log = logs.start(build)
        except OSError as error:
            LOG.warning('Build %s: log not kept on disk (%s)', build.id, error)
            return
        if hasattr(tee, 'sink'):
            key = build.log
            tee.sink = lambda line: logs.line(key, line)

    # ---- the worker ----
    def _wake(self):
        if self.worker is None or self.worker.done():
            first = self._pick()
            if first is not None:
                # The first build runs from this moment, so the page never sees it wait for nothing.
                if first not in self.tasks:
                    self._begin(first)
                self._first = first
                self.worker = asyncio.get_running_loop().create_task(self._work())
        else:
            self._poke()
        self._changed()

    def _poke(self):
        if self._wanted is not None:
            self._wanted.set()
        elif self.worker is None or self.worker.done():
            self._wake()

    def _begin(self, build):
        self.running, build.state, build.started = build, RUNNING, time.time()

    def _pick(self):
        """Who has the slot next: a build that gave it up and wants it back, else the first that waits in the line."""
        while self.returning:
            build = self.returning.popleft()
            if build in self.tasks:
                return build
        if self.line and not self.held:
            # Never a second build of a profile whose build waits beside the line (its screen is being checked, or it
            # waits for its turn to install): it would install over it, or empty its build folder. It goes after.
            busy = {b.file for b in self.aside if b.file}
            for i, build in enumerate(self.line):
                if build.file not in busy:
                    return self.line.pop(i)
        return None

    async def _work(self):
        while True:
            holder, self._first = (self._first or self._pick()), None
            if holder is None:
                if not self.tasks:
                    break
                # Nothing for the slot now, builds wait beside it: until one ends or something wants the slot.
                self._wanted = asyncio.Event()
                waiting = asyncio.ensure_future(self._wanted.wait())
                try:
                    await asyncio.wait([waiting, *self.tasks.values()], return_when=asyncio.FIRST_COMPLETED)
                finally:
                    waiting.cancel()
                    self._wanted = None
                continue
            holder.yielded.clear()
            if holder in self.tasks:
                self.running = holder
                holder.granted.set()
            else:
                if holder.state != RUNNING:
                    self._begin(holder)
                else:
                    self.running = holder
                self._changed()
                self.tasks[holder] = asyncio.get_running_loop().create_task(self._run(holder))
            # Until it gives the slot up (handoff) or ends.
            await holder.yielded.wait()
            if self.running is holder:
                self.running = None
        # Nothing more to build: what the builds left is measured, or cleaned up when that is on (build_files.py).
        files = getattr(self.manager, 'build_files', None)
        if files is not None:
            files.after_line()

    async def _run(self, build):
        CURRENT.set(build)
        state = 'failed'
        try:
            # A screen's plugins file is written again first: the icons in it follow this app's fixed set.
            icons = getattr(self.manager, 'icons', None)
            if icons:
                icons.before_build(build)
            if build.fresh and build.file:
                await self.firmware.clean_build(build.file)
            state = await build.run(build) or 'success'
        except asyncio.CancelledError:
            state = 'interrupted'
        except ValueError as error:
            # Refused at its turn: the profile went, an address is no longer right.
            build.reason = error.args[0] if len(error.args) == 1 else str(error)
        except Exception as error:   # a step that broke must not stop the line
            LOG.exception('Build %s of %s broke', build.id, build.file)
            build.reason = type(error).__name__
        finally:
            holding = self.running is build
            # It ended beside the line: what it kept is its own; its ESPHome log is not the slot's.
            build.ended_aside = not holding
            if build in self.aside:
                self.aside.remove(build)
            self.tasks.pop(build, None)
            if holding:
                self.running = None
            self._end(build, state if state in ENDS else 'failed')
            build.yielded.set()
            if state == 'failed' and build.round:
                for other in [b for b in self.line if b.round is build.round]:
                    self.drop(other)
            self._poke()

    def _end(self, build, state):
        """A build ended: its outcome and log are kept, whoever waits for it is told, the page hears of it. Whatever goes
        wrong here, the build counts as ended (`done`), so nothing waits for it for ever."""
        build.state, build.finished = state, time.time()
        try:
            if build.stepped and not build.ended_aside:
                # Its last step's log and the memory that build had (build_memory): why it was slow, or why it stopped.
                # The ESPHome step it got to (compile, upload): where a build that failed stopped (build_failures.failure_kind).
                self._snapshot(build)
            if build.log:
                tee = getattr(self.firmware, 'logs', None)
                if getattr(tee, 'sink', None) is not None and not build.ended_aside:
                    tee.sink = None
                logs = getattr(self.manager, 'build_logs', None)
                if logs is not None:
                    logs.end(build)
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
        """Until nothing runs, waits beside the line or waits in it (tests, shutdown)."""
        while (self.worker and not self.worker.done()) or self.tasks:
            if self.worker and not self.worker.done():
                await asyncio.shield(self.worker)
            elif self.tasks:
                await asyncio.wait(list(self.tasks.values()))

    async def close(self):
        """The app stops: what waits is dropped, what runs is stopped (its ESPHome with it), also beside the line."""
        for build in list(self.line):
            self.drop(build, 'interrupted')
        started = list(self.tasks.items())
        for _, task in started:
            task.cancel()
        if started:
            await asyncio.gather(*(task for _, task in started), return_exceptions=True)
        if self.worker and not self.worker.done():
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass
        # A build that began but whose steps had not started yet ends with the rest.
        # A build that began but whose steps never ran (its task was stopped before it started) ends with the rest.
        for build in [self.running, self._first, *(b for b, _ in started)]:
            if build is not None and not build.done.is_set():
                self.tasks.pop(build, None)
                if build in self.aside:
                    self.aside.remove(build)
                self.running = None if self.running is build else self.running
                self._end(build, 'interrupted')
        self._first = None

    # ---- for the page ----
    def view(self, build):
        """A build as the page follows it. While it runs, the ESPHome step it is at (`stage`) and the memory it has."""
        out = {'id': build.id, 'by': build.by, 'file': build.file, 'screen': build.screen, 'action': build.action,
               'target': build.target, 'state': build.state, 'asked': build.asked, 'started': build.started,
               'finished': build.finished, 'phase': build.phase, 'plugins': list(build.plugins['add']), 'log': build.log}
        if build.state == WAITING:
            out['place'] = self.place(build)
            # Who builds now: what the page says the build waits for.
            out['after'] = self.running.file if self.running else None
        job = getattr(self.firmware, 'job', None) or {}
        if build.state == RUNNING and build.stepped and job.get('state') == 'running' and self.running is build:
            # On the build server: its name and the step it is at (`remote`: bundle, send, queued, build, fetch), or the
            # reason it builds here after all (`fallback`).
            out.update(stage=job.get('stage'), memory=job.get('memory'), where=job.get('where'), server=job.get('server'),
                       remote=job.get('remote'), fallback=job.get('fallback'))
        elif build.state in ENDS:
            out.update(reason=shown(build.reason) if build.reason else None, memory=build.memory, where=build.where,
                       server=build.server, fallback=build.fallback, stage=build.stage, verified=build.verified,
                       retried=build.retried)
        return out

    def payload(self):
        """What runs, what waits (in order) and what ended last (newest first), without logs."""
        return [self.view(build) for build in [*self.on_the_way(), *reversed(self.ended)]]

    def log(self, number):
        """The log of one build: the lines ESPHome writes now for the one that runs, the kept ones for one that ended."""
        build = self.find(number)
        if build is None:
            raise ValueError(t('addon.errors.firmware.build_gone'))
        lines = (list(self.firmware.logs) if build.stepped and self.running is build else build.logs) \
            if build.state == RUNNING else build.logs
        return {'build': self.view(build), 'logs': lines}
