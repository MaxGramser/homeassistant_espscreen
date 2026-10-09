"""Plugins in the app (docs/PLUGINS.md): which exist, which each screen runs, the file that builds them into a screen's
firmware, and the data their tiles show.

Where plugins come from:
- **the index**, github.com/MaxGramser/tessera-plugins `index.json`: every plugin with its manifest, its texts and its
  README at the commit of its release. Read when the editor opens and at most every ten minutes, kept in
  /data/plugins/ for when the internet is away.
- **a folder** in Home Assistant's config, `tessera-plugins/<id>/` beside the `esphome/` folder: a plugin someone is
  making. Every build takes what the folder holds now; the app shows it as a test and offers no updates.

The app never runs a plugin's code. It reads the manifest (plugin_manifest.py), writes the screen's plugins file so
ESPHome builds the plugin into that screen, and carries out the plugin's fetches with its own rules (plugin_fetch.py).
"""
import asyncio
import json
import logging
import math
import re
import time
from copy import deepcopy
from pathlib import Path

import yaml

import core
import plugin_fetch
import plugin_manifest as pm
import tile_icons
from i18n import t
from plugin_store import PluginSecrets, PluginStore

LOG = logging.getLogger('plugins')

INDEX_URL = 'https://raw.githubusercontent.com/MaxGramser/tessera-plugins/main/index.json'
# How old the index may be before the next editor visit asks GitHub again: a conditional request (ETag) that costs
# nothing when it did not change, so a new release shows as an update within minutes.
INDEX_TTL = 10 * 60
# How often a plugin added with a link asks its repository for a newer release: two calls of GitHub's API each time,
# which allows 60 an hour to an app without a token.
LINK_TTL = 60 * 60
INDEX_MAX = 2 * 1024 * 1024
INDEX_FORMAT = 1
TESSERA_OWNER = 'https://github.com/MaxGramser/'
GITHUB_LINK = re.compile(r'^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:/tree/([^/]+)(?:/(.+?))?)?/?$')
GITHUB_API = 'https://api.github.com/repos/{owner}/{repo}'
GITHUB_RAW = 'https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}'
FOLDER = 'tessera-plugins'
PLUGIN_ICON = 'F0A66'         # puzzle-outline, for a plugin whose icon is not in Tessera's set
X_BUDGET = 2600               # bytes of a tile's data on the wire: the message carries more and stays under 4 KB
# How far lists are shortened, each to the same length from the end, until an answer or a tile's entity fits its bytes:
# first not at all, then a day of quarters twice, once, half a day.
LIST_STEPS = (None, 192, 96, 48, 24, 16, 12, 8, 4, 2, 1, 0)
LOOP_SECONDS = 15


async def read_whole(response, limit):
    """The whole body of `response`, at most `limit` bytes (ValueError past it). content.read(n) is not this: it returns
    what has arrived so far, and a body in more than one piece came back cut off."""
    raw = bytearray()
    async for chunk in response.content.iter_chunked(65536):
        raw += chunk
        if len(raw) > limit:
            raise ValueError(f'larger than {limit} bytes')
    return bytes(raw)


def board_name(key):
    """How a person knows a board of boards.yaml: "Waveshare ESP32-P4-86-Panel-ETH-2RO"; the key for one this app lacks."""
    catalog = core.SHAPES.get(key, {}).get('catalog') or {}
    return ' '.join(part for part in (catalog.get('name'), catalog.get('model')) if part) or key


def api_text():
    return f'{pm.PLUGIN_API[0]}.{pm.PLUGIN_API[1]}'


def glyph(name):
    return tile_icons.GLYPHS.get(name) or PLUGIN_ICON


def json_size(value):
    return len(json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode())


def bounded(value, limit=3200):
    """An answer for a screen within `limit` bytes of JSON: long texts cut to 48 bytes, then lists shortened from the
    end until it fits, each to the same length. A screen's message is at most 4 KB with everything around it. Bytes
    decide, not a count: 96 prices of a quarter of an hour fit whole."""
    def cut(node, items):
        if isinstance(node, str):
            return core.short(node, 48)
        if isinstance(node, list):
            return [cut(child, items) for child in (node if items is None else node[:items])]
        if isinstance(node, dict):
            return {str(key)[:32]: cut(child, items) for key, child in list(node.items())[:24]}
        return node if isinstance(node, (int, float, bool)) or node is None else str(node)[:48]
    for items in LIST_STEPS:
        shaped = cut(value, items)
        if json_size(shaped) <= limit:
            return shaped
    return None


def trimmed(data):
    """A tile's data within X_BUDGET: the last items go first."""
    if not isinstance(data, dict):
        return data
    data = dict(data)
    while len(json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode()) > X_BUDGET:
        items = data.get('items')
        if not isinstance(items, list) or not items:
            return {'wait': 'too_large'}
        data['items'] = items[:-1]
    return data


class Entry:
    """One plugin the app knows, from the index, a snapshot of an installed release, or a folder."""

    def __init__(self, raw, translations, readme, source, label, repo=None, path='.', ref=None, folder=None, status='ok'):
        self.raw, self.translations, self.readme = raw, translations, readme
        self.source, self.label, self.repo, self.path, self.ref = source, label, repo, path or '.', ref
        self.folder, self.status = folder, status
        self.manifest = pm.check(raw, translations.get('en'))
        self.id, self.version = self.manifest['id'], self.manifest['version']
        self.texts = pm.texts(self.manifest, translations)

    def text(self, key, language='en'):
        words = self.texts.get(key) or {}
        return words.get(language) or words.get(language.split('-')[0]) or words.get('en') or key

    def tile(self, tile_id):
        return next((tile for tile in self.manifest['tiles'] if tile['id'] == tile_id), None)

    def fetch(self, fetch_id):
        return next((fetch for fetch in self.manifest['fetch'] if fetch['id'] == fetch_id), None)

    def link(self):
        """The plugin's folder on GitHub, at its commit."""
        if not self.repo:
            return ''
        base = self.repo.rstrip('/').removesuffix('.git')
        return base if self.path in ('', '.') else f'{base}/tree/{self.ref or "main"}/{self.path}'

    def snapshot(self):
        return {'raw': self.raw, 'translations': self.translations, 'readme': self.readme, 'source': self.source,
                'label': self.label, 'repo': self.repo, 'path': self.path, 'ref': self.ref}


def read_folder(folder):
    """An Entry from a plugin's folder on disk, or raises."""
    folder = Path(folder)
    raw = yaml.safe_load((folder / 'tessera-plugin.yaml').read_text(encoding='utf-8'))
    translations = {}
    for path in sorted((folder / 'translations').glob('*.json')):
        try:
            translations[path.stem] = json.loads(path.read_text(encoding='utf-8'))
        except ValueError:
            continue
    readme = {}
    for path in sorted(folder.glob('README*.md')):
        language = path.stem.split('.', 1)[1] if '.' in path.stem else 'en'
        readme[language] = path.read_text(encoding='utf-8')[:64 * 1024]
    return Entry(raw, translations, readme, 'folder', 'test', folder=folder)


class Plugins:
    def __init__(self, manager, data_dir, config_dir, session_factory=None):
        self.manager = manager
        self.data = Path(data_dir) / 'plugins'
        self.config = Path(config_dir)
        self.store = PluginStore(Path(data_dir) / 'plugins.json')
        self.secrets = PluginSecrets(Path(data_dir) / 'plugin_secrets.json')
        self.fetcher = plugin_fetch.Fetcher(f'Tessera/{core.FIRMWARE_VERSION} (+plugins)', session_factory)
        self.index = {}             # id -> Entry, from index.json
        self.index_state = {'at': None, 'error': None, 'etag': None, 'checked': 0.0, 'blocked': []}
        self.folders = {}           # id -> Entry, from tessera-plugins/<id>/
        self.folder_errors = {}     # folder name -> what is wrong with it
        self.snapshots = {}         # (id, ref) -> Entry of an installed release
        self.links = {}             # id -> Entry added with a link (a release of any repository, or a branch to test)
        self.links_checked = 0.0    # when refresh_links last asked for the linked repositories' newest releases
        self.jobs = {}              # inbox -> what its waiting or running build adds and removes, and its state
        self.queue = []             # the screens that wait for a build, in the order they were asked
        self.worker = None
        self.http = None            # the session that reads the index: never the one that holds Home Assistant's token
        self._load_cached_index()
        self.scan_folders()

    # ---- What exists ----

    def _index_file(self):
        return self.data / 'index.json'

    def _load_cached_index(self):
        try:
            cached = json.loads(self._index_file().read_text())
        except (OSError, ValueError):
            return
        self._take_index(cached.get('index') or {}, cached.get('etag'), cached.get('at'))

    def _take_index(self, index, etag=None, at=None):
        if not isinstance(index, dict) or index.get('format') != INDEX_FORMAT:
            self.index_state['error'] = 'format'
            return
        entries = {}
        for item in index.get('plugins') or []:
            try:
                repo = str(item.get('repo') or '')
                label = 'tessera' if item.get('label') == 'tessera' and repo.startswith(TESSERA_OWNER) else 'community'
                release = item.get('release') or {}
                entry = Entry(item['manifest'], item.get('translations') or {}, item.get('readme') or {}, 'index', label,
                              repo=repo, path=item.get('path') or '.', ref=release.get('sha'), status=item.get('status', 'ok'))
            except (pm.ManifestError, KeyError, TypeError, ValueError) as error:
                LOG.warning('Index plugin %s skipped: %s', (item or {}).get('id') if isinstance(item, dict) else '?', error)
                continue
            entries[entry.id] = entry
        self.index = entries
        self.index_state.update(at=at, etag=etag, error=None,
                                blocked=[b for b in index.get('blocked') or [] if isinstance(b, dict)])
        self._know_tiles()

    async def refresh_index(self, force=False):
        """index.json again when it is older than INDEX_TTL (or `force`), with its ETag; the last one stays offline."""
        if not force and time.monotonic() - self.index_state['checked'] < INDEX_TTL and self.index_state['at']:
            return
        self.index_state['checked'] = time.monotonic()
        import aiohttp
        try:
            if self.http is None or self.http.closed:
                self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15),
                                                  headers={'User-Agent': self.fetcher.user_agent})
            headers = {'If-None-Match': self.index_state['etag']} if self.index_state['etag'] and not force else {}
            async with self.http.get(INDEX_URL, headers=headers) as response:
                if response.status == 304:
                    return
                response.raise_for_status()
                index = json.loads(await read_whole(response, INDEX_MAX))
                etag = response.headers.get('ETag')
        except Exception as error:
            self.index_state['error'] = type(error).__name__
            LOG.info('Plugin index not read (%s)', error)
            return
        at = time.time()
        self._take_index(index, etag, at)
        try:
            self.data.mkdir(parents=True, exist_ok=True)
            self._index_file().write_text(json.dumps({'index': index, 'etag': etag, 'at': at}))
        except OSError as error:
            LOG.warning('Plugin index not kept (%s)', error)

    def folder_root(self):
        return self.config.parent / FOLDER

    def scan_folders(self):
        """The plugins someone is making, in tessera-plugins/<id>/ beside the ESPHome folder."""
        found, errors = {}, {}
        root = self.folder_root()
        if root.is_dir():
            for folder in sorted(root.iterdir()):
                if not (folder / 'tessera-plugin.yaml').is_file() or folder.is_symlink():
                    continue
                try:
                    entry = read_folder(folder)
                except (OSError, ValueError, yaml.YAMLError, pm.ManifestError) as error:
                    errors[folder.name] = str(error)[:300]
                    continue
                if entry.id != folder.name:
                    errors[folder.name] = f'the folder must be called {entry.id}, as the plugin\'s id'
                    continue
                found[entry.id] = entry
        self.folders, self.folder_errors = found, errors
        self._know_tiles()

    def _snapshot_file(self, plugin, ref):
        return self.data / 'releases' / f'{plugin}-{ref}.json'

    def snapshot_of(self, plugin, ref):
        """The manifest, texts and README of an installed release, kept when it was installed: an older version stays
        known after the index moved on."""
        key = (plugin, ref)
        if key not in self.snapshots:
            try:
                data = json.loads(self._snapshot_file(plugin, ref).read_text())
                self.snapshots[key] = Entry(data['raw'], data['translations'], data.get('readme') or {}, data['source'],
                                            data['label'], repo=data.get('repo'), path=data.get('path'), ref=data.get('ref'))
            except (OSError, ValueError, KeyError, pm.ManifestError):
                return None
        return self.snapshots[key]

    def keep_snapshot(self, entry):
        path = self._snapshot_file(entry.id, entry.ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry.snapshot()))
        self.snapshots[(entry.id, entry.ref)] = entry

    def entry_for(self, record):
        """What an installed plugin is: its folder, the branch it follows, or the release it is pinned to."""
        if record.get('source') == 'folder':
            return self.folders.get(record['id'])
        if record.get('source') == 'branch':
            return self.links.get(record['id']) or self.snapshot_of(record['id'], record.get('ref'))
        return self.snapshot_of(record['id'], record.get('ref')) or (
            self.index.get(record['id']) if self.index.get(record['id']) and self.index[record['id']].ref == record.get('ref') else None)

    def known(self, plugin):
        """Any manifest of this plugin: on a screen first, then a folder, then the index."""
        for records in self.store.everywhere().values():
            for record in records:
                if record['id'] == plugin:
                    entry = self.entry_for(record)
                    if entry:
                        return entry
        return self.folders.get(plugin) or self.links.get(plugin) or self.index.get(plugin)

    def _know_tiles(self):
        """Every tile type's price for core.tile_cost (the screen's plugin_host::bytes uses the same manifest)."""
        prices = {}
        for entry in [*self.index.values(), *self.folders.values(), *self.snapshots.values(), *self.links.values()]:
            for tile in entry.manifest['tiles']:
                prices[f'plugin:{entry.id}.{tile["id"]}'] = tile['memory']
        core.PLUGIN_MEMORY.clear()
        core.PLUGIN_MEMORY.update(prices)

    def blocked(self, entry):
        for item in self.index_state['blocked']:
            if item.get('plugin') == entry.id and (entry.version in (item.get('versions') or []) or
                                                   (entry.ref and entry.ref == item.get('sha'))):
                return str(item.get('reason') or 'blocked')
        return None

    # ---- Adding with a link ----

    async def _github(self, url, text=False):
        import aiohttp
        if self.http is None or self.http.closed:
            self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15),
                                              headers={'User-Agent': self.fetcher.user_agent})
        async with self.http.get(url, headers={'Accept': 'application/vnd.github+json'}) as response:
            if response.status == 404:
                raise ValueError(t('addon.errors.plugins.link_not_found'))
            if response.status in (403, 429):
                raise ValueError(t('addon.errors.plugins.link_rate'))
            response.raise_for_status()
            try:
                raw = await read_whole(response, INDEX_MAX)
            except ValueError:
                raise ValueError(t('addon.errors.plugins.link_not_found')) from None
            return raw.decode('utf-8', errors='replace') if text else json.loads(raw)

    async def resolve_link(self, url, branch=None, folder=None, path=None):
        """A plugin from a link, read before anything is built: the newest release of a GitHub repository (pinned to its
        commit), a branch to test (every build takes its newest commit), or a folder in tessera-plugins/. The editor
        then shows its details like any plugin's. `path`: the plugin's folder in the repository, for a link without
        one (refresh_links)."""
        if folder:
            self.scan_folders()
            name = Path(str(folder).rstrip('/')).name
            if name in self.folder_errors:
                raise ValueError(t('addon.errors.plugins.folder', folder=name, why=self.folder_errors[name]))
            if name not in self.folders:
                raise ValueError(t('addon.errors.plugins.link_not_found'))
            return self.folders[name]
        match = GITHUB_LINK.match(str(url or '').strip())
        if not match:
            raise ValueError(t('addon.errors.plugins.link_invalid'))
        owner, repo, tree_ref, path_in_link = match.groups()
        path = (path or path_in_link or '.').strip('/') or '.'
        # The folder goes into the screen's plugins file and into git's path: letters, digits, . _ - and /, never a
        # step up or a character YAML or a shell reads as something else.
        if path != '.' and (not re.fullmatch(r'[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*', path) or '..' in path.split('/')):
            raise ValueError(t('addon.errors.plugins.link_invalid'))
        api = GITHUB_API.format(owner=owner, repo=repo)
        wanted = (branch or '').strip() or None
        if wanted and not re.fullmatch(r'[A-Za-z0-9_./-]{1,100}', wanted):
            raise ValueError(t('addon.errors.plugins.link_invalid'))
        if wanted:
            sha = (await self._github(f'{api}/commits/{wanted}'))['sha']
        else:
            # A link copied from GitHub (.../tree/main/<folder>) names the plugin's folder; what is built is still the
            # newest release, which refresh_links follows. A repository without a release keeps the link's commit.
            try:
                tag = (await self._github(f'{api}/releases/latest'))['tag_name']
            except ValueError:
                if not tree_ref:
                    raise
                tag = tree_ref
            sha = (await self._github(f'{api}/commits/{tag}'))['sha']
        base = '' if path == '.' else path + '/'
        raw = lambda name: GITHUB_RAW.format(owner=owner, repo=repo, ref=sha, path=base + name)
        manifest = yaml.safe_load(await self._github(raw('tessera-plugin.yaml'), text=True))
        listing = await self._github(f'{api}/contents/{base}translations?ref={sha}')
        translations = {}
        for item in listing if isinstance(listing, list) else []:
            name = item.get('name', '')
            if name.endswith('.json') and len(translations) < 16:
                try:
                    translations[name[:-5]] = json.loads(await self._github(raw('translations/' + name), text=True))
                except ValueError:
                    continue
        readme = {}
        files = await self._github(f'{api}/contents/{path if path != "." else ""}?ref={sha}')
        for item in files if isinstance(files, list) else []:
            name = item.get('name', '')
            if re.fullmatch(r'README(\.[a-z]{2}(-[A-Za-z]{2})?)?\.md', name):
                language = name[7:-3] or 'en'
                readme[language] = (await self._github(raw(name), text=True))[:64 * 1024]
        repo_url = f'https://github.com/{owner}/{repo}'
        label = 'test' if wanted else ('tessera' if repo_url.startswith(TESSERA_OWNER) else 'community')
        try:
            entry = Entry(manifest, translations, readme, 'branch' if wanted else 'link', label, repo=repo_url, path=path,
                          ref=wanted or sha)
        except pm.ManifestError as error:
            raise ValueError(t('addon.errors.plugins.manifest', why=str(error)[:200]))
        self.links[entry.id] = entry
        self._know_tiles()
        return entry

    async def refresh_links(self, force=False):
        """A plugin added with a link to a repository's release follows that repository: its newest release is asked
        for at most every LINK_TTL, and the editor offers it as an update like one of the index (installed releases
        only; a branch to test takes its newest commit at every build anyway). Nothing goes through Tessera: the
        maker publishes a release, the app sees it."""
        if not force and time.monotonic() - self.links_checked < LINK_TTL:
            return
        self.links_checked = time.monotonic()
        seen = set()
        for records in self.store.everywhere().values():
            for record in records:
                if record.get('source') != 'link' or record['id'] in seen:
                    continue
                seen.add(record['id'])
                entry = self.links.get(record['id']) or self.snapshot_of(record['id'], record.get('ref'))
                if not entry or not entry.repo or not GITHUB_LINK.match(entry.repo):
                    continue
                try:
                    owner, repo = GITHUB_LINK.match(entry.repo).groups()[:2]
                    api = GITHUB_API.format(owner=owner, repo=repo)
                    tag = (await self._github(f'{api}/releases/latest'))['tag_name']
                    if (await self._github(f'{api}/commits/{tag}'))['sha'] != entry.ref:
                        await self.resolve_link(entry.repo, path=entry.path)   # a new release: read it whole
                    else:
                        self.links[record['id']] = entry   # the one installed is the newest
                except Exception as error:   # offline, rate-limited, a release that no longer reads: keep what is there
                    LOG.info('Plugin %s: newest release not read (%s)', record['id'], error)

    # ---- What the editor shows ----

    def entities_with(self, domains, attributes):
        """The ids of the entities of `domains` whose attributes include every one of `attributes`, at most 500."""
        states = getattr(self.manager.ha, 'states', {}) or {}
        return sorted(eid for eid, state in states.items()
                      if isinstance(eid, str) and eid.split('.')[0] in domains
                      and all(name in ((state or {}).get('attributes') or {}) for name in attributes))[:500]

    def editor_plugin(self, entry, language='en'):
        manifest = entry.manifest
        words = lambda key: dict(entry.texts.get(key) or {'en': key}) if key else None
        option = lambda o: {**{k: v for k, v in o.items() if k not in ('label', 'hint', 'choices')},
                            'label': words(o['label']), 'hint': words(o.get('hint')),
                            **({'choices': [{'value': c['value'], 'label': words(c['label'])} for c in o['choices']]}
                               if o.get('choices') else {})}
        gpio = any(item['kind'] == 'gpio' for item in manifest['inputs'])
        return {
            'id': entry.id, 'name': words('name'), 'summary': words('summary'),
            'icon': glyph(manifest['icon']), 'maintainer': manifest['maintainer'], 'tessera': entry.label == 'tessera',
            'version': entry.version, 'repo': entry.link(), 'ref': entry.ref, 'license': manifest['license'],
            'stage': manifest['stage'], 'kind': 'hardware' if gpio or manifest['boards'] != 'any' else 'behaviour', 'boards': manifest['boards'],
            'board_names': None if manifest['boards'] == 'any' else [board_name(key) for key in manifest['boards']],
            'requires': {'psram': manifest['requires']['psram']}, 'flash_kb': manifest['flash_kb'],
            'permissions': {'home_assistant': manifest['permissions']['home_assistant_actions'] + manifest['permissions']['ha_commands'],
                            'network': manifest['permissions']['network'],
                            'read_entities': manifest['permissions']['read_entities']},
            'privacy': manifest.get('privacy'), 'readme': entry.readme,
            'languages': pm.complete_languages(manifest, entry.translations),
            'inputs': [{'id': i['id'], 'kind': i['kind'], 'scope': i['scope'], 'label': words(i['label']),
                        'hint': words(i['hint']), 'domains': i['domains']} for i in manifest['inputs']],
            'parts': [{'id': p['id'], 'label': words(p['label']), 'hint': words(p['hint']) or {'en': ''},
                       'flash_kb': p['flash_kb'], 'default': p['default']} for p in manifest['parts']],
            'attributes': manifest['attributes'],
            'tiles': [{'id': tile['id'], 'name': words(tile['name']), 'icon': glyph(tile['icon']),
                       'min': tile['min'], 'max': tile['max'], 'memory': tile['memory'],
                       'domains': tile['domains'], 'data': tile.get('data'),
                       # The entities the inspector offers when the tile needs certain attributes (`has_attributes`).
                       **({'entities': self.entities_with(tile['domains'], tile['has_attributes'])}
                          if tile.get('has_attributes') else {}),
                       'options': [option(o) for o in tile['options']],
                       'example': words(tile.get('example')), 'preview': bool(tile.get('preview'))}
                      for tile in manifest['tiles']],
            'settings': [{'key': s['key'], 'label': words(s['label'])} for s in manifest['settings']],
            'cards': [{'id': c['id'], 'name': words(c['name'])} for c in manifest['cards']],
            'tap_actions': [{'id': a['id'], 'label': words(a['label']), 'domains': a['domains']} for a in manifest['tap_actions']],
            'bar_items': [{'id': b['id'], 'label': words(b['label']), 'icon': glyph(b['icon']), 'example': words(b['example'])}
                          for b in manifest['bar_items']],
            'source': entry.source, 'label': entry.label, 'status': entry.status, 'blocked': self.blocked(entry),
            'fits_api': pm.api_fits(manifest['api']), 'api': manifest['api'],
            # What a person agrees to (permissions and attributes), as one fingerprint: an update with another asks again.
            'permission_hash': pm.permission_hash(manifest),
        }

    def running(self):
        """What each screen's last hello said it runs: {inbox: [{id, version, tiles}]}."""
        out = {}
        for inbox, sender in getattr(self.manager, 'page_senders', {}).items():
            if getattr(sender, 'plugin_api', None):
                out[inbox] = list(getattr(sender, 'plugins', []))
        return out

    def payload(self, language='en'):
        self.scan_folders()
        listed = {}
        for entry in self.index.values():
            listed[entry.id] = entry
        for entry in self.links.values():
            listed[entry.id] = entry  # a link someone added in this app
        for entry in self.folders.values():
            listed[entry.id] = entry  # a folder of the same id is the one someone is working on
        installed = {}
        for inbox, records in self.store.everywhere().items():
            installed[inbox] = []
            for record in records:
                entry = self.entry_for(record)
                if entry and entry.id not in listed:
                    listed[entry.id] = entry   # an installed release the index no longer lists
                installed[inbox].append({'id': record['id'], 'version': record.get('version', ''),
                                         'source': record.get('source', 'index'), 'ref': record.get('ref'),
                                         'parts': record.get('parts', []), 'values': record.get('values', {}),
                                         'consent': (record.get('consent') or {}).get('permissions'),
                                         'state': record.get('state', 'active'), 'reason': record.get('reason')})
        secrets = {}
        for entry in listed.values():
            for item in entry.manifest['inputs']:
                if item['kind'] == 'secret':
                    secrets.setdefault(entry.id, {})[item['id']] = self.secrets.has(entry.id, item['id'])
        # The entities of every domain a plugin names (a tile's `entity`, an input of kind entity): the editor's own list
        # has only the domains Tessera draws tiles for, and a plugin may add one it does not (a calendar).
        domains = {d for entry in listed.values() for tile in entry.manifest['tiles'] for d in tile['domains']}
        domains |= {d for entry in listed.values() for item in entry.manifest['inputs'] for d in item['domains']}
        states = getattr(self.manager.ha, 'states', {}) or {}
        entities = sorted(({'id': eid, 'name': (state.get('attributes') or {}).get('friendly_name') or eid}
                           for eid, state in states.items() if isinstance(eid, str) and eid.split('.')[0] in domains),
                          key=lambda e: e['name'].lower())[:500]
        return {'api': api_text(), 'plugins': [self.editor_plugin(entry, language) for entry in listed.values()],
                'entities': entities,
                'installed': installed, 'running': self.running(), 'secrets': secrets,
                'index': {'at': self.index_state['at'], 'error': self.index_state['error']},
                'folders': {'path': str(self.folder_root()), 'errors': self.folder_errors},
                'fetch': self.fetcher.status()}

    # ---- A screen's plugins file ----

    def sidecar(self, inbox):
        """The text of `<name>.plugins.yaml` for this screen's records."""
        packages, components = [], []
        for record in self.store.of(inbox):
            entry = self.entry_for(record)
            if not entry:
                continue
            values = record.get('values') or {}
            variables = {item['id'].upper(): str(values.get(item['id'], '')) for item in entry.manifest['inputs']
                         if item['kind'] != 'secret' and values.get(item['id'], '') != ''}
            parts = [p['file'] for p in entry.manifest['parts'] if p['id'] in (record.get('parts') or [])]
            name = f'plugin_{entry.id}'
            if record.get('source') == 'folder':
                # Relative to the ESPHome folder, so the app, Device Builder and a shared folder find the same files.
                base = f'../{FOLDER}/{entry.id}'
                include = f'!include {base}/plugin.yaml' if not variables else \
                    '!include {file: %s/plugin.yaml, vars: %s}' % (base, json.dumps(variables))
                packages.append(f'  {name}: {include}')
                for part in parts:
                    packages.append(f'  {name}_{Path(part).stem}: !include {base}/{part}')
                components.append(f'  - source: {{type: local, path: {base}/components}}')
                continue
            folder = '' if entry.path in ('', '.') else entry.path.rstrip('/') + '/'
            # A branch to test takes its newest commit at every build; everything else stays on its commit.
            refresh = '0s' if record.get('source') == 'branch' else 'never'
            packages += [f'  {name}:', f'    url: {entry.repo}', f'    ref: {entry.ref}  # {entry.id} {entry.version}',
                         f'    refresh: {refresh}', '    files:', f'      - path: {folder}plugin.yaml']
            if variables:
                packages.append(f'        vars: {json.dumps(variables)}')
            packages += [f'      - path: {folder}{part}' for part in parts]
            components += ['  - source:', '      type: git', f'      url: {entry.repo}', f'      ref: {entry.ref}',
                           f'      path: {folder}components', f'    refresh: {refresh}']
        lines = ['# Written by Tessera. Change plugins in Tessera, not here.']
        if packages:
            lines += ['packages:', *packages, 'external_components:', *components]
        else:
            lines.append('{}')
        return '\n'.join(lines) + '\n'

    def attach_line(self, profile_name):
        return f'packages:\n  tessera_plugins: !include {Path(profile_name).stem}.plugins.yaml'

    # ---- Adding and removing ----

    def fits(self, entry, screen):
        """None when the plugin fits this screen, else the reason (the editor's Misfit words)."""
        manifest = entry.manifest
        if not pm.api_fits(manifest['api']):
            return 'api'
        if manifest['boards'] != 'any' and core.board_of(screen) not in manifest['boards']:
            return 'board'
        # PSRAM: a board that draws camera pictures has it (features/camera.yaml is for PSRAM boards only).
        if manifest['requires']['psram'] and not screen.get('pictures') and not core.SHAPES.get(core.board_of(screen), {}).get('camera'):
            return 'psram'
        if self.blocked(entry):
            return 'blocked'
        return None

    async def apply(self, inbox, body):
        """Add and remove plugins on one screen, write its plugins file and build it. `body`:
        {"add": [{"id", "source": "index"|"folder", "parts": [...], "values": {...}, "secrets": {...}}], "remove": [id]}"""
        if not isinstance(body, dict):
            raise ValueError(t('addon.errors.plugins.request'))
        screen = self.manager.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        inbox = screen['id']
        profile, host = self.manager.updates.resolve(screen)
        adds = body.get('add') or []
        removes = body.get('remove') or []
        if not isinstance(adds, list) or not isinstance(removes, list) or len(adds) > 8 or len(removes) > 8:
            raise ValueError(t('addon.errors.plugins.request'))
        firmware = self.manager.firmware
        self.scan_folders()
        changes = []
        for item in adds:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str):
                raise ValueError(t('addon.errors.plugins.request'))
            source = item.get('source') or ('folder' if item['id'] in self.folders else 'index')
            entry = (self.folders if source == 'folder' else self.links if source in ('link', 'branch') else self.index).get(item['id'])
            if entry is None:
                raise ValueError(t('addon.errors.plugins.unknown', id=item['id']))
            reason = self.fits(entry, screen)
            if reason:
                words = {'api': 'addon.errors.plugins.misfit_api', 'board': 'addon.errors.plugins.misfit_board',
                         'psram': 'addon.errors.plugins.misfit_psram', 'blocked': 'addon.errors.plugins.misfit_blocked'}
                raise ValueError(t(words[reason], name=entry.text('name')))
            for required in entry.manifest['requires']['plugins']:
                if not self.store.get(inbox, required) and not any(a.get('id') == required for a in adds):
                    raise ValueError(t('addon.errors.plugins.requires', name=entry.text('name'), other=required))
            values, secrets = item.get('values') or {}, item.get('secrets') or {}
            if not isinstance(values, dict) or not isinstance(secrets, dict):
                raise ValueError(t('addon.errors.plugins.request'))
            # What this screen has now: an update that leaves an input or its parts out keeps what was filled in when
            # the plugin was added (a calendar, a part that is on), so nothing is lost by updating.
            had = self.store.get(inbox, entry.id)
            kept = {}
            for spec in entry.manifest['inputs']:
                given = secrets.get(spec['id']) if spec['kind'] == 'secret' else values.get(spec['id'])
                if given is not None and (not isinstance(given, str) or len(given) > 256):
                    raise ValueError(t('addon.errors.plugins.request'))
                if spec['kind'] == 'secret':
                    if given:
                        self.secrets.set(entry.id, spec['id'], given, 'all' if spec['scope'] == 'all' else inbox)
                elif given:
                    kept[spec['id']] = given.strip()
                elif given is None and had and (had.get('values') or {}).get(spec['id']):
                    kept[spec['id']] = had['values'][spec['id']]
            known = {x['id'] for x in entry.manifest['parts']}
            asked = item.get('parts')
            parts = [p for p in (asked if isinstance(asked, list) else (had or {}).get('parts') or []) if p in known]
            # An update that asks for more than the person agreed to waits for their yes (the editor asks again).
            agreed = (had or {}).get('consent', {}).get('permissions') if had else None
            if had and agreed and agreed != pm.permission_hash(entry.manifest) and item.get('consent') is not True:
                raise ValueError(t('addon.errors.plugins.consent', name=entry.text('name')))
            if entry.source in ('index', 'link', 'branch'):
                self.keep_snapshot(entry)
            changes.append({'id': entry.id, 'source': entry.source, 'repo': entry.repo, 'path': entry.path,
                            'ref': entry.ref, 'version': entry.version, 'parts': parts, 'values': kept,
                            'consent': {'permissions': pm.permission_hash(entry.manifest), 'at': int(time.time())},
                            'state': 'building' if profile else 'active'})
        for record in changes:
            self.store.put(inbox, record)
        for plugin in removes:
            if isinstance(plugin, str):
                self.store.remove(inbox, plugin)
                if not self.store.in_use(plugin):
                    self.secrets.drop_plugin(plugin)
        self._know_tiles()
        text = self.sidecar(inbox)
        if not profile:
            # A screen built from its own YAML: the app cannot build it, so the page shows the file and the line.
            return {'own_yaml': True, 'file': f'{screen.get("node") or "screen"}.plugins.yaml', 'content': text,
                    'line': self.attach_line(f'{screen.get("node") or "screen"}.yaml')}
        firmware.save_plugins(profile, text)
        if not host:
            return {'written': True, 'built': False}
        # One build at a time, in the order asked: ticking three screens on the Plugins page builds them one after the
        # other. A screen asked again while it waits builds once, with everything asked for it.
        job = self.jobs.get(inbox) if self.jobs.get(inbox, {}).get('state') == 'queued' else None
        added = [c['id'] for c in changes]
        if job:
            job['add'] = sorted(set(job['add']) | set(added))
            job['remove'] = sorted(set(job['remove']) | {r for r in removes if isinstance(r, str)})
        else:
            self.jobs[inbox] = {'add': added, 'remove': [r for r in removes if isinstance(r, str)], 'state': 'queued',
                                'profile': profile, 'host': host, 'asked': int(time.time())}
            self.queue.append(inbox)
        if self.worker is None or self.worker.done():
            self.worker = asyncio.get_running_loop().create_task(self._build_queue())
        self.manager.notify()
        return {'written': True, 'built': True, 'queued': self.queue.index(inbox) if inbox in self.queue else 0}

    async def _build_queue(self):
        """Build the screens that wait, one at a time, each when the app's one build slot is free."""
        firmware = self.manager.firmware
        while self.queue:
            while firmware.task and not firmware.task.done():
                await asyncio.sleep(2)
            inbox = self.queue.pop(0)
            job = self.jobs.get(inbox)
            if not job:
                continue
            job.update(state='building', started=int(time.time()))
            self.manager.notify()
            try:
                firmware.start({'file': job['profile'], 'action': 'install', 'target': job['host']})
                await firmware.task
                ok = (firmware.job or {}).get('state') == 'success'
                reason = None if ok else ((firmware.job or {}).get('error') or 'build')
            except Exception as error:   # refused before it started (a file that went, an address that is wrong)
                ok, reason = False, str(error)[:200]
            for plugin in job['add']:
                if self.store.get(inbox, plugin):
                    self.store.set_state(inbox, plugin, 'active' if ok else 'failed', reason)
            self.jobs.pop(inbox, None)
            self.manager.notify()
            self.manager.ha.changed.set()

    def file_for(self, inbox):
        screen = self.manager.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        profile, _ = self.manager.updates.resolve(screen)
        name = profile or f'{screen.get("node") or "screen"}.yaml'
        return {'file': f'{Path(name).stem}.plugins.yaml', 'content': self.sidecar(screen['id']),
                'line': self.attach_line(name), 'own_yaml': not profile}

    def forget_screen(self, inbox):
        for record in self.store.of(inbox):
            self.store.remove(inbox, record['id'])
            if not self.store.in_use(record['id']):
                self.secrets.drop_plugin(record['id'])

    def set_secret(self, plugin, input_id, value):
        entry = self.known(plugin)
        spec = entry and next((i for i in entry.manifest['inputs'] if i['id'] == input_id and i['kind'] == 'secret'), None)
        if not spec or (value is not None and (not isinstance(value, str) or len(value) > 256)):
            raise ValueError(t('addon.errors.plugins.request'))
        self.secrets.set(plugin, input_id, (value or '').strip())
        self.manager.ha.changed.set()
        return {'set': bool(value)}

    # ---- Data for tiles ----

    def values_of(self, entry, tile, options):
        """A tile's options with the manifest's defaults, plus the plugin's inputs for every screen."""
        chosen = {o['id']: o['default'] for o in tile['options'] if 'default' in o}
        for key, value in (options or {}).items():
            spec = next((o for o in tile['options'] if o['id'] == key), None)
            if spec is None:
                continue
            try:
                chosen[key] = pm.option_value(spec, value)
            except pm.ManifestError:
                continue
        return chosen

    async def tile_data(self, entry, tile, chosen, ask=True):
        """What the screen gets for one tile: the mapped answer of its fetch, with "stale" or "wait"."""
        if not tile.get('data'):
            return None
        fetch = entry.fetch(tile['data'])
        secrets = self.secrets.of(entry.id)
        values = {**{k: str(v) for k, v in chosen.items()}}
        try:
            if ask:
                _, cached = await self.fetcher.get(entry.id, entry.manifest, fetch, values, secrets)
            else:
                cached = self.fetcher.peek(entry.id, fetch, values, secrets)
        except plugin_fetch.FetchRefused as error:
            return {'wait': 'not_filled' if 'not filled' in str(error) else 'refused'}
        if not cached or cached['data'] is None:
            return {'wait': 'failed' if cached and cached['error'] else 'asking'}
        try:
            data = plugin_fetch.apply_map(fetch['map'], cached['data'], values)
        except Exception as error:   # an answer of another shape than the map expects
            LOG.warning('plugin %s: the answer did not fit its map (%s)', entry.id, error)
            return {'wait': 'failed'}
        if cached['stale']:
            data['stale'] = True
        return trimmed(data)

    def entity_part(self, kind, tile):
        """(entity, what the screen gets of it) for a tile that belongs to an entity: its state, its name, the
        attributes its manifest names and the `fields` it takes out of them, bounded as every tile's: a text at 48
        bytes, and the lists together within X_BUDGET, each shortened from the end to the same length only when they
        do not fit (96 prices of a quarter of an hour fit, twice). An attribute named ..._at, ..._time or ...date that
        holds a moment goes as seconds since 1970, so the screen says it in its words."""
        entity = (tile.get('options') or {}).get('plugin_entity')
        if not kind or not kind['domains'] or not entity:
            return None, None
        if entity.split('.')[0] not in kind['domains']:
            return entity, {'wait': 'wrong_entity'}
        state = self.manager.ha.states.get(entity) or {}
        attrs = state.get('attributes') or {}
        bounded = {}
        for name in kind['attributes']:
            value = attrs.get(name)
            if name.endswith(('_at', '_time', 'date')) and isinstance(value, str):
                moment = plugin_fetch.epoch_of(value, getattr(self.manager.ha, 'time_zone', None))
                if moment is not None:
                    bounded[name] = moment
                    continue
            if isinstance(value, bool) or (isinstance(value, (int, float)) and math.isfinite(value)):
                bounded[name] = value
            elif isinstance(value, str):
                bounded[name] = core.short(value, 48)
            elif isinstance(value, list):
                # Texts and numbers; a list of objects reaches the screen through `fields` (raw_today[*].value).
                bounded[name] = [core.short(v, 48) if isinstance(v, str) else v for v in value[:1000]
                                 if isinstance(v, str) or (isinstance(v, (int, float)) and not isinstance(v, bool)
                                                           and math.isfinite(v))]
        zone = getattr(self.manager.ha, 'time_zone', None)
        for name, field in (kind.get('fields') or {}).items():
            bounded[name] = plugin_fetch.field_value(attrs, {**field, 'tz': field.get('tz') or zone})
        part = {'state': core.short(str(state.get('state', 'unavailable')), 160),
                'name': core.short(attrs.get('friendly_name') or entity, 48), 'attributes': bounded}
        for items in LIST_STEPS:
            shaped = {**part, 'attributes': {name: value if not isinstance(value, list) or items is None else value[:items]
                                             for name, value in bounded.items()}}
            if json_size(shaped) <= X_BUDGET:
                return entity, shaped
        return entity, {'wait': 'too_large'}

    async def tile_message(self, index, tile, ask=True):
        """The state message of a plugin tile (core.state_message's shape): no entity behind it, its options, its data."""
        plugin, tile_id = core.plugin_tile(tile['entity'])
        entry = self.known(plugin)
        kind = entry.tile(tile_id) if entry else None
        options = tile.get('options') or {}
        wire = {key: deepcopy(options[key]) for key in ('size', 'background', 'tap') if key in options}
        icon = options.get('icon')
        if icon in tile_icons.ICONS:
            wire['icon'] = tile_icons.ICONS[icon][0]
        elif kind:
            wire['icon'] = glyph(kind['icon'])
        chosen = self.values_of(entry, kind, options.get('plugin')) if kind else dict(options.get('plugin') or {})
        if chosen:
            wire['plugin'] = chosen
        entity, part = self.entity_part(kind, tile)
        if entity:
            wire['pe'] = entity
        name = tile.get('name') or (part or {}).get('name') or (entry.text(kind['name']) if kind else tile_id)
        message = {'v': 1, 'op': 'state', 'i': index, 'entity': tile['entity'], 'name': core.short(name, 80),
                   'state': 'ok', 'a': {}, 'o': wire}
        if kind:
            data = await self.tile_data(entry, kind, chosen, ask)
            if part or data:
                message['x'] = trimmed({**(part or {}), **(data or {})})
        return message

    async def choices(self, plugin, fetch_id, values):
        """The choices of an option with `options_from`, for the editor's inspector: [{value, label}]."""
        entry = self.known(plugin)
        fetch = entry.fetch(fetch_id) if entry else None
        if not fetch or 'value' not in fetch['map']:
            raise ValueError(t('addon.errors.plugins.request'))
        clean = {k: str(v)[:64] for k, v in (values or {}).items() if isinstance(k, str)}
        try:
            _, cached = await self.fetcher.get(entry.id, entry.manifest, fetch, clean, self.secrets.of(entry.id))
        except plugin_fetch.FetchRefused:
            return {'choices': [], 'wait': 'not_filled'}
        if cached['data'] is None:
            return {'choices': [], 'wait': 'failed', 'error': cached['error']}
        return {'choices': plugin_fetch.apply_choices(fetch['map'], cached['data'], clean)}

    async def preview(self, plugin, tile_id, options):
        """What the editor draws for a plugin tile (it cannot run the plugin's C++): the manifest's `preview` filled in
        from the tile's data, for its first items: [{badge, title, value, at}], `at` a moment the editor counts down to."""
        entry = self.known(plugin)
        kind = entry.tile(tile_id) if entry else None
        if not kind or not kind.get('preview'):
            raise ValueError(t('addon.errors.plugins.request'))
        chosen = self.values_of(entry, kind, {k: v for k, v in options.items() if k != 'entity'})
        if kind.get('data'):
            data = await self.tile_data(entry, kind, chosen)
        else:
            _, part = self.entity_part(kind, {'options': {'plugin_entity': options.get('entity')}})
            data = {'items': [{**part['attributes'], 'state': part['state'], 'name': part['name']}]} \
                if part and 'wait' not in part else (part or {'wait': 'no_entity'})
        if not data or 'wait' in data:
            return {'items': [], 'wait': (data or {}).get('wait', 'asking')}
        rows = data.get('items') if isinstance(data.get('items'), list) else [data]
        spec, out = kind['preview'], []
        # A list (a day of prices) is the plugin's to draw: a template leaves it out.
        word = lambda value: '' if value is None or isinstance(value, (list, dict)) else str(value)
        fill = lambda text, row: pm.PLACEHOLDER.sub(lambda m: word(row.get(m.group(1))), text).strip()
        for row in rows[:6]:
            item = {key: fill(spec[key], row) for key in ('badge', 'title', 'value') if key in spec}
            if 'countdown' in spec:
                item['at'] = row.get(spec['countdown'])
            out.append(item)
        return {'items': out, **({'stale': True} if data.get('stale') else {})}

    # ---- A plugin's settings under Screen settings ----

    SETTING_DOMAINS = ('switch', 'number', 'select')

    def _setting_entities(self, screen, entry):
        """{key: entity_id} of a plugin's settings on this screen: entities of its device whose id ends in _<key>."""
        device = (screen or {}).get('device_id')
        registry = getattr(self.manager.ha, 'registry', None) or []
        found = {}
        for setting in entry.manifest['settings']:
            for item in registry:
                eid = item.get('entity_id') if isinstance(item, dict) else None
                if (isinstance(eid, str) and item.get('device_id') == device and eid.split('.')[0] in self.SETTING_DOMAINS
                        and eid.endswith('_' + setting['key'])):
                    found[setting['key']] = eid
        return found

    def settings_for(self, inbox, language='en'):
        """The plugins' settings of one screen, as the editor draws them: [{plugin, name, rows: [{entity, kind, label,
        hint, value, min, max, step, options, available}]}]."""
        screen = self.manager.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        states = getattr(self.manager.ha, 'states', {}) or {}
        out = []
        for record in self.store.of(screen['id']):
            entry = self.entry_for(record)
            if not entry or not entry.manifest['settings']:
                continue
            entities = self._setting_entities(screen, entry)
            rows = []
            for setting in entry.manifest['settings']:
                eid = entities.get(setting['key'])
                state = states.get(eid) or {} if eid else {}
                attrs = state.get('attributes') or {}
                kind = eid.split('.')[0] if eid else None
                value = state.get('state')
                available = bool(eid) and value not in (None, 'unavailable', 'unknown') and screen.get('online')
                row = {'entity': eid, 'kind': kind, 'label': entry.texts.get(setting['label']) or {'en': setting['label']},
                       'hint': entry.texts.get(setting['hint']) if setting['hint'] else None, 'available': bool(available)}
                if kind == 'switch':
                    row['value'] = value == 'on'
                elif kind == 'number':
                    try:
                        row['value'] = float(value)
                    except (TypeError, ValueError):
                        row['value'] = None
                    row.update(min=attrs.get('min'), max=attrs.get('max'), step=attrs.get('step') or 1,
                               unit=attrs.get('unit_of_measurement') or '')
                elif kind == 'select':
                    row.update(value=value, options=[o for o in attrs.get('options') or [] if isinstance(o, str)][:16])
                rows.append(row)
            out.append({'plugin': entry.id, 'name': entry.texts.get('name') or {'en': entry.id}, 'rows': rows})
        return out

    async def set_setting(self, inbox, entity, value):
        """Change one plugin setting of this screen through Home Assistant: only an entity a plugin on the screen names
        in its manifest's `settings`, of that screen's own device."""
        screen = self.manager.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        allowed = {}
        for record in self.store.of(screen['id']):
            entry = self.entry_for(record)
            if entry:
                allowed.update({eid: key for key, eid in self._setting_entities(screen, entry).items()})
        if entity not in allowed:
            raise ValueError(t('addon.errors.plugins.request'))
        domain = entity.split('.')[0]
        if domain == 'switch' and isinstance(value, bool):
            await self.manager.ha.call_service('switch', 'turn_on' if value else 'turn_off', {'entity_id': entity})
        elif domain == 'number' and isinstance(value, (int, float)) and not isinstance(value, bool):
            await self.manager.ha.call_service('number', 'set_value', {'entity_id': entity, 'value': value})
        elif domain == 'select' and isinstance(value, str) and len(value) <= 64:
            await self.manager.ha.call_service('select', 'select_option', {'entity_id': entity, 'option': value})
        else:
            raise ValueError(t('addon.errors.plugins.request'))
        return {'ok': True}

    # ---- A plugin's question (tessera::send) ----

    async def answer(self, request):
        """One question of a plugin on a screen: a Home Assistant command its manifest names, asked on its behalf, the
        answer sent back bounded (op "plugin"). Every command goes into the log with the screen, the plugin and the
        command, never its values."""
        if not isinstance(request, dict):
            return
        inbox = getattr(self.manager, 'aliases', {}).get(request.get('inbox'), request.get('inbox'))
        plugin = request.get('plugin')
        screen = self.manager.screen(inbox) if isinstance(inbox, str) else None
        if not screen or not isinstance(plugin, str) or not self.store.get(inbox, plugin):
            return
        try:
            body = json.loads(request.get('body') or '{}')
        except ValueError:
            return
        if not isinstance(body, dict):
            return
        reply = {'re': body.get('re') if isinstance(body.get('re'), int) else 0}
        entry = self.entry_for(self.store.get(inbox, plugin))
        ask = body.get('ask')
        data = body.get('data') if isinstance(body.get('data'), dict) else {}
        if not entry or not isinstance(ask, str) or ask not in entry.manifest['permissions']['ha_commands']:
            reply.update(ok=False, error='not_allowed')
        else:
            LOG.info('Plugin %s on %s asks Home Assistant: %s', plugin, screen.get('name') or inbox, ask)
            try:
                if ask.startswith('call_service:'):
                    domain, service = ask.split(':', 1)[1].split('.', 1)
                    target = {key: data[key] for key in ('entity_id', 'device_id', 'area_id') if key in data}
                    fields = {key: value for key, value in data.items() if key not in target}
                    result = await self.manager.ha.request('call_service', domain=domain, service=service,
                                                           service_data=fields, target=target, return_response=True)
                    result = (result or {}).get('response', result) if isinstance(result, dict) else result
                else:
                    result = await self.manager.ha.request(ask, **data)
                # An answer the manifest maps (`answers`) goes as its fields, the rest as it came; both bounded.
                spec = next((a for a in entry.manifest.get('answers') or [] if a['command'] == ask), None)
                if spec:
                    zone = getattr(self.manager.ha, 'time_zone', None)
                    result = {name: plugin_fetch.field_value(result, {**field, 'tz': field.get('tz') or zone})
                              for name, field in spec['fields'].items()}
                reply.update(ok=True, result=bounded(result))
            except Exception as error:   # Home Assistant said no, or did not answer
                reply.update(ok=False, error=str(error)[:120] or type(error).__name__)
        action = self.manager.transport(inbox, screen) if hasattr(self.manager, 'transport') else None
        if action:
            await self.manager.send_auxiliary(inbox, {'v': 2, 'op': 'plugin', 'p': plugin, 'm': reply}, action, request)

    def plugin_tiles(self):
        """Every plugin tile on a screen's pages: [(inbox, tile)]."""
        out = []
        for inbox, layout in (getattr(self.manager, 'layouts', None) or {}).items():
            for tile in (layout or {}).get('tiles', []):
                if core.plugin_tile(tile.get('entity')):
                    out.append((inbox, tile))
        return out

    async def refresh_data(self):
        """One round of the fetch loop: ask what is due for every plugin tile on a screen, and send the tiles whose
        answer changed."""
        changed = set()
        for _, tile in self.plugin_tiles():
            plugin, tile_id = core.plugin_tile(tile['entity'])
            entry = self.known(plugin)
            kind = entry.tile(tile_id) if entry else None
            if not kind or not kind.get('data'):
                continue
            chosen = self.values_of(entry, kind, (tile.get('options') or {}).get('plugin'))
            fetch = entry.fetch(kind['data'])
            try:
                before = (self.fetcher.peek(entry.id, fetch, {k: str(v) for k, v in chosen.items()},
                                            self.secrets.of(entry.id)) or {}).get('changed')
                _, cached = await self.fetcher.get(entry.id, entry.manifest, fetch, {k: str(v) for k, v in chosen.items()},
                                                   self.secrets.of(entry.id))
            except plugin_fetch.FetchRefused:
                continue
            if cached['changed'] != before:
                changed.add(tile['entity'])
        self.fetcher.forget_unused()
        if changed:
            self.manager.ha.dirty.update(changed)
            self.manager.ha.changed.set()

    async def loop(self):
        while True:
            try:
                if self.plugin_tiles():
                    await self.refresh_data()
            except Exception as error:   # one plugin's trouble never stops the app
                LOG.warning('Plugin data round failed: %s', error)
            await asyncio.sleep(LOOP_SECONDS)
