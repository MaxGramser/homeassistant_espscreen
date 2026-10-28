"""Plugins in the app (docs/PLUGINS.md): which exist, which each screen runs, the file that builds them into a screen's
firmware, and the data their tiles show.

Where plugins come from:
- **the index**, github.com/MaxGramser/tessera-plugins `index.json`: every plugin with its manifest, its texts and its
  README at the commit of its release. Read when the editor opens and at most every ten minutes, kept in
  /data/plugins/ for when the internet is away.
- **a folder** in Home Assistant's config, `tessera-plugins/<id>/` beside the `esphome/` folder: a plugin someone is
  making. Every build takes what the folder holds now; the app shows it as a test and offers no updates.

The app itself runs no plugin code: it reads the manifest (plugin_manifest.py), writes the screen's plugins file so
ESPHome builds the plugin into that screen, and carries out the plugin's fetches with its own rules (plugin_fetch.py).
ESPHome does run a plugin's Python, its component's `__init__.py`, while it builds the screen, in this app's container
(docs/PLUGINS.md, "Where a plugin's code runs"): the build gets the environment the build tools read and nothing of the
app's own (firmware.build_environment), and the plugins repository holds a listed plugin's Python to what a component
needs (its tools/check.py).
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

import build_cache
import core
import entity_settings
import feedback
import page_delivery
import plugin_fetch
import plugin_likes
import plugin_manifest as pm
import plugin_pictures
import tile_icons
from i18n import t
from plugin_store import PluginSecrets, PluginStore

LOG = logging.getLogger('plugins')

INDEX_URL = 'https://raw.githubusercontent.com/MaxGramser/tessera-plugins/{branch}/index.json'
# How many people like each plugin: the website counts the likes, the plugins repository copies the counts every hour, so
# reading them is a request to GitHub like the index's, never to the website (plugin_likes.py sends a like).
LIKES_URL = 'https://raw.githubusercontent.com/MaxGramser/tessera-plugins/main/likes.json'
# Each plugin's likes, rating (from three ratings), ratings and the homes that use it, copied with the likes.
STATS_URL = 'https://raw.githubusercontent.com/MaxGramser/tessera-plugins/main/stats.json'
LIKES_MAX = 256 * 1024
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
GITHUB_REPOSITORY = 'https://api.github.com/repositories/{id}'
GITHUB_RAW = 'https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}'
FOLDER = 'tessera-plugins'
# A plugin's picture on the Plugins page: store.png beside its manifest, made with the plugins repository's
# tools/store_image.py or by hand (its docs/PUBLISHING.md). The app fetches it at the plugin's commit and serves it to
# the editor itself, as the editor shows no picture from another address.
STORE_IMAGE = 'store.png'
STORE_IMAGE_MAX = 1024 * 1024
STORE_IMAGE_SIZE = (2560, 1440)   # the largest it takes; the tool makes 1280 x 720
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
PLUGIN_ICON = 'F0A66'         # puzzle-outline, for a plugin whose icon is not in Tessera's set
X_BUDGET = 2600               # bytes of a tile's data on the wire: the message carries more and stays under 4 KB
# What a tile's message holds besides its own fields on the way (session, sequence, revision, slot, the "x" key): its
# data gets what is left of the 4 KB after the message and this, at most X_BUDGET (0.12: a tile's options take up to
# pm.OPTIONS_BYTES of it).
ENVELOPE = 128
# How long the answer to what a person typed in a searched list stays (0.12): the next search asks again anyway.
SEARCH_EVERY = 600
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


def origin_of(repo, path='.'):
    """Where a plugin comes from as one text to compare: github.com/<owner>/<repo>, and /<folder> for one in a folder of
    its repository. Lowercase, without .git or a trailing slash, so one repository linked two ways is one origin. A plugin
    is known by its id (it lives in the firmware, the layouts and the secrets); its origin says which plugin of that id."""
    match = GITHUB_LINK.match(str(repo or '').strip())
    if not match:
        return str(repo or '').strip().lower().rstrip('/')
    folder = str(path or '.').strip('/')
    return f'github.com/{match.group(1).lower()}/{match.group(2).lower()}' + ('' if folder in ('', '.') else f'/{folder}')


def record_origin(record):
    """The origin of a plugin on a screen, from its record."""
    return 'folder' if record.get('source') == 'folder' else origin_of(record.get('repo'), record.get('path'))


def build_reason(logs):
    """Why a build failed, in one line of its log. The app's own last line says it in words (memory that ran short, a
    screen that did not answer); only when that line points to the log, the last error the compiler or ESPHome named.
    The whole log stays under Firmware & USB until the next build."""
    lines = [str(line).strip() for line in list(logs or [])[-60:] if str(line).strip()]
    if not lines:
        return 'build'
    if 'see the log' not in lines[-1]:
        return lines[-1][:200]
    errors = [line for line in lines if re.search(r'\berror\b|ERROR', line) and 'see the log' not in line]
    return (errors or lines)[-1][:200]


# A compiler error in a file of an external component: `../src/esphome/components/tap_sound/tap_sound.h:19:8: error: ...`.
COMPONENT_ERROR = re.compile(r'components/([a-z0-9_]+)/[^\s:]+:\d+(?::\d+)?:\s*(?:fatal\s+)?error:')
# A plugin the core refused while ESPHome read the configuration, before any compiler ran (smart_display.register_plugin):
# `Plugin tap_sound wants plugin API 0.11; this firmware offers 0.10.` or `Plugin tap_sound was written for plugin API ...`.
API_REFUSAL = re.compile(r'Plugin ([a-z0-9_]+) (?:wants|was written for) plugin API')


def failed_components(logs):
    """The components a build's compiler errors lie in, and the plugins the core refused by their API, Tessera's own
    components left out."""
    lines = [str(line) for line in logs or []]
    found = {match.group(1) for line in lines for match in [COMPONENT_ERROR.search(line)] if match}
    found |= {match.group(1) for line in lines for match in [API_REFUSAL.search(line)] if match}
    return found - {'smart_display', 'flash_layout'}


# After a build went on, the screen reboots and says hello again within this many seconds; until then whether it runs
# the plugins just built is not known.
SETTLING = 180


def runs(inbox, record, running, now=None):
    """Whether the screen of `inbox` runs the installed plugin `record` at its version, by the screen's last hello
    (`running`, Plugins.running()): True or False, or None while it cannot be known: the screen has not said (offline,
    or a firmware from before plugins), the record is not active (building, failed), or its build went on a moment ago
    and the screen has not said hello since. False is a plugin that crashed at boot or a firmware built without it."""
    reported = running.get(inbox)
    if reported is None or record.get('state', 'active') != 'active':
        return None
    if (now if now is not None else time.time()) - (record.get('settled') or 0) < SETTLING:
        return None
    return any(item.get('id') == record['id'] and item.get('version') == record.get('version') for item in reported)


def version_tuple(text):
    return tuple(int(n) for n in re.findall(r'\d+', str(text or ''))[:3])


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


def plugin_entities(entries, states, most=500):
    """The entities of every domain a plugin names (a tile's `entity`, an input of kind entity, a screensaver step of
    an entity, an entity option of a tile) that the editor's own list lacks, for its pickers and its check of tiles whose entity is gone: that list
    has the domains Tessera draws tiles for and the top bar's (core.discover), and a plugin may add one it does not (a
    plant, GitHub #262). Those the editor has stay out, so the `most` here go to the plugins' own domains alone."""
    entries = list(entries)
    domains = {d for entry in entries for tile in entry.manifest['tiles'] for d in tile['domains']}
    domains |= {d for entry in entries for item in entry.manifest['inputs'] for d in item['domains']}
    domains |= {d for entry in entries for saver in entry.manifest.get('savers', []) for d in saver.get('domains', [])}
    domains |= {d for entry in entries for tile in entry.manifest['tiles'] for option in tile.get('options', [])
                if option.get('kind') == 'entity' for d in option.get('domains', [])}
    domains -= core.DOMAINS | core.HEADER_ONLY_DOMAINS
    return sorted(({'id': eid, 'name': (state.get('attributes') or {}).get('friendly_name') or eid}
                   for eid, state in states.items() if isinstance(eid, str) and eid.split('.')[0] in domains),
                  key=lambda e: e['name'].lower())[:most]


def trimmed(data, budget=X_BUDGET):
    """A tile's data within `budget` bytes (X_BUDGET, or less beside large options): the last items go first."""
    if not isinstance(data, dict):
        return data
    data = dict(data)
    while len(json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode()) > budget:
        items = data.get('items')
        if not isinstance(items, list) or not items:
            return {'wait': 'too_large'}
        data['items'] = items[:-1]
    return data


def store_image_ok(body):
    """Whether `body` is a PNG the Plugins page takes: the signature, a header Pillow reads, and at most STORE_IMAGE_SIZE.
    Only the header is read, so a picture that claims an enormous size is refused before anything is decoded."""
    if not body or len(body) > STORE_IMAGE_MAX or not body.startswith(PNG_SIGNATURE):
        return False
    try:
        from io import BytesIO
        from PIL import Image
        with Image.open(BytesIO(body)) as image:
            width, height = image.size
            return image.format == 'PNG' and 0 < width <= STORE_IMAGE_SIZE[0] and 0 < height <= STORE_IMAGE_SIZE[1]
    except Exception:
        return False


class Entry:
    """One plugin the app knows, from the index, a snapshot of an installed release, or a folder."""

    def __init__(self, raw, translations, readme, source, label, repo=None, path='.', ref=None, folder=None, status='ok',
                 repo_id=None, branch=None, date=None, changelog=None, image=None):
        self.raw, self.translations, self.readme = raw, translations, readme
        # STORE_IMAGE when the plugin has a picture for the Plugins page, else None.
        self.image = STORE_IMAGE if image == STORE_IMAGE else None
        self.source, self.label, self.repo, self.path, self.ref = source, label, repo, path or '.', ref
        self.folder, self.status = folder, status
        # GitHub's number of the repository (it follows a rename, and a new repository under an old name has another),
        # the branch a test follows (ref is then the commit it was pinned to), and the day of the release.
        self.repo_id, self.branch, self.date = repo_id, branch, date
        # Its CHANGELOG.md per language: a `## <version>` heading per release, newest first. The editor shows the lines
        # between the version a screen runs and the one on offer.
        self.changelog = changelog or {}
        # A folder someone is making is checked strictly (they hear about a topic this app does not know); the index and
        # a link are read leniently, so a newer plugins repository never hides a plugin.
        self.manifest = pm.check(raw, translations.get('en'), strict=source == 'folder')
        self.origin = 'folder' if source == 'folder' else origin_of(repo, path)
        self.id, self.version = self.manifest['id'], self.manifest['version']
        self.texts = pm.texts(self.manifest, translations)

    def text(self, key, language='en'):
        words = self.texts.get(key) or {}
        return words.get(language) or words.get(language.split('-')[0]) or words.get('en') or key

    def tile(self, tile_id):
        return next((tile for tile in self.manifest['tiles'] if tile['id'] == tile_id), None)

    def fetch(self, fetch_id):
        return next((fetch for fetch in self.manifest['fetch'] if fetch['id'] == fetch_id), None)

    def card(self, card_id):
        return next((card for card in self.manifest['cards'] if card['id'] == card_id), None)

    def saver(self, saver_id):
        return next((saver for saver in self.manifest.get('savers') or () if saver['id'] == saver_id), None)

    def link(self):
        """The plugin's folder on GitHub, at its commit."""
        if not self.repo:
            return ''
        base = self.repo.rstrip('/').removesuffix('.git')
        return base if self.path in ('', '.') else f'{base}/tree/{self.ref or "main"}/{self.path}'

    def snapshot(self):
        return {'raw': self.raw, 'translations': self.translations, 'readme': self.readme, 'source': self.source,
                'label': self.label, 'repo': self.repo, 'path': self.path, 'ref': self.ref, 'repo_id': self.repo_id,
                'branch': self.branch, 'date': self.date, 'changelog': self.changelog, 'image': self.image}


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
    readme, changelog = {}, {}
    for name, into in (('README', readme), ('CHANGELOG', changelog)):
        for path in sorted(folder.glob(f'{name}*.md')):
            language = path.stem.split('.', 1)[1] if '.' in path.stem else 'en'
            into[language] = path.read_text(encoding='utf-8')[:64 * 1024]
    return Entry(raw, translations, readme, 'folder', 'test', folder=folder, changelog=changelog,
                 image=STORE_IMAGE if (folder / STORE_IMAGE).is_file() else None)


class Plugins:
    def __init__(self, manager, data_dir, config_dir, session_factory=None):
        self.manager = manager
        self.data = Path(data_dir) / 'plugins'
        self.config = Path(config_dir)
        self.store = PluginStore(Path(data_dir) / 'plugins.json')
        self.secrets = PluginSecrets(Path(data_dir) / 'plugin_secrets.json')
        installed = {}
        for records in self.store.everywhere().values():
            for record in records:
                installed.setdefault(record['id'], set()).add(record_origin(record))
        self.secrets.adopt(installed)
        self.liker = plugin_likes.Likes(Path(data_dir) / 'plugin_likes.json')
        self.fetcher = plugin_fetch.Fetcher(f'Tessera/{core.FIRMWARE_VERSION} (+plugins)', session_factory)
        # The pictures of plugin tiles (plugin API 0.10), through the fetcher's session, or Home Assistant's own.
        self.pictures = plugin_pictures.Pictures(self.fetcher, lambda path: self.manager.ha.entity_picture(path))
        self.index = {}             # id -> Entry, from index.json
        self.index_state = {'at': None, 'error': None, 'etag': None, 'branch': None, 'checked': 0.0, 'blocked': [],
                            'featured': []}
        # likes.json: how many like each plugin; `fresh`: the website's own answer to a like from this app, which counts
        # until likes.json has caught up (it is copied once an hour).
        self.likes = {'counts': {}, 'etag': None, 'checked': 0.0, 'fresh': {}}
        # stats.json: per plugin its likes, rating, ratings and homes; `fresh` as for likes, from this app's own rating.
        self.stats = {'numbers': {}, 'etag': None, 'fresh': {}}
        self.folders = {}           # id -> Entry, from tessera-plugins/<id>/
        self.folder_errors = {}     # folder name -> what is wrong with it
        self.snapshots = {}         # (id, ref) -> Entry of an installed release
        self.links = {}             # id -> Entry added with a link (a release of any repository, or a branch to test)
        self.links_checked = 0.0    # when refresh_links last asked for the linked repositories' newest releases
        self.saver_cache = {}       # (inbox, key) -> the fetch's answer for a plugin's step of the screensaver (0.14)
        self.http = None            # the session that reads the index: never the one that holds Home Assistant's token
        self.ready = False
        self._load_cached_index()
        self.scan_folders()
        self.ready = True

    # ---- What exists ----

    def _index_file(self):
        return self.data / 'index.json'

    def _load_cached_index(self):
        try:
            cached = json.loads(self._index_file().read_text())
        except (OSError, ValueError):
            return
        self._take_index(cached.get('index') or {}, cached.get('etag'), cached.get('at'))
        self.index_state['branch'] = cached.get('branch')

    def _take_index(self, index, etag=None, at=None):
        if not isinstance(index, dict) or index.get('format') != INDEX_FORMAT:
            self.index_state['error'] = 'format'
            return
        entries = {}
        for item in index.get('plugins') or []:
            try:
                repo = str(item.get('repo') or '')
                label = 'tessera' if item.get('label') == 'tessera' and repo.lower().startswith(TESSERA_OWNER.lower()) else 'community'
                release = item.get('release') or {}
                entry = Entry(item['manifest'], item.get('translations') or {}, item.get('readme') or {}, 'index', label,
                              repo=repo, path=item.get('path') or '.', ref=release.get('sha'), status=item.get('status', 'ok'),
                              repo_id=item.get('repo_id'), date=release.get('date'),
                              changelog=item.get('changelog') if isinstance(item.get('changelog'), dict) else None,
                              image=item.get('image'))
            except (pm.ManifestError, KeyError, TypeError, ValueError) as error:
                LOG.warning('Index plugin %s skipped: %s', (item or {}).get('id') if isinstance(item, dict) else '?', error)
                continue
            entries[entry.id] = entry
        self.index = entries
        blocked = [b for b in index.get('blocked') or [] if isinstance(b, dict)]
        newly = blocked != self.index_state['blocked']
        self.index_state.update(at=at, etag=etag, error=None, blocked=blocked,
                                featured=[i for i in index.get('featured') or [] if isinstance(i, str) and i in entries])
        self._know_tiles()
        if newly:
            self.drop_blocked()

    @staticmethod
    def index_branches():
        """The branches of the plugins repository whose index.json this app reads, the first that has one. The plugins
        repository has a dev branch as Tessera has (its AGENTS.md, "Branches"): a plugin that needs what only Tessera's
        dev firmware has waits there for Tessera's next release. The dev app reads it, so such a plugin is installed and
        updated the way every plugin is; it falls back on main while dev has no index. Every other app reads main."""
        return ('dev', 'main') if core.channel() == 'dev' else ('main',)

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
            index = None
            for branch in self.index_branches():
                same = self.index_state.get('branch') == branch
                headers = {'If-None-Match': self.index_state['etag']} if self.index_state['etag'] and same and not force else {}
                async with self.http.get(INDEX_URL.format(branch=branch), headers=headers) as response:
                    if response.status == 304:
                        return
                    if response.status == 404 and branch != self.index_branches()[-1]:
                        continue
                    response.raise_for_status()
                    index = json.loads(await read_whole(response, INDEX_MAX))
                    etag = response.headers.get('ETag')
                    self.index_state['branch'] = branch
                    break
        except Exception as error:
            self.index_state['error'] = type(error).__name__
            LOG.info('Plugin index not read (%s)', error)
            return
        at = time.time()
        self._take_index(index, etag, at)
        try:
            self.data.mkdir(parents=True, exist_ok=True)
            self._index_file().write_text(json.dumps({'index': index, 'etag': etag, 'at': at,
                                                      'branch': self.index_state['branch']}))
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
                                            data['label'], repo=data.get('repo'), path=data.get('path'), ref=data.get('ref'),
                                            repo_id=data.get('repo_id'), branch=data.get('branch'), date=data.get('date'),
                                            changelog=data.get('changelog'), image=data.get('image'))
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
        # Pinned to the commit it was built from, as every source but a folder: its snapshot, or the link or index entry
        # of that same commit. A release just read from a link has no snapshot until apply() has written the plugins
        # file, and is in no index, so the link stands in (#260).
        ref = record.get('ref')
        found = self.snapshot_of(record['id'], ref)
        if not found and record.get('source') in ('link', 'branch'):
            link = self.links.get(record['id'])
            found = link if link and link.ref == ref else None
        if not found and record.get('source') != 'branch':
            index = self.index.get(record['id'])
            found = index if index and index.ref == ref else None
        return found

    def secret_values(self, entry, inbox=None):
        """The secrets a fetch of this plugin may carry: filled in for its own origin (a folder someone is making in
        their own config folder may use any), for this screen where one is set for it."""
        return self.secrets.of(entry.id, inbox, None if entry.source == 'folder' else entry.origin)

    def known(self, plugin, inbox=None):
        """The manifest of this plugin: the one this screen runs when `inbox` is given, else any on a screen, then a
        folder, then the index. Two screens may run two plugins of one id (a fork, a folder being made); a tile asks with
        its screen, so it gets its own plugin's fetch, options and secrets."""
        record = self.store.get(inbox, plugin) if inbox else None
        entry = self.entry_for(record) if record else None
        if entry:
            return entry
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

    def blocked_record(self, record):
        """Why the plugin a screen runs is blocked, or None."""
        for item in self.index_state['blocked']:
            if item.get('plugin') == record.get('id') and (record.get('version') in (item.get('versions') or []) or
                                                           (record.get('ref') and record.get('ref') == item.get('sha'))):
                return str(item.get('reason') or 'blocked')
        return None

    def drop_blocked(self):
        """A release the index blocks leaves the firmware of every screen that runs it at that screen's next build: its
        plugins file is written again without it, whatever starts the build (an update, ESPHome's Device Builder). The
        editor says why and offers the newer release."""
        if not self.ready:
            return
        for inbox, records in self.store.everywhere().items():
            if any(self.blocked_record(record) for record in records):
                LOG.warning('A plugin on screen %s is blocked: it leaves the next build', inbox)
                self.rewrite_sidecar(inbox)

    def rewrite_sidecar(self, inbox):
        """Write a screen's plugins file again from its records, without building."""
        try:
            screen = self.manager.screen(inbox)
            profile = self.manager.updates.resolve(screen)[0] if screen else None
            if profile:
                self.manager.firmware.save_plugins(profile, self.sidecar(inbox))
        except Exception as error:   # the next apply writes it anyway
            LOG.warning('Plugins file of %s not written again: %s', inbox, error)

    # ---- Likes ----

    def like_count(self, plugin):
        count = int(self.likes['counts'].get(plugin) or 0)
        fresh = self.likes['fresh'].get(plugin)
        if fresh and time.monotonic() - fresh[1] < 2 * 3600 and fresh[0] != count:
            return fresh[0]
        return count

    def numbers(self, plugin):
        """A plugin's rating (None below three ratings), ratings and homes from stats.json, or this app's own rating's
        answer until stats.json has caught up."""
        found = self.stats['numbers'].get(plugin) or {}
        numbers = {'rating': found.get('rating'), 'ratings': int(found.get('ratings') or 0), 'homes': int(found.get('homes') or 0)}
        fresh = self.stats['fresh'].get(plugin)
        if fresh and time.monotonic() - fresh[1] < 2 * 3600 and fresh[0]['ratings'] != numbers['ratings']:
            numbers.update(rating=fresh[0]['rating'], ratings=fresh[0]['ratings'])
        return numbers

    async def _read_repository_file(self, url, kept):
        """A JSON file of the plugins repository (likes.json, stats.json) with its ETag: the data, or None when it did
        not change or could not be read."""
        import aiohttp
        try:
            if self.http is None or self.http.closed:
                self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15),
                                                  headers={'User-Agent': self.fetcher.user_agent})
            headers = {'If-None-Match': kept['etag']} if kept['etag'] else {}
            async with self.http.get(url, headers=headers) as response:
                if response.status == 304:
                    return None
                response.raise_for_status()
                data = json.loads(await read_whole(response, LIKES_MAX))
                kept['etag'] = response.headers.get('ETag')
                return data
        except Exception as error:
            LOG.info('Plugin %s not read (%s)', url.rsplit('/', 1)[-1], error)
            return None

    async def refresh_likes(self):
        """likes.json and stats.json from the plugins repository, with the index, at most every INDEX_TTL."""
        if time.monotonic() - self.likes['checked'] < INDEX_TTL and self.likes['checked']:
            return
        self.likes['checked'] = time.monotonic()
        data = await self._read_repository_file(LIKES_URL, self.likes)
        counts = (data or {}).get('likes') if isinstance(data, dict) and data.get('format') == 1 else None
        if isinstance(counts, dict):
            self.likes['counts'] = {k: v for k, v in counts.items() if isinstance(k, str) and isinstance(v, int) and v >= 0}
        data = await self._read_repository_file(STATS_URL, self.stats)
        found = (data or {}).get('plugins') if isinstance(data, dict) and data.get('format') == 1 else None
        if isinstance(found, dict):
            count = lambda value: isinstance(value, int) and not isinstance(value, bool) and value >= 0
            self.stats['numbers'] = {
                plugin: {'rating': value['rating'] if isinstance(value.get('rating'), (int, float))
                         and not isinstance(value.get('rating'), bool) else None,
                         'ratings': value['ratings'] if count(value.get('ratings')) else 0,
                         'homes': value['homes'] if count(value.get('homes')) else 0}
                for plugin, value in found.items() if isinstance(plugin, str) and isinstance(value, dict)}

    def _index_records(self, plugin=None):
        """{inbox: [record]} of the plugins of the index this app's screens have from the index's own origin (one from
        a link, a branch or a folder is not the plugin others count), active: what a rating and counting speak of."""
        out = {}
        for inbox, records in self.store.everywhere().items():
            for record in records:
                entry = self.index.get(record['id'])
                if (plugin is None or record['id'] == plugin) and entry and record_origin(record) == entry.origin \
                        and record.get('state', 'active') == 'active':
                    out.setdefault(inbox, []).append(record)
        return out

    async def like(self, plugin, like, consent=False):
        """Like a plugin of the index, also one that runs on none of this app's screens, or take the like back
        (plugin_likes.py). Only a plugin of the index: one from a link or a folder is not the plugin others count."""
        if not self.index.get(plugin) and like:
            raise ValueError(t('addon.errors.plugins.like_not_listed'))
        try:
            result = await self.liker.send(plugin, like, consent)
        except ValueError as error:
            texts = {'like_consent': lambda: t('addon.errors.plugins.like_consent'),
                     'like_off': lambda: t('addon.errors.plugins.like_off'),
                     'request': lambda: t('addon.errors.plugins.request')}
            raise ValueError(texts.get(str(error), lambda: t('addon.errors.plugins.like_failed'))()) from None
        if result['likes'] is not None:
            self.likes['fresh'][plugin] = (result['likes'], time.monotonic())
        return {'liked': result['liked'], 'likes': self.like_count(plugin)}

    # ---- Ratings and counting (plugin_likes.py) ----

    def _board(self, inbox):
        screen = next((s for s in self.screens() if s.get('id') == inbox), None)
        board = core.board_of(screen) if screen else None
        return board if board in core.SHAPES else None

    async def rate(self, plugin, stars, inbox=None):
        """Rate a plugin of the index that runs on one of this app's screens (`inbox` names the screen whose model goes
        along, else the first that has it), or take the rating back (stars None)."""
        places = self._index_records(plugin)
        if stars is not None and not places:
            raise ValueError(t('addon.errors.plugins.rate_not_installed'))
        inbox = inbox if inbox in places else next(iter(places), None)
        record = next(iter(places.get(inbox) or []), {})
        try:
            result = await self.liker.rate(plugin, stars, record.get('version'), self._board(inbox) if inbox else None)
        except ValueError as error:
            texts = {'rate_off': 'addon.errors.plugins.like_off', 'request': 'addon.errors.plugins.request'}
            raise ValueError(t(texts.get(str(error), 'addon.errors.plugins.rate_failed'))) from None
        if result['ratings'] is not None:
            self.stats['fresh'][plugin] = ({'rating': result['rating'], 'ratings': result['ratings']}, time.monotonic())
        return {'stars': result['stars'], **self.numbers(plugin)}

    def ask_card(self, screen):
        """The card above a screen that asks for a plugin's stars (docs/PLUGINS.md, "Likes, ratings and counting"), or
        None: a plugin of the index this screen has run ASK_AFTER, not yet rated, the cards not told to stop."""
        inbox = screen.get('id')
        records = {r['id']: r for r in self._index_records().get(inbox, [])}
        reported = {item.get('id') for item in self.running().get(inbox) or []}
        self.liker.saw(inbox, sorted(set(records) & reported))
        found = self.liker.ask_for(inbox, sorted(records))
        if not found:
            return None
        plugin, days = found
        entry = self.index[plugin]
        words = lambda key: dict(entry.texts.get(key) or {'en': key})
        return {'plugin': plugin, 'name': words('name'), 'version': records[plugin].get('version'), 'days': days,
                'maintainer': entry.manifest['maintainer'], 'tessera': entry.label == 'tessera',
                # Where a problem with it goes: its repository's issues on GitHub, opened and posted by the person.
                'issues': f"{entry.repo.rstrip('/').removesuffix('.git')}/issues/new"
                if str(entry.repo or '').startswith('https://github.com/') else None,
                'image': self.image_url(entry), 'board': self._board(inbox),
                'ask_counting': not self.liker.view()['counting_asked'], 'privacy': feedback.PRIVACY_URL}

    def card_answer(self, plugin, action):
        """Later (this plugin, again after a while) or never (no plugin's card again) on the stars card."""
        if action == 'later' and plugin_likes.ID.match(str(plugin or '')):
            self.liker.later(plugin)
        elif action == 'never':
            self.liker.never()
        elif action == 'ask':
            self.liker.never(asking=True)
        elif action == 'asked_counting':
            self.liker.asked_counting()
        else:
            raise ValueError(t('addon.errors.plugins.request'))
        return self.liker.view()

    async def set_counting(self, on):
        try:
            await self.liker.set_counting(on)
        except ValueError as error:
            raise ValueError(t('addon.errors.plugins.count_failed' if str(error) == 'count_failed'
                               else 'addon.errors.plugins.like_off')) from None
        if on:
            await self.count_tick()
        return self.liker.view()

    def usage(self):
        """What counting says: each plugin of the index this app's screens run, its version and the screen models."""
        found = {}
        for inbox, records in self._index_records().items():
            board = self._board(inbox)
            for record in records:
                item = found.setdefault(record['id'], {'id': record['id'], 'version': record.get('version') or None, 'boards': []})
                if board and board not in item['boards']:
                    item['boards'].append(board)
        return [{**item, 'boards': sorted(item['boards'])} for _, item in sorted(found.items())]

    async def count_tick(self):
        """Counting's turn: send what the screens run when a day has passed or it changed (plugin_likes.usage_due)."""
        plugins = self.usage()
        if self.liker.usage_due(plugins):
            if await self.liker.send_usage(plugins):
                LOG.info('Plugins counted at Tessera: %d', len(plugins))

    async def counting(self):
        """The app's counting loop: a look every minute, a request only when count_tick says so."""
        while True:
            await asyncio.sleep(60)
            try:
                await self.count_tick()
            except Exception as error:   # the next minute tries again
                LOG.info('Plugin counting skipped (%s)', error)

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
        """A plugin from a link, read before anything is built: the newest release of a GitHub repository, or a branch to
        test, each pinned to the commit it was read at (what is built is what the editor showed; a newer commit is an
        update), or a folder in tessera-plugins/. The editor then shows its details like any plugin's. `path`: the plugin's folder in the repository, for a link without
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
        # The repository as GitHub knows it now: its number, which follows a rename and differs for a new repository that
        # took an old name, and its name as GitHub writes it (a link to a renamed repository still finds it).
        info = await self._github(api)
        repo_id = info.get('id') if isinstance(info, dict) and isinstance(info.get('id'), int) else None
        full_name = str(info.get('full_name') or '') if isinstance(info, dict) else ''
        if re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', full_name):
            owner, repo = full_name.split('/')
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
                sha = (await self._github(f'{api}/commits/{tag}'))['sha']
            except ValueError:
                # No release: the simplest way to try a plugin is to push it. The link's branch, else the repository's
                # default branch, becomes a test pinned to its newest commit; a newer push is offered as an update.
                wanted = tree_ref or (info.get('default_branch') if isinstance(info, dict) else None)
                if not wanted or not re.fullmatch(r'[A-Za-z0-9_./-]{1,100}', wanted):
                    raise
                sha = (await self._github(f'{api}/commits/{wanted}'))['sha']
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
        readme, changelog, image = {}, {}, None
        files = await self._github(f'{api}/contents/{path if path != "." else ""}?ref={sha}')
        for item in files if isinstance(files, list) else []:
            name = item.get('name', '')
            if name == STORE_IMAGE and isinstance(item.get('size'), int) and item['size'] <= STORE_IMAGE_MAX:
                image = STORE_IMAGE
            found = re.fullmatch(r'(README|CHANGELOG)(?:\.([a-z]{2}(?:-[A-Za-z]{2})?))?\.md', name)
            if found:
                into = readme if found.group(1) == 'README' else changelog
                into[found.group(2) or 'en'] = (await self._github(raw(name), text=True))[:64 * 1024]
        repo_url = f'https://github.com/{owner}/{repo}'
        label = 'test' if wanted else ('tessera' if repo_url.lower().startswith(TESSERA_OWNER.lower()) else 'community')
        try:
            entry = Entry(manifest, translations, readme, 'branch' if wanted else 'link', label, repo=repo_url, path=path,
                          ref=sha, repo_id=repo_id, branch=wanted, changelog=changelog, image=image)
        except pm.ManifestError as error:
            raise ValueError(t('addon.errors.plugins.manifest', why=str(error)[:200]))
        self.links[entry.id] = entry
        self._know_tiles()
        return entry

    def forget_link(self, plugin):
        """Take a plugin someone added with a link (a release or a branch) off the Plugins page again. Only one that
        runs on no screen: one a screen runs is taken off the screen first, which is what keeps its commit pinned."""
        if plugin not in self.links:
            raise ValueError(t('addon.errors.plugins.unknown', id=plugin))
        if any(record['id'] == plugin for records in self.store.everywhere().values() for record in records):
            raise ValueError(t('addon.errors.plugins.forget_running'))
        del self.links[plugin]
        self._know_tiles()

    async def refresh_links(self, force=False):
        """A plugin added with a link follows its repository: its newest release (a link) or the newest commit of its
        branch (a test) is asked for at most every LINK_TTL, and the editor offers it as an update. The repository is
        found again by its number, so a rename is followed and a new repository that took the old name is never built.
        Nothing goes through Tessera: the maker publishes, the app sees it."""
        if not force and time.monotonic() - self.links_checked < LINK_TTL:
            return
        self.links_checked = time.monotonic()
        seen = set()
        for inbox, records in self.store.everywhere().items():
            for record in records:
                if record.get('source') not in ('link', 'branch'):
                    continue
                entry = self.entry_for(record) or self.links.get(record['id'])
                if not entry or not entry.repo or not GITHUB_LINK.match(entry.repo):
                    continue
                try:
                    repo = entry.repo
                    if entry.repo_id:
                        info = await self._github(GITHUB_REPOSITORY.format(id=int(entry.repo_id)))
                        moved = f'https://github.com/{info["full_name"]}'
                        if GITHUB_LINK.match(moved) and origin_of(moved) != origin_of(repo):
                            LOG.info('Plugin %s: its repository is now %s', record['id'], moved)
                            repo = moved
                            self.store.put(inbox, {**record, 'repo': moved})
                            self.rewrite_sidecar(inbox)
                    branch = record.get('branch')
                    key = (record['id'], origin_of(repo, entry.path), branch)
                    if key in seen:
                        continue
                    seen.add(key)
                    owner, name = GITHUB_LINK.match(repo).groups()[:2]
                    api = GITHUB_API.format(owner=owner, repo=name)
                    if record.get('source') == 'branch' and branch:
                        newest = (await self._github(f'{api}/commits/{branch}'))['sha']
                    else:
                        tag = (await self._github(f'{api}/releases/latest'))['tag_name']
                        newest = (await self._github(f'{api}/commits/{tag}'))['sha']
                    if newest != entry.ref or entry.repo != repo:
                        await self.resolve_link(repo, branch=branch if record.get('source') == 'branch' else None,
                                                path=entry.path)   # newer: read it whole
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
        return {
            'id': entry.id, 'name': words('name'), 'summary': words('summary'),
            'icon': glyph(manifest['icon']), 'maintainer': manifest['maintainer'], 'tessera': entry.label == 'tessera',
            'version': entry.version, 'repo': entry.link(), 'ref': entry.ref, 'license': manifest['license'],
            # Which plugin of this id (an origin, docs/PLUGINS.md "Which plugin"), the branch a test follows, the day of
            # its release.
            'origin': entry.origin, 'branch': entry.branch, 'date': entry.date,
            # What it adds (read from the manifest), what it is about (the maker's word), and how it is liked.
            'type': pm.plugin_type(manifest), 'topics': manifest['topics'],
            'featured': entry.id in self.index_state['featured'] and entry.source == 'index',
            'likes': self.like_count(entry.id), 'liked': self.liker.liked(entry.id),
            # Its rating (None below three), ratings and homes (stats.json), and this app's own stars for it.
            **(self.numbers(entry.id) if entry.source == 'index' else {}),
            'stars': self.liker.stars(entry.id) if entry.source == 'index' else None,
            'stage': manifest['stage'], 'boards': manifest['boards'],
            'board_names': None if manifest['boards'] == 'any' else [board_name(key) for key in manifest['boards']],
            'requires': {'psram': manifest['requires']['psram'], 'plugins': manifest['requires']['plugins'],
                         'features': manifest['requires']['features'], **({'esphome': manifest['requires']['esphome']}
                                                                          if manifest['requires'].get('esphome') else {})},
            'provides': manifest['provides'], 'flash_kb': manifest['flash_kb'],
            'permissions': {'home_assistant': manifest['permissions']['home_assistant_actions'] + manifest['permissions']['ha_commands'],
                            'network': manifest['permissions']['network'],
                            'read_entities': manifest['permissions']['read_entities']},
            'privacy': manifest.get('privacy'), 'readme': entry.readme, 'changelog': entry.changelog,
            # Its picture for the Plugins page, through the app (store_image), named after its commit so a browser keeps
            # it until the plugin changes.
            'image': self.image_url(entry),
            'languages': pm.complete_languages(manifest, entry.translations),
            'inputs': [{'id': i['id'], 'kind': i['kind'], 'scope': i['scope'], 'label': words(i['label']),
                        'hint': words(i['hint']), 'domains': i['domains']} for i in manifest['inputs']],
            'parts': [{'id': p['id'], 'label': words(p['label']), 'hint': words(p['hint']) or {'en': ''},
                       'flash_kb': p['flash_kb'], 'default': p['default'], 'features': p['features']}
                      for p in manifest['parts']],
            'attributes': manifest['attributes'],
            'tiles': [{'id': tile['id'], 'name': words(tile['name']), 'icon': glyph(tile['icon']),
                       'min': tile['min'], 'max': tile['max'], 'memory': tile['memory'],
                       'domains': tile['domains'], 'data': tile.get('data'),
                       # The entities the inspector offers when the tile needs certain attributes (`has_attributes`).
                       **({'entities': self.entities_with(tile['domains'], tile['has_attributes'])}
                          if tile.get('has_attributes') else {}),
                       'options': [option(o) for o in tile['options']],
                       'example': words(tile.get('example')), 'preview': bool(tile.get('preview')),
                       # Places for pictures on the tile (0.10), shown only where the screen has the memory for them.
                       'pictures': tile['pictures']}
                      for tile in manifest['tiles']],
            # Its screensavers (plugin API 0.14): a face of a step or a step of its own, for the Screensaver card.
            'savers': [{'id': saver['id'], 'name': words(saver['name']), 'icon': glyph(saver['icon']), 'step': saver['step'],
                        'pictures': saver['pictures'], 'taps': saver['taps'], 'domains': saver['domains'],
                        'options': [option(o) for o in saver['options']], 'example': words(saver.get('example'))}
                       for saver in manifest.get('savers') or ()],
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

    def listed(self):
        """One plugin per id, as the editor lists them: the index's, a link someone added in this app over it, and a folder
        someone is making over both."""
        listed = {}
        for entry in [*self.index.values(), *self.links.values(), *self.folders.values()]:
            listed[entry.id] = entry
        return listed

    def image_url(self, entry):
        """The editor's address of a plugin's picture, or None: named after its commit (a folder: the file's time), so a
        new picture is a new address."""
        if not entry.image:
            return None
        version = entry.ref
        if entry.folder is not None:
            try:
                version = int((Path(entry.folder) / STORE_IMAGE).stat().st_mtime)
            except OSError:
                return None
        return f'api/plugins/{entry.id}/image?v={version or 0}'

    async def store_image(self, plugin_id):
        """The PNG of a listed plugin's picture for the Plugins page, or None: from its folder, or fetched from GitHub at
        the plugin's commit and kept under data/images (one per plugin), checked to be a PNG of a size the page takes."""
        entry = self.listed().get(plugin_id)
        if entry is None or not entry.image:
            return None
        if entry.folder is not None:
            try:
                body = (Path(entry.folder) / STORE_IMAGE).read_bytes()
            except OSError:
                return None
            return body if store_image_ok(body) else None
        found = GITHUB_LINK.match(entry.repo or '')
        if not found or not re.fullmatch(r'[0-9a-f]{40}', entry.ref or ''):
            return None
        kept = self.data / 'images' / f'{entry.id}-{entry.ref}.png'
        try:
            return kept.read_bytes()
        except OSError:
            pass
        base = '' if entry.path in ('', '.') else entry.path.strip('/') + '/'
        url = GITHUB_RAW.format(owner=found.group(1), repo=found.group(2), ref=entry.ref, path=base + STORE_IMAGE)
        import aiohttp
        try:
            if self.http is None or self.http.closed:
                self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15),
                                                  headers={'User-Agent': self.fetcher.user_agent})
            async with self.http.get(url) as response:
                if response.status != 200:
                    return None
                body = bytes(await read_whole(response, STORE_IMAGE_MAX))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
            LOG.info('Plugin %s: picture not read (%s)', entry.id, error)
            return None
        if not store_image_ok(body):
            LOG.info('Plugin %s: %s is not a PNG the Plugins page takes', entry.id, STORE_IMAGE)
            return None
        try:
            kept.parent.mkdir(parents=True, exist_ok=True)
            for old in kept.parent.glob(f'{entry.id}-*.png'):
                old.unlink(missing_ok=True)
            kept.write_bytes(body)
        except OSError as error:
            LOG.warning('Plugin %s: picture not kept (%s)', entry.id, error)
        return body

    def settle(self):
        """What a plugin's record says squared with what its screen runs, for a screen without a build on its way: a
        plugin the screen reports at that version is active (built elsewhere: ESPHome Device Builder, a computer), and one
        still building without a build is failed (the app restarted during it), so the editor offers to build again
        instead of waiting for ever."""
        running = self.running()
        line = getattr(self.manager, 'build_queue', None)
        for inbox, records in self.store.everywhere().items():
            if line and line.on_the_way(screen=inbox):
                continue
            reported = {item['id']: item.get('version') for item in running.get(inbox) or []}
            for record in records:
                state = record.get('state', 'active')
                if state in ('building', 'failed') and reported.get(record['id']) == record.get('version'):
                    self._settle_build(inbox, [record['id']], True, None)
                elif state == 'building':
                    self._settle_build(inbox, [record['id']], False, 'interrupted')

    def payload(self, language='en'):
        self.settle()
        self.scan_folders()
        listed = self.listed()
        installed = {}
        running = self.running()
        for inbox, records in self.store.everywhere().items():
            installed[inbox] = []
            for record in records:
                entry = self.entry_for(record)
                if entry and entry.id not in listed:
                    listed[entry.id] = entry   # an installed release the index no longer lists
                installed[inbox].append({'id': record['id'], 'version': record.get('version', ''),
                                         'source': record.get('source', 'index'), 'ref': record.get('ref'),
                                         'origin': record_origin(record), 'branch': record.get('branch'),
                                         'auto': bool(record.get('auto')),
                                         'blocked': self.blocked_record(record),
                                         'parts': record.get('parts', []), 'values': record.get('values', {}),
                                         'consent': (record.get('consent') or {}).get('permissions'),
                                         'state': record.get('state', 'active'), 'reason': record.get('reason'),
                                         # Whether the screen runs it (runs): the editor says so when it does not.
                                         'running': runs(inbox, record, running),
                                         **({'failed_update': record['failed_update']} if record.get('failed_update') else {}),
                                         # Which of its secrets for this screen alone are set (never their values).
                                         'secrets': {item['id']: self.secrets.has(
                                             record['id'], item['id'], inbox, None if record.get('source') == 'folder'
                                             else record_origin(record))
                                             for item in (entry.manifest['inputs'] if entry else [])
                                             if item['kind'] == 'secret' and item['scope'] == 'screen'}})
        secrets = {}
        for entry in listed.values():
            for item in entry.manifest['inputs']:
                if item['kind'] == 'secret':
                    secrets.setdefault(entry.id, {})[item['id']] = self.secrets.has(
                        entry.id, item['id'], origin=None if entry.source == 'folder' else entry.origin)
        entities = plugin_entities(listed.values(), getattr(self.manager.ha, 'states', {}) or {})
        # Per screen: the features its board and its plugins bring, and why a plugin cannot go on it when that is
        # something only the app knows (a feature nothing brings, a plugin it needs that does not fit, ESPHome too old).
        # The editor works out the board, PSRAM and room itself.
        features, fit = {}, {}
        for screen in map(self.known_board, self.screens()):
            features[screen['id']] = sorted(self.features_on(screen))
            reasons = {entry.id: reason for entry in listed.values()
                       if (reason := self.fits(entry, screen)) in ('esphome', 'feature', 'needs', 'built_in')}
            if reasons:
                fit[screen['id']] = reasons
        return {'api': api_text(), 'plugins': [self.editor_plugin(entry, language) for entry in listed.values()],
                'entities': entities,
                'installed': installed, 'running': running, 'secrets': secrets,
                'features': features, 'fit': fit, 'likes': self.liker.view(),
                'index': {'at': self.index_state['at'], 'error': self.index_state['error']},
                'folders': {'path': str(self.folder_root()), 'errors': self.folder_errors},
                'fetch': self.fetcher.status()}

    # ---- A screen's plugins file ----

    def sidecar(self, inbox, records=None):
        """The text of `<name>.plugins.yaml` for this screen's records (or the ones it is about to have). A plugin whose
        first build failed is left out, so the screen's next build (an update of the core) does not fail on it."""
        packages, components = [], []
        records = [r for r in (self.store.of(inbox) if records is None else records) if r.get('state') != 'failed']
        screen = self.screen_of(inbox) or {'id': inbox}
        have = self.features_on(screen, records)
        for record in records:
            entry = self.entry_for(record)
            # A release the index blocks is left out of the next build (drop_blocked); the editor says why. So is one that
            # brings what the screen's board now brings itself: two of one ESPHome id would stop the build.
            if not entry or self.blocked_record(record) or self.fits(entry, screen, deep=False) == 'built_in':
                continue
            values = record.get('values') or {}
            variables = {item['id'].upper(): str(values.get(item['id'], '')) for item in entry.manifest['inputs']
                         if item['kind'] != 'secret' and values.get(item['id'], '') != ''}
            # A part that needs a feature is built only on a screen that has it (a voice answering out loud: a speaker).
            parts = [p['file'] for p in entry.manifest['parts']
                     if p['id'] in (record.get('parts') or []) and set(p['features']) <= have]
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
            # Every source but a folder is pinned to one commit: what is built is what the editor showed.
            packages += [f'  {name}:', f'    url: {entry.repo}', f'    ref: {entry.ref}  # {entry.id} {entry.version}',
                         '    refresh: never', '    files:', f'      - path: {folder}plugin.yaml']
            if variables:
                packages.append(f'        vars: {json.dumps(variables)}')
            packages += [f'      - path: {folder}{part}' for part in parts]
            components += ['  - source:', '      type: git', f'      url: {entry.repo}', f'      ref: {entry.ref}',
                           f'      path: {folder}components', '    refresh: never']
        lines = ['# Written by Tessera. Change plugins in Tessera, not here.']
        if packages:
            lines += ['packages:', *packages, 'external_components:', *components]
        else:
            lines.append('{}')
        return '\n'.join(lines) + '\n'

    def attach_line(self, profile_name):
        return f'packages:\n  tessera_plugins: !include {Path(profile_name).stem}.plugins.yaml'

    # ---- Adding and removing ----

    def screens(self):
        """The screens this app knows (the manager's list)."""
        screens = getattr(self.manager, 'screens', None)
        return list(screens() if callable(screens) else [])

    def screen_of(self, inbox):
        """The screen as the manager knows it (None when it is not paired), with the board package its profile builds
        from while it reports no board itself: offline or restarting, its Screen board sensor says nothing, and without
        its board's features a part that needs one (Screen camera's Video, a microphone) fell out of its plugins file,
        so the next build had no video (a reTerminal D1001, 2026-10-27)."""
        screen = self.manager.screen(inbox)
        return self.known_board(screen) if screen else None

    def known_board(self, screen):
        if core.board_of(screen) in core.SHAPES or screen.get('package'):
            return screen
        package_of = getattr(self.manager, 'package_of', None)
        package = package_of(screen) if callable(package_of) else None
        return {**screen, 'package': package} if package else screen

    def features_on(self, screen, records=None):
        """The features a screen has: what its board brings (boards.json `features`) and what its plugins bring."""
        have = set(core.SHAPES.get(core.board_of(screen), {}).get('features') or [])
        for record in self.store.of(screen['id']) if records is None else records:
            entry = self.entry_for(record)
            if entry and not self.blocked_record(record):
                have |= set(entry.manifest['provides'])
        return have

    def fits(self, entry, screen, deep=True):
        """None when the plugin fits this screen, else the reason (the editor's Misfit words). `deep`: also what it
        needs, one step down: a plugin it needs that the screen lacks must exist and fit, and every feature it needs must
        be on the screen or brought by a plugin that fits."""
        manifest = entry.manifest
        if not pm.api_fits(manifest['api']):
            return 'api'
        if manifest['boards'] != 'any' and core.board_of(screen) not in manifest['boards']:
            return 'board'
        # What the board brings itself (boards.json `features`): a plugin that brings it too would define its id twice.
        # A screen that had such a plugin before its board brought the feature leaves it out of its build (sidecar).
        if set(manifest['provides']) & set(core.SHAPES.get(core.board_of(screen), {}).get('features') or []):
            return 'built_in'
        # PSRAM: a board that draws camera pictures has it (features/camera.yaml is for PSRAM boards only).
        if manifest['requires']['psram'] and not screen.get('pictures') and not core.SHAPES.get(core.board_of(screen), {}).get('camera'):
            return 'psram'
        if self.blocked(entry):
            return 'blocked'
        # The ESPHome the app builds with (its Dockerfile); a screen with its own YAML may build with another.
        wanted, have = manifest['requires'].get('esphome'), build_cache.esphome_version()
        if wanted and have and version_tuple(have) < version_tuple(wanted):
            return 'esphome'
        if deep and (manifest['requires']['plugins'] or manifest['requires']['features']):
            for need in manifest['requires']['plugins']:
                other = self.index.get(need) or self.folders.get(need)
                if not self.store.get(screen['id'], need) and (other is None or self.fits(other, screen, deep=False)):
                    return 'needs'
            have = self.features_on(screen)
            for feature in manifest['requires']['features']:
                if feature not in have and not self.providers(feature, screen):
                    return 'feature'
        return None

    def providers(self, feature, screen):
        """The plugins of the list that bring `feature` and fit this screen, Tessera's own first."""
        found = [entry for entry in self.listed().values()
                 if feature in entry.manifest['provides'] and not self.fits(entry, screen, deep=False)]
        return sorted(found, key=lambda e: (e.label != 'tessera', e.id))

    def _entry_asked(self, item):
        if not isinstance(item, dict) or not isinstance(item.get('id'), str):
            raise ValueError(t('addon.errors.plugins.request'))
        source = item.get('source') or ('folder' if item['id'] in self.folders else 'index')
        entry = (self.folders if source == 'folder' else self.links if source in ('link', 'branch') else self.index).get(item['id'])
        if entry is None:
            raise ValueError(t('addon.errors.plugins.unknown', id=item['id']))
        return entry

    def _plan(self, screen, body, language='en'):
        """What a change of one screen's plugins comes to (plan() says it to the editor, apply() carries it out).

        The plugins asked for come with what they need: a plugin of `requires.plugins` the screen lacks, from the index,
        and for a feature of `requires.features` the screen lacks, the one plugin that brings it and fits; when several
        do, the person chooses (`providers`: {feature: id}), and when none does it cannot be done. One screen has one of
        each feature. A plugin another one on the screen needs is only removed together with it. Returns {"add": [{"entry",
        "auto", "for"}], "remove": [ids], "choose": [{"feature", "for", "options"}], "orphans": [ids], "error": text}."""
        adds, removes = body.get('add') or [], body.get('remove') or []
        providers = body.get('providers') if isinstance(body.get('providers'), dict) else {}
        if not isinstance(adds, list) or not isinstance(removes, list) or len(adds) > 8 or len(removes) > 8:
            raise ValueError(t('addon.errors.plugins.request'))
        removes = {r for r in removes if isinstance(r, str)}
        name = lambda entry: entry.text('name', language)
        records = [r for r in self.store.of(screen['id']) if r['id'] not in removes]
        on = {r['id']: e for r in records if (e := self.entry_for(r))}
        auto = {r['id'] for r in records if r.get('auto')}
        steps, queue, choose = {}, [], []
        for item in adds:
            entry = self._entry_asked(item)
            reason = self.fits(entry, screen, deep=False)
            if reason:
                return self._refusal(reason, entry, language)
            # `auto`: the editor sends what its plan showed as coming along with the rest, with what was filled in.
            steps[entry.id] = {'entry': entry, 'auto': item.get('auto') is True, 'for': []}
            on[entry.id] = entry
            queue.append(entry)
        board = set(core.SHAPES.get(core.board_of(screen), {}).get('features') or [])

        def come_along(entry, why):
            if entry.id in steps:
                steps[entry.id]['for'].append(why.id)
                return
            steps[entry.id] = {'entry': entry, 'auto': True, 'for': [why.id]}
            on[entry.id] = entry
            queue.append(entry)

        seen = set()
        while queue:
            entry = queue.pop(0)
            if entry.id in seen:
                continue
            seen.add(entry.id)
            for need in entry.manifest['requires']['plugins']:
                if need in on:
                    continue
                other = self.index.get(need)
                if other is None:
                    return {'error': t('addon.errors.plugins.requires_unknown', name=name(entry), other=need)}
                if self.fits(other, screen, deep=False):
                    return {'error': t('addon.errors.plugins.requires_misfit', name=name(entry), other=name(other))}
                come_along(other, entry)
            for feature in entry.manifest['requires']['features']:
                if feature in board or any(feature in e.manifest['provides'] for e in on.values()):
                    continue
                options = [o for o in self.providers(feature, screen) if o.id not in removes]
                chosen = next((o for o in options if o.id == providers.get(feature)), None)
                if chosen is None and len(options) == 1:
                    chosen = options[0]
                if chosen is not None:
                    come_along(chosen, entry)
                elif options:
                    choose.append({'feature': feature, 'for': entry.id, 'options': [o.id for o in options]})
                else:
                    return {'error': t('addon.errors.plugins.feature_missing', name=name(entry),
                                       feature=t(f'editor.plugins.features.{feature}') if feature in pm.FEATURES else feature)}
        # One of each feature: two plugins, or a board and a plugin, cannot both bring a speaker (one ESPHome id).
        for feature in pm.FEATURES:
            bringing = [e for e in on.values() if feature in e.manifest['provides']]
            if len(bringing) + (feature in board) > 1:
                return {'error': t('addon.errors.plugins.feature_conflict', feature=t(f'editor.plugins.features.{feature}'),
                                   names=', '.join(name(e) for e in bringing))}
        # What is removed must not leave another plugin without what it needs.
        have = board | {f for e in on.values() for f in e.manifest['provides']}
        for plugin in removes:
            gone = self.entry_for(self.store.get(screen['id'], plugin) or {'id': plugin}) if self.store.get(screen['id'], plugin) else None
            if gone is None:
                continue
            needing = [e for e in on.values() if plugin in e.manifest['requires']['plugins']
                       or any(f in gone.manifest['provides'] and f not in have for f in e.manifest['requires']['features'])]
            if needing:
                return {'error': t('addon.errors.plugins.needed_by', name=name(gone), others=', '.join(name(e) for e in needing)),
                        'needed_by': {plugin: [e.id for e in needing]}}
        # Plugins that only came along for something that is now gone: the editor offers to remove them as well.
        needed = {need for e in on.values() for need in e.manifest['requires']['plugins']}
        needed |= {e.id for e in on.values() if any(f in e.manifest['provides'] and f not in board
                                                       for other in on.values() for f in other.manifest['requires']['features'])}
        orphans = sorted(pid for pid in on if pid in auto and pid not in steps and pid not in needed)
        return {'add': list(steps.values()), 'remove': sorted(removes), 'choose': choose, 'orphans': orphans, 'error': None}

    def _refusal(self, reason, entry, language='en'):
        """Why a plugin asked for cannot go on this screen, in a sentence."""
        name = entry.text('name', language)
        texts = {'api': lambda: t('addon.errors.plugins.misfit_api', name=name),
                 'board': lambda: t('addon.errors.plugins.misfit_board', name=name),
                 'psram': lambda: t('addon.errors.plugins.misfit_psram', name=name),
                 'blocked': lambda: t('addon.errors.plugins.misfit_blocked', name=name),
                 'built_in': lambda: t('addon.errors.plugins.misfit_built_in', name=name),
                 'esphome': lambda: t('addon.errors.plugins.misfit_esphome', name=name,
                                      version=entry.manifest['requires'].get('esphome', ''))}
        return {'error': texts[reason]()}

    def plan(self, inbox, body, language='en'):
        """What adding and removing these plugins on one screen comes to, for the editor to show before anything is built:
        what comes along and why, a feature to choose a plugin for, what else could go, and why it cannot be done."""
        screen = self.screen_of(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        if not isinstance(body, dict):
            raise ValueError(t('addon.errors.plugins.request'))
        self.scan_folders()
        plan = self._plan(screen, body, language)
        if plan.get('error'):
            return {'error': plan['error'], 'needed_by': plan.get('needed_by') or {}}
        return {'error': None,
                'add': [{'id': step['entry'].id, 'source': step['entry'].source, 'auto': step['auto'], 'for': step['for'],
                         'flash_kb': step['entry'].manifest['flash_kb'],
                         'permission_hash': pm.permission_hash(step['entry'].manifest)} for step in plan['add']],
                'remove': plan['remove'], 'choose': plan['choose'], 'orphans': plan['orphans']}

    async def apply(self, inbox, body):
        """Add and remove plugins on one screen, write its plugins file and build it. `body`:
        {"add": [{"id", "source": "index"|"folder"|"link"|"branch", "parts": [...], "values": {...}, "secrets": {...},
        "consent": bool, "switch": bool, "auto": bool}], "remove": [id], "providers": {feature: id}}. What the plugins
        asked for need comes along in the same build (_plan), marked as come along; `switch` replaces a plugin of the same
        id from another origin on this screen, which nothing does unasked."""
        if not isinstance(body, dict):
            raise ValueError(t('addon.errors.plugins.request'))
        screen = self.screen_of(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        inbox = screen['id']
        profile, host = self.manager.updates.resolve(screen)
        firmware = self.manager.firmware
        self.scan_folders()
        plan = self._plan(screen, body)
        if plan.get('error'):
            raise ValueError(plan['error'])
        if plan['choose']:
            first = plan['choose'][0]
            raise ValueError(t('addon.errors.plugins.choose', feature=t(f'editor.plugins.features.{first["feature"]}'),
                               name=self.listed()[first['for']].text('name') if first['for'] in self.listed() else first['for']))
        given = {item['id']: item for item in body.get('add') or [] if isinstance(item, dict)}
        # A screen the app has a profile for but no address of cannot be built now: say so before anything changes, so the
        # person tries again once it is on (the editor keeps what was set aside).
        if profile and not host:
            raise ValueError(t('addon.errors.plugins.offline', screen=screen.get('name') or screen.get('node') or inbox))
        # Everything is checked first and nothing is kept until the plugins file is written: a request that is refused
        # halfway, or a file the app cannot write, leaves the records, the secrets and the file as they were.
        changes, secret_sets = [], []
        for step in plan['add']:
            entry = step['entry']
            item = given.get(entry.id) or {'id': entry.id}
            had = self.store.get(inbox, entry.id)
            # Another plugin of this id on this screen (a fork, a folder being made) is replaced only when the person
            # said so: an update never moves a screen to another repository by itself.
            if had and record_origin(had) != entry.origin and item.get('switch') is not True:
                raise ValueError(t('addon.errors.plugins.other_origin', name=entry.text('name'), origin=record_origin(had)))
            values, secrets = item.get('values') or {}, item.get('secrets') or {}
            if not isinstance(values, dict) or not isinstance(secrets, dict):
                raise ValueError(t('addon.errors.plugins.request'))
            # What this screen has now: an update that leaves an input or its parts out keeps what was filled in when
            # the plugin was added (a calendar, a part that is on), so nothing is lost by updating.
            same = had if had and record_origin(had) == entry.origin else None
            kept = {}
            for spec in entry.manifest['inputs']:
                given_value = secrets.get(spec['id']) if spec['kind'] == 'secret' else values.get(spec['id'])
                if given_value is not None and (not isinstance(given_value, str) or len(given_value) > 256):
                    raise ValueError(t('addon.errors.plugins.request'))
                if spec['kind'] == 'secret':
                    if given_value:
                        secret_sets.append((entry.id, spec['id'], given_value, 'all' if spec['scope'] == 'all' else inbox,
                                            None if entry.source == 'folder' else entry.origin))
                elif given_value:
                    kept[spec['id']] = given_value.strip()
                elif given_value is None and same and (same.get('values') or {}).get(spec['id']):
                    kept[spec['id']] = same['values'][spec['id']]
            known = {x['id'] for x in entry.manifest['parts']}
            asked = item.get('parts')
            defaults = [x['id'] for x in entry.manifest['parts'] if x['default']]
            parts = [x for x in (asked if isinstance(asked, list) else (same or {}).get('parts', defaults) if same else defaults)
                     if x in known]
            # An update that asks for more than the person agreed to waits for their yes (the editor asks again).
            agreed = (same or {}).get('consent', {}).get('permissions') if same else None
            if same and agreed and agreed != pm.permission_hash(entry.manifest) and item.get('consent') is not True:
                raise ValueError(t('addon.errors.plugins.consent', name=entry.text('name')))
            # Came along: added for another plugin, and not asked for by name before or now.
            came = step['auto'] and (had is None or bool(had.get('auto')))
            # What the screen ran before, built and working: a build that fails puts it back (_settle_build), so a failed
            # update never leaves a screen whose plugins file no longer builds.
            previous = had.get('previous') or (had if had.get('state', 'active') == 'active' else None) if had else None
            changes.append({'entry': entry, 'record': {
                'id': entry.id, 'source': entry.source, 'repo': entry.repo, 'path': entry.path,
                'ref': entry.ref, 'version': entry.version, 'parts': parts, 'values': kept,
                **({'repo_id': entry.repo_id} if entry.repo_id else {}),
                **({'branch': entry.branch} if entry.branch else {}),
                **({'auto': True} if came else {}),
                **({'previous': {k: v for k, v in previous.items() if k not in ('previous', 'failed_update')}}
                   if previous and profile else {}),
                'consent': {'permissions': pm.permission_hash(entry.manifest), 'at': int(time.time())},
                'state': 'building' if profile else 'active'}})
        removes = plan['remove']
        had_records = self.store.of(inbox)
        records = [r for r in had_records if r['id'] not in removes and r['id'] not in {c['record']['id'] for c in changes}]
        records += [dict(c['record'], changed=int(time.time())) for c in changes]
        text = self.sidecar(inbox, records)
        if profile:
            firmware.save_plugins(profile, text)
        # Written: now the records and the secrets follow.
        for change in changes:
            if change['entry'].source in ('index', 'link', 'branch'):
                self.keep_snapshot(change['entry'])
            self.store.put(inbox, change['record'])
        for args in secret_sets:
            self.secrets.set(*args)
        for plugin in removes:
            gone = self.store.get(inbox, plugin)
            self.store.remove(inbox, plugin)
            origin = record_origin(gone) if gone else None
            if gone and not any(record_origin(r) == origin for screen_records in self.store.everywhere().values()
                                for r in screen_records if r['id'] == plugin):
                self.secrets.drop_plugin(plugin, None if origin == 'folder' else origin)
            self.secrets.drop_scope(plugin, inbox)
        self._know_tiles()
        if not profile:
            # A screen built from its own YAML: the app cannot build it, so the page shows the file and the line.
            return {'own_yaml': True, 'file': f'{screen.get("node") or "screen"}.plugins.yaml', 'content': text,
                    'line': self.attach_line(f'{screen.get("node") or "screen"}.yaml')}
        # The screen's build waits its turn in the app's one build line (build_queue, docs/BUILDS.md): ticking three
        # screens on the Plugins page builds them one after the other. A screen asked again while its build waits builds
        # once, with everything asked for it, and so does one whose update waits; one asked while its build runs builds
        # once more after it, since that build may have read its YAML before this change.
        line = self.manager.build_queue
        # A plugin whose parts changed builds from an empty build folder (BuildQueue, Build.fresh).
        before = {r['id']: r for r in had_records}
        fresh = any(c['record']['id'] in before and
                    sorted(before[c['record']['id']].get('parts') or []) != sorted(c['record']['parts'] or [])
                    for c in changes)
        build = line.add('plugins', profile, self._build, screen=inbox, target=host,
                         plugins={'add': [c['record']['id'] for c in changes], 'remove': list(removes), 'fresh': fresh})
        if self._built not in build.ends:
            build.ends.append(self._built)
        self.manager.notify()
        return {'written': True, 'built': True, 'queued': line.place(build)}

    async def _build(self, build):
        """A plugin build's turn: the screen's firmware with its plugins file, installed over Wi-Fi."""
        ok = await self.manager.build_queue.step({'file': build.file, 'action': 'install', 'target': build.target})
        return 'success' if ok else 'failed'

    def _built(self, build):
        """What the end of a build of this screen (a plugin build, or the update it became one with) means for the
        plugins it brought: whether the screen's firmware with them went on. A plugin asked for again while it built is
        settled by the build that waits for it."""
        later = self.manager.build_queue.waiting(build.file)
        again = set(later.plugins['add']) if later else set()
        ok = build.installed
        reason = None if ok else ('interrupted' if build.state == 'interrupted'
                                  else build_reason(build.logs) if build.logs else str(build.reason or build.state))
        self._settle_build(build.screen, [p for p in build.plugins['add'] if p not in again], ok, reason)

    def _settle_build(self, inbox, added, ok, reason):
        """What a build's end means for the plugins it added. Built: they are active and what came before is forgotten.
        Failed: the screen still runs what it ran, so the plugins file goes back to that, and the next build of this screen
        (an update of the core, Device Builder) does not fail on the same plugin. A new plugin stays listed as failed,
        out of the file, until the person tries again or removes it; an update goes back to the version that worked and
        remembers which one failed, so the editor can say so and offer it again."""
        rewrite = False
        for plugin in added:
            record = self.store.get(inbox, plugin)
            if not record:
                continue
            if ok:
                for key in ('previous', 'failed_update', 'reason'):
                    record.pop(key, None)
                # `settled`: when it went on, so the screen gets its reboot before its hello is held against it (runs).
                self.store.put(inbox, dict(record, state='active', settled=int(time.time())))
            elif record.get('previous'):
                back = dict(record['previous'], state='active',
                            failed_update={'version': record.get('version'), 'ref': record.get('ref'), 'reason': reason})
                self.store.put(inbox, back)
                rewrite = True
            else:
                self.store.set_state(inbox, plugin, 'failed', reason)
                rewrite = True
        if rewrite:
            self._know_tiles()
            self.rewrite_sidecar(inbox)

    def blame(self, inbox, logs):
        """The plugin of this screen a failed build stopped on: a compiler error in one of its components, which are
        named after it (`tap_sound`, `tap_sound_player`). {'id', 'name', 'version', 'update'}, with `update` the version
        on offer when it is another than the one built, or None when no plugin of this screen is to blame."""
        broken = failed_components(logs)
        for record in self.store.of(inbox) if broken else []:
            plugin = record.get('id') or ''
            if not any(name == plugin or name.startswith(plugin + '_') for name in broken):
                continue
            entry, source = self.known(plugin, inbox), record.get('source', 'index')
            # The same newer release the editor offers (hasUpdate in web/src/stores/plugins.ts): a test of a branch by
            # its commit, a release by its version; a folder is built as it is.
            offer = None if source == 'folder' else (self.links if source in ('link', 'branch') else self.index).get(plugin)
            newer = offer and (offer.ref != record.get('ref') if source == 'branch' else offer.version != record.get('version'))
            update = offer.version if newer else None
            return {'id': plugin, 'name': entry.text('name') if entry else plugin, 'version': record.get('version'),
                    'update': update}
        return None

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
            self.secrets.drop_scope(record['id'], inbox)
            if not self.store.in_use(record['id']):
                self.secrets.drop_plugin(record['id'])

    def set_secret(self, plugin, input_id, value):
        """A secret for every screen, for the plugin of this id the editor lists (its origin keeps it from a fork)."""
        entry = self.listed().get(plugin) or self.known(plugin)
        spec = entry and next((i for i in entry.manifest['inputs'] if i['id'] == input_id and i['kind'] == 'secret'), None)
        if not spec or (value is not None and (not isinstance(value, str) or len(value) > 256)):
            raise ValueError(t('addon.errors.plugins.request'))
        self.secrets.set(plugin, input_id, (value or '').strip(), origin=None if entry.source == 'folder' else entry.origin)
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

    @staticmethod
    def asks(fetch, chosen):
        """The questions of one tile's fetch: [(values, pick)], the tile's options as words (plugin_fetch.word_of). One,
        or for a fetch with `each` (0.12) one per value of that list option, in its order, with the option's place
        holding that one value and `pick` its {value, label}; none while the list is empty."""
        words = plugin_fetch.words_of(chosen)
        each = fetch.get('each')
        if not each:
            return [(words, None)]
        out = []
        for item in (chosen.get(each) if isinstance(chosen.get(each), list) else [])[:pm.MAX_MULTIPLE]:
            pick = item if isinstance(item, dict) else {'value': str(item), 'label': str(item)}
            out.append(({**words, each: str(pick.get('value', ''))}, pick))
        return out

    async def tile_data(self, entry, tile, chosen, ask=True, inbox=None):
        """What the screen gets for one tile: the mapped answer of its fetch, with "stale" or "wait". A fetch with `each`
        (0.12) puts the answers of its values together; one that has none yet is left out, one that failed makes the
        list stale, and only when none has an answer does the tile wait."""
        if not tile.get('data'):
            return None
        fetch = entry.fetch(tile['data'])
        secrets = self.secret_values(entry, inbox)
        asks = self.asks(fetch, chosen)
        if not asks:
            return {'wait': 'not_filled'}
        answers, waits, stale = [], [], False
        for values, pick in asks:
            try:
                if ask:
                    _, cached = await self.fetcher.get(entry.id, entry.manifest, fetch, values, secrets)
                else:
                    cached = self.fetcher.peek(entry.id, fetch, values, secrets)
            except plugin_fetch.FetchRefused as error:
                waits.append('not_filled' if 'not filled' in str(error) else 'refused')
                continue
            if not cached or cached['data'] is None:
                waits.append('failed' if cached and cached['error'] else 'asking')
                continue
            stale = stale or cached['stale']
            answers.append((cached['data'], values, pick))
        if not answers:
            return {'wait': next(w for w in ('refused', 'not_filled', 'failed', 'asking') if w in waits)}
        try:
            if fetch.get('each'):
                data = plugin_fetch.apply_each(fetch['map'], answers)
            else:
                data = plugin_fetch.apply_map(fetch['map'], *answers[0])
        except Exception as error:   # an answer of another shape than the map expects
            LOG.warning('plugin %s: the answer did not fit its map (%s)', entry.id, error)
            return {'wait': 'failed'}
        if stale or 'failed' in waits:
            data['stale'] = True
        return trimmed(data)

    def state_part(self, spec, entity, budget=X_BUDGET, updated=False):
        """(entity, what the screen gets of it) for a tile that belongs to an entity, or one an entity option chose
        (plugin API 0.15): its state, its name, the attributes `spec` names and the `fields` it takes out of them,
        bounded as every tile's: a text at 48 bytes, and the lists together within `budget`, each shortened from the
        end to the same length only when they do not fit (96 prices of a quarter of an hour fit, twice). An attribute
        named ..._at, ..._time or ...date that holds a moment goes as seconds since 1970, so the screen says it in its
        words. `updated`: also when Home Assistant last heard from the entity, in seconds since 1970 (an entity option's,
        so a tile of several sources can say how old its values are)."""
        if not spec or not spec.get('domains') or not entity:
            return None, None
        if entity.split('.')[0] not in spec['domains']:
            return entity, {'wait': 'wrong_entity'}
        state = self.manager.ha.states.get(entity) or {}
        attrs = state.get('attributes') or {}
        bounded = {}
        for name in spec.get('attributes', ()):
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
        for name, field in (spec.get('fields') or {}).items():
            bounded[name] = plugin_fetch.field_value(attrs, {**field, 'tz': field.get('tz') or zone})
        part = {'state': core.short(str(state.get('state', 'unavailable')), 160),
                'name': core.short(attrs.get('friendly_name') or entity, 48), 'attributes': bounded}
        moment = plugin_fetch.epoch_of(state.get('last_updated'), zone) if updated else None
        if moment is not None:
            part['updated'] = moment
        for items in LIST_STEPS:
            shaped = {**part, 'attributes': {name: value if not isinstance(value, list) or items is None else value[:items]
                                             for name, value in bounded.items()}}
            if json_size(shaped) <= budget:
                return entity, shaped
        return entity, {'wait': 'too_large'}

    def entity_part(self, kind, tile, budget=X_BUDGET):
        """The tile's own entity (its `plugin_entity`), as state_part has it."""
        entity = (tile.get('options') or {}).get('plugin_entity')
        return self.state_part(kind, entity, budget)

    @staticmethod
    def option_entities(kind, chosen):
        """The selected Home Assistant entities of a plugin tile's entity options (plugin API 0.15)."""
        if not kind:
            return ()
        return tuple(value for option in kind.get('options', ()) if option['kind'] == 'entity'
                     for value in (chosen.get(option['id']),) if isinstance(value, str) and value)

    async def tile_message(self, index, tile, ask=True, inbox=None):
        """The state message of a plugin tile (core.state_message's shape): no entity behind it, its options, its data.
        `inbox`: the screen it goes to, whose own plugin of that id answers."""
        plugin, tile_id = core.plugin_tile(tile['entity'])
        entry = self.known(plugin, inbox)
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
        bound = (options.get('plugin_entity') or '') if kind and kind['domains'] else ''
        if bound:
            wire['pe'] = bound
        # The data gets what the message leaves of its 4 KB (the tile's options count, a name of at most 80 bytes).
        room = min(X_BUDGET, page_delivery.MAX_MESSAGE - ENVELOPE - 80 - json_size(
            {'v': 1, 'op': 'state', 'i': index, 'entity': tile['entity'], 'name': '', 'state': 'ok', 'a': {}, 'o': wire}))
        entity, part = self.entity_part(kind, tile, room)
        if entity:
            wire['pe'] = entity
        name = tile.get('name') or (part or {}).get('name') or (entry.text(kind['name']) if kind else tile_id)
        message = {'v': 1, 'op': 'state', 'i': index, 'entity': tile['entity'], 'name': core.short(name, 80),
                   'state': 'ok', 'a': {}, 'o': wire}
        if kind:
            data = await self.tile_data(entry, kind, chosen, ask, inbox)
            # The entities its entity options chose (0.15), under x.entities.<option id>: they share what the tile's
            # own entity and data leave of the room, so one with long attributes waits as too large on its own instead
            # of taking the whole tile with it.
            picked = [(option, chosen[option['id']]) for option in kind.get('options', ())
                      if option['kind'] == 'entity' and isinstance(chosen.get(option['id']), str) and chosen[option['id']]]
            entities = {}
            if picked:
                left = room - json_size({**(part or {}), **(data or {}), 'entities': {}})
                share = left // len(picked) - max(len(option['id']) for option, _ in picked) - 4
                for option, selected in picked:
                    _, selected_part = self.state_part(option, selected, share, updated=True)
                    if selected_part:
                        entities[option['id']] = selected_part
            if part or data or entities:
                message['x'] = trimmed({**(part or {}), **(data or {}), **({'entities': entities} if entities else {})}, room)
        return message

    async def choices(self, plugin, fetch_id, values, inbox=None, search=''):
        """The choices of an option with `options_from`, for the editor's inspector: [{value, label}]. `values`: the
        tile's other options as they are kept (0.12: typed, a list as a list); `search`: what the person typed in a
        searched list, the fetch's {search}, whose answer is soon forgotten."""
        entry = self.known(plugin, inbox)
        fetch = entry.fetch(fetch_id) if entry else None
        if not fetch or 'value' not in fetch['map']:
            raise ValueError(t('addon.errors.plugins.request'))
        clean = {}
        for key, value in plugin_fetch.words_of(values if isinstance(values, dict) else {}).items():
            if isinstance(key, str) and pm.ID.match(key) and key != pm.SEARCH:
                clean[key] = [v[:64] for v in value[:pm.MAX_MULTIPLE]] if isinstance(value, list) else value[:64]
        typed = (search if isinstance(search, str) else '').strip()[:pm.MAX_TEXT]
        if typed:
            clean[pm.SEARCH] = typed
        try:
            _, cached = await self.fetcher.get(entry.id, entry.manifest, fetch, clean, self.secret_values(entry, inbox),
                                               every=SEARCH_EVERY if typed else None)
        except plugin_fetch.FetchRefused:
            return {'choices': [], 'wait': 'not_filled'}
        if cached['data'] is None:
            return {'choices': [], 'wait': 'failed', 'error': cached['error']}
        return {'choices': plugin_fetch.apply_choices(fetch['map'], cached['data'], clean)}

    async def preview(self, plugin, tile_id, options, inbox=None, entity=None):
        """What the editor draws for a plugin tile (it cannot run the plugin's C++): the manifest's `preview` filled in
        from the tile's data, for its first items: [{badge, title, value, at}], `at` a moment the editor counts down to."""
        entry = self.known(plugin, inbox)
        kind = entry.tile(tile_id) if entry else None
        if not kind or not kind.get('preview'):
            raise ValueError(t('addon.errors.plugins.request'))
        chosen = self.values_of(entry, kind, options if isinstance(options, dict) else {})
        if kind.get('data'):
            data = await self.tile_data(entry, kind, chosen, inbox=inbox)
        else:
            _, part = self.entity_part(kind, {'options': {'plugin_entity': entity}})
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

    # ---- A plugin's settings, in its details on the screen's Plugins tab ----

    # The rows and their Home Assistant calls are a board's extras' too: entity_settings.py is the one way both go.
    SETTING_DOMAINS = entity_settings.SETTING_DOMAINS
    STATUS_DOMAINS = entity_settings.STATUS_DOMAINS
    object_id = staticmethod(entity_settings.object_id)

    def _setting_entities(self, screen, entry):
        """{key: entity_id} of a plugin's settings and their status sensors on this screen (entity_settings.entities)."""
        return entity_settings.entities(self.manager, screen, entry.manifest['settings'])

    def setting_row(self, setting, entities, states, entry, online):
        """One row as the editor draws it, with the plugin's own words (entity_settings.row)."""
        return entity_settings.row(setting, entities, states, entry.texts.get(setting['label']) or {'en': setting['label']},
                                   entry.texts.get(setting['hint']) if setting['hint'] else None, online)

    def settings_for(self, inbox, language='en'):
        """The plugins' settings of one screen, as the editor draws them: [{plugin, name, rows: [{key, entity, kind,
        label, hint, value, available, ...}]}]; a button's row has its `status`, a text's `max` and `password`."""
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
            rows = [self.setting_row(setting, entities, states, entry, screen.get('online'))
                    for setting in entry.manifest['settings']]
            out.append({'plugin': entry.id, 'name': entry.texts.get('name') or {'en': entry.id}, 'rows': rows})
        return out

    async def set_setting(self, inbox, entity, value):
        """Change one plugin setting of this screen through Home Assistant: only an entity a plugin on the screen names
        in its manifest's `settings`, of that screen's own device. A button is pressed (value true)."""
        screen = self.manager.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        allowed = set()
        for record in self.store.of(screen['id']):
            entry = self.entry_for(record)
            if entry:
                keys = {setting['key'] for setting in entry.manifest['settings']}
                allowed |= {eid for key, eid in self._setting_entities(screen, entry).items() if key in keys}
        if entity not in allowed:
            raise ValueError(t('addon.errors.plugins.request'))
        return await entity_settings.change(self.manager, entity, value, t('addon.errors.plugins.request'))

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

    # ---- A plugin's screensaver (plugin API 0.14, docs/PLUGINS.md "A screensaver") ----
    def saver_kinds(self, inbox):
        """{key: (entry, saver)} of every screensaver of a plugin this screen runs: in this app's record of the screen
        (what it built in) and in the screen's hello (what its firmware has), `plugin:<plugin>.<saver>`."""
        sender = getattr(self.manager, 'page_senders', {}).get(inbox)
        out = {}
        for item in getattr(sender, 'plugins', None) or ():
            if not item.get('savers') or not self.store.get(inbox, item['id']):
                continue
            entry = self.known(item['id'], inbox)
            for saver_id in item['savers']:
                kind = entry.saver(saver_id) if entry else None
                if kind:
                    out[f'plugin:{entry.id}.{saver_id}'] = (entry, kind)
        return out

    def saver_plugins(self, screen, choice, states):
        """What screen_saver.message needs of a screen's plugins: {'faces': {key: step}, 'steps': {key: what the step
        draws from, None while it has nothing to show}}, or None for a screen without a plugin's screensaver."""
        inbox = screen.get('id')
        kinds = self.saver_kinds(inbox)
        if not kinds:
            return None
        steps = {}
        for key in choice.get('order') or ():
            if key in kinds and kinds[key][1]['step'] == 'own':
                setting = (choice.get('plugins') or {}).get(key) or {}
                steps[key] = self.saver_step(inbox, key, *kinds[key], setting, states)
        return {'faces': {key: kind['step'] for key, (_, kind) in kinds.items()}, 'steps': steps}

    def saver_values(self, inbox, key, options):
        """A plugin saver's options with its manifest's defaults, as a tile's (values_of); as they are for one this screen
        does not have."""
        entry, kind = self.saver_kinds(inbox).get(key, (None, None))
        return self.values_of(entry, kind, options) if kind else dict(options or {})

    def saver_step(self, inbox, key, entry, kind, setting, states):
        """What a plugin's step of its own draws from (its fetch's answer and its entity, as a tile's `x`), or None
        while the step has nothing to show by its manifest's `when`."""
        options = self.values_of(entry, kind, setting.get('options'))
        room = min(X_BUDGET, page_delivery.MAX_MESSAGE - ENVELOPE - 160 - json_size(options))
        entity, part = self.entity_part(kind, {'options': {'plugin_entity': setting.get('entity', '')}}, room)
        if kind['domains'] and not entity:
            return None
        data = self.saver_cache.get((inbox, key)) if kind.get('data') else None
        when = kind.get('when', 'always')
        if when == 'data' and (not data or 'wait' in data):
            return None
        if isinstance(when, dict) and (states.get(entity) or {}).get('state') not in when['state']:
            return None
        step = {**(part or {}), **(data or {})}
        # The step's entity in its words (#286): the screen asks for the step's pictures `for` it, and the app shows
        # Home Assistant's own only for the entity chosen for the step. On a step of an entity it is always the app's,
        # so a field of the fetch's answer cannot stand in for it, and none while an entity of another domain waits.
        if kind['domains']:
            step.pop('entity', None)
            if 'wait' not in part:
                step['entity'] = entity
        return trimmed(step, room)

    def saver_steps(self):
        """Every plugin step of a screensaver with a fetch, on a screen whose screensaver is on: [(inbox, key, entry,
        saver, options)]."""
        out = []
        manager = self.manager
        for inbox in list(getattr(manager, 'layouts', None) or {}):
            screen = manager.screen(inbox) if hasattr(manager, 'screen') else None
            device = (screen or {}).get('device_id')
            choice = manager.savers.get(device) if device and hasattr(manager, 'savers') else None
            if not choice or not choice.get('show'):
                continue
            kinds = self.saver_kinds(inbox)
            for key in choice['order']:
                if key in kinds and key not in choice['off'] and kinds[key][1].get('data'):
                    entry, kind = kinds[key]
                    setting = (choice.get('plugins') or {}).get(key) or {}
                    out.append((inbox, key, entry, kind, self.values_of(entry, kind, setting.get('options'))))
        return out

    async def refresh_savers(self):
        """The fetches of the plugins' screensaver steps, as the tiles' (refresh_data): a pass when an answer changed."""
        changed = False
        seen = set()
        for inbox, key, entry, kind, options in self.saver_steps():
            seen.add((inbox, key))
            data = await self.tile_data(entry, kind, options, True, inbox)
            if self.saver_cache.get((inbox, key)) != data:
                self.saver_cache[(inbox, key)] = data
                changed = True
        for gone in set(self.saver_cache) - seen:
            del self.saver_cache[gone]
        if changed:
            self.manager.ha.changed.set()

    async def refresh_data(self):
        """One round of the fetch loop: ask what is due for every plugin tile on a screen, and send the tiles whose
        answer changed."""
        changed = set()
        for inbox, tile in self.plugin_tiles():
            plugin, tile_id = core.plugin_tile(tile['entity'])
            entry = self.known(plugin, inbox)
            kind = entry.tile(tile_id) if entry else None
            if not kind or not kind.get('data'):
                continue
            chosen = self.values_of(entry, kind, (tile.get('options') or {}).get('plugin'))
            fetch = entry.fetch(kind['data'])
            secrets = self.secret_values(entry, inbox)
            for values, _ in self.asks(fetch, chosen):
                try:
                    before = (self.fetcher.peek(entry.id, fetch, values, secrets) or {}).get('changed')
                    _, cached = await self.fetcher.get(entry.id, entry.manifest, fetch, values, secrets)
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
                # The screensaver's steps first: the tiles' round forgets the answers nobody asked for in it.
                await self.refresh_savers()
                if self.plugin_tiles():
                    await self.refresh_data()
            except Exception as error:   # one plugin's trouble never stops the app
                LOG.warning('Plugin data round failed: %s', error)
            await asyncio.sleep(LOOP_SECONDS)
