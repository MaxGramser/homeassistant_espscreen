"""Every build's log, kept on disk (docs/BUILDS.md, "Kept logs").

The build line keeps the last builds in memory with the last lines ESPHome wrote (build_queue.py); that is gone when the
app restarts, and a build the app restarted during is the one whose log matters most. So every build that runs an ESPHome
step writes its log here, line by line as ESPHome writes it (`Tee`), into `<data>/build_logs/<key>.log`, with what it was
in `<key>.json` beside it: the build's kind, profile, screen, plugins, when it started and how it ended. A log whose build
never ended (the app stopped during it) reads as interrupted. The newest `KEEP` stay; older ones go when a new one starts.

What a build shows of its log in the page (the line's `log`), a plugin that did not build (its `log`) and Firmware &
USB's list all name a log by its key, and api/firmware/logs/{key} sends it as a file. Lines are redacted before they get
here (Firmware.redact), so a log holds no Wi-Fi password or key.
"""
import collections
import json
import logging
import re
import time
from pathlib import Path

import atomic
from i18n import t

LOG = logging.getLogger('screen_manager')

KEY = re.compile(r'^[0-9]{8}-[0-9]{6}-[a-z0-9_.-]{1,80}$')


class Tee(collections.deque):
    """Firmware's log (the last lines, in memory) that also hands every line to `sink` while a build is written down."""

    def __init__(self, maxlen):
        super().__init__(maxlen=maxlen)
        self.sink = None

    def append(self, line):
        super().append(line)
        if self.sink is not None:
            try:
                self.sink(line)
            except Exception:   # a full disk never stops a build
                LOG.exception('Build log line not kept')
                self.sink = None


class BuildLogs:
    KEEP = 40

    def __init__(self, data):
        self.folder = Path(data) / 'build_logs'
        self._open = {}   # key -> open file of a build that runs

    # ---- writing ----
    def start(self, build):
        """A build runs its first ESPHome step: its log file and what it is. Returns the key."""
        self.folder.mkdir(parents=True, exist_ok=True)
        started = build.started or time.time()
        stem = re.sub(r'[^a-z0-9_.-]+', '-', Path(build.file or 'build').stem.lower()).strip('-') or 'build'
        base = time.strftime('%Y%m%d-%H%M%S', time.localtime(started)) + '-' + stem[:70]
        key, n = base, 1
        while (self.folder / f'{key}.log').exists():
            n += 1
            key = f'{base}-{n}'
        self._write_meta(key, {'key': key, 'by': build.by, 'file': build.file, 'screen': build.screen,
                               'plugins': list(build.plugins['add']), 'started': started, 'state': 'running'})
        handle = (self.folder / f'{key}.log').open('a', encoding='utf-8')
        handle.write(f'# {build.by} build of {build.file}, started {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started))}\n')
        handle.flush()
        self._open[key] = handle
        self.prune()
        return key

    def line(self, key, text):
        handle = self._open.get(key)
        if handle is not None:
            handle.write(str(text).rstrip('\n') + '\n')
            handle.flush()

    def end(self, build):
        """The build ended: how, and why, at the end of its log and in what it is."""
        key = getattr(build, 'log', None)
        if not key:
            return
        handle = self._open.pop(key, None)
        reason = str(build.reason) if build.reason else None
        try:
            if handle is not None:
                handle.write(f'# Ended: {build.state}{f" ({reason})" if reason else ""}\n')
                handle.close()
            meta = self._read_meta(key) or {'key': key}
            self._write_meta(key, {**meta, 'state': build.state, 'reason': reason, 'finished': build.finished or time.time()})
        except OSError as error:
            LOG.warning('Build log %s not closed: %s', key, error)

    def discard(self, key):
        """A log started for a step that never ran: gone, files and all."""
        handle = self._open.pop(key, None)
        if handle is not None:
            handle.close()
        for suffix in ('.log', '.json'):
            try:
                (self.folder / f'{key}{suffix}').unlink()
            except OSError:
                pass

    def _write_meta(self, key, meta):
        atomic.write_json(self.folder / f'{key}.json', meta)

    def _read_meta(self, key):
        try:
            return json.loads((self.folder / f'{key}.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def _newest_first(self):
        """The kept logs by when their build started, newest first (several may start in one second)."""
        def started(path):
            meta = self._read_meta(path.stem) or {}
            try:
                return float(meta.get('started') or path.stat().st_mtime)
            except (OSError, TypeError, ValueError):
                return 0.0
        return sorted(self.folder.glob('*.log'), key=lambda p: (started(p), p.name), reverse=True)

    def prune(self):
        logs = self._newest_first()
        for old in logs[self.KEEP:]:
            if old.stem in self._open:
                continue
            for path in (old, old.with_suffix('.json')):
                try:
                    path.unlink()
                except OSError:
                    pass

    # ---- reading ----
    def listed(self):
        """Every kept log, newest first: what it was and how it ended. One still marked running without a build that
        writes it was cut off by a restart: interrupted."""
        out = []
        if not self.folder.is_dir():
            return out
        for path in self._newest_first():
            key = path.stem
            meta = self._read_meta(key) or {'key': key}
            if meta.get('state', 'running') == 'running' and key not in self._open:
                meta['state'] = 'interrupted'
            try:
                meta['size'] = path.stat().st_size
            except OSError:
                continue
            out.append({**meta, 'key': key})
        return out

    def latest(self, file):
        """The newest kept log of a profile, or None."""
        return next((item['key'] for item in self.listed() if item.get('file') == file), None)

    def path(self, key):
        """The file of a kept log by its key; ValueError for a key that names none."""
        if not isinstance(key, str) or not KEY.match(key):
            raise ValueError(t('addon.errors.firmware.log_gone'))
        path = self.folder / f'{key}.log'
        if not path.is_file():
            raise ValueError(t('addon.errors.firmware.log_gone'))
        return path
