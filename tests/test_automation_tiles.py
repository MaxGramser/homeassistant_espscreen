"""An automation as a tile (firmware 0.7.0, GitHub #62): a tap switches it on or off and holding the tile runs its actions,
or with the tap option `run` the other way round. tests/test_tile_controls.cpp checks the firmware's routes and colours;
these keep the app, the firmware and the editor in step with each other and with Home Assistant (its 2026.9 core and
frontend: automation/icons.json, state_color.ts, DOMAINS_TOGGLE and more-info-automation.ts).
"""
from firmware_sources import firmware_domains, runtime_source
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

COMPONENT = ROOT / 'components/smart_display'
MODEL = (COMPONENT / 'runtime_model.h').read_text()
CONTROLS = (COMPONENT / 'tile_controls.h').read_text()
RECEIVER = (COMPONENT / 'page_receiver.cpp').read_text()
TILES = runtime_source()
VALIDATION = (ROOT / 'web/src/model/page-validation.ts').read_text()
INSPECTOR = (ROOT / 'web/src/model/tile-options.ts').read_text()
PALETTE = (ROOT / 'web/src/model/tile-palette.ts').read_text()


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
        # The editor offers and validates the same choice, and the firmware reads the tap option as it is.
        self.assertEqual(catalogue.taps('automation'), [*catalogue.TILE['taps'], 'run'])
        # (A plugin's tap action is the one exception, checked by the plugin's manifest: page-validation.ts.)
        self.assertIn("? undefined : i.tap, catalogueTaps(domain)]", VALIDATION)
        self.assertIn('const keys = ["auto", "run", "none", "action"];', INSPECTOR)
        self.assertIn('tile.tap = string(options["tap"]);', RECEIVER)
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
        self.assertIn('tile.running = extra["run"].as<bool>();', RECEIVER)

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
        self.assertIn('if (d == "automation" && tile.state == "off") return "\\U000F16A7";', TILES)
        self.assertIn('robot-off', tile_icons.BIG_GLYPHS)

    def test_colours(self):
        # state_color.ts: automation has no colour variable of its own, so on is --state-active-color (amber).
        self.assertIn('d == "script" || d == "automation" || d == "remote" || d == "timer"', CONTROLS)
        self.assertIn('"script", "automation", "remote", "timer", "camera"].includes(domain)) return c.AMBER', PALETTE)
        # A run button is coloured only while its actions run, in the firmware and in the editor's preview.
        self.assertIn('if (runs()) return running;', MODEL)
        self.assertIn('if (runs && domain === "automation") return Number(value?.a?.current) > 0;', PALETTE)

    def test_run_is_home_assistants_run_actions(self):
        # more-info-automation.ts: automation.trigger with skip_condition true, which is Home Assistant's default for
        # the action and a strict bool in its schema, so the screen sends the entity alone.
        self.assertIn('if (d == "automation") return {"automation.trigger", "", ""};', CONTROLS)
        self.assertIn('hold != t.runs() ? "automation.trigger" : "automation.toggle"', CONTROLS)
        self.assertNotIn('"skip_condition"', CONTROLS)


if __name__ == '__main__':
    unittest.main()
