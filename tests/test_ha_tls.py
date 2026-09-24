"""Home Assistant on https with a self-signed certificate (Docker, docs/DOCKER.md, app 0.2.134).

The app checked Home Assistant's certificate against the system's list only, so a self-signed one ended every connection
in ClientConnectorCertificateError and the screens stayed on "Waiting for ESP Screens". HA_CA_FILE trusts that
certificate for Home Assistant, HA_VERIFY_SSL "0" checks nothing, and the log names both.
"""
import asyncio
import importlib.util
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp import ClientConnectorCertificateError, ClientSession, web
    from server import HomeAssistant, ha_tls, ingress_from


def self_signed(folder, address='127.0.0.1'):
    """A certificate like the one a home server makes for itself: signed by its own key, naming its IP address."""
    cert, key = Path(folder) / 'ha.pem', Path(folder) / 'ha.key'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2', '-subj', '/CN=homeassistant',
                    '-addext', f'subjectAltName=IP:{address}', '-keyout', str(key), '-out', str(cert)],
                   check=True, capture_output=True)
    return cert, key


@unittest.skipUnless(HAS_AIOHTTP, 'needs aiohttp')
class Settings(unittest.TestCase):
    def test_the_default_checks_against_the_system_list(self):
        self.assertIs(ha_tls({}), True)

    def test_verify_off(self):
        for value in ('0', 'false', 'No', ' off '):
            self.assertIs(ha_tls({'HA_VERIFY_SSL': value}), False)
        self.assertIs(ha_tls({'HA_VERIFY_SSL': '1'}), True)

    def test_a_missing_ca_file_stops_the_start(self):
        with self.assertRaises(FileNotFoundError):
            ha_tls({'HA_CA_FILE': '/nonexistent/ha.pem'})

    def test_ingress_from(self):
        self.assertEqual(ingress_from({}), set())
        self.assertEqual(ingress_from({'SCREEN_INGRESS_FROM': ' 192.168.0.80, ::ffff:192.168.0.80 ,'}),
                         {'192.168.0.80', '::ffff:192.168.0.80'})

    def test_compose_and_guide_name_the_settings(self):
        compose, guide = (ROOT / 'docker/compose.yaml').read_text(), (ROOT / 'docs/DOCKER.md').read_text()
        for name in ('HA_CA_FILE', 'HA_VERIFY_SSL', 'SCREEN_INGRESS_FROM'):
            self.assertIn(name, compose)
            self.assertIn(f'`{name}`', guide)


@unittest.skipUnless(HAS_AIOHTTP and shutil.which('openssl'), 'needs aiohttp and openssl')
class SelfSigned(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.cert, key = self_signed(self.folder.name)
        self.server_tls = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        self.server_tls.load_cert_chain(self.cert, key)

    async def serve(self):
        async def state(request):
            return web.json_response({'state': 'on'})
        app = web.Application()
        app.router.add_get('/api/states/sensor.x', state)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0, ssl_context=self.server_tls)
        await site.start()
        return runner, f'https://127.0.0.1:{runner.addresses[0][1]}/api'

    def fetch(self, tls):
        async def go():
            runner, base = await self.serve()
            try:
                async with ClientSession() as session:
                    async with session.get(base + '/states/sensor.x', ssl=tls) as response:
                        return (await response.json())['state']
            finally:
                await runner.cleanup()
        return asyncio.run(go())

    def test_the_system_list_turns_it_down(self):
        with self.assertRaises(ClientConnectorCertificateError):
            self.fetch(ha_tls({}))

    def test_ha_ca_file_trusts_it(self):
        self.assertEqual(self.fetch(ha_tls({'HA_CA_FILE': str(self.cert)})), 'on')

    def test_verify_off_takes_it(self):
        self.assertEqual(self.fetch(ha_tls({'HA_VERIFY_SSL': '0'})), 'on')

    def test_the_log_says_what_to_set(self):
        async def go():
            runner, base = await self.serve()
            try:
                async with ClientSession() as session:
                    ha = HomeAssistant(session, base, 'token')
                    with self.assertLogs('screen_manager', 'WARNING') as logs:
                        task = asyncio.create_task(ha.run())
                        for _ in range(100):
                            await asyncio.sleep(0.05)
                            if logs.output:
                                break
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                    return logs.output
            finally:
                await runner.cleanup()
        output = '\n'.join(asyncio.run(go()))
        self.assertIn('ClientConnectorCertificateError', output)
        self.assertIn('HA_CA_FILE', output)
        self.assertIn('HA_VERIFY_SSL', output)


if __name__ == '__main__':
    unittest.main()
