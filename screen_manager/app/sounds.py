"""The sounds a screen plays, chosen on the editor's Events page (docs/SOUNDS.md): what rings when another screen calls
(`call`), the chime when a doorbell rings (`doorbell`) and the tone of an alert (`alert`).

A sound is a WAV file of 16 kHz, mono, 16 bits. It reaches a screen as a file of this app (screen_files): the message
that needs it carries its link (a ring's `rt`, a doorbell's `ch`, the op `sound` beside an alert), and the screen
downloads it once and keeps it until a message names another. A call's tone holds its own pause and plays back to back
for as long as it rings; a chime and an alert's tone play once.

One library for every kind. Six sounds come with the app, made here at each start (BUILT_IN); `classic` is the ring a
screen made itself before (module_call.cpp, make_ring) and `chime` its doorbell's ding-dong (module_doorbell.cpp,
make_chime), which a screen still plays when no file comes. Someone can add their own: the editor cuts, filters and
levels the sound in the browser (web/src/model/ringtone.ts) and sends the finished WAV, which this checks and keeps
(`own`); a sound of one's own can be chosen for every kind whose length it fits. Per kind the choice is one for every
screen (`default`) and, where someone set one, a screen's own; NONE is silence.

Nothing changes by itself: a call rings Classic, a doorbell chimes Ding-dong and an alert stays silent until someone
chooses otherwise.

The sounds are bright on purpose: the small speakers of these screens carry 1.4 to 1.9 kHz best, and 523 Hz at a quarter
of full scale could not be heard at half volume (a reTerminal D1001, 2026-11-10).
"""
import array
import io
import math
import threading
import wave
from pathlib import Path

import atomic

VERSION = 1
RATE = 16000
MIN_SECONDS = 0.25
MAX_OWN = 12
NAME_MOST = 40
NONE = 'none'
OWN = 'own-'
# What a screen does with each kind, and how long a sound of it may be: a call's tone loops (its pause included), the
# others play once.
# A kind's `volume` is where it starts (VOLUME, below): a call rings with the speaker raised to the top, a chime and an
# alert's sound play at the screen's own volume, so the chime starts as loud as the screen's own ding-dong was (about
# -7 dB); at -20 dB it was barely heard on a Guition 10.1 (2026-11-22).
KINDS = {
    'call': {'default': 'classic', 'max_seconds': 3.0, 'loops': True, 'volume': -20},
    'doorbell': {'default': 'chime', 'max_seconds': 5.0, 'loops': False, 'volume': -7},
    'alert': {'default': NONE, 'max_seconds': 3.0, 'loops': False, 'volume': -20},
}
MAX_SECONDS = max(kind['max_seconds'] for kind in KINDS.values())
# The largest WAV someone may send: the longest sound and room for its head.
MOST_BYTES = int(MAX_SECONDS * RATE * 2) + 4096
# The screen's feature for sounds as files (the hello's `sounds`): a doorbell's chime and an alert's tone. A call's ring
# needs none: the module call reads `rt` since it came.
FEATURE = 'sounds'
# Where every sound's loudest sample sits: half of full scale (-6 dB). At 97 % the speakers distorted with the volume a
# ring stands at (the owner heard it on the Guition 10.1 and the D1001, 2026-11-22); the editor levels to the same
# (web/src/model/ringtone.ts, PEAK).
LEVEL = 0.5
# How loud a screen plays each kind: the loudest sample of what it gets, in dB of full scale (the editor's Volume). The
# app makes the file at that volume (at_volume), so a screen needs nothing new for it. At -6 dB the speakers of the
# Guition 10.1 still distorted a ring; the owner chose -20 dB of -10, -14 and -20 (2026-11-22). A kind starts at its own
# `volume` (KINDS); one is kept only once someone moves its slider, so a kind nobody set follows its start.
VOLUME = -20
VOLUME_RANGE = (-40, 0)
# How long the Test key lets a screen ring (server.sound_test).
TEST_RING_SECONDS = 6


def _blank(seconds):
    return [0.0] * int(round(seconds * RATE))


def _classic():
    # module_call.cpp, make_ring: two bursts of a two-tone ring, 1.1 s, the next ring 3 s after the last.
    out = _blank(3.0)
    low, high, burst, gap, length = 1400.0, 1900.0, 0.42, 0.56, 1.1
    for i in range(int(length * RATE)):
        t = i / RATE
        u = t if t < gap else t - gap
        if u > burst:
            continue
        edge = min(min(u, burst - u) / 0.012, 1.0)
        out[i] = edge * (math.sin(2 * math.pi * low * t) + math.sin(2 * math.pi * high * t)) * 0.49
    return out


def _notes(out, notes, decay, partials, attack=0.004):
    for start, freq in notes:
        first = int(start * RATE)
        for i in range(first, len(out)):
            t = (i - first) / RATE
            envelope = math.exp(-t * decay) * min(t / attack, 1.0)
            if t > attack and envelope < 0.001:
                break
            out[i] += envelope * sum(level * math.sin(2 * math.pi * freq * k * t) for k, level in partials)
    return out


def _marimba():
    # Three rising notes, twice, like a struck bar: the fundamental and its fourth partial, dying away.
    notes = [(0.00, 1319.0), (0.15, 1568.0), (0.30, 1976.0), (0.70, 1319.0), (0.85, 1568.0), (1.00, 1976.0)]
    return _notes(_blank(2.4), notes, 9.0, ((1, 1.0), (4, 0.18)))


def _digital():
    # Two runs of four short beeps.
    out = _blank(2.2)
    for run in (0.0, 0.7):
        for beep in range(4):
            first = int((run + beep * 0.12) * RATE)
            for i in range(int(0.07 * RATE)):
                t = i / RATE
                edge = min(min(t, 0.07 - t) / 0.004, 1.0)
                out[first + i] = edge * (math.sin(2 * math.pi * 2000.0 * t) + 0.3 * math.sin(2 * math.pi * 6000.0 * t))
    return out


def _bell():
    # An old telephone's bell: two trills of two clappers at 20 strokes a second.
    out = _blank(3.0)
    for start in (0.0, 0.6):
        for stroke in range(8):
            _notes(out, [(start + stroke * 0.05, 1750.0)], 14.0, ((1, 1.0), (1.23, 0.6), (2.0, 0.25)))
    return out


def _chime():
    # module_doorbell.cpp, make_chime: E5 then C5 0.55 s later, a bell's partials dying away over 1.9 s.
    out = _blank(1.9)
    for n, freq in enumerate((659.25, 523.25)):
        for i in range(int(n * 0.55 * RATE), len(out)):
            u = i / RATE - n * 0.55
            envelope = min(1.0, u / 0.006) * math.exp(-u / 0.42)
            out[i] += sum(level * envelope * math.sin(2 * math.pi * freq * k * u) for k, level in ((1, 1.0), (2, 0.32), (3, 0.1)))
    return [max(-1.0, min(1.0, s * 0.33)) for s in out]


def _notice():
    # Two short rising notes: something to look at, not an alarm.
    return _notes(_blank(1.0), [(0.0, 1568.0), (0.16, 2093.0)], 7.0, ((1, 1.0), (2, 0.12)))


BUILT_IN = {'classic': _classic, 'marimba': _marimba, 'digital': _digital, 'bell': _bell, 'chime': _chime, 'notice': _notice}


def to_wav(samples, levelled=True):
    """16-bit mono WAV bytes of `samples` (floats in -1..1), with `levelled` the loudest at LEVEL of full scale."""
    peak = max((abs(s) for s in samples), default=0.0) or 1.0
    gain = LEVEL / peak if levelled else 1.0
    pcm = array.array('h', (max(-32767, min(32767, int(round(s * gain * 32767)))) for s in samples))
    if array.array('h', [1]).tobytes()[0] != 1:
        pcm.byteswap()
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return out.getvalue()


def seconds_of(data):
    with wave.open(io.BytesIO(bytes(data)), 'rb') as w:
        return w.getnframes() / w.getframerate()


def checked(data):
    """A sound someone sent, as a plain WAV of this app: 16 kHz, mono, 16 bits, MIN_SECONDS to MAX_SECONDS.
    Raises ValueError with what is wrong."""
    try:
        with wave.open(io.BytesIO(bytes(data)), 'rb') as w:
            if w.getcomptype() != 'NONE':
                raise ValueError('format')
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != RATE:
                raise ValueError('format')
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as error:
        raise ValueError('format') from error
    seconds = len(frames) / 2 / RATE
    if seconds < MIN_SECONDS:
        raise ValueError('short')
    if seconds > MAX_SECONDS + 0.01:
        raise ValueError('long')
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)
    return out.getvalue()


class Sounds:
    def __init__(self, data_dir, files):
        self.files = files
        self.path = Path(data_dir) / 'sounds.json'
        self.lock = threading.RLock()
        data = atomic.read_json(self.path, VERSION) or self._ringtones(Path(data_dir) / 'ringtones.json')
        self.own = [o for o in data.get('own') or [] if isinstance(o, dict) and isinstance(o.get('id'), str)
                    and isinstance(o.get('name'), str) and isinstance(o.get('file'), str)]
        self.built = {key: files.add(to_wav(make(), levelled=key != 'chime'), 'wav', keep=False) for key, make in BUILT_IN.items()}
        self.length = {key: seconds_of(files.get(name)[0]) for key, name in self.built.items()}
        for o in self.own:
            found = files.get(o['file'])
            self.length[o['id']] = seconds_of(found[0]) if found else 0.0
        stored = data.get('kinds') if isinstance(data.get('kinds'), dict) else {}
        self.kinds = {}
        for kind, rule in KINDS.items():
            mine = stored.get(kind) if isinstance(stored.get(kind), dict) else {}
            default = mine.get('default') if self.fits(kind, mine.get('default')) else rule['default']
            screens = {str(k): v for k, v in (mine.get('screens') or {}).items() if self.fits(kind, v)} if isinstance(mine.get('screens'), dict) else {}
            volume = mine.get('volume')
            volume = int(volume) if isinstance(volume, (int, float)) and not isinstance(volume, bool) and VOLUME_RANGE[0] <= volume <= VOLUME_RANGE[1] else None
            self.kinds[kind] = {'default': default, 'screens': screens}
            if volume is not None:
                self.kinds[kind]['volume'] = volume
        self.made = {}  # (file, volume): the name of that file at that volume (at_volume)

    @staticmethod
    def _ringtones(path):
        """The store of the first version on dev, a call's ringtone alone (ringtones.json), as this one."""
        old = atomic.read_json(path, VERSION) or {}
        if not old:
            return {}
        return {'own': old.get('own') or [], 'kinds': {'call': {'default': old.get('default'), 'screens': old.get('screens') or {}}}}

    def save(self):
        with self.lock:
            atomic.write_json(self.path, {'version': VERSION, 'own': self.own, 'kinds': self.kinds}, 0o644, separators=(',', ':'))

    def ids(self):
        return list(self.built) + [o['id'] for o in self.own]

    def fits(self, kind, sound):
        """Whether `sound` can be chosen for `kind`: silence, or a sound no longer than the kind allows."""
        if sound == NONE:
            return True
        return isinstance(sound, str) and sound in self.length and self.length[sound] <= KINDS[kind]['max_seconds'] + 0.01

    def file_of(self, sound):
        if sound in self.built:
            return self.built[sound]
        return next((o['file'] for o in self.own if o['id'] == sound), None)

    def sound_of(self, kind, screen):
        """The sound a screen plays for `kind`: its own choice, else the one for every screen."""
        mine = self.kinds[kind]
        sound = mine['screens'].get(str(screen))
        return sound if self.fits(kind, sound) else mine['default']

    def link(self, kind, base, screen):
        """The link of the sound `screen` plays for `kind`, or NONE for silence: a message's field for it."""
        sound = self.sound_of(kind, screen)
        if sound == NONE:
            return NONE
        name = self.file_of(sound) or self.built['classic']
        return self.files.link(base, self.at_volume(name, self.volume_of(kind)))

    def volume_of(self, kind):
        """How loud `kind` plays: what someone set, else where the kind starts."""
        return self.kinds[kind].get('volume', KINDS[kind].get('volume', VOLUME))

    def at_volume(self, name, volume):
        """The file `name` with its loudest sample at `volume` dB of full scale: a file of its own, held in memory and made
        again after a restart as a screen asks for it; the same file and volume are the same name, so a screen keeps it."""
        key = (name, volume)
        if key not in self.made:
            found = self.files.get(name)
            if not found:
                return name
            with wave.open(io.BytesIO(found[0]), 'rb') as w:
                pcm = array.array('h', w.readframes(w.getnframes()))
            if array.array('h', [1]).tobytes()[0] != 1:
                pcm.byteswap()
            peak = max((abs(x) for x in pcm), default=0) or 1
            gain = 32767 * 10 ** (volume / 20) / peak
            out = array.array('h', (max(-32767, min(32767, int(round(x * gain)))) for x in pcm))
            if array.array('h', [1]).tobytes()[0] != 1:
                out.byteswap()
            data = io.BytesIO()
            with wave.open(data, 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(out.tobytes())
            self.made[key] = self.files.add(data.getvalue(), 'wav', keep=False)
        return self.made[key]

    def set_volume(self, kind, volume):
        """The volume of `kind`, in whole dB within VOLUME_RANGE."""
        if kind not in KINDS or isinstance(volume, bool) or not isinstance(volume, (int, float)) or not VOLUME_RANGE[0] <= volume <= VOLUME_RANGE[1]:
            raise ValueError('volume')
        with self.lock:
            self.kinds[kind]['volume'] = int(round(volume))
            self.save()

    def view(self, screens):
        """What the editor shows: every sound with its length, and per kind its limit, the one for every screen and each
        screen that can play it with its own (`screens`: {kind: [{id, name}]})."""
        sounds = [{'id': key, 'built_in': True, 'file': name, 'seconds': round(self.length[key], 2)} for key, name in self.built.items()]
        sounds += [{'id': o['id'], 'name': o['name'], 'built_in': False, 'file': o['file'], 'seconds': round(self.length.get(o['id'], 0), 2)}
                   for o in self.own]
        kinds = {kind: {'default': self.kinds[kind]['default'], 'max_seconds': rule['max_seconds'], 'loops': rule['loops'],
                        'volume': self.volume_of(kind),
                        'screens': [{**screen, 'sound': self.kinds[kind]['screens'].get(str(screen['id']), '')} for screen in screens.get(kind, [])]}
                 for kind, rule in KINDS.items()}
        return {'rate': RATE, 'min_seconds': MIN_SECONDS, 'max_seconds': MAX_SECONDS, 'max_own': MAX_OWN, 'name_most': NAME_MOST,
                'volume_range': list(VOLUME_RANGE),
                'sounds': sounds, 'kinds': kinds}

    def wav(self, sound, volume=None):
        """The WAV of `sound`, at `volume` dB when given (what a screen gets), else as it is kept."""
        name = self.file_of(sound)
        if name and volume is not None:
            name = self.at_volume(name, volume)
        found = self.files.get(name) if name else None
        return found[0] if found else None

    def add(self, name, data):
        """Keeps a sound someone made; its id. ValueError: 'name', 'many', or what checked() found."""
        name = ' '.join(str(name or '').split())[:NAME_MOST]
        if not name:
            raise ValueError('name')
        wav_bytes = checked(data)
        with self.lock:
            if len(self.own) >= MAX_OWN:
                raise ValueError('many')
            file = self.files.add(wav_bytes, 'wav')
            sound = OWN + file[:12]
            if sound not in self.ids():
                self.own.append({'id': sound, 'name': name, 'file': file})
                self.length[sound] = seconds_of(wav_bytes)
                self.save()
            return sound

    def remove(self, sound):
        """Forgets a sound someone made; whatever played it plays the kind's own sound again."""
        with self.lock:
            gone = next((o for o in self.own if o['id'] == sound), None)
            if gone is None:
                raise ValueError('unknown')
            self.own.remove(gone)
            self.length.pop(sound, None)
            for kind, mine in self.kinds.items():
                mine['screens'] = {screen: chosen for screen, chosen in mine['screens'].items() if chosen != sound}
                if mine['default'] == sound:
                    mine['default'] = KINDS[kind]['default']
            if not any(o['file'] == gone['file'] for o in self.own):
                self.files.remove(gone['file'])
            self.save()

    def choose(self, kind, screen, sound):
        """`sound` for `kind` on `screen`, or on every screen when `screen` is empty. A screen's '' follows every screen's."""
        if kind not in KINDS:
            raise ValueError('unknown')
        with self.lock:
            mine = self.kinds[kind]
            if not screen:
                if not self.fits(kind, sound):
                    raise ValueError('unknown')
                mine['default'] = sound
            elif not sound:
                mine['screens'].pop(str(screen), None)
            elif self.fits(kind, sound):
                mine['screens'][str(screen)] = sound
            else:
                raise ValueError('unknown')
            self.save()

    def forget_screen(self, screen):
        with self.lock:
            gone = [mine['screens'].pop(str(screen), None) for mine in self.kinds.values()]
            if any(sound is not None for sound in gone):
                self.save()


def sound_message(link):
    """The op `sound` (docs/SOUNDS.md): play the file of `link` once, as an alert's tone."""
    return {'v': 1, 'op': 'sound', 'u': link}
