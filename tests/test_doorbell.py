"""A doorbell's ring on the screens (docs/DOORBELL.md): an automation fires esp_screens_doorbell with the doorbell's camera
and the screens it names; a screen that draws a doorbell opens the camera live, any other gets its alert; the first that
answers closes it on the others, a ring nobody answered shows in the top bars, and the app fires one answered or missed
event per ring. The Events page's wizard puts such an automation into Home Assistant (automations.py)."""
import asyncio
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import package_yaml  # noqa: E402
import automations  # noqa: E402
import doorbell  # noqa: E402
import live_stream  # noqa: E402
import talk_bridge  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import Manager


class TheEvent(unittest.TestCase):
    def test_its_fields(self):
        self.assertEqual(doorbell.request({'camera': 'camera.front_door', 'title': 'Front door', 'timeout': '45'}),
                         ('camera.front_door', 'Front door', 45, []))
        self.assertEqual(doorbell.request({'camera': 'camera.front_door'}), ('camera.front_door', '', doorbell.TIMEOUT, []))
        self.assertEqual(doorbell.request({'camera': 'camera.x', 'timeout': 5})[2], doorbell.TIMEOUT_MIN)
        self.assertEqual(doorbell.request({'camera': 'camera.x', 'timeout': 9999})[2], doorbell.TIMEOUT_MAX)
        self.assertEqual(doorbell.request({'camera': 'camera.x', 'timeout': 'soon'})[3], ['timeout'])

    def test_no_camera_no_ring(self):
        for data in ({}, {'camera': 'image.front_door'}, {'camera': ['camera.x']}, None):
            self.assertIsNone(doorbell.request(data)[0], data)

    def test_its_name(self):
        self.assertEqual(doorbell.name_of('camera.front_door', 'Front door', {}), 'Front door')
        self.assertEqual(doorbell.name_of('camera.front_door', None, {'camera.front_door': {'attributes': {'friendly_name': 'Porch'}}}), 'Porch')


class Suggestions(unittest.TestCase):
    # Only an offer for the wizard: the doorbells Home Assistant knows as such, each with the camera on its device.
    def test_doorbells_home_assistant_knows(self):
        states = {'event.front_door_doorbell': {'state': '2026-10-22T10:07:52+00:00', 'attributes': {'device_class': 'doorbell', 'friendly_name': 'Front door Doorbell'}},
                  'event.button_press': {'state': 'unknown', 'attributes': {'device_class': 'button'}},
                  'binary_sensor.porch_visitor': {'state': 'off', 'attributes': {'friendly_name': 'Porch Visitor'}},
                  'binary_sensor.porch_person': {'state': 'off', 'attributes': {}},
                  'binary_sensor.g4_doorbell': {'state': 'off', 'attributes': {'friendly_name': 'G4 Doorbell'}},
                  'binary_sensor.other_visitor': {'state': 'off', 'attributes': {}},
                  'camera.front_door': {'state': 'idle'}, 'camera.porch_fluent': {'state': 'idle'}}
        registry = {'binary_sensor.porch_visitor': {'platform': 'reolink', 'translation_key': 'visitor'},
                    'binary_sensor.porch_person': {'platform': 'reolink', 'translation_key': 'person'},
                    'binary_sensor.g4_doorbell': {'platform': 'unifiprotect', 'translation_key': 'doorbell'},
                    'binary_sensor.other_visitor': {'platform': 'someone_else', 'translation_key': 'visitor'}}
        devices = {'event.front_door_doorbell': [{'entity_id': 'camera.front_door'}],
                   'binary_sensor.porch_visitor': [{'entity_id': 'camera.porch_clear', 'disabled_by': 'user'}, {'entity_id': 'camera.porch_fluent'}]}
        self.assertEqual(doorbell.suggestions(states, registry, lambda entity: devices.get(entity, [])), [
            {'trigger': 'binary_sensor.g4_doorbell', 'kind': 'on', 'camera': None, 'name': 'G4 Doorbell'},
            {'trigger': 'binary_sensor.porch_visitor', 'kind': 'on', 'camera': 'camera.porch_fluent', 'name': 'Porch Visitor'},
            {'trigger': 'event.front_door_doorbell', 'kind': 'doorbell', 'camera': 'camera.front_door', 'name': 'Front door Doorbell'}])

    def test_how_an_entity_starts_it(self):
        self.assertEqual(doorbell.trigger_kind('event.x', {'device_class': 'doorbell'}), 'doorbell')
        self.assertEqual(doorbell.trigger_kind('event.x', {}), 'event')
        self.assertEqual(doorbell.trigger_kind('binary_sensor.x'), 'on')
        self.assertEqual(doorbell.trigger_kind('input_button.x'), 'press')
        self.assertIsNone(doorbell.trigger_kind('light.x'))


class TheRings(unittest.TestCase):
    def test_answered_on_one_screen_closes_it_on_the_others_once(self):
        rings = doorbell.Doorbells()
        key = rings.start('camera.front_door', 'Front door', 45, ['a', 'b'], ['cyd'])
        message = rings.message(key)
        self.assertEqual({k: message[k] for k in ('op', 'e', 'n', 'k', 't')},
                         {'op': 'doorbell', 'e': 'camera.front_door', 'n': 'Front door', 'k': key, 't': 45})
        self.assertEqual(rings.open(), [key])
        self.assertEqual(rings.answered(key), (['a', 'b'], ['cyd']))
        self.assertEqual(rings.answered(key), ([], []), 'the second screen that answers closes nothing')
        self.assertEqual(rings.open(), [])
        self.assertFalse(rings.unanswered(key), 'an answered ring is not missed')
        self.assertEqual(rings.message(key, close=True), {'v': 1, 'op': 'doorbell', 'k': key, 'c': 1})

    def test_missed_until_seen_or_a_later_ring_is_answered(self):
        rings = doorbell.Doorbells()
        first = rings.start('camera.front_door', 'Front door', 60, ['a'])
        self.assertIsNone(rings.bar_item())
        self.assertTrue(rings.unanswered(first))
        self.assertEqual(rings.bar_item(), {'k': 'ago', 'i': 'F12E6', 'e': rings.ring(first)['at'], 'b': 1})
        rings.answered(rings.start('camera.front_door', 'Front door', 60, ['a']))
        self.assertIsNone(rings.bar_item(), 'answering the next ring of that door clears it')
        rings.unanswered(rings.start('camera.front_door', 'Front door', 60, ['a']))
        self.assertTrue(rings.seen())
        self.assertFalse(rings.seen())

    def test_a_missed_ring_kept_for_a_while_says_until_when_and_then_goes(self):
        """keep_minutes (docs/DOORBELL.md): the item says until when it stands (`x`, the ring's moment and the minutes),
        the screens take it away then by their own clock, and past it the app sends it no more either. None or 0 keeps
        it until someone opens it, as before."""
        self.assertEqual(doorbell.keep_of({}), (0, []))
        self.assertEqual(doorbell.keep_of({'keep_minutes': ''}), (0, []))
        self.assertEqual(doorbell.keep_of({'keep_minutes': '30'}), (30, []))
        self.assertEqual(doorbell.keep_of({'keep_minutes': 0}), (0, []))
        self.assertEqual(doorbell.keep_of({'keep_minutes': 99999}), (doorbell.KEEP_MAX, []))
        self.assertEqual(doorbell.keep_of({'keep_minutes': 'soon'}), (0, ['keep_minutes']))
        self.assertEqual(doorbell.keep_of({'keep_minutes': -5}), (0, ['keep_minutes']))
        rings = doorbell.Doorbells()
        key = rings.start('camera.front_door', 'Front door', 60, ['a'], keep=30)
        rings.unanswered(key)
        at = rings.ring(key)['at']
        self.assertEqual(rings.bar_item(now=at + 60), {'k': 'ago', 'i': 'F12E6', 'e': at, 'b': 1, 'x': at + 1800})
        self.assertIsNotNone(rings.bar_item(now=at + 1799))
        self.assertIsNone(rings.bar_item(now=at + 1800))
        self.assertIsNone(rings.missed, 'past its keep it is gone from the app too')
        # Until someone opens it: no `x`, at any time.
        rings.unanswered(rings.start('camera.front_door', 'Front door', 60, ['a']))
        self.assertNotIn('x', rings.bar_item(now=at + 10 ** 6))
        # The wizard's choices, and what a new automation gets.
        self.assertEqual(doorbell.KEEP_CHOICES, (10, 30, 60, 240, 0))
        self.assertEqual(doorbell.reference()['keep'], {'choices': [10, 30, 60, 240, 0], 'new': 30, 'max': doorbell.KEEP_MAX})

    def test_the_item_goes_first_within_the_bar_limit(self):
        item = {'k': 'ago', 'i': 'F12E6', 'e': 1, 'b': 1}
        self.assertEqual(doorbell.with_missed([{'k': 'clock'}], item, 6), [item, {'k': 'clock'}])
        self.assertEqual(len(doorbell.with_missed([{'k': 'clock'}] * 6, item, 6)), 6)


class TheDoor(unittest.TestCase):
    def test_a_lock_or_an_action_and_the_lock_first(self):
        self.assertEqual(doorbell.door_of({'lock': 'lock.front_door'}), ({'lock': 'lock.front_door'}, []))
        self.assertEqual(doorbell.door_of({'door_action': 'button.press', 'door_data': {'entity_id': 'button.gate'}}),
                         ({'action': 'button.press', 'data': {'entity_id': 'button.gate'}}, []))
        self.assertEqual(doorbell.door_of({'lock': 'lock.front_door', 'door_action': 'script.open_gate'})[0], {'lock': 'lock.front_door'})
        self.assertEqual(doorbell.door_of({}), (None, []))
        self.assertEqual(doorbell.door_of({'lock': 'switch.front_door'}), (None, ['lock']))
        self.assertEqual(doorbell.door_of({'door_action': 'not an action'}), (None, ['door_action']))
        self.assertEqual(doorbell.door_of({'door_action': 'script.open_gate', 'door_data': 'gate'}), (None, ['door_action']))

    def test_a_lock_that_asks_a_code_needs_its_default_code(self):
        states = {'lock.front_door': {'state': 'locked', 'attributes': {'code_format': r'^\d{4}$'}}, 'lock.back': {'state': 'locked', 'attributes': {}}}
        self.assertTrue(doorbell.door_blocked('lock.front_door', states, {}))
        self.assertIsNone(doorbell.door_blocked('lock.front_door', states, {'options': {'lock': {'default_code': '1234'}}}))
        self.assertIsNone(doorbell.door_blocked('lock.back', states, None))

    def test_the_op_says_what_the_key_is_and_the_locks_state(self):
        rings = doorbell.Doorbells()
        lock = rings.start('camera.porch', 'Porch', 60, ['a'], door={'lock': 'lock.front_door'}, nodes=['hall'])
        action = rings.start('camera.porch', 'Porch', 60, ['a'], door={'action': 'script.open_gate', 'data': {}}, nodes=['hall'])
        plain = rings.start('camera.porch', 'Porch', 60, ['a'], nodes=['hall'])
        self.assertEqual((rings.message(lock, door_state='locked')['d'], rings.message(lock, door_state='locked')['ds']), (doorbell.DOOR_LOCK, 'locked'))
        self.assertEqual(rings.message(action)['d'], doorbell.DOOR_ACTION)
        self.assertNotIn('ds', rings.message(action))
        self.assertNotIn('d', rings.message(plain))
        self.assertEqual(rings.door_message(lock, 'unlocked'), {'v': 1, 'op': 'doorbell', 'k': lock, 'ds': 'unlocked'})

    def test_only_a_screen_that_shows_the_ring_opens_its_door_once(self):
        rings = doorbell.Doorbells()
        key = rings.start('camera.porch', 'Porch', 60, ['a', 'b'], door={'lock': 'lock.front_door'}, nodes=['hall', 'kitchen'])
        self.assertIsNone(rings.door_press(key, 'garage'), 'a screen that never showed it')
        self.assertIsNone(rings.door_press('other', 'hall'), 'no such ring')
        self.assertEqual(rings.door_press(key, 'hall'), {'lock': 'lock.front_door'})
        self.assertIsNone(rings.door_press(key, 'kitchen'), 'one press, delivered twice or from two screens at once')
        rings.rings[key]['door_at'] -= doorbell.DOOR_AGAIN
        rings.gone(key, ['hall'])
        self.assertIsNone(rings.door_press(key, 'hall'), 'its view closed there')
        self.assertEqual(rings.door_press(key, 'kitchen'), {'lock': 'lock.front_door'})
        rings.rings[key]['since'] -= doorbell.DOOR_LIFE + 1
        rings.rings[key]['door_at'] = None
        self.assertEqual(rings.showing(key), [], 'past the door\'s life')
        self.assertIsNone(rings.door_press(key, 'kitchen'))
        rings.gone(key, ['kitchen'])
        rings.back(key, 'hall')
        self.assertEqual(rings.showing(key), ['hall'], 'opened again from the top bar')
        self.assertIsNone(rings.door_press(rings.start('camera.porch', 'Porch', 60, ['a'], nodes=['hall']), 'hall'), 'a ring without a door')


class TheSound(unittest.TestCase):
    def test_on_unless_the_event_says_quiet(self):
        self.assertEqual(doorbell.sound_of({}), (True, []))
        self.assertEqual(doorbell.sound_of({'sound': False}), (False, []))
        self.assertEqual(doorbell.sound_of({'sound': 'off'}), (False, []))
        self.assertEqual(doorbell.sound_of({'sound': True}), (True, []))
        self.assertEqual(doorbell.sound_of({'sound': 3}), (True, ['sound']))
        rings = doorbell.Doorbells()
        self.assertEqual(rings.message(rings.start('camera.porch', 'Porch', 60, ['a'], sound=False))['m'], 1)
        self.assertNotIn('m', rings.message(rings.start('camera.porch', 'Porch', 60, ['a'])))
        # The chime the same way: on unless the event says false.
        self.assertEqual(doorbell.sound_of({'chime': False}, 'chime'), (False, []))
        self.assertEqual(doorbell.sound_of({}, 'chime'), (True, []))
        self.assertEqual(rings.message(rings.start('camera.porch', 'Porch', 60, ['a'], chime=False))['nc'], 1)
        self.assertNotIn('nc', rings.message(rings.start('camera.porch', 'Porch', 60, ['a'])))


def cxx(source):
    """The output of a little C++ program over the firmware's own headers, compiled as tools/check.sh compiles the C++
    tests; None without a compiler."""
    compiler = shutil.which(os.environ.get('CXX', 'clang++')) or shutil.which('g++')
    if not compiler:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'probe.cpp'
        path.write_text(source)
        subprocess.run([compiler, '-std=c++17', f'-I{ROOT}', f'-I{ROOT / "tests"}', str(path), '-o', str(Path(tmp) / 'probe')],
                       check=True)
        return subprocess.run([str(Path(tmp) / 'probe')], check=True, capture_output=True, text=True).stdout


def receiver_branch(op):
    """The part of the page receiver (page_receiver.cpp) that reads op `op`, up to the next op it reads."""
    receiver = (ROOT / 'components/smart_display/page_receiver.cpp').read_text()
    start = receiver.index(f'if (op == "{op}")')
    return receiver[start:receiver.index('if (op == ', start + 1)]


class TheFirmwareReadsTheSame(unittest.TestCase):
    """The app and the screen speak one protocol (AGENTS.md, "Compatibility"): what the one sends, the other reads, by the
    same names and numbers. What the screen does with a ring is module_doorbell.cpp's, its rules doorbell_ring.h's and
    doorbell_door.h's, proven by tests/test_doorbell_ring.cpp and tests/test_doorbell_door.cpp."""

    def test_every_field_of_the_op_is_read_and_nothing_else(self):
        rings = doorbell.Doorbells()
        key = rings.start('camera.porch', 'Porch', 60, ['a'], door={'lock': 'lock.front_door'}, nodes=['hall'], sound=False,
                          chime=False)
        sent = set(rings.message(key, door_state='locked', link='http://x/camera/a.mjpeg', talk='http://x/talk/a'))
        sent |= set(rings.message(key, close=True)) | set(rings.door_message(key, 'unlocked'))
        # The chime chosen for the screen (docs/SOUNDS.md), on a ring that chimes.
        sent |= set(rings.message(rings.start('camera.porch', 'Porch', 60, ['a']), chime='http://x/files/a.wav'))
        read = set(re.findall(r'root\["(\w+)"\]', receiver_branch('doorbell')))
        self.assertEqual(sent - {'v', 'op'}, read,
                         'the op "doorbell" the app sends (doorbell.Doorbells.message, door_message) and the one '
                         'page_receiver.cpp reads must name the same fields: change both, and docs/DOORBELL.md')

    def test_a_missed_ring_in_the_top_bar_opens_it_again(self):
        rings = doorbell.Doorbells()
        rings.unanswered(rings.start('camera.porch', 'Porch', 60, ['a']))
        self.assertEqual(rings.bar_item()['b'], 1)
        self.assertIn('value["b"]', (ROOT / 'components/smart_display/page_receiver.cpp').read_text(),
                      'the top bar\'s item of a missed ring says so with `b` (doorbell.Doorbells.bar_item), which the '
                      'receiver reads to open that ring again: change both')

    def test_the_door_and_the_timeout_are_the_same_numbers(self):
        out = cxx(f'''#define THEME_TEST
#include "components/smart_display/doorbell_door.h"
#include "components/smart_display/doorbell_ring.h"
#include <cstdio>
int main() {{
  using doorbell_door::Kind;
  std::printf("%d %d %d\\n", doorbell_door::kind_of({doorbell.DOOR_LOCK}) == Kind::LOCK,
              doorbell_door::kind_of({doorbell.DOOR_ACTION}) == Kind::ACTION, doorbell_door::kind_of(0) == Kind::NONE);
  std::printf("%u %u %u\\n", (unsigned) doorbell_ring::TIMEOUT_S, (unsigned) doorbell_ring::TIMEOUT_MIN_S,
              (unsigned) doorbell_ring::TIMEOUT_MAX_S);
}}
''')
        if out is None:
            self.skipTest('no C++ compiler')
        kinds, timeouts = out.splitlines()[:2]
        self.assertEqual(kinds, '1 1 1', 'the app\'s DOOR_LOCK and DOOR_ACTION are the screen\'s lock and action '
                                         '(doorbell_door::kind_of): change both')
        self.assertEqual(tuple(map(int, timeouts.split())), (doorbell.TIMEOUT, doorbell.TIMEOUT_MIN, doorbell.TIMEOUT_MAX),
                         'a ring stays as long on the screen (doorbell_ring.h) as the app counts it (doorbell.TIMEOUT, '
                         'TIMEOUT_MIN, TIMEOUT_MAX): change both')

    def test_the_screen_reports_what_the_app_reads(self):
        report = package_yaml.script('doorbell_report')
        events = [step['homeassistant.event'] for step in package_yaml.steps(report) if 'homeassistant.event' in step]
        self.assertEqual([e['event'] for e in events], [doorbell.EVENT],
                         'the screen reports a ring\'s end as the one event the app listens to (doorbell.EVENT)')
        self.assertEqual(set(events[0]['data']), {'action', 'key', 'screen'},
                         'Manager.doorbell_report reads action, key and screen from the screen\'s report')
        module = (ROOT / 'components/smart_display/module_doorbell.cpp').read_text()
        self.assertEqual(set(re.findall(r'say\("(\w+)"\)', module)), {action for action, _ in doorbell.ENDINGS} | {doorbell.DOOR},
                         'module_doorbell.cpp says the endings the app knows (doorbell.ENDINGS) and the door key\'s "door", '
                         'no others: change both, and docs/DOORBELL.md')

    def test_the_hello_says_doorbell(self):
        self.assertEqual(len(re.findall(rf'features\.add\("{doorbell.FEATURE}"\)', (ROOT / 'packages/core.yaml').read_text())), 1,
                         f'a screen that draws a ring says "{doorbell.FEATURE}" in its hello, once: the app sends the op only '
                         'to such a screen')

    def test_whatever_holds_the_glass_for_an_alert_holds_it_for_a_ring(self):
        # Standby and Back to Home wait while an alert shows; a ring on the glass holds them too (a ring after two quiet
        # minutes closed at once without it).
        guards = 0
        for path in package_yaml.files():
            text = path.read_text()
            for found in re.finditer(r'\|\| id\(alert_active\)\) return false;', text):
                guards += 1
                self.assertIn('runtime_tiles::doorbell_holds()', text[found.end():text.find('then:', found.end())],
                              f'{path.relative_to(ROOT)}: a guard that waits while an alert shows waits while a ring shows '
                              'too: add `if (runtime_tiles::doorbell_holds()) return false;` after it')
        self.assertGreaterEqual(guards, 2, 'standby and Back to Home each wait while an alert shows')

    def test_no_switch_of_its_own(self):
        # Which screens get a ring is the event's `screen`, not a switch on each screen.
        for path in [*package_yaml.files(), *(ROOT / 'components/smart_display').glob('*.*')]:
            self.assertNotIn('ts_doorbell', path.read_text(errors='replace'),
                             f'{path.relative_to(ROOT)}: no doorbell switch; the event names its screens')

    def test_the_chime_has_half_a_second_ahead(self):
        # glass: a ring's chime on a Guition 4848S040 plays whole, without gaps. The chime is handed over every 250 ms
        # (camera_tick); at the bus's own rate ts_speaker's resampler hands it straight to the mixer's announcement input,
        # so that input holds half a second itself: with ESPHome's 100 ms a Guition's chime came in pieces of 200 ms with
        # gaps between (2026-10-28).
        player = package_yaml.load(ROOT / 'packages/features/audio-player.yaml')
        mixer = next(s for s in player['speaker'] if s.get('id') == 'ts_mixer')
        source = next(s for s in mixer['source_speakers'] if s['id'] == 'ts_announcement_input')
        self.assertEqual(source.get('buffer_duration'), '500ms', 'the mixer\'s announcement input holds half a second')


class TheAutomations(unittest.TestCase):
    automation = {'alias': 'Doorbell Front door', 'triggers': [{'trigger': 'doorbell.rang', 'target': {'entity_id': 'event.front_door_doorbell'}}],
                  'actions': [{'event': 'esp_screens_doorbell', 'event_data': {'camera': 'camera.front_door'}}]}

    def test_every_one_is_called_tessera(self):
        self.assertEqual(automations.checked('doorbell', self.automation)['alias'], 'Tessera: Doorbell Front door')
        self.assertEqual(automations.checked('doorbell', {**self.automation, 'alias': 'tessera:  Doorbell'})['alias'], 'Tessera: Doorbell')

    def test_only_our_events_and_our_ids(self):
        for wrong in ({**self.automation, 'actions': [{'action': 'lock.unlock', 'target': {'entity_id': 'lock.front'}}]},
                      {**self.automation, 'actions': [{'event': 'esp_screens_show_alert'}]},
                      {**self.automation, 'triggers': []}, {**self.automation, 'alias': ''}):
            with self.assertRaises(ValueError):
                automations.checked('doorbell', wrong)
        self.assertEqual(automations.kind_of(automations.new_id('alert')), 'alert')
        self.assertIsNone(automations.kind_of('morning_lights'))
        # A button's action rides inside our event, which the app performs when the button is pressed (the alert wizard).
        buttons = {**self.automation, 'alias': 'Someone at the door', 'actions': [{'event': 'esp_screens_show_alert', 'event_data': {
            'title': 'Someone at the door', 'button_text': 'Open', 'button_color': 'green', 'action': 'lock.unlock',
            'data': {'entity_id': 'lock.front_door'}, 'button2_text': 'Not now'}}]}
        self.assertEqual(automations.checked('alert', buttons)['actions'], buttons['actions'])

    def test_the_list_by_id_and_by_name(self):
        states = {'automation.tessera_doorbell': {'state': 'on', 'attributes': {'id': 'tessera_doorbell_0a1b2c3d', 'friendly_name': 'Tessera: Doorbell'}},
                  'automation.by_hand': {'state': 'off', 'attributes': {'id': '1700000000', 'friendly_name': 'Tessera: made by hand'}},
                  'automation.other': {'state': 'on', 'attributes': {'id': '1700000001', 'friendly_name': 'Morning lights'}}}
        listed = automations.listed(states)
        self.assertEqual([(item['entity'], item['kind']) for item in listed],
                         [('automation.tessera_doorbell', 'doorbell'), ('automation.by_hand', None)])
        self.assertEqual([item['entity'] for item in automations.listed(states, 'doorbell')], ['automation.tessera_doorbell'])


class Screen:
    def __init__(self, inbox, node, features=('doorbell',), online=True):
        self.record = {'id': inbox, 'node': node, 'name': node, 'online': online, 'room': ''}
        self.sender = type('Sender', (), {'features': set(features)})()


@unittest.skipUnless(HAS_AIOHTTP, 'aiohttp')
class TheManager(unittest.TestCase):
    def manager(self, screens):
        manager = Manager.__new__(Manager)
        manager.talks = talk_bridge.Links(None)
        manager.ha = type('HA', (), {})()
        manager.ha.states = {'camera.front_door': {'state': 'idle', 'attributes': {'friendly_name': 'Front door'}}}
        manager.ha.changed = asyncio.Event()
        manager.fired = []

        async def fire(event_type, data):
            manager.fired.append((event_type, data))
        manager.ha.fire = fire
        manager.page_senders = {s.record['id']: s.sender for s in screens}
        manager.screens = lambda: [s.record for s in screens]
        manager.transport = lambda inbox, screen=None: 'v2'
        manager.page_scope = lambda inbox: {}
        manager.device_name_of = lambda entity: None
        manager.alert_cameras = {}
        manager.doorbells = doorbell.Doorbells()
        manager.sent_messages, manager.broadcasts = [], []

        async def send_auxiliary(inbox, message, action, request):
            manager.sent_messages.append((inbox, message))
            return True

        async def broadcast(event_type, data, sound_kind='alert'):
            manager.broadcasts.append((event_type, data))
            return {'sent': len(data.get('screen') or []), 'skipped': 0, 'failed': 0}
        manager.send_auxiliary, manager.broadcast = send_auxiliary, broadcast
        manager.doorbell_unanswered = lambda key, timeout: asyncio.sleep(0)
        # The ring's own streams (Manager.doorbell_link): this app's address on each screen's network, its camera links.
        manager.live = live_stream.LiveFeed(None, None, lambda e: True)
        manager.warmed = []
        manager.live.warm = manager.warmed.append

        async def link_base(screen):
            return 'http://10.0.0.2:8099'
        manager.link_base = link_base
        manager.caps_of_screen = lambda screen: {'speaker': screen['id'] == 'a'}
        manager.picture_turn_of = lambda inbox: 0
        return manager

    def test_a_ring_opens_the_view_on_p4s_and_the_alert_elsewhere(self):
        screens = [Screen('a', 'hall'), Screen('b', 'kitchen'), Screen('c', 'cyd', features=()), Screen('d', 'off', online=False)]
        manager = self.manager(screens)
        result = asyncio.run(manager.doorbell_show({'camera': 'camera.front_door', 'timeout': 30}))
        self.assertEqual([inbox for inbox, _ in manager.sent_messages], ['a', 'b'])
        message = manager.sent_messages[0][1]
        self.assertEqual((message['e'], message['n'], message['t']), ('camera.front_door', 'Front door', 30))
        # Each view gets a stream of its own, made as the event came (docs/PLATFORM_PLAN.md 4.9): its room comes with the
        # screen's first open, its sound where the screen has a speaker.
        links = [m['l'] for _, m in manager.sent_messages]
        self.assertEqual(len(set(links)), 2)
        for (inbox, _), link in zip(manager.sent_messages, links):
            self.assertRegex(link, r'^http://10\.0\.0\.2:8099/camera/[\w-]+\.mjpeg$')
            made = manager.live.links[link.rsplit('/', 1)[1][:-len('.mjpeg')]]
            self.assertEqual((made.entity, made.box, made.screen, made.tile, made.sound),
                             ('camera.front_door', None, inbox, False, inbox == 'a'))
        self.assertEqual(manager.warmed, ['camera.front_door'], 'its camera starts before the first screen opens')
        self.assertEqual(manager.broadcasts, [('esp_screens_show_alert', {'title': 'Front door', 'icon': 'doorbell', 'camera': 'camera.front_door',
                                                                          'timeout': 30, 'screen': ['cyd', 'off']})])
        self.assertEqual((result['sent'], result['alerts']), (2, 2))
        self.assertIn('camera.front_door', manager.alert_cameras, 'the screens may open its camera')

        # The hall answers: the kitchen closes its view, the CYD its alert, and the app says so once.
        manager.sent_messages.clear()
        manager.broadcasts.clear()
        asyncio.run(manager.doorbell_report({'action': 'answered', 'key': message['k'], 'screen': 'hall'}))
        self.assertEqual(manager.sent_messages, [('b', {'v': 1, 'op': 'doorbell', 'k': message['k'], 'c': 1})])
        self.assertEqual(manager.broadcasts, [('esp_screens_dismiss_alert', {'screen': ['cyd', 'off']})])
        self.assertEqual(manager.fired, [('esp_screens_doorbell_answered', {'camera': 'camera.front_door', 'title': 'Front door', 'screen': 'hall'})])
        asyncio.run(manager.doorbell_report({'action': 'closed', 'key': message['k'], 'screen': 'kitchen'}))
        self.assertEqual(len(manager.fired), 1)

    def test_the_event_names_its_screens(self):
        manager = self.manager([Screen('a', 'hall'), Screen('b', 'kitchen')])
        asyncio.run(manager.doorbell_show({'camera': 'camera.front_door', 'title': 'Back door', 'screen': 'kitchen'}))
        self.assertEqual([(inbox, message['n']) for inbox, message in manager.sent_messages], [('b', 'Back door')])
        self.assertEqual(manager.broadcasts, [])

    def test_without_a_camera_nothing(self):
        manager = self.manager([Screen('a', 'hall')])
        self.assertEqual(asyncio.run(manager.doorbell_show({'title': 'Door'}))['sent'], 0)
        self.assertEqual(manager.sent_messages, [])

    def test_dismiss_closes_every_open_ring(self):
        manager = self.manager([Screen('a', 'hall')])
        asyncio.run(manager.doorbell_show({'camera': 'camera.front_door'}))
        key = manager.sent_messages[0][1]['k']
        manager.sent_messages.clear()
        asyncio.run(manager.doorbell_dismiss({}))
        self.assertEqual(manager.sent_messages, [('a', {'v': 1, 'op': 'doorbell', 'k': key, 'c': 1})])

    def test_the_door_key_unlocks_the_lock_from_the_screen_that_shows_it(self):
        manager = self.manager([Screen('a', 'hall'), Screen('b', 'kitchen')])
        manager.registry_index = lambda: {}
        manager.ha.states['lock.front_door'] = {'state': 'locked', 'attributes': {}}
        calls = []

        async def call(action, data):
            calls.append((action, data))
        manager.ha.call = call
        asyncio.run(manager.doorbell_show({'camera': 'camera.front_door', 'lock': 'lock.front_door', 'screen': 'hall'}))
        message = manager.sent_messages[0][1]
        self.assertEqual((message['d'], message['ds']), (doorbell.DOOR_LOCK, 'locked'))
        asyncio.run(manager.doorbell_report({'action': 'door', 'key': message['k'], 'screen': 'kitchen'}))
        self.assertEqual(calls, [], 'the kitchen never showed this ring')
        asyncio.run(manager.doorbell_report({'action': 'door', 'key': message['k'], 'screen': 'hall'}))
        self.assertEqual(calls, [('lock.unlock', {'entity_id': 'lock.front_door'})])

    def test_the_door_key_performs_the_action_and_a_lock_with_a_code_gets_none(self):
        manager = self.manager([Screen('a', 'hall')])
        manager.registry_index = lambda: {}
        manager.ha.states['lock.front_door'] = {'state': 'locked', 'attributes': {'code_format': r'^\d{4}$'}}
        calls = []

        async def call(action, data):
            calls.append((action, data))
        manager.ha.call = call
        asyncio.run(manager.doorbell_show({'camera': 'camera.front_door', 'lock': 'lock.front_door'}))
        self.assertNotIn('d', manager.sent_messages[0][1], 'no keypad on the view: no key without a default code')
        manager.sent_messages.clear()
        asyncio.run(manager.doorbell_show({'camera': 'camera.front_door', 'door_action': 'button.press', 'door_data': {'entity_id': 'button.gate'}}))
        message = manager.sent_messages[0][1]
        self.assertEqual(message['d'], doorbell.DOOR_ACTION)
        asyncio.run(manager.doorbell_report({'action': 'door', 'key': message['k'], 'screen': 'hall'}))
        self.assertEqual(calls, [('button.press', {'entity_id': 'button.gate'})])

    def test_a_missed_ring_is_seen_once(self):
        manager = self.manager([Screen('a', 'hall')])
        key = manager.doorbells.start('camera.front_door', 'Front door', 60, ['a'])
        manager.doorbells.unanswered(key)
        asyncio.run(manager.doorbell_report({'action': 'seen', 'key': key, 'screen': 'hall'}))
        self.assertIsNone(manager.doorbells.bar_item())
        self.assertTrue(manager.ha.changed.is_set(), 'the top bars are sent again')


if __name__ == '__main__':
    unittest.main()
