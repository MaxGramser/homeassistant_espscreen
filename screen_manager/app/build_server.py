"""Builds on a build server (docs/BUILDS.md, "On a build server"): ESPHome Device Builder's remote build, with this app
as the side that sends.

A Raspberry Pi takes a long time over a screen's firmware and sometimes runs out of memory. Many people already run a
build server on a faster computer: ESPHome Desktop, ESPHome Device Builder, or `esphome-device-builder
--remote-build-only`. This app pairs with one the way a Device Builder pairs with it (its "peer link") and sends it
the screen's YAML to compile; the firmware comes back, and everything after the build stays here as before: OTA, USB,
the browser download, the bridge and the wide partition table (Firmware.run with `esphome upload --file`).

The build server stays ESPHome's. This module only speaks the sending side of its peer link, as Device Builder's own
offloader does (github.com/esphome/device-builder, docs/ARCHITECTURE.md "Remote build"):

- A WebSocket to ws://<host>:<port>/remote-build/peer-link (6055 by default). Every frame is one binary message:
  three Noise_XX_25519_ChaChaPoly_SHA256 handshake messages (msg1 carries `{"intent": ...}` in the clear, msg3 our
  details encrypted), then the receiver's `intent_response`, then JSON application frames, each encrypted.
- Pairing: `preview` shows the server's key (its fingerprint, seven emoji), `pair_request` asks to be let in (with the
  one-time key a headless server prints), `pair_status` waits for the person to accept it on the server.
- Building: one long-lived `peer_link` session with pings, on which `submit_job` (the bundle `esphome bundle` makes, in
  chunks) goes out, `job_state_changed` and `job_output` come back, and `download_artifacts` fetches the build.

Whatever goes wrong before the server builds, or whenever the link drops, the build runs here instead (`Fallback`), and
the log and the page say why. Only a compile that failed on the server is a failed build (`Failed`): the same YAML
fails here too, after a much longer wait. The server builds with the ESPHome this app has (`target_esphome_version`):
it installs that version once, beside its own.

The protocol has no version number of its own (asked upstream: github.com/orgs/esphome/discussions/3910). Fields come
and go additively; a frame this module does not know is ignored, and one it cannot read ends the session, which again
means a build here."""
import asyncio
import base64
import contextlib
import gzip
import hashlib
import io
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import tarfile
import tempfile
import time

import aiohttp

import atomic

LOG = logging.getLogger('screen_manager')

try:  # In the app's container through ESPHome (aioesphomeapi speaks Noise to every screen).
    from noise.connection import Keypair, NoiseConnection
except ImportError:  # pragma: no cover - a test environment without it skips this module's tests
    Keypair = NoiseConnection = None

PORT = 6055
PATH = '/remote-build/peer-link'
PATTERN = b'Noise_XX_25519_ChaChaPoly_SHA256'
# Raw bytes of the bundle per frame, as Device Builder sends them: under its 60 KiB frame limit once in base64 and JSON.
CHUNK = 32 * 1024
FRAME_MAX = 4 * 1024 * 1024
STEP_SECONDS = 10           # one handshake message, as the receiver waits for it
ACK_SECONDS = 60            # the receiver's answer to a whole bundle
PING_SECONDS = 30           # Device Builder's heartbeat; silence for three of them is a dead link
DEAD_SECONDS = 90
PAIR_WAIT_SECONDS = 3600    # pair_status is answered when the person accepts, refuses, or the window closes
BUILD_SECONDS = 7200        # as long as a build here may take
ARTIFACTS_MAX = 256 * 1024 * 1024
BUNDLE_SECONDS = 300
RETRY_SECONDS = (2, 5, 10, 30)
# What travels back that this app never uses: the debug symbols are by far the largest part of a build.
SKIP_SUFFIXES = ('.elf', '.map')
NAME_MAX = 128
# A terminal's colour codes as the server's log lines carry them, written out ("\\033[32m") rather than as the byte.
ESCAPED = re.compile(r'\\(?:033|x1[bB]|u001[bB]|e)\[[0-9;?]*[A-Za-z]')

# The seven emoji of a key's fingerprint, as Device Builder shows them (helpers/pin_emoji.py there, from Matrix's SAS
# emoji list): the person compares them on both sides, so the order is fixed.
SAS = (('\U0001f436', 'Dog'), ('\U0001f431', 'Cat'), ('\U0001f981', 'Lion'), ('\U0001f40e', 'Horse'),
       ('\U0001f984', 'Unicorn'), ('\U0001f437', 'Pig'), ('\U0001f418', 'Elephant'), ('\U0001f430', 'Rabbit'),
       ('\U0001f43c', 'Panda'), ('\U0001f413', 'Rooster'), ('\U0001f427', 'Penguin'), ('\U0001f422', 'Turtle'),
       ('\U0001f41f', 'Fish'), ('\U0001f419', 'Octopus'), ('\U0001f98b', 'Butterfly'), ('\U0001f337', 'Flower'),
       ('\U0001f333', 'Tree'), ('\U0001f335', 'Cactus'), ('\U0001f344', 'Mushroom'), ('\U0001f30f', 'Globe'),
       ('\U0001f319', 'Moon'), ('☁️', 'Cloud'), ('\U0001f525', 'Fire'), ('\U0001f34c', 'Banana'),
       ('\U0001f34e', 'Apple'), ('\U0001f353', 'Strawberry'), ('\U0001f33d', 'Corn'), ('\U0001f355', 'Pizza'),
       ('\U0001f382', 'Cake'), ('❤️', 'Heart'), ('\U0001f600', 'Smiley'), ('\U0001f916', 'Robot'),
       ('\U0001f3a9', 'Hat'), ('\U0001f453', 'Glasses'), ('\U0001f527', 'Wrench'), ('\U0001f385', 'Santa'),
       ('\U0001f44d', 'Thumbs up'), ('☂️', 'Umbrella'), ('⌛️', 'Hourglass'), ('⏰', 'Clock'),
       ('\U0001f381', 'Gift'), ('\U0001f4a1', 'Light bulb'), ('\U0001f4d5', 'Book'), ('✏️', 'Pencil'),
       ('\U0001f4ce', 'Paperclip'), ('✂️', 'Scissors'), ('\U0001f512', 'Lock'), ('\U0001f511', 'Key'),
       ('\U0001f528', 'Hammer'), ('☎️', 'Telephone'), ('\U0001f3c1', 'Flag'), ('\U0001f682', 'Train'),
       ('\U0001f6b2', 'Bicycle'), ('✈️', 'Aeroplane'), ('\U0001f680', 'Rocket'), ('\U0001f3c6', 'Trophy'),
       ('⚽️', 'Ball'), ('\U0001f3b8', 'Guitar'), ('\U0001f3ba', 'Trumpet'), ('\U0001f514', 'Bell'),
       ('⚓️', 'Anchor'), ('\U0001f3a7', 'Headphones'), ('\U0001f4c1', 'Folder'), ('\U0001f4cc', 'Pin'))


def fingerprint(pin):
    """The seven (emoji, name) of a key's pin (the hex SHA-256 of its public key): its first 42 bits, six at a time."""
    bits = int(pin[:11], 16)
    return [SAS[(bits >> (44 - 6 * (i + 1))) & 0x3F] for i in range(7)]


def pin_of(public):
    return hashlib.sha256(public).hexdigest()


def esphome_version():
    """The ESPHome this app builds with, which the server is asked to build with too; '' when it cannot tell."""
    try:
        from importlib.metadata import version
        return version('esphome')
    except Exception:  # noqa: BLE001 - a test without ESPHome; the server then builds with its own
        return ''


# Why a build ran here after all, for its log (in English, as the rest of a build's log); the page has its own words for
# each (editor.build.server.fallback.<reason>).
FALLBACK_NOTES = {
    'offline': 'the build server is not reachable right now.',
    'refused': 'the build server no longer knows this app; pair it again in Settings.',
    'mismatch': 'the build server answered with another key than the one you checked; pair it again in Settings.',
    'unavailable': 'this app cannot talk to a build server here.',
    'lost': 'the link to the build server dropped during the build.',
    'refused_job': 'the build server did not take the build.',
    'provision': 'the build server could not install the ESPHome this app builds with.',
    'cancelled': 'the build was stopped on the build server.',
    'fetch': 'the firmware did not come back from the build server.',
    'bundle': 'the YAML could not be packed for the build server.',
}


class Fallback(Exception):
    """The server could not build this one (offline, busy elsewhere, refused it, the link dropped): build here instead.
    `args[0]` is the reason's key, `detail` what the server or the link said."""

    def __init__(self, reason, detail=''):
        super().__init__(reason)
        self.reason, self.detail = reason, detail


class Failed(Exception):
    """The server built it and the build failed: the log says why, and the same YAML fails here too."""


class Refused(Exception):
    """A pairing step the person can act on: `args[0]` is the reason's key (addon.errors.build_server.<key>)."""


class Noise:
    """The initiator's side of one Noise XX session."""

    def __init__(self, private):
        if NoiseConnection is None:
            raise Fallback('unavailable', 'the noise library is missing')
        self.connection = NoiseConnection.from_name(PATTERN)
        self.connection.set_as_initiator()
        self.connection.set_keypair_from_private_bytes(Keypair.STATIC, private)
        self.connection.start_handshake()
        self.state = self.connection.noise_protocol.handshake_state
        self.remote = None

    def write(self, payload=b''):
        return bytes(self.connection.write_message(payload))

    def read(self, message):
        payload = bytes(self.connection.read_message(message))
        # The server's static key arrives with msg2; Noise forgets it once the handshake is done, so it is kept here.
        remote = getattr(self.state, 'rs', None)
        if self.remote is None and hasattr(remote, 'public_bytes'):
            self.remote = bytes(remote.public_bytes)
        return payload

    def encrypt(self, frame):
        return bytes(self.connection.encrypt(json.dumps(frame, separators=(',', ':')).encode()))

    def decrypt(self, data):
        return json.loads(bytes(self.connection.decrypt(data)))


async def _receive(ws, seconds):
    message = await asyncio.wait_for(ws.receive(), seconds)
    if message.type != aiohttp.WSMsgType.BINARY:
        raise ConnectionError(f'the server closed the link ({message.type.name.lower()})')
    return message.data


async def handshake(ws, private, intent, details=None, expect=None):
    """msg1 (the intent, in the clear), msg2 (the server's key), msg3 (our details, encrypted), then the server's answer.
    (noise, answer, the server's pin). With `expect`, a server whose key is another one gets nothing of msg3: a pairing
    key or our name never reaches a server the person did not check."""
    noise = Noise(private)
    await ws.send_bytes(noise.write(json.dumps({'intent': intent}).encode()))
    noise.read(await _receive(ws, STEP_SECONDS))
    pin = pin_of(noise.remote or b'')
    if expect and pin != expect:
        raise Refused('mismatch')
    await ws.send_bytes(noise.write(json.dumps(details or {}).encode()))
    answer = noise.decrypt(await _receive(ws, STEP_SECONDS))
    if not isinstance(answer, dict) or not isinstance(answer.get('intent_response'), str):
        raise ConnectionError('the server gave no answer to the handshake')
    return noise, answer, pin


def _text(value, limit=NAME_MAX):
    return value.strip()[:limit] if isinstance(value, str) else ''


def _version(value):
    return value if isinstance(value, str) and re.fullmatch(r'[0-9][0-9A-Za-z.+-]{0,40}', value) else ''


def _host(value):
    value = _text(value, 253)
    if not re.fullmatch(r'[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?|\[?[0-9A-Fa-f:.]+\]?', value or '-'):
        raise Refused('host')
    return value.strip('[]')


def _port(value):
    try:
        port = int(value if value not in (None, '') else PORT)
    except (TypeError, ValueError):
        raise Refused('port') from None
    if not 1 <= port <= 65535:
        raise Refused('port')
    return port


def _url(host, port):
    return f'ws://[{host}]:{port}{PATH}' if ':' in host else f'ws://{host}:{port}{PATH}'


class Job:
    """One build on the server, as its frames come in."""

    def __init__(self, number):
        self.id = number
        self.ack = asyncio.get_running_loop().create_future()
        self.events = asyncio.Queue()
        self.artifacts = None   # {'size', 'chunks', 'sha256', 'parts', 'done'} while they come


class Link:
    """The long-lived peer_link session: pings both ways, frames to the job they belong to, and the server's state."""

    def __init__(self, ws, noise, answer):
        self.ws, self.noise, self.answer = ws, noise, answer
        self.lock = asyncio.Lock()
        self.jobs = {}
        self.queue = {'idle': True, 'running': False, 'queue_depth': 0}
        self.heard = time.monotonic()
        self.closed = asyncio.Event()
        self.reason = ''

    async def send(self, frame):
        async with self.lock:
            await self.ws.send_bytes(self.noise.encrypt(frame))

    async def run(self, changed):
        """Until the link drops: every frame read, a ping now and then, the server's queue for the page."""
        pinger = asyncio.create_task(self._ping())
        try:
            async for message in self.ws:
                if message.type != aiohttp.WSMsgType.BINARY:
                    break
                try:
                    frame = self.noise.decrypt(message.data)
                except Exception:  # noqa: BLE001 - a frame we cannot read ends the session, as the server does
                    self.reason = 'malformed'
                    break
                self.heard = time.monotonic()
                kind = frame.get('type') if isinstance(frame, dict) else None
                if kind == 'ping':
                    await self.send({'type': 'pong', 'nonce': frame.get('nonce')})
                elif kind == 'terminate':
                    self.reason = _text(frame.get('reason'), 40) or 'terminated'
                    break
                elif kind == 'queue_status':
                    self.queue = {key: frame.get(key) for key in ('idle', 'running', 'queue_depth')}
                    changed()
                else:
                    self._to_job(kind, frame)
        finally:
            pinger.cancel()
            self.reason = self.reason or 'closed'
            self.closed.set()
            for job in self.jobs.values():
                if not job.ack.done():
                    job.ack.set_exception(Fallback('lost', self.reason))
                job.events.put_nowait(('lost', self.reason))
            with contextlib.suppress(Exception):
                await self.ws.close()

    async def _ping(self):
        nonce = 0
        while True:
            await asyncio.sleep(PING_SECONDS)
            if time.monotonic() - self.heard > DEAD_SECONDS:
                self.reason = 'silent'
                await self.ws.close()
                return
            nonce += 1
            with contextlib.suppress(Exception):
                await self.send({'type': 'ping', 'nonce': nonce})

    def _to_job(self, kind, frame):
        job = self.jobs.get(frame.get('job_id'))
        if job is None:
            return   # a frame of a job this app no longer follows, or one it does not know: ignored
        if kind == 'submit_job_ack' and not job.ack.done():
            job.ack.set_result(frame)
        elif kind == 'job_output':
            job.events.put_nowait(('output', frame.get('line')))
        elif kind == 'job_state_changed':
            job.events.put_nowait(('state', frame))
        elif kind == 'artifacts_start':
            job.artifacts = {'size': frame.get('total_bytes'), 'chunks': frame.get('num_chunks'),
                             'sha256': frame.get('artifacts_sha256'), 'parts': [], 'bytes': 0}
            if not isinstance(job.artifacts['size'], int) or not 0 < job.artifacts['size'] <= ARTIFACTS_MAX:
                job.events.put_nowait(('artifacts', {'accepted': False, 'reason': 'oversized'}))
                job.artifacts = None
            else:
                job.events.put_nowait(('fetching', job.artifacts['size']))
        elif kind == 'artifacts_chunk' and job.artifacts is not None:
            part = base64.b64decode(frame.get('data_b64') or '')
            if frame.get('chunk_index') != len(job.artifacts['parts']) or job.artifacts['bytes'] + len(part) > job.artifacts['size']:
                job.events.put_nowait(('artifacts', {'accepted': False, 'reason': 'out of order'}))
                job.artifacts = None
                return
            job.artifacts['parts'].append(part)
            job.artifacts['bytes'] += len(part)
        elif kind == 'artifacts_end':
            job.events.put_nowait(('artifacts', frame))


class BuildServer:
    """The pairing with one build server, the link to it while it is paired, and the builds sent to it.

    Stored in /data (build-server.json and this app's own key, build-server.key), never in a backup's way: a restored
    app pairs again. `view` is what the page shows (the live inventory's `build_server`)."""

    VERSION = 1

    def __init__(self, folder, changed=lambda: None, version=None):
        self.path, self.key_path = Path(folder) / 'build-server.json', Path(folder) / 'build-server.key'
        self.changed_cb = changed
        self.esphome = esphome_version() if version is None else version
        raw = atomic.read_json(self.path, self.VERSION) or {}
        # Random from its first character: the server names its folder for this app by the first eight (dir_id there).
        self.id = raw.get('id') if isinstance(raw.get('id'), str) and re.fullmatch(r'[A-Za-z0-9_-]{8,64}', raw['id']) else \
            secrets.token_hex(16)
        self.enabled = raw.get('enabled') is True
        server = raw.get('server') if isinstance(raw.get('server'), dict) else None
        self.server = None
        if server and isinstance(server.get('host'), str) and isinstance(server.get('pin'), str):
            self.server = {'host': server['host'], 'port': _port(server.get('port')), 'pin': server['pin'],
                           'name': _text(server.get('name')), 'esphome': _version(server.get('esphome')),
                           'state': server.get('state') if server.get('state') in ('paired', 'pending') else 'pending',
                           'since': server.get('since') if isinstance(server.get('since'), (int, float)) else time.time()}
        self.last = raw.get('last') if isinstance(raw.get('last'), dict) else None
        self.link = None
        self.connection = 'off'   # off, connecting, online, offline, refused, mismatch
        self.error = ''
        self.previewed = {}       # (host, port) -> the server's pin, from the preview the person checked
        self.task = None          # the link while paired, or the wait for the person to accept
        self.building = None      # what the server builds for this app now: {'file', 'phase', 'started'}
        # Per profile the bundle the server built last, its images and when: an update builds, then installs, the same
        # YAML, and the second asks the server nothing when nothing changed. A YAML that follows a branch (follows_branch)
        # is the same YAML after a push too, so its build is taken again only within the same update.
        self.built = {}
        self._private = None
        self.rev = int(time.time() * 1000)   # from the start time: a restarted app never counts below an open page

    # ---- what is stored ----
    def save(self):
        atomic.write_json(self.path, {'version': self.VERSION, 'id': self.id, 'enabled': self.enabled,
                                      'server': self.server, 'last': self.last})

    @property
    def private(self):
        """This app's own key for the link, made once: the server knows this app by it."""
        if self._private is None:
            try:
                text = self.key_path.read_text().strip()
                data = bytes.fromhex(text) if len(text) == 64 else None
            except (OSError, ValueError):
                data = None
            if data is None:
                data = secrets.token_bytes(32)
                atomic.write_text(self.key_path, data.hex(), 0o600)
            self._private = data
        return self._private

    @property
    def pin(self):
        """This app's own fingerprint, which the server shows when the person accepts it."""
        if NoiseConnection is None:
            return ''
        if getattr(self, '_pin', None) is None:
            from noise.backends.default.keypairs import KeyPair25519
            self._pin = pin_of(bytes(KeyPair25519.from_private_bytes(self.private).public_bytes))
        return self._pin

    def changed(self):
        # A number that only grows: the page keeps the newest of what an answer and the live stream bring it.
        self.rev += 1
        with contextlib.suppress(Exception):
            self.changed_cb()

    # ---- for the page ----
    def view(self):
        own = self.pin
        server = self.server
        queue = self.link.queue if self.link and self.connection == 'online' else None
        return {'rev': self.rev, 'available': NoiseConnection is not None, 'enabled': self.enabled, 'esphome': self.esphome,
                'own': {'pin': own, 'emoji': [{'emoji': e, 'name': n} for e, n in fingerprint(own)] if own else []},
                'server': None if not server else {
                    'host': server['host'], 'port': server['port'], 'name': server['name'] or server['host'],
                    'esphome': server['esphome'], 'state': server['state'], 'since': server['since'],
                    'emoji': [{'emoji': e, 'name': n} for e, n in fingerprint(server['pin'])]},
                'connection': self.connection if server else 'off', 'error': self.error,
                'queue': queue, 'building': self.building, 'last': self.last}

    def wanted(self):
        """Whether a build goes to the server first: on, and paired."""
        return bool(self.enabled and self.server and self.server['state'] == 'paired')

    # ---- pairing ----
    async def _one_shot(self, host, port, intent, details=None, expect=None, seconds=STEP_SECONDS + 5):
        timeout = aiohttp.ClientTimeout(total=seconds, sock_connect=STEP_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as http, \
                    http.ws_connect(_url(host, port), max_msg_size=FRAME_MAX, autoping=True) as ws:
                return await handshake(ws, self.private, intent, details, expect)
        except Refused:
            raise
        except aiohttp.WSServerHandshakeError as error:
            # Something answers there over HTTP, but not with the build server's WebSocket.
            LOG.info('Build server %s:%s: %s', host, port, error)
            raise Refused('protocol') from None
        except (asyncio.TimeoutError, aiohttp.ClientError, OSError) as error:
            LOG.info('Build server %s:%s: %s', host, port, error)
            raise Refused('unreachable') from None
        except Exception as error:  # noqa: BLE001 - anything else of the protocol: not a server we can talk to
            LOG.warning('Build server %s:%s answered something this app cannot read: %r', host, port, error)
            raise Refused('protocol') from None

    def _details(self, pairing_key=None):
        details = {'dashboard_id': self.id, 'label': 'Tessera', 'friendly_name': 'Tessera Screen Manager',
                   'ha_addon': False, 'label_auto': False}
        if pairing_key:
            details['pairing_key'] = pairing_key
        return details

    async def preview(self, host, port=None):
        """The server's name, ESPHome and fingerprint, for the person to compare with what the server shows."""
        host, port = _host(host), _port(port)
        _, answer, pin = await self._one_shot(host, port, 'preview')
        if answer['intent_response'] != 'ok':
            raise Refused('protocol')
        self.previewed[(host, port)] = pin
        return {'host': host, 'port': port, 'pin': pin, 'name': _text(answer.get('friendly_name')) or host,
                'esphome': _version(answer.get('esphome_version')), 'needs_key': answer.get('requires_pairing_key') is True,
                'provisions': answer.get('auto_provision_supported') is True,
                'emoji': [{'emoji': e, 'name': n} for e, n in fingerprint(pin)]}

    async def pair(self, host, port=None, pairing_key=None):
        """Ask the previewed server to let this app in. Approved at once (a known key, or a headless server's one-time
        key), or pending until the person accepts it on the server: a wait that runs on (`_wait_for_approval`)."""
        host, port = _host(host), _port(port)
        pin = self.previewed.get((host, port))
        if not pin:
            raise Refused('preview_first')
        key = _text(pairing_key, 64) or None
        _, answer, _ = await self._one_shot(host, port, 'pair_request', self._details(key), expect=pin)
        response = answer['intent_response']
        if response == 'no_pairing_window':
            raise Refused('no_window_key' if key else 'no_window')
        if response not in ('approved', 'pending', 'ok'):
            raise Refused('rejected')
        await self.stop()
        self.server = {'host': host, 'port': port, 'pin': pin, 'name': _text(answer.get('friendly_name')) or host,
                       'esphome': _version(answer.get('esphome_version')),
                       'state': 'pending' if response == 'pending' else 'paired', 'since': time.time()}
        if self.server['state'] == 'paired':
            self.enabled = True
        self.error, self.last = '', None   # the last build of another server says nothing about this one
        self.save()
        self.start()
        self.changed()
        return self.view()

    async def _wait_for_approval(self):
        """The person accepts (or refuses) on the server; the window closing ends the wait too."""
        server = self.server
        while self.server is server and server['state'] == 'pending':
            try:
                _, answer, _ = await self._one_shot(server['host'], server['port'], 'pair_status',
                                                    {'dashboard_id': self.id}, expect=server['pin'],
                                                    seconds=PAIR_WAIT_SECONDS)
            except Refused as error:
                self.connection, self.error = ('mismatch' if error.args[0] == 'mismatch' else 'offline'), error.args[0]
                self.changed()
                await asyncio.sleep(RETRY_SECONDS[-1])
                continue
            response = answer['intent_response']
            if response in ('approved', 'ok'):
                server['state'], self.enabled, self.error = 'paired', True, ''
                self.save()
                self.changed()
                return await self._keep_linked()
            if response == 'pending':
                continue
            # Refused, or the pairing window closed before anyone accepted.
            self.connection = 'refused'
            self.error = 'expired' if response == 'no_pairing_window' else 'rejected'
            self.changed()
            return

    async def forget(self):
        """Unpair: this app stops sending builds there. The server keeps its row until someone removes it there."""
        await self.stop()
        self.server, self.enabled, self.error, self.connection, self.last = None, False, '', 'off', None
        self.save()
        self.changed()
        return self.view()

    def set_enabled(self, enabled):
        if enabled and not (self.server and self.server['state'] == 'paired'):
            raise Refused('not_paired')
        self.enabled = bool(enabled)
        self.save()
        self.changed()
        return self.view()

    # ---- the link ----
    def start(self):
        """While paired, a link is kept, so the page shows whether the server is there and builds start at once."""
        if self.server and (self.task is None or self.task.done()):
            run = self._wait_for_approval if self.server['state'] == 'pending' else self._keep_linked
            self.task = asyncio.get_running_loop().create_task(run())

    async def stop(self):
        task, self.task = self.task, None
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self.link = None
        self.connection = 'off'

    async def _keep_linked(self):
        attempt = 0
        while self.server and self.server['state'] == 'paired':
            server = self.server
            self.connection = 'connecting' if attempt == 0 else self.connection
            self.changed()
            try:
                await self._session(server)
                attempt = 0
            except Refused as error:
                reason = error.args[0]
                self.connection, self.error = ('mismatch', reason) if reason == 'mismatch' else \
                    ('refused', reason) if reason in ('unknown', 'rejected') else ('offline', reason)
                self.changed()
                if self.connection in ('mismatch', 'refused'):
                    return   # only the person can mend this: pair again
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - any other trouble of one session: try again in a while
                LOG.info('Build server link: %r', error)
                self.connection, self.error = 'offline', 'unreachable'
                self.changed()
            self.link = None
            await asyncio.sleep(RETRY_SECONDS[min(attempt, len(RETRY_SECONDS) - 1)])
            attempt += 1

    async def _session(self, server):
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=STEP_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as http, \
                    http.ws_connect(_url(server['host'], server['port']), max_msg_size=FRAME_MAX) as ws:
                noise, answer, _ = await handshake(ws, self.private, 'peer_link',
                                                   {'dashboard_id': self.id, 'friendly_name': 'Tessera Screen Manager',
                                                    'ha_addon': False}, expect=server['pin'])
                if answer['intent_response'] != 'ok':
                    reason = answer.get('reason')
                    if reason == 'pending_not_approved':
                        raise Refused('pending')
                    raise Refused('unknown' if reason in ('no_approved_peer', 'pin_mismatch', 'bad_dashboard_id') else 'rejected')
                # The server's name and ESPHome as it says them now: renamed or updated since the pairing.
                name, version = _text(answer.get('friendly_name')), _version(answer.get('esphome_version'))
                if (name and name != server['name']) or (version and version != server['esphome']):
                    server['name'], server['esphome'] = name or server['name'], version or server['esphome']
                    self.save()
                self.link = Link(ws, noise, answer)
                self.connection, self.error = 'online', ''
                self.changed()
                LOG.info('Build server %s (%s:%s) is linked', server['name'], server['host'], server['port'])
                await self.link.run(self.changed)
                LOG.info('Build server link ended (%s)', self.link.reason)
        except (asyncio.TimeoutError, aiohttp.ClientError, OSError) as error:
            raise Refused('unreachable') from error
        finally:
            self.link = None
            if self.connection == 'online':
                self.connection = 'offline'
                self.changed()

    # ---- building ----
    async def compile(self, profile, root, data, env, log, phase, fresh=False):
        """Build `profile` (a screen's YAML in the ESPHome folder `root`) on the server. Returns the images it made,
        staged in data/build/<profile>/server: {'factory', 'ota', 'table'}. Raises Fallback (build here) or Failed.

        `log` takes one line of the build's log, `phase` each step for the page: bundle, send, queued, build, fetch.
        `fresh`: the server empties its build folder for this screen first (`esphome clean` there, a job of target
        "clean" on the same bundle), as Firmware.clean_build does here: a plugin part changed, and a component the
        earlier build left behind (screen camera's empty esp_h264 for a build without video) would shadow the real one
        and fail the build. Seen on a reTerminal D1001 going from Screen camera 0.2.0 to 0.6.13 with Video, 2026-10-29."""
        server = self.server
        if not self.wanted():
            raise Fallback('off')
        # Just restarted, or the server only now came back: give a link that is being made a moment.
        for _ in range(20):
            if self.link is not None or self.connection != 'connecting':
                break
            await asyncio.sleep(0.25)
        link = self.link
        if link is None:
            raise Fallback(self.connection if self.connection in ('refused', 'mismatch') else 'offline', self.error)
        name = server['name'] or server['host']
        started = time.monotonic()
        self.building = {'file': profile.name, 'phase': 'bundle', 'started': time.time()}
        self.changed()
        number = secrets.token_hex(12)
        job = None
        try:
            phase('bundle')
            bundle = await make_bundle(profile, root, env, log)
            # What is in it, not the gzip around it, whose header carries the time it was packed.
            digest = hashlib.sha256(gzip.decompress(bundle)).hexdigest()
            done = None if fresh else self.built.get(profile.name)
            if done and done[0] == digest and done[2] == server['pin'] and all(p is None or p.is_file() for p in done[1].values()) \
                    and (time.time() - done[3] < REUSE_MOVING_SECONDS or not follows_branch(profile)):
                log(f'Build server: the YAML is the same as in the build {name} just made; using that firmware.')
                now = time.time()
                for path in done[1].values():
                    if path is not None:
                        os.utime(path, (now, now))   # the newest again, over a build made here meanwhile
                return done[1]
            stem = profile.name.removesuffix('.yaml')
            if fresh:
                log(f'A plugin part changed: {name} empties its build folder for this screen first.')
                phase('send')
                self._phase('send')
                job = await self._submit(link, secrets.token_hex(12), profile, bundle, stem, 'clean')
                await self._follow(job, log, lambda step: None, name)
            log(f'Build server: sending the YAML to {name} ({max(1, round(len(bundle) / 1024))} KB).')
            phase('send')
            self._phase('send')
            job = await self._submit(link, number, profile, bundle, stem, 'compile')
            phase('queued')
            self._phase('queued')
            log(f'Build server: {name} took the build. ESPHome {self.esphome or "(its own)"}'
                + ('' if not self.esphome or self.esphome == server['esphome']
                   else f' is installed there once for this, beside its own {server["esphome"] or "ESPHome"}.'
                   if server['esphome'] else '.'))
            await self._follow(job, log, phase, name)
            phase('fetch')
            self._phase('fetch')
            log(f'Build server: fetching the firmware from {name}.')
            try:
                await link.send({'type': 'download_artifacts', 'job_id': number})
            except Exception as error:  # noqa: BLE001
                raise Fallback('lost', str(error)) from None
            archive = await self._artifacts(job)
            images = await asyncio.to_thread(stage_artifacts, archive, Path(data) / 'build' / stem / 'server')
            self.built[profile.name] = (digest, images, server['pin'], time.time())
            seconds = round(time.monotonic() - started)
            log(f'Build server: built on {name} in {seconds // 60} min {seconds % 60} s.')
            self.last = {'file': profile.name, 'where': 'server', 'server': name, 'seconds': seconds, 'at': time.time()}
            self.save()
            return images
        except asyncio.CancelledError:
            if job is not None:
                with contextlib.suppress(Exception):
                    await link.send({'type': 'cancel_job', 'job_id': number})
            raise
        except Fallback as fallback:
            self.last = {'file': profile.name, 'where': 'here', 'server': name, 'reason': fallback.reason, 'at': time.time()}
            self.save()
            if job is not None and fallback.reason == 'lost':
                with contextlib.suppress(Exception):
                    await link.send({'type': 'cancel_job', 'job_id': number})
            raise
        except Failed:
            self.last = {'file': profile.name, 'where': 'server', 'server': name, 'failed': True, 'at': time.time()}
            self.save()
            raise
        finally:
            link.jobs.pop(number, None)
            self.building = None
            self.changed()

    def _phase(self, step):
        if self.building:
            self.building['phase'] = step
            self.changed()

    async def _submit(self, link, number, profile, bundle, stem, target):
        """One job to the server: its header, the bundle in chunks, and its ack. `target` is "compile" or "clean"."""
        job = link.jobs[number] = Job(number)
        header = {'type': 'submit_job', 'job_id': number, 'configuration_filename': profile.name, 'target': target,
                  'total_bundle_bytes': len(bundle), 'num_chunks': (len(bundle) + CHUNK - 1) // CHUNK,
                  'bundle_sha256': hashlib.sha256(bundle).hexdigest(), 'device_name': stem,
                  'device_friendly_name': stem, 'target_esphome_version': self.esphome, 'skip_bootloader': False}
        try:
            await link.send(header)
            for index in range(header['num_chunks']):
                part = bundle[index * CHUNK:(index + 1) * CHUNK]
                await link.send({'type': 'submit_job_chunk', 'job_id': number, 'chunk_index': index,
                                 'data_b64': base64.b64encode(part).decode(), 'is_last': index == header['num_chunks'] - 1})
            ack = await asyncio.wait_for(job.ack, ACK_SECONDS)
        except (asyncio.TimeoutError, ConnectionError, aiohttp.ClientError, OSError, RuntimeError) as error:
            raise Fallback('lost', str(error)) from None
        if not ack.get('accepted'):
            raise Fallback('refused_job', _text(ack.get('reason'), 80))
        return job

    async def _follow(self, job, log, phase, name):
        """The build on the server until it ended: its log lines here, its steps for the page."""
        deadline = time.monotonic() + BUILD_SECONDS
        while True:
            try:
                kind, value = await asyncio.wait_for(job.events.get(), max(1, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                raise Fallback('lost', 'the build took longer than two hours') from None
            if kind == 'output':
                if isinstance(value, str):
                    log(ESCAPED.sub('', value))
            elif kind == 'lost':
                raise Fallback('lost', value)
            elif kind == 'state':
                status = value.get('status')
                if status == 'running':
                    phase('build')
                    self._phase('build')
                elif status == 'completed':
                    return
                elif status == 'failed':
                    message = _text(value.get('error_message'), 300)
                    if value.get('failure_reason') == 'provision':
                        raise Fallback('provision', message)
                    raise Failed(f'The build failed on {name}' + (f': {message}' if message else '; see the log.'))
                elif status == 'cancelled':
                    raise Fallback('cancelled', _text(value.get('error_message'), 300))

    async def _artifacts(self, job):
        deadline = time.monotonic() + 600
        while True:
            try:
                kind, value = await asyncio.wait_for(job.events.get(), max(1, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                raise Fallback('fetch', 'no firmware came back') from None
            if kind == 'lost':
                raise Fallback('lost', value)
            if kind != 'artifacts':
                continue
            if not value.get('accepted'):
                raise Fallback('fetch', _text(value.get('detail') or value.get('reason'), 200))
            got = job.artifacts
            if got is None:
                raise Fallback('fetch', 'the firmware came back incomplete')
            data = b''.join(got['parts'])
            if len(data) != got['size'] or hashlib.sha256(data).hexdigest() != got['sha256']:
                raise Fallback('fetch', 'the firmware came back damaged')
            return data


# A screen's YAML whose packages come from a branch (`ref: dev` or `ref: main`, the app's channels) builds something
# else after every push with the same text: the server fetches the branch as it builds, the bundle carries only the
# YAML. Its build is taken again only this long after it was made, the build and the install of one update; a
# release tag or a commit always builds the same. Seen 2026-10-29: a reinstall from dev took the build of 37 minutes
# before and installed the firmware the screen already had.
REUSE_MOVING_SECONDS = 120
MOVING_REF = re.compile(r'(?m)^[ \t]+ref:[ \t]*["\']?(?:main|dev)["\']?[ \t]*(?:#.*)?$')


def follows_branch(profile):
    """True when the screen's YAML takes a package from a branch (MOVING_REF); also when it cannot be read."""
    try:
        return bool(MOVING_REF.search(Path(profile).read_text()))
    except (OSError, UnicodeDecodeError):
        return True


async def make_bundle(profile, root, env, log):
    """`esphome bundle` of the screen's YAML, with the plugins kept in a folder beside the ESPHome folder put inside it
    (bundle_folder_plugins): ESPHome leaves out what lies outside its folder, and the server has only the bundle."""
    with tempfile.TemporaryDirectory(prefix='tessera-bundle-') as folder:
        out = Path(folder) / 'bundle.tar.gz'
        process = await asyncio.create_subprocess_exec('esphome', 'bundle', str(profile), '-o', str(out), cwd=root, env=env,
                                                       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                       start_new_session=True)
        lines = []
        try:
            async with asyncio.timeout(BUNDLE_SECONDS):
                async for line in process.stdout:
                    lines.append(line.decode(errors='replace').rstrip())
                code = await process.wait()
        except (asyncio.TimeoutError, asyncio.CancelledError):
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            raise Fallback('bundle', 'packing the YAML took too long') from None
        if code or not out.is_file():
            for line in lines[-20:]:
                log(line)
            raise Fallback('bundle', lines[-1] if lines else f'esphome bundle exited {code}')
        data = out.read_bytes()
    return await asyncio.to_thread(bundle_folder_plugins, data, Path(root), profile.name.removesuffix('.yaml'))


def bundle_folder_plugins(data, root, stem, folder='tessera-plugins'):
    """The bundle with the plugins a screen takes from a folder beside the ESPHome folder (docs/PLUGINS.md, `../<folder>/`)
    copied into it, and the screen's plugins file pointing there. Returns `data` unchanged when it has none."""
    sidecar = f'{stem}.plugins.yaml'
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        members = {member.name: member for member in tar.getmembers()}
        if sidecar not in members:
            return data
        text = tar.extractfile(members[sidecar]).read().decode()
        ids = sorted(set(re.findall(rf'\.\./{re.escape(folder)}/([A-Za-z0-9_-]+)', text)))
        if not ids:
            return data
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:gz') as new:
            for name, member in members.items():
                if name == sidecar:
                    _add(new, name, text.replace(f'../{folder}/', f'{folder}/').encode())
                elif name == 'manifest.json':
                    manifest = json.loads(tar.extractfile(member).read())
                    extra = [f'{folder}/{p.relative_to(root.parent / folder)}' for plugin in ids
                             for p in sorted((root.parent / folder / plugin).rglob('*')) if _plain(p)]
                    manifest['files'] = list(manifest.get('files') or []) + extra
                    _add(new, name, json.dumps(manifest, indent=2).encode())
                else:
                    new.addfile(member, tar.extractfile(member) if member.isfile() else None)
            for plugin in ids:
                base = root.parent / folder / plugin
                for path in sorted(base.rglob('*')):
                    if _plain(path):
                        _add(new, f'{folder}/{path.relative_to(root.parent / folder)}', path.read_bytes())
        return out.getvalue()


def _plain(path):
    return path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts and not path.name.startswith('.')


def _add(tar, name, payload):
    info = tarfile.TarInfo(name=name)
    info.size, info.mode, info.mtime = len(payload), 0o644, 0
    tar.addfile(info, io.BytesIO(payload))


def stage_artifacts(archive, target):
    """The build the server sent back, into `target` (data/build/<profile>/server) as a local build lays it out, so the
    app's own lookups find it (Firmware.FACTORY_IMAGES, OTA_IMAGES): {'factory', 'ota', 'table'} paths, None where the
    build made none. Only plain files inside `target`; the debug symbols stay out."""
    target = Path(target)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    root = target.resolve()
    storage = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            if not member.isfile() or name.is_absolute() or '..' in name.parts or '\\' in member.name:
                continue
            if member.name == 'storage.json':
                with contextlib.suppress(ValueError):
                    storage = json.loads(tar.extractfile(member).read())
                continue
            if name.suffix in SKIP_SUFFIXES or member.name in ('idedata.json', 'platformio.ini'):
                continue
            total += member.size
            if total > ARTIFACTS_MAX:
                raise Fallback('fetch', 'the firmware came back too large')
            path = (target / member.name).resolve()
            if not path.is_relative_to(root):
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, open(path, 'wb') as sink:
                shutil.copyfileobj(source, sink)
    node = storage.get('name') if isinstance(storage.get('name'), str) and re.fullmatch(r'[A-Za-z0-9_-]+', storage['name']) else None

    def first(*patterns):
        for pattern in patterns:
            found = sorted(target.glob(pattern))
            if found:
                return found[0]
        return None
    factory = first('build/firmware.factory.bin', '.pioenvs/*/firmware.factory.bin')
    ota = first('build/firmware.ota.bin', '.pioenvs/*/firmware.ota.bin', *([f'build/{node}.bin'] if node else []),
                '.pioenvs/*/firmware.bin')
    # With ESPHome's own ESP-IDF the image an update sends is build/<node>.bin: beside it under the name the app looks
    # for (Firmware.OTA_IMAGES), so its size and its room for plugins read as for a build made here.
    if ota is not None and ota.parent == target / 'build' and ota.name != 'firmware.ota.bin':
        shutil.copyfile(ota, target / 'build' / 'firmware.ota.bin')
        ota = target / 'build' / 'firmware.ota.bin'
    table = first('build/partition_table/partition-table.bin', '.pioenvs/*/partitions.bin')
    if factory is None and ota is None:
        raise Fallback('fetch', 'the server sent no firmware image')
    # Newer than any build made here before, so the app's lookups (the newest wins) take these.
    now = time.time()
    for path in target.rglob('*'):
        if path.is_file():
            os.utime(path, (now, now))
    return {'factory': factory, 'ota': ota, 'table': table}
