"""Building ahead (docs/BUILDS.md, "Building ahead"): in a round the next screen is built while the one before restarts
and is checked, installs only once every screen before it passed its check, and a failure that says nothing about the
firmware puts a screen back at the end of the round instead of ending it."""
import asyncio
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import FIRMWARE_VERSION  # noqa: E402
import test_updates  # noqa: E402


class AheadFirmware(test_updates.FakeFirmware):
    """ESPHome as the round sees it: every job with its start time, the screen on the new version only once its firmware
    went on (install or upload), and a first build of a profile that can stop on the network."""

    def __init__(self, ha):
        super().__init__(ha)
        self.times, self.logs, self.flips, self.network_once = [], [], {'living-room.yaml': True, 'kitchen.yaml': True}, set()

    def start(self, data):
        job = super().start(data)
        self.times.append((data['file'], data['action'], time.monotonic()))
        self.job['stage'] = 'upload' if data['action'] == 'upload' else 'compile'
        return job

    async def run(self, data):
        await asyncio.sleep(0.02)
        self.logs = [f"ESPHome: {data['action']} {data['file']}"]
        if data['action'] == 'build' and data['file'] in self.network_once:
            self.network_once.discard(data['file'])
            self.logs.append('fatal: unable to access https://github.com/x/y/: Could not resolve host: github.com')
            self.job['state'] = 'failed'
            return
        if data['action'] in ('install', 'upload') and self.flips.get(data['file']):
            entity = {'living-room.yaml': 'text.fw1', 'kitchen.yaml': 'text.fw2'}[data['file']]
            self.ha.states[entity] = {'state': FIRMWARE_VERSION}
        self.job['state'] = 'success'


@unittest.skipUnless(test_updates.HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class BuildingAhead(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp):
        m = test_updates.UpdaterTests.setup_manager(self, tmp)
        m.firmware = AheadFirmware(m.ha)
        m.updates.hosts['text.screen2'] = '10.0.0.6'
        m.updates.verify_timeout = 0.3
        return m

    def ended(self, m, screen):
        return [b for b in m.build_queue.ended if b.screen == screen]

    async def test_the_next_screen_builds_while_the_one_before_is_checked_and_installs_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.updates.settle_seconds = 0.3   # the first screen is checked a while: the second builds meanwhile
            await m.updates.launch(['text.screen1', 'text.screen2']).wait()
            jobs = [(file, action) for file, action, _ in m.firmware.times]
            self.assertEqual(jobs, [('living-room.yaml', 'build'), ('living-room.yaml', 'upload'),
                                    ('kitchen.yaml', 'build'), ('kitchen.yaml', 'upload')])
            first_done = self.ended(m, 'text.screen1')[0].finished
            kitchen = {action: at for file, action, at in m.firmware.times if file == 'kitchen.yaml'}
            # Built while the first screen was still being checked, installed only once it had passed.
            self.assertLess(kitchen['build'] - time.monotonic() + time.time(), first_done)
            self.assertGreaterEqual(kitchen['upload'] - time.monotonic() + time.time() + 0.01, first_done)
            self.assertEqual({k: v['state'] for k, v in m.updates.results.items()},
                             {'text.screen1': 'success', 'text.screen2': 'success'})

    async def test_a_screen_that_fails_its_check_keeps_the_one_built_ahead_from_going_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.firmware.flips['living-room.yaml'] = False   # it never reports the new firmware
            await m.updates.launch(['text.screen1', 'text.screen2']).wait()
            jobs = [(file, action) for file, action, _ in m.firmware.times]
            self.assertIn(('kitchen.yaml', 'build'), jobs, 'built ahead while the first was checked')
            self.assertNotIn(('kitchen.yaml', 'upload'), jobs, 'a bad firmware never reaches the next screen')
            self.assertEqual(m.updates.results['text.screen1']['state'], 'failed')
            self.assertEqual(m.updates.results['text.screen2']['state'], 'skipped')

    async def test_a_download_that_did_not_come_puts_the_screen_back_at_the_end_of_the_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.firmware.network_once.add('living-room.yaml')
            round = m.updates.launch(['text.screen1', 'text.screen2'])
            await round.wait()
            await m.build_queue.idle()
            jobs = [(file, action) for file, action, _ in m.firmware.times]
            self.assertEqual(jobs[0], ('living-room.yaml', 'build'))
            self.assertIn(('kitchen.yaml', 'upload'), jobs, 'the round went on')
            self.assertEqual(jobs[-2:], [('living-room.yaml', 'build'), ('living-room.yaml', 'upload')])
            states = [b.state for b in self.ended(m, 'text.screen1')]
            self.assertEqual(sorted(states), ['retry', 'success'])
            self.assertEqual({k: v['state'] for k, v in m.updates.results.items()},
                             {'text.screen1': 'success', 'text.screen2': 'success'})

    async def test_a_board_with_4_mb_built_ahead_waits_for_its_turn_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.updates.settle_seconds = 0.3
            m.updates.word_timeout = 0.01
            # The kitchen's board takes the wide partition table: it goes its own way (Updater.install_wide).
            m.firmware.wide_slots = lambda profile: str(profile).endswith('kitchen.yaml')
            m.firmware.image_size = lambda profile: 0
            m.firmware.NARROW_SLOT = 1
            await m.updates.launch(['text.screen1', 'text.screen2']).wait()
            first_done = self.ended(m, 'text.screen1')[0].finished
            kitchen = [(action, at - time.monotonic() + time.time()) for file, action, at in m.firmware.times if file == 'kitchen.yaml']
            self.assertEqual([action for action, _ in kitchen], ['build', 'install'])
            self.assertLess(kitchen[0][1], first_done, 'built while the first screen was checked')
            self.assertGreaterEqual(kitchen[1][1] + 0.01, first_done, 'installed only after the first passed its check')

    async def test_a_second_build_of_a_screen_waits_while_its_update_waits_beside_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.updates.settle_seconds = 0.3
            m.updates.launch(['text.screen1', 'text.screen2'])
            while not m.build_queue.aside:   # the first screen is being checked, beside the line
                await asyncio.sleep(0.01)
            other = m.build_queue.add('install', 'living-room.yaml',
                                      lambda build: m.build_queue.step({'file': 'living-room.yaml', 'action': 'build'}))
            await m.build_queue.idle()
            first = self.ended(m, 'text.screen1')[0]
            starts = {b.id: b.started for b in m.build_queue.ended}
            self.assertGreaterEqual(starts[other.id], first.finished, 'it waited for the update of its screen to end')

    async def test_a_screen_once_more_keeps_its_plugins_its_log_and_the_round_waits_for_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.firmware.network_once.add('living-room.yaml')
            ended = []
            round = m.updates.launch(['text.screen1', 'text.screen2'])
            first = round.builds[0]
            first.plugins['add'] = ['rain']
            first.ends.append(ended.append)
            await round.wait()   # also the screen once more, which joined the round later
            again = [b for b in self.ended(m, 'text.screen1') if b.attempt == 2][0]
            self.assertEqual(again.state, 'success')
            self.assertEqual(again.plugins['add'], ['rain'], 'what it brought for its plugins goes along')
            self.assertIn(again, ended, 'whoever waits for its end hears of the build that ended for real')
            # Its log is every step's: the build made ahead and its upload.
            self.assertTrue(any('build living-room.yaml' in line for line in again.logs))
            self.assertTrue(any('upload living-room.yaml' in line for line in again.logs))

    async def test_a_screen_updated_alone_builds_and_installs_in_one_go(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.updates.start('text.screen1')
            await m.build_queue.idle()
            self.assertEqual([(f, a) for f, a, _ in m.firmware.times], [('living-room.yaml', 'install')])


if __name__ == '__main__':
    unittest.main()
