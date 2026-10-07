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
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
from core import ATTRS, cover_related, discover_screens, extras, state_message  # noqa: E402

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


class Firmware(unittest.TestCase):
    def test_a_tap_on_a_cover_opens_the_cover_card(self):
        event = RUNTIME[RUNTIME.index('inline void event(lv_event_t *event) {'):]
        event = event[:event.index('\n}\n')]
        # Since firmware 0.2.58 tile_controls::tap_route decides and event() carries the route out.
        controls = (ROOT / 'components/smart_display/tile_controls.h').read_text()
        cards = controls[controls.index('inline bool runtime_card_domain('):]
        cards = cards[:cards.index('\n}\n')]
        self.assertIn('d == "cover"', cards, 'covers go to show_detail with the other runtime cards')
        self.assertIn('d == "climate"', cards, 'a thermostat opens the computed card too (firmware 0.2.80)')
        self.assertIn('if (runtime_card_domain(d)) return {TapRoute::CARD, "", true};', controls)
        # Firmware 0.2.80: only a light with a colour still opens the board's own card; the rest is the runtime's.
        self.assertIn('return light_colour(t) ? Tap{TapRoute::OVERLAY', controls, "not to the board's value overlay any more")
        self.assertIn('d == "light" || d == "fan" ? Tap{TapRoute::CARD, "", true}', controls)
        self.assertIn('case tile_controls::TapRoute::CARD:', event)
        self.assertIn('show_detail(w.index);', event)
        self.assertIn('}else if(d=="cover"){', RUNTIME)
        self.assertIn('render_cover_detail(t,large,width,height,pad,columns);', RUNTIME)
        for name, text in PROFILES.items():
            # Firmware 0.2.80: the preview asks the firmware's own routing instead of listing domains, so it
            # opens whatever a hold opens - the runtime's card for a cover, a light that dims and a fan.
            self.assertIn('if (tile_controls::tap_route(tile, true).route == tile_controls::TapRoute::OVERLAY && runtime_tiles::detail) {',
                          text, f'{name}: the preview opens the card a hold opens')

    def test_the_card_commits_on_release_and_keeps_its_status_line(self):
        # Both views dispatch through the capability-checked percentage helper.
        # Percentage direction and all feature masks are exercised in C++.
        event = RUNTIME[RUNTIME.index('inline void cover_slider_event('):RUNTIME.index('inline lv_obj_t *cover_slider(')]
        self.assertIn('code!=LV_EVENT_RELEASED', event)
        self.assertIn('tile_controls::cover_position_action(t,lv_slider_get_value(slider),tilt)', event)
        self.assertIn('if(call.valid())action(call.service,t.entity,call.key,call.value)', event)
        self.assertIn('if(cmd>=70 && cmd<130){auto a=tile_controls::key_action(t,cmd-70);', RUNTIME)
        # The once-a-second tick of an open card must not replace "Open · 60% · Tilt 40%" with the raw state.
        tick = RUNTIME[RUNTIME.index('inline void tick() {'):]
        self.assertIn('card_status(t,detail_status_brief)', tick[:tick.index('if(!enabled)return;')])
        # A key the cover cannot use stays disabled: it paints itself faded at its end stop, also after the card waited
        # (docs/CARD_PARTS.md: the tick touches the keys only when the wait changes, then the card paints again).
        self.assertIn('paint_state(button,LV_STATE_DISABLED,card_blocked||key->disabled);', RUNTIME)
        self.assertIn('card_bind(button,t,cover_key_paint,"",key.command);', RUNTIME)
        # Track and fill share one radius: no layer per redraw on the CYD.
        self.assertIn('lv_obj_set_style_radius(slider,radius,LV_PART_MAIN);lv_obj_set_style_radius(slider,radius,LV_PART_INDICATOR);', RUNTIME)
        self.assertIn('next.tilt = number(a["current_tilt_position"]);', RUNTIME)

    def test_every_setting_number_publishes_a_value_home_assistant_lacks(self):
        for name, text in PROFILES.items():
            script = text[text.index('- id: apply_screen_settings'):]
            script = script[:script.index('\n  - id: ', 10)]
            self.assertIn('if (!entity->has_state() || entity->state != value) entity->publish_state(value);', script, name)
            for number in ('setting_brightness', 'setting_standby_brightness', 'setting_night_brightness', 'setting_standby_seconds', 'setting_auto_home_seconds'):
                self.assertIn(f'std::make_pair(id({number}),', script, f'{name}: {number}')
            self.assertNotRegex(script, r'if \(id\(setting_\w+\)\.state != ', name)


if __name__ == '__main__':
    unittest.main()
