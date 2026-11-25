"""A board's own steps (docs/BOARD_STEPS.md): what there is to do with a board beyond its firmware, once, which New
screen offers after the screen works and the screen's page until it is done.

Most boards need nothing but their firmware. Some need one more thing: a second chip that takes a firmware of its own,
a part someone sets by hand. A board's entry in boards.yaml lists them under `steps`, in order, each with an id, a kind
and what its kind needs:

    steps:
      - id: buzzer
        kind: chip_firmware
        chip: indicator-rp2040

A kind is the one piece of code a step has. Here it is a row of KINDS: its check, what the editor gets to do the step
with, whether the screen itself can see that the step is done, and when what the screen found is older than what this
app has. In the editor it is a component that does the step (web/src/components/steps/). A step's words are the
translations' (`editor.steps.<id>`). So a new step of a kind that exists is an entry in boards.yaml and its words; a
new kind is a row here and a component there.

Whether a step is done comes from the screen where it can see it (its hello's `steps`: {id: what it found}, as the
firmware of a chip that answers), and from the person where it cannot ("done", kept here). "Later" is kept too: New
screen goes on and the card above the screen stays away, and the step waits in the screen's settings.

What it does not know: the boards (the caller hands it a board's steps from boards.json), the screens, or how a step
is done. tests/test_board_steps.py proves it.
"""
import json
import re
import threading
from pathlib import Path

import atomic

VERSION = 1
CHIPS = Path(__file__).resolve().parent / 'chips'
# A step is open until it is done; `later` is a person's "not now", `update` a step that is done with something older
# than this app has.
OPEN, LATER, DONE, UPDATE = 'open', 'later', 'done', 'update'
ANSWERS = (LATER, DONE, '')
ID = re.compile(r'[a-z][a-z0-9_]{0,31}')
NAME = re.compile(r'[a-z0-9][a-z0-9-]{0,39}')


def version_tuple(text):
    """'1.2.3' as (1, 2, 3); what is no such version is older than every one."""
    parts = str(text or '').split('.')
    return tuple(int(part) for part in parts) if parts and all(part.isdigit() for part in parts) else ()


def chip(name):
    """The firmware this app has for a board's second chip (chips/<name>.json beside its file, written by
    tools/build_chips.py), or None: its version, its file and size, the USB ids of the chip's port and the name of the
    drive it shows as when it takes a new firmware."""
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return None
    try:
        found = json.loads((CHIPS / f'{name}.json').read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(found, dict) or found.get('name') != name or not (CHIPS / str(found.get('file'))).is_file():
        return None
    return found


def chip_file(name):
    """(the bytes of the chip's firmware, the name a download of it gets), or None."""
    found = chip(name)
    if found is None:
        return None
    return (CHIPS / found['file']).read_bytes(), f"tessera-{name}-{found['version']}.uf2"


def _chip_firmware(step):
    """`chip_firmware`: Tessera's firmware for a second chip of the board, written through the chip's own USB port. The
    step names the chip; the editor gets where the file is, how large, the port's USB ids and the drive's name."""
    found = chip(step.get('chip'))
    if found is None:
        raise ValueError(f"the app has no firmware for the chip {step.get('chip')!r} (screen_manager/app/chips)")
    return {'chip': found['name'], 'version': found['version'], 'size': found['size'], 'file': f"api/chips/{found['name']}/firmware",
            'download': f"tessera-{found['name']}-{found['version']}.uf2", 'usb': found['usb'], 'drive': found['drive']}


# kind: `view` checks a step and says what the editor gets for it (ValueError: what is wrong); `seen` whether a screen
# reports the step in its hello, so no person's word is taken for it; `stale` whether what a screen found is older than
# what `view` offers.
KINDS = {
    'chip_firmware': {'view': _chip_firmware, 'seen': True,
                      'stale': lambda offered, found: version_tuple(found) < version_tuple(offered['version'])},
}


def checked(steps):
    """A board's `steps` as boards.yaml has them, checked: a list of {id, kind, ...}, every id once, every kind one of
    KINDS and content with its step. ValueError says what is wrong. Returns them as they go into boards.json."""
    if steps is None:
        return []
    if not isinstance(steps, list):
        raise ValueError('steps is a list')
    out, seen = [], set()
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get('id'), str) or not ID.fullmatch(step['id']):
            raise ValueError('a step has an id of small letters, digits and _')
        if step['id'] in seen:
            raise ValueError(f"the step {step['id']} is listed twice")
        seen.add(step['id'])
        kind = KINDS.get(step.get('kind'))
        if kind is None:
            raise ValueError(f"the step {step['id']} has a kind that is one of {', '.join(KINDS)}")
        kind['view'](step)
        out.append({str(key): value for key, value in step.items()})
    return out


def view(steps, seen, answers):
    """What the editor shows of a board's steps for one screen: each with its state and what its kind gives the editor.
    `seen` is what the screen's hello says of them ({id: what it found}), `answers` what a person said ({id: answer}).
    `seen` None is a screen that says nothing of steps (it is away since this app started, or its firmware is from
    before its board had steps): a step only the screen can call done is then left out, since nobody could tell when it
    is. So is a step whose kind this app cannot serve (its file is missing): there is nothing to offer."""
    out = []
    for step in steps or []:
        kind = KINDS.get(step.get('kind'))
        if kind is None or (seen is None and kind['seen']):
            continue
        try:
            offered = kind['view'](step)
        except ValueError:
            continue
        found, said = (seen or {}).get(step['id']), (answers or {}).get(step['id'])
        if found is not None and kind['seen']:
            state = UPDATE if kind['stale'](offered, found) else DONE
        elif said == DONE and not kind['seen']:
            state = DONE
        else:
            state = LATER if said == LATER else OPEN
        out.append({'id': step['id'], 'kind': step['kind'], 'state': state, 'found': found or '', **offered})
    return out


class BoardSteps:
    """What people said of their screens' steps, kept over a restart: {screen: {step: 'later' | 'done'}}."""

    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'board_steps.json'
        self.lock = threading.RLock()
        data = atomic.read_json(self.path, VERSION) or {}
        kept = data.get('screens') if isinstance(data.get('screens'), dict) else {}
        self.answers = {str(screen): {step: said for step, said in mine.items() if isinstance(step, str) and said in (LATER, DONE)}
                        for screen, mine in kept.items() if isinstance(mine, dict)}

    def save(self):
        with self.lock:
            atomic.write_json(self.path, {'version': VERSION, 'screens': {screen: mine for screen, mine in self.answers.items() if mine}},
                              0o644, separators=(',', ':'))

    def of(self, screen):
        return dict(self.answers.get(str(screen), {}))

    def answer(self, steps, screen, step, said):
        """A person's word for a step of this screen's board: 'later', 'done' where the screen cannot see it itself, or
        '' to take the word back. ValueError: 'unknown' (no such step or word), 'seen' (the screen says when it is done)."""
        found = next((one for one in steps or [] if one.get('id') == step), None)
        if found is None or said not in ANSWERS or found.get('kind') not in KINDS:
            raise ValueError('unknown')
        if said == DONE and KINDS[found['kind']]['seen']:
            raise ValueError('seen')
        with self.lock:
            mine = self.answers.setdefault(str(screen), {})
            if said:
                mine[step] = said
            else:
                mine.pop(step, None)
            self.save()

    def forget_screen(self, screen):
        with self.lock:
            if self.answers.pop(str(screen), None):
                self.save()
