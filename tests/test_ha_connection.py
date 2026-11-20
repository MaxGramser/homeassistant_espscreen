"""The app's websocket to Home Assistant (server.py HomeAssistant.run): a home with many entities answers with messages
larger than any fixed cap (issue #315: an entity registry of 16.45 MiB with 15,000 entities, a get_states of 28 MB with
a few large sensors), and the app connects to it all the same. A small Home Assistant in this file answers the requests
the app makes while it connects."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))

HAS_DEPS = all(importlib.util.find_spec(name) is not None for name in ('aiohttp', 'yaml'))

if HAS_DEPS:
    import aiohttp
    from aiohttp import web
    from server import HomeAssistant

# Just past the 16 MiB the app used to allow.
LARGE = 17 * 1024 * 1024


def registry(size):
    """An entity registry list of about `size` bytes of JSON."""
    entry = {'entity_id': 'sensor.x', 'platform': 'demo', 'device_id': None, 'options': {'note': 'x' * 1000}}
    count = size // len(json.dumps(entry)) + 1
    return [dict(entry, entity_id=f'sensor.e{i}') for i in range(count)]


@unittest.skipUnless(HAS_DEPS, 'needs aiohttp and PyYAML')
class LargeAnswers(unittest.IsolatedAsyncioTestCase):
    async def connect(self, entities):
        async def websocket(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({'type': 'auth_required'})
            await ws.receive_json()
            await ws.send_json({'type': 'auth_ok'})
            async for msg in ws:
                data = json.loads(msg.data)
                kind = data['type']
                result = (entities if kind == 'config/entity_registry/list' else
                          [] if kind.endswith('/list') or kind == 'get_states' else
                          {} if kind in ('get_config', 'get_services') else None)
                await ws.send_str(json.dumps({'id': data['id'], 'type': 'result', 'success': True, 'result': result}))
            return ws

        app = web.Application()
        app.router.add_get('/api/websocket', websocket)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        self.addAsyncCleanup(runner.cleanup)
        port = site._server.sockets[0].getsockname()[1]
        session = aiohttp.ClientSession()
        self.addAsyncCleanup(session.close)
        ha = HomeAssistant(session, f'http://127.0.0.1:{port}/api', 'token')
        task = asyncio.create_task(ha.run())
        self.addCleanup(task.cancel)
        for _ in range(200):
            if ha.online:
                break
            await asyncio.sleep(0.05)
        return ha

    async def test_an_entity_registry_past_16_mib_connects(self):
        ha = await self.connect(registry(LARGE))
        self.assertTrue(ha.online)
        self.assertGreater(len(json.dumps(ha.registry)), LARGE)


class CloseReason(unittest.TestCase):
    @unittest.skipUnless(HAS_DEPS, 'needs aiohttp and PyYAML')
    def test_a_close_while_connecting_names_its_code(self):
        """A websocket that ends before the app is connected still says why (1009: a message too big)."""
        ha = HomeAssistant(None, 'http://ha/api', 'token')
        ha.ws = types.SimpleNamespace(close_code=1009, exception=lambda: None)
        self.assertEqual(ha.describe_close(None), ', close code 1009')

    @unittest.skipUnless(HAS_DEPS, 'needs aiohttp and PyYAML')
    def test_no_websocket_says_nothing(self):
        ha = HomeAssistant(None, 'http://ha/api', 'token')
        self.assertEqual(ha.describe_close(None), '')


if __name__ == '__main__':
    unittest.main()
