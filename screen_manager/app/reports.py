"""My screen doesn't work right (app 0.4.91): one troubleshooting report per screen, read before anything leaves.

The owner presses one button on the screen's page. The app then gathers, in the background, everything a developer
asks for one by one today and nobody can find: the board and every version, the screen's own YAML and plugins, the
crash the screen kept from its previous boot and a minute of its live log, Home Assistant's log lines about this
screen, Home Assistant's own diagnostics of the ESPHome device, the app's own log and the last build. All of it goes
through redaction.py (keys, addresses, Wi-Fi names, the screen's names) and into one zip under /data/reports. The page
lists every file, shows any of them in full, offers the zip to download, and only after a consent per report sends it
to the Tessera website with the board's feedback key as the bearer (feedback.py), with a note and, if the owner wants a
question back, an e-mail address. The website answers a reference (TR-XXXXXX) to quote on GitHub or Discord, and keeps
the report for its retention period.

Depth (docs/REPORTS.md): `basic` holds what is about this screen alone; `full` is an opt-in on the page that adds the
screen's pages and tiles with their entity ids, every ESPHome log line of every screen and every warning Home Assistant
kept, and the whole storage of the ESPHome entry. The person is told what that adds before choosing it.

Crashes (CrashWatch): a screen that reboots changes its "Last boot" sensor. The app then connects to it over the native
API for a few seconds, as the first log subscriber, and keeps what ESPHome stored in .noinit RAM about the crash (reason,
PC, backtrace) plus the debug component's reset reason, in /data/crashes.json, decoded through addr2line when the ELF
of that build is here. The page shows the last crash; the report carries all of them. Never more than one capture
per screen per CAPTURE_SPACING seconds.

What a build server built has no ELF here (build_server.SKIP_SUFFIXES): such a crash stays a list of addresses, and the
report says so (warning no_elf)."""
import asyncio
import collections
import contextlib
import glob
import hashlib
import io
import json
import logging
import os
import re
import secrets
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout, FormData

import atomic
import feedback
import redaction
from i18n import t

LOG = logging.getLogger('screen_manager')

REPORTS_URL = f'{feedback.API}/reports'
PRIVACY_URL = feedback.PRIVACY_URL
DEPTHS = ('basic', 'full')
KEEP = 5                     # reports kept on disk per app, oldest removed first
ZIP_MAX = 8 * 1024 * 1024    # what the website takes
NOTE_MAX = 2000
EMAIL_TEXT = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')
CAPTURE_SECONDS = 45         # of the screen's live log in a report
CRASH_SECONDS = 8            # to read the crash record and the reset reason after a reboot
LINES_MAX = 3000             # of any one log file
HA_LOG_LINES = 2000
ADDON_LOG_LINES = 1500
CAPTURE_SPACING = 300
CRASHES_KEPT = 10
WATCH_INTERVAL = 30
WEEK = 7 * 86400
API_PORT = 6053
STEPS = ('identity', 'profile', 'crash', 'screen_log', 'ha_log', 'addon_log', 'build_log', 'zip')
# Home Assistant's own log line: time, level, thread, logger name, message. What has no such head continues the line
# before it (a traceback).
HA_LINE = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) (\w+) \(([^)]*)\) \[([^\]]+)\] (.*)$')
SCREEN_LOGGERS = ('homeassistant.components.esphome', 'aioesphomeapi', 'noiseprotocol', 'bleak_esphome')
ADDRESS = re.compile(r'0x4[0-9a-fA-F]{7}')
# A log line's prefix is `[E][esp32.crash:437]:` on the screen (a colon after the brackets) and `[E][esp32.crash:437]`
# in older logs and tests: the keyword follows either.
CRASH_LINE = re.compile(r'CRASH DETECTED ON PREVIOUS BOOT|THE MAIN LOOP AT THE LAST TASK WATCHDOG|INTERNAL RAM ON PREVIOUS BOOT|ABORT ON PREVIOUS BOOT'
                        r'|^\s*(?:\[[^\]]*\]\s*)*:?\s*(?:Reason|PC|EXCVADDR|MTVAL|BT\d+|LOOP\d+|Backtrace|MEPC|RA|Use|Lowest|Failed|Details|AT\d+)\s*:'
                        r'|assert failed: 0x4|Guru Meditation|abort\(\) was called|Panic|rst:0x|Reset Reason|ELF file SHA256|Crashed core')
RESET_LINE = re.compile(r'Reset Reason:\s*(.+?)\s*$')
REASON_LINE = re.compile(r'Reason:\s*(.+?)\s*$')
ELF_LINE = re.compile(r'ELF file SHA256:\s*([0-9a-f]+)')
HARMLESS_RESETS = ('power on', 'software reset', 'reboot request', 'deep sleep', 'unknown', 'usb', 'jtag', 'external')


def now_iso(clock=time.time):
    return datetime.fromtimestamp(clock(), timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def new_id(clock=time.time):
    return f'r-{datetime.fromtimestamp(clock(), timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}'


def clean_note(note):
    if note is None:
        return None
    if not isinstance(note, str):
        raise ValueError('note')
    note = note.strip()
    if len(note) > NOTE_MAX:
        raise ValueError('note')
    return note or None


def clean_email(email):
    if email in (None, ''):
        return None
    if not isinstance(email, str) or len(email) > 254 or not EMAIL_TEXT.fullmatch(email.strip()):
        raise ValueError('email')
    return email.strip()


def strip_ansi(text):
    return redaction.ANSI.sub('', text)


def ha_log_lines(text, names, loggers=SCREEN_LOGGERS, everything=False, limit=HA_LOG_LINES):
    """The lines of Home Assistant's log about one screen: those of the ESPHome integration and its library that name
    the screen (its device name, friendly name, node, host or MAC), with their continuation lines; `everything` keeps
    every line of those loggers (depth full). The last `limit` lines."""
    wanted = tuple(n.lower() for n in names if isinstance(n, str) and len(n) >= 3)
    out, keeping = [], False
    for line in text.splitlines():
        head = HA_LINE.match(line)
        if head:
            logger, message = head.group(4), head.group(5)
            keeping = logger.startswith(loggers) and (everything or any(n in message.lower() for n in wanted))
        if keeping:
            out.append(line)
    return out[-limit:]


def system_log_text(entries, everything=False):
    """Home Assistant's kept warnings and errors (websocket system_log/list) as text, newest first as it gives them."""
    lines = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get('name') or '')
        if not everything and not name.startswith(SCREEN_LOGGERS):
            continue
        when = datetime.fromtimestamp(float(entry.get('timestamp') or 0), timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        source = entry.get('source') or []
        lines.append(f"{when} {entry.get('level')} [{name}] x{entry.get('count', 1)} {':'.join(str(s) for s in source)}")
        for message in entry.get('message') or []:
            lines.append(f'  {message}')
        if entry.get('exception'):
            lines.extend('  ' + l for l in str(entry['exception']).splitlines())
    return '\n'.join(lines)


def _entries_about(entries, names):
    """system_log entries with only the messages that name the screen (an entry groups every screen's lines)."""
    wanted = tuple(n.lower() for n in names if isinstance(n, str) and len(n) >= 3)
    out = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        messages = [m for m in entry.get('message') or [] if any(w in str(m).lower() for w in wanted)]
        if messages or (not entry.get('message') and str(entry.get('name', '')).startswith(SCREEN_LOGGERS)):
            out.append({**entry, 'message': messages})
    return out


def crash_lines(lines):
    """The crash block and the reset reason out of a screen's log, as the first subscriber after a reboot sees them."""
    return [l for l in lines if CRASH_LINE.search(l)]


def crash_summary(lines, clock=time.time):
    """{'at', 'reason', 'reset', 'elf', 'lines'} from a screen's log lines, or None when they hold no crash: a reset
    reason ESPHome calls harmless (power on, a reboot it asked for) is not a crash."""
    kept = crash_lines(lines)
    reason = reset = elf = None
    for line in kept:
        m = REASON_LINE.search(line)
        if m and 'Reset Reason' not in line and reason is None:
            reason = m.group(1)
        m = RESET_LINE.search(line)
        if m:
            reset = m.group(1)
        m = ELF_LINE.search(line)
        if m:
            elf = m.group(1)
    crashed = any('CRASH DETECTED' in l or 'assert failed' in l or 'Guru Meditation' in l or 'abort()' in l for l in kept)
    if not crashed and (reset is None or reset.lower().startswith(HARMLESS_RESETS)):
        return None
    return {'at': now_iso(clock), 'reason': reason or reset or 'unknown', 'reset': reset, 'elf': elf, 'lines': kept[:80]}


class Decoder:
    """addr2line over the ELF of a screen's own build (firmware.py keeps it under /data/build/<stem>/build or
    .pioenvs/<node>), with the toolchain ESP-IDF wrote into its CMakeCache; a build server's build left no ELF."""

    def __init__(self, data):
        self.data = Path(data)

    def elf(self, stem):
        for pattern in (f'build/{stem}/build/firmware.elf', f'build/{stem}/.pioenvs/*/firmware.elf', f'build/{stem}/build/*.elf'):
            found = sorted(glob.glob(str(self.data / pattern)))
            if found:
                return Path(found[0])
        return None

    def addr2line(self, stem, chip=''):
        cache = self.data / 'build' / stem / 'build' / 'CMakeCache.txt'
        with contextlib.suppress(OSError, UnicodeDecodeError):
            for line in cache.read_text().splitlines():
                if line.startswith('CMAKE_ADDR2LINE:') and '=' in line:
                    path = line.split('=', 1)[1].strip()
                    if path and Path(path).exists():
                        return path
        family = 'riscv32' if chip in ('esp32p4', 'esp32c6', 'esp32c3', 'esp32h2') else 'xtensa'
        idf = os.environ.get('ESPHOME_ESP_IDF_PREFIX', str(self.data / 'idf'))
        for root in (idf, str(Path.home() / '.platformio' / 'packages')):
            found = sorted(glob.glob(f'{root}/**/bin/{family}-*-addr2line', recursive=True))
            if found:
                return found[-1]
        return None

    @staticmethod
    def elf_sha(path):
        digest = hashlib.sha256()
        with open(path, 'rb') as f:
            for block in iter(lambda: f.read(1 << 20), b''):
                digest.update(block)
        return digest.hexdigest()

    async def decode(self, stem, chip, lines, expected_sha=None):
        """['0x4...: function at file:line', ...] for every address in the crash lines, or [] without an ELF or a tool;
        a mismatching ELF (another build than the one that crashed) decodes nothing and says why."""
        elf = self.elf(stem) if stem else None
        if elf is None:
            return [], 'no_elf'
        if expected_sha and not self.elf_sha(elf).startswith(expected_sha):
            return [], 'elf_mismatch'
        tool = self.addr2line(stem, chip)
        if tool is None:
            return [], 'no_addr2line'
        addresses = []
        for line in lines:
            for address in ADDRESS.findall(line):
                if address not in addresses:
                    addresses.append(address)
        if not addresses:
            return [], None
        try:
            process = await asyncio.create_subprocess_exec(tool, '-pfiaC', '-e', str(elf), *addresses[:64],
                                                           stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(process.communicate(), 30)
        except (OSError, asyncio.TimeoutError):
            return [], 'decode_failed'
        decoded = [l.strip() for l in out.decode('utf-8', 'replace').splitlines() if l.strip() and '?? ??:0' not in l]
        return decoded, None


class LogBuffer(logging.Handler):
    """The app's own last lines, so the report has them even where the Supervisor's /addons/self/logs says no."""

    def __init__(self, size=ADDON_LOG_LINES):
        super().__init__()
        self.lines = collections.deque(maxlen=size)
        self.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s'))

    def emit(self, record):
        with contextlib.suppress(Exception):
            self.lines.append(self.format(record))


async def screen_log(host, key, seconds, *, port=API_PORT, dump_config=True, level='DEBUG', limit=LINES_MAX, name='tessera'):
    """Up to `seconds` of a screen's log over the native API, from the first line (ESPHome's kept crash record goes to
    the first subscriber after a reboot, then the config dump with the reset reason). (lines, device_info or None)."""
    from aioesphomeapi import APIClient, LogLevel
    client = APIClient(host, port, None, noise_psk=key or None, client_info=f'ESP Screen Manager {name}')
    lines, info = [], None
    done = asyncio.Event()

    def on_log(message):
        text = message.message.decode('utf-8', 'replace') if isinstance(message.message, bytes) else str(message.message)
        for line in strip_ansi(text).splitlines():
            if line.strip():
                lines.append(line)
        if len(lines) >= limit:
            done.set()

    started = time.monotonic()
    await client.connect(login=True)
    try:
        with contextlib.suppress(Exception):
            info = await client.device_info()
        client.subscribe_logs(on_log, log_level=getattr(LogLevel, f'LOG_LEVEL_{level}'), dump_config=dump_config)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(done.wait(), seconds)
    finally:
        with contextlib.suppress(Exception):
            await client.disconnect()
    LOG.info('Read %d log lines of %s in %.0f s', len(lines), name, time.monotonic() - started)
    return lines, info


def device_info_dict(info):
    if info is None:
        return {}
    keys = ('name', 'friendly_name', 'esphome_version', 'compilation_time', 'model', 'manufacturer', 'project_name',
            'project_version', 'api_encryption_supported', 'has_deep_sleep')
    return {key: getattr(info, key, None) for key in keys if getattr(info, key, None) not in (None, '')}


class CrashStore:
    """/data/crashes.json: per inbox the crashes seen, newest last, with the "Last boot" value they followed."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = {}
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, dict) and data.get('version') == 1:
                self.data = data.get('screens') or {}
        except (OSError, ValueError):
            self.data = {}

    def save(self):
        with contextlib.suppress(OSError):
            atomic.write_json(self.path, {'version': 1, 'screens': self.data})

    def record(self, inbox):
        return self.data.setdefault(inbox, {'boot': None, 'crashes': [], 'captured': 0})

    def add(self, inbox, crash):
        record = self.record(inbox)
        record['crashes'] = (record['crashes'] + [crash])[-CRASHES_KEPT:]
        self.save()

    def last(self, inbox, clock=time.time):
        """The last crash of a screen as the page shows it, or None."""
        crashes = self.record(inbox).get('crashes') or []
        if not crashes:
            return None
        last = crashes[-1]
        week = [c for c in crashes if _epoch(c.get('at')) >= clock() - WEEK]
        return {'at': last.get('at'), 'reason': last.get('reason'), 'decoded': last.get('decoded') or [], 'count': len(week)}

    def forget(self, inbox):
        if self.data.pop(inbox, None) is not None:
            self.save()


def _card_kinds(tiles):
    """What the tiles are, counted by kind: an entity's domain, a plugin's or a content tile's kind."""
    kinds = collections.Counter()
    for tile in tiles:
        if not isinstance(tile, dict):
            continue
        entity = tile.get('entity')
        content = tile.get('content') if isinstance(tile.get('content'), dict) else {}
        kind = entity.split('.', 1)[0] if isinstance(entity, str) and '.' in entity else content.get('kind') or ('plugin' if tile.get('key') else '?')
        kinds[str(kind)] += 1
    return dict(sorted(kinds.items()))


def _count(value):
    """How many: a list's length, a number as it is (a layout keeps its page count as a number)."""
    if isinstance(value, (list, tuple, dict)):
        return len(value)
    return value if isinstance(value, int) else None


def _epoch(iso):
    try:
        return datetime.fromisoformat(str(iso).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError):
        return 0


class Report:
    def __init__(self, id, inbox, depth, clock=time.time):
        self.id, self.inbox, self.depth = id, inbox, depth
        self.state, self.step, self.progress = 'collecting', STEPS[0], 0.0
        self.files, self.summary, self.warnings = [], {}, []
        self.texts = {}          # name -> text, in order of the zip
        self.size, self.reference, self.sent_at, self.expires_at, self.error = 0, None, None, None, None
        self.created = clock()
        self.path = None
        self.task = None

    def view(self):
        return {'id': self.id, 'screen': self.inbox, 'depth': self.depth, 'state': self.state, 'step': self.step,
                'progress': round(self.progress, 2), 'files': self.files, 'summary': self.summary, 'warnings': self.warnings,
                'size': self.size, 'reference': self.reference, 'sent_at': self.sent_at, 'expires_at': self.expires_at,
                'error': self.error}


class Reports:
    def __init__(self, manager, data, clock=time.time, transport=None):
        self.manager, self.data, self.clock = manager, Path(data), clock
        self.dir = self.data / 'reports'
        self.reports = {}
        self.crashes = CrashStore(self.data / 'crashes.json')
        self.decoder = Decoder(self.data)
        self.buffer = LogBuffer()
        self.transport = transport or self._post
        self.settings_path = self.dir / 'settings.json'
        self.settings = self._read_settings()
        self.index_path = self.dir / 'index.json'
        self.watch_task = None
        self._session = None
        logging.getLogger().addHandler(self.buffer)
        self._load_index()

    # ---- the reports on disk, so a reference survives a restart of the app
    def _load_index(self):
        try:
            rows = json.loads(self.index_path.read_text())
        except (OSError, ValueError):
            return
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or row.get('state') not in ('ready', 'sent'):
                continue
            path = self.dir / f"{row.get('id')}.zip"
            if not path.is_file():
                continue
            report = Report(row['id'], row.get('screen'), row.get('depth', 'basic'), self.clock)
            report.created = row.get('created') or report.created
            report.state, report.step, report.progress = row['state'], 'zip', 1.0
            report.files, report.summary, report.warnings = row.get('files') or [], row.get('summary') or {}, row.get('warnings') or []
            report.size, report.reference = row.get('size') or path.stat().st_size, row.get('reference')
            report.sent_at, report.expires_at, report.path = row.get('sent_at'), row.get('expires_at'), path
            try:
                with zipfile.ZipFile(path) as bundle:
                    report.texts = {name: bundle.read(name).decode('utf-8', 'replace') for name in bundle.namelist()}
            except (OSError, zipfile.BadZipFile):
                continue
            self.reports[report.id] = report

    def _save_index(self):
        rows = [{'id': r.id, 'screen': r.inbox, 'depth': r.depth, 'state': r.state, 'created': r.created, 'files': r.files,
                 'summary': r.summary, 'warnings': r.warnings, 'size': r.size, 'reference': r.reference, 'sent_at': r.sent_at,
                 'expires_at': r.expires_at} for r in self.reports.values() if r.state in ('ready', 'sent')]
        with contextlib.suppress(OSError):
            self.dir.mkdir(parents=True, exist_ok=True)
            atomic.write_json(self.index_path, rows)

    # ---- settings (the remembered e-mail)
    def _read_settings(self):
        try:
            data = json.loads(self.settings_path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def remember(self, **values):
        self.settings.update(values)
        with contextlib.suppress(OSError):
            self.dir.mkdir(parents=True, exist_ok=True)
            atomic.write_json(self.settings_path, self.settings)

    # ---- the page
    def status(self, inbox, screen):
        profile, _ = self.manager.updates.resolve(screen)
        blockers = []
        if profile is None:
            blockers.append('no_profile')
        if any(r.inbox == inbox and r.state == 'collecting' for r in self.reports.values()):
            blockers.append('collecting')
        last = next((r for r in sorted(self.reports.values(), key=lambda r: r.created, reverse=True)
                     if r.inbox == inbox and r.state == 'sent'), None)
        return {'ready': not blockers, 'blockers': blockers, 'retention_days': self.settings.get('retention_days', 30),
                'last': {'id': last.id, 'reference': last.reference, 'sent_at': last.sent_at, 'depth': last.depth} if last else None,
                'crash': self.crashes.last(inbox, self.clock), 'email': self.settings.get('email'), 'privacy_url': PRIVACY_URL}

    def start(self, inbox, screen, depth):
        if depth not in DEPTHS:
            raise ValueError(t('addon.errors.report.depth'))
        status = self.status(inbox, screen)
        if 'collecting' in status['blockers']:
            raise ValueError(t('addon.errors.report.busy'))
        if 'no_profile' in status['blockers']:
            raise ValueError(t('addon.errors.report.no_profile'))
        # One unsent report per screen: a new one takes the place of the last that was never sent.
        for old in [r for r in self.reports.values() if r.inbox == inbox and r.state != 'sent']:
            self.delete(old.id)
        report = Report(new_id(self.clock), inbox, depth, self.clock)
        self.reports[report.id] = report
        report.task = asyncio.ensure_future(self._collect(report, screen))
        return report.id

    def get(self, id):
        report = self.reports.get(id)
        if report is None:
            raise ValueError(t('addon.errors.report.not_found'))
        return report

    def file(self, id, name):
        report = self.get(id)
        if name not in report.texts:
            raise ValueError(t('addon.errors.report.not_found'))
        return report.texts[name]

    def zip_bytes(self, id):
        report = self.get(id)
        if report.state == 'collecting' or report.path is None:
            raise ValueError(t('addon.errors.report.not_ready'))
        return report.path.read_bytes()

    def filename(self, id):
        report = self.get(id)
        stamp = datetime.fromtimestamp(report.created, timezone.utc).strftime('%Y%m%d-%H%M')
        node = re.sub(r'[^a-z0-9-]+', '-', str(report.summary.get('node') or report.inbox).lower()).strip('-')[:40]
        return f'tessera-report-{node}-{stamp}.zip'

    def delete(self, id):
        report = self.reports.pop(id, None)
        if report is None:
            return
        if report.task and not report.task.done():
            report.task.cancel()
        if report.path:
            with contextlib.suppress(OSError):
                report.path.unlink()
        self._save_index()

    def _prune(self):
        kept = sorted(self.reports.values(), key=lambda r: r.created, reverse=True)
        for old in kept[KEEP:]:
            self.delete(old.id)

    # ---- collecting
    def _set(self, report, step, progress):
        report.step, report.progress = step, progress
        self.manager.notify()

    def _names(self, screen, extra=()):
        meta = self.manager.built_as(screen)
        names = [screen.get('name'), screen.get('device'), screen.get('node'), meta.get('node'), meta.get('friendly'),
                screen.get('ip'), *extra]
        return [n for n in names if isinstance(n, str) and n.strip()]

    def _secret_values(self):
        return list(getattr(self.manager.firmware, '_secret_values', []) or [])

    def _redact(self, text, names):
        return redaction.redact_text(text, names, self._secret_values())

    async def _collect(self, report, screen):
        try:
            await self._collect_steps(report, screen)
            report.state = 'ready'
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - the page gets the sentence, the log the cause
            LOG.exception('Collecting the report of %s failed', report.inbox)
            report.state, report.error = 'failed', t('addon.errors.report.failed', reason=type(error).__name__)
        finally:
            report.progress = 1.0
            self.manager.notify()

    async def _collect_steps(self, report, screen):
        m = self.manager
        inbox = report.inbox
        entry = await self._entry_of(screen)
        mac = self._mac_of(screen)
        names = self._names(screen, [n for n in ((entry or {}).get('title'), mac, mac.replace(':', '') if mac else None) if n])
        full = report.depth == 'full'
        warnings = report.warnings

        # 1. identity
        self._set(report, 'identity', 0.05)
        profile, host = m.updates.resolve(screen)
        meta = m.built_as(screen)
        board = m.feedback_board(screen) or screen.get('board')
        board_row = self._board_row(board)
        versions = m.feedback_versions(screen)
        running = m.plugins.running().get(inbox, []) if hasattr(m, 'plugins') else []
        sender = m.page_senders.get(inbox) if hasattr(m, 'page_senders') else None
        memory = (getattr(sender, 'memory', None) or getattr(sender, 'last_memory', None)) if sender else None
        layout = m.layouts.get(inbox, {}) if hasattr(m, 'layouts') else {}
        tiles = layout.get('tiles') or []
        info = await self._supervisor_info()
        stem = Path(profile).stem if profile else None
        elf = self.decoder.elf(stem) if stem else None
        built_on = 'unknown'
        if stem:
            if (self.data / 'build' / stem / 'server').exists() and elf is None:
                built_on = 'build_server'
            elif elf is not None:
                built_on = 'addon'
        chip = self._chip_of(board)
        catalog = (board_row or {}).get('catalog') or {}
        summary = {
            'board': board, 'board_name': ' '.join(str(catalog.get(k)) for k in ('name', 'model') if catalog.get(k)) or None,
            'board_status': catalog.get('status'), 'inch': catalog.get('inch'),
            'chip': chip, 'shape': screen.get('shape'), 'features': screen.get('features'), 'flash': screen.get('flash'),
            'firmware': versions.get('firmware_version'), 'firmware_raw': screen.get('firmware'),
            'channel': self._channel(), 'ref': self._ref_of(profile),
            'esphome': self._esphome_version(), 'addon': versions.get('addon_version') or self._addon_version(),
            'ha': info.get('homeassistant'), 'supervisor': info.get('supervisor'), 'os': info.get('hassos'),
            'machine': info.get('machine'), 'arch': info.get('arch'),
            'plugins': self._plugin_summary(running), 'plugins_source': 'hello' if running else None,
            'crash': None, 'online': bool(screen.get('online')), 'built_on': built_on, 'elf': elf is not None,
            'node': screen.get('node') or meta.get('node'), 'language': screen.get('language'), 'area_set': bool(screen.get('area')),
            'status': screen.get('status'), 'memory': memory, 'pages': _count(layout.get('pages')) if isinstance(layout, dict) else None,
            'tiles': len(tiles), 'cards': _card_kinds(tiles),
            'profile': profile, 'depth': report.depth, 'made_at': now_iso(self.clock),
            'plugins_installed': self._installed_plugins(inbox),
        }
        heap = self._device_sensors(screen)
        if heap:
            summary['sensors'] = heap
        report.summary = summary
        if not screen.get('online'):
            warnings.append('screen_offline')

        # 2. profile
        self._set(report, 'profile', 0.15)
        texts = {}
        if profile:
            for suffix, name in (('', 'profile.yaml'), (m.firmware.OVERRIDE_SUFFIX, 'override.yaml'), (m.firmware.PLUGINS_SUFFIX, 'plugins.yaml')):
                path = m.firmware.root / (stem + suffix if suffix else profile)
                try:
                    texts[name] = self._redact(path.read_text(), names)
                except OSError:
                    continue
        else:
            warnings.append('no_profile')
        if full:
            texts['layout.json'] = self._redact(json.dumps(layout, indent=1, ensure_ascii=False, default=str), names)

        # 3 + 4. crash record and the live log of the screen
        self._set(report, 'crash', 0.2)
        key = self._api_key(profile) if profile else None
        if profile and key is None and self._needs_key(profile):
            warnings.append('no_api_key')
        lines, device = [], None
        if screen.get('online') and host:
            self._set(report, 'screen_log', 0.25)
            try:
                lines, device = await screen_log(host, key, CAPTURE_SECONDS, name=inbox)
            except Exception as error:  # noqa: BLE001 - the report says the log could not be read
                LOG.info('Reading the log of %s failed (%s)', inbox, type(error).__name__)
                warnings.append('screen_log_failed')
        crash = crash_summary(lines, self.clock) if lines else None
        decoded, why = [], None
        if crash:
            decoded, why = await self.decoder.decode(stem, chip, crash['lines'], crash.get('elf'))
            crash['decoded'] = decoded
            self.crashes.add(inbox, crash)
        elif lines:
            warnings.append('no_crash_record')
        if why:
            warnings.append(why)
        elif stem and elf is None and 'no_elf' not in warnings:
            warnings.append('no_elf')
        kept = self.crashes.record(inbox).get('crashes') or []
        summary['crash'] = {'reason': kept[-1]['reason'], 'at': kept[-1]['at'], 'decoded': kept[-1].get('decoded') or []} if kept else None
        summary['device'] = device_info_dict(device)
        parts = []
        if kept:
            parts.append('# Crashes this app saw (newest last)')
            for c in kept:
                parts.append(f"## {c.get('at')}  {c.get('reason')}")
                parts.extend(c.get('lines') or [])
                if c.get('decoded'):
                    parts.append('decoded:')
                    parts.extend('  ' + d for d in c['decoded'])
                parts.append('')
        parts.append(f'# Live log, {CAPTURE_SECONDS} s at DEBUG (the firmware caps it at its compiled level)' if lines
                     else '# Live log: none (the screen was offline or could not be reached)')
        parts.extend(lines)
        texts['screen.log'] = self._redact('\n'.join(parts), names)
        # The screen's hello names what it runs, and the app forgets it when the screen goes (page_delivery). A screen
        # that was restarting as the report began, the one a report is made for, had said none: it is asked once more
        # now, after the log's 45 seconds, and failing that the plugins the app installed on it stand in, said so
        # (TR-4EFBDE, 2026-10-23: a Tab5 with nine plugins, "Plugins running: none").
        if not summary['plugins'] and hasattr(m, 'plugins'):
            summary['plugins'] = self._plugin_summary(m.plugins.running().get(inbox, []))
            summary['plugins_source'] = 'hello' if summary['plugins'] else None
        if not summary['plugins'] and summary.get('plugins_installed'):
            summary['plugins'] = self._plugin_summary(summary['plugins_installed'])
            summary['plugins_source'] = 'installed'

        # 5. Home Assistant's log and diagnostics
        self._set(report, 'ha_log', 0.7)
        ha_text = await self._ha_log(names, full)
        if ha_text is None:
            warnings.append('ha_log_unavailable')
        else:
            texts['home-assistant.log'] = self._redact(ha_text, names)
        diagnostics = await self._diagnostics(screen, full, entry)
        if diagnostics is not None:
            texts['diagnostics.json'] = json.dumps(redaction.redact_data(diagnostics, names=names, values=self._secret_values()),
                                                  indent=1, ensure_ascii=False, default=str)
            summary['ha'] = summary.get('ha') or (diagnostics.get('home_assistant') or {}).get('version')
        else:
            warnings.append('diagnostics_unavailable')

        # 6. the app's own log
        self._set(report, 'addon_log', 0.85)
        own = await self._addon_log()
        if own is None:
            warnings.append('addon_log_unavailable')
            own = '\n'.join(self.buffer.lines)
        texts['addon.log'] = self._redact(own, names)

        # 7. the last build
        self._set(report, 'build_log', 0.9)
        build = self._build_log(profile)
        if build:
            texts['build.log'] = self._redact(build, names)

        # 8. report.md first, summary.json second, then the zip
        self._set(report, 'zip', 0.95)
        ordered = {'report.md': self._report_md(summary, warnings, texts), 'summary.json': json.dumps(summary, indent=1, ensure_ascii=False, default=str)}
        ordered.update(texts)
        report.texts = ordered
        report.files = [{'name': name, 'size': len(text.encode('utf-8')), 'lines': text.count('\n') + 1,
                         'kind': name.rsplit('.', 1)[-1]} for name, text in ordered.items()]
        self.dir.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for name, text in ordered.items():
                bundle.writestr(name, text)
        data = buffer.getvalue()
        report.path = self.dir / f'{report.id}.zip'
        report.path.write_bytes(data)
        with contextlib.suppress(OSError):
            os.chmod(report.path, 0o600)
        report.size = len(data)
        self._prune()
        self._save_index()

    @staticmethod
    def _plugin_summary(items):
        """Plugins as the summary lists them, id and version only: from a hello's list or the store's records."""
        return [{'id': p.get('id'), 'version': p.get('version')} for p in items or [] if isinstance(p, dict)]

    @staticmethod
    def _plugin_lines(s):
        """The two lines of report.md about plugins: what the app installed on the screen (the store, with a record's
        state when it is not active), and what the screen's own hello said it runs, or that none was heard and the
        installed ones stand in for it in the summary."""
        installed = ', '.join(f"{r.get('id')} {r.get('version')}" + (f" ({r['state']})" if r.get('state') not in (None, 'active') else '')
                              for r in s.get('plugins_installed') or [] if isinstance(r, dict)) or 'none'
        if s.get('plugins_source') == 'installed':
            running = 'not heard (the screen said no hello while the report was made; the installed ones stand in)'
        else:
            running = ', '.join('%s %s' % (p.get('id'), p.get('version')) for p in s.get('plugins') or []) or 'none'
        return [f'- Plugins installed: {installed}', f"- Plugins running (the screen's hello): {running}"]

    def _report_md(self, s, warnings, texts):
        crash = s.get('crash') or {}
        lines = [f"# Tessera troubleshooting report ({s.get('made_at')})", '',
                 f"- Board: {s.get('board_name') or s.get('board')} (`{s.get('board')}`, {s.get('chip') or 'chip unknown'}), shape {s.get('shape')}",
                 f"- Firmware: {s.get('firmware') or s.get('firmware_raw')} on {s.get('channel') or '?'} ({s.get('ref') or 'ref unknown'}), ESPHome {s.get('esphome')}, built on {s.get('built_on')}, ELF here: {s.get('elf')}",
                 f"- App: {s.get('addon')}; Home Assistant {s.get('ha')}, Supervisor {s.get('supervisor')}, OS {s.get('os')}, {s.get('machine')} ({s.get('arch')})",
                 f"- Screen: online {s.get('online')}, status {s.get('status')}, language {s.get('language')}, pages {s.get('pages')}, tiles {s.get('tiles')}, cards {', '.join(s.get('cards') or [])}",
                 *self._plugin_lines(s),
                 f"- Memory (hello): {s.get('memory')}", f"- Sensors: {s.get('sensors')}", f"- Device info: {s.get('device')}", '']
        if crash:
            lines += ['## Last crash', f"{crash.get('at')}: {crash.get('reason')}", *('  ' + d for d in crash.get('decoded') or []), '']
        else:
            lines += ['## Crashes', 'None seen by the app.', '']
        if warnings:
            lines += ['## Notes', *(f'- {w}' for w in warnings), '']
        lines += ['## Files', *(f'- {name}' for name in ['report.md', 'summary.json', *texts.keys()]), '',
                  'Redacted: passwords, keys, Wi-Fi names, IP and MAC addresses, coordinates; the screen\'s names read `<screen>`.']
        return '\n'.join(lines)

    # ---- sources
    def _channel(self):
        try:
            import core
            return core.channel()
        except Exception:  # noqa: BLE001
            return None

    def _addon_version(self):
        try:
            import core
            return core.APP_VERSION
        except Exception:  # noqa: BLE001
            return None

    def _esphome_version(self):
        try:
            import build_cache
            return build_cache.esphome_version()
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _board_row(board):
        """The row of boards.json for a board key (core.SHAPES is keyed by entry file; each row names its `board`)."""
        try:
            import core
            return next((row for row in core.SHAPES.values() if isinstance(row, dict) and row.get('board') == board), None)
        except Exception:  # noqa: BLE001
            return None

    def _chip_of(self, board):
        row = self._board_row(board)
        return str(row.get('chip')).lower().replace('-', '') if row and row.get('chip') else None

    def _installed_plugins(self, inbox):
        try:
            store = getattr(self.manager.plugins, 'store', None)
            return [{'id': r.get('id'), 'version': r.get('version'), 'ref': r.get('ref'), 'state': r.get('state'), 'source': r.get('source')}
                    for r in (store.of(inbox) if store is not None else []) if isinstance(r, dict)]
        except Exception:  # noqa: BLE001
            return None

    def _device_sensors(self, screen):
        """The firmware's own diagnostic sensors of this screen as Home Assistant has them now: heap, PSRAM, Wi-Fi
        signal, last boot, uptime."""
        device = screen.get('device_id')
        wanted = ('heap free', 'heap fragmentation', 'heap largest block', 'heap minimum free', 'psram free', 'psram largest block',
                  'wifi signal', 'last boot', 'uptime', 'node status', 'screen firmware', 'screen board', 'screen flash', 'screen layout')
        out = {}
        for item in getattr(self.manager.ha, 'registry', []) or []:
            if not isinstance(item, dict) or item.get('device_id') != device:
                continue
            name = str(item.get('original_name') or '').lower()
            if name in wanted:
                state = (self.manager.ha.states.get(item['entity_id']) or {})
                out[name] = state.get('state')
        return out

    def _ref_of(self, profile):
        """The branch or tag the screen's YAML builds its package from (`ref:` of the package, or GITHUB_REF)."""
        if not profile:
            return None
        with contextlib.suppress(OSError):
            text = (self.manager.firmware.root / profile).read_text()
            m = re.search(r'^\s*ref:\s*["\']?([\w./-]+)', text, re.M) or re.search(r'GITHUB_REF:\s*["\']?([\w./-]+)', text)
            return m.group(1) if m else None
        return None

    def _needs_key(self, profile):
        with contextlib.suppress(OSError):
            return 'encryption' in (self.manager.firmware.root / profile).read_text()
        return False

    def _api_key(self, profile):
        """The screen's API encryption key: inline in its YAML, or from secrets.yaml when it is a !secret."""
        try:
            text = (self.manager.firmware.root / profile).read_text()
        except OSError:
            return None
        m = re.search(r'encryption:\s*\n\s*key:\s*(.+)', text)
        if not m:
            return None
        value = m.group(1).strip().strip('"\'')
        if value.startswith('!secret'):
            name = value[len('!secret'):].strip()
            try:
                import yaml
                secrets_data = yaml.safe_load((self.manager.firmware.root / 'secrets.yaml').read_text()) or {}
                value = secrets_data.get(name)
            except Exception:  # noqa: BLE001
                return None
        return value if isinstance(value, str) and value else None

    def _session_for(self):
        return getattr(self.manager.ha, 'session', None)

    async def _supervisor_info(self):
        token = os.environ.get('SUPERVISOR_TOKEN', '')
        session = self._session_for()
        if not token or session is None:
            return {}
        try:
            async with session.get('http://supervisor/info', headers={'Authorization': f'Bearer {token}'},
                                   timeout=ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return {}
                data = (await response.json()).get('data') or {}
                return {k: data.get(k) for k in ('homeassistant', 'supervisor', 'hassos', 'machine', 'arch', 'channel') if data.get(k)}
        except Exception:  # noqa: BLE001
            return {}

    async def _addon_log(self):
        token = os.environ.get('SUPERVISOR_TOKEN', '')
        session = self._session_for()
        if not token or session is None:
            return None
        try:
            async with session.get('http://supervisor/addons/self/logs', headers={'Authorization': f'Bearer {token}', 'Range': f'entries=:-{ADDON_LOG_LINES}:'},
                                   timeout=ClientTimeout(total=20)) as response:
                if response.status != 200:
                    LOG.info('The Supervisor gave no log of this app for the report (%s)', response.status)
                    return None
                text = await response.text()
                return '\n'.join(strip_ansi(text).splitlines()[-ADDON_LOG_LINES:])
        except Exception as error:  # noqa: BLE001
            LOG.info('Reading this app\'s log for the report failed (%s)', type(error).__name__)
            return None

    async def _ha_log(self, names, full):
        """Home Assistant's log lines about the screen (REST /api/error_log, the whole file of this run) and the warnings
        it kept (system_log/list), or None when neither could be read."""
        ha = self.manager.ha
        session, base, token = getattr(ha, 'session', None), getattr(ha, 'base', None), getattr(ha, 'token', None)
        parts, got = [], False
        # Under the Supervisor, Home Assistant logs to the journal, which the Supervisor serves (/core/logs; the role
        # homeassistant of config.yaml); elsewhere the log file of this run (/api/error_log).
        supervisor = os.environ.get('SUPERVISOR_TOKEN', '')
        if session is not None and supervisor:
            try:
                async with session.get(f'http://supervisor/core/logs?lines={HA_LOG_LINES * 4}', timeout=ClientTimeout(total=30),
                                       headers={'Authorization': f'Bearer {supervisor}', 'Accept': 'text/plain'}) as response:
                    if response.status == 200:
                        text = strip_ansi(await response.text())
                        lines = ha_log_lines(text, names, everything=full)
                        parts.append(f'# Home Assistant\'s log (journal), lines about this screen ({len(lines)})' if not full
                                     else f'# Home Assistant\'s log (journal), every ESPHome line ({len(lines)})')
                        parts.extend(lines)
                        got = True
                    else:
                        LOG.info('The Supervisor gave no Home Assistant log for the report (%s)', response.status)
            except Exception as error:  # noqa: BLE001
                LOG.info('Reading Home Assistant\'s journal for the report failed (%s)', type(error).__name__)
        if session is not None and base and token and not got:
            try:
                async with session.get(f'{base}/error_log', headers={'Authorization': f'Bearer {token}'}, timeout=ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        text = await response.text()
                        lines = ha_log_lines(text, names, everything=full)
                        parts.append(f'# home-assistant.log, lines about this screen ({len(lines)})' if not full
                                     else f'# home-assistant.log, every ESPHome line ({len(lines)})')
                        parts.extend(lines)
                        got = True
                    else:
                        LOG.info('Home Assistant gave no log for the report (%s)', response.status)
            except Exception as error:  # noqa: BLE001
                LOG.info('Reading Home Assistant\'s log for the report failed (%s)', type(error).__name__)
        try:
            entries = await ha.request('system_log/list')
            if isinstance(entries, list):
                if not full:
                    entries = _entries_about(entries, names)
                parts += ['', '# Warnings and errors Home Assistant kept (system_log, newest first)', system_log_text(entries, everything=full)]
                got = True
        except Exception as error:  # noqa: BLE001
            LOG.info('Reading Home Assistant\'s warnings for the report failed (%s)', type(error).__name__)
        return '\n'.join(parts) if got else None

    async def _entry_of(self, screen):
        """The screen's ESPHome config entry in Home Assistant (its title heads every log line about the screen), or None."""
        ha = self.manager.ha
        try:
            entries = await ha.request('config_entries/get', domain='esphome')
        except Exception:  # noqa: BLE001
            return None
        device = next((d for d in getattr(ha, 'devices', []) or [] if isinstance(d, dict) and d.get('id') == screen.get('device_id')), {})
        entry_ids = set(device.get('config_entries') or [])
        names = {str(n).lower() for n in (screen.get('device'), screen.get('name'), screen.get('node')) if n}
        return next((e for e in entries or [] if isinstance(e, dict) and e.get('entry_id') in entry_ids), None) \
            or next((e for e in entries or [] if isinstance(e, dict) and str(e.get('title', '')).lower() in names), None)

    def _mac_of(self, screen):
        device = next((d for d in getattr(self.manager.ha, 'devices', []) or [] if isinstance(d, dict) and d.get('id') == screen.get('device_id')), {})
        for kind, value in device.get('connections') or []:
            if kind == 'mac' and isinstance(value, str):
                return value
        return None

    async def _diagnostics(self, screen, full, entry=None):
        """Home Assistant's own diagnostics of the screen's ESPHome entry (what Download diagnostics gives), shortened to
        what is about the device unless the report is a full one."""
        ha = self.manager.ha
        session, base, token = getattr(ha, 'session', None), getattr(ha, 'base', None), getattr(ha, 'token', None)
        if session is None or not base or not token:
            return None
        entry = entry or await self._entry_of(screen)
        if entry is None:
            return None
        try:
            async with session.get(f"{base}/diagnostics/config_entry/{entry['entry_id']}", headers={'Authorization': f'Bearer {token}'},
                                   timeout=ClientTimeout(total=20)) as response:
                if response.status != 200:
                    LOG.info('Home Assistant gave no diagnostics for the report (%s)', response.status)
                    return None
                data = await response.json()
        except Exception as error:  # noqa: BLE001
            LOG.info('Reading the diagnostics for the report failed (%s)', type(error).__name__)
            return None
        if not isinstance(data, dict):
            return None
        if not full:
            inner = data.get('data')
            if isinstance(inner, dict) and isinstance(inner.get('storage_data'), dict):
                storage = inner['storage_data']
                inner['storage_data'] = {k: v for k, v in storage.items() if k in ('device_info', 'api_version')}
        return data

    def _build_log(self, profile):
        if not profile:
            return None
        queue = getattr(self.manager, 'build_queue', None)
        for build in reversed(list(getattr(queue, 'ended', []) or [])):
            if getattr(build, 'file', None) == profile and getattr(build, 'logs', None):
                return f"# Build {build.id} ({build.action}, {build.state}, {build.reason or ''})\n" + '\n'.join(build.logs)
        return None

    # ---- sending
    def _token_for(self, device):
        record = self.manager.feedback.record(device)
        if not feedback.TOKEN_TEXT.fullmatch(record.get('token') or ''):
            record['token'] = feedback.new_token()
            self.manager.feedback.save()
        return record['token']

    async def send(self, id, consent, note, email, remember_email, screen):
        report = self.get(id)
        if consent is not True:
            raise ValueError(t('addon.errors.report.consent'))
        if report.state not in ('ready', 'sent'):
            raise ValueError(t('addon.errors.report.not_ready'))
        note, email = clean_note(note), clean_email(email)
        if remember_email:
            self.remember(email=email)
        elif self.settings.get('email') and not email:
            self.remember(email=None)
        if report.size > ZIP_MAX:
            return {'state': 'too_large', 'error': t('addon.errors.report.too_large')}
        board = self.manager.feedback_board(screen)
        if not board:
            return {'state': 'invalid', 'error': t('addon.errors.feedback.unknown_board')}
        device = screen.get('device_id')
        token = self._token_for(device)
        fields = {'board_id': board, 'depth': report.depth, 'consent': 'true',
                  'summary': json.dumps(self._site_summary(report.summary, report.files), ensure_ascii=False)[:16 * 1024]}
        for key, value in self.manager.feedback_versions(screen).items():
            if value:
                fields[key] = value
        if note:
            fields['note'] = note
        if email:
            fields['email'] = email
        result = await self.transport(token, fields, report.path.read_bytes(), self.filename(id))
        if result.get('state') == 'sent':
            report.state, report.reference = 'sent', result['reference']
            report.sent_at, report.expires_at = now_iso(self.clock), result.get('expires_at')
            if result.get('retention_days'):
                self.remember(retention_days=result['retention_days'])
            self._save_index()
            self.manager.notify()
            return {'state': 'sent', 'reference': report.reference, 'expires_at': report.expires_at}
        words = {'retry': 'addon.errors.report.retry', 'offline': 'addon.errors.report.offline',
                 'too_large': 'addon.errors.report.too_large', 'invalid': 'addon.errors.report.invalid'}
        return {'state': result.get('state', 'retry'), 'error': t(words.get(result.get('state'), 'addon.errors.report.retry'))}

    @staticmethod
    def _site_summary(summary, files):
        keep = ('board', 'board_name', 'chip', 'firmware', 'channel', 'esphome', 'addon', 'ha', 'supervisor', 'os', 'machine', 'arch',
                'plugins', 'crash', 'online', 'built_on', 'elf', 'depth', 'pages', 'tiles', 'cards', 'status', 'memory')
        out = {k: summary.get(k) for k in keep if summary.get(k) is not None}
        if isinstance(out.get('crash'), dict):
            out['crash'] = {'reason': out['crash'].get('reason'), 'at': out['crash'].get('at')}
        out['files'] = [f['name'] for f in files]
        return out

    async def _post(self, token, fields, data, filename):
        """One upload to the website. {'state': 'sent', 'reference', 'expires_at', 'retention_days'} or a state to show."""
        form = FormData()
        for key, value in fields.items():
            form.add_field(key, value)
        form.add_field('report', data, filename=filename, content_type='application/zip')
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        try:
            async with ClientSession() as session:
                async with session.post(REPORTS_URL, data=form, headers=headers, timeout=ClientTimeout(total=120), allow_redirects=False) as response:
                    if response.status == 201:
                        try:
                            body = await response.json()
                        except (ValueError, ClientError):
                            return {'state': 'retry'}
                        row = body.get('data') if isinstance(body, dict) else None
                        if isinstance(row, dict) and isinstance(row.get('reference'), str):
                            return {'state': 'sent', 'reference': row['reference'], 'expires_at': row.get('expires_at'),
                                    'retention_days': row.get('retention_days')}
                        return {'state': 'retry'}
                    if response.status == 413:
                        return {'state': 'too_large'}
                    if response.status in (429,) or response.status >= 500:
                        return {'state': 'retry'}
                    return {'state': 'invalid', 'status': response.status}
        except (ClientError, asyncio.TimeoutError, OSError):
            return {'state': 'offline'}

    # ---- crash watch
    def watch(self):
        if self.watch_task is None:
            self.watch_task = asyncio.ensure_future(self._watch_loop())

    async def close(self):
        if self.watch_task:
            self.watch_task.cancel()
        for report in list(self.reports.values()):
            if report.task and not report.task.done():
                report.task.cancel()

    async def _watch_loop(self):
        while True:
            try:
                await asyncio.sleep(WATCH_INTERVAL)
                await self._watch_once()
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001 - the watch never stops the app
                LOG.exception('The crash watch failed once')

    def _boot_values(self):
        """{inbox: the "Last boot" state} of every screen, from Home Assistant's states."""
        out = {}
        registry = getattr(self.manager.ha, 'registry', []) or []
        boots = {}
        for item in registry:
            if isinstance(item, dict) and str(item.get('original_name') or '').lower() == 'last boot' and item.get('platform') == 'esphome':
                state = (self.manager.ha.states.get(item['entity_id']) or {}).get('state')
                if state not in (None, 'unknown', 'unavailable'):
                    boots[item.get('device_id')] = state
        for screen in self.manager.screens():
            value = boots.get(screen.get('device_id'))
            if value:
                out[screen['id']] = (value, screen)
        return out

    async def _watch_once(self):
        for inbox, (boot, screen) in self._boot_values().items():
            record = self.crashes.record(inbox)
            if record.get('boot') is None:
                record['boot'] = boot
                self.crashes.save()
                continue
            if record['boot'] == boot:
                continue
            record['boot'] = boot
            self.crashes.save()
            if self.clock() - (record.get('captured') or 0) < CAPTURE_SPACING or not screen.get('online'):
                continue
            record['captured'] = self.clock()
            await self._capture(inbox, screen)

    async def _capture(self, inbox, screen):
        profile, host = self.manager.updates.resolve(screen)
        if not host:
            return
        key = self._api_key(profile) if profile else None
        try:
            lines, _ = await screen_log(host, key, CRASH_SECONDS, name=inbox)
        except Exception as error:  # noqa: BLE001
            LOG.info('Reading the crash record of %s failed (%s)', inbox, type(error).__name__)
            return
        crash = crash_summary(lines, self.clock)
        if crash is None:
            return
        stem = Path(profile).stem if profile else None
        chip = self._chip_of(self.manager.feedback_board(screen) or screen.get('board'))
        crash['decoded'], _ = await self.decoder.decode(stem, chip, crash['lines'], crash.get('elf'))
        self.crashes.add(inbox, crash)
        LOG.warning('%s rebooted after a crash: %s', inbox, crash['reason'])
        self.manager.notify()

