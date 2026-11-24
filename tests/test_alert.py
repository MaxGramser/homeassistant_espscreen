"""The alert a Home Assistant action puts over the whole screen (packages/core.yaml).

What the card makes of its fields is screen_alert::make and where its parts stand screen_alert::layout (alert_overlay.h),
proven by tests/test_alert_overlay.cpp and tests/test_alert_layout.py. What a screen shows of an alert, each text on its
own part, one button or two as asked and a title one line high however long, is the host render's alert round
(tools/render/run.py, alert_words_faults). When an alert is up, what ends it, its blinks, what Home Assistant hears and
how it meets the standby is alert_life.h, proven by running it (tests/test_alert_life.cpp), and each ending as Home
Assistant hears it on the real firmware is the host render's alert life round (tools/render/run.py guition --only
alertlife). Here: the contract with Home Assistant and the app, and what only the YAML can get wrong."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import tile_icons  # noqa: E402
from core import ALERT_CHOICE_ORDER, ALERT_ENDINGS, ALERT_EVENT, ALERT_FALLBACK_ICON, ALERT_FIELDS  # noqa: E402
import package_yaml  # noqa: E402

CORE = package_yaml.load(package_yaml.CORE)
CARD = package_yaml.widgets(CORE['lvgl']['top_layer'])
LIMITS = ('ALERT_TITLE_MAX', 'ALERT_SUBTITLE_MAX', 'ALERT_BUTTON_MAX')


def values(node):
    """Every string under a parsed node: the C++ of its lambdas, the arguments of its steps."""
    if isinstance(node, dict):
        return [s for v in node.values() for s in values(v)]
    if isinstance(node, list):
        return [s for v in node for s in values(v)]
    return [node] if isinstance(node, str) else []


def every_dismissal():
    """[(file, its arguments)] of every `script.execute` of alert_dismiss in every package: a script, an action, a widget."""
    found = []
    for path in package_yaml.files():
        def walk(node):
            if isinstance(node, dict):
                target = node.get('script.execute')
                if isinstance(target, dict) and target.get('id') == 'alert_dismiss':
                    found.append((path, target))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(package_yaml.load(path))
    return found


class TheActions(unittest.TestCase):
    """What Home Assistant calls (esphome.<device>_show_alert and the rest): its names and fields are the app's
    (tests/test_alerts_reference.py), and every field reaches the card."""

    def test_every_field_reaches_the_card_by_its_name(self):
        actions = package_yaml.actions()
        show = package_yaml.script('alert_show')
        parameters = set(show['parameters'])
        for name, fields in (('show_alert', [f[0] for f in ALERT_FIELDS]), ('show_alert_choice', list(ALERT_CHOICE_ORDER))):
            action = actions[name]
            self.assertEqual(list(action['variables']), fields, f'{name} takes the fields the app sends it, in its order')
            calls = package_yaml.executed(action)
            self.assertEqual([script for script, _ in calls], ['alert_show'], f'{name} hands the alert to alert_show alone')
            given = calls[0][1]
            self.assertEqual(set(given), parameters, f'{name} gives alert_show every parameter it has')
            for field in parameters:
                expected = f'return {field};' if field in fields else ''
                self.assertEqual(given[field], expected, f'{name}: alert_show\'s {field} is the action\'s own field, or '
                                                         'empty when the action has no such field')

    def test_dismiss_alert_ends_it_as_remote(self):
        self.assertEqual(package_yaml.executed(package_yaml.actions()['dismiss_alert']), [('alert_dismiss', {'reason': 'remote'})])


class TheCard(unittest.TestCase):
    def test_it_lies_on_the_top_layer_hidden_until_an_alert(self):
        # LVGL's top layer lies over every page, card and the dim overlay.
        for part in ('alert_overlay', 'alert_card', 'alert_icon', 'alert_title', 'alert_subtitle', 'alert_ok', 'alert_ok_label',
                     'alert_button2', 'alert_button2_label'):
            self.assertIn(part, CARD, f'{part} belongs to the alert card on lvgl.top_layer in packages/core.yaml')
        self.assertTrue(CARD['alert_overlay'][1].get('hidden'), 'the alert overlay is hidden until an alert shows it')
        pages = package_yaml.widgets(CORE['lvgl']['pages'])
        self.assertFalse([part for part in pages if part.startswith('alert_')], 'no part of the alert lies on a page')

    def test_its_icon_starts_as_the_fallback(self):
        glyph = chr(int(tile_icons.GLYPHS[ALERT_FALLBACK_ICON], 16))
        self.assertEqual(CARD['alert_icon'][1]['text'], glyph,
                         f'the alert card\'s icon starts as the fallback icon ({ALERT_FALLBACK_ICON}), as an alert without one')

    def test_every_text_ends_in_dots(self):
        # LVGL ends a DOT label in dots when its text is taller than the label; screen_alert::layout and alert_place give
        # each one its height. The icon is one glyph.
        labels = [name for name, (kind, _) in CARD.items() if kind == 'label' and name != 'alert_icon']
        self.assertGreaterEqual(len(labels), 4)
        for name in labels:
            self.assertEqual(CARD[name][1].get('long_mode'), 'DOT', f'{name} on the alert card has long_mode: DOT')

    def test_the_words_have_the_fonts_the_app_measures(self):
        # ESP Screens works the card's picture box out from the title's and subtitle's line heights
        # (screen_manager/app/alert_layout.py, from headline and sublabel_big).
        self.assertEqual(CARD['alert_title'][1]['text_font'], 'headline', 'the alert\'s title draws in headline')
        self.assertEqual(CARD['alert_subtitle'][1]['text_font'], 'sublabel_big', 'the alert\'s subtitle draws in sublabel_big')

    def test_every_button_is_guarded_and_ends_it_with_its_own_reason(self):
        reasons = []
        for name, (_, widget) in CARD.items():
            if 'on_click' not in widget:
                continue
            guard = [step for step in package_yaml.steps({'then': widget['on_click']}) if 'if' in step]
            self.assertTrue(guard and 'screen_input::touch_guard.accept(' in str(guard[0]['if']['condition']),
                            f'{name}: a tap on the alert goes through the touch guard before it ends the alert')
            calls = package_yaml.executed(guard[0]['if'])
            self.assertEqual([script for script, _ in calls], ['alert_dismiss'], f'{name} ends the alert through alert_dismiss')
            reasons.append(calls[0][1]['reason'])
        self.assertEqual(sorted(reasons), ['button2', 'ok'], 'the two buttons end it as ok and button2')

    def test_the_helper_header_is_included(self):
        self.assertIn('<esphome/components/smart_display/alert_overlay.h>', CORE['esphome']['includes'],
                      'packages/core.yaml includes alert_overlay.h, which alert_show asks (screen_alert::make)')


class TheEnd(unittest.TestCase):
    LIFE = (ROOT / 'components/smart_display/alert_life.h').read_text()
    TEXT = package_yaml.CORE.read_text()

    def test_every_script_of_an_alert_is_one_call(self):
        # The names the actions, the card's keys and an Override YAML use: each is alert_life.h's own function and
        # nothing beside it, so there is no second place where a rule of an alert could live.
        calls = {
            'alert_dismiss': 'alert_life::the().dismiss(reason.c_str());',
            'alert_flash': 'alert_life::the().flash(millis());',
            'alert_timeout': 'alert_life::the().timeout(seconds, millis());',
            'alert_report': 'alert_life::the().report(action.c_str());',
        }
        for name, call in calls.items():
            self.assertEqual(package_yaml.script(name)['then'], [{'lambda': call}], f'{name} is one call')
        show = package_yaml.script('alert_show')['then']
        self.assertEqual(len(show), 1, 'alert_show is one call')
        self.assertTrue(show[0]['lambda'].startswith('alert_life::the().show(screen_alert::make(title, subtitle, icon, color, '))
        # Its time and its blinks wait on one script that the latest ask replaces.
        wait = package_yaml.script('alert_wait')
        self.assertEqual(wait.get('mode'), 'restart')
        self.assertEqual(wait['then'][1], {'lambda': 'alert_life::the().due(millis());'})
        self.assertIn('alert.glass.later = [](uint32_t ms) { id(alert_wait).execute(ms); };', self.TEXT)
        for name, item in ((n, i) for _, n, i in package_yaml.every_script() if n.startswith('alert_')):
            self.assertIn(name, {*calls, 'alert_show', 'alert_wait', 'alert_event'}, f'{name}: no package has an alert script of its own')

    def test_only_its_life_closes_the_card(self):
        # A card closing, standby, Wake or a setting never takes the alert away: it ends through alert_life's dismiss,
        # which reports how. The card comes and goes in one place, the binding of glass.reveal; the UI self test shows
        # and hides the overlay on its own, and reports nothing.
        for pattern in ('screen_motion::hide(id(alert_overlay)', 'screen_motion::show(id(alert_overlay)'):
            total = sum(path.read_text().count(pattern) for path in package_yaml.files())
            self.assertEqual(total, 1, f'only alert_life reveals the card ({pattern})')
        reveal = re.search(r'alert\.glass\.reveal = \[\]\(bool shown\) \{(.*?)\};', self.TEXT, re.S)
        self.assertTrue(reveal and 'screen_motion::show(id(alert_overlay)' in reveal[1] and 'screen_motion::hide(id(alert_overlay)' in reveal[1])
        hides = {name for _, name, item in package_yaml.every_script()
                 for step in package_yaml.steps(item) if step.get('lvgl.widget.hide') == 'alert_overlay'}
        self.assertEqual(hides, {'ui_self_test'}, 'only the UI self test hides the overlay itself')
        self.assertFalse([path.name for path in package_yaml.files() if 'alert' not in path.name
                          and re.search(r'lvgl\.widget\.hide:\s*alert_overlay', path.read_text())
                          and path.name != 'self-test.yaml'], 'nothing else hides the alert overlay')
        # No package keeps an alert's state of its own any more.
        for path in package_yaml.files():
            for gone in ('alert_active', 'alert_title_text', 'alert_card_color', 'alert_timeout_seconds', 'alert_flash_requested'):
                self.assertNotIn(gone, path.read_text(), f'{path.name}: {gone} lived in the YAML before alert_life.h')

    def test_every_ending_reports_to_home_assistant(self):
        event = package_yaml.script('alert_event')
        events = [step['homeassistant.event'] for step in package_yaml.steps(event) if 'homeassistant.event' in step]
        self.assertEqual([e['event'] for e in events], [ALERT_EVENT], 'an alert\'s end is the one event the app listens to')
        self.assertEqual(set(events[0]['data']), {'action', 'title', 'screen'},
                         'Manager.alert_ended and automations read action, title and screen from it')
        self.assertIn('alert.glass.report = [](const char *action, const std::string &title) { id(alert_event).execute(std::string(action), title); };',
                      self.TEXT, 'what alert_life reports goes out as that event')
        self.assertEqual(sum(path.read_text().count('event: esphome.screen_alert') for path in package_yaml.files()), 1,
                         'one place sends the event')
        # The endings the screen can report are the ones the app documents and reads (core.ALERT_ENDINGS): the reasons
        # the YAML ends an alert with (the card's keys, the action dismiss_alert, a standby by hand), and the two the
        # life ends it with itself: its time running out, and a new alert over it.
        reasons = {target['reason'] for _, target in every_dismissal()}
        reasons |= set(re.findall(r'alert_life::the\(\)\.dismiss\("(\w+)"\)', self.TEXT))
        reasons |= set(re.findall(r'(?:dismiss|report)\("(\w+)"\)', self.LIFE))
        self.assertEqual(reasons, {ending for ending, _ in ALERT_ENDINGS},
                         'the screen ends an alert as exactly the endings the app knows (core.ALERT_ENDINGS): change both')

    def test_the_self_test_shows_the_card_and_tells_nobody(self):
        # ui_self_test renders every overlay without controlling a device: it shows and hides the alert's overlay itself
        # and never runs an alert, which would report to Home Assistant.
        test = package_yaml.script('ui_self_test')
        steps = package_yaml.steps(test)
        self.assertIn('alert_overlay', [step.get('lvgl.widget.show') for step in steps])
        self.assertIn('alert_overlay', [step.get('lvgl.widget.hide') for step in steps])
        self.assertFalse({'alert_show', 'alert_dismiss', 'alert_report'} & {name for name, _ in package_yaml.executed(test)})
        self.assertFalse([key for step in steps for key in step if key.startswith('homeassistant.')],
                         'the UI self test sends nothing to Home Assistant')

    def test_a_board_says_how_often_its_backlight_blinks(self):
        # glass: an alert with flash: true blinks the backlight four times as it arrives and leaves it lit. The blinks,
        # their times and the light coming back at an ending are alert_life.h's (tests/test_alert_life.cpp); how often
        # is the board's, and a backlight that must never go dark says none. No PC can see a backlight.
        self.assertEqual(str(CORE['substitutions']['ALERT_BLINKS']), '4')
        always_on = package_yaml.load(ROOT / 'packages/features/backlight-always-on.yaml')
        self.assertEqual(str(always_on['substitutions']['ALERT_BLINKS']), '0')
        self.assertIn('alert.blinks = ${ALERT_BLINKS};', self.TEXT)
        self.assertIn('alert.glass.light = [](int level, int ms) { id(set_backlight).execute(level, ms); };', self.TEXT,
                      'the blinks go through the board\'s one owner of the backlight')


class TheLimits(unittest.TestCase):
    def test_the_looks_limits_reach_the_card(self):
        # Bytes per text, per look (packages/looks/): the cheatsheet names them, so the card must cut there.
        for look in sorted((ROOT / 'packages/looks').glob('*.yaml')):
            limits = profiles.substitutions_of(look)
            if not any(key in limits for key in LIMITS):
                continue
            for key in LIMITS:
                self.assertGreater(int(limits[key]), 0, f'{look.name}: {key}')
            self.assertGreater(int(limits['ALERT_SUBTITLE_MAX']), int(limits['ALERT_TITLE_MAX']), look.name)
        show = ''.join(values(package_yaml.script('alert_show')))
        for key in LIMITS:
            self.assertIn(f'${{{key}}}', show, f'alert_show cuts the alert\'s texts at the look\'s {key} (screen_alert::make)')

    def test_the_card_fits_every_board(self):
        # Every board's glass, lying down and standing up, with its words above its button (screen_alert::layout, which
        # screen_manager/app/alert_layout.py mirrors and tests/test_alert_layout.py keeps alike).
        import alert_layout
        import font_metrics
        core = profiles.CORE.read_text()
        shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        for board in profiles.BOARDS:
            values_ = profiles.board_values(board)
            title = font_metrics.line_height(ROOT / font_metrics.font_file(core, 'headline', values_), int(values_['FONT_HEADLINE_SIZE']))
            sub = font_metrics.line_height(ROOT / font_metrics.font_file(core, 'sublabel_big', values_), int(values_['FONT_SUBLABEL_BIG_SIZE']))
            for way, side in shapes[board]['orientations'].items():
                card = alert_layout.layout(side['width'], side['height'], title, sub, False,
                                           round(float(values_['DISPLAY_DPI'])), values_['LOOK'])
                where = f'{board} {way}'
                self.assertLessEqual(card.card_w, side['width'] - 16, where)
                self.assertLessEqual(card.card_h, side['height'] - 16, where)
                self.assertLessEqual(card.text_x + card.text_w, card.card_w - card.icon_x, where)
                self.assertGreaterEqual(card.subtitle_h, 2 * sub, where)
                self.assertLessEqual(card.subtitle_y + card.subtitle_h, card.card_h - card.button_inset - card.button_h, where)


if __name__ == '__main__':
    unittest.main()
