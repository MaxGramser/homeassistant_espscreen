"""An automation as a tile (firmware 0.7.0, GitHub #62): a tap switches it on or off and holding the tile runs its actions,
or with the tap option `run` the other way round, as Home Assistant (its 2026.9 core and frontend:
automation/icons.json, state_color.ts, DOMAINS_TOGGLE and more-info-automation.ts). tests/test_tile_controls.cpp checks
the firmware's routes (trigger with the entity alone), keys and colours (a run button only while it runs);
web/wasm/test_automation_tile.mjs reads the real tiles (icons, colours, the app's `run`, a tap and a run button);
the editor's choices and colours are in web/tests (tile-options.spec, pages.spec, layout.spec). Here: the app's side.
"""
from firmware_sources import firmware_domains
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import catalogue  # noqa: E402
import core  # noqa: E402
import ha_catalogue  # noqa: E402
import header_bar  # noqa: E402
import tile_icons  # noqa: E402



def layout(entity, **options):
    return {'title': 'Home', 'tiles': [{'entity': entity, 'slot': 0, **({'options': options} if options else {})}]}


class TheApp(unittest.TestCase):
    def test_an_automation_is_a_tile_and_a_top_bar_item(self):
        self.assertIn('automation', core.DOMAINS)
        self.assertTrue(core.entity_id('automation.curtains_at_sunset'))
        core.validate_header({'items': [{'type': 'entity', 'entity': 'automation.curtains_at_sunset'}]})
        # The top bar colours it as Home Assistant's badges do: amber while on, the calm grey while off.
        self.assertEqual(header_bar.accent('automation.a', {'state': 'on'}), header_bar.AMBER)
        self.assertIsNone(header_bar.accent('automation.a', {'state': 'off'}))
        self.assertEqual(header_bar.DOMAIN_ICONS['automation'], 'robot')

    def test_a_layout_with_one_waits_for_firmware_0_7_0(self):
        self.assertEqual(core.AUTOMATION_MIN_FIRMWARE, (0, 7, 0))
        self.assertEqual(core.min_firmware(layout('automation.a')), (0, 7, 0))
        self.assertLessEqual(core.AUTOMATION_MIN_FIRMWARE, tuple(int(n) for n in core.FIRMWARE_VERSION.split('.')))
        # Older firmware refuses the domain; this one takes it.
        self.assertIn('automation', firmware_domains())

    def test_run_is_a_tap_choice_of_an_automation_alone(self):
        self.assertEqual(core.validate_layout(layout('automation.a', tap='run'))['tiles'][0]['options'], {'tap': 'run'})
        for tap in ('auto', 'toggle', 'none', 'detail'):
            core.validate_layout(layout('automation.a', tap=tap))
        for entity in ('script.a', 'switch.a', 'scene.a'):
            with self.assertRaises(ValueError):
                core.validate_layout(layout(entity, tap='run'))
        # The editor offers and validates the same choice (tile-options.spec.ts, pages.spec.ts), and the screen runs a
        # tile set to it (test_automation_tile.mjs).
        self.assertEqual(catalogue.taps('automation'), [*catalogue.TILE['taps'], 'run'])
        self.assertEqual(core.screen_options({'entity': 'automation.a', 'options': {'tap': 'run'}}, {})['tap'], 'run')

    def test_when_it_last_ran_and_whether_it_runs_now(self):
        def states(state='on', **attributes):
            return {'automation.a': {'state': state, 'attributes': attributes}}
        tile = {'entity': 'automation.a'}
        self.assertEqual(core.extras(tile, states(last_triggered='2026-09-27T10:00:00+00:00', current=0)), {'last': 1790503200})
        self.assertEqual(core.extras(tile, states(last_triggered='2026-09-27T10:00:00+00:00', current=2)), {'last': 1790503200, 'run': True})
        self.assertEqual(core.extras(tile, states('off', current=1)), {'run': True})
        self.assertIsNone(core.extras(tile, states(last_triggered=None, current=0)))
        self.assertIsNone(core.extras(tile, states()))

    def test_the_wide_card_controls(self):
        self.assertEqual([key for key, _ in core.CONTROLS['automation']], ['toggle', 'run'])
        actions = {'automation.toggle', 'automation.trigger', 'automation.turn_on', 'automation.turn_off', 'automation.reload'}
        caps = ha_catalogue.capabilities('automation.a', actions, {'state': 'on', 'attributes': {}}, {})
        self.assertTrue(caps['toggle'])
        self.assertEqual(caps['controls'], ['toggle', 'run'])
        wide = {'entity': 'automation.a', 'options': {'size': 'wide'}}
        self.assertEqual(core.resolve_controls(wide), 'toggle')


class HomeAssistantsWay(unittest.TestCase):
    def test_icons(self):
        # automation/icons.json: mdi:robot, mdi:robot-off while off, mdi:robot-confused while unavailable.
        self.assertEqual((tile_icons.GLYPHS['robot'], tile_icons.GLYPHS['robot-off'], tile_icons.GLYPHS['robot-confused']),
                         ('F06A9', 'F16A7', 'F169F'))
        self.assertEqual(tile_icons.DEFAULTS['automation'], 'robot')
        self.assertIn('robot-off', tile_icons.BIG_GLYPHS)

if __name__ == '__main__':
    unittest.main()
