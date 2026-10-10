"""What each screen runs of plugins, and the secrets a person filled in for them (docs/PLUGINS.md, "Kept").

- `/data/plugins.json`: per screen (its inbox, the key LayoutStore uses) the plugins it has: where each comes from, the
  commit it is pinned to, its version, its optional parts, what was filled in (never a secret), what the person agreed to
  and its state. Written whole and atomically, like the layouts.
- `/data/plugin_secrets.json` (mode 0600): the values of inputs of kind `secret`, by plugin, input and scope, each with
  the origin it was filled in for (app 0.4.x, plugin API 0.7: `origins`). A secret never leaves this file except into a
  fetch of its own plugin from that origin: not to another plugin with the same id (a fork), not to the editor (it only
  hears that one is set), not to a screen, not into YAML or a log.

A file that is missing means no screen has plugins. Version 1 starts empty; a newer version this app does not know is
left alone and read as empty, so a downgrade never rewrites it.
"""
import json
import os
import tempfile
import threading
import time
from pathlib import Path

VERSION = 1


def _write(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w') as handle:
            json.dump(data, handle, indent=1, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _read(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get('version') == VERSION else None


class PluginStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        data = _read(self.path) or {}
        self.screens = data.get('screens') if isinstance(data.get('screens'), dict) else {}

    def save(self):
        with self.lock:
            _write(self.path, {'version': VERSION, 'screens': self.screens}, 0o644)

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
            if not entry['plugins']:
                self.screens.pop(inbox, None)
            self.save()

    def forget_screen(self, inbox):
        with self.lock:
            if self.screens.pop(inbox, None) is not None:
                self.save()

    def everywhere(self):
        """{inbox: [records]} for every screen with plugins."""
        return {inbox: self.of(inbox) for inbox in self.screens}

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
