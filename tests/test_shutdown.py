"""Stopping the app (app 0.2.78).

`init: false` came from the first add-on, whose image was Home Assistant's s6 base with its own init. The ESPHome base
image has none, so python3 ran as process 1: it ignored SIGTERM (every stop waited ten seconds for SIGKILL) and never
reaped a killed build. The app now gets Home Assistant's default init (tini), Docker Compose `init: true`, and the
server ends on SIGTERM through its own cleanup, which also stops a running build.
"""
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'screen_manager/app'
HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None

# The real server.py as `python3 server.py` runs it, with every port the OS's choice instead of 8099 and 8098.
LAUNCH = '''
import runpy, sys
from aiohttp import web
class Site(web.TCPSite):
    def __init__(self, runner, host=None, port=None, **kwargs):
        super().__init__(runner, '127.0.0.1', 0, **kwargs)
web.TCPSite = Site
sys.path.insert(0, sys.argv[1])
runpy.run_path(sys.argv[1] + '/server.py', run_name='__main__')
'''


class Configuration(unittest.TestCase):
    def test_the_app_and_compose_run_an_init(self):
        config = (ROOT / 'screen_manager/config.yaml').read_text()
        self.assertNotRegex(config, r'(?m)^init:', "Home Assistant's default (init: true) gives the app tini as process 1")
        self.assertRegex((ROOT / 'docker/compose.yaml').read_text(), r'(?m)^    init: true$')
        self.assertIn('handle_signals=True', (APP / 'server.py').read_text())


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Signal(unittest.TestCase):
    def test_sigterm_ends_the_app_at_once_and_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / 'token'
            token.write_text('not-a-real-token\n')
            env = {**os.environ, 'SCREEN_DEV': '1', 'HA_TOKEN_FILE': str(token), 'HA_API': 'http://127.0.0.1:9/api',
                   'SCREEN_DATA': tmp, 'ESPHOME_CONFIG': str(Path(tmp) / 'esphome'), 'HA_CONFIG': tmp, 'PYTHONUNBUFFERED': '1'}
            process = subprocess.Popen([sys.executable, '-c', LAUNCH, str(APP)], env=env, cwd=tmp,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            try:
                # Up once it tried Home Assistant (nothing listens on port 9 here).
                deadline, lines = time.monotonic() + 20, []
                while time.monotonic() < deadline:
                    line = process.stderr.readline()
                    lines.append(line)
                    if 'Home Assistant temporarily unavailable' in line or not line:
                        break
                self.assertIn('Home Assistant temporarily unavailable', ''.join(lines), ''.join(lines))
                started = time.monotonic()
                process.send_signal(signal.SIGTERM)
                code = process.wait(timeout=10)
                self.assertEqual(code, 0, 'a normal stop, not killed by the signal')
                self.assertLess(time.monotonic() - started, 5)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stderr.close()

    def test_ha_token_env_starts_without_token_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k not in ('HA_TOKEN_FILE', 'SUPERVISOR_TOKEN')}
            env.update({'SCREEN_DEV': '1', 'HA_TOKEN': 'not-a-real-token', 'HA_API': 'http://127.0.0.1:9/api',
                        'SCREEN_DATA': tmp, 'ESPHOME_CONFIG': str(Path(tmp) / 'esphome'), 'HA_CONFIG': tmp, 'PYTHONUNBUFFERED': '1'})
            process = subprocess.Popen([sys.executable, '-c', LAUNCH, str(APP)], env=env, cwd=tmp,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            try:
                deadline, lines = time.monotonic() + 20, []
                while time.monotonic() < deadline:
                    line = process.stderr.readline()
                    lines.append(line)
                    if 'Home Assistant temporarily unavailable' in line or not line:
                        break
                self.assertIn('Home Assistant temporarily unavailable', ''.join(lines), ''.join(lines))
                process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=10), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stderr.close()


if __name__ == '__main__':
    unittest.main()
