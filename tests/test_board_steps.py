"""A board's own steps (docs/BOARD_STEPS.md): board_steps.py whole (the check of a board's steps, a step's state from
what the screen says and what a person said, what is kept), the steps boards.yaml lists, the hello's `steps` as the app
reads it, and the chips' firmware in the app (tools/build_chips.py --check, docs/SECOND_CHIP.md)."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import board_steps  # noqa: E402
import page_delivery  # noqa: E402

# tools/build_chips.py by its path: tools/ on the path would put its i18n.py before the app's.
_spec = importlib.util.spec_from_file_location('build_chips', ROOT / 'tools/build_chips.py')
build_chips = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_chips)

BUZZER = {'id': 'buzzer', 'kind': 'chip_firmware', 'chip': 'indicator-rp2040'}


class TheCheck(unittest.TestCase):
    def test_a_board_without_steps_has_none(self):
        self.assertEqual(board_steps.checked(None), [])
        self.assertEqual(board_steps.checked([]), [])

    def test_a_step_needs_an_id_a_kind_and_what_its_kind_needs(self):
        self.assertEqual(board_steps.checked([BUZZER]), [BUZZER])
        for wrong in ('buzzer', [{'kind': 'chip_firmware'}], [{'id': 'Buzzer', 'kind': 'chip_firmware', 'chip': 'indicator-rp2040'}],
                      [{'id': 'buzzer', 'kind': 'unheard_of'}], [{'id': 'buzzer', 'kind': 'chip_firmware'}],
                      [{'id': 'buzzer', 'kind': 'chip_firmware', 'chip': 'no-such-chip'}],
                      [{'id': 'buzzer', 'kind': 'chip_firmware', 'chip': '../boards'}], [BUZZER, BUZZER]):
            with self.assertRaises(ValueError, msg=wrong):
                board_steps.checked(wrong)


class TheState(unittest.TestCase):
    def state(self, seen, answers=None):
        steps = board_steps.view([BUZZER], seen, answers or {})
        return steps[0]['state'] if steps else None

    def test_the_screen_says_when_a_chips_firmware_is_on(self):
        have = board_steps.chip('indicator-rp2040')['version']
        self.assertEqual(self.state({}), 'open')
        self.assertEqual(self.state({'buzzer': have}), 'done')
        # Something older than the app has is offered again; a person's "done" is no proof where the screen can tell.
        self.assertEqual(self.state({'buzzer': '0.0.1'}), 'update')
        self.assertEqual(self.state({}, {'buzzer': 'done'}), 'open')
        self.assertEqual(self.state({}, {'buzzer': 'later'}), 'later')
        self.assertEqual(self.state({'buzzer': have}, {'buzzer': 'later'}), 'done')

    def test_a_screen_that_says_nothing_of_steps_is_not_asked(self):
        # Its firmware is from before its board had steps, or it has been away since the app started: nobody could tell
        # when the step is done, so it is not offered.
        self.assertIsNone(self.state(None))
        self.assertIsNone(page_delivery.steps_of({'features': []}))
        self.assertEqual(page_delivery.steps_of({'steps': {}}), {})
        self.assertEqual(page_delivery.steps_of({'steps': {'buzzer': '1.0.0', 'x': 3, 4: 'y'}}), {'buzzer': '1.0.0'})

    def test_the_editor_gets_what_it_needs_to_do_it(self):
        step = board_steps.view([BUZZER], {}, {})[0]
        record = board_steps.chip('indicator-rp2040')
        self.assertEqual({key: step[key] for key in ('id', 'kind', 'found', 'chip', 'version', 'size', 'usb', 'drive')},
                         {'id': 'buzzer', 'kind': 'chip_firmware', 'found': '', 'chip': 'indicator-rp2040', 'version': record['version'],
                          'size': record['size'], 'usb': record['usb'], 'drive': record['drive']})
        # Relative, so it works behind ingress; and the file is the one the record names.
        self.assertEqual(step['file'], 'api/chips/indicator-rp2040/firmware')
        data, name = board_steps.chip_file('indicator-rp2040')
        self.assertEqual((len(data), name), (record['size'], step['download']))
        self.assertIsNone(board_steps.chip_file('no-such-chip'))
        self.assertIsNone(board_steps.chip('../boards'))

    def test_versions_compare_as_numbers(self):
        self.assertLess(board_steps.version_tuple('1.9.0'), board_steps.version_tuple('1.10.0'))
        self.assertEqual(board_steps.version_tuple('soon'), ())


class WhatIsKept(unittest.TestCase):
    def test_later_is_kept_over_a_restart_and_goes_with_the_screen(self):
        folder = tempfile.mkdtemp()
        kept = board_steps.BoardSteps(folder)
        kept.answer([BUZZER], 'hall', 'buzzer', 'later')
        self.assertEqual(board_steps.BoardSteps(folder).of('hall'), {'buzzer': 'later'})
        kept.answer([BUZZER], 'hall', 'buzzer', '')
        self.assertEqual(board_steps.BoardSteps(folder).of('hall'), {})
        kept.answer([BUZZER], 'hall', 'buzzer', 'later')
        kept.forget_screen('hall')
        self.assertEqual(board_steps.BoardSteps(folder).of('hall'), {})

    def test_only_a_step_of_the_board_and_a_word_that_exists(self):
        kept = board_steps.BoardSteps(tempfile.mkdtemp())
        for step, said in (('other', 'later'), ('buzzer', 'never'), ('buzzer', 'done')):
            with self.assertRaises(ValueError):
                kept.answer([BUZZER], 'hall', step, said)
        with self.assertRaises(ValueError):
            kept.answer(None, 'hall', 'buzzer', 'later')


class TheCatalog(unittest.TestCase):
    def test_every_step_of_a_board_is_one_the_app_serves_and_the_screen_reports(self):
        shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        english = json.loads((ROOT / 'screen_manager/translations/en.json').read_text())['editor']['steps']
        found = 0
        import yaml
        catalog = yaml.safe_load((ROOT / 'boards.yaml').read_text())
        for board, shape in shapes.items():
            if board not in catalog:
                continue
            steps = (shape.get('catalog') or {}).get('steps') or []
            self.assertEqual(board_steps.checked(steps), steps, board)
            for step in steps:
                found += 1
                # Its words, and where its kind is seen by the screen, the board file's line that says so.
                for key in ('menu', 'title', 'lead', 'note', 'done_title', 'done_lead', 'update_title', 'update_lead'):
                    self.assertIn(key, english[step['id']], (board, step['id']))
                self.assertIn(step['kind'], english['kinds'])
                if board_steps.KINDS[step['kind']]['seen']:
                    file = ROOT / 'packages/boards' / catalog[board]['file']
                    self.assertRegex(file.read_text(), rf'HELLO_BOARD_STEPS:.*steps\["{step["id"]}"\]', board)
        self.assertGreater(found, 0)
        self.assertIn('{ ${HELLO_BOARD_STEPS} }', (ROOT / 'packages/core.yaml').read_text())

    def test_the_chips_firmware_in_the_app_is_built_from_the_sources_as_they_are(self):
        self.assertEqual([found for found in map(build_chips.check, build_chips.chips()) if found], [])
        # And the chip says the version its record names.
        for folder in build_chips.chips():
            about = json.loads((folder / 'chip.json').read_text())
            self.assertEqual(board_steps.chip(about['name'])['version'], (folder / 'version.txt').read_text().strip())

    def test_the_page_and_the_tool_speak_the_chips_words(self):
        header = (ROOT / 'components/chip_link/chip_protocol.h').read_text()
        model = (ROOT / 'web/src/model/board-steps.ts').read_text()
        tool = (ROOT / 'tools/chip.py').read_text()
        for name, value in (('HELLO', '0x01'), ('TRY', '0x14'), ('HELLO_BACK', '0x81')):
            self.assertRegex(header, rf'\b{name} = {value},')
            self.assertRegex(model, rf'\b{name} = {value}\b')
        self.assertIn('HELLO, BEGIN, AUDIO, END, VOLUME, TRY, HELLO_BACK, STATUS = 0x01, 0x10, 0x11, 0x12, 0x13, 0x14, 0x81, 0x90', tool)


if __name__ == '__main__':
    unittest.main()
