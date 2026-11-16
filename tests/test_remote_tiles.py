"""A remote as a tile (firmware 0.22.0, GitHub #117): its card switches it on and off and lists its activities, as Home
Assistant's dialog does, and its keys are tiles that perform remote.send_command (2026.10 core and frontend:
remote/icons.json, remote/services.yaml, state_color.ts, more-info-remote.ts). Here: the add-on's side. The firmware is
read from its real cards in web/wasm/test_remote_card.mjs (the tile's icon and activity, the dialog's activities and
power key, the keypad's commands, every clean tap) and checked in tests/test_tile_controls.cpp (routes, keys, amber
while on); the editor in web/tests (layout.spec.ts: colours; tile-text.spec.ts: the activity; library.spec.ts: the
filter; tile-options.spec.ts: the commands offered for Send command).
"""
from firmware_sources import firmware_domains
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import catalogue  # noqa: E402
import core  # noqa: E402
import ha_catalogue  # noqa: E402
import header_bar  # noqa: E402
import tile_icons  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None

ACTIONS = {'remote.turn_on', 'remote.turn_off', 'remote.toggle', 'remote.send_command', 'remote.learn_command',
           'remote.delete_command'}


def layout(entity, **options):
    return {'title': 'Home', 'tiles': [{'entity': entity, 'slot': 0, **({'options': options} if options else {})}]}


class TheApp(unittest.TestCase):
    def test_a_remote_is_a_tile_and_a_top_bar_item(self):
        self.assertIn('remote', core.DOMAINS)
        self.assertTrue(core.entity_id('remote.living_room'))
        core.validate_header({'items': [{'type': 'entity', 'entity': 'remote.living_room'}]})
        # The top bar colours it as Home Assistant's badges do: amber while on, the calm grey while off.
        self.assertEqual(header_bar.accent('remote.a', {'state': 'on'}), header_bar.AMBER)
        self.assertIsNone(header_bar.accent('remote.a', {'state': 'off'}))
        self.assertEqual(header_bar.DOMAIN_ICONS['remote'], 'remote')

    def test_a_layout_with_one_waits_for_firmware_0_22_0(self):
        self.assertEqual(catalogue.of_type('remote')['firmware'], '0.22.0')
        self.assertEqual(core.min_firmware(layout('remote.a')), (0, 22, 0))
        self.assertGreaterEqual(tuple(map(int, core.FIRMWARE_VERSION.split('.'))), (0, 22, 0))
        # Older firmware refuses the domain; this one takes it.
        self.assertIn('remote', firmware_domains())

    def test_taps_and_the_wide_card_switch(self):
        for tap in ('auto', 'toggle', 'none', 'detail'):
            core.validate_layout(layout('remote.a', tap=tap))
        with self.assertRaises(ValueError):
            core.validate_layout(layout('remote.a', tap='run'))
        caps = ha_catalogue.capabilities('remote.a', ACTIONS, {'state': 'on', 'attributes': {}}, {})
        self.assertTrue(caps['toggle'])
        self.assertEqual(caps['controls'], ['toggle'])
        self.assertEqual(core.resolve_controls({'entity': 'remote.a', 'options': {'size': 'wide'}}), 'toggle')

    def test_a_key_is_perform_action_with_send_command(self):
        # Home Assistant lists no commands, so a key is a tile of its own: remote.send_command with a typed command.
        tile = core.validate_layout(layout('remote.a', tap='action', action={'action': 'remote.send_command',
                                                                               'data': {'command': 'play', 'device': 'bluray'}}))['tiles'][0]
        self.assertEqual(tile['options']['tap'], 'action')
        self.assertEqual(tile['options']['action']['action'], 'remote.send_command')

    def test_the_activities_reach_the_screen(self):
        activities = [f'Activity {n}' for n in range(20)]
        states = {'remote.hub': {'state': 'on', 'attributes': {'supported_features': 4, 'current_activity': 'Watch TV',
                                                                'activity_list': ['Watch TV', *activities]}}}
        attributes = core.state_message(0, {'entity': 'remote.hub', 'name': ''}, states)['a']
        self.assertEqual(attributes['current_activity'], 'Watch TV')
        # Sixteen at most, as a select's options: the card pages through them.
        self.assertEqual(len(attributes['activity_list']), 16)
        self.assertEqual(attributes['activity_list'][0], 'Watch TV')
        # A remote without activities (Broadlink, Apple TV) sends neither.
        plain = core.state_message(0, {'entity': 'remote.ir', 'name': ''}, {'remote.ir': {'state': 'on', 'attributes': {}}})['a']
        self.assertNotIn('activity_list', plain)


class CommandsFromTheSource(unittest.TestCase):
    """Send command offers what the remote's integration takes, read from Home Assistant and the library it pins
    (tools/read_remote_commands.py); typed text still goes, so a learned code or a hub's own name keeps working."""
    SEND = {'command': {'required': True, 'selector': {'object': {}}}, 'device': {'selector': {'text': {}}},
            'num_repeats': {'selector': {'number': {'min': 0, 'max': 255}}}}

    def choices(self, platform):
        services = {'remote': {'send_command': {'fields': self.SEND, 'target': {'entity': [{'domain': ['remote']}]}}}}
        found = ha_catalogue.action_choices('remote.tv', {'remote.send_command'}, {'state': 'on', 'attributes': {}}, services, {}, platform)
        return {field['key']: field for field in found[0]['fields']}

    def test_every_list_names_where_it_was_read(self):
        source = json.loads((ROOT / 'catalogue/_remote_commands.json').read_text())
        self.assertTrue(source['source'].startswith('home-assistant/core '))
        self.assertEqual(json.loads((ROOT / 'screen_manager/app/remote_commands.json').read_text()), source)
        for platform, entry in source['platforms'].items():
            self.assertTrue(entry['from'], platform)
            self.assertTrue(entry['commands'] and len(set(entry['commands'])) == len(entry['commands']), platform)
        # A library's pinned version, as Home Assistant's manifest has it.
        self.assertTrue(any(item.startswith('rokuecp==') for item in source['platforms']['roku']['from']))

    def test_send_command_offers_the_integrations_commands(self):
        roku = self.choices('roku')
        self.assertIn('play', roku['command']['suggestions'])
        self.assertIn('volume_up', roku['command']['suggestions'])
        # Only the command field, and nothing for an integration whose names live on the hub or in learned codes.
        self.assertNotIn('suggestions', roku['device'])
        self.assertNotIn('suggestions', self.choices('broadlink')['command'])
        self.assertNotIn('suggestions', self.choices(None)['command'])
        self.assertIn('DPAD_CENTER', catalogue.remote_commands('androidtv_remote'))
        # Android's keyboard and game pad keys are no TV remote's.
        self.assertFalse({'A', 'F1', 'BUTTON_A', 'NUMPAD_1', 'CTRL_LEFT'} & set(catalogue.remote_commands('androidtv_remote')))


class Keypad(unittest.TestCase):
    """A remote's keypad (firmware 0.22.0): a ring of arrows round OK and the round keys its integration has, each key the
    command that integration takes for it, checked against the list read from Home Assistant."""
    def test_each_integration_sends_its_own_names(self):
        self.assertEqual(catalogue.remote_keypad('apple_tv')[:6], ['up', 'down', 'left', 'right', 'select', 'menu'])
        self.assertEqual(catalogue.remote_keypad('androidtv_remote')[4], 'DPAD_CENTER')
        # A Sky box has no volume keys: the screen draws none.
        self.assertEqual(catalogue.remote_keypad('sky_remote')[8:], ['', '', ''])
        self.assertIsNone(catalogue.remote_keypad('broadlink'))
        self.assertIsNone(catalogue.remote_keypad(None))
        for platform, keys in catalogue.of_type('remote')['keypad'].items():
            for command in keys.values():
                self.assertIn(command, catalogue.remote_commands(platform), platform)

    def test_a_name_home_assistant_does_not_take_stops_the_generator(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('generate_catalogue', ROOT / 'tools/generate_catalogue.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        commands = {'roku': {'commands': ['up', 'down', 'left', 'right', 'select']}}
        module.keypad('remote', {'roku': {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right', 'ok': 'select'}}, commands)
        with self.assertRaises(module.CatalogueError):
            module.keypad('remote', {'roku': {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right', 'ok': 'enter'}}, commands)
        with self.assertRaises(module.CatalogueError):
            module.keypad('remote', {'harmony': {'up': 'up'}}, commands)



@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class KeypadReachesTheScreen(unittest.IsolatedAsyncioTestCase):
    async def test_a_remote_with_a_keypad_sends_its_integrations_keys(self):
        import test_scaling
        from manager_fixtures import with_screen_grid
        from server import Manager
        with tempfile.TemporaryDirectory() as tmp:
            ha = test_scaling.fake_ha(firmware='0.22.0')
            ha.registry = ha.registry + [{'entity_id': 'remote.box', 'platform': 'apple_tv'},
                                         {'entity_id': 'remote.ir', 'platform': 'broadlink'}]
            ha.states.update({'remote.box': {'state': 'on', 'attributes': {}}, 'remote.ir': {'state': 'on', 'attributes': {}}})
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            m.save('text.screen', {'title': 'Home', 'tiles': [{'entity': 'remote.box', 'name': ''}, {'entity': 'remote.ir', 'name': ''}]})
            box, ir = m.layouts['text.screen']['tiles']
            self.assertEqual((await m.tile_message(0, box))['x']['keys'], catalogue.remote_keypad('apple_tv'))
            self.assertNotIn('keys', (await m.tile_message(1, ir)).get('x', {}), 'an integration without a keypad sends none')


class HomeAssistantsWay(unittest.TestCase):
    def test_icons(self):
        # remote/icons.json: mdi:remote, mdi:remote-off while off; the firmware draws them (test_remote_card.mjs).
        self.assertEqual((tile_icons.GLYPHS['remote'], tile_icons.GLYPHS['remote-off']), ('F0454', 'F0EC4'))
        self.assertEqual(tile_icons.DEFAULTS['remote'], 'remote')
        self.assertIn('remote-off', tile_icons.BIG_GLYPHS)


if __name__ == '__main__':
    unittest.main()
