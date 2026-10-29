from manager_fixtures import seed_layout
"""What Home Assistant says an entity can do (app 0.2.67): the editor offers On / off, a small slider, direct controls
and displays from Home Assistant's own action list, and a save refuses a new setting Home Assistant doesn't support.

SERVICES are real action descriptions (`get_services` of Home Assistant 2026.9.2, trimmed to what the tests use); the
entities carry the supported_features of real devices. On that installation `local_actions` gave the same answer as
Home Assistant's `get_services_for_target` for 30 entities out of 30."""
from manager_fixtures import with_screen_grid
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import ha_catalogue  # noqa: E402
from core import validate_layout  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import HomeAssistant, Manager, Refused, create_app
    from aiohttp.test_utils import TestClient, TestServer

SERVICES = json.loads('''{"cover":{"toggle":{"target":{"entity":[{"domain":["cover"],"supported_features":[3]}]}},
"open_cover":{"target":{"entity":[{"domain":["cover"],"supported_features":[1]}]}},"close_cover":{"target":{"entity":[{"domain":["cover"],"supported_features":[2]}]}},
"stop_cover":{"target":{"entity":[{"domain":["cover"],"supported_features":[8]}]}},"set_cover_position":{"target":{"entity":[{"domain":["cover"],"supported_features":[4]}]}}},
"media_player":{"toggle":{"target":{"entity":[{"domain":["media_player"],"supported_features":[384]}]}},"turn_on":{"target":{"entity":[{"domain":["media_player"],"supported_features":[128]}]}},
"turn_off":{"target":{"entity":[{"domain":["media_player"],"supported_features":[256]}]}},"volume_set":{"target":{"entity":[{"domain":["media_player"],"supported_features":[4]}]}},
"volume_mute":{"target":{"entity":[{"domain":["media_player"],"supported_features":[8]}]}},"media_play_pause":{"target":{"entity":[{"domain":["media_player"],"supported_features":[16385]}]}},
"media_next_track":{"target":{"entity":[{"domain":["media_player"],"supported_features":[32]}]}},"media_previous_track":{"target":{"entity":[{"domain":["media_player"],"supported_features":[16]}]}}},
"light":{"toggle":{"target":{"entity":[{"domain":["light"]}]}},"turn_on":{"target":{"entity":[{"domain":["light"]}]},"fields":{"brightness_pct":{"filter":{"attribute":{"supported_color_modes":["brightness","color_temp","hs","xy","rgb","rgbw","rgbww"]}},"selector":{"number":{"min":0.0,"max":100.0,"unit_of_measurement":"%","step":1.0,"mode":"slider"}}},"additional_fields":{"collapsed":true,"fields":{"white":{"filter":{"attribute":{"supported_color_modes":["white"]}}}}}}},
"turn_off":{"target":{"entity":[{"domain":["light"]}]}}},
"climate":{"toggle":{"target":{"entity":[{"domain":["climate"],"supported_features":[128,256]}]}},"set_temperature":{"target":{"entity":[{"domain":["climate"],"supported_features":[1,2]}]}},"set_hvac_mode":{"target":{"entity":[{"domain":["climate"]}]}}},
"homeassistant":{"toggle":{"target":{}},"restart":{}},"sonos":{"snapshot":{"target":{"entity":[{"integration":"sonos","domain":["media_player"]}]}}},
"scene":{"turn_on":{"target":{"entity":[{"domain":["scene"]}]}},"delete":{"target":{"entity":[{"integration":"homeassistant","domain":["scene"]}]}}},
"script":{"turn_on":{"target":{"entity":[{"domain":["script"]}]}},"toggle":{"target":{"entity":[{"domain":["script"]}]}}},
"fan":{"toggle":{"target":{"entity":[{"domain":["fan"]}]}},"set_percentage":{"target":{"entity":[{"domain":["fan"],"supported_features":[1]}]}}},
"weather":{"get_forecasts":{"target":{"entity":[{"domain":["weather"],"supported_features":[1,2,4]}]},"response":{"optional":false}}},
"switch":{"toggle":{"target":{"entity":[{"domain":["switch"]}]}}},"notify":{"send_message":{"target":{"entity":[{"domain":["notify"]}]}}}}''')

# entity: (state, attributes, integration)
ENTITIES = {
    'media_player.sonos': ('idle', {'supported_features': 8321599, 'device_class': 'speaker', 'friendly_name': 'Bathroom'}, 'sonos'),
    'media_player.tv': ('off', {'supported_features': 24509, 'device_class': 'tv'}, 'webostv'),
    'cover.curtains': ('open', {'supported_features': 15, 'device_class': 'curtain', 'current_position': 100}, 'zha'),
    'cover.garage': ('closed', {'supported_features': 3, 'device_class': 'garage'}, 'demo'),
    'cover.position_only': ('open', {'supported_features': 4}, 'demo'),
    'light.hood': ('off', {'supported_features': 0, 'supported_color_modes': ['onoff']}, 'switch_as_x'),
    'light.bathroom': ('on', {'supported_features': 44, 'supported_color_modes': ['color_temp', 'xy']}, 'zha'),
    'climate.airco': ('cool', {'supported_features': 425, 'hvac_modes': ['off', 'cool']}, 'esphome'),
    'climate.old_thermostat': ('heat', {'supported_features': 1}, 'demo'),
    'scene.evening': ('2026-09-17T08:00:00+00:00', {}, 'homeassistant'),
    'script.wake_up': ('off', {}, 'script'),
    'fan.ceiling': ('off', {'supported_features': 0}, 'demo'),
    'sensor.temperature': ('21.456', {'unit_of_measurement': '°C', 'state_class': 'measurement'}, 'demo'),
    'sensor.washer': ('rinsing', {'device_class': 'enum'}, 'demo'),
    'weather.buienradar': ('rainy', {'supported_features': 1}, 'buienradar'),
    'weather.hourly_only': ('rainy', {'supported_features': 2}, 'demo'),
}


def state(entity):
    value, attributes, _ = ENTITIES[entity]
    return {'entity_id': entity, 'state': value, 'attributes': attributes}


def actions(entity):
    _, attributes, platform = ENTITIES[entity]
    return ha_catalogue.local_actions(SERVICES, entity, attributes, platform)


def caps(entity):
    return ha_catalogue.capabilities(entity, actions(entity), state(entity), SERVICES)


class ActionsForAnEntity(unittest.TestCase):
    def test_a_range_thermostat_offers_its_setpoint_and_one_without_a_temperature_does_not(self):
        # Firmware 0.19.0 draws a range on the -/+ with the chip for its end, as Home Assistant's tile has its target
        # temperature feature for one; an older screen gets it without them (core.drawn_controls).
        state = {'state': 'heat_cool', 'attributes': {'supported_features': 2}}
        result = ha_catalogue.capabilities('climate.range', ['climate.set_temperature', 'climate.set_hvac_mode'], state, SERVICES)
        self.assertIn('setpoint', result['controls'])
        self.assertIn('mode', result['controls'])
        fan_only = {'state': 'fan_only', 'attributes': {'supported_features': 8}}
        result = ha_catalogue.capabilities('climate.fan', ['climate.set_temperature', 'climate.set_hvac_mode'], fan_only, SERVICES)
        self.assertNotIn('setpoint', result['controls'])
        self.assertIn('mode', result['controls'])

    def test_home_assistants_target_filters(self):
        # Every mask of an action must be supported completely: a Sonos lacks on and off, a TV has both.
        self.assertNotIn('media_player.toggle', actions('media_player.sonos'))
        self.assertIn('media_player.toggle', actions('media_player.tv'))
        self.assertEqual([a for a in actions('cover.curtains') if a.startswith('cover.')],
                         ['cover.close_cover', 'cover.open_cover', 'cover.set_cover_position', 'cover.stop_cover', 'cover.toggle'])
        self.assertIn('cover.toggle', actions('cover.garage'))
        self.assertNotIn('cover.toggle', actions('cover.position_only'))
        # Either mask of climate.toggle will do.
        self.assertIn('climate.toggle', actions('climate.airco'))
        self.assertNotIn('climate.toggle', actions('climate.old_thermostat'))
        # An integration filter: only a Sonos gets sonos.snapshot; only scenes of Home Assistant itself can be deleted.
        self.assertIn('sonos.snapshot', actions('media_player.sonos'))
        self.assertNotIn('sonos.snapshot', actions('media_player.tv'))
        self.assertIn('scene.delete', actions('scene.evening'))
        # A target without an entity filter takes every entity; an action without a target is no entity action.
        self.assertIn('homeassistant.toggle', actions('sensor.washer'))
        self.assertNotIn('homeassistant.restart', actions('light.hood'))
        self.assertNotIn('notify.send_message', actions('light.hood'))

    def test_fields_follow_their_filter_also_inside_a_section(self):
        turn_on = SERVICES['light']['turn_on']
        self.assertFalse(ha_catalogue.field_matches(ha_catalogue.find_field(turn_on, 'brightness_pct'), {'supported_color_modes': ['onoff']}))
        self.assertTrue(ha_catalogue.field_matches(ha_catalogue.find_field(turn_on, 'brightness_pct'), {'supported_color_modes': ['xy']}))
        white = ha_catalogue.find_field(turn_on, 'white')
        self.assertIsNotNone(white, 'fields in a section (additional_fields) count too')
        self.assertTrue(ha_catalogue.field_matches(white, {'supported_color_modes': ['white', 'xy']}))
        self.assertTrue(ha_catalogue.field_matches({'selector': {}}, {}), 'a field without a filter is always there')


class CoverTiltCapabilities(unittest.TestCase):
    def test_tilt_combinations_require_both_groups_of_actions(self):
        choices = ['cover.open_cover', 'cover.set_cover_position', 'cover.set_cover_tilt_position',
                   'cover.open_cover_tilt', 'cover.stop_cover_tilt', 'cover.close_cover_tilt']
        for mask in range(1 << len(choices)):
            actions = [action for i, action in enumerate(choices) if mask & (1 << i)]
            controls = ha_catalogue.capabilities('cover.test', actions, {'state': 'open'}, {})['controls']
            tilt = bool(mask & 60)
            self.assertEqual('tilt' in controls, tilt)
            self.assertEqual('buttons_tilt' in controls, tilt and bool(mask & 1))
            self.assertEqual('position_tilt' in controls, tilt and bool(mask & 2))


class WhatTheEditorOffers(unittest.TestCase):
    def test_on_off_follows_home_assistant(self):
        self.assertFalse(caps('media_player.sonos')['toggle'])
        self.assertTrue(caps('media_player.tv')['toggle'])
        self.assertTrue(caps('cover.curtains')['toggle'], 'issue #7: a cover taps open and closed')
        self.assertTrue(caps('script.wake_up')['toggle'])
        self.assertFalse(caps('scene.evening')['toggle'])
        self.assertFalse(caps('sensor.temperature')['toggle'])

    def test_small_slider_and_direct_controls(self):
        self.assertEqual(caps('light.hood'), {'toggle': True, 'inline': False, 'controls': ['toggle'], 'displays': ['standard', 'watch']})
        self.assertEqual((caps('light.bathroom')['inline'], caps('light.bathroom')['controls']), (True, ['toggle', 'brightness', 'presets', 'brightness_presets']))
        self.assertEqual((caps('cover.curtains')['inline'], caps('cover.curtains')['controls']), (True, ['buttons', 'position']))
        self.assertEqual((caps('cover.garage')['inline'], caps('cover.garage')['controls']), (False, ['buttons']))
        self.assertEqual((caps('cover.position_only')['inline'], caps('cover.position_only')['controls']), (True, ['position']))
        # Volume over the playback keys came with the taller card (catalogue/media_player.yaml volume_playback, firmware 0.56.0).
        self.assertEqual(caps('media_player.sonos')['controls'], ['volume', 'playback', 'volume_playback'])
        self.assertEqual(caps('climate.old_thermostat')['controls'], ['setpoint', 'mode', 'setpoint_mode'])
        self.assertEqual((caps('fan.ceiling')['inline'], caps('fan.ceiling')['controls']), (False, ['toggle']))
        self.assertEqual(caps('scene.evening')['controls'], ['run'])

    def test_displays(self):
        self.assertIn('graph', caps('sensor.temperature')['displays'])
        self.assertNotIn('graph', caps('sensor.washer')['displays'])
        self.assertIn('forecast', caps('weather.buienradar')['displays'])
        self.assertNotIn('forecast', caps('weather.hourly_only')['displays'])
        unavailable = {'entity_id': 'weather.x', 'state': 'unavailable', 'attributes': {}}
        self.assertIn('forecast', ha_catalogue.capabilities('weather.x', [], unavailable, SERVICES)['displays'])


class NewSettingsOnly(unittest.TestCase):
    def test_a_new_setting_home_assistant_lacks_is_refused_a_saved_one_stays(self):
        sonos = {'entity': 'media_player.sonos', 'options': {'tap': 'toggle'}}
        self.assertEqual(ha_catalogue.unsupported(sonos, None, caps('media_player.sonos')), ('tap', 'toggle'))
        before = {'entity': 'media_player.sonos', 'options': {'tap': 'auto'}}
        self.assertEqual(ha_catalogue.unsupported(sonos, before, caps('media_player.sonos')), ('tap', 'toggle'))
        saved = {'entity': 'media_player.sonos', 'options': {'tap': 'toggle', 'background': 'blue'}}
        changed = {'entity': 'media_player.sonos', 'options': {'tap': 'toggle', 'background': 'red'}}
        self.assertIsNone(ha_catalogue.unsupported(changed, saved, caps('media_player.sonos')), 'a setting the tile already had stays')
        self.assertIsNone(ha_catalogue.unsupported(sonos, None, None), 'nothing is refused while Home Assistant cannot say')
        curtain = {'entity': 'cover.curtains', 'options': {'tap': 'toggle', 'inline': 'slider'}}
        self.assertIsNone(ha_catalogue.unsupported(curtain, None, caps('cover.curtains')))
        hood = {'entity': 'light.hood', 'options': {'inline': 'slider'}}
        self.assertEqual(ha_catalogue.unsupported(hood, None, caps('light.hood')), ('inline', 'slider'))
        self.assertEqual(ha_catalogue.unsupported({'entity': 'cover.garage', 'options': {'size': 'wide', 'controls': 'position'}}, None,
                                                  caps('cover.garage')), ('controls', 'position'))
        self.assertEqual(ha_catalogue.unsupported({'entity': 'sensor.washer', 'options': {'display': 'graph'}}, None, caps('sensor.washer')),
                         ('display', 'graph'))
        self.assertIn("can't turn Bathroom on and off", ha_catalogue.refusal('media_player.sonos', 'Bathroom', 'tap', 'toggle'))

    def test_a_setting_a_newer_app_saved_never_stops_the_app(self):
        stored = {'title': 'Hall', 'tiles': [{'entity': 'cover.curtains', 'name': '', 'slot': 0,
                                              'options': {'tap': 'swipe', 'swipe': {'action': 'cover.toggle'}}}]}
        with self.assertRaises(ValueError):
            validate_layout(stored)
        kept = validate_layout(stored, stored=True)
        self.assertEqual(kept['tiles'][0]['options'], stored['tiles'][0]['options'])
        with self.assertRaises(ValueError, msg='a broken entity still stops loading'):
            validate_layout({'title': 'Hall', 'tiles': [{'entity': 'nonsense', 'options': {}}]}, stored=True)


def fake_ha(target_lookup=True):
    class HA(HomeAssistant):
        def __init__(self):
            super().__init__(None, 'http://supervisor/core/api', 'token')
            self.registry = [{'entity_id': 'text.d1_tiles', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                             {'entity_id': 'sensor.d1_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                             {'entity_id': 'sensor.d1_fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'}]
            self.states = {'text.d1_tiles': {'state': 'Synced'}, 'sensor.d1_node': {'state': 'living-room'}, 'sensor.d1_fw': {'state': '0.2.58'}}
            for entity, (_, attributes, platform) in ENTITIES.items():
                self.registry.append({'entity_id': entity, 'platform': platform, 'device_id': 'd9'})
                self.states[entity] = state(entity)
            self.devices, self.areas = [{'id': 'd1', 'name': 'Living room screen'}, {'id': 'd9', 'name': 'Demo'}], []
            self.services, self.services_rev = SERVICES, 1
            self.asked, self.fired, self.published = [], [], {}

        async def request(self, kind, **data):
            self.asked.append((kind, data))
            if kind != 'get_services_for_target':
                raise AssertionError(kind)
            if not target_lookup:
                raise Refused('Unknown command.')
            entity = data['target']['entity_id'][0]
            return ha_catalogue.local_actions(SERVICES, entity, self.states[entity]['attributes'], ENTITIES[entity][2])

        async def fire(self, event_type, data):
            self.fired.append((event_type, data))

        async def set_state(self, entity_id, value, attributes):
            self.published[entity_id] = (value, attributes)
    return HA()


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class AskingHomeAssistant(unittest.IsolatedAsyncioTestCase):
    async def test_home_assistant_answers_and_the_answer_is_kept_per_entity(self):
        ha = fake_ha()
        self.assertFalse((await ha.capabilities('media_player.sonos'))['toggle'])
        self.assertTrue((await ha.capabilities('cover.curtains'))['toggle'])
        await ha.capabilities('cover.curtains')
        self.assertEqual([data['target'] for _, data in ha.asked], [{'entity_id': ['media_player.sonos']}, {'entity_id': ['cover.curtains']}])
        # New features, a new action list or a new registry ask again.
        ha.states['cover.curtains'] = {**state('cover.curtains'), 'attributes': {'supported_features': 4}}
        self.assertFalse((await ha.capabilities('cover.curtains'))['toggle'])
        ha.services_rev += 1
        await ha.capabilities('cover.curtains')
        self.assertEqual(len(ha.asked), 4)
        self.assertIsNone(await ha.capabilities('light.unknown'), 'no state: unknown, so nothing is refused')

    async def test_an_older_home_assistant_gets_the_same_answer_from_the_descriptions(self):
        ha = fake_ha(target_lookup=False)
        self.assertFalse((await ha.capabilities('media_player.sonos'))['toggle'])
        self.assertTrue((await ha.capabilities('cover.curtains'))['toggle'])
        self.assertEqual(len(ha.asked), 1, 'asked once; after "Unknown command" the descriptions answer')
        self.assertIs(ha.target_lookup, False)

    async def test_no_action_list_yet_means_unknown(self):
        ha = fake_ha()
        ha.services = {}
        self.assertIsNone(await ha.capabilities('cover.curtains'))
        self.assertEqual(ha.asked, [])

    async def test_saving_and_tile_events_refuse_only_new_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screens.json'
            m = Manager(with_screen_grid(fake_ha()), path)
            tiles = [{'entity': 'cover.curtains', 'name': '', 'slot': 0, 'options': {'tap': 'toggle'}},
                     {'entity': 'media_player.sonos', 'name': '', 'slot': 1}]
            data = {'title': 'Living room', 'tiles': tiles}
            await m.check_supported('text.d1_tiles', data)
            m.save('text.d1_tiles', data)
            refused = {'title': 'Living room', 'tiles': [tiles[0], {**tiles[1], 'options': {'tap': 'toggle'}}]}
            with self.assertRaisesRegex(ValueError, "can't turn Bathroom on and off"):
                await m.check_supported('text.d1_tiles', refused)
            # A layout saved before 0.2.67 with On / off on that speaker keeps saving when something else changes.
            historic = m.layouts['text.d1_tiles']
            historic['tiles'][1]['options'] = {'tap': 'toggle'}
            seed_layout(m, 'text.d1_tiles', historic)
            await m.check_supported('text.d1_tiles', {'title': 'Renamed', 'tiles': [tiles[0], {**tiles[1], 'options': {'tap': 'toggle'}}]})
            # Claude in Home Assistant gets the same answer.
            m.ha.tile_events = asyncio.Queue()
            m.ha.tile_events.put_nowait(('esp_screens_add_tile', {'entity': 'light.hood', 'inline': 'slider'}))
            m.ha.tile_events.put_nowait(('esp_screens_add_tile', {'entity': 'cover.garage', 'tap': 'toggle'}))
            worker = asyncio.create_task(m.tile_loop())
            for _ in range(200):
                await asyncio.sleep(0.01)
                if len(m.ha.fired) == 2:
                    break
            worker.cancel()
            answers = [answer for _, answer in m.ha.fired]
            self.assertFalse(answers[0]['ok'])
            self.assertIn('small slider', answers[0]['error'])
            self.assertTrue(answers[1]['ok'], answers[1])
            saved = m.layouts['text.d1_tiles']
            self.assertEqual({t['entity']: t.get('options', {}).get('tap') for t in saved['tiles']},
                             {'cover.curtains': 'toggle', 'media_player.sonos': 'toggle', 'cover.garage': 'toggle'})

    async def test_the_editor_asks_for_several_entities_at_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(with_screen_grid(fake_ha()), Path(tmp) / 'screens.json')
            async with TestClient(TestServer(create_app(m, True))) as client:
                answer = await (await client.get('/api/capabilities?entity=cover.curtains&entity=media_player.sonos&entity=light.unknown')).json()
        found = answer['capabilities']
        self.assertTrue(found['cover.curtains']['toggle'])
        self.assertFalse(found['media_player.sonos']['toggle'])
        self.assertIsNone(found['light.unknown'])


if __name__ == '__main__':
    unittest.main()
