"""The plugins repository's part of a release (docs/RELEASING.md, "The release", step 6; its AGENTS.md, "Branches").

github.com/MaxGramser/tessera-plugins has a dev and a main branch, each with its own index.json: every app reads main's,
the dev app dev's first. A plugin that needs what only Tessera's dev firmware has (a newer plugin API) waits on its dev.
So when Tessera releases, the plugins repository's dev goes to its main the same moment, its index is built again on
main against the released core, and the release checks that what every app now offers fits that core:

- before anything is published (`preflight`): the plugins' check is green on their dev, every plugin of dev's index fits
  the plugin API of this release, and dev merges into main without a conflict outside the generated files;
- after Tessera's main moved (`release`): dev merges into main (main has commits of its own: the hourly likes and index,
  a community plugin), main's index is built by its workflow against the released core, and checked: it names this
  core's plugin API, every plugin in it fits, every plugin dev offered is there in at least that version, and the
  plugins' check is green on main; then dev moves up to main, so the two start the next round alike.

A hotfix leaves the plugins alone: it brings no newer plugin API. Each step can run again (`tools/release.py plugins`):
a main that has dev already only gets its index built and checked. Standard library only, and git and gh.
"""
import calendar
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

REPOSITORY = 'MaxGramser/tessera-plugins'
WORK, RELEASES = 'dev', 'main'
# The files the plugins repository's workflow writes (index.yml): in a merge, dev's index (it is built again on main
# right after) and main's likes (the newest count).
GENERATED = {'index.json': 'dev', 'likes.json': 'main'}
CHECK_JOB = 'check'
INDEX_WORKFLOW = 'index.yml'
WAIT = 20 * 60          # seconds a workflow of the plugins repository may take before the release says so
POLL = 15


class Problem(Exception):
    pass


# ----- pure rules ---------------------------------------------------------------------------------------------------

def remote_of(tessera_url):
    """The plugins repository's address beside Tessera's own (the same host and the same way in), or
    TESSERA_PLUGINS_REMOTE."""
    if os.environ.get('TESSERA_PLUGINS_REMOTE'):
        return os.environ['TESSERA_PLUGINS_REMOTE']
    url = re.sub(r'homeassistant_espscreen(\.git)?$', r'tessera-plugins\1', tessera_url.strip())
    if url == tessera_url.strip():
        raise Problem(f'cannot tell the plugins repository from {tessera_url}: set TESSERA_PLUGINS_REMOTE')
    return url


def api_text(api):
    return f'{api[0]}.{api[1]}'


def entries(index):
    """(id, version, api) of every plugin an index offers (one that cannot be offered, status not ok, is left out)."""
    out = []
    for plugin in (index or {}).get('plugins') or []:
        if plugin.get('status', 'ok') != 'ok':
            continue
        manifest = plugin.get('manifest') or {}
        version = (plugin.get('release') or {}).get('version') or manifest.get('version') or ''
        out.append((plugin.get('id', ''), version, str(manifest.get('api', ''))))
    return out


def version_tuple(text):
    return tuple(int(part) if part.isdigit() else 0 for part in str(text or '').split('.'))


def misfits(index, fits):
    """The plugins of an index the core cannot build: 'id version (plugin API x.y)'. `fits(api)` is the core's own rule
    (plugin_manifest.api_fits with its PLUGIN_API)."""
    return [f'{plugin} {version} (plugin API {api})' for plugin, version, api in entries(index) if not fits(api)]


def brings(main_index, dev_index):
    """What the release brings every app: [(id, version on main or None, version on dev)], newer on dev only."""
    on_main = {plugin: version for plugin, version, _ in entries(main_index)}
    return [(plugin, on_main.get(plugin), version) for plugin, version, _ in entries(dev_index)
            if plugin not in on_main or version_tuple(version) > version_tuple(on_main[plugin])]


def index_problems(index, api, fits, offered):
    """What is wrong with main's index after the release: it names another plugin API than the released core's, a
    plugin in it does not fit that core, or a plugin dev offered (`offered`, an index) is missing or older."""
    problems = []
    if str((index or {}).get('plugin_api')) != api_text(api):
        problems.append(f'main\'s index names plugin API {(index or {}).get("plugin_api")}, the release has {api_text(api)}')
    problems += [f'{misfit} does not fit the released core' for misfit in misfits(index, fits)]
    on_main = {plugin: version for plugin, version, _ in entries(index)}
    for plugin, version, _ in entries(offered):
        if plugin not in on_main:
            problems.append(f'{plugin} {version} from dev is not in main\'s index')
        elif version_tuple(on_main[plugin]) < version_tuple(version):
            problems.append(f'{plugin} is {on_main[plugin]} in main\'s index, dev had {version}')
    return problems


def core_api(root):
    """(PLUGIN_API, fits) of the core in `root`: the manifest rule the app and the firmware build of this release use."""
    path = Path(root) / 'screen_manager' / 'app' / 'plugin_manifest.py'
    spec = importlib.util.spec_from_file_location('release_plugin_manifest', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PLUGIN_API, (lambda api: module.api_fits(api, module.PLUGIN_API, module.PLUGIN_API_BREAKS))


# ----- the repository -----------------------------------------------------------------------------------------------

def run(command, cwd=None, check=True, input=None):
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, input=input)
    if check and done.returncode:
        raise Problem(f'{" ".join(command[:3])}: {done.stderr.strip() or done.stdout.strip()}')
    return done.stdout.strip()


class Clone:
    """A clone of the plugins repository of its own, in a folder that goes again (`with Clone(url) as plugins`)."""

    def __init__(self, url):
        self.url = url
        self.folder = None

    def __enter__(self):
        self.folder = tempfile.TemporaryDirectory(prefix='tessera-plugins-')
        self.path = Path(self.folder.name) / 'plugins'
        run(['git', 'clone', '--quiet', self.url, str(self.path)])
        # A merge commit wants a name: the maintainer's own (commit-author rule), else one that says what made it.
        if not self.git('config', 'user.name', check=False):
            self.git('config', 'user.name', 'Tessera release')
            self.git('config', 'user.email', 'release@tessera.invalid')
        return self

    def __exit__(self, *_):
        self.folder.cleanup()

    def git(self, *args, check=True, input=None):
        return run(['git', *args], cwd=self.path, check=check, input=input)

    def fetch(self):
        self.git('fetch', '--quiet', 'origin')

    def sha(self, branch):
        return self.git('rev-parse', f'origin/{branch}')

    def ahead(self, of, branch):
        """The commits on `branch` that `of` lacks, one line each."""
        return [line for line in self.git('log', '--oneline', f'origin/{of}..origin/{branch}').splitlines() if line]

    def contains(self, older, newer):
        return subprocess.run(['git', 'merge-base', '--is-ancestor', older, newer], cwd=self.path).returncode == 0

    def last_own(self, branch):
        """The newest commit on `branch` that the index workflow did not make: its own commits start no check
        (index.yml), so the check of a branch is the one on this commit."""
        return self.git('log', '-1', '--format=%H', '--perl-regexp', '--author=^(?!github-actions)', f'origin/{branch}')

    def index(self, ref):
        text = self.git('show', f'{ref}:index.json', check=False)
        try:
            return json.loads(text) if text else {}
        except ValueError:
            return {}

    def merge(self, message, keep=False):
        """dev merged into main in the clone: (the merge commit or None when main has dev already, the conflicts outside
        the generated files). The generated files take GENERATED's side. Without `keep` the merge is undone again (a
        trial)."""
        self.git('checkout', '--quiet', '-B', 'release-merge', f'origin/{RELEASES}')
        if self.contains(f'origin/{WORK}', 'HEAD'):
            return None, []
        done = subprocess.run(['git', 'merge', '--no-ff', '--no-commit', f'origin/{WORK}'], cwd=self.path,
                              capture_output=True, text=True)
        conflicts = [path for path in self.git('diff', '--name-only', '--diff-filter=U').splitlines() if path]
        if done.returncode and not conflicts:
            self.git('merge', '--abort', check=False)
            raise Problem(f'git merge: {done.stderr.strip() or done.stdout.strip()}')
        for path in conflicts:
            if path in GENERATED:
                self.git('checkout', '--theirs' if GENERATED[path] == WORK else '--ours', '--', path)
                self.git('add', '--', path)
        left = [path for path in conflicts if path not in GENERATED]
        if left or not keep:
            self.git('merge', '--abort', check=False)
            return None, left
        self.git('commit', '--quiet', '-m', message)
        return self.git('rev-parse', 'HEAD'), []


# ----- GitHub -------------------------------------------------------------------------------------------------------

def gh(*args):
    return run(['gh', *args])


def check_state(sha):
    """The plugins' check on a commit: success, failure, a status while it runs, or missing."""
    rows = gh('api', f'repos/{REPOSITORY}/commits/{sha}/check-runs?per_page=100', '--jq',
              '.check_runs[] | [.name, (.conclusion // .status)] | @tsv')
    states = [row.partition('\t')[2] for row in rows.splitlines() if row.partition('\t')[0] == CHECK_JOB]
    return 'success' if 'success' in states else (states[0] if states else 'missing')


def wait_for_check(sha, say=print):
    """The plugins' check on `sha` once it ended (it starts with every push)."""
    end = time.monotonic() + WAIT
    while True:
        state = check_state(sha)
        if state not in ('queued', 'in_progress', 'pending', 'waiting', 'requested', 'missing'):
            return state
        if time.monotonic() > end:
            return state
        say(f'  the plugins\' check on {sha[:7]}: {state}, waiting')
        time.sleep(POLL)


def build_index(say=print):
    """Runs the index workflow on main (index.yml: built against TESSERA_REF main, the released core, and committed
    when it changed) and waits for it: its conclusion."""
    started = time.time() - 5
    gh('workflow', 'run', INDEX_WORKFLOW, '--repo', REPOSITORY, '--ref', RELEASES)
    end = time.monotonic() + WAIT
    while time.monotonic() < end:
        time.sleep(POLL)
        rows = json.loads(gh('run', 'list', '--repo', REPOSITORY, '--workflow', INDEX_WORKFLOW, '--branch', RELEASES,
                             '--event', 'workflow_dispatch', '--limit', '5', '--json', 'databaseId,status,conclusion,createdAt'))
        mine = [row for row in rows if calendar.timegm(time.strptime(row['createdAt'], '%Y-%m-%dT%H:%M:%SZ')) >= started]
        if mine and mine[0]['status'] == 'completed':
            return mine[0]['conclusion']
        say(f'  the index on main: {mine[0]["status"] if mine else "starting"}, waiting')
    return 'timed out'


# ----- the steps ----------------------------------------------------------------------------------------------------

def report(plugins, api, fits):
    """Lines for `status` and `prepare`: what the plugins repository's dev brings to every app with this release."""
    plugins.fetch()
    ahead, behind = plugins.ahead(RELEASES, WORK), plugins.ahead(WORK, RELEASES)
    dev_index, main_index = plugins.index(f'origin/{WORK}'), plugins.index(f'origin/{RELEASES}')
    lines = [f'tessera-plugins: dev has {len(ahead)} commit(s) main lacks, main {len(behind)} dev lacks '
             f'(merged with the release). This core offers plugin API {api_text(api)}.']
    new = brings(main_index, dev_index)
    lines += [f'  {plugin}: {old or "new"} -> {version}' for plugin, old, version in new] or ['  no plugin changes']
    lines += [f'  does not fit this release: {misfit}' for misfit in misfits(dev_index, fits)]
    return lines


def preflight(plugins, api, fits):
    """What stops the plugins going along with this release, before anything is published: [problems]."""
    plugins.fetch()
    problems = []
    dev = plugins.last_own(WORK)
    state = check_state(dev)
    if state != 'success':
        problems.append(f'the plugins\' check on their dev ({dev[:7]}) is {state}')
    dev_index = plugins.index(f'origin/{WORK}')
    problems += [f'{misfit} on the plugins\' dev does not fit this release: update it or take it off dev'
                 for misfit in misfits(dev_index, fits)]
    _, conflicts = plugins.merge('trial', keep=False)
    if conflicts:
        problems.append('the plugins\' dev does not merge into their main by itself (' + ', '.join(conflicts)
                        + '): merge main into their dev by hand first')
    return problems


def release(plugins, api, fits, version, say=print):
    """The plugins' dev into their main, main's index built against the released core and checked, dev up to main.
    Raises Problem with what is left to do by hand."""
    plugins.fetch()
    dev = plugins.sha(WORK)
    offered = plugins.index(f'origin/{WORK}')
    merged, conflicts = plugins.merge(f'Merge dev into main: the plugins for Tessera {version} (plugin API {api_text(api)})',
                                      keep=True)
    if conflicts:
        raise Problem('dev does not merge into main by itself (' + ', '.join(conflicts) + '): merge it by hand, then '
                      'tools/release.py plugins --yes')
    if merged:
        plugins.git('push', '--quiet', 'origin', f'{merged}:refs/heads/{RELEASES}')
        say(f'tessera-plugins: dev ({dev[:7]}) merged into main as {merged[:7]}.')
    else:
        say('tessera-plugins: main has dev already.')
    conclusion = build_index(say)
    if conclusion != 'success':
        raise Problem(f'the index workflow on main ended {conclusion}: '
                      f'gh run list --repo {REPOSITORY} --workflow {INDEX_WORKFLOW} --branch main')
    plugins.fetch()
    main, checked = plugins.sha(RELEASES), plugins.last_own(RELEASES)
    problems = index_problems(plugins.index(f'origin/{RELEASES}'), api, fits, offered)
    state = wait_for_check(checked, say)
    if state != 'success':
        problems.append(f'the plugins\' check on main ({checked[:7]}) is {state}')
    if problems:
        raise Problem('main of tessera-plugins is not what this release offers:\n  - ' + '\n  - '.join(problems))
    say(f'tessera-plugins: main {main[:7]} offers {len(entries(plugins.index(f"origin/{RELEASES}")))} plugins, all '
        f'fitting plugin API {api_text(api)}; the check is green.')
    # dev starts the next round where main is: a fast-forward, when nobody pushed to dev meanwhile.
    if plugins.sha(WORK) == dev and plugins.contains(f'origin/{WORK}', f'origin/{RELEASES}'):
        plugins.git('push', '--quiet', 'origin', f'origin/{RELEASES}:refs/heads/{WORK}')
        say('tessera-plugins: dev moved up to main.')
    else:
        say('tessera-plugins: dev moved meanwhile: merge their main into their dev by hand.')
