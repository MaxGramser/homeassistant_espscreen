"""Regression checks for the page geometry (the board's grid) and the event guards."""
from firmware_sources import runtime_source
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
SOURCE = profiles.resolved('checkout/cyd.yaml')
VALUES = dict(re.findall(r'^  (\w+): "([^"]*)"', SOURCE, re.M))

class LayoutTests(unittest.TestCase):
    def test_a_board_states_a_page_that_fits_its_glass_either_way_up(self):
        """A board states its panel, the angle that lays it down, its two grids, its margin and its gaps; the firmware
        divides the canvas LVGL gives it over the cells (firmware 0.2.92+). The sizes of the cells are no longer in the
        file, so what is left to check is that the board's own numbers agree with each other: the panel really is
        landscape at the angle it names, and a page of either grid leaves room for every cell it asks for."""
        for name in profiles.PROFILES:
            values = profiles.substitutions(name)
            v = lambda k: int(values[k])
            self.assertIn(v('ROTATION_LANDSCAPE'), (0, 90, 180, 270), name)
            # The only line that differs between a screen built lying down and the same screen standing up, and in
            # the board file it is the board's own angle: a file on its own builds a screen that lies down.
            self.assertEqual(values['LVGL_ROTATION'], values['ROTATION_LANDSCAPE'],
                             f'{name}: the board file itself must lie down')
            panel = (v('PANEL_W'), v('PANEL_H'))
            wide = panel[::-1] if v('ROTATION_LANDSCAPE') in (90, 270) else panel
            self.assertGreaterEqual(wide[0], wide[1], f'{name}: at ROTATION_LANDSCAPE the canvas must be landscape')
            grids = {'lying down': ((v('GRID_COLS'), v('GRID_ROWS')), wide),
                     'standing up': ((v('GRID_COLS_PORTRAIT'), v('GRID_ROWS_PORTRAIT')), wide[::-1])}
            for way, ((cols, rows), (width, height)) in grids.items():
                where = f'{name} {way}'
                self.assertGreaterEqual(cols, 1, where)
                self.assertGreaterEqual(rows, 1, where)
                # The firmware holds 64 tiles in all, so a page of more cells than that could never be filled.
                self.assertLessEqual(cols * rows, 64, where)
                band = height - v('SCROLL_Y') - v('PAGE_BAR_H')
                self.assertGreater(band, 0, f'{where}: top bar and page bar leave no room for tiles')
                self.assertGreater(width - 2 * v('GRID_MARGIN') - (cols - 1) * v('GRID_GAP_X'), 0,
                                   f'{where}: the margin and the gaps leave no width for the cells')
                self.assertGreater(band - (rows - 1) * v('GRID_GAP_Y'), 0,
                                   f'{where}: the gaps leave no height for the cells')
            # Square glass hangs one way only, so its two grids are the same page.
            if wide[0] == wide[1]:
                self.assertEqual(grids['lying down'][0], grids['standing up'][0], f'{name}: square glass, one grid')

    def test_a_look_names_a_size_only_after_stating_it(self):
        """ESPHome works a file's substitutions out in their order, so a size made of another size of the same look
        must come after it: SCROLL_Y ahead of GRID_MARGIN built a bedside clock a page too large (found building firmware 0.14.0)."""
        for look in sorted((ROOT / 'packages' / 'looks').glob('*.yaml')):
            stated = []
            for name, value in re.findall(r'^  (\w+): (.*)$', look.read_text(), re.M):
                later = set(re.findall(r'\b[A-Z][A-Z0-9_]+\b', value)) & set(re.findall(r'^  (\w+):', look.read_text(), re.M))
                self.assertFalse(later - set(stated) - {name}, f'{look.name}: {name} names {sorted(later - set(stated))} before they are stated')
                stated.append(name)

    def test_the_top_bar_and_the_page_keys_keep_the_tiles_margin(self):
        """One margin all round (firmware 0.14.0+): the top bar from the sides and the top, the tiles, and the ink of
        the page keys' chevrons all keep GRID_MARGIN."""
        for look in ('standard', 'compact'):
            text = (ROOT / 'packages' / 'looks' / f'{look}.yaml').read_text()
            self.assertIn('HEADER_INSET: ${GRID_MARGIN}', text, look)
            self.assertNotIn('PAGE_CHEVRON_INSET', text, look)
        self.assertIn('nav_align(previous,true);nav_align(next,false);', runtime_source())

    def test_a_board_brings_a_card_for_every_cell_of_both_its_grids(self):
        """One file of cards per board (packages/cells/<number>.yaml), and a screen is built lying down or standing up
        from that one file: it has to hold the cells of whichever page asks for most."""
        for board, path in sorted(profiles.BOARDS.items()):
            values = profiles.board_values(board)
            v = lambda k: int(values[k])
            wanted = max(v('GRID_COLS') * v('GRID_ROWS'), v('GRID_COLS_PORTRAIT') * v('GRID_ROWS_PORTRAIT'))
            cells = profiles.cells_of(path)
            self.assertEqual(len(cells), 1, board)
            self.assertGreaterEqual(int(cells[0].stem), wanted, f'{board}: {cells[0].name} is short of cards')

    def test_the_cards_are_cells_of_an_lvgl_grid(self):
        """No card carries a coordinate: the container is a grid and place_page only names a cell and its span."""
        self.assertIn('type: GRID', SOURCE)
        self.assertNotRegex(SOURCE, r'id: tile\d+\n\s+x: ')
        self.assertEqual(SOURCE.count('grid_cell_row_pos: 0'), int(VALUES['GRID_COLS']) * int(VALUES['GRID_ROWS']))
        runtime = runtime_source()
        self.assertIn('lv_obj_set_grid_dsc_array(container, grid_columns_dsc.data(), grid_rows_dsc.data());', runtime)
        # A card's cell goes through set_cell, which sets it only when it changes (firmware 0.3.2+, kept pages).
        self.assertIn('set_cell(w.tile,column,span_x,row,span_y);', runtime)
        self.assertIn('lv_obj_set_grid_cell(obj, LV_GRID_ALIGN_STRETCH, column, span_x, LV_GRID_ALIGN_STRETCH, row, span_y);', runtime)

    def test_runtime_binds_every_tile_and_guards_a_tap(self):
        """The tiles are bound by the runtime; it filters a tap before anything happens."""
        cells = int(VALUES['GRID_COLS']) * int(VALUES['GRID_ROWS'])
        for n in range(1, cells + 1):
            self.assertIn(f'runtime_tiles::bind({n - 1}, id(tile{n})', SOURCE)
        self.assertNotIn(f'runtime_tiles::bind({cells}, ', SOURCE)
        runtime = runtime_source()
        # A tap that switches is a wish and takes every clean tap (docs/OPTIMISTIC.md); any other keeps the 600 ms guard.
        self.assertIn('if (!(switches ? allowed_wish(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), tile.entity)', runtime)
        self.assertIn(': allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), tile.entity))) return;', runtime)

    def test_navigation_is_above_grid_but_below_modal_overlays(self):
        grid = SOURCE.index('            id: tile_scroll')
        nav = SOURCE.index('            id: page_prev')
        modal = SOURCE.index('            id: color_detail_overlay')
        self.assertLess(grid, nav)
        self.assertLess(nav, modal)

    def test_page_key_press_shows_around_the_chevron(self):
        from firmware_sources import runtime_source
        RUNTIME_TILES = runtime_source()
        self.assertIn('if(!nav_prev){nav_key_patch(previous);nav_key_patch(next);}', RUNTIME_TILES)
        self.assertIn('theme::style(theme::Paint::page_pressed)', RUNTIME_TILES)
        self.assertIn('inline lv_area_t ink_area(lv_obj_t *o)', RUNTIME_TILES)

    def test_page_keys_are_the_halves_of_the_band_under_the_tiles(self):
        """Firmware 0.2.69+: a chevron in each half of the band, the dots between them take no touches. The half is
        half of the glass, said as a percentage, so it is still half after the screen is built standing up."""
        for name in profiles.PROFILES:
            source = profiles.resolved(name)
            values = profiles.substitutions(name)
            band = int(values['PAGE_BAR_H'])
            for key, glyph in (('page_prev', 'F0141'), ('page_next', 'F0142')):
                block = source.split(f'            id: {key}\n', 1)[1].split('\n        - ', 1)[0]
                self.assertIn('width: 50%\n', block, f'{name} {key}')
                self.assertIn(f'height: {band}\n', block, f'{name} {key}')
                # Firmware 0.3.1: the half takes the touch but stays clear; the press shows around the chevron only.
                self.assertIn('pressed:\n              bg_opa: TRANSP', block, f'{name} {key}: the half stays clear under a finger')
                self.assertIn(f'\\U000{glyph}', block, f'{name} {key}')
                self.assertIn('text_font: materialdesign_icons_mini', block, f'{name} {key}')
                self.assertNotIn('Previous', block)
                self.assertNotIn('Next  >', block)
            number = source.split('            id: page_number\n', 1)[1].split('\n        - ', 1)[0]
            self.assertIn('clickable: false', number, name)
            self.assertIn(f'height: {band}\n', number, name)
        runtime = runtime_source()
        self.assertIn('settings_screen::page_dots(nav_number,model.page_data.ordinal(page),sequential_count,', runtime)
        self.assertIn('set_hidden(control,!sequential)', runtime)

    def test_nothing_is_placed_before_a_layout_arrives(self):
        """Until ESP Screens sends a layout the cells stay empty; place_page hides every slot the page has no card for."""
        block = SOURCE.split('  - id: show_tile_page\n', 1)[1].split('  - id: apply_screen_settings', 1)[0]
        self.assertIn('lv_obj_add_flag(w.tile, LV_OBJ_FLAG_HIDDEN)', block)
        self.assertIn('id(page_prev), id(page_next), id(page_number)', block)
        runtime = runtime_source()
        self.assertIn('else{lv_obj_add_flag(w.tile,LV_OBJ_FLAG_HIDDEN);hide_extra(w);hide_panel(w);}', runtime)

    def test_self_test_cannot_call_a_home_assistant_action(self):
        block = SOURCE.split('  - id: ui_self_test\n', 1)[1].split('  - id: show_tile_page', 1)[0]
        self.assertNotIn('homeassistant.action:', block)
        self.assertNotIn('do_tile_action', block)
        self.assertNotIn('climate_target_commit', block)

if __name__ == '__main__':
    unittest.main()
