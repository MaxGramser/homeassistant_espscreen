"""The building block `fetch`: the add-on asks a web API on a plugin's behalf, and the screen gets only what the
plugin's manifest maps, bounded like every tile state.

A plugin never runs code in the add-on. Its manifest describes a fetch (URL, headers, how often, which fields), and
this module carries it out with its own rules (docs/PLUGINS.md, "Fetch"):

- only hosts the manifest names in `permissions.network`, never an address on the home network, checked again for the
  address the connection really goes to, so a DNS answer cannot point it at the router or Home Assistant;
- https, or plain http only for a fetch that carries no secret; no redirects, at most 64 KB, 10 seconds, JSON only;
- one ask per distinct question (plugin, fetch, the URL and headers with every value filled in), shared by every tile
  and every screen, never more often than the manifest's `every` and never under 30 seconds;
- on a failure the last good answer stays, marked stale, and the next try waits 1, 2, 5, then 15 minutes;
- a secret appears in no log, no answer to the editor and no message to a screen.
"""
import asyncio
import hashlib
import ipaddress
import json
import logging
import math
import socket
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from plugin_manifest import MAX_ITEMS, PLACEHOLDER, parse_path

log = logging.getLogger('plugin_fetch')

MAX_BYTES = 64 * 1024
TIMEOUT = 10
TEXT_BYTES = 48
BACKOFF = (60, 120, 300, 900)
FORGET_AFTER = 2           # intervals a question nobody asks for stays in the cache


class FetchRefused(ValueError):
    """A fetch the rules do not allow: the plugin's manifest or a value filled in is wrong."""


def short(value, limit=TEXT_BYTES):
    """At most `limit` bytes of UTF-8 without breaking a character."""
    raw = str(value).encode()[:limit]
    return raw.decode(errors='ignore')


# ---- The map: what of an answer reaches the screen ----

def walk(data, steps, values=None):
    """Every value a path reaches. `[*]` takes the items of a list or the values of a mapping."""
    found = [data]
    for step in steps:
        nxt = []
        for node in found:
            kind = step[0]
            if kind in ('key', 'var'):
                name = step[1] if kind == 'key' else str((values or {}).get(step[1], ''))
                if isinstance(node, dict) and name in node:
                    nxt.append(node[name])
            elif kind == 'all':
                if isinstance(node, list):
                    nxt.extend(node)
                elif isinstance(node, dict):
                    nxt.extend(node.values())
            elif kind == 'at':
                if isinstance(node, list) and step[1] < len(node):
                    nxt.append(node[step[1]])
            elif kind == 'first':
                if isinstance(node, list):
                    nxt.extend(node[:step[1]])
                elif isinstance(node, dict):
                    nxt.extend(list(node.values())[:step[1]])
        found = nxt
    return found


def first(data, steps):
    found = walk(data, steps)
    return found[0] if found else None


def epoch_of(value, zone=None):
    """Seconds since 1970 from a number, an ISO 8601 time with an offset, or a time without one in `zone`."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value / 1000) if value > 10_000_000_000 else int(value)
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace('Z', '+00:00')
    if len(text) >= 5 and text[-5] in '+-' and text[-4:].isdigit() and ':' not in text[-5:]:
        text = text[:-2] + ':' + text[-2:]          # +0200 -> +02:00
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        tz = None
        if zone:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(zone)
            except Exception:
                tz = None
        moment = moment.replace(tzinfo=tz) if tz else moment.astimezone()
    return int(moment.timestamp())


def number_of(value):
    """A number from a number or a text such as "0,231"; None for anything else (a price not known yet stays a gap, and
    NaN, which JSON cannot carry, is none)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    if not isinstance(value, str):
        return None
    try:
        return number_of(float(value.replace(',', '.')))
    except ValueError:
        return None


def field_value(item, field):
    if field['as'] == 'numbers':
        # Every value the path reaches, in order, as one list: `[*].value` of 96 objects is 96 numbers.
        return [number_of(value) for value in walk(item, field['path'])[:1000]]
    value = first(item, field['path'])
    if field['as'] == 'epoch':
        return epoch_of(value, field.get('tz'))
    if field['as'] == 'number':
        return number_of(value)
    if value is None or isinstance(value, (dict, list)):
        return None
    return short(value)


def _filled(values, rules):
    """Conditions with their placeholders filled in; a condition whose value is empty is no condition."""
    out = {}
    for name, wanted in (rules or {}).items():
        words = []
        for word in wanted:
            word = PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), '')), word)
            if word != '':
                words.append(word)
        if words:
            out[name] = set(words)
    return out


def _word(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return '' if value is None else str(value)


def apply_map(spec, data, values=None):
    """What the screen gets of one answer: `{"items": [...]}` for a list, or the fields of one object."""
    values = values or {}
    if 'fields' not in spec:
        raise FetchRefused('this fetch fills a list of choices')
    if 'items' not in spec:
        return {name: field_value(data, field) for name, field in spec['fields'].items()}
    keep, skip = _filled(values, spec.get('where')), _filled(values, spec.get('skip'))
    items = []
    for raw in walk(data, spec['items'], values):
        if not isinstance(raw, dict):
            continue
        item = {name: field_value(raw, field) for name, field in spec['fields'].items()}
        if any(_word(item.get(name)) not in wanted for name, wanted in keep.items()):
            continue
        if any(_word(item.get(name)) in unwanted for name, unwanted in skip.items()):
            continue
        items.append(item)
        if len(items) >= 1000:
            break
    if spec.get('sort'):
        name = spec['sort'].lstrip('-')
        present = [i for i in items if i.get(name) is not None]
        missing = [i for i in items if i.get(name) is None]
        present.sort(key=lambda i: (isinstance(i[name], str), i[name]), reverse=spec['sort'].startswith('-'))
        items = present + missing
    return {'items': items[:min(spec.get('limit', MAX_ITEMS), MAX_ITEMS)]}


def apply_choices(spec, data, values=None):
    """A list of choices for the inspector: [{value, label}], each value once, at most 48."""
    out, seen = [], set()
    for raw in walk(data, spec['items'], values or {}):
        value = ' '.join(_word(first(raw, path)) for path in spec['value']).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        label = ' · '.join(word for word in (_word(first(raw, path)) for path in spec['label']) if word)
        out.append({'value': short(value, 64), 'label': short(label or value, 64)})
        if len(out) >= MAX_ITEMS:
            break
    return sorted(out, key=lambda c: (len(c['value']), c['value']))


# ---- Filling in a fetch ----

def fill(fetch, values, secrets):
    """The URL and headers with every placeholder filled in. A value in the URL is percent-encoded; a secret may only
    stand in a header or the query (the manifest check makes sure). Raises FetchRefused when one is missing."""
    missing = [name for name in fetch['placeholders']
               if str(values.get(name, secrets.get(name, ''))).strip() == '']
    if missing:
        raise FetchRefused(f'not filled in: {", ".join(missing)}')

    def word(match, encode):
        name = match.group(1)
        value = str(secrets[name]) if name in secrets else str(values.get(name, ''))
        return quote(value, safe='') if encode else value

    url = PLACEHOLDER.sub(lambda m: word(m, True), fetch['url'])
    headers = {key: PLACEHOLDER.sub(lambda m: word(m, False), value) for key, value in fetch['headers'].items()}
    if any(c in value for value in headers.values() for c in '\r\n'):
        raise FetchRefused('a header value holds a line break')
    return url, headers


def question(plugin, url, headers):
    """One key per distinct ask: every tile, screen and fetch of a plugin with the same filled-in URL and headers shares
    it (the bus's departures and its list of lines read the same answer)."""
    digest = hashlib.sha256(json.dumps([url, sorted(headers.items())]).encode()).hexdigest()[:20]
    return f'{plugin}.{digest}'


def redact(text, secrets):
    for value in secrets.values():
        if value:
            text = text.replace(str(value), '***').replace(quote(str(value), safe=''), '***')
    return text


def blocked_address(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified
            or ip.is_reserved or not ip.is_global)


class PublicResolver:
    """aiohttp's resolver, refusing every address on the home network at the moment the connection is made."""

    def __init__(self):
        from aiohttp.resolver import DefaultResolver
        self.inner = DefaultResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        answers = await self.inner.resolve(host, port, family)
        public = [a for a in answers if not blocked_address(a['host'])]
        if not public:
            raise OSError(f'{host} has no public address')
        return public

    async def close(self):
        await self.inner.close()


class Fetcher:
    """Every plugin fetch of the add-on: one cache, one schedule, one session of its own (never the one that holds
    Home Assistant's token)."""

    def __init__(self, user_agent='Tessera (+plugins)', session_factory=None, clock=time.monotonic):
        self.user_agent = user_agent
        self.session_factory = session_factory
        self.session = None
        self.clock = clock
        self.cache = {}         # question -> {'data', 'at', 'ok', 'error', 'stale', 'next', 'fails', 'asked'}
        self.locks = {}

    async def _session(self):
        if self.session is None or self.session.closed:
            if self.session_factory:
                self.session = self.session_factory()
            else:
                import aiohttp
                connector = aiohttp.TCPConnector(resolver=PublicResolver(), limit=8, ttl_dns_cache=300)
                self.session = aiohttp.ClientSession(connector=connector, headers={'User-Agent': self.user_agent},
                                                     timeout=aiohttp.ClientTimeout(total=TIMEOUT))
        return self.session

    async def close(self):
        if self.session is not None and not self.session.closed:
            await self.session.close()

    async def download(self, url, headers, network):
        """The JSON at `url`, within the rules; raises on anything else."""
        parts = urlsplit(url)
        host = (parts.hostname or '').lower()
        if parts.scheme not in ('https', 'http') or host not in network:
            raise FetchRefused(f'{host or url} is not a host this plugin may reach')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise FetchRefused('a fetch names a host, not an address')
        session = await self._session()
        async with session.get(url, headers=headers, allow_redirects=False) as response:
            if response.status in (301, 302, 303, 307, 308):
                raise OSError(f'HTTP {response.status}: redirects are not followed')
            if response.status >= 400:
                raise OSError(f'HTTP {response.status}')
            raw = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                raw += chunk
                if len(raw) > MAX_BYTES:
                    raise OSError('the answer is larger than 64 KB')
        try:
            return json.loads(raw.decode('utf-8', errors='replace'))
        except ValueError:
            raise OSError('the answer is not JSON')

    def peek(self, plugin, fetch, values, secrets):
        """The cache entry for this question without asking, or None; raises FetchRefused when it cannot be filled in."""
        url, headers = fill(fetch, values, secrets)
        return self.cache.get(question(plugin, url, headers))

    async def get(self, plugin, manifest, fetch, values, secrets, force=False):
        """(key, entry) for this question, asked again when its answer is older than this fetch's `every` (and no
        failure asks it to wait). Never raises for a network failure: the entry says what went wrong and keeps the last
        good data. `entry['changed']` counts the answers that differed from the one before."""
        url, headers = fill(fetch, values, secrets)
        key = question(plugin, url, headers)
        now = self.clock()
        entry = self.cache.setdefault(key, {'data': None, 'fetched': None, 'ok': None, 'error': None, 'stale': False,
                                            'retry': 0, 'fails': 0, 'asked': now, 'every': fetch['every'], 'changed': 0})
        entry['asked'] = now
        entry['every'] = min(entry['every'], fetch['every'])
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            fresh = entry['fetched'] is not None and self.clock() - entry['fetched'] < fetch['every']
            if not force and (fresh or self.clock() < entry['retry']):
                return key, entry
            try:
                data = await self.download(url, headers, manifest['permissions']['network'])
                if data != entry['data']:
                    entry['changed'] += 1
                entry.update(data=data, fetched=self.clock(), ok=time.time(), error=None, stale=False, fails=0, retry=0)
            except FetchRefused:
                raise
            except Exception as error:   # the network, the service, its answer
                entry['fails'] += 1
                wait = BACKOFF[min(entry['fails'], len(BACKOFF)) - 1]
                if entry['data'] is not None and not entry['stale']:
                    entry['changed'] += 1
                entry.update(error=redact(str(error) or type(error).__name__, secrets)[:160],
                             stale=entry['data'] is not None, retry=self.clock() + wait)
                log.warning('plugin %s fetch %s: %s', plugin, fetch['id'], entry['error'])
        return key, entry

    def forget_unused(self):
        """Drop questions no tile asked for during two of their intervals."""
        now = self.clock()
        for key in [k for k, e in self.cache.items() if now - e['asked'] > FORGET_AFTER * e['every'] + 60]:
            self.cache.pop(key, None)
            self.locks.pop(key, None)

    def status(self):
        """Per question what a person may see: when it last worked, the last error. No URL, no header."""
        return {key: {'ok': e['ok'], 'error': e['error'], 'stale': e['stale']} for key, e in self.cache.items()}
