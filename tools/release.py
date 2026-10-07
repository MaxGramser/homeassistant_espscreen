"""A release (docs/RELEASING.md): what is on dev goes to main in one go, when the maintainer asks for it.

Work goes to dev and reaches nobody; main is what every Home Assistant installs and every screen builds. A release
names the app version and the firmware numbers once, for everything since the last one, tests that exact commit as an
upgrade from main, and then moves main to it.

    tools/release.py status                what the next release holds: the commits since main, the notes under
                                           "## Unreleased" in the CHANGELOG, the firmware it is, and whether main has a
                                           hotfix dev lacks
    tools/release.py prepare [--version X.Y.Z]
                                           the release's edits in the working tree, for you to commit: the app version
                                           in screen_manager/config.yaml, the CHANGELOG heading in place of
                                           "## Unreleased", the firmware numbers tools/affected_boards.py works out
                                           (packages/core.yaml and core.FIRMWARE_VERSION, or the board files), and
                                           screen_manager/app/boards.json
    tools/release.py ci                    starts CI by hand on the pushed release commit: tools/check.sh and every
                                           board on both ESPHome versions (about an hour), the heavy checks that run
                                           once a release and never on a push to dev
    tools/release.py candidate             pushes the branch release-candidate: HEAD with the published packages
                                           pointed at that branch, so a test Home Assistant builds the release through
                                           its own Update button before main has it (docs/TESTING.md, "6. The upgrade")
    tools/release.py candidate --delete    removes that branch again
    tools/release.py publish --notes FILE [--yes]
                                           main fast-forwards to HEAD, the tag screens-vX.Y.Z, the GitHub release with
                                           FILE as its notes, and the candidate branch goes. Only for a commit that is
                                           pushed, green in CI and the one the candidate was made of; without --yes it
                                           says what it would do and does nothing

Any refusal exits 1 with the reason. Standard library and PyYAML only; publish also needs gh.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import affected_boards  # noqa: E402
import firmware_count  # noqa: E402
import profiles  # noqa: E402

ROOT = profiles.ROOT
CHANGELOG = 'screen_manager/CHANGELOG.md'
CONFIG = 'screen_manager/config.yaml'
CORE_PY = 'screen_manager/app/core.py'
WORK = 'dev'
RELEASES = 'main'
CANDIDATE = 'release-candidate'
REPOSITORY = 'MaxGramser/homeassistant_espscreen'
# The CI jobs a release waits for (.github/workflows/ci.yml).
CI_JOBS = ('checks', 'firmware (add-on)', 'firmware (min_version)')

UNRELEASED = re.compile(r'^## Unreleased[ \t]*$', re.M)
SECTION = re.compile(r'^#{1,2} ', re.M)
FIRST_HEADING = re.compile(r'^## (.+)$', re.M)
APP_VERSION = re.compile(r'^(version:[ \t]*)["\']?(\d+\.\d+\.\d+)["\']?[ \t]*$', re.M)
CORE_NUMBER = re.compile(r'^(  SCREEN_FIRMWARE_VERSION:[ \t]*)"[^"\n]*"[ \t]*$', re.M)
CORE_PY_NUMBER = re.compile(r"^(FIRMWARE_VERSION = )'[^'\n]*'[ \t]*$", re.M)
BOARD_ID = re.compile(r'^  BOARD_ID:.*\n', re.M)
# What a published entry (packages/<board>.yaml, packages/bridge.yaml) fetches from main: its components and fonts.
REF_MAIN = re.compile(r'^(\s+ref:[ \t]*)main[ \t]*$', re.M)
FONTS_MAIN = re.compile(r'(raw\.githubusercontent\.com/' + re.escape(REPOSITORY) + r'/)main/')
# The branch a published entry fetches its components and fonts from (packages/<key>.yaml, GITHUB_REF): main unless the
# screen's own YAML says otherwise, as the dev channel's does.
GITHUB_REF_MAIN = re.compile(r'^(\s+GITHUB_REF:[ \t]*)"main"[ \t]*$', re.M)


class Refusal(Exception):
    pass


# ----- the text of the files a release changes ---------------------------------------------------------------------

def unreleased(text):
    """The notes under "## Unreleased", stripped, or None when the CHANGELOG has no such heading."""
    match = UNRELEASED.search(text)
    if not match:
        return None
    end = SECTION.search(text, match.end())
    return text[match.end():end.start() if end else len(text)].strip()


def heading(app, release):
    """The CHANGELOG heading of a release, in the form tests/test_release_lint.py and What's new read."""
    boards = f' for {", ".join(release["boards"])}' if release['kind'] == 'boards' else ''
    return f'## {app} (firmware {release["firmware"]}{boards})'


def named(text, line):
    """The CHANGELOG with "## Unreleased" turned into the release's heading `line`."""
    notes = unreleased(text)
    if notes is None:
        raise Refusal('The CHANGELOG has no "## Unreleased" section: nothing says what this release brings. Write the '
                      'notes under "## Unreleased" at the top of screen_manager/CHANGELOG.md first.')
    if not notes:
        raise Refusal('"## Unreleased" in the CHANGELOG has no notes yet.')
    if UNRELEASED.search(text, UNRELEASED.search(text).end()):
        raise Refusal('The CHANGELOG has "## Unreleased" twice: merge them into one section first.')
    return UNRELEASED.sub(line, text, count=1)


def version_of(config):
    match = APP_VERSION.search(config)
    if not match:
        raise Refusal(f'{CONFIG} has no version: "X.Y.Z" line')
    return match.group(2)


def next_version(version):
    x, y, z = firmware_count.parse(version)
    return f'{x}.{y}.{z + 1}'


def with_version(config, version):
    return APP_VERSION.sub(lambda m: f'{m.group(1)}"{version}"', config, count=1)


def one(pattern, text, replacement, where):
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise Refusal(f'{where}: the line to change was not found')
    return text


def with_core_number(core_yaml, number):
    return one(CORE_NUMBER, core_yaml, lambda m: f'{m.group(1)}"{number}"', 'packages/core.yaml SCREEN_FIRMWARE_VERSION')


def with_core_py_number(core_py, number):
    return one(CORE_PY_NUMBER, core_py, lambda m: f"{m.group(1)}'{number}'", f'{CORE_PY} FIRMWARE_VERSION')


def with_board_number(board_yaml, number, app):
    """A board file that builds `number` of its own (docs/BOARD_RELEASES.md): its line changed, or added under
    BOARD_ID with the comment such a line carries."""
    if CORE_NUMBER.search(board_yaml):
        return with_core_number(board_yaml, number)
    found = BOARD_ID.search(board_yaml)
    if not found:
        raise Refusal('a board file without BOARD_ID: its own number has no place')
    added = (f"  # This board's own firmware revision (docs/BOARD_RELEASES.md), app {app} in the CHANGELOG.\n"
             '  # The next shared release takes this line out again.\n'
             f'  SCREEN_FIRMWARE_VERSION: "{number}"\n')
    return board_yaml[:found.end()] + added + board_yaml[found.end():]


def without_board_number(board_yaml):
    """A board file without its own SCREEN_FIRMWARE_VERSION and the comment lines right above it: a shared release
    overtakes the board's revision."""
    lines = board_yaml.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if CORE_NUMBER.fullmatch(line.rstrip('\n')):
            start = index
            while start > 0 and lines[start - 1].lstrip().startswith('#') and lines[start - 1].startswith('  '):
                start -= 1
            return ''.join(lines[:start] + lines[index + 1:])
    return board_yaml


def pointed_at(entry, branch):
    """(a published entry that fetches its components and fonts from `branch` instead of main, how many places
    changed)."""
    entry, default = GITHUB_REF_MAIN.subn(lambda m: m.group(1) + f'"{branch}"', entry)
    entry, refs = REF_MAIN.subn(lambda m: m.group(1) + branch, entry)
    entry, fonts = FONTS_MAIN.subn(lambda m: m.group(1) + branch + '/', entry)
    return entry, default + refs + fonts


def section(changelog, version):
    """The heading line and the notes of `version` in the CHANGELOG, or None."""
    match = re.search(rf'^## {re.escape(version)}\b.*$', changelog, re.M)
    if not match:
        return None
    end = SECTION.search(changelog, match.end())
    return match.group(0), changelog[match.end():end.start() if end else len(changelog)].strip()


ISSUE = re.compile(r'github\.com/' + re.escape(REPOSITORY) + r'/(?:issues|pull)/(\d+)|(?<![\w/&])#(\d+)\b')


def issues_in(notes):
    """The issue and pull request numbers a CHANGELOG section names, as links or as #123, in order, once each."""
    found = []
    for match in ISSUE.finditer(notes):
        number = int(match.group(1) or match.group(2))
        if number not in found:
            found.append(number)
    return found


def title(changelog_heading):
    """The GitHub release's title from its CHANGELOG heading: "Tessera 0.4.84 · firmware 0.52.0"."""
    match = re.fullmatch(r'## (\d+\.\d+\.\d+) \(firmware (\d+\.\d+\.\d+)((?: for [a-z0-9, ]+)?)\)', changelog_heading)
    if not match:
        raise Refusal(f'The CHANGELOG heading "{changelog_heading}" names no firmware')
    return f'Tessera {match.group(1)} · firmware {match.group(2)}{match.group(3)}'


# ----- git and GitHub ----------------------------------------------------------------------------------------------

def git(*args, env=None, input=None, check=True, cwd=None):
    done = subprocess.run(['git', *args], cwd=cwd or ROOT, capture_output=True, text=True, env=env, input=input)
    if check and done.returncode:
        raise Refusal(f'git {" ".join(args)}: {done.stderr.strip() or done.stdout.strip()}')
    return done.stdout.strip()


def has(ref):
    return bool(git('rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}', check=False))


def ancestor(older, newer):
    return subprocess.run(['git', 'merge-base', '--is-ancestor', older, newer], cwd=ROOT).returncode == 0


def fetch():
    git('fetch', '--quiet', '--tags', 'origin')


def branch():
    return git('rev-parse', '--abbrev-ref', 'HEAD')


def clean():
    """Whether nothing tracked is changed (new untracked files don't go into a release either way)."""
    return not git('status', '--porcelain', '--untracked-files=no')


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def write(path, text):
    (ROOT / path).write_text(text, encoding='utf-8')


def gh(*args):
    done = subprocess.run(['gh', *args], cwd=ROOT, capture_output=True, text=True)
    if done.returncode:
        raise Refusal(f'gh {" ".join(args[:2])}: {done.stderr.strip() or done.stdout.strip()}')
    return done.stdout.strip()


def ci_state(sha):
    """{job: conclusion or status} of the CI jobs a release waits for, on commit `sha`."""
    rows = gh('api', f'repos/{REPOSITORY}/commits/{sha}/check-runs?per_page=100', '--jq',
              '.check_runs[] | [.name, (.conclusion // .status)] | @tsv')
    found = {}
    for row in rows.splitlines():
        name, _, state = row.partition('\t')
        # A job run again: one success of it is enough.
        if found.get(name) != 'success':
            found[name] = state
    return {job: found.get(job, 'missing') for job in CI_JOBS}


def the_release():
    """What the working tree is as a release, counted from where it left origin/main."""
    base = affected_boards.default_base()
    reach = affected_boards.sort(affected_boards.changed_paths(base), base)
    new = affected_boards.new_boards(base)
    return base, reach, new, affected_boards.release_of(reach, new, affected_boards.read_at(base))


# ----- the commands ------------------------------------------------------------------------------------------------

def status(_args):
    fetch()
    here = branch()
    print(f'On {here} at {git("rev-parse", "--short", "HEAD")}.')
    ahead = git('log', '--oneline', f'origin/{RELEASES}..HEAD')
    missing = git('log', '--oneline', f'HEAD..origin/{RELEASES}')
    print(f'\nSince the last release ({git("describe", "--tags", "--abbrev=0", f"origin/{RELEASES}", check=False) or RELEASES}): '
          f'{len(ahead.splitlines())} commit(s).')
    for line in ahead.splitlines()[:40]:
        print(f'  {line}')
    if missing:
        print(f'\nmain has {len(missing.splitlines())} commit(s) this branch lacks (a hotfix or a docs push): merge '
              f'origin/main into {WORK} before the release.')
    notes = unreleased(read(CHANGELOG))
    print('\nCHANGELOG, "## Unreleased":', 'missing' if notes is None else ('empty' if not notes else ''))
    for line in (notes or '').splitlines()[:30]:
        print(f'  {line}')
    base, reach, new, _release = the_release()
    print(f'\nThe firmware, against {base[:12]}:\n')
    print(affected_boards.plan(reach, new, affected_boards.read_at(base)))
    return 0


def prepare(args):
    fetch()
    here = branch()
    if here != WORK and not here.startswith('hotfix') and not args.any_branch:
        raise Refusal(f'A release is prepared on {WORK} (or a hotfix branch made from main), not on {here}.')
    if not clean():
        raise Refusal('The working tree has changes: commit or stash them first, the release commit holds only the release.')
    if has(f'origin/{here}') and git('rev-parse', 'HEAD') != git('rev-parse', f'origin/{here}'):
        raise Refusal(f'HEAD is not origin/{here}: pull or push first, so the release is what everyone sees on {here}.')
    if not ancestor(f'origin/{RELEASES}', 'HEAD'):
        raise Refusal(f'origin/{RELEASES} has commits this branch lacks (a hotfix or a docs push): '
                      f'git merge origin/{RELEASES} first, so main can move here without losing them.')
    changelog, config = read(CHANGELOG), read(CONFIG)
    current = version_of(config)
    version = args.version or next_version(current)
    if not firmware_count.parse(version) or firmware_count.parse(version) <= firmware_count.parse(current):
        raise Refusal(f'The app version has to go up from {current}, not to {version}.')
    _base, reach, new, release = the_release()
    if not release['firmware']:
        raise Refusal('packages/core.yaml names no SCREEN_FIRMWARE_VERSION')
    line = heading(version, release)
    write(CHANGELOG, named(changelog, line))
    write(CONFIG, with_version(config, version))
    touched = [CHANGELOG, CONFIG]
    if release['kind'] == 'shared':
        write('packages/core.yaml', with_core_number(read('packages/core.yaml'), release['firmware']))
        write(CORE_PY, with_core_py_number(read(CORE_PY), release['firmware']))
        touched += ['packages/core.yaml', CORE_PY]
        for key, path in profiles.BOARDS.items():
            text = path.read_text(encoding='utf-8')
            if CORE_NUMBER.search(text):
                path.write_text(without_board_number(text), encoding='utf-8')
                touched.append(str(path.relative_to(ROOT)))
    elif release['kind'] == 'boards':
        for key in release['boards']:
            path = profiles.BOARDS[key]
            path.write_text(with_board_number(path.read_text(encoding='utf-8'), release['firmware'], version), encoding='utf-8')
            touched.append(str(path.relative_to(ROOT)))
    if release['kind'] != 'app':
        subprocess.run([sys.executable, 'tools/generate_board_shapes.py'], cwd=ROOT, check=True, capture_output=True)
        touched.append('screen_manager/app/boards.json')
    print(f'Release {line[3:]}')
    print('Changed: ' + ', '.join(dict.fromkeys(touched)))
    firmware = release['kind'] != 'app'
    steps = [
        'Read the CHANGELOG section once more: it is what Home Assistant shows under the update.',
        *(['The firmware number changed, so the editor\'s preview is stale: sh web/wasm/build.sh, then cd web && '
           'npm run build (docs/RELEASING.md, "Firmware preview").'] if firmware else []),
        'tools/check.sh (the firmware of every board is built by CI on the release commit, step 5).',
        f'Commit as "Release {version} (firmware {release["firmware"]}): <what it brings>" and push to {here}.',
        'tools/release.py ci: every board on both ESPHome versions with the flash budget, in CI, about an hour; the '
        'upgrade test can run meanwhile.',
        'tools/release.py candidate, then the upgrade test (docs/TESTING.md, "6. The upgrade").',
        'Write the GitHub release notes in English in a file, then tools/release.py publish --notes <file> --yes.',
    ]
    print('\nNext:')
    for number, step in enumerate(steps, 1):
        print(f'{number}. {step}')
    print('\nThe firmware plan (CI builds it in step 5; locally only a board you want to look at):\n')
    print(affected_boards.plan(reach, new, affected_boards.read_at(_base)))
    return 0


def ci(_args):
    fetch()
    here, head = branch(), git('rev-parse', 'HEAD')
    if not has(f'origin/{here}') or git('rev-parse', f'origin/{here}') != head:
        raise Refusal(f'HEAD is not origin/{here}: push the release commit first; CI builds what the branch has.')
    state = ci_state(head)
    if all(value == 'success' for value in state.values()):
        print(f'CI is green on {head[:12]} already.')
        return 0
    gh('workflow', 'run', 'ci.yml', '--repo', REPOSITORY, '--ref', here)
    print(f'CI started on {here} at {head[:12]}: tools/check.sh and every board on both ESPHome versions.')
    print(f'Follow it with: gh run list --repo {REPOSITORY} --workflow ci.yml --branch {here} --limit 1, then gh run watch <id>')
    return 0


def candidate_commit(head, cwd=None):
    """(a commit on top of `head` whose published entries fetch from the candidate branch, how many entries changed),
    made without touching the working tree or the index."""
    entries = [path for path in git('ls-tree', '--name-only', head, 'packages/', cwd=cwd).splitlines()
               if path.endswith('.yaml')]
    with tempfile.TemporaryDirectory() as folder:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(folder) / 'index')}
        git('read-tree', head, env=env, cwd=cwd)
        pointed = 0
        for path in entries:
            text, changed = pointed_at(git('show', f'{head}:{path}', cwd=cwd), CANDIDATE)
            if REF_MAIN.search(text) or FONTS_MAIN.search(text) or GITHUB_REF_MAIN.search(text):
                raise Refusal(f'{path} still fetches from main after the change')
            if changed:
                blob = git('hash-object', '-w', '--stdin', input=text + '\n', cwd=cwd)
                git('update-index', '--cacheinfo', f'100644,{blob},{path}', env=env, cwd=cwd)
                pointed += 1
        if not pointed:
            raise Refusal('No published entry under packages/ fetches from main: nothing to point at the candidate')
        tree = git('write-tree', env=env, cwd=cwd)
    message = (f'Release candidate of {head[:12]}: the packages fetch from {CANDIDATE}\n\n'
               f'tools/release.py candidate. The same tree as {head[:12]} but for the refs of the published entries, so a\n'
               f'test Home Assistant builds this commit through its own Update button. Never merged anywhere.\n')
    return git('commit-tree', tree, '-p', head, input=message, cwd=cwd), pointed


def candidate(args):
    fetch()
    if args.delete:
        if git('ls-remote', '--heads', 'origin', CANDIDATE):
            git('push', '--quiet', 'origin', '--delete', CANDIDATE)
            print(f'Removed {CANDIDATE}.')
        else:
            print(f'There is no {CANDIDATE}.')
        return 0
    head = git('rev-parse', 'HEAD')
    if not clean():
        print('Note: the working tree has changes; the candidate is HEAD as committed, without them.')
    commit, pointed = candidate_commit(head)
    git('push', '--quiet', '--force', 'origin', f'{commit}:refs/heads/{CANDIDATE}')
    print(f'{CANDIDATE} is {head[:12]} with {pointed} published entries pointed at it ({commit[:12]}).')
    print(f'Point a test screen at it: `ref: {CANDIDATE}` under packages: display: in its YAML, then Update or Install.')
    return 0


def publish(args):
    fetch()
    head = git('rev-parse', 'HEAD')
    here = branch()
    problems = []
    if not clean():
        problems.append('the working tree has changes')
    if here == WORK:
        if git('rev-parse', f'origin/{WORK}') != head:
            problems.append(f'HEAD is not origin/{WORK}: push it, then let CI run')
    elif not git('branch', '-r', '--contains', head):
        problems.append('HEAD is on no branch of origin: push it, then let CI run')
    if not ancestor(f'origin/{RELEASES}', head):
        problems.append(f'origin/{RELEASES} has commits HEAD lacks: merge them first, main only moves forward')
    changelog = read(CHANGELOG)
    version = version_of(read(CONFIG))
    if unreleased(changelog) is not None:
        problems.append('the CHANGELOG still has "## Unreleased": tools/release.py prepare names it')
    first = FIRST_HEADING.search(changelog)
    found = section(changelog, version)
    if not first or not found or first.group(0) != found[0]:
        problems.append(f'the newest CHANGELOG heading is not {version}, the version in {CONFIG}')
    tag = f'screens-v{version}'
    if has(f'refs/tags/{tag}') or git('ls-remote', '--tags', 'origin', f'refs/tags/{tag}'):
        problems.append(f'the tag {tag} exists already')
    lint = subprocess.run([sys.executable, '-m', 'unittest', '-q', 'tests.test_release_lint'], cwd=ROOT,
                          capture_output=True, text=True)
    if lint.returncode:
        problems.append('tests/test_release_lint.py fails:\n' + lint.stderr.strip()[-1500:])
    if not args.without_ci:
        state = ci_state(head)
        if any(value != 'success' for value in state.values()):
            problems.append('CI is not green on HEAD (tools/release.py ci starts it): '
                            + ', '.join(f'{job} {value}' for job, value in state.items()))
    if not args.without_upgrade_test:
        tested = git('ls-remote', '--heads', 'origin', CANDIDATE).split('\t')[0]
        if not tested:
            problems.append(f'there is no {CANDIDATE}: make it from this commit and run the upgrade test '
                            '(docs/TESTING.md, "6. The upgrade"), or say why not with --without-upgrade-test')
        else:
            git('fetch', '--quiet', 'origin', CANDIDATE)
            if git('rev-parse', f'{tested}^') != head:
                problems.append(f'{CANDIDATE} was made of another commit than HEAD: the upgrade test ran on something '
                                'else; make it again and test this one')
    notes = Path(args.notes)
    if not notes.is_file() or not notes.read_text(encoding='utf-8').strip():
        problems.append(f'no release notes in {notes}')
    if problems:
        raise Refusal('Not published:\n- ' + '\n- '.join(problems))
    name = title(found[0])
    plan = [f'push {head[:12]} to main (a fast-forward from {git("rev-parse", "--short", f"origin/{RELEASES}")})',
            f'tag {tag} on it and push the tag',
            f'GitHub release "{name}" with the notes in {notes}',
            f'remove {CANDIDATE}']
    if not args.yes:
        print('Would:\n- ' + '\n- '.join(plan) + '\nNothing done: run again with --yes.')
        return 0
    git('push', '--quiet', 'origin', f'{head}:refs/heads/{RELEASES}')
    git('tag', tag, head)
    git('push', '--quiet', 'origin', f'refs/tags/{tag}')
    gh('release', 'create', tag, '--repo', REPOSITORY, '--title', name, '--notes-file', str(notes), '--verify-tag')
    if git('ls-remote', '--heads', 'origin', CANDIDATE):
        git('push', '--quiet', 'origin', '--delete', CANDIDATE)
    print(f'Published {name}: main is {head[:12]}, tag {tag}.')
    named = issues_in(found[1])
    if named:
        print('Reply on each with the version that has it and how to get it, then close it: '
              + ', '.join(f'https://github.com/{REPOSITORY}/issues/{number}' for number in named))
    if here != WORK:
        print(f'This came from {here}: merge origin/main into {WORK} now, so the next release has it too.')
    print('Point the test screens back at main (ref: main), and keep an eye on new issues today.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='what the next release holds')
    commands.add_parser('ci', help='CI on the pushed release commit, every board')
    ready = commands.add_parser('prepare', help="the release's edits in the working tree")
    ready.add_argument('--version', help='the app version (default: the last one, its last number up)')
    ready.add_argument('--any-branch', action='store_true', help='prepare on another branch than dev or hotfix*')
    test = commands.add_parser('candidate', help=f'push {CANDIDATE} for the upgrade test')
    test.add_argument('--delete', action='store_true', help=f'remove {CANDIDATE}')
    out = commands.add_parser('publish', help='main, the tag and the GitHub release')
    out.add_argument('--notes', required=True, help='a file with the GitHub release notes, in English')
    out.add_argument('--yes', action='store_true', help='do it (without: say what it would do)')
    out.add_argument('--without-ci', action='store_true', help='publish while CI is not green on HEAD')
    out.add_argument('--without-upgrade-test', action='store_true', help=f'publish without a {CANDIDATE} of HEAD')
    args = parser.parse_args(argv)
    try:
        return {'status': status, 'prepare': prepare, 'ci': ci, 'candidate': candidate, 'publish': publish}[args.command](args)
    except Refusal as refusal:
        print(f'release: {refusal}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
