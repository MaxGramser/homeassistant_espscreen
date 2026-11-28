"""Every build's log kept on disk (build_logs.py, docs/BUILDS.md "Kept logs"): written line by line while ESPHome writes
it, so a build the app restarted during still has its log, and offered by its key to the page."""
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
from build_logs import BuildLogs, Tee  # noqa: E402
from build_queue import BuildQueue  # noqa: E402


class Firmware:
    """ESPHome as the line sees it, with the app's own log (a Tee that Firmware.start clears, never replaces)."""

    def __init__(self):
        self.task, self.job, self.logs, self.fail, self.gate = None, None, Tee(300), False, None

    def start(self, data):
        self.logs.clear()
        self.logs.append(f"ESPHome: {data['action']} {data['file']}")
        self.job = {'file': data['file'], 'action': data['action'], 'state': 'running'}
        self.task = asyncio.get_running_loop().create_task(self.run())

    async def run(self):
        self.logs.append('Compiling src/main.cpp')
        if self.gate:
            await self.gate.wait()
        self.logs.append('ERROR it broke' if self.fail else 'Succeeded: install')
        self.job['state'] = 'failed' if self.fail else 'success'


class Owner:
    def __init__(self, data):
        self.firmware = Firmware()
        self.build_logs = BuildLogs(data)
        self.build_queue = BuildQueue(self)

    def notify(self):
        pass


def install(line, file):
    async def run(build):
        return 'success' if await line.step({'file': file, 'action': 'install', 'target': ''}) else 'failed'
    return run


class KeptLogs(unittest.IsolatedAsyncioTestCase):
    async def test_a_failed_build_keeps_its_whole_log_with_how_it_ended(self):
        with tempfile.TemporaryDirectory() as data:
            owner = Owner(data)
            owner.firmware.fail = True
            line = owner.build_queue
            build = line.add('plugins', 'wallbox.yaml', install(line, 'wallbox.yaml'), screen='wallbox',
                             plugins={'add': ['buienradar']})
            await line.idle()
            self.assertEqual(build.state, 'failed')
            self.assertTrue(build.log)
            self.assertEqual(line.view(build)['log'], build.log)
            text = owner.build_logs.path(build.log).read_text()
            self.assertIn('ESPHome: install wallbox.yaml', text)
            self.assertIn('ERROR it broke', text)
            self.assertTrue(text.rstrip().endswith('# Ended: failed'))
            [kept] = owner.build_logs.listed()
            self.assertEqual((kept['key'], kept['file'], kept['state'], kept['plugins']),
                             (build.log, 'wallbox.yaml', 'failed', ['buienradar']))
            self.assertEqual(owner.build_logs.latest('wallbox.yaml'), build.log)
            # The next build of the app no longer writes into it.
            self.assertIsNone(owner.firmware.logs.sink)

    async def test_a_build_the_app_restarted_during_keeps_what_it_wrote(self):
        with tempfile.TemporaryDirectory() as data:
            owner = Owner(data)
            owner.firmware.gate = asyncio.Event()
            line = owner.build_queue
            build = line.add('plugins', 'wallbox.yaml', install(line, 'wallbox.yaml'), screen='wallbox')
            for _ in range(5):
                await asyncio.sleep(0)
            # The app stops here: what was written is on disk already, and a new app reads it as interrupted.
            after = BuildLogs(data)
            [kept] = after.listed()
            self.assertEqual(kept['state'], 'interrupted')
            self.assertIn('Compiling src/main.cpp', after.path(build.log).read_text())
            owner.firmware.gate.set()
            await line.idle()

    async def test_only_the_newest_are_kept_and_a_key_names_nothing_else(self):
        with tempfile.TemporaryDirectory() as data:
            owner = Owner(data)
            owner.build_logs.KEEP = 3
            line = owner.build_queue
            for n in range(5):
                line.add('update', f'screen{n}.yaml', install(line, f'screen{n}.yaml'))
                await line.idle()
            listed = owner.build_logs.listed()
            self.assertEqual(len(listed), 3)
            self.assertEqual([item['file'] for item in listed], ['screen4.yaml', 'screen3.yaml', 'screen2.yaml'])
            for bad in ('../screens', '20261123-101010-../../x', 'nope'):
                with self.assertRaises(ValueError):
                    owner.build_logs.path(bad)


if __name__ == '__main__':
    unittest.main()
