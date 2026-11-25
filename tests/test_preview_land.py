"""The job that rebuilds the editor's firmware preview lands it on a branch that keeps moving (web/wasm/land.py,
.github/workflows/preview.yml, docs/RELEASING.md "Firmware preview").

Two repositories on this machine stand in for GitHub and the job's runner: `origin.git` is the branch everyone pushes
to, `runner` is the job's shallow clone, and `dev` is everyone else. The two builds are cheap stand-ins with the real
ones' shape (STUB below): the WebAssembly is a function of the firmware sources alone, the editor's bundle is a
function of the WebAssembly, web/src and what the commits say of the preview's age, and its file is named after its
content, so two builds of it cannot be merged. Every test runs web/wasm/land.py as the job does and reads the result
from origin.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAND = ROOT / 'web/wasm/land.py'
WORKFLOW = ROOT / '.github/workflows/preview.yml'

STUB = r'''
import hashlib, os, pathlib, shutil, subprocess, sys

root = pathlib.Path.cwd()
wasm, generated, static = root / 'web/src/wasm/firmware_preview.wasm', root / 'web/wasm/generated', root / 'screen_manager/app/static'


def fingerprint():
    return hashlib.sha256((root / 'components/card.h').read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(['git', *args], cwd=root, text=True, capture_output=True)


def stale():
    """web/preview-age.ts: the firmware's paths changed in a commit that came after the preview's last one."""
    firmware = git('log', '-1', '--format=%H', '--', 'components', 'packages').stdout.strip()
    preview = git('log', '-1', '--format=%H', '--', 'web/src/wasm/firmware_preview.wasm').stdout.strip()
    return firmware != preview and git('merge-base', '--is-ancestor', preview, firmware).returncode == 0


if sys.argv[1] == 'build':      # web/wasm/build.sh: the firmware sources, and nothing else
    wasm.parent.mkdir(parents=True, exist_ok=True)
    wasm.write_text('wasm of ' + (root / 'components/card.h').read_text())
    shutil.rmtree(generated, ignore_errors=True)
    generated.mkdir(parents=True)
    (generated / 'manifest.h').write_text(fingerprint())
    (generated / f'ui_{fingerprint()[:6]}.h').write_text('ui')      # a file that comes with these sources and goes with them
elif sys.argv[1] == 'check':    # generate_renderer_manifest.py --check, which reads every generated header too
    manifest, headers = generated / 'manifest.h', {path.name for path in generated.glob('*.h')}
    sys.exit(0 if headers == {'manifest.h', f'ui_{fingerprint()[:6]}.h'} and manifest.read_text() == fingerprint() else 1)
elif sys.argv[1] == 'editor':   # npm run build
    # The branch moves while the job builds the editor: the next line of `moves`, when the test left one.
    moves = pathlib.Path(os.environ.get('STUB_MOVES', ''))
    lines = moves.read_text().splitlines() if moves.is_file() else []
    if lines:
        moves.write_text('\n'.join(lines[1:]))
        subprocess.run(lines[0], shell=True, check=True, capture_output=True)
    app = (root / 'web/src/app.ts').read_text()
    if 'does not compile' in app:
        sys.exit(1)
    content = f'{app}|{wasm.read_text()}|stale={stale()}'
    name = 'index-' + hashlib.sha256(content.encode()).hexdigest()[:8] + '.js'
    shutil.rmtree(static / 'assets', ignore_errors=True)
    (static / 'assets').mkdir(parents=True)
    (static / 'assets' / name).write_text(content)
    (static / 'index.html').write_text(f'<script src="./assets/{name}"></script>')
'''


class Bench:
    """origin, the runner's clone with a preview built for the head, and the clone everyone else pushes from."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.stub = self.folder / 'stub.py'
        self.stub.write_text(STUB)
        self.moves = self.folder / 'moves'
        # Git as a runner has it: no configuration of the person who runs the test.
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(('GIT_', 'GITHUB_'))}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
        self.origin, self.dev, self.runner = self.folder / 'origin.git', self.folder / 'dev', self.folder / 'runner'
        self.git(self.folder, 'init', '--quiet', '--bare', '--initial-branch=dev', str(self.origin))
        self.git(self.folder, 'clone', '--quiet', str(self.origin), str(self.dev))
        self.git(self.dev, 'config', 'user.name', 'Someone Else')
        self.git(self.dev, 'config', 'user.email', 'else@example.com')
        # A branch with a current preview, and then a firmware change that makes it stale: what starts the job.
        self.write(self.dev, {'components/card.h': 'card 1', 'packages/board.yaml': 'pin 1', 'web/src/app.ts': 'app 1'})
        self.build(self.dev, 'build', 'editor')
        self.commit(self.dev, 'start')
        self.start = self.push(self.commit(self.dev, 'the firmware draws a card another way', {'components/card.h': 'card 2'}))
        # The job: a shallow clone of the head, as actions/checkout makes it, and the ten-minute build.
        self.git(self.folder, 'clone', '--quiet', '--depth', '1', '--branch', 'dev', self.origin.as_uri(), str(self.runner))
        self.git(self.runner, 'config', 'user.name', 'Preview Job')
        self.git(self.runner, 'config', 'user.email', 'job@example.com')
        self.build(self.runner, 'build')

    def git(self, where, *args, check=True):
        return subprocess.run(['git', *args], cwd=where, env=self.env, text=True, capture_output=True, check=check).stdout.strip()

    def build(self, where, *steps):
        for step in steps:
            subprocess.run([sys.executable, str(self.stub), step], cwd=where, env=self.env, check=True)

    def write(self, where, files):
        for name, text in files.items():
            (where / name).parent.mkdir(parents=True, exist_ok=True)
            (where / name).write_text(text)

    def commit(self, where, message, files=None, *steps):
        """Someone's commit: the files, then the builds they ran (`build`, `editor`), all of it committed."""
        self.write(where, files or {})
        self.build(where, *steps)
        self.git(where, 'add', '-A')
        self.git(where, 'commit', '--quiet', '-m', message)
        return self.git(where, 'rev-parse', 'HEAD')

    def push(self, commit):
        self.git(self.dev, 'push', '--quiet', 'origin', f'{commit}:refs/heads/dev')
        return commit

    def push_during_the_editor_build(self, commit):
        """The branch moves to `commit` after the job took its head and before it pushes."""
        with self.moves.open('a') as moves:
            moves.write(f'git -C "{self.dev}" push --quiet origin {commit}:refs/heads/dev\n')

    def land(self, *options):
        return subprocess.run([sys.executable, str(LAND), 'dev', '--repo', str(self.runner), '--pause', '0',
                               '--check', f'"{sys.executable}" "{self.stub}" check',
                               '--editor', f'"{sys.executable}" "{self.stub}" editor', *options],
                              env={**self.env, 'STUB_MOVES': str(self.moves)}, text=True, capture_output=True)

    def head(self):
        return self.git(self.origin, 'rev-parse', 'dev')

    def show(self, name, commit='dev'):
        return self.git(self.origin, 'show', f'{commit}:{name}')

    def files(self, folder, commit='dev'):
        return self.git(self.origin, 'ls-tree', '-r', '--name-only', commit, '--', folder).split()

    def fresh_build_differs(self):
        """What tools/check.sh's "bundle in Git is fresh" and the stale check say of origin's head, in a full clone."""
        clone = self.folder / f'fresh-{self.head()[:7]}'
        self.git(self.folder, 'clone', '--quiet', str(self.origin), str(clone))
        self.build(clone, 'check', 'editor')
        return self.git(clone, 'status', '--porcelain')


class Landing(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.bench = Bench(folder.name)

    def landed(self, run, on):
        """The preview is one commit of the job on top of `on`, and its bundle is the one that commit builds to."""
        bench = self.bench
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('Landed on dev', run.stdout)
        self.assertEqual(bench.git(bench.origin, 'rev-parse', 'dev^'), on, 'not on top of the head it was built on')
        self.assertEqual(bench.git(bench.origin, 'log', '-1', '--format=%an|%s', 'dev'),
                         f'Preview Job|Firmware preview: rebuilt for {on[:7]}')
        self.assertEqual(bench.show('web/src/wasm/firmware_preview.wasm'), 'wasm of card 2')
        self.assertEqual(len(bench.files('screen_manager/app/static/assets')), 1, 'the bundle of another build is still there')
        self.assertEqual(bench.fresh_build_differs(), '', 'the bundle in Git is not what its commit builds to')

    def quiet(self, run, head, words):
        """The run ends well and the branch is where it was."""
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn(words, run.stdout)
        self.assertEqual(self.bench.head(), head)

    def test_the_head_did_not_move(self):
        self.landed(self.bench.land(), on=self.bench.start)

    def test_the_head_moved_and_the_firmware_sources_did_not(self):
        # What failed in November 2026: a push that rebuilt the editor's bundle while the job built. The two bundles
        # have other file names, which no rebase can merge. It also touches a firmware path the preview is not made
        # from, so the commits alone would call the preview older than the firmware.
        bench = self.bench
        theirs = bench.push(bench.commit(bench.dev, 'a page in the editor, and a pin',
                                         {'web/src/app.ts': 'app 2', 'packages/board.yaml': 'pin 2'}, 'editor'))
        self.landed(bench.land(), on=theirs)
        self.assertIn('app 2|wasm of card 2|stale=False', bench.show(bench.files('screen_manager/app/static/assets')[0]))
        # What the build no longer makes is gone, what it makes now is there.
        self.assertEqual(len(bench.files('web/wasm/generated')), 2)

    def test_the_head_moved_and_the_firmware_sources_too(self):
        bench = self.bench
        theirs = bench.push(bench.commit(bench.dev, 'the card again', {'components/card.h': 'card 3'}))
        self.quiet(bench.land(), theirs, 'this run is out of date')

    def test_the_head_already_carries_a_current_preview(self):
        bench = self.bench
        # Someone changed the firmware again and built the preview by hand, as a release does.
        theirs = bench.push(bench.commit(bench.dev, 'the card again, with its preview', {'components/card.h': 'card 3'},
                                         'build', 'editor'))
        self.quiet(bench.land(), theirs, 'already carries a current preview')

    def test_a_refused_push_lands_on_the_newer_head(self):
        bench = self.bench
        theirs = bench.commit(bench.dev, 'a page in the editor', {'web/src/app.ts': 'app 2'}, 'editor')
        bench.push_during_the_editor_build(theirs)
        run = bench.land()
        self.assertIn('Attempt 1 of 5: the push to dev was refused', run.stdout)
        self.landed(run, on=theirs)

    def test_a_push_refused_by_a_firmware_change_ends_the_run(self):
        bench = self.bench
        theirs = bench.commit(bench.dev, 'the card again', {'components/card.h': 'card 3'})
        bench.push_during_the_editor_build(theirs)
        self.quiet(bench.land(), theirs, 'this run is out of date')

    def test_a_push_refused_every_time_fails(self):
        bench = self.bench
        for number in (2, 3, 4):
            last = bench.commit(bench.dev, f'app {number}', {'web/src/app.ts': f'app {number}'}, 'editor')
            bench.push_during_the_editor_build(last)
        run = bench.land('--attempts', '3')
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn('did not land on dev in 3 attempts', run.stdout)
        self.assertEqual(bench.head(), last)

    def test_a_build_that_is_not_what_its_sources_ask_for_fails(self):
        bench = self.bench
        (bench.runner / 'web/wasm/generated/manifest.h').write_text('another fingerprint')
        run = bench.land()
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(bench.head(), bench.start)

    def test_an_editor_that_does_not_build_fails(self):
        bench = self.bench
        theirs = bench.push(bench.commit(bench.dev, 'half a page', {'web/src/app.ts': 'does not compile'}))
        run = bench.land()
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn('The editor does not build on dev', run.stdout)
        self.assertEqual(bench.head(), theirs)

    def test_a_working_copy_with_other_changes_is_left_alone(self):
        bench = self.bench
        (bench.runner / 'web/src/app.ts').write_text('work nobody committed')
        run = bench.land()
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual((bench.runner / 'web/src/app.ts').read_text(), 'work nobody committed')
        self.assertEqual(bench.head(), bench.start)


class TheJob(unittest.TestCase):
    """What the landing counts on in the workflow, and the one list of the preview's tests."""

    def test_every_preview_test_is_in_the_one_list(self):
        listed = set(re.findall(r'^(?:\w+=\S+ )*node web/wasm/(test_\w+\.mjs)$', (ROOT / 'web/wasm/test.sh').read_text(), re.M))
        # test_protocol.mjs is what the tests import to talk to the preview, not a test.
        tests = {path.name for path in (ROOT / 'web/wasm').glob('test_*.mjs')} - {'test_protocol.mjs'}
        self.assertEqual(listed, tests, 'web/wasm/test.sh is the list of the preview\'s tests: add the test there')

    def test_the_list_is_written_once(self):
        for path in (WORKFLOW, ROOT / 'tools/check.sh'):
            text = path.read_text()
            self.assertIn('sh web/wasm/test.sh', text, path)
            self.assertNotRegex(text, r'node web/wasm/test_', f'{path}: the tests are listed in web/wasm/test.sh')

    def test_a_run_that_builds_is_never_cancelled(self):
        # A build takes longer than the time between two pushes on a busy day: cancelled at each push, none finishes
        # (docs/RELEASING.md, "Firmware preview"). Without cancel-in-progress GitHub lets the running one finish and
        # keeps only the newest one waiting.
        text = WORKFLOW.read_text()
        self.assertRegex(text, r'(?m)^concurrency:\n  group: preview-\$\{\{ github\.ref \}\}\n  cancel-in-progress: false$')
        self.assertIn('python web/wasm/land.py "$GITHUB_REF_NAME"', text)
        self.assertNotRegex(text, r'git (pull|rebase|merge)', 'built files are built again on the head, never merged')


if __name__ == '__main__':
    unittest.main()
