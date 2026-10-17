"""Where the add-on's ESPHome CLI keeps what it downloads and builds (app 0.2.89+): all in the app's own /data, apart
from the ESPHome folder the ESPHome Device Builder app cleans, and PlatformIO from before ESPHome 2026.7 removed once.
And what of the container's environment a build gets: the build tools' names and families, never the app's token."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from firmware import BUILD_ENV_NAMES, Firmware, build_environment  # noqa: E402

PROFILE = {'board': 'cyd', 'name': 'kitchen', 'friendly_name': 'Kitchen', 'wifi_ssid': 'ssid', 'wifi_password': 'password'}
KEYS = ('ESPHOME_BUILD_PATH', 'ESPHOME_DATA_DIR', 'ESPHOME_ESP_IDF_PREFIX', 'CCACHE_MAXSIZE', 'PLATFORMIO_CORE_DIR',
        'ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT', 'CCACHE_IGNOREOPTIONS', 'CCACHE_COMPILERCHECK')

# Stands in for the ESPHome CLI: it writes the environment it got, and whether PlatformIO's old folder was still there.
FAKE_CLI = '''#!{python}
import json, os, sys
from pathlib import Path
data = Path(os.environ['ESPHOME_FAKE_DATA'])
record = {{key: os.environ.get(key) for key in {keys!r}}}
record['platformio_left'] = (data / 'platformio' / 'packages').exists()
record['names'] = sorted(os.environ)
with open(data / 'env.jsonl', 'a') as out:
    out.write(json.dumps(record) + '\\n')
'''


def fake_cli(folder, data):
    bin_dir = Path(folder) / 'bin'
    bin_dir.mkdir(exist_ok=True)
    cli = bin_dir / 'esphome'
    cli.write_text(FAKE_CLI.format(python=sys.executable, keys=KEYS))
    cli.chmod(0o755)
    return {'PATH': f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", 'ESPHOME_FAKE_DATA': str(data),
            'ESP_SCREENS_BUILD_CACHE': 'off'}


def records(data):
    return [json.loads(line) for line in (data / 'env.jsonl').read_text().splitlines()]


class BuildEnvironment(unittest.IsolatedAsyncioTestCase):
    async def test_everything_esphome_keeps_goes_in_the_apps_own_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            data.mkdir()
            with patch.dict(os.environ, fake_cli(tmp, data)):
                os.environ.pop('CCACHE_MAXSIZE', None)
                os.environ.pop('ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT', None)
                f = Firmware(Path(tmp) / 'esphome', data)
                # Not the memory of the machine the test runs on (build_memory, app 0.4.65): unknown, so every core.
                f.MEMINFO, f.CGROUP = str(Path(tmp) / 'no-meminfo'), str(Path(tmp) / 'no-cgroup')
                f.create(PROFILE)
                f.start({'file': 'kitchen.yaml', 'action': 'build'})
                await f.task
            self.assertEqual(f.job['state'], 'success', list(f.logs))
            got = records(data)[0]
            self.assertEqual(got['ESPHOME_BUILD_PATH'], str(data / 'build' / 'kitchen'))
            # Not the ESPHome folder's .esphome, which the ESPHome Device Builder app deletes whenever it starts.
            self.assertEqual(got['ESPHOME_DATA_DIR'], str(data / 'esphome'))
            self.assertFalse(got['ESPHOME_DATA_DIR'].startswith(str(Path(tmp) / 'esphome')))
            # ESP-IDF and the compiler cache survive a restart of the app, which empties the container's own cache.
            self.assertEqual(got['ESPHOME_ESP_IDF_PREFIX'], str(data / 'idf'))
            self.assertEqual(got['CCACHE_MAXSIZE'], Firmware.CCACHE_SIZE)
            self.assertEqual(got['PLATFORMIO_CORE_DIR'], str(data / 'platformio'))
            # As many compilers at once as cores, as PlatformIO ran them; ninja alone would start two more.
            self.assertEqual(got['ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT'], str(os.cpu_count() or 1))
            # A compile cache GitHub made answers here (build_cache, app 0.4.49): paths only mapped, the compiler by its
            # version rather than its file date.
            self.assertIn('-fdebug-prefix-map=*', got['CCACHE_IGNOREOPTIONS'])
            self.assertEqual(got['CCACHE_COMPILERCHECK'], '%compiler% --version')

    async def test_limits_of_the_owner_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            data.mkdir()
            with patch.dict(os.environ, {**fake_cli(tmp, data), 'CCACHE_MAXSIZE': '300M', 'ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT': '1'}):
                f = Firmware(Path(tmp) / 'esphome', data)
                f.create(PROFILE)
                f.start({'file': 'kitchen.yaml', 'action': 'build'})
                await f.task
            self.assertEqual(records(data)[0]['CCACHE_MAXSIZE'], '300M')
            self.assertEqual(records(data)[0]['ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT'], '1')

    async def test_the_apps_own_standing_with_home_assistant_stays_out_of_a_build(self):
        """ESPHome runs a plugin's Python while it builds (docs/PLUGINS.md, "Where a plugin's code runs"): the build gets
        the names the build tools read, and never the Supervisor's token or anything else of the container's."""
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            data.mkdir()
            with patch.dict(os.environ, {**fake_cli(tmp, data), 'SUPERVISOR_TOKEN': 'never', 'HASSIO_TOKEN': 'never',
                                         'ESPHOME_WEB_TOKEN': 'never', 'S6_KEEP_ENV': '1', 'CCACHE_DIR': '/tmp/ccache',
                                         'PLATFORMIO_SETTING': 'yes', 'PIP_ROOT_USER_ACTION': 'ignore'}):
                f = Firmware(Path(tmp) / 'esphome', data)
                f.create(PROFILE)
                f.start({'file': 'kitchen.yaml', 'action': 'build'})
                await f.task
            self.assertEqual(f.job['state'], 'success', list(f.logs))
            names = set(records(data)[0]['names'])
            self.assertFalse(names & {'SUPERVISOR_TOKEN', 'HASSIO_TOKEN', 'ESPHOME_WEB_TOKEN', 'S6_KEEP_ENV'}, names)
            self.assertFalse([n for n in names if 'TOKEN' in n.upper() or 'SECRET' in n.upper() or 'PASSWORD' in n.upper()], names)
            # The tools' own: the path the fake CLI is on, its home, and the families ESPHome, ccache, PlatformIO and pip read.
            self.assertTrue({'PATH', 'ESPHOME_FAKE_DATA', 'CCACHE_DIR', 'PLATFORMIO_SETTING', 'PIP_ROOT_USER_ACTION',
                             'ESPHOME_BUILD_PATH', 'ESPHOME_DATA_DIR', 'PLATFORMIO_CORE_DIR'} <= names, names)

    def test_what_a_build_environment_keeps(self):
        got = build_environment({'PATH': '/bin', 'HOME': '/root', 'LANG': 'C.UTF-8', 'TZ': 'Europe/Amsterdam',
                                 'SUPERVISOR_TOKEN': 'x', 'HASSIO_TOKEN': 'x', 'SUPERVISOR_API': 'http://supervisor',
                                 'ESPHOME_DASHBOARD_USE_PING': '1', 'ESPHOME_API_TOKEN': 'x', 'IDF_TOOLS_PATH': '/data/idf',
                                 'CCACHE_MAXSIZE': '1G', 'GIT_SSL_CAINFO': '/certs', 'PYTHONUNBUFFERED': '1',
                                 'ESP_SCREENS_BUILD_CACHE': 'off', 'S6_CMD_WAIT_FOR_SERVICES': '1', 'HOSTNAME': 'addon',
                                 'MY_PASSWORD': 'x', 'A_SECRET': 'x', 'npm_config_credentials': 'x'})
        self.assertEqual(got, {'PATH': '/bin', 'HOME': '/root', 'LANG': 'C.UTF-8', 'TZ': 'Europe/Amsterdam',
                               'ESPHOME_DASHBOARD_USE_PING': '1', 'IDF_TOOLS_PATH': '/data/idf', 'CCACHE_MAXSIZE': '1G',
                               'GIT_SSL_CAINFO': '/certs', 'PYTHONUNBUFFERED': '1', 'ESP_SCREENS_BUILD_CACHE': 'off'})
        # A token stays out whatever family it is in, and the names themselves spell none.
        self.assertFalse([n for n in BUILD_ENV_NAMES if 'TOKEN' in n or 'SECRET' in n])

    def test_the_supervisor_starts_the_app_again_when_it_stops(self):
        """The app's loops run under one gather: an exception none of them catches ends the process. With Home Assistant's
        Watchdog switch on, the Supervisor starts it again, and with this address also when the app stops answering
        (/health, which the app answers from any address: server.py guard)."""
        config = yaml.safe_load((ROOT / 'screen_manager/config.yaml').read_text())
        self.assertEqual(config.get('watchdog'), 'http://[HOST]:[PORT:8099]/health')

    def test_every_cache_stays_out_of_a_backup(self):
        config = yaml.safe_load((ROOT / 'screen_manager/config.yaml').read_text())
        excluded = set(config['backup_exclude'])
        for folder in ('build', 'esphome', 'idf', 'platformio'):
            self.assertIn(f'*/{folder}/', excluded)
        # Never /data as a whole: screens.json and updates.json are the owner's.
        self.assertFalse({'*', '/data', '*/data/'} & excluded)

    async def test_platformio_from_before_esphome_2026_7_goes_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            (data / 'platformio' / 'packages' / 'toolchain-xtensa-esp32').mkdir(parents=True)
            with patch.dict(os.environ, fake_cli(tmp, data)):
                f = Firmware(Path(tmp) / 'esphome', data)
                f.create(PROFILE)
                # A check of the YAML downloads and builds nothing, so it leaves it.
                f.start({'file': 'kitchen.yaml', 'action': 'validate'})
                await f.task
                self.assertTrue((data / 'platformio' / 'packages').exists())
                # The first build removes it before ESPHome runs.
                f.start({'file': 'kitchen.yaml', 'action': 'build'})
                await f.task
                self.assertEqual(f.job['state'], 'success', list(f.logs))
                self.assertFalse(records(data)[-1]['platformio_left'])
                self.assertIn('Removing PlatformIO from before ESPHome 2026.7: the screens build with ESP-IDF now.', f.logs)
                # Once ESPHome has its own ESP-IDF, whatever PlatformIO gets later is left alone.
                (data / 'idf').mkdir()
                (data / 'platformio' / 'packages').mkdir(parents=True)
                f.start({'file': 'kitchen.yaml', 'action': 'build'})
                await f.task
                self.assertTrue(records(data)[-1]['platformio_left'])
                self.assertTrue((data / 'platformio' / 'packages').exists())
                self.assertNotIn('Removing PlatformIO from before ESPHome 2026.7: the screens build with ESP-IDF now.', f.logs)


if __name__ == '__main__':
    unittest.main()


class TerminalLines(unittest.TestCase):
    """Each line of a build log as a terminal shows it (app 0.4.63), so the editor's bar reads ninja's latest count."""

    def test_only_the_last_update_of_a_rewritten_line_stands(self):
        from firmware import terminal_line
        raw = "[0/2] Re-checking globbed directories...\x1b[K\r[1/1702] Performing build step\x1b[K\r[851/1702] Building C object x.c.obj\x1b[K\n"
        self.assertEqual(terminal_line(raw), '[851/1702] Building C object x.c.obj')
        self.assertEqual(terminal_line('\x1b[01m\x1b[Kmain.cpp:3:\x1b[m\x1b[K warning: x\n'), 'main.cpp:3: warning: x')
        self.assertEqual(terminal_line('INFO Compiling app...\r\n'), 'INFO Compiling app...')
        self.assertEqual(terminal_line('\n'), '')
