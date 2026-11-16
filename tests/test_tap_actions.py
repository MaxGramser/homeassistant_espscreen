"""Perform action (app 0.2.67, firmware 0.2.58): a tap runs an action Home Assistant offers for the tile's entity, with
data for its fields. The editor lists the actions under Home Assistant's own names, a save accepts only what Home
Assistant would take, and the screen gets a compact form it sends as ESPHome action data and templates."""
from manager_fixtures import with_screen_grid
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import ha_catalogue  # noqa: E402
from core import (action_for_screen, apply_tile_event, layout_snapshot, screen_options, state_message,  # noqa: E402
                  validate_layout, validate_tap_action)
from test_ha_capabilities import ENTITIES, SERVICES, actions, state  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import Manager, Refused, create_app
    from aiohttp.test_utils import TestClient, TestServer
    from test_ha_capabilities import fake_ha

# Real descriptions of Home Assistant 2026.9.2 with their fields, and its English names for them.
DESCRIBED = copy.deepcopy(SERVICES)
DESCRIBED['cover']['set_cover_position']['fields'] = {
    'position': {'required': True, 'selector': {'number': {'min': 0.0, 'max': 100.0, 'unit_of_measurement': '%', 'step': 1.0, 'mode': 'slider'}}},
    'speed': {'example': 'fast', 'filter': {'supported_features': [256]}, 'selector': {'state': {'attribute': 'speed'}}}}
NAMES = {
    'component.cover.services.set_cover_position.name': 'Set cover position',
    'component.cover.services.set_cover_position.description': 'Moves a cover to a specific position.',
    'component.cover.services.set_cover_position.fields.position.name': 'Position',
    'component.cover.services.set_cover_position.fields.position.description': 'Target position.',
    'component.cover.services.toggle.name': 'Toggle cover',
    'component.homeassistant.services.toggle.name': 'Generic toggle',
    'component.sonos.services.snapshot.name': 'Snapshot',
}


def template_value(template):
    """What Home Assistant renders from a template the app wrote: `{{ "<json>" | from_json }}`."""
    inner = re.fullmatch(r'\{\{ (".*") \| from_json \}\}', template)
    return json.loads(json.loads(inner.group(1)))


class StoredAction(unittest.TestCase):
    def test_what_a_tap_action_may_hold(self):
        self.assertEqual(validate_tap_action({'action': 'cover.toggle'}), {'action': 'cover.toggle'})
        self.assertEqual(validate_tap_action({'action': 'sonos.snapshot', 'data': {'with_group': True}}),
                         {'action': 'sonos.snapshot', 'data': {'with_group': True}})
        for bad in ({'action': 'cover'}, {'action': 'Cover.toggle'}, {'action': 'cover.toggle', 'target': {}}, 'cover.toggle',
                    {'action': 'cover.toggle', 'data': {'entity_id': 'cover.other'}}, {'action': 'cover.toggle', 'data': {'Bad key': 1}},
                    {'action': 'light.turn_on', 'data': {f'f{i}': i for i in range(9)}},
                    {'action': 'light.turn_on', 'data': {'effect': 'x' * 500}},
                    {'action': 'light.turn_on', 'data': {'brightness': float('nan')}}):
            with self.assertRaises(ValueError, msg=bad):
                validate_tap_action(bad)

    def test_the_layout_keeps_the_action_only_with_perform_action(self):
        layout = validate_layout({'title': 'Hall', 'tiles': [
            {'entity': 'cover.curtains', 'options': {'tap': 'action', 'action': {'action': 'cover.set_cover_position', 'data': {'position': 50}}}},
            {'entity': 'light.hood', 'options': {'tap': 'toggle', 'action': {'action': 'light.turn_on'}}}]})
        self.assertEqual(layout['tiles'][0]['options']['action'], {'action': 'cover.set_cover_position', 'data': {'position': 50}})
        self.assertNotIn('action', layout['tiles'][1]['options'], 'another tap choice drops a stale action')
        with self.assertRaises(ValueError):
            validate_layout({'title': 'Hall', 'tiles': [{'entity': 'cover.curtains', 'options': {'tap': 'action'}}]})
        with self.assertRaises(ValueError):
            validate_layout({'title': 'Hall', 'tiles': [{'entity': 'screen.clock', 'options': {'tap': 'action', 'action': {'action': 'light.turn_on'}}}]})

    def test_the_screen_gets_text_as_data_and_every_other_value_as_a_template(self):
        value = {'action': 'light.turn_on', 'data': {'effect': 'colorloop', 'brightness_pct': 40, 'rgb_color': [255, 0, 0],
                                                      'flash': True, 'transition': 1.5, 'name': 'Café "late"'}}
        act = action_for_screen(validate_tap_action(value))
        self.assertEqual(act['s'], 'light.turn_on')
        self.assertEqual(act['d'], [['effect', 'colorloop'], ['name', 'Café "late"']])
        self.assertEqual({key: template_value(text) for key, text in act['t']},
                         {'brightness_pct': 40, 'rgb_color': [255, 0, 0], 'flash': True, 'transition': 1.5})
        tile = {'entity': 'cover.curtains', 'name': '', 'options': {'tap': 'action', 'action': {'action': 'cover.toggle'}}}
        self.assertEqual(screen_options(tile, {}), {'tap': 'action', 'act': {'s': 'cover.toggle'}})
        message = state_message(0, tile, {'cover.curtains': state('cover.curtains')})
        self.assertEqual(message['o'], {'tap': 'action', 'act': {'s': 'cover.toggle'}})
        broken = {'entity': 'cover.curtains', 'name': '', 'options': {'tap': 'action', 'action': {'action': 'nonsense'}}}
        self.assertEqual(screen_options(broken, {}), {'tap': 'action'}, 'a stored action the screen could not send stays behind')

    def test_tile_events_and_the_layout_sensor(self):
        layout = apply_tile_event({'title': 'Hall', 'tiles': []}, 'add',
                                  {'entity': 'cover.curtains', 'action': 'cover.set_cover_position', 'data': {'position': 30}})
        options = layout['tiles'][0]['options']
        self.assertEqual((options['tap'], options['action']), ('action', {'action': 'cover.set_cover_position', 'data': {'position': 30}}))
        kept = apply_tile_event(layout, 'add', {'entity': 'cover.curtains', 'tap': 'detail'})
        self.assertEqual(validate_layout(kept)['tiles'][0]['options'].get('tap'), 'detail')
        self.assertNotIn('action', validate_layout(kept)['tiles'][0]['options'])
        snapshot = layout_snapshot({'name': 'Hall'}, validate_layout(layout))
        self.assertEqual((snapshot['tiles'][0]['tap'], snapshot['tiles'][0]['action']['action']), ('action', 'cover.set_cover_position'))


class HomeAssistantsList(unittest.TestCase):
    def test_actions_under_home_assistants_names_with_the_fields_of_this_entity(self):
        found = ha_catalogue.action_choices('media_player.sonos', actions('media_player.sonos'), state('media_player.sonos'), DESCRIBED, NAMES, 'sonos')
        order = [item['action'] for item in found]
        self.assertLess(order.index('media_player.volume_set'), order.index('sonos.snapshot'))
        self.assertLess(order.index('sonos.snapshot'), order.index('homeassistant.toggle'))
        self.assertEqual(next(item for item in found if item['action'] == 'sonos.snapshot')['name'], 'Snapshot')
        curtains = ha_catalogue.action_choices('cover.curtains', actions('cover.curtains'), state('cover.curtains'), DESCRIBED, NAMES, 'zha')
        position = next(item for item in curtains if item['action'] == 'cover.set_cover_position')
        self.assertEqual((position['name'], position['description']), ('Set cover position', 'Moves a cover to a specific position.'))
        self.assertEqual([(f['key'], f['name'], f['required']) for f in position['fields']], [('position', 'Position', True)],
                         'speed needs the SPEED feature, which these curtains lack')
        self.assertEqual(next(item for item in curtains if item['action'] == 'cover.close_cover')['name'], 'cover.close_cover',
                         'without a name anywhere the action id stands in')
        weather = ha_catalogue.action_choices('weather.buienradar', actions('weather.buienradar'), state('weather.buienradar'), DESCRIBED, NAMES)
        self.assertNotIn('weather.get_forecasts', [item['action'] for item in weather], 'an action that only answers with data is left out')

    def test_a_field_that_asks_for_a_value_of_the_entity_lists_its_values(self):
        described = copy.deepcopy(DESCRIBED)
        described['media_player']['select_source'] = {'target': {'entity': [{'domain': ['media_player'], 'supported_features': [2048]}]},
                                                      'fields': {'source': {'required': True, 'selector': {'state': {'attribute': 'source'}}}}}
        sonos = {**state('media_player.sonos'), 'attributes': {**state('media_player.sonos')['attributes'], 'source_list': ['TV', 'NPO Radio 2', 'Qmusic']}}
        found = ha_catalogue.action_choices('media_player.sonos', ['media_player.select_source'], sonos, described, NAMES)
        self.assertEqual(found[0]['fields'][0]['options'], ['TV', 'NPO Radio 2', 'Qmusic'])
        self.assertEqual(ha_catalogue.attribute_options({'fan_modes': ['auto', 'low']}, 'fan_mode'), ['auto', 'low'])
        self.assertEqual(ha_catalogue.attribute_options({'supported_speeds': ['slow', 'fast']}, 'speed'), ['slow', 'fast'])
        self.assertIsNone(ha_catalogue.attribute_options({'source_list': []}, 'source'))

    def test_what_a_save_refuses(self):
        curtains = actions('cover.curtains')
        problem = lambda action, entity='cover.curtains', offered=curtains: ha_catalogue.action_problem(
            entity, 'Curtains', action, state(entity), offered, DESCRIBED)
        self.assertIsNone(problem({'action': 'cover.set_cover_position', 'data': {'position': 50}}))
        self.assertIsNone(problem({'action': 'cover.toggle'}))
        self.assertIn("doesn't offer media_player.volume_set", problem({'action': 'media_player.volume_set'}))
        self.assertIn('needs a value for position', problem({'action': 'cover.set_cover_position'}))
        self.assertIn('no field speed', problem({'action': 'cover.set_cover_position', 'data': {'position': 5, 'speed': 'fast'}}))
        self.assertIn('only answers with data', problem({'action': 'weather.get_forecasts'}, 'weather.buienradar', actions('weather.buienradar')))
        self.assertIsNone(problem({'action': 'cover.toggle'}, offered=None), 'nothing is refused while Home Assistant cannot say')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class SavingAndTheEditor(unittest.IsolatedAsyncioTestCase):
    async def test_the_names_come_with_the_action_list_and_a_refused_request_leaves_none(self):
        ha = fake_ha()
        answers = {'get_services': DESCRIBED, 'frontend/get_translations': {'resources': NAMES}, 'frontend/get_icons': {'resources': {}}}
        async def request(kind, **data):
            if kind in answers:
                return answers[kind]
            raise AssertionError(kind)
        ha.request = request
        await ha.fetch_services()
        self.assertEqual(ha.service_names['component.cover.services.toggle.name'], 'Toggle cover')
        async def refusing(kind, **data):
            if kind == 'frontend/get_translations':
                raise Refused('Unknown command.')
            return DESCRIBED
        ha.request, ha.service_names = refusing, {}
        await ha.fetch_services()
        self.assertEqual(ha.service_names, {})
        self.assertEqual(ha.services, DESCRIBED)

    async def test_a_save_takes_only_what_home_assistant_would(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            ha.services = DESCRIBED
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            def layout(action):
                return {'title': 'Living room', 'tiles': [{'entity': 'cover.curtains', 'name': '', 'slot': 0,
                                                           'options': {'tap': 'action', 'action': action}}]}
            with self.assertRaisesRegex(ValueError, 'needs a value for position'):
                await m.check_supported('text.d1_tiles', layout({'action': 'cover.set_cover_position'}))
            with self.assertRaisesRegex(ValueError, "doesn't offer light.turn_on"):
                await m.check_supported('text.d1_tiles', layout({'action': 'light.turn_on'}))
            good = layout({'action': 'cover.set_cover_position', 'data': {'position': 50}})
            await m.check_supported('text.d1_tiles', good)
            m.save('text.d1_tiles', good)
            # Home Assistant drops the action later (an integration removed): the saved tile still saves.
            ha.services = {key: value for key, value in DESCRIBED.items() if key != 'cover'}
            ha.services_rev += 1
            await m.check_supported('text.d1_tiles', {**good, 'title': 'Renamed'})
            saved = m.layouts['text.d1_tiles']
            self.assertEqual(saved['tiles'][0]['options']['action'], {'action': 'cover.set_cover_position', 'data': {'position': 50}})

    async def test_claude_in_home_assistant_sets_an_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screens.json'
            ha = fake_ha()
            ha.services = DESCRIBED
            m = Manager(with_screen_grid(ha), path)
            ha.tile_events = asyncio.Queue()
            ha.tile_events.put_nowait(('esp_screens_add_tile', {'entity': 'cover.curtains', 'action': 'cover.set_cover_position'}))
            ha.tile_events.put_nowait(('esp_screens_add_tile', {'entity': 'cover.curtains', 'action': 'cover.set_cover_position', 'data': {'position': 70}}))
            worker = asyncio.create_task(m.tile_loop())
            for _ in range(200):
                await asyncio.sleep(0.01)
                if len(ha.fired) == 2:
                    break
            worker.cancel()
            answers = [answer for _, answer in ha.fired]
            self.assertFalse(answers[0]['ok'])
            self.assertIn('needs a value for position', answers[0]['error'])
            self.assertTrue(answers[1]['ok'], answers[1])
            tile = m.layouts['text.d1_tiles']['tiles'][0]
            self.assertEqual(screen_options(tile, {})['act'], {'s': 'cover.set_cover_position', 't': [['position', '{{ "70" | from_json }}']]})

    async def test_the_editor_asks_for_an_entitys_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            ha.services, ha.service_names = DESCRIBED, NAMES
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            async with TestClient(TestServer(create_app(m, True))) as client:
                found = (await (await client.get('/api/entity-actions?entity=cover.curtains')).json())['actions']
                unknown = (await (await client.get('/api/entity-actions?entity=light.unknown')).json())['actions']
                nonsense = (await (await client.get('/api/entity-actions?entity=../etc')).json())['actions']
        self.assertEqual(found[0]['action'].split('.')[0], 'cover')
        self.assertIn({'action': 'cover.toggle', 'name': 'Toggle cover', 'description': '', 'fields': []}, found)
        self.assertIsNone(unknown)
        self.assertIsNone(nonsense)


class Editor(unittest.TestCase):
    def setUp(self):
        import editor_sources
        self.SCRIPT = editor_sources.SCRIPT
        self.PICKER = editor_sources.component('ActionPicker')

    def test_perform_action_is_a_tap_choice_with_home_assistants_list(self):
        import editor_sources
        self.assertIn('keys.push("action");', self.SCRIPT)
        self.assertEqual(editor_sources.text('tile.tap.action'), 'Perform action')
        self.assertIn('getJson(`entity-actions?entity=${encodeURIComponent(entity)}`)', self.SCRIPT)
        self.assertIn('<ActionPicker v-if="domain !== \'screen\' && !goesTo && tap === \'action\'" :tile="tile" />', self.SCRIPT)
        # Fields follow Home Assistant's selectors; an empty field is left out of the data.
        for marker in ("kindOf(field) === 'boolean'", "kindOf(field) === 'number' || kindOf(field) === 'color_temp'", 'config.options', 'delete data[key]'):
            self.assertIn(marker, self.PICKER, marker)
        self.assertIn('supports(0, 2, 58)', self.PICKER)


if __name__ == '__main__':
    unittest.main()
