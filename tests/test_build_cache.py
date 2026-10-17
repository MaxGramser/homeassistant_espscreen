"""The compile cache GitHub makes ahead (app 0.4.49): fetched once per board, never in the way of a build."""
import asyncio
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
import build_cache  # noqa: E402

LIST = 'https://example.test/release'
FILE = 'https://example.test/cache.tar.gz'


def archive(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class Response:
    def __init__(self, status, body=b'', delay=0):
        self.status, self.body, self.delay = status, body, delay
        self.content = self

    async def __aenter__(self):
        await asyncio.sleep(self.delay)
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        return json.loads(self.body)

    async def iter_chunked(self, size):
        for start in range(0, len(self.body), size):
            yield self.body[start:start + size]


class Session:
    """Stands in for aiohttp: the release list and one file, and which URLs were asked for."""
    def __init__(self, assets, file=b'', status=200, delay=0):
        self.assets, self.file, self.status, self.delay, self.asked = assets, file, status, delay, []

    def get(self, url, headers=None):
        self.asked.append(url)
        if url == LIST:
            return Response(200, json.dumps({'assets': self.assets}).encode())
        return Response(self.status, self.file, self.delay)


def asset(board='cyd', stamp='2026-10-01T03:40:00Z', version='2026.9.0', digest=None):
    return {'name': build_cache.asset_name(board, version), 'updated_at': stamp, 'size': 41_000_000,
            'browser_download_url': FILE, **({'digest': digest} if digest else {})}


class Seed(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / 'idf' / 'ccache'
        self.env = {'ESP_SCREENS_BUILD_CACHE': LIST}
        self.logs = []
        version = patch.object(build_cache, 'esphome_version', return_value='2026.9.0')
        version.start()
        self.addCleanup(version.stop)
        which = patch('build_cache.shutil.which', return_value=None)  # no ccache -c in a test
        which.start()
        self.addCleanup(which.stop)

    def tearDown(self):
        self.tmp.cleanup()

    async def seed(self, session, board='cyd'):
        return await build_cache.seed(board, self.folder, self.logs.append, self.env, session)

    async def test_unpacks_the_boards_cache_and_keeps_its_own_counters(self):
        self.folder.mkdir(parents=True)
        (self.folder / 'a').mkdir()
        (self.folder / 'a' / 'stats').write_text('own')
        files = {'./a/1234R': b'object', './a/stats': b'theirs', './ccache.conf': b'max_size = 9G'}
        outcome = await self.seed(Session([asset()], archive(files)))
        self.assertIn('1 files', outcome)
        self.assertEqual((self.folder / 'a' / '1234R').read_bytes(), b'object')
        self.assertEqual((self.folder / 'a' / 'stats').read_text(), 'own')
        self.assertFalse((self.folder / 'ccache.conf').exists())
        self.assertEqual(list(self.folder.parent.glob('*.part')), [], 'the download is cleaned up')

    async def test_the_download_has_to_match_the_digest_github_names(self):
        """ccache trusts what is in its folder by its key, so what goes in has to be what GitHub built: the release
        asset's sha256 (`digest`), when GitHub names one."""
        import hashlib
        files = archive({'./a/1R': b'x'})
        good = 'sha256:' + hashlib.sha256(files).hexdigest()
        self.assertIn('1 files', await self.seed(Session([asset(digest=good.upper())], files)))
        self.assertEqual((self.folder / 'a' / '1R').read_bytes(), b'x')
        other = archive({'./a/2R': b'y'})
        with self.assertLogs('screen_manager', 'WARNING'):
            outcome = await self.seed(Session([asset(stamp='2026-10-02T03:40:00Z', digest=good)], other))
        self.assertEqual(outcome, 'digest mismatch')
        self.assertFalse((self.folder / 'a' / '2R').exists(), 'nothing of the wrong download is unpacked')
        self.assertEqual(list(self.folder.parent.glob('*.part')), [], 'and the download is gone')
        # The marker still names the cache that was unpacked, so the next good one is fetched.
        self.assertIn('1 files', await self.seed(Session([asset(stamp='2026-10-03T03:40:00Z')], other)))

    async def test_the_same_cache_is_fetched_once(self):
        await self.seed(Session([asset()], archive({'./a/1R': b'x'})))
        again = Session([asset()], archive({'./a/1R': b'x'}))
        self.assertEqual(await self.seed(again), 'already here')
        self.assertEqual(again.asked, [LIST])
        newer = Session([asset(stamp='2026-10-02T03:40:00Z')], archive({'./a/2R': b'y'}))
        self.assertIn('1 files', await self.seed(newer))

    async def test_only_this_boards_cache_of_this_esphome(self):
        session = Session([asset('guition'), asset('cyd', version='2026.8.0')])
        self.assertEqual(await self.seed(session), 'none for cyd on ESPHome 2026.9.0')
        self.assertEqual(session.asked, [LIST])
        self.assertFalse(self.folder.exists())

    async def test_off_asks_nothing(self):
        self.env = {'ESP_SCREENS_BUILD_CACHE': 'off'}
        session = Session([asset()])
        self.assertEqual(await self.seed(session), 'off')
        self.assertEqual(session.asked, [])

    async def test_a_slow_download_is_left_for_the_build(self):
        with patch.object(build_cache, 'TIME_LIMIT', 0.05):
            outcome = await self.seed(Session([asset()], archive({'./a/1R': b'x'}), delay=1))
        self.assertIn('skipped, slower than', outcome)
        self.assertFalse(any(self.folder.rglob('1R')))
        self.assertEqual(list(self.folder.parent.glob('*.part')), [])

    async def test_a_broken_download_never_stops_the_build(self):
        self.assertEqual(await self.seed(Session([asset()], status=404)), 'download failed (404)')
        self.assertIn('skipped', await self.seed(Session([asset()], b'not a tar file')))
        self.assertFalse((self.folder / build_cache.MARKER).exists(), 'tried again next time')

    async def test_a_path_out_of_the_cache_is_refused(self):
        outcome = await self.seed(Session([asset()], archive({'../escaped': b'x'})))
        self.assertIn('skipped', outcome)
        self.assertFalse((self.folder.parent / 'escaped').exists())


if __name__ == '__main__':
    unittest.main()
