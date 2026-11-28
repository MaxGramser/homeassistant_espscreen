"""The page loads its own script and styles by content hash (app 0.2.58, Vite build since 0.2.73).

After updating to 0.2.57, Safari showed an empty Screen settings panel: it kept a cached script from before
the update. Vite names every built file after a hash of its content and index.html asks for those names, so a
new version is always fetched and an old one is never combined with a new page.
"""
import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'screen_manager/app/static'
HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    sys.path.insert(0, str(ROOT / 'screen_manager/app'))
    import test_scaling
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app


class Build(unittest.TestCase):
    def test_the_build_is_committed_and_names_its_files_by_hash(self):
        page = (STATIC / 'index.html').read_text()
        script = re.search(r'<script type="module" crossorigin src="\./(assets/index-[\w-]+\.js)"></script>', page)
        styles = re.search(r'<link rel="stylesheet" crossorigin href="\./(assets/index-[\w-]+\.css)">', page)
        self.assertTrue(script and styles, 'index.html is the Vite build of web/ (cd web && npm run build)')
        for name in (script[1], styles[1]):
            self.assertTrue((STATIC / name).exists(), name)
        self.assertFalse((STATIC / 'app.js').exists(), 'the old script is gone')
        self.assertEqual(len(list((STATIC / 'assets').glob('index-*.js'))), 1, 'one build at a time: npm run build clears assets/')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Assets(unittest.IsolatedAsyncioTestCase):
    async def test_the_server_serves_the_page_and_its_hashed_assets(self):
        page = (STATIC / 'index.html').read_text()
        script = re.search(r'src="\./(assets/index-[\w-]+\.js)"', page)[1]
        with tempfile.TemporaryDirectory() as tmp:
            manager = Manager(test_scaling.fake_ha(), Path(tmp) / 'screens.json')
            async with TestClient(TestServer(create_app(manager, True))) as client:
                response = await client.get('/')
                self.assertEqual(response.status, 200)
                self.assertEqual(await response.text(), page)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertIn('text/html', response.headers['Content-Type'])
                asset = await client.get(f'/{script}')
                self.assertEqual((asset.status, await asset.read()), (200, (STATIC / script).read_bytes()))
                self.assertEqual((await client.get('/static/app.js')).status, 404)

    async def test_hashed_assets_are_kept_and_the_page_and_api_never(self):
        # A hashed file never changes under its name: the browser keeps it instead of fetching ~310 KB on every open
        # (app 0.2.78). `private`, as the request behind ingress carries Home Assistant's session.
        page = (STATIC / 'index.html').read_text()
        names = re.findall(r'(?:src|href)="\./(assets/[^"]+)"', page)
        self.assertTrue(any(name.endswith('.js') for name in names) and any(name.endswith('.css') for name in names), names)
        with tempfile.TemporaryDirectory() as tmp:
            manager = Manager(test_scaling.fake_ha(), Path(tmp) / 'screens.json')
            async with TestClient(TestServer(create_app(manager, True))) as client:
                for name in names:
                    asset = await client.get(f'/{name}')
                    self.assertEqual((asset.status, asset.headers['Cache-Control']), (200, 'private, max-age=31536000, immutable'), name)
                    again = await client.get(f'/{name}', headers={'If-None-Match': asset.headers['ETag']})
                    self.assertEqual((again.status, again.headers['Cache-Control']), (304, 'private, max-age=31536000, immutable'), name)
                missing = await client.get('/assets/index-nothere.js')
                self.assertEqual(missing.status, 404)
                self.assertNotIn('immutable', missing.headers.get('Cache-Control', ''))
                for path in ('/', '/api/inventory', '/api/inventory?light=1'):
                    self.assertEqual((await client.get(path)).headers['Cache-Control'], 'no-store', path)


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Guard(unittest.IsolatedAsyncioTestCase):
    async def test_only_ingress_reaches_the_app_and_a_change_needs_the_page_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = Manager(test_scaling.fake_ha(), Path(tmp) / 'screens.json')
            # Production only answers Home Assistant's ingress proxy (172.30.32.2), not a request from anywhere else.
            async with TestClient(TestServer(create_app(manager))) as client:
                for path in ('/', '/api/inventory', '/assets/x.js'):
                    response = await client.get(path)
                    self.assertEqual((response.status, await response.text()), (403, 'Open this page through Home Assistant.'), path)
                # Docker's health check comes from inside the container, not through ingress, and is the one
                # request that is answered anyway (issue #23): no page, no data, no change.
                health = await client.get('/health')
                self.assertEqual((health.status, await health.text()), (200, 'ok\n'))
                self.assertEqual((await client.post('/health')).status, 403)
            # The development server answers localhost, and a change still needs the token the page got.
            async with TestClient(TestServer(create_app(manager, True))) as client:
                self.assertEqual((await client.get('/api/inventory')).status, 200)
                for headers in ({}, {'X-Screen-CSRF': 'guessed'}):
                    response = await client.put('/api/updates', json={'auto': True}, headers=headers)
                    self.assertEqual((response.status, await response.text()), (403, 'Refresh this page and try again.'))
                self.assertFalse(manager.updates.auto)


if __name__ == '__main__':
    unittest.main()
