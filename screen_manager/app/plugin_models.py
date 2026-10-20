"""Public microWakeWord sources resolved once into verified, portable build assets.

Only server-stored entries may supply identities or snapshot hashes. Request validation
is pure; downloads use the plugin fetcher's public-only resolver, never HA credentials.
"""
import copy
import hashlib
import errno
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
import uuid
from urllib.parse import urljoin

from aiohttp import ClientError
from plugin_manifest import ID, public_model_host

MAX_MODELS = 16
MAX_MANIFEST_BYTES = 64 * 1024
MAX_MODEL_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
SNAPSHOT_DIR = '.tessera-models'
SNAPSHOT_FILES = ('source.json', 'manifest.json', 'model.tflite')
DIGEST = re.compile(r'^[0-9a-f]{64}$')
IMPORT_DIR = '.imports'
UPLOAD = re.compile(r'^[0-9a-f]{32}$')
IMPORTED_ID = re.compile(r'^ww_[0-9a-f]{24}$')


class ModelError(ValueError):
    """An unsafe source, incompatible model, or damaged immutable asset."""


def validate_url(url):
    """Keep resolver errors typed while sharing the catalogue's exact URL policy."""
    try:
        return public_model_host(url)
    except ValueError as error:
        raise ModelError(str(error)) from error


def model_source(entry):
    """Project a resolved server record back to its exclusive request source."""
    key = 'upload' if 'upload' in entry else 'url'
    return {'id': entry['id'], key: entry[key]}


def validate_requested(spec, requested, previous=None, *, root=None):
    """Validate source shape; Apply additionally checks identities against stored sources."""
    if not isinstance(requested, list) or len(requested) > MAX_MODELS:
        raise ModelError(f'Choose at most {MAX_MODELS} wake models')
    catalogue = {entry['url']: entry['id'] for entry in spec.get('catalogue', [])}
    trusted = {}
    for entry in previous or []:
        if isinstance(entry, dict) and isinstance(entry.get('id'), str):
            key = 'upload' if 'upload' in entry else 'url'
            trusted.setdefault(entry['id'], set()).add((key, entry.get(key)))
    sources, ids, out = set(), set(), []
    for entry in requested:
        if (not isinstance(entry, dict) or set(entry) - {'id', 'url', 'upload'}
                or ('url' in entry) == ('upload' in entry)):
            raise ModelError('Each wake model must contain a URL or upload token and an optional existing ID')
        key = 'upload' if 'upload' in entry else 'url'
        source = entry[key]
        if key == 'url':
            validate_url(source)
        elif not isinstance(source, str) or not UPLOAD.fullmatch(source):
            raise ModelError('Invalid wake model upload token')
        model_id = entry.get('id')
        if 'id' in entry and (not isinstance(model_id, str) or not ID.fullmatch(model_id)):
            raise ModelError('Invalid wake model ID')
        if key == 'upload' and root is not None:
            registered = _read_import(root, source)
            if model_id is not None and model_id != registered['id']:
                raise ModelError('A wake model ID must belong to the registered upload')
            model_id = registered['id']
        elif key == 'url':
            if (model_id is not None and previous is not None and catalogue.get(source) != model_id
                    and (key, source) not in trusted.get(model_id, set())):
                raise ModelError('A wake model ID must belong to an existing model with the same URL')
            if model_id is None:
                historical = next((item for item in previous or [] if item.get('url') == source), None)
                model_id = (historical or {}).get('id') or catalogue.get(source)
        if (key, source) in sources:
            raise ModelError('The same wake model source was added twice')
        if model_id is not None and model_id in ids:
            raise ModelError('The same wake model ID was added twice')
        sources.add((key, source))
        if model_id is not None:
            ids.add(model_id)
        out.append({'id': model_id, key: source} if model_id is not None else {key: source})
    return out


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ModelError('Wake model JSON contains duplicate keys')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ModelError('Wake model JSON must not contain non-finite numbers')


def _finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        _invalid_constant(value)
    return parsed


def parse_manifest(raw, feature_step_size=None):
    """Validate real ESPHome v1/v2 metadata; return original JSON and normalized metadata."""
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ModelError('Wake model JSON exceeds 64 KiB')
    try:
        original = json.loads(raw.decode('utf-8'), object_pairs_hook=_json_object,
                              parse_constant=_invalid_constant, parse_float=_finite_float)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ModelError(f'Invalid wake model JSON: {error}') from error
    if not isinstance(original, dict):
        raise ModelError('Wake model JSON must be an object')
    # Use the pinned runtime's schemas and v1 conversion, including its native
    # minimum_esphome_version validation. Do not substitute timing metadata.
    from esphome.components.micro_wake_word import (
        MANIFEST_SCHEMA_V1, MANIFEST_SCHEMA_V2, _convert_manifest_v1_to_v2,
    )
    from esphome.config_validation import Invalid
    try:
        version = original.get('version')
        if type(version) is not int or version not in (1, 2):
            raise ModelError('Wake model manifest version must be 1 or 2')
        if version == 1:
            metadata = _convert_manifest_v1_to_v2(MANIFEST_SCHEMA_V1(copy.deepcopy(original)))
        else:
            metadata = MANIFEST_SCHEMA_V2(copy.deepcopy(original))
    except (ValueError, OverflowError, Invalid) as error:
        raise ModelError(f'Invalid wake model manifest: {error}') from error
    word, micro = metadata['wake_word'], metadata['micro']
    if not word.strip() or word.strip().casefold() == 'vad':
        raise ModelError('Choose a named wake word, not a VAD model')
    if not isinstance(original['model'], str) or not original['model'].strip():
        raise ModelError('Wake model manifest needs a model URL')
    cutoff = micro['probability_cutoff']
    if not math.isfinite(cutoff) or not 0 <= cutoff <= 1:
        raise ModelError(f'{word}: probability_cutoff must be between 0 and 1')
    if micro['tensor_arena_size'] <= 0 or micro['feature_step_size'] <= 0:
        raise ModelError(f'{word}: tensor arena and feature step must be positive')
    # Native positive_int permits zero, but inference indexes this window and
    # divides by its size. Reject zero for both native v2 and converted v1 models.
    if micro['sliding_window_size'] <= 0:
        raise ModelError(f'{word}: sliding_window_size must be positive')
    if feature_step_size is not None and micro['feature_step_size'] != feature_step_size:
        raise ModelError(f'{word}: feature_step_size is {micro["feature_step_size"]} ms; this plugin requires {feature_step_size} ms')
    return original, metadata


def _check_binary(raw):
    # This is a bounded format sanity check, not operator/audio compatibility proof.
    if not 12 <= len(raw) <= MAX_MODEL_BYTES or raw[4:8] != b'TFL3':
        raise ModelError('Wake model binary must be a TFLite file of at most 2 MiB')
    offset = int.from_bytes(raw[:4], 'little')
    if offset < 8 or offset % 4 or offset > len(raw) - 4:
        raise ModelError('Wake model binary has an invalid TFLite root offset')


def _digest(source, model):
    return hashlib.sha256(len(source).to_bytes(8, 'big') + source
                          + len(model).to_bytes(8, 'big') + model).hexdigest()


def _runnable(original):
    try:
        return (json.dumps({**original, 'model': 'model.tflite'}, ensure_ascii=False,
                           sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    except (ValueError, UnicodeError) as error:
        raise ModelError('Wake model manifest contains invalid Unicode or numbers') from error


def _snapshot_digest(value):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise ModelError('Invalid wake model snapshot digest')
    return value


def snapshot_manifest_path(entry):
    return f'{SNAPSHOT_DIR}/{_snapshot_digest(entry.get("snapshot"))}/manifest.json'


def _open_directory(path, *, dir_fd=None):
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)


def _read_file(directory, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ModelError('Wake model snapshot contains an invalid or oversized file')
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ModelError('Wake model snapshot exceeds the file limit')
        return raw


def verify_snapshot(root, digest):
    """Read and verify all three files through no-follow directory/file handles."""
    digest = _snapshot_digest(digest)
    try:
        root_fd = _open_directory(Path(root))
        try:
            assets_fd = _open_directory(SNAPSHOT_DIR, dir_fd=root_fd)
            try:
                snapshot_fd = _open_directory(digest, dir_fd=assets_fd)
                try:
                    files = {name: _read_file(snapshot_fd, name, MAX_MODEL_BYTES if name == 'model.tflite'
                                              else MAX_MANIFEST_BYTES + 1024) for name in SNAPSHOT_FILES}
                finally:
                    os.close(snapshot_fd)
            finally:
                os.close(assets_fd)
        finally:
            os.close(root_fd)
        source, model = files['source.json'], files['model.tflite']
        if _digest(source, model) != digest:
            raise ModelError('Wake model snapshot digest does not match its contents')
        original, _ = parse_manifest(source)
        _check_binary(model)
        if files['manifest.json'] != _runnable(original):
            raise ModelError('Wake model snapshot runnable manifest has changed')
        return files
    except OSError as error:
        raise ModelError('Wake model snapshot is missing, unreadable or contains a symlink') from error


def snapshot_files(root, entries):
    """Exact portable export files for referenced entries; digest-only entries work too."""
    result, total = {}, 0
    for digest in dict.fromkeys(_snapshot_digest(entry.get('snapshot')) for entry in entries):
        files = verify_snapshot(root, digest)
        total += len(files['model.tflite'])
        if total > MAX_TOTAL_BYTES:
            raise ModelError('Wake models exceed the 8 MiB screen limit')
        result.update({f'{SNAPSHOT_DIR}/{digest}/{name}': raw for name, raw in files.items()})
    return result


def _publish_snapshot(root, source, model, original):
    digest = _digest(source, model)
    root_fd = assets_fd = temporary_fd = None
    temporary = '.tmp-' + uuid.uuid4().hex
    created = False
    try:
        root_fd = _open_directory(Path(root))
        try:
            os.mkdir(SNAPSHOT_DIR, mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        assets_fd = _open_directory(SNAPSHOT_DIR, dir_fd=root_fd)
        # Existing snapshots are immutable, including on a repeat download.
        try:
            os.stat(digest, dir_fd=assets_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            verify_snapshot(root, digest)
            return digest
        os.mkdir(temporary, mode=0o700, dir_fd=assets_fd)
        created = True
        temporary_fd = _open_directory(temporary, dir_fd=assets_fd)
        for name, raw in {'source.json': source, 'manifest.json': _runnable(original), 'model.tflite': model}.items():
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=temporary_fd)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        os.fsync(temporary_fd)
        try:
            os.rename(temporary, digest, src_dir_fd=assets_fd, dst_dir_fd=assets_fd)
            created = False
            os.fsync(assets_fd)
        except OSError as error:
            if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
            verify_snapshot(root, digest)  # a concurrent resolver published the same bytes
        return digest
    except OSError as error:
        raise ModelError('Cannot safely store wake model snapshot') from error
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if created and assets_fd is not None:
            for name in SNAPSHOT_FILES:
                try:
                    os.unlink(f'{temporary}/{name}', dir_fd=assets_fd)
                except FileNotFoundError:
                    pass
            os.rmdir(temporary, dir_fd=assets_fd)
        if assets_fd is not None:
            os.close(assets_fd)
        if root_fd is not None:
            os.close(root_fd)

def _import_record(directory, token):
    if not isinstance(token, str) or not UPLOAD.fullmatch(token):
        raise ModelError('Invalid wake model upload token')
    try:
        record = json.loads(_read_file(directory, token + '.json', 1024),
                            object_pairs_hook=_json_object)
    except (ValueError, UnicodeError) as error:
        raise ModelError('Invalid wake model import registry') from error
    if (not isinstance(record, dict) or set(record) != {'id', 'snapshot'}
            or not isinstance(record['id'], str) or not IMPORTED_ID.fullmatch(record['id'])):
        raise ModelError('Invalid wake model import registry')
    _snapshot_digest(record['snapshot'])
    return record


def _read_import(root, token):
    root_fd = assets_fd = imports_fd = None
    try:
        root_fd = _open_directory(Path(root))
        assets_fd = _open_directory(SNAPSHOT_DIR, dir_fd=root_fd)
        imports_fd = _open_directory(IMPORT_DIR, dir_fd=assets_fd)
        return _import_record(imports_fd, token)
    except OSError as error:
        raise ModelError('Unknown or unreadable wake model upload') from error
    finally:
        for fd in (imports_fd, assets_fd, root_fd):
            if fd is not None:
                os.close(fd)


def _resolved_upload(root, token, spec, record=None):
    record = record if record is not None else _read_import(root, token)
    files = verify_snapshot(root, record['snapshot'])
    _, metadata = parse_manifest(files['source.json'], spec['feature_step_size'])
    return {**record, 'upload': token, 'label': metadata['wake_word'],
            'model_bytes': len(files['model.tflite']),
            'feature_step_size': metadata['micro']['feature_step_size']}


def import_model(spec, source, model, root):
    """Register a private pair without fetching its reference or changing installed models."""
    original, _ = parse_manifest(source, spec['feature_step_size'])
    _check_binary(model)
    digest = _publish_snapshot(root, source, model, original)
    root_fd = assets_fd = imports_fd = None
    temporary = None
    try:
        root_fd = _open_directory(Path(root))
        assets_fd = _open_directory(SNAPSHOT_DIR, dir_fd=root_fd)
        try:
            os.mkdir(IMPORT_DIR, mode=0o700, dir_fd=assets_fd)
        except FileExistsError:
            pass
        imports_fd = _open_directory(IMPORT_DIR, dir_fd=assets_fd)
        fcntl.flock(imports_fd, fcntl.LOCK_EX)
        for name in os.listdir(imports_fd):
            if name.endswith('.json') and UPLOAD.fullmatch(name[:-5]):
                record = _import_record(imports_fd, name[:-5])
                if record['snapshot'] == digest:
                    return _resolved_upload(root, name[:-5], spec, record)
        token = uuid.uuid4().hex
        record = {'id': 'ww_' + uuid.uuid4().hex[:24], 'snapshot': digest}
        name = '.tmp-' + uuid.uuid4().hex
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=imports_fd)
        temporary = name
        with os.fdopen(fd, 'wb') as stream:
            stream.write((json.dumps(record, sort_keys=True) + '\n').encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        # A hard-link publication never overwrites an existing token, even on collision.
        os.link(temporary, token + '.json', src_dir_fd=imports_fd, dst_dir_fd=imports_fd,
                follow_symlinks=False)
        os.fsync(imports_fd)
        return _resolved_upload(root, token, spec, record)
    except OSError as error:
        raise ModelError('Cannot safely store wake model import') from error
    finally:
        if temporary is not None and imports_fd is not None:
            os.unlink(temporary, dir_fd=imports_fd)
        for fd in (imports_fd, assets_fd, root_fd):
            if fd is not None:
                os.close(fd)



async def _download(fetcher, url, limit):
    host = validate_url(url)
    try:
        raw = await fetcher.download_bytes(url, {}, [host], limit, require_status=200)
    except (OSError, ValueError, TimeoutError, ClientError) as error:
        raise ModelError(f'Cannot download wake model from {host}: {error}') from error
    if not isinstance(raw, bytes) or len(raw) > limit:
        raise ModelError(f'Wake model response exceeds {limit} bytes')
    return raw


async def resolve_models(spec, requested, previous, fetcher, root):
    """Resolve whole requested list, reusing trusted immutable same-origin entries.

    previous may combine desired, installed, and failed-request entries. Caller owns
    the screen mutation lock and commits no records/sidecar until this returns.
    """
    previous = previous or []
    requested = validate_requested(spec, requested, previous, root=root)
    resolved, total, used_ids = [], 0, set()
    for request in requested:
        url, model_id = request.get('url'), request.get('id')
        old = next((entry for entry in previous if url is not None and entry.get('url') == url
                    and (model_id is None or entry.get('id') == model_id) and entry.get('snapshot')), None)
        if 'upload' in request:
            entry = _resolved_upload(root, request['upload'], spec)
        elif old is not None:
            files = verify_snapshot(root, old['snapshot'])
            _, metadata = parse_manifest(files['source.json'], spec['feature_step_size'])
            entry = {'id': old['id'], 'url': url, 'snapshot': old['snapshot'],
                     'label': metadata['wake_word'], 'model_bytes': len(files['model.tflite']),
                     'feature_step_size': metadata['micro']['feature_step_size']}
        else:
            source = await _download(fetcher, url, MAX_MANIFEST_BYTES)
            original, metadata = parse_manifest(source, spec['feature_step_size'])
            if any(ord(char) <= 32 or ord(char) == 127 for char in original['model']):
                raise ModelError('Wake model binary reference must not contain whitespace or control characters')
            binary_url = urljoin(url, original['model'])
            validate_url(binary_url)
            model = await _download(fetcher, binary_url, MAX_MODEL_BYTES)
            _check_binary(model)
            if total + len(model) > MAX_TOTAL_BYTES:
                raise ModelError('Wake models exceed the 8 MiB screen limit')
            # Keep a historical ID even if its snapshot is not yet materialized.
            historical = next((item for item in previous if item.get('url') == url
                               and (model_id is None or item.get('id') == model_id)), None)
            model_id = model_id or (historical or {}).get('id') or 'ww_' + uuid.uuid4().hex[:24]
            entry = {'id': model_id, 'url': url, 'label': metadata['wake_word'],
                     'snapshot': _publish_snapshot(root, source, model, original), 'model_bytes': len(model),
                     'feature_step_size': metadata['micro']['feature_step_size']}
        if not isinstance(entry['id'], str) or not ID.fullmatch(entry['id']) or entry['id'] in used_ids:
            raise ModelError('Wake model IDs must be valid and unique')
        used_ids.add(entry['id'])
        total += entry['model_bytes']
        if total > MAX_TOTAL_BYTES:
            raise ModelError('Wake models exceed the 8 MiB screen limit')
        resolved.append(entry)
    return resolved


def build_revision(specs, build_values):
    """Canonical revision includes declared targets, ordered identities and snapshots."""
    settings = [{'id': spec['id'], 'target': spec['target'], 'models': build_values.get(spec['id'], [])}
                for spec in sorted(specs, key=lambda item: item['id'])]
    return hashlib.sha256(json.dumps(settings, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
