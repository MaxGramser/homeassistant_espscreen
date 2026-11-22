"""The files a screen downloads from this app (docs/SCREEN_FILES.md): one store, one path, every kind of file.

A file is named by its content, the sha256 of its bytes in hex, and served on the camera port (picture_links, 8098) as
/files/<name>.<ext>. A screen that has a name has its file: it asks for nothing until a link names another, and an
answer carries the name as its ETag. What a file means is its owner's (sounds.py for the sounds a screen plays, docs/SOUNDS.md); this only
keeps bytes. A file the app makes itself (a built-in ringtone) is kept in memory and made again at each start; a file
someone gave the app is written into `files/` of its data, so it is still there after a restart.

The names are not secret: what a file holds is nothing a screen on the LAN may not have (a ringtone), and a name nobody
was given cannot be guessed. A kind of file that must stay private would need links of its own, as the pictures have.
"""
import hashlib
import logging
import re
import threading
from pathlib import Path

import atomic

LOG = logging.getLogger('screen_manager')
TYPES = {'wav': 'audio/wav'}
NAME = re.compile(r'^[0-9a-f]{64}$')


def name_of(data):
    return hashlib.sha256(data).hexdigest()


class ScreenFiles:
    def __init__(self, data_dir):
        self.folder = Path(data_dir) / 'files'
        self.lock = threading.RLock()
        self.memory = {}   # name: (bytes, ext), what the app makes itself
        self.kept = {}     # name: ext, what is written in `folder`
        try:
            for path in self.folder.iterdir():
                name, _, ext = path.name.partition('.')
                if NAME.match(name) and ext in TYPES:
                    self.kept[name] = ext
        except OSError:
            pass

    def add(self, data, ext, keep=True):
        """The name of `data` as a file of kind `ext`: written into the app's data with `keep`, else held in memory."""
        if ext not in TYPES:
            raise ValueError(ext)
        data = bytes(data)
        name = name_of(data)
        with self.lock:
            if not keep:
                self.memory[name] = (data, ext)
            elif name not in self.kept:
                self.folder.mkdir(parents=True, exist_ok=True)
                atomic.write_bytes(self.folder / f'{name}.{ext}', data, 0o644)
                self.kept[name] = ext
        return name

    def get(self, name):
        """(bytes, ext) of a file, or None."""
        if not isinstance(name, str) or not NAME.match(name):
            return None
        with self.lock:
            if name in self.memory:
                return self.memory[name]
            ext = self.kept.get(name)
        if ext is None:
            return None
        try:
            return (self.folder / f'{name}.{ext}').read_bytes(), ext
        except OSError:
            LOG.warning('Screen file %s.%s is gone from the data folder', name, ext)
            return None

    def remove(self, name):
        """Forgets a file someone gave the app (its owner knows nothing uses it any more)."""
        with self.lock:
            ext = self.kept.pop(name, None)
        if ext:
            try:
                (self.folder / f'{name}.{ext}').unlink()
            except OSError:
                pass

    def ext_of(self, name):
        with self.lock:
            if name in self.memory:
                return self.memory[name][1]
            return self.kept.get(name)

    def link(self, base, name):
        """Where a screen downloads the file: `base` is this app's address on the screen's network (lan_address)."""
        ext = self.ext_of(name)
        return f'{base}/files/{name}.{ext}' if ext else ''

    def serve(self, name, etag=None):
        """(HTTP status, bytes or None, etag, content type) for one load of a screen."""
        found = self.get(name)
        if found is None:
            return 404, None, '', ''
        data, ext = found
        tag = f'"{name}"'
        if etag == tag:
            return 304, None, tag, TYPES[ext]
        return 200, data, tag, TYPES[ext]
