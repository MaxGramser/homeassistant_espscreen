#!/usr/bin/env python3
"""Land a rebuilt firmware preview on a branch that keeps moving (.github/workflows/preview.yml, docs/RELEASING.md).

    python web/wasm/land.py dev

Runs after web/wasm/build.sh and web/wasm/test.sh, in the clone the preview was built in. It takes that clone to the
head of the branch, so it refuses a working copy with other changes: it is made for the job's clone.

The rule: a built file is committed on the head it was built from, and is never merged or rebased.

- The WebAssembly (PREVIEW) is made from the firmware sources alone, and generate_renderer_manifest.py --check is the
  one place that knows which those are. So a preview built for one commit is good for every later head that check
  passes on, and for no other.
- The editor's bundle (BUNDLE) is made from the WebAssembly and web/src, and its files are named after their
  content. Two builds of it never merge, so it is built again on the head it is committed to, every time.

What happens, for the head of the branch at the moment of landing:

- it already carries a current preview (someone built one by hand): nothing to land, the run ends well;
- the built preview fits it (the head is the one the build started from, or the firmware sources did not change since):
  the editor is built on that head, both are committed as one commit and pushed;
- the built preview does not fit it (the firmware sources changed while it was built): this run is out of date and
  ends well, without a commit. The push that changed them started a run of its own;
- the push is refused because the branch moved again: the same from the top, on the new head, ATTEMPTS times at most,
  and then the run fails.

It does not know how the preview or the editor is built or tested: those are the two commands below, which
tests/test_preview_land.py replaces with cheap ones to walk every case above between two repositories on one machine.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
# What web/wasm/build.sh writes, and what the editor's build writes.
PREVIEW = ('web/src/wasm', 'web/wasm/generated')
BUNDLE = ('screen_manager/app/static',)
# Whether the preview in the working copy is the one its firmware sources build to.
CHECK = f'"{sys.executable}" web/wasm/generate_renderer_manifest.py --check'
# The editor, from a clean install: the head it is built on may bring other packages than the one before.
EDITOR = 'cd web && npm ci --no-audit --no-fund && npm run build'
ATTEMPTS = 5


def say(text, kind=None):
    """A line in the log; with a kind (notice, error) also on the run's page on GitHub."""
    print(f'::{kind}::{text}' if kind and os.environ.get('GITHUB_ACTIONS') else text, flush=True)


class Clone:
    def __init__(self, path):
        self.path = Path(path)

    def git(self, *args, check=True):
        return subprocess.run(['git', *args], cwd=self.path, text=True, capture_output=True, check=check)

    def out(self, *args):
        return self.git(*args).stdout.strip()

    def ok(self, *args):
        return self.git(*args, check=False).returncode == 0

    def run(self, command):
        """One of the two commands, with its output in the log."""
        say(f'$ {command}')
        return subprocess.run(command, shell=True, cwd=self.path).returncode == 0


def land(clone, branch, remote='origin', check=CHECK, editor=EDITOR, attempts=ATTEMPTS, pause=5.0):
    """True when the branch has what it needs from this run (see the top of the file), False when the run failed."""
    others = clone.out('status', '--porcelain', '--untracked-files=no', '--', '.', *(f':!{path}' for path in PREVIEW + BUNDLE))
    if others:
        say(f'This takes the working copy to the head of {branch} and it has other changes:\n{others}', 'error')
        return False
    built_for = clone.out('rev-parse', 'HEAD')
    # The built preview, kept as a tree in this clone: every attempt lays it over the head it lands on.
    clone.git('add', '-A', '--', *PREVIEW)
    built = clone.out('write-tree')
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            time.sleep(pause)
        if not clone.ok('fetch', '--quiet', remote, branch):
            say(f'Attempt {attempt} of {attempts}: {branch} could not be fetched from {remote}.')
            continue
        head = clone.out('rev-parse', 'FETCH_HEAD')
        name = f'{branch} at {head[:7]}'
        # The head as it is in Git, without the build (staged above) or the commit of an attempt before this one;
        # detached, so no branch of this clone moves.
        clone.git('checkout', '--quiet', '--force', '--detach', head)
        if head != built_for and clone.run(check):
            say(f'{name} already carries a current preview: nothing to land.', 'notice')
            return True
        clone.git('restore', f'--source={built}', '--staged', '--worktree', '--', *PREVIEW)
        if not clone.run(check):
            if head == built_for:
                say(f'The preview built for {built_for[:7]} is not the one its own sources ask for.', 'error')
                return False
            say(f'The firmware sources changed between {built_for[:7]}, which this preview was built for, and {name}: '
                'this run is out of date and lands nothing. The push that changed them started a run of its own.', 'notice')
            return True
        if clone.ok('diff', '--cached', '--quiet', '--', *PREVIEW):
            say(f'The build equals the preview of {name}: nothing to land.', 'notice')
            return True
        # The preview is committed before the editor is built: the editor's build reads from the commits whether the
        # preview is older than the firmware (web/preview-age.ts), and here it is not.
        clone.git('commit', '--quiet', '-m', f'Firmware preview: rebuilt for {head[:7]}')
        if not clone.run(editor):
            say(f'The editor does not build on {name}.', 'error')
            return False
        clone.git('add', '-A', '--', *BUNDLE)
        clone.git('commit', '--quiet', '--amend', '--no-edit')
        pushed = clone.git('push', '--quiet', remote, f'HEAD:refs/heads/{branch}', check=False)
        if pushed.returncode == 0:
            say(f'Landed on {name} as {clone.out("rev-parse", "--short=7", "HEAD")}.', 'notice')
            return True
        say(f'Attempt {attempt} of {attempts}: the push to {branch} was refused.\n{pushed.stderr.strip()}')
    say(f'The preview did not land on {branch} in {attempts} attempts.', 'error')
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('branch', help='the branch the preview was built for and lands on')
    parser.add_argument('--remote', default='origin')
    parser.add_argument('--repo', default=ROOT, help='the clone the preview was built in, this one by default')
    parser.add_argument('--check', default=CHECK, help='the command that says whether the preview fits its sources')
    parser.add_argument('--editor', default=EDITOR, help='the command that builds the editor')
    parser.add_argument('--attempts', type=int, default=ATTEMPTS)
    parser.add_argument('--pause', type=float, default=5.0, help='seconds between two attempts')
    args = parser.parse_args()
    try:
        landed = land(Clone(args.repo), args.branch, args.remote, args.check, args.editor, args.attempts, args.pause)
    except subprocess.CalledProcessError as error:
        say(f'{" ".join(map(str, error.cmd))} failed:\n{error.stderr}', 'error')
        landed = False
    sys.exit(0 if landed else 1)


if __name__ == '__main__':
    main()
