"""Durable, versioned page documents with per-screen migration and revisions.

All writers share a file lock and reload inside that lock. Replacing a whole
store therefore cannot lose an unrelated screen's save. Pending v1 records
retain their original JSON payload, including fields this release cannot read.
Network delivery is deliberately not part of a storage transaction.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import tempfile
import threading

import atomic
from i18n import t
from core import validate_settings
from page_layout import FORMAT, LayoutError, fingerprint, grid_of_record, new_id, screen_grid_of_record, validate_document
from layout_migrations import migrate_legacy

VERSION = 2
LEGACY = "legacy-v1"


class Conflict(LayoutError):
    """The browser must reconcile its draft with a newer saved document."""


class CommitUncertain(OSError):
    """Replacement happened but directory durability could not be confirmed.

    The caller must reread the saved revision, like a lost HTTP response. It
    must not claim that the previous file is still active or undo the commit.
    """


def _members(text, start=0):
    """Yield exact JSON value slices, without reserializing pending records."""
    decoder = json.JSONDecoder()
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != "{":
        raise LayoutError(t('addon.errors.pages.fields'))
    index += 1
    while True:
        while text[index].isspace(): index += 1
        if text[index] == "}": return
        key, index = decoder.raw_decode(text, index)
        while text[index].isspace(): index += 1
        if text[index] != ":": raise LayoutError(t('addon.errors.pages.storage_json'))
        index += 1
        while text[index].isspace(): index += 1
        begin = index
        _, index = decoder.raw_decode(text, index)
        yield key, text[begin:index]
        while text[index].isspace(): index += 1
        if text[index] == "}": return
        if text[index] != ",": raise LayoutError(t('addon.errors.pages.storage_json'))
        index += 1


def _json(text, *, legacy=False):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise LayoutError(t('addon.errors.pages.storage_duplicate'))
            result[key] = value
        return result
    def constant(value):
        if legacy:
            return float(value.replace("Infinity", "inf"))
        raise LayoutError(t('addon.errors.pages.storage_nonfinite'))
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, TypeError) as error:
        raise LayoutError(t('addon.errors.pages.storage_json')) from error


class LayoutStore:
    def __init__(self, path, grid_for):
        self.path = Path(path)
        self.grid_for = grid_for
        self._mutex = threading.RLock()
        self._records = {}
        self._stamp = None
        with self._locked():
            self._reload()

    @contextmanager
    def _locked(self):
        with self._mutex:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.with_suffix(self.path.suffix + ".lock").open("a", encoding="utf8") as lock:
                os.chmod(lock.name, 0o600)
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def _directory_sync(self):
        descriptor = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _replace(self, records):
        payload = json.dumps({"version": VERSION, "screens": records}, ensure_ascii=False,
                             allow_nan=False, separators=(",", ":")) + "\n"
        # Whole or not at all (atomic.write_text); the folder's sync is this store's own, so an uncertain one is reported.
        atomic.write_text(self.path, payload, sync_folder=False)
        self._records = records
        self._stamp = self._file_stamp()
        try:
            self._directory_sync()
        except OSError as error:
            raise CommitUncertain("Storage was replaced; reread its revision before retrying") from error

    def _backup(self, original):
        backup = self.path.with_name(self.path.stem + ".v1.backup.json")
        if backup.exists():
            if backup.read_bytes() == original:
                return
            # A deliberate restore followed by more v1 edits deserves its own
            # backup; the first pre-migration backup is never overwritten.
            backup = self.path.with_name(self.path.stem + ".v1." + fingerprint(original.decode("utf8")) + ".backup.json")
            if backup.exists():
                if backup.read_bytes() != original:
                    raise LayoutError(t('addon.errors.pages.backup_conflict'))
                return
        descriptor, name = tempfile.mkstemp(prefix=backup.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as output:
                os.fchmod(output.fileno(), 0o600)
                output.write(original)
                output.flush()
                os.fsync(output.fileno())
            # link is atomic and refuses an existing destination. A failed
            # backup never leaves a truncated file under the recovery name.
            os.link(name, backup)
            self._directory_sync()
        finally:
            if os.path.exists(name): os.unlink(name)

    def _converted(self, inbox, payload):
        try:
            grid = self.grid_for(inbox)
            if grid is None:
                return {"format": LEGACY, "payload": payload, "migrationError": "addon.errors.pages.source_grid"}
            record = migrate_legacy(_json(payload, legacy=True), grid, recover=True)
        except Exception as error:
            return {"format": LEGACY, "payload": payload, "migrationError": "addon.errors.pages.migration_unreadable"}
        return {**record, "revision": new_id()}

    def _file_stamp(self):
        try:
            stat = self.path.stat()
            return stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size
        except FileNotFoundError:
            return None

    def _reload(self):
        stamp = self._file_stamp()
        if stamp is None:
            self._records = {}
            self._stamp = None
            return
        if stamp == self._stamp:
            return
        original = self.path.read_bytes()
        text = original.decode("utf8")
        # Main's v1 writer allowed NaN/Infinity. Parse the envelope permissively
        # so one historical tile cannot prevent all screens from starting.
        # Converted documents still pass strict validation and finite JSON writes.
        envelope = _json(text, legacy=True)
        if (not isinstance(envelope, dict) or set(envelope) != {"version", "screens"}
                or type(envelope.get("version")) is not int or envelope["version"] not in (1, VERSION)
                or not isinstance(envelope.get("screens"), dict)):
            raise LayoutError(t('addon.errors.pages.storage_version'))
        if envelope["version"] == 1:
            screens_text = next(value for key, value in _members(text) if key == "screens")
            records = {inbox: self._converted(inbox, payload) for inbox, payload in _members(screens_text)}
            self._validate_records(records)
            self._backup(original)
            self._replace(records)
        else:
            self._validate_records(envelope["screens"])
            self._records = envelope["screens"]
            self._stamp = stamp

    @staticmethod
    def _validate_records(records):
        for inbox, record in records.items():
            if not isinstance(inbox, str) or not isinstance(record, dict):
                raise LayoutError(t('addon.errors.pages.storage_record'))
            if record.get("format") == LEGACY:
                if set(record) - {"format", "payload", "migrationError", "settings"} or not isinstance(record.get("payload"), str):
                    raise LayoutError(t('addon.errors.pages.storage_record'))
                _json(record["payload"], legacy=True)
                if "settings" in record: validate_settings(record["settings"])
            elif record.get("format") == FORMAT:
                allowed = {"format", "sourceGrid", "layout", "revision", "settings", "migration", "workspace"}
                if set(record) - allowed or not isinstance(record.get("revision"), str):
                    raise LayoutError(t('addon.errors.pages.fields'))
                validate_document(record.get("layout"), grid_of_record(record))
                if "settings" in record: validate_settings(record["settings"])
                if "migration" in record:
                    migration = record["migration"]
                    if (not isinstance(migration, dict) or set(migration) - {"inactivePageTitles", "droppedTiles", "adjustedFields"}
                            or not isinstance(migration.get("inactivePageTitles", []), list)
                            or len(migration.get("inactivePageTitles", [])) > 8
                            or any(not isinstance(title, str) or len(title.encode()) > 96 for title in migration.get("inactivePageTitles", []))):
                        raise LayoutError(t('addon.errors.pages.storage_metadata'))
                    dropped = migration.get("droppedTiles", [])
                    adjusted = migration.get('adjustedFields', [])
                    if not isinstance(adjusted, list) or len(adjusted) > 6 or any(key not in ('title', 'pages', 'page_titles', 'header', 'settings', 'other') for key in adjusted):
                        raise LayoutError(t('addon.errors.pages.storage_metadata'))
                    if (not isinstance(dropped, list) or any(not isinstance(tile, dict)
                            or set(tile) != {"entity", "name", "reason"}
                            or any(not isinstance(value, str) for value in tile.values()) for tile in dropped)):
                        raise LayoutError(t('addon.errors.pages.storage_metadata'))
                if "workspace" in record:
                    LayoutStore._workspace(record["workspace"], {p["id"] for p in record["layout"]["pages"]})
            else:
                raise LayoutError(t('addon.errors.pages.storage_version'))

    @staticmethod
    def _workspace(value, page_ids):
        if (not isinstance(value, dict) or set(value) != {"revision", "positions"}
                or not isinstance(value["revision"], str) or not isinstance(value["positions"], dict)
                or set(value["positions"]) - page_ids):
            raise LayoutError(t('addon.errors.pages.workspace_refs'))
        for point in value["positions"].values():
            if (not isinstance(point, dict) or set(point) != {"x", "y"}
                    or any(type(v) is not int or not -100000 <= v <= 100000 for v in point.values())):
                raise LayoutError(t('addon.errors.pages.workspace_position'))
        return deepcopy(value)

    def snapshot_since(self, stamp):
        """Read a new snapshot only after an atomic file replacement.

        Hot read paths need one stat, not a lock and a deep copy of every
        screen. Writers still reload under the shared process/file lock.
        """
        if stamp == self._file_stamp():
            return stamp, None
        with self._locked():
            self._reload()
            return self._stamp, deepcopy(self._records)

    def records(self):
        with self._locked():
            self._reload()
            return deepcopy(self._records)

    def get(self, inbox):
        return self.records().get(inbox)

    def retry_migrations(self):
        with self._locked():
            self._reload()
            records = deepcopy(self._records)
            for inbox, record in records.items():
                if record["format"] == LEGACY:
                    records[inbox] = self._converted(inbox, record["payload"])
                    if "settings" in record: records[inbox]["settings"] = deepcopy(record["settings"])
            if records != self._records:
                self._replace(records)
            return deepcopy(records)

    def save(self, inbox, layout, expected_revision, workspace=None, *, settings=None, adapt_grid=False, grid=None):
        with self._locked():
            self._reload()
            previous = self._records.get(inbox)
            if previous and previous["format"] != FORMAT:
                raise LayoutError(t('addon.errors.pages.migration_pending'))
            if expected_revision != (previous["revision"] if previous else None):
                raise Conflict(t('addon.errors.pages.layout_conflict'))
            # `grid`: the one the caller counted this save on (a grid the editor chose, firmware 0.53.0+), else the screen's.
            grid = grid or self.grid_for(inbox) or (screen_grid_of_record(previous) if previous else None)
            if grid is None:
                raise LayoutError(t('addon.errors.pages.source_grid'))
            changed_grid = previous and grid != grid_of_record(previous)
            if changed_grid and not adapt_grid:
                raise LayoutError(t('addon.errors.pages.adaptation'))
            document = validate_document(layout, grid)
            record = deepcopy(previous) if previous else {"format": FORMAT, "sourceGrid": {"columns": grid.columns, "rows": grid.rows}}
            record["layout"] = document
            record["sourceGrid"] = {"columns": grid.columns, "rows": grid.rows}
            record["revision"] = previous["revision"] if previous and not changed_grid and previous["layout"] == document else new_id()
            if settings is not None:
                record["settings"] = validate_settings(settings)
            page_ids = {p["id"] for p in document["pages"]}
            if workspace is not None:
                before = (previous or {}).get("workspace", {"revision": "", "positions": {}})
                if not isinstance(workspace, dict) or workspace.get("revision") != before["revision"]:
                    raise Conflict(t('addon.errors.pages.workspace_conflict'))
                record["workspace"] = self._workspace({**workspace, "revision": new_id()}, page_ids)
            elif "workspace" in record:
                positions = {key: point for key, point in record["workspace"]["positions"].items() if key in page_ids}
                if positions != record["workspace"]["positions"]:
                    record["workspace"] = {"revision": new_id(), "positions": positions}
            records = {**self._records, inbox: record}
            self._validate_records(records)
            if records != self._records: self._replace(records)
            return deepcopy(record)

    def save_workspace(self, inbox, expected_revision, workspace):
        with self._locked():
            self._reload()
            previous = self._records.get(inbox)
            if not previous or previous["format"] != FORMAT or previous["revision"] != expected_revision:
                raise Conflict(t('addon.errors.pages.layout_conflict'))
            current = previous.get("workspace", {"revision": "", "positions": {}})
            if not isinstance(workspace, dict) or workspace.get("revision") != current["revision"]:
                raise Conflict(t('addon.errors.pages.workspace_conflict'))
            value = self._workspace(workspace, {p["id"] for p in previous["layout"]["pages"]})
            if value["positions"] == current["positions"]: return deepcopy(current)
            value["revision"] = new_id()
            self._replace({**self._records, inbox: {**previous, "workspace": value}})
            return deepcopy(value)

    def start_fresh(self, inbox, expected_payload_revision, title):
        """Explicit recovery of an unreadable screen, keeping its original backup."""
        with self._locked():
            self._reload()
            previous = self._records.get(inbox)
            if not previous or previous['format'] != LEGACY or fingerprint(previous['payload']) != expected_payload_revision:
                raise Conflict(t('addon.errors.pages.layout_conflict'))
            grid = self.grid_for(inbox)
            if grid is None: raise LayoutError(t('addon.errors.pages.source_grid'))
            page_id = new_id()
            document = validate_document({'title': title, 'homePageId': page_id, 'pages': [{
                'id': page_id, 'navigation': {'excludeFromPagination': False}, 'tiles': [],
                'topbar': {'leading': [{'id': new_id(), 'kind': 'home'}], 'title': {'source': 'screen'},
                           'trailing': [{'id': new_id(), 'type': 'clock'}]},
            }]}, grid)
            record = {'format': FORMAT, 'sourceGrid': {'columns': grid.columns, 'rows': grid.rows},
                      'layout': document, 'revision': new_id()}
            if 'settings' in previous: record['settings'] = deepcopy(previous['settings'])
            self._replace({**self._records, inbox: record})
            return deepcopy(record)

    def dismiss_migration(self, inbox, expected_revision):
        """Acknowledge recovery notes without changing layout or its backup."""
        with self._locked():
            self._reload()
            previous = self._records.get(inbox)
            if not previous or previous['format'] != FORMAT or previous['revision'] != expected_revision:
                raise Conflict(t('addon.errors.pages.layout_conflict'))
            updated = deepcopy(previous)
            migration = updated.get('migration', {})
            migration.pop('droppedTiles', None)
            migration.pop('adjustedFields', None)
            if not migration: updated.pop('migration', None)
            if updated != previous: self._replace({**self._records, inbox: updated})
            return deepcopy(updated)

    def save_settings(self, inbox, settings):
        settings = validate_settings(settings)
        with self._locked():
            self._reload()
            previous = self._records.get(inbox)
            if not previous:
                raise LayoutError(t('addon.errors.pages.save_first'))
            self._replace({**self._records, inbox: {**previous, "settings": settings}})

    def forget(self, inbox):
        with self._locked():
            self._reload()
            if inbox not in self._records: return False
            self._replace({key: value for key, value in self._records.items() if key != inbox})
            return True

    def rename(self, old, new):
        with self._locked():
            self._reload()
            if old not in self._records: return False
            if new in self._records: raise Conflict(t('addon.errors.pages.destination_exists'))
            self._replace({(new if key == old else key): value for key, value in self._records.items()})
            return True
