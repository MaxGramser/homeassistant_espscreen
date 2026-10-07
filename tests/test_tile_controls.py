"""Direct controls on wide cards: editor choices, validation and what goes on the wire."""
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
from core import CONTROLS, controls_catalogue, min_firmware, packets, resolve_controls, screen_options, state_message, validate_layout
import tile_icons
import test_portal

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None


class ControlChoices(unittest.TestCase):
    def test_catalogue_offers_each_domain_its_sets_plus_none(self):
        catalogue = controls_catalogue()
        self.assertEqual(catalogue['media_player']['default'], 'volume')
        self.assertEqual([c['key'] for c in catalogue['media_player']['choices']], ['volume', 'playback', 'none'])
        self.assertEqual([c['key'] for c in catalogue['climate']['choices']], ['setpoint', 'mode', 'setpoint_mode', 'none'])
        for domain in ('climate', 'switch', 'vacuum', 'cover', 'media_player'):
            self.assertIn(domain, catalogue)
        self.assertNotIn('sensor', catalogue)

    def test_validation_accepts_own_sets_and_rejects_others(self):
        layout = validate_layout({'title': 'T', 'tiles': [{'entity': 'cover.curtain', 'options': {'size': 'wide', 'controls': 'position'}}]})
        self.assertEqual(layout['tiles'][0]['options']['controls'], 'position')
        validate_layout({'title': 'T', 'tiles': [{'entity': 'light.a', 'options': {'controls': 'none'}}]})
        for entity, choice in (('cover.a', 'volume'), ('sensor.a', 'toggle'), ('switch.a', 'brightness'), ('climate.a', 42), ('light.a', 'run')):
            with self.assertRaises(ValueError):
                validate_layout({'title': 'T', 'tiles': [{'entity': entity, 'options': {'size': 'wide', 'controls': choice}}]})

    def test_cover_tilt_choices_roundtrip_without_a_new_schema(self):
        import page_layout
        from layout_migrations import migrate_legacy
        for choice in ('tilt', 'buttons_tilt', 'position_tilt'):
            old = validate_layout({'title': 'Covers', 'tiles': [
                {'entity': 'cover.test', 'options': {'size': 'full', 'controls': choice}}]})
            record = migrate_legacy(old, page_layout.Grid())
            document = page_layout.validate_document(record['layout'], page_layout.Grid())
            tiles = page_layout.compile_tiles(document, page_layout.Grid())
            self.assertEqual(tiles[0]['options']['controls'], choice)
            self.assertEqual(resolve_controls(tiles[0]), choice)
            self.assertEqual(min_firmware(old), (0, 3, 1))
            self.assertFalse(page_layout.legacy_compatible(document, page_layout.Grid()))
            with self.assertRaises(page_layout.LayoutError):
                page_layout.legacy_projection(record)

    def test_wide_cards_get_the_default_set_only_in_the_standard_layout(self):
        self.assertEqual(resolve_controls({'entity': 'climate.a', 'options': {'size': 'wide'}}), 'setpoint')
        self.assertEqual(resolve_controls({'entity': 'media_player.a', 'options': {'size': 'wide', 'controls': 'playback'}}), 'playback')
        self.assertIsNone(resolve_controls({'entity': 'media_player.a', 'options': {'size': 'wide', 'controls': 'none'}}))
        self.assertIsNone(resolve_controls({'entity': 'climate.a'}), 'single cards stay as they are')
        self.assertIsNone(resolve_controls({'entity': 'climate.a', 'options': {'size': 'wide', 'display': 'watch'}}))
        self.assertIsNone(resolve_controls({'entity': 'light.a', 'options': {'size': 'wide', 'inline': 'slider'}}))
        self.assertIsNone(resolve_controls({'entity': 'sensor.a', 'options': {'size': 'wide'}}))

    def test_wire_carries_only_the_shown_set_and_the_attributes_the_panels_need(self):
        states = {'media_player.sonos': {'state': 'playing', 'attributes': {'volume_level': 0.17, 'is_volume_muted': False, 'media_title': 'TV', 'supported_features': 8321599, 'assumed_state': True}},
                  'cover.curtain': {'state': 'open', 'attributes': {'current_position': 80, 'device_class': 'curtain', 'supported_features': 15}},
                  'climate.ac': {'state': 'cool', 'attributes': {'hvac_action': 'cooling', 'hvac_modes': ['off', 'cool', 'heat'], 'temperature': 20, 'target_temp_step': 1.0}}}
        msg = state_message(0, {'entity': 'media_player.sonos', 'name': '', 'options': {'size': 'wide'}}, states)
        self.assertEqual(msg['o'], {'size': 'wide', 'controls': 'volume'})
        self.assertIs(msg['a']['is_volume_muted'], False)
        self.assertIs(msg['a']['assumed_state'], True, "a player's power keys follow it, as in Home Assistant's dialog")
        msg = state_message(1, {'entity': 'cover.curtain', 'name': '', 'options': {'size': 'wide', 'controls': 'none', 'background': 'blue'}}, states)
        self.assertEqual(msg['o'], {'size': 'wide', 'background': 'blue'}, 'an explicit none is not sent; the stored choice stays')
        self.assertEqual(msg['a']['device_class'], 'curtain')
        msg = state_message(2, {'entity': 'climate.ac', 'name': '', 'options': {'size': 'wide', 'controls': 'mode'}}, states)
        self.assertEqual(msg['o'], {'size': 'wide', 'controls': 'mode'})
        self.assertEqual(msg['a']['hvac_action'], 'cooling')
        self.assertTrue(all(len(p) <= 255 for p in packets(msg)))
        msg = state_message(3, {'entity': 'climate.ac', 'name': '', 'options': {'controls': 'mode'}}, states)
        self.assertEqual(msg['o'], {}, 'a single card never shows a panel')
        self.assertIsNone(min_firmware({'tiles': [{'entity': 'climate.ac', 'options': {'size': 'wide', 'controls': 'mode'}}]}), 'older firmware ignores the field')

    def test_screen_options_keeps_the_choice_out_of_the_wire_but_in_storage(self):
        tile = {'entity': 'switch.desk', 'name': '', 'options': {'size': 'wide', 'controls': 'toggle', 'icon': 'auto'}}
        self.assertEqual(screen_options(tile, {}), {'size': 'wide', 'controls': 'toggle'})
        self.assertEqual(validate_layout({'title': 'T', 'tiles': [tile]})['tiles'][0]['options'], tile['options'])

    def test_control_glyphs_exist_in_the_icon_fonts_and_the_editor_font(self):
        header = (ROOT / 'components/smart_display/tile_controls.h').read_text()
        used = {code.upper() for code in re.findall(r'\\U000(F[0-9A-F]{4})', header)}
        carried = {code for code in tile_icons.GLYPHS.values()}
        self.assertTrue(used <= carried, used - carried)
        self.assertTrue(set(tile_icons.CONTROL_GLYPHS) <= set(tile_icons.GLYPHS))
        self.assertEqual(set(tile_icons.editor()['controls']), set(tile_icons.CONTROL_GLYPHS))
        for name in ('checkout/guition.yaml', 'checkout/cyd.yaml', 'packages/guition.yaml', 'packages/cyd.yaml'):
            text = profiles.text(name)
            for code in used:
                self.assertIn(f'"\\U000{code}"', text, (name, code))
            self.assertIn('runtime_tiles::control_font = id(sublabel_big)->get_lv_font();', text, name)


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class ControlInventory(unittest.IsolatedAsyncioTestCase):
    async def test_inventory_lists_the_catalogue_and_a_saved_choice_survives_an_old_editor(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = test_portal.ManagerTests().setup_manager(Path(tmp) / 'screens.json')
            self.assertEqual(m.inventory()[0][0]['id'], 'text.screen')
            m.save('text.screen', {'title': 'Home', 'tiles': [{'entity': 'light.a', 'options': {'size': 'wide', 'controls': 'brightness'}}]})
            m.save('text.screen', {'title': 'Home', 'tiles': [{'entity': 'light.a', 'options': {'size': 'wide'}}]})
            self.assertEqual(m.layouts['text.screen']['tiles'][0]['options'], {'size': 'wide', 'controls': 'brightness'})
            await m.sync_one('text.screen', m.layouts['text.screen'])
            self.assertEqual(m.ha.messages[1][1]['o'], {'size': 'wide', 'controls': 'brightness'})
            from aiohttp.test_utils import TestClient, TestServer
            from server import create_app
            async with TestClient(TestServer(create_app(m, development=True))) as client:
                data = await (await client.get('/api/inventory')).json()
                self.assertEqual(data['controls']['cover']['default'], 'buttons')
                self.assertIn('controls', data['icons'])
                light = await (await client.get('/api/inventory?light=1')).json()
                self.assertNotIn('controls', light)
