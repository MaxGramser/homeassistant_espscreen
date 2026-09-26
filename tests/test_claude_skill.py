"""The Claude Code skill behind Alerts → Install for Claude: complete, valid, and written only on request."""
import asyncio
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import claude_skill  # noqa: E402
import tile_icons  # noqa: E402
from core import (ALERT_EVENT, ALERT_FIELDS, ALERT_LIMITS, ALERT_MIN_FIRMWARE, AUTO_STANDBY_MIN_FIRMWARE, BROADCAST_DISMISS,  # noqa: E402
                  BROADCAST_SHOW, CONTROLS, DISPLAYS, TILE_BACKGROUNDS, TILE_EVENTS, TILE_RESULT_EVENT,
                  WAKE_SLEEP_MIN_FIRMWARE, DARK_MODE_MIN_FIRMWARE)

HAS_YAML = importlib.util.find_spec('yaml') is not None
HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app


class SkillText(unittest.TestCase):
    def test_frontmatter_names_the_skill_and_says_when_to_use_it(self):
        text = claude_skill.text()
        front = re.match(r'---\nname: (.+)\ndescription: (.+)\n---\n', text)
        self.assertIsNotNone(front)
        self.assertEqual(front[1], 'esp-screens')
        self.assertLessEqual(len(front[2]), 200, 'claude.ai refuses longer descriptions')
        for words in ('ESP Screens', 'tile', 'order', 'alert', 'awake'):
            self.assertIn(words, front[2])
        self.assertEqual(text, claude_skill.text(), 'same text every time, so status() can compare')
        self.assertNotRegex(text, r'\{[A-Z_]+\}', 'no placeholder left over')
        self.assertLess(text.count('\n'), 500, 'Claude Code advises SKILL.md under 500 lines')

    def test_it_carries_everything_the_cheatsheet_does(self):
        text = claude_skill.text()
        for needle in (BROADCAST_SHOW, BROADCAST_DISMISS, ALERT_EVENT, ALERT_MIN_FIRMWARE, '_show_alert', '_dismiss_alert'):
            self.assertIn(needle, text)
        for name, kind, *_ in ALERT_FIELDS:
            self.assertRegex(text, rf'\| `{name}` \| ', name)
        for field, limit in ALERT_LIMITS['standard'].items():
            self.assertIn(f"CYD {ALERT_LIMITS['compact'][field]} · Guition and Waveshare {limit} bytes", text)
        for name, item in TILE_BACKGROUNDS.items():
            if item['color']:
                self.assertIn(f'`{name}`', text)
        # Standby from automations (0.2.48): the switch, the numbers and when the switch arrived.
        standby = text.split('## Standby and brightness', 1)[1]
        for entity in ('switch.<screen>_auto_standby', 'number.<screen>_standby_after', 'number.<screen>_normal_brightness',
                       'number.<screen>_standby_brightness', 'number.<screen>_night_brightness'):
            self.assertIn(f'`{entity}`', standby)
        self.assertIn(AUTO_STANDBY_MIN_FIRMWARE, standby)
        # Wake and Sleep (0.2.53): the buttons, when they arrived, and how to press several at once.
        for entity in ('button.<screen>_wake', 'button.<screen>_sleep'):
            self.assertIn(f'`{entity}`', standby)
        self.assertIn(f'Firmware {WAKE_SLEEP_MIN_FIRMWARE} or newer', standby)
        # Dark mode (0.2.63): the switch and the firmware that has it.
        self.assertIn('`switch.<screen>_dark_mode`', standby)
        self.assertIn(f'Firmware {DARK_MODE_MIN_FIRMWARE} or newer', standby)
        self.assertIn('`button.press`', standby)
        self.assertIn('(#standby-and-brightness)', text, 'the intro links to the section')
        # Tiles (0.2.51): the events, what a tile can do per domain, how to read a screen and the rule to ask first.
        tiles = text.split('## Tiles on a screen', 1)[1].split('## All screens', 1)[0]
        for event in TILE_EVENTS:
            self.assertIn(f'`{event}`', tiles)
        self.assertIn(TILE_RESULT_EVENT, tiles)
        self.assertIn('sensor.esp_screens_<device name>', tiles)
        for domain, choices in CONTROLS.items():
            self.assertRegex(tiles, rf'\| `{domain}` \|' + ''.join(rf'.*`{key}`' for key, _ in choices))
        for domain, names in DISPLAYS.items():
            for name in names:
                self.assertIn(f'`{name}`', tiles)
        self.assertIn('wait for a yes', tiles)
        self.assertIn('(#tiles-on-a-screen)', text, 'the intro links to the section')
        icons = text.split('## Icons', 1)[1].split('## When an alert ends', 1)[0]
        self.assertEqual(set(re.findall(r'`([a-z0-9-]+)`', icons)) - {'icon'}, set(tile_icons.GLYPHS), 'exactly the glyphs the firmware carries')

    @unittest.skipUnless(HAS_YAML, 'PyYAML needed')
    def test_every_yaml_example_parses(self):
        import yaml
        blocks = re.findall(r'```yaml\n(.*?)```', claude_skill.text(), re.S)
        self.assertEqual(len(blocks), 13)
        parsed = [yaml.safe_load(block) for block in blocks]
        # Tiles first (0.2.51): putting one on a screen, and ordering a page.
        self.assertEqual(parsed[0]['actions'][0]['event'], 'esp_screens_add_tile')
        self.assertEqual(set(parsed[0]['actions'][0]['event_data']), {'screen', 'entity'})
        self.assertEqual(parsed[1]['actions'][0]['event'], 'esp_screens_order_tiles')
        self.assertEqual(set(parsed[1]['actions'][0]['event_data']), {'screen', 'page', 'entities'})
        self.assertEqual(parsed[2]['actions'][0]['event'], BROADCAST_SHOW)
        self.assertEqual(set(parsed[2]['actions'][0]['event_data']), {name for name, *_ in ALERT_FIELDS})
        # One screen through the event (0.2.133): `screen` with a camera, which the screen's own action cannot take.
        one = parsed[3]['actions'][0]
        self.assertEqual(one['event'], BROADCAST_SHOW)
        self.assertEqual((one['event_data']['screen'], one['event_data']['camera']), ('kitchen-screen', 'camera.front_door'))
        self.assertEqual(set(parsed[4]['actions'][0]['data']), {name for name, *_ in ALERT_FIELDS}, 'the per-screen action needs all seven')
        # Two buttons (firmware 0.3.3+): the second button's text and both colours, through the event.
        choice = parsed[5]['actions'][0]['event_data']
        self.assertEqual((choice['button2_text'], choice['button_color'], choice['button2_color']), ('Not now', 'green', 'red'))
        self.assertEqual(parsed[6][0]['wait_for_trigger'][0]['event_type'], ALERT_EVENT)
        choose = parsed[7]['actions'][0]['choose']
        self.assertEqual([option['sequence'][0]['event'] for option in choose], [BROADCAST_SHOW, BROADCAST_DISMISS])
        # Open a page (0.2.102): the per-screen action with its one field.
        opened = parsed[8]['actions'][0]
        self.assertTrue(opened['action'].startswith('esphome.') and opened['action'].endswith('_show_page'))
        self.assertEqual(opened['data'], {'page': 4})
        # Wake on motion for one screen, Sleep for two, each branch on its own trigger.
        buttons = parsed[9]
        options = buttons['actions'][0]['choose']
        self.assertEqual({trigger['id'] for trigger in buttons['triggers']}, {option['conditions'][0]['id'] for option in options})
        pressed = []
        for option in options:
            step = option['sequence'][0]
            self.assertEqual(step['action'], 'button.press')
            targets = step['target']['entity_id']
            pressed.append([targets] if isinstance(targets, str) else targets)
        self.assertTrue(all(entity.startswith('button.') and entity.endswith('_wake') for entity in pressed[0]))
        self.assertTrue(all(entity.startswith('button.') and entity.endswith('_sleep') for entity in pressed[1]))
        self.assertGreater(len(pressed[1]), 1, 'shows how to reach several screens at once')
        awake = parsed[10]
        self.assertEqual(awake['mode'], 'restart')
        branch = awake['actions'][0]
        self.assertEqual((branch['then'][0]['action'], branch['else'][0]['action']), ('switch.turn_off', 'switch.turn_on'))
        self.assertTrue(branch['then'][0]['target']['entity_id'].endswith('_auto_standby'))
        watched = set(awake['triggers'][0]['entity_id'])
        conditions = {branch['if'][0]['entity_id']} | {c['entity_id'] for c in branch['if'][1]['conditions']}
        self.assertEqual(watched, conditions, 'the automation reacts to every entity its condition reads')
        # Dark mode at night (0.2.63): one automation that turns the switch on at one time and off at the other.
        night = parsed[11]
        self.assertEqual({trigger['id'] for trigger in night['triggers']}, {'night', 'day'})
        branch = night['actions'][0]
        self.assertEqual((branch['if'][0]['condition'], branch['if'][0]['id']), ('trigger', 'night'))
        self.assertEqual((branch['then'][0]['action'], branch['else'][0]['action']), ('switch.turn_on', 'switch.turn_off'))
        for step in (branch['then'][0], branch['else'][0]):
            self.assertTrue(step['target']['entity_id'].endswith('_dark_mode'))


class Archive(unittest.TestCase):
    def test_zip_holds_the_skill_folder_as_claude_ai_expects(self):
        import io
        import zipfile
        data = claude_skill.archive()
        self.assertEqual(data, claude_skill.archive(), 'same bytes every time')
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            self.assertEqual(bundle.namelist(), ['esp-screens/SKILL.md'])
            self.assertEqual(bundle.read('esp-screens/SKILL.md').decode('utf8'), claude_skill.text())


class Install(unittest.TestCase):
    def test_status_install_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = claude_skill.skill_dir(tmp)
            self.assertEqual(target, Path(tmp) / '.claude' / 'skills' / 'esp-screens')
            self.assertEqual(claude_skill.status(target), {'installed': False, 'current': False, 'path': str(target)})
            first = claude_skill.install(target)
            self.assertEqual(first, {'installed': True, 'current': True, 'path': str(target), 'restart': True})
            self.assertEqual((target / 'SKILL.md').read_text(encoding='utf8'), claude_skill.text())
            self.assertEqual(sorted(p.name for p in target.iterdir()), ['SKILL.md'], 'no temp file left behind')
            self.assertFalse(claude_skill.install(target)['restart'], 'the skills folder already existed')
            (target / 'SKILL.md').write_text('older text', encoding='utf8')
            self.assertEqual(claude_skill.status(target)['current'], False)
            self.assertTrue(claude_skill.install(target)['current'])

    def test_a_new_skill_next_to_existing_skills_needs_no_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / '.claude' / 'skills' / 'other').mkdir(parents=True)
            self.assertFalse(claude_skill.install(claude_skill.skill_dir(tmp))['restart'])
            self.assertTrue((Path(tmp) / '.claude' / 'skills' / 'other').is_dir(), 'other skills untouched')

    def test_a_folder_that_cannot_be_written_gives_a_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / '.claude').write_text('a file, not a folder')
            with self.assertRaises(ValueError) as caught:
                claude_skill.install(claude_skill.skill_dir(tmp))
            self.assertIn("Couldn't write the skill", str(caught.exception))


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Endpoint(unittest.IsolatedAsyncioTestCase):
    async def test_inventory_reports_and_the_button_installs(self):
        class HA:
            online = True
            registry, devices, areas, states = [], [], [], {}
            changed = asyncio.Event()
        with tempfile.TemporaryDirectory() as tmp:
            manager = Manager(HA(), Path(tmp) / 'data' / 'screens.json')
            manager.skill_dir = claude_skill.skill_dir(Path(tmp) / 'config')
            async with TestClient(TestServer(create_app(manager, True))) as client:
                full = await (await client.get('/api/inventory')).json()
                self.assertEqual(full['claude_skill'], {'installed': False, 'current': False, 'path': str(manager.skill_dir)})
                self.assertNotIn('claude_skill', await (await client.get('/api/inventory?light=1')).json())
                download = await client.get('/api/claude-skill.zip')
                self.assertEqual(download.status, 200)
                self.assertEqual(download.headers['Content-Type'], 'application/zip')
                self.assertEqual(download.headers['Content-Disposition'], 'attachment; filename="esp-screens.zip"')
                self.assertEqual(await download.read(), claude_skill.archive())
                self.assertFalse(manager.skill_dir.exists(), 'opening the page or downloading writes nothing')
                refused = await client.post('/api/claude-skill')
                self.assertEqual(refused.status, 403, 'CSRF like every other change')
                response = await client.post('/api/claude-skill', headers={'X-Screen-CSRF': full['csrf']})
                self.assertEqual(await response.json(), {'installed': True, 'current': True, 'path': str(manager.skill_dir), 'restart': True})
                self.assertTrue((manager.skill_dir / 'SKILL.md').is_file())
                (Path(tmp) / 'blocked').write_text('a file, not a folder')
                manager.skill_dir = claude_skill.skill_dir(Path(tmp) / 'blocked')
                failed = await client.post('/api/claude-skill', headers={'X-Screen-CSRF': full['csrf']})
                self.assertEqual(failed.status, 400)
                self.assertIn("Couldn't write the skill", (await failed.json())['error'])


if __name__ == '__main__':
    unittest.main()
