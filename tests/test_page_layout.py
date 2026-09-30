"""Migration and document operations through the actual legacy card validator."""
from copy import deepcopy
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "screen_manager/app"))
from core import Grid, header_items, validate_layout
from page_layout import (LayoutError, compile_tiles, copy_page, delete_page, grown,
                         fingerprint, legacy_projection, pagination, sequential_target, validate_document, replace_tiles, CompiledLayouts)
from layout_migrations import migrate_legacy


class PageLayoutTests(unittest.TestCase):
    def migrate(self, value, grid=None):
        counter = itertools.count(1)
        return migrate_legacy(value, grid or Grid(), lambda: f"{next(counter):016x}")

    def test_migration_preserves_gaps_titles_options_settings_and_empty_pages(self):
        old = {
            "title": "Screen", "pages": 4, "page_titles": ["First", "", "Third", "", "Recovery title"],
            "header": {"items": [{"type": "entity", "entity": "sensor.temperature", "content": "state", "icon": "none", "show": "always"}]},
            "tiles": [
                {"entity": "light.dimmer", "name": "Light", "slot": 2,
                 "options": {"inline": "slider", "background": "yellow", "sub": "text:Brightness"}},
                {"entity": "climate.room", "name": "Climate", "slot": 6,
                 "options": {"size": "full", "controls": "none"}},
                {"entity": "screen.page_1", "name": "Return", "slot": 13},
            ], "settings": {"home_button": False, "standby_seconds": 1200},
        }
        before = deepcopy(old)
        canonical_old = validate_layout(old, grid=Grid())
        record = self.migrate(old)
        projected = legacy_projection(record)
        self.assertEqual(old, before)
        self.assertEqual(projected, canonical_old)
        self.assertEqual(len(record["layout"]["pages"]), 4)
        self.assertEqual(record["layout"]["pages"][3]["tiles"], [])
        self.assertEqual(record["migration"]["inactivePageTitles"], ["Recovery title"])
        self.assertEqual(record["layout"]["homePageId"], record["layout"]["pages"][0]["id"])

    def test_implicit_and_explicit_empty_headers_have_different_meanings(self):
        for old in ({"title": "Screen", "tiles": []},
                    {"title": "Screen", "tiles": [], "header": {"items": []}},
                    {"title": "Screen", "tiles": [], "settings": {"show_clock": False}}):
            with self.subTest(old=old):
                record = self.migrate(old)
                self.assertEqual(legacy_projection(record)["header"]["items"], header_items(old))

    def test_missing_slots_are_packed_on_the_verified_grid(self):
        grid = Grid(3, 3)
        old = {"title": "Screen", "tiles": [{"entity": f"sensor.t{i}"} for i in range(10)]}
        record = self.migrate(old, grid)
        self.assertEqual([len(p["tiles"]) for p in record["layout"]["pages"]], [9, 1])
        self.assertEqual(record["layout"]["pages"][1]["tiles"][0]["placement"], {"row": 0, "column": 0, "columns": 1, "rows": 1})
        self.assertEqual(legacy_projection(record)["tiles"], validate_layout(old, grid=grid)["tiles"])

    def test_rectangular_footprints_leave_future_sizes_capability_gated(self):
        record = self.migrate({"title": "Screen", "tiles": [
            {"entity": "media_player.test", "slot": 0, "options": {"size": "wide"}}]})
        tile = record["layout"]["pages"][0]["tiles"][0]
        self.assertEqual(tile["placement"], {"row": 0, "column": 0, "columns": 2, "rows": 1})
        tile["placement"]["rows"] = 2
        with self.assertRaisesRegex(LayoutError, "future screen capability"):
            validate_document(record["layout"], Grid())
        tile["placement"]["rows"] = 3
        with self.assertRaisesRegex(LayoutError, "future screen capability"):
            validate_document(record["layout"], Grid())
        tile["appearance"]["presentation"] = "full"
        validate_document(record["layout"], Grid())
        self.assertEqual(compile_tiles(record["layout"], Grid())[0]["options"]["size"], "full")
        tile["placement"]["column"] = 1
        with self.assertRaises(ValueError): validate_document(record["layout"], Grid())

    def test_one_column_wide_cards_keep_their_presentation_and_controls(self):
        grid = Grid(1, 4)
        old = {'title': 'Portrait', 'tiles': [
            {'entity': 'light.single', 'slot': 0},
            {'entity': 'light.wide', 'slot': 1, 'options': {'size': 'wide', 'controls': 'brightness'}},
            {'entity': 'climate.full', 'slot': 4, 'options': {'size': 'full'}},
        ]}
        record = self.migrate(old, grid)
        first, wide = record['layout']['pages'][0]['tiles']
        self.assertEqual((first['placement']['columns'], first['placement']['rows']), (1, 1))
        self.assertEqual((wide['placement']['columns'], wide['placement']['rows']), (1, 1))
        self.assertEqual(wide['appearance']['presentation'], 'wide')
        self.assertEqual(legacy_projection(record)['tiles'], validate_layout(old, grid=grid)['tiles'])

    def test_tile_events_keep_page_configuration_and_instance_identity(self):
        record = self.migrate({'title': 'Test', 'pages': 3, 'tiles': [
            {'entity': 'light.a', 'slot': 0}, {'entity': 'screen.page_3', 'slot': 6}]})
        original = record['layout']
        original['homePageId'] = original['pages'][2]['id']
        original['pages'][1]['navigation']['excludeFromPagination'] = True
        original['pages'][1]['tiles'][0]['content']['target'] = {'kind': 'home'}
        original['pages'][1]['topbar']['trailing'] = []
        flat = legacy_projection(record, require_representable=False)
        flat['tiles'][0]['slot'] = 13
        flat['tiles'].append({'entity': 'switch.new', 'name': '', 'slot': 2})
        result = replace_tiles(record, flat)
        self.assertEqual(result['homePageId'], original['homePageId'])
        self.assertEqual([p['id'] for p in result['pages']], [p['id'] for p in original['pages']])
        self.assertEqual(result['pages'][2]['tiles'][0]['id'], original['pages'][0]['tiles'][0]['id'])
        self.assertEqual(result['pages'][1], original['pages'][1])
        view = CompiledLayouts({'test': record})
        view['test']['tiles'].clear()
        self.assertEqual(len(view['test']['tiles']), 2)
        with self.assertRaises(LayoutError): view.legacy('test')
        compatible = self.migrate({'title': 'Home', 'tiles': []})
        self.assertEqual(CompiledLayouts({'test': compatible}).legacy('test'), legacy_projection(compatible))
        with self.assertRaises(TypeError): view['test'] = {}

    def test_unknown_fields_and_ambiguous_targets_are_not_dropped(self):
        for old in (
            {"title": "Screen", "tiles": [], "future": True},
            {"title": "Screen", "tiles": [{"entity": "sensor.a", "future": True}]},
            {"title": "Screen", "tiles": [{"entity": "sensor.a", "options": {"future": True}}]},
            {"title": "Screen", "tiles": [{"entity": "screen.page_5"}]},
        ):
            before = deepcopy(old)
            with self.subTest(old=old), self.assertRaises(ValueError):
                self.migrate(old)
            self.assertEqual(old, before)

    def test_every_reorder_keeps_page_targets_and_home_identity(self):
        record = self.migrate({"title": "Screen", "pages": 3, "tiles": [{"entity": "screen.page_3", "slot": 0}]})
        original = record["layout"]
        target_id = original["pages"][2]["id"]
        revision = fingerprint(original)
        for order in itertools.permutations(range(3)):
            layout = deepcopy(original)
            layout["pages"] = [layout["pages"][i] for i in order]
            validate_document(layout, Grid())
            self.assertEqual(compile_tiles(layout, Grid())[0]["entity"], f"screen.page_{order.index(2)+1}")
            source = next(p for p in layout["pages"] if p["tiles"])
            self.assertEqual(source["tiles"][0]["content"]["target"]["pageId"], target_id)
            self.assertEqual(layout["homePageId"], original["homePageId"])
            if order != (0, 1, 2):
                self.assertNotEqual(fingerprint(layout), revision)

    def test_exclusion_changes_only_the_sequential_route(self):
        record = self.migrate({"title": "Screen", "pages": 5, "tiles": [{"entity": "screen.page_5"}]})
        layout = record["layout"]
        before_tiles = compile_tiles(layout, Grid())
        for i in (1, 3):
            layout["pages"][i]["navigation"]["excludeFromPagination"] = True
        self.assertEqual(pagination(layout), [0, 2, 4])
        self.assertEqual(sequential_target(layout, 0, 1), 2)
        self.assertEqual(sequential_target(layout, 4, 1), 4)
        self.assertEqual(sequential_target(layout, 2, -1), 0)
        self.assertEqual(sequential_target(layout, 1, 1), 1)
        self.assertEqual(compile_tiles(layout, Grid()), before_tiles)
        layout["homePageId"] = layout["pages"][1]["id"]
        validate_document(layout, Grid())
        for page in layout["pages"]:
            page["navigation"]["excludeFromPagination"] = True
        self.assertEqual(pagination(layout), [])
        self.assertEqual(sequential_target(layout, 0, 1), 0)

    def test_old_firmware_refuses_new_only_choices(self):
        original = self.migrate({"title": "Screen", "pages": 2, "tiles": []})
        for feature in ("home", "exclude", "leading", "items"):
            record = deepcopy(original)
            pages = record["layout"]["pages"]
            if feature == "home": record["layout"]["homePageId"] = pages[1]["id"]
            if feature == "exclude": pages[1]["navigation"]["excludeFromPagination"] = True
            if feature == "leading": pages[1]["topbar"]["leading"] = []
            if feature == "items": pages[1]["topbar"]["trailing"] = []
            with self.subTest(feature=feature), self.assertRaises(LayoutError):
                legacy_projection(record)

    def test_duplicate_ids_across_regions_are_rejected(self):
        record = self.migrate({"title": "Screen", "pages": 2, "tiles": [{"entity": "sensor.a"}]})
        for region in ("page", "item", "control", "tile"):
            layout = deepcopy(record["layout"])
            page = layout["pages"][0]
            if region == "page": layout["pages"][1]["id"] = page["id"]
            if region == "item": page["topbar"]["trailing"][0]["id"] = page["id"]
            if region == "control": page["topbar"]["leading"][0]["id"] = page["id"]
            if region == "tile": page["tiles"][0]["id"] = page["id"]
            with self.subTest(region=region), self.assertRaises(LayoutError):
                validate_document(layout, Grid())

    def test_a_grid_that_only_grows_keeps_every_tile_where_it_was(self):
        # The 10.1-inch Guition went from 5 x 4 to 5 x 5 (firmware 0.18.0): three pages, a full tile and a tall one.
        old, new = Grid(5, 4), Grid(5, 5)
        record = self.migrate({"title": "Wall", "pages": 3, "tiles": [
            {"entity": "sensor.a", "slot": 4},
            {"entity": "light.b", "slot": 20, "options": {"size": "full"}},
            {"entity": "sensor.c", "slot": 47, "options": {"size": "tall"}},
            {"entity": "light.d", "slot": 58, "options": {"size": "wide"}}]}, old)
        layout = grown(record["layout"], old, new)
        before = [[(t["placement"]["row"], t["placement"]["column"]) for t in page["tiles"]] for page in record["layout"]["pages"]]
        after = [[(t["placement"]["row"], t["placement"]["column"]) for t in page["tiles"]] for page in layout["pages"]]
        self.assertEqual(after, before)
        self.assertEqual(len(layout["pages"]), 3)
        full = layout["pages"][1]["tiles"][0]
        self.assertEqual((full["placement"]["columns"], full["placement"]["rows"], full["appearance"]["presentation"]), (5, 5, "full"))
        self.assertEqual([t["slot"] for t in compile_tiles(layout, new)], [4, 25, 57, 68])
        validate_document(layout, new)
        # More columns too: two by three to three by four. The ids and the pages stay.
        small = self.migrate({"title": "Hall", "pages": 2, "tiles": [{"entity": "light.w", "slot": 2, "options": {"size": "wide"}},
                                                                      {"entity": "sensor.e", "slot": 7}]}, Grid(2, 3))
        wider = grown(small["layout"], Grid(2, 3), Grid(3, 4))
        self.assertEqual([t["slot"] for t in compile_tiles(wider, Grid(3, 4))], [3, 13])
        self.assertEqual([p["id"] for p in wider["pages"]], [p["id"] for p in small["layout"]["pages"]])
        # Anything that shrinks one way, or stays the same, waits for a review in the editor.
        for target in (Grid(5, 4), Grid(4, 5), Grid(6, 3)):
            self.assertIsNone(grown(record["layout"], old, target), target)

    def test_board_limits_and_footprints_are_enforced(self):
        record = self.migrate({"title": "Screen", "pages": 7, "tiles": [{"entity": "sensor.a", "slot": 62}]}, Grid(3, 3))
        validate_document(record["layout"], Grid(3, 3))
        with self.assertRaises(ValueError):
            self.migrate({"title": "Screen", "pages": 9, "tiles": []}, Grid(3, 3))
        layout = record["layout"]
        tile = layout["pages"][-1]["tiles"][0]
        tile["placement"]["columns"] = 2
        with self.assertRaises(ValueError): validate_document(layout, Grid(3, 3))
        tile["placement"] = {"row": True, "column": 0, "columns": 1, "rows": 1}
        with self.assertRaises(ValueError): validate_document(layout, Grid(3, 3))

    def test_copy_puts_the_entities_on_new_tiles(self):
        layout = self.migrate({"title": "Screen", "tiles": [{"entity": "sensor.a"}]})["layout"]
        before = deepcopy(layout)
        # One entity on several tiles (firmware 0.16.0+): the copy's tiles have ids of their own.
        full = copy_page(layout, layout["homePageId"], Grid())
        self.assertEqual(layout, before)
        self.assertEqual([tile["content"] for tile in full["pages"][1]["tiles"]], [tile["content"] for tile in layout["pages"][0]["tiles"]])
        self.assertNotEqual(full["pages"][1]["tiles"][0]["id"], layout["pages"][0]["tiles"][0]["id"])
        copied = copy_page(layout, layout["homePageId"], Grid(), empty=True)
        self.assertEqual(copied["pages"][1]["tiles"], [])
        self.assertFalse(copied["pages"][1]["navigation"]["excludeFromPagination"])
        self.assertEqual(copied["homePageId"], layout["homePageId"])
        self.assertNotEqual(copied["pages"][0]["topbar"]["trailing"][0]["id"], copied["pages"][1]["topbar"]["trailing"][0]["id"])

    def test_copy_remaps_only_self_links(self):
        layout = self.migrate({"title": "Screen", "pages": 2, "tiles": [{"entity": "screen.page_1"}, {"entity": "screen.page_2"}]})["layout"]
        copied = copy_page(layout, layout["homePageId"], Grid())
        page = copied["pages"][1]
        self.assertEqual(page["tiles"][0]["content"]["target"]["pageId"], page["id"])
        self.assertEqual(page["tiles"][1]["content"]["target"]["pageId"], layout["pages"][1]["id"])

    def test_delete_removes_incoming_links_and_reassigns_home_atomically(self):
        layout = self.migrate({"title": "Screen", "pages": 2, "tiles": [{"entity": "screen.page_1", "slot": 6}]})["layout"]
        before = deepcopy(layout)
        result = delete_page(layout, layout["homePageId"], Grid())
        self.assertEqual(layout, before)
        self.assertEqual(result["homePageId"], result["pages"][0]["id"])
        self.assertEqual(result["pages"][0]["tiles"], [])
        with self.assertRaises(LayoutError): delete_page(result, result["homePageId"], Grid())

    def test_credentials_and_runtime_fields_cannot_enter_a_document(self):
        layout = self.migrate({"title": "Screen", "tiles": []})["layout"]
        for key in ("api_key", "state", "workspace", "settings", "revision"):
            with self.subTest(key=key), self.assertRaises(LayoutError):
                validate_document({**layout, key: "synthetic"}, Grid())


if __name__ == "__main__":
    unittest.main()
