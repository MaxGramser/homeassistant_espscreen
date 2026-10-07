"""One way to show a finger's change before Home Assistant confirms it (docs/OPTIMISTIC.md).

The wish in optimistic.h is that way: these checks keep the doc's field table equal to the code and keep the tile's old
private hold for on and off from coming back.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPTIMISTIC = (ROOT / 'components/smart_display/optimistic.h').read_text()
TILES = (ROOT / 'components/smart_display/runtime_tiles.h').read_text()
MODEL = (ROOT / 'components/smart_display/runtime_model.h').read_text()
DOC = (ROOT / 'docs/OPTIMISTIC.md').read_text()


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
        read = TILES[TILES.index('inline std::string wish_read('):TILES.index('inline void wish_write(')]
        write = TILES[TILES.index('inline void wish_write('):TILES.index('inline void wish_show(')]
        for name in fields():
            self.assertIn(f'F::{name}', read, f'wish_read does not read {name} (docs/OPTIMISTIC.md, "Adding a field")')
            self.assertIn(f'F::{name}', write, f'wish_write does not write {name} (docs/OPTIMISTIC.md, "Adding a field")')

    def test_no_private_hold_for_on_and_off(self):
        # The tile's own optimistic toggle (firmware 0.2.59 to 0.47.0) is the wish's ON_OFF now.
        for old in ('optimistic_tap', 'undo_optimistic', 'tap_held', 'optimistic_on', 'press_key('):
            self.assertNotIn(old, TILES + MODEL, f'{old}: use wish() (docs/OPTIMISTIC.md)')

    def test_the_rules_follow_home_assistant(self):
        # ha-entity-toggle.ts: two seconds after the call returned.
        self.assertIn('constexpr uint32_t TAP_HOLD = 2000;', OPTIMISTIC)
        # A choice goes out at once; taps while it is on its way fold into one.
        self.assertNotIn('QUIET_TAP', OPTIMISTIC + TILES)
        self.assertIn('wish_run(w, esphome::millis());  // a choice goes out now, unless one is on its way', TILES)


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
            body = TILES[TILES.index(f'inline void {card}('):]
            body = body[:body.index('\n}\n')]
            self.assertIn(f'card_shaped(t,{shape});', body, f'{card} names no shape (docs/CARD_PARTS.md)')

    def test_the_pages_over_a_card_wish(self):
        # The lamp page and the effects page change a lamp or a row as a wish and keep no hold of their own.
        for page in ('group_page.h', 'effects_page.h'):
            source = (ROOT / 'components/smart_display' / page).read_text()
            self.assertIn('wish(', source)
            self.assertNotIn('SENT_HOLD_MS', source)
        self.assertIn('group_page::wish = runtime_tiles::wish_part;', (ROOT / 'packages/core.yaml').read_text())

    def test_a_change_paints_before_it_builds(self):
        refresh = TILES[TILES.index('inline void refresh_detail(unsigned index){'):]
        refresh = refresh[:refresh.index('\n}\n')]
        self.assertLess(refresh.index('card_repaint('), refresh.index('show_detail(index);'))
        self.assertIn('card_parts.clear();card_shape_of=nullptr;', TILES)


if __name__ == '__main__':
    unittest.main()
