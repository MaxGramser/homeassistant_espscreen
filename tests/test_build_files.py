"""The build files (build_files.py, docs/BUILDS.md "Build files"): what the builds leave in /data is measured by kind,
the clean-up removes only that and never while the line builds, builds asked meanwhile wait for it, the offer follows
the size, and the automatic clean-up runs once the line is quiet."""
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_files  # noqa: E402
from build_files import BuildFiles  # noqa: E402
from test_build_queue import Owner, one_step  # noqa: E402

MB = 1024 * 1024
# What a screen's own data is: none of it is a build file.
KEPT = ['screens.json', 'updates.json', 'plugins/clock/plugin.yaml', 'images/cover.jpg',
        'icons/hall.png', 'build-server.key', 'esphome/storage/hall.yaml.json']


def write(root, name, size=1):
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'x' * size)


def tree(root):
    for name in KEPT:
        write(root, name)
    write(root, 'build/hall/.esphome/build/hall/firmware.bin', 3 * MB)
    write(root, 'build/kitchen/src/main.cpp', 2 * MB)
    write(root, 'idf/ccache/a/b.o', 1 * MB)
    write(root, 'idf/frameworks/esp-idf/README.md', 4 * MB)
    write(root, 'idf/tools/xtensa/bin/gcc', 4 * MB)
    write(root, 'platformio/packages/x', 1 * MB)
    write(root, 'esphome/packages/abc/packages/core.yaml', 1 * MB)
    write(root, 'esphome/external_components/def/x.h', 1 * MB)


class Owned(Owner):
    """The build line's owner with the build files beside it, as the Manager holds them."""

    def __init__(self, data):
        super().__init__()
        self.build_files = BuildFiles(self.build_queue, data, self.notify)


class TheSizes(unittest.TestCase):
    def test_each_kind_is_measured_on_its_own(self):
        with tempfile.TemporaryDirectory() as root:
            tree(root)
            sizes = build_files.measure(root)
            self.assertEqual(sizes['screens'], 2)
            self.assertGreaterEqual(sizes['folders'], 5 * MB)
            self.assertLess(sizes['folders'], 6 * MB)
            self.assertGreaterEqual(sizes['cache'], 1 * MB)
            self.assertLess(sizes['cache'], 2 * MB)
            # ESP-IDF and its tools, PlatformIO, and what ESPHome fetched; never ESPHome's storage.
            self.assertGreaterEqual(sizes['tools'], 11 * MB)
            self.assertLess(sizes['tools'], 12 * MB)
            self.assertEqual(sizes['total'], sizes['folders'] + sizes['cache'] + sizes['tools'])

    def test_an_empty_data_folder_is_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(build_files.measure(root)['total'], 0)


class TheCleanUp(unittest.IsolatedAsyncioTestCase):
    async def test_folders_takes_only_the_build_folders(self):
        with tempfile.TemporaryDirectory() as root:
            tree(root)
            owner = Owned(root)
            view = await owner.build_files.clean('folders')
            self.assertEqual(list((Path(root) / 'build').iterdir()), [])
            self.assertTrue((Path(root) / 'idf/ccache/a/b.o').exists())
            self.assertTrue((Path(root) / 'idf/tools/xtensa/bin/gcc').exists())
            for name in KEPT:
                self.assertTrue((Path(root) / name).exists(), name)
            self.assertEqual(view['sizes']['folders'], 0)
            self.assertGreaterEqual(view['last']['freed'], 5 * MB)

    async def test_all_takes_the_cache_and_tools_but_never_the_screens_data(self):
        with tempfile.TemporaryDirectory() as root:
            tree(root)
            owner = Owned(root)
            view = await owner.build_files.clean('all')
            self.assertEqual(view['sizes']['total'], 0)
            for gone in ('build/hall', 'idf/ccache', 'idf/tools', 'idf/frameworks', 'platformio', 'esphome/packages',
                         'esphome/external_components'):
                self.assertFalse((Path(root) / gone).exists(), gone)
            for name in KEPT:
                self.assertTrue((Path(root) / name).exists(), name)

    async def test_a_symlinked_build_folder_is_left_alone(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as elsewhere:
            write(elsewhere, 'precious.txt')
            (Path(root) / 'build').mkdir()
            (Path(root) / 'build/link').symlink_to(elsewhere)
            await Owned(root).build_files.clean('all')
            self.assertTrue((Path(elsewhere) / 'precious.txt').exists())

    async def test_refused_while_a_build_runs_or_waits(self):
        with tempfile.TemporaryDirectory() as root:
            tree(root)
            owner = Owned(root)
            owner.firmware.gate = asyncio.Event()
            line = owner.build_queue
            line.add('install', 'hall.yaml', one_step(line, 'hall.yaml'))
            line.add('install', 'kitchen.yaml', one_step(line, 'kitchen.yaml'))
            with self.assertRaises(ValueError):
                await owner.build_files.clean('folders')
            self.assertTrue((Path(root) / 'build/hall').exists())
            owner.firmware.gate.set()
            await line.idle()
            with self.assertRaises(ValueError):
                await owner.build_files.clean('everything')

    async def test_a_build_asked_during_the_clean_up_waits_for_it(self):
        with tempfile.TemporaryDirectory() as root:
            tree(root)
            owner = Owned(root)
            line = owner.build_queue
            import threading
            started = threading.Event()   # set from the clean-up's thread
            real = build_files.remove

            def slow(data, level):
                started.set()
                import time
                time.sleep(0.2)
                return real(data, level)
            build_files.remove = slow
            try:
                cleaning = asyncio.create_task(owner.build_files.clean('folders'))
                while not started.is_set():
                    await asyncio.sleep(0.01)
                build = line.add('install', 'hall.yaml', one_step(line, 'hall.yaml'))
                await asyncio.sleep(0.05)
                self.assertEqual(build.state, 'queued')   # nothing starts on a folder that is half gone
                self.assertEqual(owner.firmware.calls, [])
                await cleaning
                await build.done.wait()
                self.assertEqual(build.state, 'success')
                self.assertFalse(line.held)
            finally:
                build_files.remove = real


class TheOffer(unittest.IsolatedAsyncioTestCase):
    def files(self, root, folders):
        files = BuildFiles(Owner().build_queue, root)
        files.sizes = {'folders': folders, 'screens': 3, 'cache': 0, 'tools': 0, 'total': folders, 'at': 0}
        return files

    def test_offered_from_the_threshold_on(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(self.files(root, build_files.OFFER_BYTES - 1).offer())
            self.assertTrue(self.files(root, build_files.OFFER_BYTES).offer())

    def test_not_now_waits_until_they_grew(self):
        with tempfile.TemporaryDirectory() as root:
            files = self.files(root, build_files.OFFER_BYTES)
            files.decline()
            self.assertFalse(files.offer())
            # Kept over a restart of the app.
            again = self.files(root, build_files.OFFER_BYTES + build_files.OFFER_AGAIN_BYTES - 1)
            self.assertFalse(again.offer())
            again.sizes['folders'] = build_files.OFFER_BYTES + build_files.OFFER_AGAIN_BYTES
            self.assertTrue(again.offer())

    def test_never_offered_when_it_cleans_up_by_itself(self):
        with tempfile.TemporaryDirectory() as root:
            files = self.files(root, 10 * build_files.OFFER_BYTES)
            (Path(root) / 'build/hall').mkdir(parents=True)
            files.set_auto(True)
            self.assertFalse(files.offer())
            self.assertTrue((Path(root) / 'build/hall').exists())   # nothing goes until the next build
            self.assertTrue(BuildFiles(Owner().build_queue, root).auto)   # kept
            with self.assertRaises(ValueError):
                files.set_auto('yes')


class Automatically(unittest.IsolatedAsyncioTestCase):
    async def quiet_line(self, auto):
        root = tempfile.mkdtemp()
        tree(root)
        owner = Owned(root)
        owner.build_files.auto = auto
        line = owner.build_queue
        line.add('install', 'hall.yaml', one_step(line, 'hall.yaml'))
        await line.idle()
        for _ in range(50):   # the clean-up or the measurement after the line went quiet
            await asyncio.sleep(0.02)
            if owner.build_files.sizes and not owner.build_files.cleaning:
                break
        return root, owner

    async def test_off_by_default_and_then_only_measured(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(BuildFiles(Owner().build_queue, root).auto)
        root, owner = await self.quiet_line(False)
        self.assertTrue((Path(root) / 'build/hall').exists())
        self.assertEqual(owner.build_files.sizes['screens'], 2)

    async def test_on_it_cleans_up_once_the_line_is_quiet(self):
        root, owner = await self.quiet_line(True)
        self.assertEqual(list((Path(root) / 'build').iterdir()), [])
        self.assertTrue((Path(root) / 'idf/ccache/a/b.o').exists())
        self.assertTrue(owner.build_files.last['automatic'])


if __name__ == '__main__':
    unittest.main()
