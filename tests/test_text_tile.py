"""The template tile (screen_manager/app/text_tile.py, template_service.py, firmware 0.58.0): a rendered template turned
into the rows a screen draws, kept within the screen's budget, and Home Assistant's results paced to the screens."""
import asyncio
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import core  # noqa: E402
import page_delivery  # noqa: E402
import template_service  # noqa: E402
import text_tile  # noqa: E402

P, B, G, A, C = range(5)


def layout(**options):
    return {'title': 'Keuken', 'tiles': [{'entity': 'screen.text', 'options': options}]}


class Rows(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(text_tile.rows('# Kitchen\nplain words\n- empty the **dishwasher**\n'), [
            ['h', [[P, 'Kitchen']]],
            ['p', [[P, 'plain words']]],
            ['li', [[P, 'empty the '], [B, 'dishwasher']]],
        ])

    def test_headings_of_every_level_and_star_bullets(self):
        self.assertEqual([row[0] for row in text_tile.rows('## Two\n### Three\n* star')], ['h', 'h', 'li'])

    def test_blank_lines_and_spaces_go(self):
        self.assertEqual(text_tile.rows('\n\n  \n   tidy   \n\n'), [['p', [[P, 'tidy']]]])

    def test_tones(self):
        self.assertEqual(text_tile.inline(':good[charged], :alert[low]'), [[G, 'charged'], [P, ', '], [A, 'low']])
        self.assertEqual(text_tile.inline(':accent[note]'), [[C, 'note']])

    def test_an_unknown_tone_is_text(self):
        self.assertEqual(text_tile.inline(':purple[x]'), [[P, ':purple[x]']])

    def test_a_table_with_its_head(self):
        out = text_tile.rows('| | Planned | Applied |\n|---|---|---|\n| Target | 80 % | **75** % |')
        self.assertEqual(out, [
            ['th', [[[P, '']], [[P, 'Planned']], [[P, 'Applied']]]],
            ['t', [[[P, 'Target']], [[P, '80 %']], [[B, '75'], [P, ' %']]]],
        ])

    def test_a_table_has_four_columns_at_most(self):
        self.assertEqual(len(text_tile.rows('|a|b|c|d|e|f|')[0][1]), 4)

    def test_aligned_rule_lines(self):
        self.assertEqual(text_tile.rows('|a|b|\n|:--|--:|')[0][0], 'th')

    def test_runs_per_row_are_capped(self):
        runs = text_tile.inline('**a** **b** **c** **d** **e**')
        self.assertEqual(len(runs), text_tile.MAX_RUNS)
        self.assertEqual(runs[-1], [P, ' c d e'])

    def test_a_long_row_is_cut(self):
        runs = text_tile.inline('x' * 500)
        self.assertEqual(len(runs[0][1]), text_tile.MAX_ROW_TEXT + 1)
        self.assertTrue(runs[0][1].endswith(text_tile.ELLIPSIS))

    def test_rows_are_capped_with_an_ellipsis(self):
        out = text_tile.rows('\n'.join(f'line {n}' for n in range(40)))
        self.assertEqual(len(out), text_tile.MAX_ROWS)
        self.assertEqual(out[-1], ['p', [[P, 'line 23' + text_tile.ELLIPSIS]]])

    def test_typography_the_fonts_lack_becomes_plain(self):
        self.assertEqual(text_tile.rows('Net \u22121,1\u202fkW \u2013 \u201cok\u201d'), [['p', [[P, 'Net -1,1 kW - "ok"']]]])

    def test_nothing_is_no_rows(self):
        self.assertEqual(text_tile.block('  \n '), {'v': 1, 'r': []})


class Budget(unittest.TestCase):
    def test_the_block_fits_the_budget(self):
        text = '\n'.join(f'- item number {n} with some words' for n in range(24))
        block = text_tile.block(text, 512)
        self.assertLessEqual(text_tile.size(block), 512)
        self.assertLess(len(block['r']), 24)
        self.assertTrue(block['r'][-1][1][-1][1].endswith(text_tile.ELLIPSIS))

    def test_size_is_the_compact_json(self):
        block = text_tile.block('# Hé')
        self.assertEqual(text_tile.size(block), len(json.dumps(block, ensure_ascii=False, separators=(',', ':')).encode()))

    def test_the_budget_has_bounds(self):
        long = '\n'.join('y' * 200 for _ in range(24))
        self.assertLessEqual(text_tile.size(text_tile.block(long, 10 ** 6)), text_tile.MAX_BYTES)
        self.assertLessEqual(text_tile.size(text_tile.block(long, 1)), 256)

    def test_a_screen_says_its_own(self):
        caps = page_delivery.caps_of({'caps': {'text_tiles': 6, 'text_bytes': 3584}})
        self.assertEqual(text_tile.budget_of(None, caps), (3584, 6))
        self.assertEqual(text_tile.budget_of(None, page_delivery.caps_of({})), (text_tile.DEFAULT_BYTES, text_tile.DEFAULT_TILES))

    def test_an_error_is_one_short_line(self):
        block = text_tile.error('UndefinedError:\n  ' + 'x' * 400)
        self.assertEqual(block['v'], 1)
        self.assertEqual(len(block['e']), text_tile.MAX_ERROR)
        self.assertNotIn('\n', block['e'])


class Layout(unittest.TestCase):
    def test_the_template_is_kept(self):
        tile = core.validate_layout(layout(template='{{ 1 }}'))['tiles'][0]
        self.assertEqual(tile['options'], {'template': '{{ 1 }}'})

    def test_faces_and_sliders_go(self):
        tile = core.validate_layout(layout(template='x', display='watch', inline='slider', sub='last_changed'))['tiles'][0]
        self.assertEqual(tile['options'], {'template': 'x'})

    def test_an_empty_or_long_template_is_refused(self):
        for template in ('', '   ', 'x' * (text_tile.MAX_TEMPLATE + 1), 5):
            with self.assertRaises(ValueError):
                core.validate_layout(layout(template=template))

    def test_taps(self):
        core.validate_layout(layout(template='x', tap='none'))
        for tap in ('detail', 'action', 'toggle'):
            with self.assertRaises(ValueError):
                core.validate_layout(layout(template='x', tap=tap, action={'action': 'script.turn_on'}))

    def test_another_tile_keeps_no_template(self):
        tile = core.validate_layout({'title': 'x', 'tiles': [{'entity': 'light.desk', 'options': {'template': 'x'}}]})['tiles'][0]
        self.assertNotIn('template', tile.get('options', {}))

    def test_the_template_never_travels(self):
        self.assertNotIn('template', core.screen_options({'entity': 'screen.text', 'options': {'template': 'x', 'size': '2x2'}}, {}) or {})

    def test_a_screen_without_the_module_cannot_draw_it(self):
        tiles = core.validate_layout(layout(template='x'))['tiles']
        self.assertTrue(text_tile.unsupported(tiles, {'live', 'pictures'}))
        self.assertFalse(text_tile.unsupported(tiles, {'text_card'}))
        self.assertFalse(text_tile.unsupported([{'entity': 'light.desk'}], set()))
        self.assertLess(core.min_firmware(core.validate_layout(layout(template='x'))), (0, 58, 0))


class Limits(unittest.TestCase):
    """The screen's numbers (module_text_card.h, said in its hello) and the app's (text_tile.py) are one set, and the
    largest budget leaves room for the rest of a state message (page_delivery.MAX_MESSAGE)."""
    def test_screen_and_app_agree(self):
        import re
        header = (ROOT / 'components/smart_display/module_text_card.h').read_text()
        budgets = [int(n) for n in re.findall(r'constexpr unsigned MAX_BYTES = (\d+);', header)]
        self.assertEqual(sorted(budgets), [text_tile.DEFAULT_BYTES, text_tile.MAX_BYTES])  # an S3's and a P4's
        self.assertLessEqual(text_tile.MAX_BYTES + 512, page_delivery.MAX_MESSAGE)
        self.assertIn(f'MAX_TILES = {text_tile.DEFAULT_TILES};', header)
        self.assertIn(f'MAX_ROWS = {text_tile.MAX_ROWS}, MAX_CELLS = {text_tile.MAX_COLUMNS}, MAX_RUNS = {text_tile.MAX_RUNS};', header)

    def test_the_fullest_tile_fits_a_message(self):
        tile = {'entity': 'screen.text', 'name': 'x' * 80, 'options': {'size': '4x4'}}
        block = text_tile.block('\n'.join('- ' + 'y' * 200 for _ in range(30)), text_tile.MAX_BYTES)
        message = core.state_message(255, tile, {}, {'md': block})
        page_delivery.bounded({**message, 'v': 2, 'session': '0' * 16, 'seq': 0xFFFFFFFF, 'rev': 'f' * 16})


class FakeHa:
    def __init__(self):
        self.online, self.connection, self.dirty, self.changed = True, 1, set(), asyncio.Event()
        self.subs, self.ended, self.next = {}, [], 0
        self.refuse = set()

    async def subscribe_template(self, template, callback):
        if template in self.refuse:
            raise template_service.Refused('TemplateSyntaxError: unexpected end')
        self.next += 1
        self.subs[self.next] = (template, callback)
        return self.next

    async def unsubscribe_template(self, key):
        self.ended.append(key)
        self.subs.pop(key, None)

    def send(self, template, event):
        for wanted, callback in list(self.subs.values()):
            if wanted == template:
                callback(event)


class Service(unittest.IsolatedAsyncioTestCase):
    async def test_subscribes_once_and_ends_what_went(self):
        ha = FakeHa()
        service = template_service.TemplateService(ha)
        await service.sync({'a', 'b'})
        await service.sync({'a', 'b'})
        self.assertEqual(sorted(t for t, _ in ha.subs.values()), ['a', 'b'])
        await service.sync({'a'})
        self.assertEqual([t for t, _ in ha.subs.values()], ['a'])
        self.assertEqual(len(ha.ended), 1)

    async def test_a_new_connection_subscribes_again(self):
        ha = FakeHa()
        service = template_service.TemplateService(ha)
        await service.sync({'a'})
        ha.connection, ha.subs = 2, {}
        await service.sync({'a'})
        self.assertEqual([t for t, _ in ha.subs.values()], ['a'])
        self.assertEqual(ha.ended, [])  # the old websocket took its subscriptions with it

    async def test_offline_keeps_the_last_result(self):
        ha = FakeHa()
        service = template_service.TemplateService(ha)
        await service.sync({'a'})
        ha.send('a', {'result': '# hi'})
        ha.online = False
        await service.sync({'a'})
        self.assertEqual(service.result('a').block(2048), {'v': 1, 'r': [['h', [[0, 'hi']]]]})

    async def test_results_mark_the_tiles_and_repeat_nothing(self):
        clock = [100.0]
        ha = FakeHa()
        service = template_service.TemplateService(ha, clock=lambda: clock[0])
        await service.sync({'a'})
        ha.send('a', {'result': 'one'})
        self.assertIn('screen.text', ha.dirty)
        ha.dirty.clear()
        ha.send('a', {'result': 'one'})
        self.assertEqual(ha.dirty, set())

    async def test_a_burst_is_paced(self):
        clock = [100.0]
        ha = FakeHa()
        service = template_service.TemplateService(ha, clock=lambda: clock[0])
        await service.sync({'a'})
        ha.send('a', {'result': '1'})
        ha.dirty.clear()
        ha.send('a', {'result': '2'})
        self.assertEqual(ha.dirty, set())
        self.assertIsNotNone(service.waiting)
        clock[0] += template_service.PACE_SECONDS
        await asyncio.sleep(template_service.PACE_SECONDS + 0.05)
        self.assertIn('screen.text', ha.dirty)
        self.assertEqual(service.result('a').text, '2')

    async def test_errors_and_warnings(self):
        ha = FakeHa()
        ha.refuse.add('bad')
        service = template_service.TemplateService(ha)
        await service.sync({'bad', 'warn'})
        self.assertIn('TemplateSyntaxError', service.result('bad').block(2048)['e'])
        ha.send('warn', {'error': "'x' is undefined", 'level': 'WARNING'})
        self.assertIsNone(service.result('warn'))
        ha.send('warn', {'error': 'boom', 'level': 'ERROR'})
        self.assertEqual(service.result('warn').block(2048), {'v': 1, 'e': 'boom'})

    def test_listeners_say_what_renders_it_again(self):
        result = template_service.result_of({'result': 'x', 'listeners': {'all': False, 'entities': ['sensor.b', 'sensor.a', 5],
                                                                             'domains': ['light'], 'time': True}})
        self.assertEqual(result.listeners, {'entities': ['sensor.a', 'sensor.b'], 'domains': ['light'], 'all': False, 'time': True})
        self.assertEqual(template_service.result_of({'result': 'x'}).listeners, {'entities': [], 'domains': [], 'all': False, 'time': False})

    async def test_preview_renders_once(self):
        ha = FakeHa()
        service = template_service.TemplateService(ha)
        task = asyncio.ensure_future(service.preview('p'))
        await asyncio.sleep(0)
        ha.send('p', {'result': '- one'})
        result = await task
        self.assertEqual(result.text, '- one')
        self.assertEqual(ha.subs, {})

    def test_wanted_is_capped_per_screen(self):
        tiles = [{'entity': 'screen.text', 'options': {'template': str(n)}} for n in range(10)] + [{'entity': 'light.x'}]
        self.assertEqual(template_service.wanted_templates([tiles], 3), {'0', '1', '2'})


if __name__ == '__main__':
    unittest.main()
