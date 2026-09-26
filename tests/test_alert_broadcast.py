"""One alert for every screen (app 0.2.45): Home Assistant fires esp_screens_show_alert or
esp_screens_dismiss_alert, and the app calls that action on each screen that can show it."""
import asyncio
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
from core import (ALERT_EVENT, ALERT_FIELDS, ALERT_MAX_TIMEOUT, BROADCAST_DISMISS, BROADCAST_EVENTS, BROADCAST_SHOW,  # noqa: E402
                  alert_action, alert_data, alert_reference, alert_screen_choice, alert_screen_names, alert_targets)

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp import WSMsgType
    from server import HomeAssistant, Manager

STATIC = ROOT / 'screen_manager/app/static'


class AlertData(unittest.TestCase):
    def test_complete_data_passes_through_typed(self):
        data = {'title': 'Mail!', 'subtitle': 'There is post', 'icon': 'mailbox', 'color': 'orange',
                'button_text': 'OK', 'timeout': 30, 'flash': True}
        self.assertEqual(alert_data(data), (data, []))
        self.assertEqual(list(alert_data(data)[0]), [name for name, *_ in ALERT_FIELDS], 'all seven, in field order')

    def test_missing_fields_become_empty_without_a_warning(self):
        empty = {'title': '', 'subtitle': '', 'icon': '', 'color': '', 'button_text': '', 'timeout': 0, 'flash': False}
        for data in ({}, None, 'text', {'title': None, 'timeout': '', 'flash': ''}):
            self.assertEqual(alert_data(data), (empty, []), data)

    def test_values_are_coerced_like_home_assistant_does(self):
        service, unusable = alert_data({'title': 42, 'timeout': '90', 'flash': 'on'})
        self.assertEqual((service['title'], service['timeout'], service['flash'], unusable), ('42', 90, True, []))
        self.assertEqual(alert_data({'timeout': 12.7})[0]['timeout'], 12)
        self.assertEqual(alert_data({'timeout': -5})[0]['timeout'], 0, 'the firmware clamps too')
        self.assertEqual(alert_data({'timeout': 10**9})[0]['timeout'], ALERT_MAX_TIMEOUT)
        self.assertEqual(alert_data({'flash': 1})[0]['flash'], True)
        self.assertEqual(alert_data({'flash': 'Off'})[0]['flash'], False)

    def test_one_unusable_value_is_left_empty_and_named(self):
        # A bare `Yes` in YAML arrives as a boolean; the rest of the alert still goes out.
        service, unusable = alert_data({'title': 'Door', 'button_text': True, 'timeout': 'soon', 'flash': 'maybe', 'icon': ['bell']})
        self.assertEqual(service, {'title': 'Door', 'subtitle': '', 'icon': '', 'color': '', 'button_text': '', 'timeout': 0, 'flash': False})
        self.assertEqual(unusable, ['icon', 'button_text', 'timeout', 'flash'])
        self.assertEqual(alert_data({'timeout': float('nan')})[1], ['timeout'])

    def test_limits_follow_the_firmware(self):
        header = (ROOT / 'components/smart_display/alert_overlay.h').read_text()
        self.assertEqual(int(re.search(r'MAX_TIMEOUT_SECONDS = (\d+);', header)[1]), ALERT_MAX_TIMEOUT)
        self.assertEqual(BROADCAST_EVENTS, {'esp_screens_show_alert': 'show_alert', 'esp_screens_dismiss_alert': 'dismiss_alert'})
        self.assertEqual(alert_reference()['broadcast'], {'show': BROADCAST_SHOW, 'dismiss': BROADCAST_DISMISS})


class AlertAction(unittest.TestCase):
    """An action behind the button (app 0.2.91): the event names it, the app performs it on the press."""

    def test_the_action_and_its_data(self):
        self.assertEqual(alert_action({'title': 'Gate', 'action': 'script.open_gate'}), (('script.open_gate', {}), True))
        self.assertEqual(alert_action({'action': ' light.turn_off ', 'data': {'entity_id': 'light.hall', 'transition': 2}}),
                         (('light.turn_off', {'entity_id': 'light.hall', 'transition': 2}), True))
        for data in ({}, {'action': ''}, {'action': None}, None, 'text'):
            self.assertEqual(alert_action(data), (None, True), data)
        for data in ({'action': 'open the gate'}, {'action': 42}, {'action': 'script.x', 'data': 'no'}, {'action': 'script.x', 'data': ['a']},
                     {'action': 'script.x', 'data': {'big': 'x' * 5000}}, {'action': 'script.x', 'data': {'nan': float('nan')}}):
            self.assertEqual(alert_action(data), (None, False), data)
        self.assertEqual(alert_reference()['action']['name'], 'action')


class AlertTargets(unittest.TestCase):
    def test_only_screens_that_can_show_it_now(self):
        screens = [{'name': 'Kitchen', 'node': 'kitchen', 'online': True, 'firmware': '0.2.31'},
                   {'name': 'Hall', 'node': 'hall', 'online': True, 'firmware': '0.2.38'},
                   {'name': 'Attic', 'node': 'attic', 'online': False, 'firmware': '0.2.38'},
                   {'name': 'Garage', 'node': 'garage', 'online': True, 'firmware': '0.2.30'},
                   {'name': 'Shed', 'node': 'shed', 'online': True, 'firmware': 'unknown'},
                   {'name': 'New', 'node': None, 'online': True, 'firmware': '0.2.38'},
                   {'name': 'Hall again', 'node': 'hall', 'online': True, 'firmware': '0.2.38'}]
        ready, skipped = alert_targets(screens)
        self.assertEqual([s['name'] for s in ready], ['Kitchen', 'Hall'])
        self.assertEqual([(s['name'], reason) for s, reason in skipped],
                         [('Attic', 'offline'), ('Garage', 'firmware 0.2.30'), ('Shed', 'firmware unknown'), ('New', 'device name unknown')])
        self.assertEqual(alert_targets([]), ([], []))


class AlertScreens(unittest.TestCase):
    """One screen or a few (app 0.2.133): the event's `screen` names who gets it."""

    def test_the_field_is_a_name_or_a_list_of_names(self):
        self.assertEqual(alert_screen_names({'title': 'Door'}), ([], True))
        for empty in ({'screen': None}, {'screen': ''}, {'screen': []}, None, 'text'):
            self.assertEqual(alert_screen_names(empty), ([], True), empty)
        self.assertEqual(alert_screen_names({'screen': ' kitchen-screen '}), (['kitchen-screen'], True))
        self.assertEqual(alert_screen_names({'screen': ['kitchen-screen', 'Hall']}), (['kitchen-screen', 'Hall'], True))
        for broken in ({'screen': True}, {'screen': {'name': 'hall'}}, {'screen': ['hall', None]}, {'screen': '  '}, {'screen': ['hall', '']}):
            self.assertEqual(alert_screen_names(broken), ([], False), broken)

    def test_a_name_matches_the_device_name_the_ha_name_or_the_room(self):
        screens = [{'node': 'kitchen-screen', 'name': 'Kitchen Screen', 'area': 'Kitchen'},
                   {'node': 'wohnzimmer-screen', 'name': 'Wohnzimmer', 'area': 'Living room'},
                   {'node': 'reading', 'name': 'Reading corner', 'area': 'Living room'}]
        pick = lambda *names: [s['node'] for s in alert_screen_choice(screens, list(names))[0]]
        self.assertEqual(pick('kitchen-screen'), ['kitchen-screen'])
        # Written loosely: the action's underscores, another case, spaces.
        self.assertEqual(pick('wohnzimmer_screen'), ['wohnzimmer-screen'])
        self.assertEqual(pick('KITCHEN SCREEN'), ['kitchen-screen'])
        self.assertEqual(pick('Wohnzimmer'), ['wohnzimmer-screen'])
        # A room reaches every screen in it; a list several, each once and in the screens' order.
        self.assertEqual(pick('living room'), ['wohnzimmer-screen', 'reading'])
        self.assertEqual(pick('reading', 'kitchen-screen', 'Reading corner'), ['kitchen-screen', 'reading'])
        # Whole names only: part of a name is no match, so a typo never reaches another screen.
        self.assertEqual(alert_screen_choice(screens, ['kitchen']), ([screens[0]], []), 'the room is called Kitchen')
        self.assertEqual(alert_screen_choice(screens, ['kitch', 'hall']), ([], ['kitch', 'hall']))
        self.assertEqual(alert_screen_choice(screens, ['hall', 'reading']), ([screens[2]], ['hall']))

    def test_the_cheatsheet_and_the_skill_describe_it(self):
        self.assertEqual(alert_reference()['screen']['name'], 'screen')
        self.assertTrue(alert_reference()['screen']['help'])


def fake_ha():
    """Three paired screens as Home Assistant's registry describes them: two current, one too old."""
    class HA:
        online = True

        def __init__(self):
            self.registry, self.devices, self.states = [], [], {}
            for device, node, firmware in (('d1', 'kitchen-screen', '0.2.38'), ('d2', 'hall', '0.2.31'), ('d3', 'attic', '0.2.30')):
                self.registry += [{'entity_id': f'text.{device}_tiles', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': device},
                                  {'entity_id': f'sensor.{device}_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': device},
                                  {'entity_id': f'sensor.{device}_fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': device}]
                self.devices.append({'id': device, 'name': node.title()})
                self.states.update({f'text.{device}_tiles': {'state': 'Synced'}, f'sensor.{device}_node': {'state': node},
                                    f'sensor.{device}_fw': {'state': firmware}})
            self.areas = []
            self.changed = asyncio.Event()
            self.broadcasts = asyncio.Queue()
            self.calls, self.failing = [], set()
            self.subscriptions = []

        async def request(self, kind, **data):
            if kind == 'subscribe_events':
                self.subscriptions.append(data.get('event_type'))
            return {}

        async def call(self, action, data):
            self.calls.append((action, data))
            if action in self.failing:
                raise ConnectionError('Home Assistant refused the command.')
    return HA()


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Broadcast(unittest.IsolatedAsyncioTestCase):
    async def test_show_and_dismiss_reach_every_current_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(fake_ha(), Path(tmp) / 'screens.json')
            with self.assertLogs('screen_manager', 'INFO') as logs:
                result = await m.broadcast(BROADCAST_SHOW, {'title': 'Mail!', 'icon': 'mailbox', 'flash': True})
            self.assertEqual(result, {'sent': 2, 'skipped': 1, 'failed': 0})
            data = {'title': 'Mail!', 'subtitle': '', 'icon': 'mailbox', 'color': '', 'button_text': '', 'timeout': 0, 'flash': True}
            self.assertEqual(sorted(m.ha.calls), [('esphome.hall_show_alert', data), ('esphome.kitchen_screen_show_alert', data)])
            self.assertIn('esp_screens_show_alert: 2 of 3 screens (not: Attic firmware 0.2.30)', logs.output[-1])
            m.ha.calls.clear()
            await m.broadcast(BROADCAST_DISMISS, {'title': 'ignored'})
            self.assertEqual(sorted(m.ha.calls), [('esphome.hall_dismiss_alert', {}), ('esphome.kitchen_screen_dismiss_alert', {})])

    async def test_the_screen_field_picks_who_gets_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(fake_ha(), Path(tmp) / 'screens.json')
            with self.assertLogs('screen_manager', 'INFO') as logs:
                result = await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'screen': 'kitchen_screen', 'action': 'script.open_gate'})
            self.assertEqual(result, {'sent': 1, 'skipped': 0, 'failed': 0, 'unknown': []})
            self.assertEqual([action for action, _ in m.ha.calls], ['esphome.kitchen_screen_show_alert'])
            self.assertNotIn('screen', m.ha.calls[0][1], 'show_alert keeps its seven fields')
            self.assertIn('esp_screens_show_alert: 1 of 1 screens for kitchen_screen', logs.output[-1])
            self.assertEqual(list(m.alert_actions), ['kitchen-screen'], 'the button action waits on that screen only')
            # A screen that cannot show it now is named, as for every screen.
            m.ha.calls.clear()
            with self.assertLogs('screen_manager', 'INFO') as logs:
                result = await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'screen': ['hall', 'Attic']})
            self.assertEqual(result, {'sent': 1, 'skipped': 1, 'failed': 0, 'unknown': []})
            self.assertEqual([action for action, _ in m.ha.calls], ['esphome.hall_show_alert'])
            self.assertIn('1 of 2 screens for hall, Attic (not: Attic firmware 0.2.30)', logs.output[-1])
            # Dismiss takes it too.
            m.ha.calls.clear()
            await m.broadcast(BROADCAST_DISMISS, {'screen': 'hall'})
            self.assertEqual(m.ha.calls, [('esphome.hall_dismiss_alert', {})])

    async def test_a_screen_nobody_has_gets_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(fake_ha(), Path(tmp) / 'screens.json')
            with self.assertLogs('screen_manager', 'WARNING') as logs:
                result = await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'screen': 'hallway'})
            self.assertEqual(result, {'sent': 0, 'skipped': 0, 'failed': 0, 'unknown': ['hallway']})
            self.assertEqual(m.ha.calls, [])
            self.assertIn('no screen called hallway (screens: attic, hall, kitchen-screen)', logs.output[-1])
            # One name known, one not: the known one gets it, the other is named.
            with self.assertLogs('screen_manager', 'INFO') as logs:
                result = await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'screen': ['hallway', 'hall']})
            self.assertEqual(result['unknown'], ['hallway'])
            self.assertEqual([action for action, _ in m.ha.calls], ['esphome.hall_show_alert'])
            # A field that is no name at all sends nothing either.
            m.ha.calls.clear()
            with self.assertLogs('screen_manager', 'WARNING') as logs:
                await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'screen': True})
            self.assertEqual(m.ha.calls, [])
            self.assertIn('unusable screen, sent to no screen', logs.output[-1])

    async def test_a_screen_added_later_gets_the_next_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            m = Manager(ha, Path(tmp) / 'screens.json')
            await m.broadcast(BROADCAST_SHOW, {'title': 'One'})
            ha.registry = ha.registry + [{'entity_id': 'text.d4_tiles', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd4'},
                                         {'entity_id': 'sensor.d4_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd4'},
                                         {'entity_id': 'sensor.d4_fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd4'}]
            ha.devices = ha.devices + [{'id': 'd4', 'name': 'Study'}]
            ha.states.update({'text.d4_tiles': {'state': 'Synced'}, 'sensor.d4_node': {'state': 'study'}, 'sensor.d4_fw': {'state': '0.2.38'}})
            ha.calls.clear()
            self.assertEqual((await m.broadcast(BROADCAST_SHOW, {'title': 'Two'}))['sent'], 3)
            self.assertIn('esphome.study_show_alert', [action for action, _ in ha.calls])

    async def test_one_failing_screen_does_not_stop_the_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(fake_ha(), Path(tmp) / 'screens.json')
            m.ha.failing.add('esphome.hall_show_alert')
            with self.assertLogs('screen_manager', 'INFO') as logs:
                result = await m.broadcast(BROADCAST_SHOW, {'title': 'Smoke', 'timeout': 'later'})
            self.assertEqual(result, {'sent': 1, 'skipped': 1, 'failed': 1})
            self.assertEqual(len(m.ha.calls), 2)
            self.assertTrue(any('unusable timeout left empty' in line for line in logs.output), logs.output)
            self.assertIn('1 of 3 screens (not: Attic firmware 0.2.30; Hall ConnectionError)', logs.output[-1])

    async def test_the_button_performs_the_alert_action_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(fake_ha(), Path(tmp) / 'screens.json')
            with self.assertLogs('screen_manager', 'INFO'):
                await m.broadcast(BROADCAST_SHOW, {'title': 'Gate', 'button_text': 'Open', 'action': 'script.open_gate', 'data': {'seconds': 5}})
            self.assertEqual(sorted(m.alert_actions), ['hall', 'kitchen-screen'])
            self.assertNotIn('action', m.ha.calls[0][1], 'show_alert keeps its seven fields')
            m.ha.calls.clear()
            # Hall presses the button: the action runs; Kitchen pressing it later runs nothing again.
            with self.assertLogs('screen_manager', 'INFO') as logs:
                await m.alert_ended({'action': 'ok', 'title': 'Gate', 'screen': 'hall'})
            self.assertEqual(m.ha.calls, [('script.open_gate', {'seconds': 5})])
            self.assertIn('script.open_gate performed', logs.output[-1])
            self.assertEqual(m.alert_actions, {})
            await m.alert_ended({'action': 'ok', 'title': 'Gate', 'screen': 'kitchen-screen'})
            await m.alert_ended({'action': 'ok', 'title': 'Other', 'screen': 'unknown'})
            self.assertEqual(len(m.ha.calls), 1)
            # A timeout, a new alert or a dismissal leaves it unperformed.
            await m.broadcast(BROADCAST_SHOW, {'title': 'Gate', 'action': 'script.open_gate'})
            await m.alert_ended({'action': 'timeout', 'title': 'Gate', 'screen': 'hall'})
            self.assertNotIn('hall', m.alert_actions)
            await m.broadcast(BROADCAST_SHOW, {'title': 'Plain'})
            self.assertEqual(m.alert_actions, {})
            await m.broadcast(BROADCAST_SHOW, {'title': 'Gate', 'action': 'script.open_gate'})
            await m.broadcast(BROADCAST_DISMISS, {})
            self.assertEqual(m.alert_actions, {})
            m.ha.calls.clear()
            # An action Home Assistant refuses is logged, not fatal; an unusable action is named and left out.
            await m.broadcast(BROADCAST_SHOW, {'title': 'Gate', 'action': 'script.open_gate'})
            m.ha.failing.add('script.open_gate')
            with self.assertLogs('screen_manager', 'WARNING') as logs:
                await m.alert_ended({'action': 'ok', 'title': 'Gate', 'screen': 'hall'})
            self.assertIn('script.open_gate failed (ConnectionError)', logs.output[-1])
            with self.assertLogs('screen_manager', 'INFO') as logs:
                await m.broadcast(BROADCAST_SHOW, {'title': 'Gate', 'action': 'open the gate'})
            self.assertTrue(any('unusable action left empty' in line for line in logs.output), logs.output)
            self.assertEqual(m.alert_actions, {})

    async def test_two_buttons_go_to_screens_that_draw_them(self):
        """A second button and button colours (firmware 0.3.3+): show_alert_choice where the screen has it, show_alert with
        one button on an older one, and each button's own action once."""
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            ha.states['sensor.d1_fw'] = {'state': '0.3.3'}
            m = Manager(ha, Path(tmp) / 'screens.json')
            with self.assertLogs('screen_manager', 'INFO') as logs:
                result = await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'button_text': 'Open', 'button_color': 'green',
                                                            'button2_text': 'Not now', 'button2_color': 'red',
                                                            'action': 'script.open_gate', 'button2_action': 'script.decline',
                                                            'button2_data': {'reason': 'busy'}})
            self.assertEqual(result, {'sent': 2, 'skipped': 1, 'failed': 0})
            calls = dict(ha.calls)
            self.assertEqual(list(calls['esphome.kitchen_screen_show_alert_choice']),
                             ['title', 'subtitle', 'icon', 'color', 'button_text', 'button_color', 'button2_text', 'button2_color', 'timeout', 'flash'])
            self.assertEqual(calls['esphome.kitchen_screen_show_alert_choice']['button2_text'], 'Not now')
            self.assertEqual(calls['esphome.hall_show_alert'],
                             {'title': 'Door', 'subtitle': '', 'icon': '', 'color': '', 'button_text': 'Open', 'timeout': 0, 'flash': False})
            self.assertTrue(any('Hall show one button (the second button needs firmware 0.3.3)' in line for line in logs.output), logs.output)
            ha.calls.clear()
            # The second button on the kitchen screen runs its own action, once, and forgets the first everywhere.
            with self.assertLogs('screen_manager', 'INFO') as logs:
                await m.alert_ended({'action': 'button2', 'title': 'Door', 'screen': 'kitchen-screen'})
            self.assertEqual(ha.calls, [('script.decline', {'reason': 'busy'})])
            self.assertIn('Alert second button on kitchen-screen: script.decline performed', logs.output[-1])
            await m.alert_ended({'action': 'ok', 'title': 'Door', 'screen': 'hall'})
            self.assertEqual(len(ha.calls), 1)
            # The first button still runs `action`.
            await m.broadcast(BROADCAST_SHOW, {'title': 'Door', 'button2_text': 'No', 'action': 'script.open_gate'})
            ha.calls.clear()
            with self.assertLogs('screen_manager', 'INFO'):
                await m.alert_ended({'action': 'ok', 'title': 'Door', 'screen': 'kitchen-screen'})
            self.assertEqual(ha.calls, [('script.open_gate', {})])
            # A colour alone is a choice too (one button in green); a second action without a second button is dropped.
            ha.calls.clear()
            with self.assertLogs('screen_manager', 'INFO') as logs:
                await m.broadcast(BROADCAST_SHOW, {'title': 'Go', 'button_color': 'green', 'button2_action': 'script.x', 'button2_text': True})
            self.assertEqual(dict(ha.calls)['esphome.kitchen_screen_show_alert_choice']['button2_text'], '')
            self.assertTrue(any('unusable button2_text left empty' in line for line in logs.output), logs.output)
            self.assertTrue(any('button2_action without button2_text' in line for line in logs.output), logs.output)
            self.assertEqual(m.alert_actions, {})

    async def test_the_reports_of_the_screens_go_through_the_alert_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(fake_ha(), Path(tmp) / 'screens.json')
            task = asyncio.create_task(m.alert_loop())
            m.ha.broadcasts.put_nowait((BROADCAST_SHOW, {'title': 'Gate', 'action': 'script.open_gate'}))
            m.ha.broadcasts.put_nowait((ALERT_EVENT, {'action': 'ok', 'title': 'Gate', 'screen': 'hall'}))
            with self.assertLogs('screen_manager', 'INFO'):
                for _ in range(50):
                    if ('script.open_gate', {}) in m.ha.calls:
                        break
                    await asyncio.sleep(0.01)
            task.cancel()
            self.assertIn(('script.open_gate', {}), m.ha.calls)
            self.assertIn("ALERT_EVENT, *TILE_EVENTS", (ROOT / 'screen_manager/app/server.py').read_text(), 'subscribed on connect')

    async def test_the_loop_keeps_the_order_and_survives_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(fake_ha(), Path(tmp) / 'screens.json')
            original = m.broadcast
            async def broadcast(event_type, data):
                if data.get('title') == 'boom':
                    raise RuntimeError('unexpected')
                return await original(event_type, data)
            m.broadcast = broadcast
            task = asyncio.create_task(m.alert_loop())
            for item in ((BROADCAST_SHOW, {'title': 'boom'}), (BROADCAST_SHOW, {'title': 'Door'}), (BROADCAST_DISMISS, {})):
                m.ha.broadcasts.put_nowait(item)
            with self.assertLogs('screen_manager', 'INFO'):
                for _ in range(50):
                    if len(m.ha.calls) == 4:
                        break
                    await asyncio.sleep(0.01)
            task.cancel()
            self.assertEqual([action.rsplit('_', 2)[-2:] for action, _ in m.ha.calls], [['show', 'alert']] * 2 + [['dismiss', 'alert']] * 2)

    async def test_home_assistant_queues_the_events_instead_of_calling_from_the_reader(self):
        class Message:
            type = WSMsgType.TEXT
            def __init__(self, data): self.data = data
            def json(self): return self.data
        class Socket:
            def __init__(self, messages): self.messages = messages
            def __aiter__(self): return self._iterate()
            async def _iterate(self):
                for message in self.messages:
                    yield Message(message)
        ha = HomeAssistant(None, 'http://ha/api', 'token')
        ha.ws = Socket([{'type': 'event', 'event': {'event_type': BROADCAST_SHOW, 'data': {'title': 'Mail!'}}},
                        {'type': 'event', 'event': {'event_type': 'call_service', 'data': {}}},
                        {'type': 'event', 'event': {'event_type': ALERT_EVENT, 'data': {'action': 'ok', 'title': 'Mail!', 'screen': 'hall'}}},
                        {'type': 'event', 'event': {'event_type': BROADCAST_DISMISS, 'data': {}}}])
        with self.assertRaises(ConnectionError):
            await ha.read()
        self.assertEqual([ha.broadcasts.get_nowait() for _ in range(ha.broadcasts.qsize())],
                         [(BROADCAST_SHOW, {'title': 'Mail!'}), (ALERT_EVENT, {'action': 'ok', 'title': 'Mail!', 'screen': 'hall'}), (BROADCAST_DISMISS, {})])
        self.assertIn('*BROADCAST_EVENTS', (ROOT / 'screen_manager/app/server.py').read_text(), 'subscribed on connect')


class Page(unittest.TestCase):
    def test_cheatsheet_explains_the_event(self):
        import editor_sources
        cheatsheet = editor_sources.component('AlertsView')
        for marker in ('id="alerts-all"', '"alerts-all",', 'id="alerts-all-example"', 'id="alerts-all-copy"',
                       'esp_screens_show_alert', 'esp_screens_dismiss_alert', 'editor.alerts.tips.claude'):
            self.assertIn(marker, cheatsheet, marker)
        # The words are in en.json (app 0.2.90).
        self.assertEqual(editor_sources.text('alerts.nav.all'), 'All screens')
        self.assertIn('Settings → Claude', editor_sources.text('alerts.tips.claude'))
        for marker in ('const allYaml = computed', 'broadcast?.show', 'copyText(allYaml, undefined, \'yaml\')'):
            self.assertIn(marker, cheatsheet, marker)
        # One screen through the same event (app 0.2.133): what goes after `screen:` for every screen, and an example.
        for marker in ('id="alerts-one"', '"alerts-one",', 'id="alerts-one-table"', 'id="alerts-one-example"', 'alert-screen-value',
                       "copyText(screenValue(screen), undefined, 'screen_name')"):
            self.assertIn(marker, cheatsheet, marker)
        self.assertEqual(editor_sources.text('alerts.nav.one'), 'One screen')


if __name__ == '__main__':
    unittest.main()
