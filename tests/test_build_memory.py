"""A build runs as many compilers at once as the machine's memory takes (build_memory, app 0.4.65): fewer when little is
free, once more with one when Linux killed a compiler all the same (GitHub #162), and plain words when even one is more
than the machine has. The job carries the plan, so the editor can say so to the person installing."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import build_memory  # noqa: E402
from firmware import Firmware  # noqa: E402

PROFILE = {'board': 'cyd', 'name': 'kitchen', 'friendly_name': 'Kitchen', 'wifi_ssid': 'ssid', 'wifi_password': 'password'}

# Stands in for the ESPHome CLI: records every run with the compilers it was allowed, and the first FAKE_FAILS compiles
# end as a compile on a machine without memory does, with GCC's line about the killed compiler.
FAKE_CLI = '''#!{python}
import json, os, sys
from pathlib import Path
data = Path(os.environ['FAKE_DATA'])
runs = data / 'runs.jsonl'
before = len(runs.read_text().splitlines()) if runs.exists() else 0
with open(runs, 'a') as out:
    out.write(json.dumps({{'stage': sys.argv[1], 'jobs': os.environ.get('ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT')}}) + '\\n')
if sys.argv[1] == 'compile' and before < int(os.environ['FAKE_FAILS']):
    print('[412/1702] Building CXX object esp-idf/src/CMakeFiles/__idf_src.dir/main.cpp.obj')
    print('xtensa-esp-elf-g++: fatal error: Killed signal terminated program cc1plus')
    print('ninja: build stopped: subcommand failed.')
    sys.exit(1)
print('[850/850] Linking CXX executable kitchen.elf')
'''


def fake_cli(folder, data, fails, free_mb):
    bin_dir = Path(folder) / 'bin'
    bin_dir.mkdir(exist_ok=True)
    cli = bin_dir / 'esphome'
    cli.write_text(FAKE_CLI.format(python=sys.executable))
    cli.chmod(0o755)
    meminfo = Path(folder) / 'meminfo'
    meminfo.write_text(f'MemTotal:        4000000 kB\nMemFree:          200000 kB\nMemAvailable:    {free_mb * 1024} kB\n')
    env = {'PATH': f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", 'FAKE_DATA': str(data), 'FAKE_FAILS': str(fails),
           'ESP_SCREENS_BUILD_CACHE': 'off'}
    return env, str(meminfo)


def runs(data):
    return [json.loads(line) for line in (data / 'runs.jsonl').read_text().splitlines()]


class TheRule(unittest.TestCase):
    def test_one_compiler_for_the_heaviest_file_and_one_more_per_extra(self):
        # Unknown memory (a Mac, a test): the cores, as before.
        self.assertEqual(build_memory.compilers(None, 4), 4)
        # Room for all of them.
        self.assertEqual(build_memory.compilers(8000, 4), 4)
        # 2 GB free: the heaviest file and nothing beside it.
        self.assertEqual(build_memory.compilers(2000, 4), 1)
        # 2.9 GB free: two more fit beside it.
        self.assertEqual(build_memory.compilers(2900, 4), 3)
        # Less than the heaviest file needs: one tries all the same.
        self.assertEqual(build_memory.compilers(900, 8), 1)
        # Never more compilers than cores, and never none.
        self.assertEqual(build_memory.compilers(64000, 2), 2)
        self.assertEqual(build_memory.compilers(0, 0), 1)

    def test_the_plan_says_why_when_it_is_fewer_than_the_cores(self):
        self.assertEqual(build_memory.plan(4, 8000)['reason'], None)
        self.assertEqual(build_memory.plan(4, None)['reason'], None)
        low = build_memory.plan(4, 2000)
        self.assertEqual((low['jobs'], low['reason'], low['cores'], low['free_mb'], low['need_mb']), (1, 'low', 4, 2000, 1500))
        self.assertEqual(build_memory.plan(4, 1200)['reason'], 'tight')
        # One core has nothing to say about memory.
        self.assertEqual(build_memory.plan(1, 2000)['reason'], None)
        # A limit the owner set in the add-on's environment caps the count and is not a reason of its own.
        self.assertEqual(build_memory.plan(8, 8000, 2), {'cores': 8, 'free_mb': 8000, 'need_mb': 1500, 'jobs': 2, 'reason': None})

    def test_linux_counts_the_memory_the_cache_gives_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'meminfo'
            path.write_text('MemTotal:        3884320 kB\nMemFree:          162188 kB\nMemAvailable:    1258292 kB\nBuffers:  1 kB\n')
            self.assertEqual(build_memory.available_mb(str(path)), 1228)
            path.write_text('MemTotal:        3884320 kB\n')
            self.assertIsNone(build_memory.available_mb(str(path)))
            self.assertIsNone(build_memory.available_mb(str(Path(tmp) / 'missing'), str(Path(tmp) / 'nocgroup')))

    def test_a_container_limit_counts_when_it_is_less_than_the_machine(self):
        with tempfile.TemporaryDirectory() as tmp:
            meminfo = Path(tmp) / 'meminfo'
            meminfo.write_text('MemAvailable:    6291456 kB\n')  # 6 GB free on the machine
            v2 = Path(tmp) / 'v2'
            v2.mkdir()
            (v2 / 'memory.max').write_text('max\n')
            (v2 / 'memory.current').write_text('524288000\n')
            # No limit: the machine's count.
            self.assertEqual(build_memory.available_mb(str(meminfo), str(v2)), 6144)
            # A 2 GB limit with 500 MB in use: 1.5 GB is what this container can still take.
            (v2 / 'memory.max').write_text('2147483648\n')
            self.assertEqual(build_memory.available_mb(str(meminfo), str(v2)), 1548)
            # cgroup v1, whose "no limit" is an enormous number.
            v1 = Path(tmp) / 'v1'
            (v1 / 'memory').mkdir(parents=True)
            (v1 / 'memory' / 'memory.limit_in_bytes').write_text('9223372036854771712\n')
            (v1 / 'memory' / 'memory.usage_in_bytes').write_text('524288000\n')
            self.assertEqual(build_memory.available_mb(str(meminfo), str(v1)), 6144)
            (v1 / 'memory' / 'memory.limit_in_bytes').write_text('3221225472\n')
            self.assertEqual(build_memory.available_mb(str(meminfo), str(v1)), 2572)
            # A container limit and no /proc/meminfo.
            self.assertEqual(build_memory.available_mb(str(Path(tmp) / 'missing'), str(v1)), 2572)

    def test_esphome_itself_killed_counts_as_out_of_memory(self):
        self.assertTrue(build_memory.killed_exit(-9))
        self.assertTrue(build_memory.killed_exit(137))
        self.assertFalse(build_memory.killed_exit(1))
        self.assertFalse(build_memory.killed_exit(0))

    def test_the_lines_of_a_compiler_stopped_for_memory(self):
        self.assertTrue(build_memory.killed('xtensa-esp-elf-g++: fatal error: Killed signal terminated program cc1plus'))
        self.assertTrue(build_memory.killed('collect2: fatal error: ld terminated with signal 9 [Killed]'))
        self.assertTrue(build_memory.killed('cc1plus: out of memory allocating 65536 bytes'))
        self.assertTrue(build_memory.killed('virtual memory exhausted: Cannot allocate memory'))
        self.assertFalse(build_memory.killed('[412/1702] Building CXX object main.cpp.obj'))
        self.assertFalse(build_memory.killed('error: expected ; before }'))


class TheBuild(unittest.IsolatedAsyncioTestCase):
    async def build(self, tmp, fails, free_mb, cores=4):
        data = Path(tmp) / 'data'
        data.mkdir(exist_ok=True)
        env, meminfo = fake_cli(tmp, data, fails, free_mb)
        with patch.dict(os.environ, env), patch('os.cpu_count', return_value=cores), patch.object(Firmware, 'MEMINFO', meminfo), \
                patch.object(Firmware, 'CGROUP', str(Path(tmp) / 'nocgroup')):
            os.environ.pop('ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT', None)
            f = Firmware(Path(tmp) / 'esphome', data)
            f.create(PROFILE)
            f.start({'file': 'kitchen.yaml', 'action': 'build'})
            await f.task
        return f, runs(data)

    async def test_a_machine_with_room_builds_with_every_core_and_says_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            f, done = await self.build(tmp, fails=0, free_mb=8000)
            self.assertEqual(f.job['state'], 'success', list(f.logs))
            self.assertEqual([run['jobs'] for run in done], ['4'])
            self.assertIsNone(f.job['memory']['reason'])
            self.assertFalse([line for line in f.logs if 'memory' in line])

    async def test_little_memory_starts_with_fewer_compilers_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            f, done = await self.build(tmp, fails=0, free_mb=2900)
            self.assertEqual(f.job['state'], 'success', list(f.logs))
            self.assertEqual([run['jobs'] for run in done], ['3'])
            self.assertEqual(f.job['memory'], {'cores': 4, 'free_mb': 2900, 'need_mb': 1500, 'jobs': 3, 'reason': 'low'})
            self.assertIn('This machine has 2.8 GB of memory free, so the build runs 3 compiler(s) at a time instead of 4. '
                          'That takes longer, but it fits.', f.logs)

    async def test_a_killed_compiler_builds_again_with_one_from_where_it_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            f, done = await self.build(tmp, fails=1, free_mb=8000)
            self.assertEqual(f.job['state'], 'success', list(f.logs))
            # The first run with every core, the second with one; ninja keeps what the first got done.
            self.assertEqual([(run['stage'], run['jobs']) for run in done], [('compile', '4'), ('compile', '1')])
            self.assertEqual(f.job['memory']['reason'], 'retry')
            self.assertEqual(f.job['memory']['jobs'], 1)
            logs = list(f.logs)
            self.assertIn('The compiler ran out of memory and was stopped. Building again with one compiler at a time, from '
                          'where it stopped. That takes longer, but it fits.', logs)
            # Both runs stand in the log, so the editor's bar goes on from the first run's count.
            self.assertEqual(logs.count('ESPHome: compile'), 2)
            self.assertEqual(logs[-1], 'Succeeded: build')

    async def test_too_little_memory_for_one_compiler_fails_in_plain_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            f, done = await self.build(tmp, fails=2, free_mb=1200)
            self.assertEqual(f.job['state'], 'failed')
            # One compiler was all it had: nothing to try again with.
            self.assertEqual([run['jobs'] for run in done], ['1'])
            self.assertEqual(f.job['memory']['reason'], 'out')
            logs = list(f.logs)
            self.assertIn('Building needs about 1.5 GB of free memory and this machine has 1.2 GB: trying with one compiler at a time.', logs)
            self.assertEqual(logs[-1], 'The compiler ran out of memory: building the firmware needs about 1.5 GB of free memory '
                                       'and this machine has 1.2 GB. Stop a few add-ons for a while or give the machine more '
                                       'memory, then try again.')

    async def test_a_machine_that_said_enough_was_free_gets_no_numbers_that_contradict_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 8 GB free, yet killed twice: a limit on the app's own memory, which /proc/meminfo does not show.
            f, done = await self.build(tmp, fails=2, free_mb=8000)
            self.assertEqual(f.job['state'], 'failed')
            self.assertEqual([run['jobs'] for run in done], ['4', '1'])
            self.assertEqual(f.job['memory']['reason'], 'limit')
            self.assertEqual(list(f.logs)[-1], 'The compiler ran out of memory, also with one compiler at a time. Stop a few '
                                               'add-ons for a while or give the machine more memory, then try again.')

    async def test_esphome_killed_without_a_word_builds_again_with_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            data.mkdir()
            env, meminfo = fake_cli(tmp, data, fails=0, free_mb=8000)
            marker = Path(tmp) / 'killed_once'
            (Path(tmp) / 'bin' / 'esphome').write_text(
                f'#!{sys.executable}\nimport os, signal, sys\nfrom pathlib import Path\nm = Path({str(marker)!r})\n'
                'if sys.argv[1] == "compile" and not m.exists():\n    m.write_text("1")\n    os.kill(os.getpid(), signal.SIGKILL)\n'
                'print("[850/850] Linking")\n')
            with patch.dict(os.environ, env), patch('os.cpu_count', return_value=4), \
                    patch.object(Firmware, 'MEMINFO', meminfo), patch.object(Firmware, 'CGROUP', str(Path(tmp) / 'nocgroup')):
                f = Firmware(Path(tmp) / 'esphome', data)
                f.create(PROFILE)
                f.start({'file': 'kitchen.yaml', 'action': 'build'})
                await f.task
            self.assertEqual(f.job['state'], 'success', list(f.logs))
            self.assertEqual(f.job['memory']['reason'], 'retry')
            self.assertEqual(list(f.logs).count('ESPHome: compile'), 2)

    async def test_a_build_that_fails_for_another_reason_is_not_tried_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            data.mkdir()
            env, meminfo = fake_cli(tmp, data, fails=0, free_mb=8000)
            # A CLI that fails with an ordinary error.
            (Path(tmp) / 'bin' / 'esphome').write_text(f'#!{sys.executable}\nprint("error: expected ; before }}")\nraise SystemExit(1)\n')
            with patch.dict(os.environ, env), patch.object(Firmware, 'MEMINFO', meminfo), \
                    patch.object(Firmware, 'CGROUP', str(Path(tmp) / 'nocgroup')):
                f = Firmware(Path(tmp) / 'esphome', data)
                f.create(PROFILE)
                f.start({'file': 'kitchen.yaml', 'action': 'build'})
                await f.task
            self.assertEqual(f.job['state'], 'failed')
            self.assertEqual(list(f.logs).count('ESPHome: compile'), 1)
            self.assertEqual(list(f.logs)[-1], 'ESPHome compile failed; see the log.')


if __name__ == '__main__':
    unittest.main()
