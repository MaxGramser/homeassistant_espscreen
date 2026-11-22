"""What each screen runs of plugins, and the secrets a person filled in for them (docs/PLUGINS.md, "Kept").

- `/data/plugins.json`: per screen (its inbox, the key LayoutStore uses) the plugins it has: where each comes from, the
  commit it is pinned to, its version, its optional parts, what was filled in (never a secret), what the person agreed to
  and its state. Beside them what a person answered to a plugin the app suggested for the screen's board
  (plugin_defaults.py): `declined`, said no or took it off, so it is not suggested again; `accepted`, said yes while an
  update waited, so that update brings it. And under `starting`, by node, what New screen's wizard chose for a screen
  Home Assistant does not have yet: the records its first firmware was built with, and what was unticked, taken over
  once the screen is paired. Written whole and atomically, like the layouts.
- `/data/plugin_secrets.json` (mode 0600): the values of inputs of kind `secret`, by plugin, input and scope, each with
  the origin it was filled in for (app 0.4.x, plugin API 0.7: `origins`). A secret never leaves this file except into a
  fetch of its own plugin from that origin: not to another plugin with the same id (a fork), not to the editor (it only
  hears that one is set), not to a screen, not into YAML or a log.

A file that is missing means no screen has plugins. Version 1 starts empty; a newer version this app does not know is
left alone and read as empty, so a downgrade never rewrites it.
"""
import threading
import time
from pathlib import Path
import atomic

VERSION = 1


def _write(path, data, mode=0o600):
    atomic.write_json(path, data, mode, indent=1, sort_keys=True)


def _read(path):
    return atomic.read_json(path, VERSION)


class PluginStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        data = _read(self.path) or {}
        self.screens = data.get('screens') if isinstance(data.get('screens'), dict) else {}
        self.starting = data.get('starting') if isinstance(data.get('starting'), dict) else {}

    def save(self):
        with self.lock:
            _write(self.path, {'version': VERSION, 'screens': self.screens,
                               **({'starting': self.starting} if self.starting else {})}, 0o644)

    def of(self, inbox):
        """The plugins of one screen, a list of records (copies)."""
        return [dict(item) for item in (self.screens.get(inbox) or {}).get('plugins', [])]

    def get(self, inbox, plugin):
        return next((item for item in self.of(inbox) if item.get('id') == plugin), None)

    def put(self, inbox, record):
        """Add or replace the record of `record['id']` on this screen."""
        with self.lock:
            entry = self.screens.setdefault(inbox, {'plugins': []})
            items = [item for item in entry['plugins'] if item.get('id') != record['id']]
            items.append(dict(record, changed=int(time.time())))
            entry['plugins'] = sorted(items, key=lambda item: item['id'])
            # On the screen now: the answers about it are spent.
            for key in ('declined', 'accepted'):
                entry[key] = [item for item in entry.get(key) or [] if item != record['id']]
                if not entry[key]:
                    del entry[key]
            self.save()

    def set_state(self, inbox, plugin, state, reason=None):
        with self.lock:
            for item in (self.screens.get(inbox) or {}).get('plugins', []):
                if item.get('id') == plugin:
                    item['state'] = state
                    if reason:
                        item['reason'] = reason
                    else:
                        item.pop('reason', None)
            self.save()

    def remove(self, inbox, plugin):
        with self.lock:
            entry = self.screens.get(inbox)
            if not entry:
                return
            entry['plugins'] = [item for item in entry['plugins'] if item.get('id') != plugin]
            if not entry['plugins'] and not entry.get('declined') and not entry.get('accepted'):
                self.screens.pop(inbox, None)
            self.save()

    def answer(self, inbox, plugin, yes):
        """What a person said to a suggested plugin (plugin_defaults.py): no, so it is not suggested for this screen
        again, or yes, so the screen's next update brings it."""
        with self.lock:
            entry = self.screens.setdefault(inbox, {'plugins': []})
            said, other = ('accepted', 'declined') if yes else ('declined', 'accepted')
            entry[said] = sorted(set(entry.get(said) or []) | {plugin})
            entry[other] = [item for item in entry.get(other) or [] if item != plugin]
            if not entry[other]:
                del entry[other]
            self.save()

    def declined(self, inbox):
        return list((self.screens.get(inbox) or {}).get('declined') or [])

    def accepted(self, inbox):
        return list((self.screens.get(inbox) or {}).get('accepted') or [])

    def start(self, node, records, declined):
        """What New screen chose for the screen it is making, until Home Assistant has it (plugins.adopt_started)."""
        with self.lock:
            if records or declined:
                self.starting[node] = {'plugins': [dict(record) for record in records], 'declined': sorted(declined)}
            else:
                self.starting.pop(node, None)
            self.save()

    def started(self, node):
        found = self.starting.get(node)
        return {'plugins': [dict(r) for r in found.get('plugins') or []], 'declined': list(found.get('declined') or [])} if found else None

    def forget_start(self, node):
        with self.lock:
            if self.starting.pop(node, None) is not None:
                self.save()

    def forget_screen(self, inbox):
        with self.lock:
            if self.screens.pop(inbox, None) is not None:
                self.save()

    def everywhere(self):
        """{inbox: [records]} for every screen with plugins."""
        return {inbox: self.of(inbox) for inbox in self.screens if self.of(inbox)}

    def in_use(self, plugin):
        return [inbox for inbox in self.screens if self.get(inbox, plugin)]


class PluginSecrets:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        data = _read(self.path) or {}
        self.values = data.get('values') if isinstance(data.get('values'), dict) else {}
        origins = data.get('origins') if isinstance(data.get('origins'), dict) else {}
        self.origins = {key: origin for key, origin in origins.items() if key in self.values and isinstance(origin, str)}

    @staticmethod
    def key(plugin, input_id, scope='all'):
        return f'{plugin}/{input_id}/{scope}'

    def _save(self):
        _write(self.path, {'version': VERSION, 'values': self.values, 'origins': self.origins})

    def set(self, plugin, input_id, value, scope='all', origin=None):
        """Keep (or with no value forget) a secret, for the origin it was filled in for."""
        with self.lock:
            key = self.key(plugin, input_id, scope)
            if value:
                self.values[key] = str(value)
                if origin:
                    self.origins[key] = origin
                else:
                    self.origins.pop(key, None)
            else:
                self.values.pop(key, None)
                self.origins.pop(key, None)
            self._save()

    def adopt(self, origins):
        """Give a secret kept before secrets had an origin (app 0.4.86 and older) the origin its plugin is installed
        from, `origins` {plugin: {origin, ...}}, so it is handed out again. One installed from a folder, from two origins
        or not at all stays without: a folder asks for every origin, and the others are filled in again."""
        with self.lock:
            changed = False
            for key in self.values:
                if key in self.origins:
                    continue
                found = {origin for origin in origins.get(key.split('/', 1)[0]) or () if origin}
                if len(found) == 1 and 'folder' not in found:
                    self.origins[key] = next(iter(found))
                    changed = True
            if changed:
                self._save()

    def _matches(self, key, origin):
        # None asks for every origin: a folder someone is making in their own config folder.
        return origin is None or self.origins.get(key) == origin

    def has(self, plugin, input_id, scope='all', origin=None):
        key = self.key(plugin, input_id, scope)
        return key in self.values and self._matches(key, origin)

    def of(self, plugin, inbox=None, origin=None):
        """{input: value} of one plugin from one origin: the value for this screen where one is set, else the one for
        every screen. A secret filled in for another origin of the same id is never handed out."""
        out = {}
        for key, value in self.values.items():
            owner, input_id, scope = key.split('/', 2)
            if owner != plugin or not self._matches(key, origin):
                continue
            if scope == 'all' and input_id not in out:
                out[input_id] = value
            elif inbox and scope == inbox:
                out[input_id] = value
        return out

    def drop_scope(self, plugin, scope):
        """Forget a plugin's secrets for one screen (scope: its inbox), when it leaves that screen."""
        with self.lock:
            key = f'{plugin}/'
            gone = [k for k in self.values if k.startswith(key) and k.split('/', 2)[2] == scope]
            for k in gone:
                self.values.pop(k, None)
                self.origins.pop(k, None)
            if gone:
                self._save()

    def drop_plugin(self, plugin, origin=None):
        """Forget a plugin's secrets: those of one origin, or all of them."""
        with self.lock:
            kept = {k: v for k, v in self.values.items()
                    if not k.startswith(plugin + '/') or (origin is not None and self.origins.get(k) != origin)}
            if kept != self.values:
                self.values = kept
                self.origins = {k: o for k, o in self.origins.items() if k in kept}
                self._save()
