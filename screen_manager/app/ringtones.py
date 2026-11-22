"""A call's ringtone, chosen on the editor's Events page, Calls (docs/CALLS.md, "Ringtone").

A ringtone is a WAV file of 16 kHz, mono, 16 bits, at most MAX_SECONDS long, that holds its own pause: the screen plays
it back to back for as long as it rings. It reaches the screen as a file of this app (screen_files): a ring's op `call`
carries `rt`, the link of the tone chosen for that screen, and the screen downloads it once and keeps it until a ring
names another.

Four come with the app, made here at each start (BUILT_IN); `classic` is the tone a screen made itself before ringtones
(module_call.cpp, make_ring), which it still rings with when no tone comes. Someone can add their own: the editor cuts,
filters and levels the sound in the browser (web/src/model/ringtone.ts) and sends the finished WAV, which this checks
and keeps (`own`). The choice is one for every screen (`default`) and, where someone set one, a screen's own.

The tones are bright on purpose: the small speakers of these screens carry 1.4 to 1.9 kHz best, and 523 Hz at a quarter
of full scale could not be heard at half volume (a reTerminal D1001, 2026-11-10).
"""
import array
import io
import json
import math
import threading
import wave
from pathlib import Path

import atomic

VERSION = 1
RATE = 16000
MAX_SECONDS = 3.0
MIN_SECONDS = 0.25
MAX_OWN = 12
NAME_MOST = 40
CLASSIC = 'classic'
OWN = 'own-'


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


def _notes(out, notes, decay, partials):
    for start, freq in notes:
        first = int(start * RATE)
        for i in range(first, len(out)):
            t = (i - first) / RATE
            envelope = math.exp(-t * decay) * min(t / 0.004, 1.0)
            if envelope < 0.001:
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


BUILT_IN = {CLASSIC: _classic, 'marimba': _marimba, 'digital': _digital, 'bell': _bell}


def to_wav(samples):
    """16-bit mono WAV bytes of `samples` (floats in -1..1), levelled so the loudest is at 97 % of full scale."""
    peak = max((abs(s) for s in samples), default=0.0) or 1.0
    gain = 0.97 / peak
    pcm = array.array('h', (max(-32767, min(32767, int(round(s * gain * 32767)))) for s in samples))
    if pcm.itemsize != 2:
        raise RuntimeError('array h is not 16 bits')
    if not _little_endian():
        pcm.byteswap()
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return out.getvalue()


def _little_endian():
    return array.array('h', [1]).tobytes()[0] == 1


def checked(data):
    """A ringtone someone sent, as a plain WAV of this app: 16 kHz, mono, 16 bits, MIN_SECONDS to MAX_SECONDS.
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


class Ringtones:
    def __init__(self, data_dir, files):
        self.files = files
        self.path = Path(data_dir) / 'ringtones.json'
        self.lock = threading.RLock()
        data = atomic.read_json(self.path, VERSION) or {}
        self.default = data.get('default') if isinstance(data.get('default'), str) else CLASSIC
        self.screens = {str(k): v for k, v in (data.get('screens') or {}).items() if isinstance(v, str)} if isinstance(data.get('screens'), dict) else {}
        self.own = [o for o in data.get('own') or [] if isinstance(o, dict) and isinstance(o.get('id'), str)
                    and isinstance(o.get('name'), str) and isinstance(o.get('file'), str)]
        self.built = {key: files.add(to_wav(make()), 'wav', keep=False) for key, make in BUILT_IN.items()}
        if self.default not in self.ids():
            self.default = CLASSIC

    def save(self):
        with self.lock:
            atomic.write_json(self.path, {'version': VERSION, 'default': self.default, 'screens': self.screens, 'own': self.own},
                              0o644, separators=(',', ':'))

    def ids(self):
        return list(self.built) + [o['id'] for o in self.own]

    def file_of(self, tone):
        if tone in self.built:
            return self.built[tone]
        return next((o['file'] for o in self.own if o['id'] == tone), None)

    def tone_of(self, screen):
        """The tone a screen rings with: its own choice, else the one for every screen."""
        tone = self.screens.get(str(screen))
        return tone if tone in self.ids() else self.default

    def link(self, base, screen):
        """The link of the tone `screen` rings with, for a ring's `rt`."""
        name = self.file_of(self.tone_of(screen)) or self.built[CLASSIC]
        return self.files.link(base, name)

    def view(self, screens):
        """What the editor shows: every tone, the one for every screen, and each screen that can ring with its own."""
        tones = [{'id': key, 'built_in': True, 'file': name} for key, name in self.built.items()]
        tones += [{'id': o['id'], 'name': o['name'], 'built_in': False, 'file': o['file']} for o in self.own]
        return {'rate': RATE, 'max_seconds': MAX_SECONDS, 'min_seconds': MIN_SECONDS, 'max_own': MAX_OWN, 'name_most': NAME_MOST,
                'default': self.default, 'tones': tones,
                'screens': [{**screen, 'tone': self.screens.get(str(screen['id']), '')} for screen in screens]}

    def wav(self, tone):
        name = self.file_of(tone)
        found = self.files.get(name) if name else None
        return found[0] if found else None

    def add(self, name, data):
        """Keeps a tone someone made; its id. ValueError: 'name', 'many', or what checked() found."""
        name = ' '.join(str(name or '').split())[:NAME_MOST]
        if not name:
            raise ValueError('name')
        wav_bytes = checked(data)
        with self.lock:
            if len(self.own) >= MAX_OWN:
                raise ValueError('many')
            file = self.files.add(wav_bytes, 'wav')
            tone = OWN + file[:12]
            if tone not in self.ids():
                self.own.append({'id': tone, 'name': name, 'file': file})
                self.save()
            return tone

    def remove(self, tone):
        """Forgets a tone someone made; the screens that rang with it ring with the one for every screen."""
        with self.lock:
            gone = next((o for o in self.own if o['id'] == tone), None)
            if gone is None:
                raise ValueError('unknown')
            self.own.remove(gone)
            self.screens = {screen: chosen for screen, chosen in self.screens.items() if chosen != tone}
            if self.default == tone:
                self.default = CLASSIC
            if not any(o['file'] == gone['file'] for o in self.own):
                self.files.remove(gone['file'])
            self.save()

    def choose(self, screen, tone):
        """`tone` for `screen`, or for every screen when `screen` is empty. A screen's '' follows every screen's."""
        with self.lock:
            if not screen:
                if tone not in self.ids():
                    raise ValueError('unknown')
                self.default = tone
            elif not tone:
                self.screens.pop(str(screen), None)
            elif tone in self.ids():
                self.screens[str(screen)] = tone
            else:
                raise ValueError('unknown')
            self.save()

    def forget_screen(self, screen):
        with self.lock:
            if self.screens.pop(str(screen), None) is not None:
                self.save()


def dumps(view):
    return json.dumps(view, separators=(',', ':'))
