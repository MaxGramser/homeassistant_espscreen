"""Compile caches GitHub makes ahead (app 0.4.49): a screen's first build skips most of the compiling.

Every board's firmware is the same code for everyone but a few lines (name, keys, Wi-Fi, language), and those few
sit in main.cpp. GitHub (.github/workflows/build-cache.yml, tools/build_cache.py) builds every board each night and
on every release with this app's own image and paths, and publishes each board's ccache as an asset of the release
`build-cache`. Before a build the app fetches its board's cache once, unpacks it into its own (Firmware.build_env)
and builds as it always did: ccache only answers a compile it has the exact inputs for, so a stale or wrong cache
costs time and never makes different firmware. A board without a cache, a cache of another ESPHome, no network or a
download over TIME_LIMIT: the build simply runs without it, as before.
"""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import tarfile
import time

from core import REPO

LOG = logging.getLogger('screen_manager')

TAG = 'build-cache'
# The release's asset list; ESP_SCREENS_BUILD_CACHE points elsewhere (a local test) or turns this off ('off', which
# the GitHub job that makes the caches sets: it has to start from an empty one).
RELEASE = 'https://api.github.com/repos/' + REPO.removeprefix('https://github.com/') + f'/releases/tags/{TAG}'
TIME_LIMIT = 300  # seconds for the whole download; past it the build goes on without
# Recorded per board in the cache folder: which published cache was unpacked, so the same one is not fetched again.
MARKER = '.esp-screens-build-cache.json'
# What lets a cache made on GitHub answer here. ESPHome sets CCACHE_BASEDIR to the build folder itself, which takes the
# screen's name out of most paths; these three options carry it still (the build folder, /data/build/<profile>), and
# they only map paths, so the object they make is the same anywhere. The compiler is recognised by its version rather
# than its file date, which differs on every machine that downloaded the same ESP-IDF toolchain.
CCACHE_ENV = {'CCACHE_IGNOREOPTIONS': '-fmacro-prefix-map=* -fdebug-prefix-map=* -DLV_CONF_PATH=*',
              'CCACHE_COMPILERCHECK': '%compiler% --version'}


def asset_name(board, esphome):
    return f'ccache-{board}-esphome-{esphome}.tar.gz'


def esphome_version():
    try:
        from importlib.metadata import version
        return version('esphome')
    except Exception:
        return None


def _read_marker(folder):
    try:
        data = json.loads((folder / MARKER).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _unpack(archive, folder):
    """The cache files into `folder`. ccache names a file after a hash of what made it, so an existing one is the same
    result; its counters (`stats`) and settings stay this app's own, and `ccache -c` counts the size again."""
    with tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers()
                   if m.isfile() and m.name.split('/')[-1] not in ('stats', 'ccache.conf') and MARKER not in m.name]
        tar.extractall(folder, members=members, filter='data')
    return len(members)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as file:
        for block in iter(lambda: file.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


async def seed(board, folder, log, env=None, session=None):
    """Fetch and unpack `board`'s published cache into the ccache folder `folder` when there is a newer one than the
    last. Returns what happened in a few words; never raises, so a build never fails on it."""
    source = (env or os.environ).get('ESP_SCREENS_BUILD_CACHE', RELEASE)
    if not board or source == 'off':
        return 'off'
    esphome = esphome_version()
    if not esphome:
        return 'no ESPHome version'
    name = asset_name(board, esphome)
    folder = Path(folder)
    started = time.monotonic()
    own = session is None
    try:
        if own:
            import aiohttp
            session = aiohttp.ClientSession()
        try:
            async with asyncio.timeout(TIME_LIMIT):
                async with session.get(source, headers={'Accept': 'application/vnd.github+json'}) as response:
                    if response.status != 200:
                        return f'no list ({response.status})'
                    release = await response.json(content_type=None)
                asset = next((a for a in release.get('assets') or [] if a.get('name') == name), None)
                if not asset:
                    return f'none for {board} on ESPHome {esphome}'
                stamp = asset.get('updated_at') or ''
                if _read_marker(folder).get(board) == stamp:
                    return 'already here'
                folder.mkdir(parents=True, exist_ok=True)
                part = folder.parent / (name + '.part')
                log(f'Fetching the prebuilt compile cache for {board} ({(asset.get("size") or 0) // 1_000_000} MB)')
                async with session.get(asset['browser_download_url']) as response:
                    if response.status != 200:
                        return f'download failed ({response.status})'
                    with part.open('wb') as file:
                        async for chunk in response.content.iter_chunked(1 << 20):
                            file.write(chunk)
        finally:
            if own:
                await session.close()
        # GitHub names the sha256 of every release asset (`digest`): a download that does not match it, however it came
        # to differ, is not unpacked. ccache trusts what is in its folder by its key, so what goes in has to be what
        # GitHub built. An older release without a digest is taken as before.
        digest = str(asset.get('digest') or '')
        if digest.startswith('sha256:'):
            found = await asyncio.to_thread(_sha256, part)
            if found != digest[7:].lower():
                part.unlink(missing_ok=True)
                LOG.warning('The compile cache for %s does not match the digest GitHub gives for it; building without it', board)
                return 'digest mismatch'
        files = await asyncio.to_thread(_unpack, part, folder)
        part.unlink(missing_ok=True)
        if shutil.which('ccache'):
            process = await asyncio.create_subprocess_exec(
                'ccache', '-c', env={**(env or os.environ), 'CCACHE_DIR': str(folder)},
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await process.wait()
        marker = _read_marker(folder)
        marker[board] = stamp
        (folder / MARKER).write_text(json.dumps(marker))
        return f'{files} files in {time.monotonic() - started:.0f} s'
    except TimeoutError:
        return f'skipped, slower than {TIME_LIMIT} s'
    except Exception as error:  # the build goes on without it, whatever went wrong
        LOG.info('No prebuilt compile cache for %s: %s', board, error)
        return f'skipped ({type(error).__name__})'
    finally:
        for leftover in folder.parent.glob(name + '.part'):
            leftover.unlink(missing_ok=True)
