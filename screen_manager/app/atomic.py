"""One way to keep a file of the app's own: written whole or not at all, and read with one rule for a file it cannot read.

Writing (write_text, write_json): the new text goes into a temporary file beside the target (the same folder, so the
rename stays on one file system), its mode set before the first byte, flushed and fsynced; then it is renamed over the
target in one step (os.replace), and the folder is fsynced so the rename itself is on the disk. At any moment the file
on the disk is the old one whole or the new one whole, never a half of either: a crash, a stop of the container or a
full disk during a save leaves the layouts, the settings and the secrets as they were.

Reading (read_json): a store is a JSON mapping with a `version`. No file is an empty store. A file that is there but is
not JSON or not a mapping is nobody's data as it is: it is set aside as `<name>.unreadable` beside the store (a copy set
aside earlier goes), the log says so, and the store starts empty, so a bug of ours loses nothing of theirs. A mapping
with a version this app does not know (another app's, docs/RELEASING.md "storage version") is left exactly as it is:
the store starts empty and write_json refuses to touch the file (Frozen) until a read finds it readable, so an app that
is put back a version never writes an older file over a newer one.
"""
import contextlib
import json
import logging
import os
from pathlib import Path
import tempfile

LOG = logging.getLogger('screen_manager')
UNREADABLE = '.unreadable'
# The files whose last read found a version this app does not know: left as they are, never written.
_FROZEN = set()


class Frozen(OSError):
    """A write refused because the file on the disk carries a version this app does not know."""


def write_text(path, text, mode=0o600, sync_folder=True):
    """`text` into `path`, whole or not at all (above). `mode` is the file's; `sync_folder` fsyncs the folder after the
    rename, which a caller that syncs it itself (the layout store, which also reports an uncertain commit) leaves off."""
    path = Path(path)
    if str(path) in _FROZEN:
        raise Frozen(f'{path.name} carries a storage version this app does not know and stays as it is')
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
    if sync_folder:
        sync(path.parent)


def write_json(path, data, mode=0o600, **dumps):
    """`data` as JSON into `path`, as write_text; `dumps` goes to json.dumps (indent, sort_keys, separators)."""
    write_text(path, json.dumps(data, ensure_ascii=False, **dumps) + '\n', mode)


def sync(folder):
    """The folder's entries onto the disk: a rename that is not synced can be gone after a power cut."""
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_json(path, version):
    """The mapping of the store at `path` when it carries `version` (an int, or the versions a caller reads), else None:
    no file, a file set aside as unreadable, or a file of another version, left alone and frozen (above)."""
    path = Path(path)
    versions = version if isinstance(version, (tuple, list, set, frozenset)) else (version,)
    try:
        text = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        _FROZEN.discard(str(path))
        return None
    except OSError as error:
        LOG.error('%s cannot be read (%s); starting without it', path.name, type(error).__name__)
        return None
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        set_aside(path, 'not a JSON mapping')
        _FROZEN.discard(str(path))
        return None
    if data.get('version') not in versions:
        LOG.error('%s carries storage version %r, which this app does not know: it stays as it is, and nothing is kept '
                  'in it until the app that wrote it runs again', path.name, data.get('version'))
        _FROZEN.add(str(path))
        return None
    _FROZEN.discard(str(path))
    return data


def frozen(path):
    """Whether the last read of `path` found a version this app does not know (nothing is written to it)."""
    return str(Path(path)) in _FROZEN


def set_aside(path, why):
    """Move the unreadable file at `path` to `<name>.unreadable` beside it, over a copy set aside before."""
    path = Path(path)
    aside = path.with_name(path.name + UNREADABLE)
    try:
        os.replace(path, aside)
    except OSError as error:
        LOG.error('%s is %s and could not be set aside (%s); starting without it', path.name, why, type(error).__name__)
        return
    LOG.error('%s is %s: kept as %s for a look by hand; starting without it', path.name, why, aside.name)
