#!/usr/bin/env python3
"""Whether a change leaves boards' firmware as it was (docs/PROFILES.md, "Parts"): the configuration ESPHome works out for
each board (`esphome config checkout/<board>.yaml`), at a git commit and in the working tree, compared without the
substitutions (names, which a part renames; what they do shows where they are used), with each domain's components in
the order of their ids and the code without blank lines. Moving a board's hardware into parts is right when nothing is
left, or only what the change means to change.

    tools/config_diff.py HEAD tab5 wavesharep4                     each board as it builds
    tools/config_diff.py HEAD tab5 --set TAB5_AUDIO_TRANSPORT=i2s  as a screen whose Override YAML says so

The secrets are made up, so no real one is read. ESPHome's clones of external components stay in .esphome/config-diff/
for the next run. The exit status is 1 when a board differs or fails to resolve."""
import argparse
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.esphome' / 'config-diff'
SECRETS = {'wifi_ssid': 'config-diff', 'wifi_password': 'config-diff', 'ota_password': 'config-diff',
           'ap_password': 'config-diff', 'api_encryption_key': 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8='}
SHOWN = 20


def esphome():
    own = ROOT / '.esphome' / 'venv313' / 'bin' / 'esphome'
    return os.environ.get('ESPHOME') or (str(own) if own.exists() else 'esphome')


class _Loader(yaml.SafeLoader):
    """ESPHome's output with its tags (!lambda, !secret, !id) kept as a tag and the text or value under it."""


_Loader.add_multi_constructor('!', lambda loader, tag, node: (tag, loader.construct_scalar(node))
                              if isinstance(node, yaml.ScalarNode) else
                              (tag, loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode)
                               else loader.construct_mapping(node)))


def canonical(value, places):
    """`value` with its lists of components in the order of their ids, its code without blank lines, and the folders
    of one side (`places`, a folder for each name) by their names."""
    if isinstance(value, dict):
        return {str(key): canonical(item, places) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        items = [canonical(item, places) for item in value]
        return items if isinstance(value, list) else tuple(items)
    if isinstance(value, str):
        for name, place in places.items():
            value = value.replace(str(place), name)
        return '\n'.join(line.rstrip() for line in value.splitlines() if line.strip())
    return value


def resolve(tree, side, board, sets):
    """The board's configuration as ESPHome works it out in `tree`, or the end of ESPHome's complaint."""
    folder = WORK / side
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'secrets.yaml').write_text(yaml.safe_dump(SECRETS))
    text = (tree / 'checkout' / f'{board}.yaml').read_text().replace('../', f'{tree}/')
    own = ''.join(f'  {name}: "{value}"\n' for name, value in sets)
    text = re.sub(r'^substitutions:\n', lambda m: m[0] + own, text, count=1, flags=re.M) if own else text
    entry = folder / f'{board}.yaml'
    entry.write_text(text)
    done = subprocess.run([esphome(), 'config', str(entry)], capture_output=True, text=True, cwd=folder)
    if done.returncode:
        return None, '\n'.join((done.stderr + done.stdout).strip().splitlines()[-8:])
    found = yaml.load(done.stdout, Loader=_Loader)
    # The substitutions are names, not firmware: what they do shows where they are used, and a part renames them.
    found.pop('substitutions', None)
    found = canonical(found, {'<entry>': folder, '<tree>': tree})
    # A domain's components in the order of their ids (then of what they are): the order the files list them in is the
    # order of their packages, which a part changes. Lists inside a component, its actions, keep their order.
    for domain, items in found.items():
        if isinstance(items, list) and all(isinstance(item, dict) for item in items):
            items.sort(key=lambda item: (str(item.get('id', '')), repr(item)))
    return found, None


def differences(before, after, path=''):
    if isinstance(before, dict) and isinstance(after, dict):
        found = []
        for key in sorted(set(before) | set(after)):
            found += differences(before.get(key, '<none>'), after.get(key, '<none>'), f'{path}.{key}' if path else key)
        return found
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [d for i, (b, a) in enumerate(zip(before, after)) for d in differences(b, a, f'{path}[{i}]')]
    return [] if before == after else [(path, before, after)]


def shown(value):
    text = repr(value)
    return text if len(text) <= 160 else text[:157] + '...'


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('base', help='the git commit to compare with, HEAD for the last one')
    parser.add_argument('boards', nargs='+', help='checkout/<board>.yaml names')
    parser.add_argument('--set', action='append', default=[], metavar='NAME=VALUE',
                        help="a substitution a screen's Override YAML sets, on both sides")
    args = parser.parse_args()
    sets = [item.split('=', 1) for item in args.set]
    WORK.mkdir(parents=True, exist_ok=True)
    failed = False
    with tempfile.TemporaryDirectory(dir=WORK) as tmp:
        base = Path(tmp) / 'tree'
        base.mkdir()
        archive = subprocess.run(['git', 'archive', args.base], cwd=ROOT, capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(base, filter='data')
        for board in args.boards:
            before, why_before = resolve(base, 'base', board, sets)
            after, why_after = resolve(ROOT, 'work', board, sets)
            if before is None or after is None:
                failed = True
                print(f'{board}: does not resolve {"at " + args.base if before is None else "in the working tree"}:\n'
                      f'{why_before or why_after}')
                continue
            found = differences(before, after)
            failed |= bool(found)
            print(f'{board}: the same' if not found else f'{board}: {len(found)} differences')
            for path, was, now in found[:SHOWN]:
                print(f'  {path}\n    was {shown(was)}\n    now {shown(now)}')
            if len(found) > SHOWN:
                print(f'  ... and {len(found) - SHOWN} more')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
