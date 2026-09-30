"""A screen without a title (firmware 0.17.0): an empty screen title leaves the top bar's home key alone. Older firmware
said "Home" for it, so the add-on asks for the firmware first, and the editor offers an empty field only from there."""
from copy import deepcopy
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "screen_manager/app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import NO_TITLE_MIN_FIRMWARE, Grid, firmware_features, min_firmware, validate_layout
from layout_migrations import migrate_legacy
from page_layout import compile_tiles, validate_document

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text()

TILES = [{"entity": "light.hall", "name": "Hall", "slot": 0}]


class NoTitleTests(unittest.TestCase):
    def test_an_empty_title_is_a_layout_that_needs_the_new_firmware(self):
        layout = validate_layout({"title": "", "tiles": deepcopy(TILES)})
        self.assertEqual(layout["title"], "")
        self.assertEqual(min_firmware(layout), NO_TITLE_MIN_FIRMWARE)
        self.assertIsNone(min_firmware(validate_layout({"title": "Hall", "tiles": deepcopy(TILES)})))
        # Spaces alone are no title either; a title still has its limit.
        self.assertEqual(validate_layout({"title": "  ", "tiles": []})["title"], "")
        with self.assertRaises(ValueError):
            validate_layout({"title": "x" * 97, "tiles": []})
        with self.assertRaises(ValueError):
            validate_layout({"title": None, "tiles": []})

    def test_the_page_document_keeps_an_empty_title(self):
        counter = itertools.count(1)
        document = migrate_legacy({"title": "", "tiles": deepcopy(TILES)}, Grid(), lambda: f"{next(counter):016x}")["layout"]
        self.assertEqual(document["title"], "")
        self.assertEqual(compile_tiles(validate_document(document, Grid()), Grid())[0]["entity"], "light.hall")
        # A stored layout from before never had an empty title: recovering one keeps the "Home" it showed.
        recovered = migrate_legacy({"title": "", "tiles": deepcopy(TILES)}, Grid(), recover=True)
        self.assertNotEqual(recovered["layout"]["title"], "")
        self.assertIn("title", recovered["migration"]["adjustedFields"])

    def test_the_editor_offers_it_from_the_firmware_that_draws_it(self):
        self.assertTrue(firmware_features(NO_TITLE_MIN_FIRMWARE)["no_title"])
        self.assertFalse(firmware_features((0, 16, 0))["no_title"])
        self.assertFalse(firmware_features(None)["no_title"])

    def test_the_screen_keeps_an_empty_title_empty(self):
        receiver, model = source("components/smart_display/page_receiver.cpp"), source("components/smart_display/runtime_model.h")
        self.assertIn("model.title = title;", receiver)
        self.assertNotIn("status_home", receiver)
        self.assertIn("title = name;", model)


if __name__ == "__main__":
    unittest.main()
