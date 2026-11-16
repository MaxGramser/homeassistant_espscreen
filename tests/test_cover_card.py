"""The cover card (app 0.2.58 / firmware 0.2.50), and two fixes found on Studio 1 after updating to 0.2.57.

- A tap on a cover opens a card like Home Assistant's own: a position slider, a tilt slider for slats, open,
  stop and close, and the battery of a battery-powered blind (Motionblinds keep it on a sensor of the device).
  The layout and the drawing are checked on the Mac host builds; tests/test_tile_controls.cpp covers the logic.
- A number whose value equals its initial state (a night brightness of 0) was never published, so Home
  Assistant showed "unknown" and ESP Screens could not change it.
- While a screen restarts its device name sensor reads "unavailable", which the app took for the device name.
"""
from firmware_sources import runtime_source
from manager_fixtures import with_screen_grid
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import ATTRS, cover_related, discover_screens, extras, state_message  # noqa: E402
import core  # noqa: E402
import page_layout  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
RUNTIME = runtime_source()
PROFILES = {name: profiles.text(name) for name in ('checkout/guition.yaml', 'checkout/cyd.yaml', 'packages/guition.yaml', 'packages/cyd.yaml')}
BLIND = 'cover.venetianblind_0001'


def motionblinds():
    """(states, device registry entries) of a Motionblinds venetian blind as Home Assistant 2026.9.1 reports it in Dutch."""
    states = {
        BLIND: {'state': 'open', 'attributes': {'friendly_name': 'Blind Links', 'current_position': 60, 'current_tilt_position': 40,
                                                'device_class': 'blind', 'supported_features': 255}},
        'sensor.venetianblind_0001_batterij': {'state': '85', 'attributes': {'device_class': 'battery', 'unit_of_measurement': '%'}},
        'sensor.venetianblind_0001_signaalsterkte': {'state': '-60', 'attributes': {}},
    }
    device = [{'entity_id': eid, 'platform': 'motion_blinds', 'device_id': 'blind'} for eid in states]
    return states, device


class CoverMessages(unittest.TestCase):
    def test_the_card_gets_the_tilt_and_the_battery_of_the_device(self):
        states, device = motionblinds()
        self.assertIn('current_tilt_position', ATTRS)
        extra = extras({'entity': BLIND}, states, device=device)
        self.assertEqual(extra, {'bat': 85})
        self.assertEqual(cover_related(BLIND, device, states), {'battery': 'sensor.venetianblind_0001_batterij'})
        message = state_message(0, {'entity': BLIND, 'name': ''}, states, extra)
        self.assertEqual((message['a']['current_position'], message['a']['current_tilt_position'], message['a']['supported_features']), (60, 40, 255))
        self.assertEqual(message['x'], {'bat': 85})
        # No battery sensor, or a cover that reports battery_level itself: nothing extra.
        self.assertIsNone(extras({'entity': BLIND}, states, device=device[:1]))
        states[BLIND]['attributes']['battery_level'] = 90
        self.assertIsNone(extras({'entity': BLIND}, states, device=device))
        states['sensor.venetianblind_0001_batterij']['state'] = 'unavailable'
        del states[BLIND]['attributes']['battery_level']
        self.assertIsNone(extras({'entity': BLIND}, states, device=device))

    def test_a_restarting_screen_is_not_named_unavailable(self):
        registry = [{'entity_id': 'text.studio_1_tile_settings', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                    {'entity_id': 'sensor.studio_1_device_name', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                    {'entity_id': 'sensor.studio_1_ip_address', 'platform': 'esphome', 'original_name': 'IP address', 'device_id': 'd1'}]
        devices = [{'id': 'd1', 'name': 'Studio 1'}]
        for state in ('unavailable', 'unknown'):
            states = {'text.studio_1_tile_settings': {'state': 'unavailable'}, 'sensor.studio_1_device_name': {'state': state},
                      'sensor.studio_1_ip_address': {'state': 'unavailable'}}
            screen = discover_screens(registry, states, devices, [])[0]
            self.assertEqual((screen['node'], screen['ip']), (None, None), state)
        states['sensor.studio_1_device_name']['state'] = 'studio-1'
        self.assertEqual(discover_screens(registry, states, devices, [])[0]['node'], 'studio-1')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class CoverSync(unittest.IsolatedAsyncioTestCase):
    async def test_a_battery_change_reaches_the_card_and_restarts_publish_no_second_sensor(self):
        import test_scaling
        from server import Manager
        states, device = motionblinds()
        with tempfile.TemporaryDirectory() as tmp:
            ha = test_scaling.fake_ha(firmware='0.2.50')
            ha.registry = ha.registry + [{**item} for item in device]
            ha.states.update(states)
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            m.save('text.screen', {'title': 'Office 1', 'tiles': [{'entity': BLIND, 'name': ''}]})
            self.assertIn('sensor.venetianblind_0001_batterij', m.watched_entities(), 'a battery change wakes the sync')
            self.assertEqual(m.related_entities({'entity': BLIND}), ('sensor.venetianblind_0001_batterij',))
            message = await m.tile_message(0, m.layouts['text.screen']['tiles'][0])
            self.assertEqual(message['x'], {'bat': 85})
            # The screen restarts: its device name reads unavailable, and no layout sensor goes out under that name.
            published = []

            async def set_state(entity_id, state, attributes):
                published.append(entity_id)
            ha.set_state = set_state
            ha.states['text.node'] = {'state': 'unavailable'}
            await m.publish_layouts()
            self.assertEqual(published, [])
            ha.states['text.node'] = {'state': 'office-1'}
            await m.publish_layouts()
            self.assertEqual(published, ['sensor.esp_screens_office_1'])


class SlatsOpenAt(unittest.TestCase):
    """Where a cover's slats stand open (tilt_open): Home Assistant's rule (0 closed, 100 fully open) is the default and
    never stored; 50 is a tile's choice for a blind closed at 0 and at 100, one way and the other (catalogue/cover.yaml)."""

    def test_the_app_keeps_50_and_stores_no_default(self):
        def layout(entity, value):
            return {'title': 'Home', 'tiles': [{'entity': entity, 'slot': 0, 'options': {'tilt_open': value}}]}
        self.assertEqual(core.validate_layout(layout('cover.blind', '50'))['tiles'][0]['options'], {'tilt_open': '50'})
        self.assertEqual(core.validate_layout(layout('cover.blind', 50))['tiles'][0]['options'], {'tilt_open': '50'})
        self.assertEqual(core.validate_layout(layout('cover.blind', '100'))['tiles'][0].get('options', {}), {})
        for bad in (layout('cover.blind', '30'), layout('light.a', '50')):
            with self.assertRaises(ValueError):
                core.validate_layout(bad)
        self.assertEqual(list(core.COVER_TILT_OPEN), ['100', '50'])
        # An event may set it too (esp_screens_add_tile and friends), and the page document carries it as an interaction.
        self.assertEqual(core.tile_options({'tilt_open': '50'}), {'tilt_open': '50'})
        self.assertEqual(page_layout.INTERACTION['tilt_open'], 'tilt_open')

    def test_it_reaches_the_screen(self):
        states = {'cover.blind': {'state': 'open', 'attributes': {'current_tilt_position': 50, 'supported_features': 255}}}
        message = core.state_message(0, {'entity': 'cover.blind', 'name': '', 'options': {'tilt_open': '50'}}, states)
        self.assertEqual(message['o']['tilt_open'], '50')
        # The screen takes it: web/wasm/test_cover_card.mjs (slats open at 50 have their end stop there).


class Firmware(unittest.TestCase):
    """The cover's card is read from the real firmware in web/wasm/test_cover_card.mjs: a tap and a hold open it, its
    status line (with the tilt the app sends) survives the tick, the slider sends set_cover_position once on release, a
    key acts, a key at its end stop is faded, and tilt_open 50 moves the slats' end stop. tests/test_tile_controls.cpp
    holds every domain's tap and hold route, and the percentage helper's directions and masks."""

    def test_the_preview_opens_the_card_a_hold_opens(self):
        # Rule: the profiles hand the browser preview the firmware's own way to a card (app 0.4.86).
        for name, text in PROFILES.items():
            self.assertIn('runtime_tiles::hold_card(index);', text, f'{name}: the preview opens the card a hold opens')

    def test_the_swap_key_starts_over_with_a_new_layout(self):
        # Kept as a quote until a preview test swaps a small cover tile and sends another layout (the swap key shows on
        # the smallest cover tiles only): the swap stands by tile index, and a new layout may put another cover at that
        # index (cancel_layout_input).
        cancel = RUNTIME[RUNTIME.index('inline void cancel_layout_input(bool invalidate_widgets) {'):]
        cancel = cancel[:cancel.index('\n}\n')]
        self.assertIn('cover_swapped.fill(0);', cancel, 'a new layout forgets every swap')
        self.assertLess(cancel.index('if (invalidate_widgets) {'), cancel.index('cover_swapped.fill(0);'), 'when its cards go')

    def test_a_slider_has_one_radius(self):
        # Rule: track and fill share one radius, so the CYD draws no layer for each redraw.
        self.assertIn('lv_obj_set_style_radius(slider,radius,LV_PART_MAIN);lv_obj_set_style_radius(slider,radius,LV_PART_INDICATOR);', RUNTIME,
                      "a cover slider's track and fill take one radius")

    def test_every_setting_number_publishes_a_value_home_assistant_lacks(self):
        # Rule (core.yaml, which the preview does not run): a setting's number publishes only a value Home Assistant lacks.
        for name, text in PROFILES.items():
            script = text[text.index('- id: apply_screen_settings'):]
            script = script[:script.index('\n  - id: ', 10)]
            self.assertIn('if (!entity->has_state() || entity->state != value) entity->publish_state(value);', script, name)
            for number in ('setting_brightness', 'setting_standby_brightness', 'setting_night_brightness', 'setting_standby_seconds', 'setting_auto_home_seconds'):
                self.assertIn(f'std::make_pair(id({number}),', script, f'{name}: {number}')
            self.assertNotRegex(script, r'if \(id\(setting_\w+\)\.state != ', name)


class AwningWithoutFeedback(unittest.TestCase):
    """An awning whose motor does not report back (Somfy RTS, 433 MHz): Home Assistant's state is "unknown" and
    assumed_state is true, and its frontend keeps open, stop and close working (data/cover.ts canOpen, canClose)."""

    def test_its_assumed_state_reaches_the_screen(self):
        import core
        states = {'cover.awning': {'state': 'unknown', 'attributes': {'friendly_name': 'Awning', 'supported_features': 11,
                                                                     'device_class': 'awning', 'assumed_state': True}}}
        message = core.state_message(0, {'entity': 'cover.awning', 'name': ''}, states)
        self.assertEqual(message['state'], 'unknown')
        self.assertIs(message['a']['assumed_state'], True)


if __name__ == '__main__':
    unittest.main()
