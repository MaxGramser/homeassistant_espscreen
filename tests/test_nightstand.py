"""The bedside clock (app 0.4.12, firmware 0.8.0): a clock over the whole page with up to three keys. A key is a tile
like any other that has no cell of its own: the page document keeps it as a child of its clock, and everywhere after
that (the compiled tiles, the watched entities, the layout sensor, the delivery) it is a tile that names the tile it
stands under (`in`) and its place there (`key`)."""
import asyncio
from copy import deepcopy
import importlib.util
import itertools
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "screen_manager/app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import (NIGHTSTAND, NIGHTSTAND_MIN_FIRMWARE, Grid, layout_snapshot, min_firmware, run_tile_event, screen_options,
                  state_message, validate_layout)
from layout_migrations import migrate_legacy
from page_layout import LayoutError, compile_tiles, copy_page, legacy_projection, replace_tiles, validate_document
import page_delivery

CLOCK = {"entity": NIGHTSTAND, "name": "", "slot": 0, "options": {"size": "full", "background": "none"}}
KEYS = [{"entity": "light.bedside", "name": "Lamp", "in": NIGHTSTAND, "key": 0},
        {"entity": "sensor.bedroom_temperature", "name": "Bedroom", "in": NIGHTSTAND, "key": 1, "options": {"tap": "none"}},
        {"entity": "lock.front_door", "name": "Front door", "in": NIGHTSTAND, "key": 2, "options": {"guard": "lock_only"}}]


def record(tiles, grid=None):
    counter = itertools.count(1)
    return migrate_legacy({"title": "Bedroom", "tiles": deepcopy(tiles)}, grid or Grid(), lambda: f"{next(counter):016x}")


class NightstandTests(unittest.TestCase):
    def test_keys_are_children_in_the_document_and_tiles_everywhere_after(self):
        document = record([CLOCK, *KEYS])["layout"]
        clock = document["pages"][0]["tiles"][0]
        self.assertEqual([child["content"]["entityId"] for child in clock["children"]],
                         ["light.bedside", "sensor.bedroom_temperature", "lock.front_door"])
        self.assertEqual(clock["children"][2]["interaction"], {"guard": "lock_only"})
        flat = compile_tiles(validate_document(document, Grid()), Grid())
        self.assertEqual(flat[1:], KEYS)
        self.assertEqual(flat[0]["options"], {"size": "full", "background": "none"})

    def test_keys_follow_the_placed_tiles_whatever_order_they_come_in(self):
        tiles = [KEYS[1], {"entity": "sensor.outside", "name": "Outside", "slot": 6}, KEYS[0], CLOCK]
        layout = validate_layout({"title": "B", "tiles": deepcopy(tiles)})
        self.assertEqual([t["entity"] for t in layout["tiles"]], [NIGHTSTAND, "sensor.outside", "light.bedside", "sensor.bedroom_temperature"])

    def test_the_clock_is_always_the_whole_page_and_takes_no_face_options(self):
        layout = validate_layout({"title": "B", "tiles": [{"entity": NIGHTSTAND, "slot": 0, "options": {"display": "flip", "inline": "slider"}}]})
        self.assertEqual(layout["tiles"][0]["options"], {"size": "full"})

    def test_a_key_stands_under_a_clock_on_a_place_of_its_own(self):
        for key in ({**KEYS[0], "in": "sensor.outside"},          # not a tile that holds keys
                    {**KEYS[0], "key": 3},                          # beyond the three places
                    {**KEYS[0], "slot": 6},                         # a key has no cell
                    {**KEYS[0], "entity": "camera.door"},           # a picture has no round form
                    {**KEYS[0], "options": {"size": "wide"}}):      # a key has no size of its own
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_layout({"title": "B", "tiles": [CLOCK, {"entity": "sensor.outside", "slot": 6}, key]})
        with self.assertRaises(ValueError):
            validate_layout({"title": "B", "tiles": [CLOCK, KEYS[0], {**KEYS[1], "key": 0}]})

    def test_an_entity_may_be_a_key_and_a_tile_but_the_clock_is_once_on_a_screen(self):
        # Any entity on several tiles, a key being one, from firmware 0.16.0 (GitHub #83).
        both = validate_layout({"title": "B", "tiles": [CLOCK, KEYS[0], {"entity": "light.bedside", "slot": 6}]})
        self.assertEqual(min_firmware(both), (0, 16, 0))
        with self.assertRaisesRegex(ValueError, "bedside clock can only be on a screen once"):
            validate_layout({"title": "B", "tiles": [CLOCK, {**CLOCK, "slot": 6}]})

    def test_a_key_is_checked_like_a_tile_of_its_own(self):
        with self.assertRaises(ValueError):
            validate_layout({"title": "B", "tiles": [CLOCK, {**KEYS[0], "options": {"guard": "lock_only"}}]})
        with self.assertRaises(ValueError):
            validate_layout({"title": "B", "tiles": [CLOCK, {**KEYS[0], "options": {"tap": "action"}}]})
        layout = validate_layout({"title": "B", "tiles": [CLOCK, {**KEYS[2], "options": {"guard": "confirm"}}]})
        self.assertEqual(layout["tiles"][1].get("options", {}), {})

    def test_only_a_clock_holds_children(self):
        document = record([CLOCK, *KEYS])["layout"]
        document["pages"][0]["tiles"][0]["content"] = {"kind": "builtin", "name": "clock"}
        with self.assertRaises(LayoutError):
            validate_document(document, Grid())

    def test_the_screen_gets_a_key_as_a_tile_naming_its_clock(self):
        flat = compile_tiles(record([CLOCK, {"entity": "sensor.outside", "name": "Outside", "slot": 6}, *KEYS])["layout"], Grid())
        self.assertEqual([t["entity"] for t in flat], [NIGHTSTAND, "sensor.outside", "light.bedside", "sensor.bedroom_temperature", "lock.front_door"])
        holders = {t["entity"]: i for i, t in enumerate(flat) if "in" not in t}
        states = {"light.bedside": {"state": "on", "attributes": {"friendly_name": "Bedside lamp", "brightness": 51}}}
        message = page_delivery.tile_message(state_message(2, flat[2], states), flat[2], initial=True, holders=holders)
        self.assertEqual((message["op"], message["in"], message["k"]), ("tile", 0, 0))
        self.assertNotIn("slot", message)
        self.assertEqual(screen_options(flat[4], {}), {"guard": "lock_only"})

    def test_the_clock_needs_its_firmware_and_so_does_a_lock_among_its_keys(self):
        self.assertEqual(min_firmware(legacy_projection(record([CLOCK]), require_representable=False)), NIGHTSTAND_MIN_FIRMWARE)
        self.assertGreaterEqual(min_firmware({"tiles": [CLOCK, *KEYS]}), NIGHTSTAND_MIN_FIRMWARE)
        with self.assertRaises(LayoutError):
            legacy_projection(record([CLOCK, *KEYS]))

    def test_tile_events_keep_the_keys_and_can_remove_one(self):
        rec = record([CLOCK, *KEYS]); rec["revision"] = "r"
        flat = legacy_projection(rec, require_representable=False)
        moved, _ = run_tile_event(flat, "add", {"entity": "sensor.outside", "page": 2})
        document = replace_tiles(rec, moved)
        self.assertEqual([c["id"] for c in document["pages"][0]["tiles"][0]["children"]],
                         [c["id"] for c in rec["layout"]["pages"][0]["tiles"][0]["children"]])
        removed, key = run_tile_event(flat, "remove", {"entity": "light.bedside"})
        self.assertEqual(key["entity"], "light.bedside")
        self.assertEqual([t["entity"] for t in removed["tiles"] if "in" in t], ["sensor.bedroom_temperature", "lock.front_door"])
        with self.assertRaises(ValueError):
            run_tile_event(flat, "move", {"entity": "light.bedside", "page": 2})
        gone, _ = run_tile_event(flat, "remove", {"entity": NIGHTSTAND})
        self.assertEqual(gone["tiles"], [])

    def test_the_layout_sensor_names_a_key_under_its_clock(self):
        snapshot = layout_snapshot({"name": "Bedroom"}, legacy_projection(record([CLOCK, *KEYS]), require_representable=False), Grid())
        self.assertEqual(snapshot["tiles"][1], {"entity": "light.bedside", "name": "Lamp", "page": 1, "under": NIGHTSTAND, "key": 1, "tap": "auto"})

    def test_a_page_with_keys_is_not_copied_onto_the_same_screen(self):
        document = record([CLOCK, *KEYS])["layout"]
        with self.assertRaises(ValueError):  # the copy would put the bedside clock on the screen twice
            copy_page(document, document["pages"][0]["id"], Grid())

    def test_a_screen_that_does_not_take_keys_is_refused_before_anything_is_sent(self):
        rec = record([CLOCK, *KEYS]); rec["revision"] = "r1"
        tiles = compile_tiles(rec["layout"], Grid())
        values = [state_message(i, tile, {}) for i, tile in enumerate(tiles)]
        sent = []

        async def send(message):
            sent.append(message["op"])
            if message["op"] == "hello":
                return {"protocol": 2, "request": message["request"], "session": "a" * 16, "status": "Session:" + "a" * 16}
            return {"protocol": 2, "session": "a" * 16, "seq": message.get("seq"), "rev": message.get("rev"), "status": "Synced"}
        with self.assertRaises(page_delivery.Refused):
            asyncio.run(page_delivery.Sender(send).synchronize("inbox", rec, {}, values, [[]]))
        self.assertEqual(sent, ["hello"])


@unittest.skipUnless(importlib.util.find_spec("aiohttp"), "needs aiohttp")
class ManagerSeesKeys(unittest.TestCase):
    """What the add-on does with a key is what it does with a tile: it follows the entity's state."""

    def test_a_key_is_watched_and_known_like_a_tile(self):
        from manager_fixtures import seed_layout, with_screen_grid
        from test_ha_capabilities import fake_ha
        from server import Manager
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(with_screen_grid(fake_ha()), Path(tmp) / "screens.json")
            m.firmware_version = lambda inbox, screen=None: (0, 8, 0)
            seed_layout(m, "text.d1_tiles", {"title": "Bedroom", "tiles": [CLOCK,
                        {"entity": "light.hood", "name": "Lamp", "in": NIGHTSTAND, "key": 0},
                        {"entity": "climate.airco", "name": "Airco", "in": NIGHTSTAND, "key": 1}]})
            watched = m.watched_entities()
            self.assertIn("light.hood", watched)
            self.assertIn("climate.airco", watched)


if __name__ == "__main__":
    unittest.main()
