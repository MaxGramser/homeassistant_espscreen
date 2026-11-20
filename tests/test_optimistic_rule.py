"""One way to show a finger's change before Home Assistant confirms it (docs/OPTIMISTIC.md).

The wish in optimistic.h is that way: these checks keep the doc's field table equal to the code and keep the tile's old
private hold for on and off from coming back. The wish's behaviour is proven in tests/test_optimistic.cpp (a tap goes out
at once, a burst folds into one, TAP_HOLD is Home Assistant's two seconds as a static_assert), and a card painted in
place against the same card built anew in web/wasm/test_card_parts.mjs.
"""
from firmware_sources import runtime_source
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPTIMISTIC = (ROOT / 'components/smart_display/optimistic.h').read_text()
TILES = runtime_source()
MODEL = (ROOT / 'components/smart_display/runtime_model.h').read_text()
DOC = (ROOT / 'docs/OPTIMISTIC.md').read_text()


def function(source, head):
    """The body of the function that starts with `head`, up to its closing brace at the start of a line."""
    body = source[source.index(head):]
    return body[:body.index('\n}\n')]


def fields():
    body = OPTIMISTIC[OPTIMISTIC.index('enum class Field'):]
    body = body[:body.index('};')]
    return re.findall(r'^\s+([A-Z_]+),', body, re.M)


class OneWish(unittest.TestCase):
    def test_every_field_is_in_the_doc(self):
        names = fields()
        self.assertGreater(len(names), 5)
        table = re.findall(r'^\| `([A-Z_]+)` \|', DOC, re.M)
        self.assertEqual(sorted(names), sorted(table), 'docs/OPTIMISTIC.md: the field table differs from optimistic::Field')

    def test_every_field_is_read_and_written(self):
        # Rule: a field the wish knows is one the tile can show and take back (docs/OPTIMISTIC.md, "Adding a field").
        read, write = function(TILES, 'inline std::string wish_read('), function(TILES, 'inline void wish_write(')
        for name in fields():
            self.assertIn(f'F::{name}', read, f'wish_read does not read {name} (docs/OPTIMISTIC.md, "Adding a field")')
            self.assertIn(f'F::{name}', write, f'wish_write does not write {name} (docs/OPTIMISTIC.md, "Adding a field")')

    def test_no_private_hold_for_on_and_off(self):
        # The tile's own optimistic toggle (firmware 0.2.59 to 0.47.0) is the wish's ON_OFF now.
        for old in ('optimistic_tap', 'undo_optimistic', 'tap_held', 'optimistic_on', 'press_key('):
            self.assertNotIn(old, TILES + MODEL, f'{old}: use wish() (docs/OPTIMISTIC.md)')

    def test_no_quiet_tap(self):
        # Rule: a choice goes out at once and taps on its way fold into one (tests/test_optimistic.cpp); no quiet time
        # before a tap goes out comes back.
        self.assertNotIn('QUIET_TAP', OPTIMISTIC + TILES, 'a tap waits for nothing: docs/OPTIMISTIC.md')


class CardParts(unittest.TestCase):
    """docs/CARD_PARTS.md: a card that paints itself binds its parts and names its shape."""

    def test_every_card_names_its_shape(self):
        # A card that names no shape is built again on every change of its tile (docs/CARD_PARTS.md).
        shapes = {'render_climate_detail': 'climate_card_shape', 'render_media_detail': 'media_card_shape',
                  'render_light_detail': 'light_card_shape', 'render_cover_detail': 'cover_card_shape',
                  'render_select_detail': 'select_card_shape', 'render_remote_detail': 'select_card_shape', 'render_vacuum_detail': 'vacuum_card_shape',
                  'render_lock_detail': 'security_card_shape', 'render_alarm_detail': 'security_card_shape',
                  'render_weather_detail': 'picture_card_shape', 'render_history_detail': 'picture_card_shape'}
        for card in re.findall(r'^inline void (render_[a-z]+_detail)\(', TILES, re.M):
            self.assertIn(card, shapes, f'{card} is a card without a shape (docs/CARD_PARTS.md)')
        for card, shape in shapes.items():
            body = function(TILES, f'inline void {card}(')
            self.assertIn(f'card_shaped(t,{shape});', body, f'{card} names no shape (docs/CARD_PARTS.md)')

    def test_the_pages_over_a_card_wish(self):
        # The lamp page and the effects page change a lamp or a row as a wish and keep no hold of their own.
        for page in ('group_page.h', 'effects_page.h'):
            source = (ROOT / 'components/smart_display' / page).read_text()
            self.assertIn('wish(', source, f'{page} changes a lamp or a row as a wish')
            self.assertNotIn('SENT_HOLD_MS', source, f'{page} keeps no hold of its own')
        # Rule: bound in C++ since app 0.4.86 (runtime_tiles::bind_pages), which the core and the browser preview both call.
        self.assertIn('group_page::wish = wish_part;', TILES, 'the lamp page wishes through the runtime')
        self.assertIn('effects_page::wish = wish_part;', TILES, 'and so does the effects page')
        self.assertIn('runtime_tiles::bind_pages();', (ROOT / 'packages/core.yaml').read_text(), 'core.yaml binds the pages at boot')


if __name__ == '__main__':
    unittest.main()
