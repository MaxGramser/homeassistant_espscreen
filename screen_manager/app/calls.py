"""The add-on holds every call between screens (docs/CALLS.md, "Signalling"). This is the state machine and nothing else:
no Home Assistant, no sockets, no clock of its own, so tests/test_calls.py drives it whole. The Manager gives it what
happened (a screen dialled, answered, went away, a doorbell rang there) and carries out what it answers: `Say` a state to a
screen, and `Fire` an event once per call into Home Assistant.

A screen is in at most one call. A ring nobody answers is missed after RING_SECONDS. A doorbell's ring during a call goes
first: the call is held, muted on both ends, and comes back when the ring's view closes. When the add-on starts, no call
is left: both ends of whatever a screen thinks it is in hear `end` (`Calls.forget`).
"""
import array
from dataclasses import dataclass
import math
import secrets

RING_SECONDS = 45
TILE, FEATURE, FIRMWARE = 'screen.call', 'call', '0.62.0'  # the first firmware with the module call
ROWS_A_MESSAGE, NAME_MOST = 12, 32

# What a screen is shown (the op `call`'s `s`).
OUT, RING, LIVE, HELD, END = 'out', 'ring', 'live', 'held', 'end'
# Why a call ended (the op's `w`).
DECLINED, BUSY, MISSED, NO_ANSWER, GONE, QUIET, HUNG_UP = 'declined', 'busy', 'missed', 'no_answer', 'gone', 'quiet', 'hung_up'
# Events into Home Assistant, once per call.
STARTED, ANSWERED, MISSED_EVENT, ENDED = 'esp_screens_call_started', 'esp_screens_call_answered', 'esp_screens_call_missed', 'esp_screens_call_ended'
# A screen in the list (`contacts`): what it can be called for now.
FREE, IN_CALL, DND, OFFLINE = 'free', 'busy', 'quiet', 'offline'


@dataclass(frozen=True)
class Say:
    """Tell screen `node` the state of call `key`: `peer` is the other end, `why` a reason on END."""
    node: str
    key: str
    state: str
    peer: str
    video: bool
    why: str = ''


@dataclass(frozen=True)
class Fire:
    event: str
    data: dict


@dataclass
class Call:
    key: str
    caller: str
    callee: str
    video: bool
    at: float
    answered: float = None
    held: bool = False

    def other(self, node):
        return self.callee if node == self.caller else self.caller

    def has(self, node):
        return node in (self.caller, self.callee)


class Calls:
    def __init__(self, new_key=lambda: secrets.token_hex(4)):
        self.new_key = new_key
        self.calls = {}    # key -> Call
        self.missed = {}   # node -> {'from', 'at', 'video'}, until its list is opened

    def of(self, node):
        return next((call for call in self.calls.values() if call.has(node)), None)

    def _event(self, event, call, **more):
        # `key` is the call's own: the same in every event of one call, so an automation can tell two calls apart.
        return Fire(event, {'from': call.caller, 'to': call.callee, 'video': call.video, 'key': call.key, **more})

    def dial(self, caller, callee, video, now, reachable=True, quiet=False):
        """`caller` calls `callee`. `reachable`: the app can send to it now; `quiet`: its Do not disturb. Busy, offline and
        quiet are said to the caller at once and leave no call behind."""
        if self.of(caller) is not None or caller == callee:
            return []
        key = self.new_key()
        refuse = GONE if not reachable else QUIET if quiet else BUSY if self.of(callee) is not None else None
        if refuse:
            return [Say(caller, key, END, callee, video, refuse)]
        call = self.calls[key] = Call(key, caller, callee, video, now)
        return [Say(caller, key, OUT, callee, video), Say(callee, key, RING, caller, video), self._event(STARTED, call)]

    def _close(self, call, why_caller, why_callee, now):
        del self.calls[call.key]
        out = [Say(call.caller, call.key, END, call.callee, call.video, why_caller),
               Say(call.callee, call.key, END, call.caller, call.video, why_callee)]
        if call.answered is not None:
            out.append(self._event(ENDED, call, seconds=round(now - call.answered)))
        return out

    def answer(self, key, node, now):
        call = self.calls.get(key)
        if call is None or call.callee != node or call.answered is not None:
            return []
        call.answered = now
        return [Say(call.caller, key, LIVE, call.callee, call.video), Say(call.callee, key, LIVE, call.caller, call.video),
                self._event(ANSWERED, call)]

    def gone_for(self, key, node):
        """A screen spoke of a call that is not there (this app started again in the middle of it, or the call ended a
        moment before): the screen is told it ended, so it never stays in a call nobody holds."""
        return [Say(node, key, END, '', False, GONE)]

    def decline(self, key, node, now):
        call = self.calls.get(key)
        if call is None:
            return self.gone_for(key, node)
        if call.callee != node or call.answered is not None:
            return []
        return self._close(call, DECLINED, DECLINED, now)

    def hang_up(self, key, node, now):
        """`end`, or `cancel` by the caller while it rings: the other end is told."""
        call = self.calls.get(key)
        if call is None:
            return self.gone_for(key, node)
        if not call.has(node):
            return []
        if call.answered is None:
            # Called off before an answer: for the one who was rung, a missed call.
            self._note_missed(call, now)
            return self._close(call, HUNG_UP, MISSED, now)
        return self._close(call, HUNG_UP, HUNG_UP, now)

    def gone(self, node, now):
        """A screen went away (offline, restarted): its call ends for the other end."""
        call = self.of(node)
        if call is None:
            return []
        if call.answered is None and node == call.caller:
            self._note_missed(call, now)
        return self._close(call, GONE, GONE, now)

    def _note_missed(self, call, now):
        self.missed[call.callee] = {'from': call.caller, 'at': now, 'video': call.video}

    def tick(self, now):
        """What the clock ends: a ring nobody answered."""
        out = []
        for call in list(self.calls.values()):
            if call.answered is None and now - call.at >= RING_SECONDS:
                self._note_missed(call, now)
                out += self._close(call, NO_ANSWER, MISSED, now)
                out.append(self._event(MISSED_EVENT, call))
        return out

    def door(self, node, ringing):
        """A doorbell rings at `node` (True) or its view closed (False): the door goes first, the call waits, muted."""
        call = self.of(node)
        if call is None or call.answered is None or call.held == ringing:
            return []
        call.held = ringing
        state = HELD if ringing else LIVE
        return [Say(call.caller, call.key, state, call.callee, call.video), Say(call.callee, call.key, state, call.caller, call.video)]

    def forget(self):
        """The app starts: whatever a screen thinks it is in is over. For every call still known (normally none)."""
        out = [each for call in list(self.calls.values()) for each in (Say(call.caller, call.key, END, call.callee, call.video, GONE),
                                                                       Say(call.callee, call.key, END, call.caller, call.video, GONE))]
        self.calls.clear()
        return out

    def contacts(self, node, screens):
        """The list on `node`: `screens` is {node: {'name', 'icon', 'hears', 'speaks', 'shows', 'films', 'online', 'quiet'}}. A row
        a screen other than `node`: `a` it can be called with sound, `v` with video (both ends need a camera to send and a
        glass that shows), `s` its state, `m` the moment it called and was missed here. Opening the list clears the marks
        the Manager shows on the tile (`seen`)."""
        mine = screens.get(node) or {}
        rows = []
        for other, facts in screens.items():
            if other == node:
                continue
            state = OFFLINE if not facts.get('online') else DND if facts.get('quiet') else IN_CALL if self.of(other) else FREE
            sound = state == FREE and bool(mine.get('hears') and mine.get('speaks') and facts.get('hears') and facts.get('speaks'))
            video = sound and bool(mine.get('films') and mine.get('shows') and facts.get('films') and facts.get('shows'))
            row = {'id': other, 'n': facts.get('name') or other, 'i': facts.get('icon') or '', 'a': int(sound), 'v': int(video), 's': state}
            missed = self.missed.get(node)
            if missed and missed['from'] == other:
                row['m'] = missed['at']
            rows.append(row)
        # The ones that can be called first: in a house of thirty screens those are what the list is for.
        order = {FREE: 0, IN_CALL: 1, DND: 2, OFFLINE: 3}
        return sorted(rows, key=lambda row: (order[row['s']], row['n'].casefold()))

    def seen(self, node):
        return self.missed.pop(node, None) is not None


# Voice switching (docs/CALLS.md): while one side speaks the other side's microphone goes down by about 18 dB, so a voice does
# not come back from the other loudspeaker; a screen whose echo canceller is at work needs none of it. Both are a call's own
# choices, the same on both screens: a small key on either glass turns voice switching, or echo cancelling, off and on for the
# call, and the screen's switch Call voice switching says what its calls start with.
HOLD_SECONDS, DUCK, FLOOR = 0.25, 0.125, 380


def rms(samples):
    return math.sqrt(sum(v * v for v in samples) / len(samples)) if samples else 0.0


def scaled(data, gain, end=None):
    """16-bit samples at `gain`, moving to `end` over the part (no clicks where the level changes)."""
    samples = array.array('h')
    samples.frombytes(bytes(data))
    end = gain if end is None else end
    n = max(1, len(samples))
    return array.array('h', (int(v * (gain + (end - gain) * i / n)) for i, v in enumerate(samples))).tobytes()


# Do not disturb (docs/CALLS.md): the screen's own switch, kept by the screen and read from Home Assistant. On, a call to it
# is refused at once and the caller reads that it does not want to be disturbed; the doorbell is not a call and still rings.
QUIET_SWITCH = ('switch', 'Do not disturb')
# Direct calls (docs/CALLS.md, "Screen to screen"): the screen's own switch as well, off as it comes while the route is
# new. A call goes direct only between two screens that both say `call_direct` and both have it on.
DIRECT_SWITCH = ('switch', 'Direct calls')


def switch_on(items, states, switch):
    """Whether a screen's own switch (domain, name) is on: `items` are the registry entries of its device, `states` Home
    Assistant's states. A screen without the switch (firmware from before it, a board without the part) has it off."""
    domain, name = switch
    for item in items or []:
        entity = item.get('entity_id') or ''
        if item.get('platform') == 'esphome' and item.get('original_name') == name and entity.split('.', 1)[0] == domain:
            return ((states or {}).get(entity) or {}).get('state') == 'on'
    return False


def quiet(items, states):
    """Whether a screen's Do not disturb is on. A screen without the switch (no speaker, or firmware from before it) is
    never quiet."""
    return switch_on(items, states, QUIET_SWITCH)


class VoiceSwitch:
    """One call's two microphones. `feed(node, part, now)` is the part as it should go on. The one who speaks first holds the
    line until HOLD_SECONDS after their last word. `duck`: voice switching is on for the call; `aec`: echo cancelling is on for
    the call, on the sides that have a canceller (`cancels`), which are not turned down while it is.

    A call starts with echo cancelling on, and with voice switching on only where it is needed: when a side has no
    canceller. Two screens that both cancel echo start without it, and either key brings it."""

    def __init__(self, a, b, cancels=()):
        self.nodes, self.cancels = (a, b), set(cancels)
        self.duck, self.aec = not self.cancels.issuperset(self.nodes), True
        self.last, self.noise, self.gain = {a: 0.0, b: 0.0}, {a: FLOOR, b: FLOOR}, {a: 1.0, b: 1.0}
        self.talker = None

    def switching(self, node):
        """Whether `node`'s microphone goes down while the other side speaks."""
        return self.duck and node in self.nodes and not (self.aec and node in self.cancels)

    def turn(self, what, on):
        """A person turned voice switching ('switch') or echo cancelling ('echo') on or off, for the call."""
        if what == 'switch':
            self.duck = bool(on)
        elif what == 'echo':
            self.aec = bool(on)
        for node in self.nodes:
            if not self.switching(node):
                self.gain[node] = 1.0

    def keys(self):
        """What both screens show: `vs` voice switching, and `ec` echo cancelling where a side of the call has a canceller."""
        return {'vs': int(self.duck), **({'ec': int(self.aec)} if self.cancels else {})}

    def feed(self, node, data, now):
        samples = array.array('h')
        samples.frombytes(bytes(data))
        level = rms(samples)
        # The room's own level follows quickly down and slowly up, so a voice never raises it.
        self.noise[node] = min(level, self.noise[node] * 1.01) if level < self.noise[node] else self.noise[node] * 1.003
        loud = level > max(FLOOR, self.noise[node] * 3)
        if loud:
            self.last[node] = now
        if self.talker is None or now - self.last[self.talker] > HOLD_SECONDS:
            self.talker = node if loud else None
        held = self.talker is not None and self.talker != node and self.switching(node)
        target = DUCK if held else 1.0
        out = scaled(data, self.gain[node], target) if self.gain[node] != 1.0 or target != 1.0 else bytes(data)
        self.gain[node] = target
        return out


def unsupported(tiles, features):
    """Whether a layout holds the Call tile for a screen whose hello does not name the feature `call`: it is not sent then, and the
    editor says which firmware it needs. A screen that said nothing yet (`features` None) is not judged here."""
    return features is not None and FEATURE not in features and any(tile.get('entity') == TILE for tile in tiles)


def contacts_messages(rows):
    """The op `contacts` in parts: a message holds at most ROWS_A_MESSAGE rows, so thirty screens fit under the 4096 bytes of
    one message however long their names are (each cut to NAME_MOST)."""
    short = [{**row, 'n': row['n'][:NAME_MOST]} for row in rows]
    parts = [short[i:i + ROWS_A_MESSAGE] for i in range(0, len(short), ROWS_A_MESSAGE)] or [[]]
    return [{'v': 1, 'op': 'contacts', 'r': part, 'p': i, 'more': int(i < len(parts) - 1)} for i, part in enumerate(parts)]


# Direct media (docs/CALLS.md, "Screen to screen"): a screen that says `call_direct` in its hello serves its own camera
# and microphone to the other screen of a call, on DIRECT_PORT, under a token ESP Screens makes for that call and that
# direction. ESP Screens then only signals; its own route stays for every call that cannot go direct.
DIRECT_FEATURE = 'call_direct'
DIRECT_PORT = 8555      # call_serve.h PORT; tests/test_calls.py holds the two together


def direct_tokens(a, b, new=lambda: secrets.token_urlsafe(16)):
    """{node: the token that screen serves under} for one call."""
    return {a: new(), b: new()}


def direct_link(ip, token):
    """Where a screen fetches the other screen's stream of a direct call."""
    return f'http://{ip}:{DIRECT_PORT}/call/{token}.mjpeg'


SET = 'set'     # the op `call` that only brings the call's choices (`vs`, `ec`) to a screen that is in it


def choices_message(key, keys):
    """The op `call` with the state `set`: the call's voice switching and echo cancelling, to both screens when one changed."""
    return {'v': 1, 'op': 'call', 'k': key, 's': SET, **keys}


def message(say, name='', icon='', link='', peer_camera=True):
    """The op `call` for a `Say` (docs/CALLS.md): additive fields, a screen without the feature never gets it."""
    out = {'v': 1, 'op': 'call', 'k': say.key, 's': say.state, 'n': name[:60], 'vd': int(say.video)}
    if icon:
        out['i'] = icon
    if say.state == LIVE and link:
        out['l'] = link
    if say.state == LIVE:
        out['pc'] = int(peer_camera)
    if say.state == END:
        out['w'] = say.why
    return out
