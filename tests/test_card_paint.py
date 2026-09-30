"""A card's paint (its background, or none) repaints the card on its own (firmware 0.17.0). The colours of a card are
cached by what its state looks like; a background changed in the editor arrives as an `appearance` message without a
new state, and an idle timer never sends one, so the card kept its old colour until the entity changed."""
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from firmware_sources import runtime_source  # noqa: E402


class CardPaintTests(unittest.TestCase):
    def test_the_colour_cache_counts_the_card_paint(self):
        source = runtime_source()
        self.assertIn('uint32_t cached_paint=UINT32_MAX;', source)
        paint = re.search(r'const uint32_t paint=t\.background\|\(t\.transparent\?1u<<24:0\);\n(.*)\n(.*)\n', source)
        self.assertIsNotNone(paint)
        self.assertIn('w.cached_paint == paint', paint.group(1))
        self.assertIn('return;', paint.group(1))
        self.assertIn('w.cached_paint=paint;', paint.group(2))

    def test_the_appearance_message_repaints_through_the_card(self):
        # The message only stores the paint and asks for the card again; the cache above decides the rest.
        source = runtime_source()
        handler = source[source.index('tile.background = tile_palette::color(background);'):]
        self.assertLess(handler.index('refresh_tile(index);'), 200)


if __name__ == '__main__':
    unittest.main()
