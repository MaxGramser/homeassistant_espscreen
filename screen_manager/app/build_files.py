"""What the builds leave in the app's /data, and cleaning it up (docs/BUILDS.md, "Build files").

Every build leaves files behind so the next one is quick (Firmware.build_env says where each goes):

- `build/<profile>`: a screen's build folder, everything ESPHome compiled for it. Without it the next build of that
  screen compiles everything again; the compile cache answers most of it, so that takes minutes, not the first build's
  quarter of an hour (on a Raspberry Pi more).
- `idf/ccache`: the compile cache (at most CCACHE_SIZE). Without it a build fetches its board's cache from GitHub again
  (build_cache.py), or compiles from scratch where there is none.
- `idf` (the rest), `platformio`, and `esphome` but its `storage`: ESP-IDF with its compilers, and what ESPHome fetched
  from GitHub. Without them the next build downloads them again before it starts.

The clean-up removes `folders` (the build folders, as ESPHome Device Builder's Clean Build Files does for one device)
or `all` (also the cache and the tools, as its Clean All). Nothing else in /data is ever touched: the layouts, keys,
profiles, icons and plugin data stay. It never runs while a build runs or waits, and the line waits for it
(BuildQueue.held), so no build starts on a folder that is half gone.

An automatic clean-up (off unless the owner turns it on) removes the build folders once the line has nothing more to
build. Measuring walks a few hundred thousand files, so it runs off the loop, when the line goes quiet, and after a
clean-up; the editor reads the last result (`view`). Tested in tests/test_build_files.py.
"""
import asyncio
import logging
import os
from pathlib import Path
import shutil
import time

import atomic
from i18n import t

LOG = logging.getLogger('screen_manager')

VERSION = 1
# The build folders are offered to be cleaned up from this size on (after a build, and in Settings): see docs/BUILDS.md.
OFFER_BYTES = 2 * 1024 ** 3
# "Not now" hides the offer until the build folders took this much more.
OFFER_AGAIN_BYTES = 2 * 1024 ** 3
LEVELS = ('folders', 'all')


def disk_bytes(path):
    """What `path` takes on the disk, as `du` counts it: every file's blocks, symlinks not followed."""
    total = 0
    try:
        info = os.lstat(path)
    except OSError:
        return 0
    if not os.path.isdir(path) or os.path.islink(path):
        return getattr(info, 'st_blocks', 0) * 512 or info.st_size
    stack = [str(path)]
    while stack:
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            total += getattr(stat, 'st_blocks', 0) * 512 or stat.st_size
            if entry.is_dir(follow_symlinks=False):
                stack.append(entry.path)
    return total


def _children(folder):
    try:
        return sorted(item for item in Path(folder).iterdir())
    except OSError:
        return []


def build_folders(data):
    return [item for item in _children(Path(data) / 'build') if item.is_dir() and not item.is_symlink()]


def cache_folder(data):
    return Path(data) / 'idf' / 'ccache'


def tool_paths(data):
    """ESP-IDF and its compilers (without the compile cache), PlatformIO, and what ESPHome fetched; its `storage` (what
    it knows of each build) stays, as ESPHome's own Clean All keeps it."""
    data = Path(data)
    idf = [item for item in _children(data / 'idf') if item.name != 'ccache']
    fetched = [item for item in _children(data / 'esphome') if item.name != 'storage']
    return idf + [data / 'platformio'] + fetched


def measure(data):
    """{'folders', 'screens', 'cache', 'tools', 'total', 'at'} in bytes, from the disk now (blocking: off the loop)."""
    folders = build_folders(data)
    sizes = {'folders': sum(disk_bytes(item) for item in folders), 'screens': len(folders),
             'cache': disk_bytes(cache_folder(data)), 'tools': sum(disk_bytes(item) for item in tool_paths(data))}
    return {**sizes, 'total': sizes['folders'] + sizes['cache'] + sizes['tools'], 'at': time.time()}


def remove(data, level):
    """The build folders, and for `all` the cache and the tools too (blocking: off the loop). (what it removed, the bytes
    that freed on the disk)."""
    paths = build_folders(data)
    if level == 'all':
        paths += [cache_folder(data), *tool_paths(data)]
    removed, freed = [], 0
    for path in paths:
        if path.is_symlink() or not path.exists():
            continue
        size = disk_bytes(path)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        freed += size - (disk_bytes(path) if path.exists() else 0)
        removed.append(path.name)
    return removed, freed


class BuildFiles:
    def __init__(self, queue, data, notify=None):
        self.queue, self.data, self.notify = queue, Path(data), notify or (lambda: None)
        self.path = self.data / 'build_files.json'
        self.auto, self.declined = False, None
        self.sizes, self.cleaning, self.last = None, None, None
        self._measuring = None
        raw = atomic.read_json(self.path, VERSION)
        if raw is not None:
            self.auto = raw.get('auto') is True
            declined = raw.get('declined')
            self.declined = declined if isinstance(declined, int) and declined >= 0 else None

    def save(self):
        atomic.write_json(self.path, {'version': VERSION, 'auto': self.auto, 'declined': self.declined})

    # ---- what the editor shows ----
    def offer(self):
        """Whether the page offers the clean-up now: the build folders are large, nothing builds, and "Not now" was not
        said at about this size."""
        folders = (self.sizes or {}).get('folders') or 0
        if self.auto or self.cleaning or folders < OFFER_BYTES:
            return False
        return self.declined is None or folders >= self.declined + OFFER_AGAIN_BYTES

    def view(self):
        return {'sizes': self.sizes, 'auto': self.auto, 'offer': self.offer(), 'cleaning': self.cleaning,
                'last': self.last, 'offer_bytes': OFFER_BYTES}

    # ---- what changes ----
    def set_auto(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError(t('addon.errors.build_files.automatic'))
        # From the next build on: turning it on removes nothing by itself, that is the clean-up's own button with its
        # question.
        self.auto = enabled
        self.save()
        self.notify()

    def decline(self):
        """"Not now": no offer until the build folders grew by OFFER_AGAIN_BYTES."""
        self.declined = (self.sizes or {}).get('folders') or 0
        self.save()
        self.notify()

    async def measure(self):
        """The sizes from the disk; one measurement at a time, a second ask shares it."""
        if self._measuring and not self._measuring.done():
            return await asyncio.shield(self._measuring)
        self._measuring = asyncio.get_running_loop().create_task(asyncio.to_thread(measure, self.data))
        try:
            self.sizes = await asyncio.shield(self._measuring)
        except Exception:
            LOG.exception('Measuring the build files failed')
        self.notify()
        return self.sizes

    async def clean(self, level='folders', automatic=False):
        """Removes the build files of `level`. Refused while a build runs or waits; builds asked meanwhile wait for it."""
        if level not in LEVELS:
            raise ValueError(t('addon.errors.build_files.level'))
        if self.cleaning:
            raise ValueError(t('addon.errors.build_files.cleaning'))
        if self.queue.busy():
            raise ValueError(t('addon.errors.build_files.building'))
        self.cleaning = level
        self.queue.hold()
        self.notify()
        try:
            removed, freed = await asyncio.to_thread(remove, self.data, level)
            LOG.info('Build files cleaned up (%s%s): %s', level, ', automatic' if automatic else '', ', '.join(removed) or 'nothing')
        finally:
            self.cleaning = None
            self.queue.release()
        await self.measure()
        self.last = {'level': level, 'at': time.time(), 'freed': freed, 'automatic': automatic}
        self.declined = None
        self.save()
        self.notify()
        return self.view()

    def after_line(self):
        """The line has nothing more to build (BuildQueue): measure, and clean up when that is on. Never raises."""
        async def run():
            try:
                if self.auto and not self.queue.busy() and not self.cleaning:
                    await self.clean('folders', automatic=True)
                else:
                    await self.measure()
            except ValueError:
                pass   # a build was asked in the meantime: the next quiet line tries again
            except Exception:
                LOG.exception('After the build line went quiet')
        try:
            return asyncio.get_running_loop().create_task(run())
        except RuntimeError:
            return None
