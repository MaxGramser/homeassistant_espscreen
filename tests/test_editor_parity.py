"""The editor's mockup measures what the screen draws with the firmware's own numbers, ported by hand.

The editor (web/) draws an HTML picture of a screen, and the sizes in it are the firmware's, written a second time in
TypeScript: ui::px and the look (ui_scale.h) in web/src/model/ui-scale.ts, the -/+ pill and the thermostat's mode bar
(runtime_tiles panel_metrics, stepper_keys, climate_tile::bar_room) there too, the top bar (header_bar.h and the look's
fonts) in topbar.ts, a tile's size (page_protocol.h, core.py) in sizes.ts, a card's colour (Tile::active,
tile_controls::accent) in tile-palette.ts and a thermostat's modes (tile_controls::climate_bar_keys) in tall-controls.ts.
The editor does not read these numbers from the firmware; this test keeps the two the same, the way
tests/test_alert_layout.py does for the alert: it compiles the C++ (the real headers, and the few lines of
runtime_tiles.h that hold the panel's sizes, cut out of it as they stand), runs the real TypeScript through vite-node,
and compares every number on every board's glass, lying down and standing up. Where the firmware decides with LVGL's
own grid (a card's width, the height of a cell), the WebAssembly build of runtime_tiles.h answers (web/wasm).

The firmware is the truth: a difference is fixed in the TypeScript.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import core  # noqa: E402
import profiles  # noqa: E402

WEB = ROOT / 'web'
VITE_NODE = WEB / 'node_modules/.bin/vite-node'
WASM = WEB / 'src/wasm/firmware_preview.wasm'
TILES = (ROOT / 'components/smart_display/runtime_tiles.h').read_text()


def need(found, what):
    """A tool the test needs: skipped without it on a laptop, a failure in CI, where a skip would prove nothing."""
    if found:
        return found
    if os.environ.get('CI'):
        raise AssertionError(f'{what} is missing, and CI must run the editor parity test')
    raise unittest.SkipTest(f'{what} is missing')


def compiler():
    return need(shutil.which(os.environ.get('CXX', 'clang++')) or shutil.which('g++'), 'a C++ compiler')


def node():
    """vite-node from web/node_modules. Without them the test waits for them: tools/check.sh runs the Python tests before
    its npm ci, and this test again after it with EDITOR_PARITY set, where they must be there (CI included)."""
    need(shutil.which('node'), 'node')
    if VITE_NODE.exists():
        return VITE_NODE
    if os.environ.get('EDITOR_PARITY'):
        raise AssertionError('web/node_modules is missing: cd web && npm ci')
    raise unittest.SkipTest('web/node_modules is missing (cd web && npm ci); tools/check.sh runs this test after its npm ci')


def shapes():
    """Every board's shape as the add-on hands it to the editor (core.board_shape), lying down and standing up; one of
    each distinct glass, grid, density, look, fonts and spacing."""
    seen, out = set(), []
    for key, board in core.SHAPES.items():
        if '/' in key:
            continue
        for way in board['orientations']:
            shape = core.board_shape(board, way)
            ident = json.dumps({k: shape.get(k) for k in ('width', 'height', 'columns', 'rows', 'dpi', 'look', 'fonts', 'spacing')},
                               sort_keys=True)
            if ident not in seen:
                seen.add(ident)
                out.append((f'{key}-{way}', key, shape))
    return out


SHAPES = shapes()
PX = list(range(-40, 1301))
REACHES = list(range(0, 1400, 7))
MODES = range(0, 8)
PLACES = ('row', 'tall', 'full')


def cut(pattern, text, what):
    """A piece of runtime_tiles.h as it stands; a firmware that moved it fails here, saying what to update."""
    found = re.search(pattern, text, re.S)
    if not found:
        raise AssertionError(f'runtime_tiles.h: {what} not found; update tests/test_editor_parity.py to where it went')
    return found.group(1) if found.groups() else found.group(0)


def panel_source():
    """The panel's sizes from runtime_tiles.h (LVGL around them, plain arithmetic inside): PanelMetrics, panel_metrics,
    panel_metrics_full, bar_metrics, the inset of a stepper's keys and the finger of a taller card."""
    parts = [cut(r'struct PanelMetrics \{[^}]*\};', TILES, 'struct PanelMetrics'),
             cut(r'inline climate_tile::Metrics bar_metrics\(.*?\n\}', TILES, 'bar_metrics'),
             cut(r'inline PanelMetrics panel_metrics\(bool large\) \{.*?\n\}', TILES, 'panel_metrics'),
             cut(r'inline PanelMetrics panel_metrics_full\(bool big\) \{.*?\n\}', TILES, 'panel_metrics_full')]
    inset = cut(r'inline void stepper_keys\(.*?\)\{\s*const int in=(.*?),d=std::max', TILES, "stepper_keys' inset")
    taller = cut(r'if\(taller\)\{\s*m\.key_h=(.*?);m\.key_w=m\.key_h;', TILES, "a taller card's key")
    return ('namespace runtime_tiles {\n' + '\n'.join(parts) +
            f'\ninline int stepper_inset() {{ return {inset}; }}\ninline int taller_key(bool large) {{ return {taller}; }}\n}}\n')


def build_and_run(source, tmp):
    path = Path(tmp) / 'parity.cpp'
    path.write_text(source)
    binary = Path(tmp) / 'parity'
    subprocess.run([compiler(), '-std=c++17', f'-I{ROOT}', f'-I{ROOT / "tests"}', str(path), '-o', str(binary)], check=True)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


def run_ts(body, data, tmp):
    """`body` with the editor's model modules imported, run by vite-node with the editor's own config (its virtual
    modules: the firmware's theme, the texts); `data` is DATA there, and what it prints comes back as JSON."""
    model = WEB / 'src/model'
    (Path(tmp) / 'data.json').write_text(json.dumps(data))
    script = Path(tmp) / 'parity.ts'
    script.write_text(f'''import {{ readFileSync }} from "node:fs";
import {{ cardContent, cardHeight, cellContent, modeBar, pillMetrics, uiScale, watchCard, watchPadding, widestSetpoint }} from "{model / 'ui-scale'}";
import {{ barGaps, barLayout, barMetricsFor }} from "{model / 'topbar'}";
import {{ sizeColumns, sizeFor, sizeRows, spanOf, spanOffered }} from "{model / 'sizes'}";
import {{ accent, tileActive }} from "{model / 'tile-palette'}";
import {{ barKeys }} from "{model / 'tall-controls'}";
const DATA = JSON.parse(readFileSync("{Path(tmp) / 'data.json'}", "utf8"));
{body}
''')
    out = subprocess.run([str(node()), '--config', 'vitest.config.ts', str(script)], cwd=WEB, check=True, capture_output=True,
                         text=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def cpp_strings(values):
    return ', '.join(json.dumps(v) for v in values)


class Sizes(unittest.TestCase):
    """ui::px and the look, the -/+ pill and the mode bar, on every board's glass."""

    @classmethod
    def setUpClass(cls):
        compiler(), node()
        with tempfile.TemporaryDirectory() as tmp:
            cls.ts = run_ts('''
const out = DATA.shapes.map((shape: any) => {
  const { px, large } = uiScale(shape);
  const bars: Record<string, any> = {};
  for (const place of ["row", "tall", "full"] as const)
    bars[place] = DATA.reaches.map((reach: number) => DATA.modes.map((modes: number) => modeBar(shape, place, reach, modes)));
  return { px: DATA.px.map(px), large, pill: pillMetrics(shape), bars };
});
console.log(JSON.stringify(out));''', {'shapes': [s for _, _, s in SHAPES], 'px': PX, 'reaches': REACHES, 'modes': list(MODES)}, tmp)
            looks = ',\n'.join(f'  {{{shape["dpi"]}, "{shape["look"]}"}}' for _, _, shape in SHAPES)
            cls.cpp = build_and_run(f'''#include "screen_text_en.h"
#define THEME_TEST
#include "components/smart_display/ui_scale.h"
#include "components/smart_display/climate_tile.h"
#include <cstdio>
#include <string>
{panel_source()}
struct Look {{ int dpi; const char *look; }};
static const Look LOOKS[] = {{
{looks}
}};
static const int PX[] = {{{', '.join(map(str, PX))}}};
static const int REACHES[] = {{{', '.join(map(str, REACHES))}}};
using namespace runtime_tiles;
int main() {{
  for (const auto &l : LOOKS) {{
    ui::configure(l.dpi, l.look);
    std::printf("look %d %d %d %d %d", ui::large() ? 1 : 0, ui::touch_min(), ui::control_max_width(), ui::column_gap(), ui::cell_height());
    for (int mm = 0; mm <= 40; ++mm) std::printf(" %d", ui::mm(mm));
    std::printf("\\npx");
    for (int n : PX) std::printf(" %d", ui::px(n));
    // The pill of a wide card's -/+ (layout_panel: m.key_h + 2) and its round keys (stepper_keys).
    const int height = panel_metrics(ui::large()).key_h + 2, in = stepper_inset();
    std::printf("\\npill %d %d %d\\n", height, in, std::max(1, height - 2 * in));
    // The mode bar's finger: the panel's key on a card of one row, a taller card's key, the full card's (by its cell).
    PanelMetrics row = panel_metrics(ui::large()), tall = row;
    tall.key_h = taller_key(ui::large());
    const climate_tile::Metrics fingers[] = {{bar_metrics(row, ui::large()), bar_metrics(tall, ui::large()),
                                              bar_metrics(panel_metrics_full(false), ui::large()), bar_metrics(panel_metrics_full(true), ui::large())}};
    const char *names[] = {{"row", "tall", "full_small", "full_big"}};
    for (int f = 0; f < 4; ++f) {{
      std::printf("bar %s %d %d", names[f], fingers[f].touch, fingers[f].inset());
      for (int reach : REACHES)
        for (int modes = 0; modes < {len(MODES)}; ++modes) {{
          const int r = std::min(reach, ui::control_max_width());
          const int room = climate_tile::bar_room(fingers[f], r, modes);
          std::printf(" %d:%d", room, climate_tile::bar_width(fingers[f], r, room, f != 0));
        }}
      std::printf("\\n");
    }}
  }}
}}
''', tmp)

    def firmware(self):
        """{shape index: {'look': [...], 'px': [...], 'pill': [...], 'bar': {name: (finger, inset, [(room, width)])}}}."""
        out = []
        for line in self.cpp.splitlines():
            tag, *rest = line.split()
            if tag == 'look':
                out.append({'look': [int(v) for v in rest], 'bar': {}})
            elif tag == 'px':
                out[-1]['px'] = [int(v) for v in rest]
            elif tag == 'pill':
                out[-1]['pill'] = [int(v) for v in rest]
            elif tag == 'bar':
                name, finger, inset, *cells = rest
                out[-1]['bar'][name] = (int(finger), int(inset), [tuple(int(v) for v in cell.split(':')) for cell in cells])
        self.assertEqual(len(out), len(SHAPES))
        return out

    def test_px_and_the_look_are_ui_scale(self):
        for (key, _, shape), fw, ts in zip(SHAPES, self.firmware(), self.ts):
            self.assertEqual(ts['px'], fw['px'], f'{key}: uiScale().px is not ui::px')
            self.assertEqual(ts['large'], bool(fw['look'][0]), f'{key}: uiScale().large is not ui::large()')

    def test_the_pill_of_a_wide_cards_stepper(self):
        for (key, _, shape), fw, ts in zip(SHAPES, self.firmware(), self.ts):
            pill = ts['pill']
            self.assertEqual([pill['height'], pill['inset'], pill['key']], fw['pill'], f'{key}: pillMetrics')

    def test_the_mode_bar_fits_as_many_modes_as_climate_tile(self):
        for (key, _, shape), fw, ts in zip(SHAPES, self.firmware(), self.ts):
            for place, name in (('row', 'row'), ('tall', 'tall')):
                finger, inset, cells = fw['bar'][name]
                mine = [bar for row in ts['bars'][place] for bar in row]
                self.assertEqual({(b['finger'], b['inset']) for b in mine}, {(finger, inset)}, f'{key} {place}: finger and inset')
                self.assertEqual([(b['room'], b['width']) for b in mine], cells, f'{key} {place}: room and width')
            # A card over the whole page takes the full card's keys by its cell's height (layout_panel:
            # panel_metrics_full(w.base_height>80)); which one that is, the grid of the firmware says
            # (Grid.test_a_full_cards_finger_follows_its_cell). Here both match the same rule.
            mine = [bar for row in ts['bars']['full'] for bar in row]
            fingers = {fw['bar'][n][0]: n for n in ('full_small', 'full_big')}
            self.assertIn(mine[0]['finger'], fingers, f'{key} full: the finger is neither of panel_metrics_full')
            finger, inset, cells = fw['bar'][fingers[mine[0]['finger']]]
            self.assertEqual([(b['room'], b['width']) for b in mine], cells, f'{key} full: room and width')
            self.assertEqual({b['inset'] for b in mine}, {inset}, f'{key} full: inset')

    def test_the_touch_minimum_is_seven_millimetres(self):
        # modeBar's taller finger works ui::touch_min() out itself; the C++ does so with ui::mm(7).
        for (key, _, shape), fw in zip(SHAPES, self.firmware()):
            self.assertEqual(fw['look'][1], (shape['dpi'] * 7 + 12) // 25, key)
            self.assertEqual(fw['look'][1], fw['look'][5 + 7], key)


class Grid(unittest.TestCase):
    """What LVGL's grid makes of a card (runtime_tiles cell_content_width, base_height), from the WebAssembly build."""

    @classmethod
    def setUpClass(cls):
        need(shutil.which('node'), 'node')
        need(WASM if WASM.exists() else None, 'web/src/wasm/firmware_preview.wasm')
        screens = []
        for key, _, shape in SHAPES:
            tiles = lambda size: [{'entity': 'switch.parity', 'name': 'Lamp', 'state': 'on', 'a': {}, 'slot': 0,
                                   'o': core.screen_options({'entity': 'switch.parity', 'options': {'size': size}}, {}, 'on') or {}}]
            sizes = ['single', 'full'] + (['wide'] if shape['columns'] >= 2 else [])
            screens.append({'key': key, 'width': shape['width'], 'height': shape['height'], 'columns': shape['columns'],
                            'rows': shape['rows'], 'dpi': shape['dpi'], 'layouts': [{'key': size, 'tiles': tiles(size)} for size in sizes]})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screens.json'
            path.write_text(json.dumps(screens))
            out = subprocess.run(['node', str(WEB / 'wasm/layout_audit.mjs'), str(path)], check=True, capture_output=True, text=True).stdout
        cls.cards = {}
        for report in json.loads(out):
            if 'error' in report:
                raise AssertionError(f"{report['screen']}: {report['error']}")
            objects = {o['id']: o for o in report['objects']}
            box = objects[report['cards'][0]['object']]
            cls.cards[(report['screen'], report['layout'])] = (box['x2'] - box['x1'] + 1, box['y2'] - box['y1'] + 1)
        with tempfile.TemporaryDirectory() as tmp:
            cls.ts = run_ts('''
console.log(JSON.stringify(DATA.shapes.map((shape: any) => ({
  content: Array.from({ length: shape.columns }, (_, i) => cardContent(shape, shape.columns, i + 1)),
  last: cardContent(shape, shape.columns, 1, shape.columns - 1), cell: cellContent(shape, shape.columns),
  full: modeBar(shape, "full", 400, 4).finger, px: [uiScale(shape).px(44), uiScale(shape).px(84)] }))));''',
                            {'shapes': [s for _, _, s in SHAPES]}, tmp)

    def test_a_cards_room_is_its_cells(self):
        for (key, _, shape), ts in zip(SHAPES, self.ts):
            edges = 2 * shape['spacing']['tile_pad'] + 2   # the card's padding and its border of one pixel
            columns = shape['columns']
            # The cards LVGL's grid lays out: one cell, a wide card of two and the whole page (cardContent).
            self.assertEqual(ts['content'][0] + edges, self.cards[(key, 'single')][0], f'{key}: cardContent of one cell')
            if columns >= 2:
                self.assertEqual(ts['content'][1] + edges, self.cards[(key, 'wide')][0], f'{key}: cardContent of a wide card')
            full = self.cards[(key, 'full')][0]
            self.assertEqual(ts['content'][-1] + edges, full, f'{key}: cardContent of the whole page')
            # And the cell a wide card's controls fill (cell_content_width): the grid's own width shared out, rounded down.
            self.assertEqual(ts['cell'], (full - (columns - 1) * shape['spacing']['gap']) // columns - edges, f'{key}: cellContent')

    # A card over the whole page takes its keys by the height of a cell (layout_panel: panel_metrics_full(w.base_height
    # > 80)), and the editor knows no cell heights: its mockup takes them by the look (modeBar "full"), which is the same
    # answer on every board but the Hosyond, whose compact look has cells of 88 and 105 pixels. Known, and kept here so
    # a fix shows up: the editor needs the board's cell height for it (the top bar's band and the page bar), which
    # boards.json does not carry yet.
    KNOWN = {'hosyond40-landscape', 'hosyond40-portrait'}

    def test_a_full_cards_finger_follows_its_cell(self):
        for (key, _, shape), ts in zip(SHAPES, self.ts):
            big = self.cards[(key, 'single')][1] > 80
            if key in self.KNOWN:
                self.assertNotEqual(ts['full'], ts['px'][1 if big else 0], f'{key} is fixed: take it out of Grid.KNOWN')
                continue
            self.assertEqual(ts['full'], ts['px'][1 if big else 0], f'{key}: the full card keys are panel_metrics_full({big})')


class WatchCard(unittest.TestCase):
    """A Big number card (display "watch"), from the WebAssembly build: the height LVGL's grid gives a card (cardHeight,
    with and without the page bar), and where the card's icon, name, number and unit stand (watchCard, runtime_tiles):
    whether the head stands above the number, the face of each line and its place from the top of the card. GitHub
    #167: the mockup's own sizes cut the number off at its middle on a 4-inch Guition with three rows and three pages.
    The widths are the firmware's own measure of its glyphs, so where a unit or a number stands across is not compared;
    the faces the firmware picks by a width are, with values that fit or miss by far. The WebAssembly build is one per
    density and look (web/wasm/preview_profiles.py), with the frame and fonts of the first board that has them, so the
    editor's numbers are compared on that board's frame; a board's own comes from the same board files its firmware
    builds from (boards.json)."""

    VALUES = (('217', 'mg/dl'), ('21.4', '°C'), ('rising slightly', ''))
    # The preview builds a density as a whole number (generate_host_ui.py), and the page bar follows the density
    # (PAGE_BAR_H, 7 mm): the Waveshare 5-inch's glass is 186.59 dpi and its bar 51 pixels, the preview's 187 dpi gives
    # 52. On those pages a card of the preview is a pixel lower than the screen's, which the editor follows; its faces
    # and whether its head stands above the number are still compared. Kept here so a fix shows up.
    KNOWN = {'waveshare5-landscape', 'waveshare5-portrait'}

    @classmethod
    def setUpClass(cls):
        need(shutil.which('node'), 'node')
        need(WASM if WASM.exists() else None, 'web/src/wasm/firmware_preview.wasm')
        sys.path.insert(0, str(WEB / 'wasm'))
        import preview_profiles  # noqa: E402
        drawn = {(dpi, look): core.SHAPES[entry] for dpi, look, entry in preview_profiles.variants()}
        cls.cases, screens = [], []
        for key, board, shape in SHAPES:
            profile = drawn[(shape['dpi'], shape['look'])]
            mine = {**shape, 'fonts': profile['fonts'], 'spacing': profile['spacing']}
            choices = (shape.get('catalog') or {}).get('choices', {}).get('GRID_ROWS') or []
            downs = sorted({shape['rows'], *(int(rows) for rows in choices if key.endswith('-landscape'))})
            for down in downs:
                layouts = []
                for pages in (1, 3):
                    for size, columns in (('single', 1), ('wide', 2)):
                        if columns > shape['columns']:
                            continue
                        for row in sorted({0, down - 1}):
                            for value, unit in cls.VALUES:
                                case = {'key': f'{key} {down} rows, {pages} pages, {size} in row {row}: {value} {unit}'.strip(),
                                        'known': key in cls.KNOWN and pages > 1,
                                        'shape': mine, 'down': down, 'pages': pages, 'size': size, 'columns': columns,
                                        'row': row, 'value': value, 'unit': unit}
                                attrs = {'unit_of_measurement': unit} if unit else {}
                                tiles = [{'entity': 'sensor.parity', 'name': 'Glucose', 'state': value, 'a': attrs,
                                          'slot': row * shape['columns'],
                                          'o': core.screen_options({'entity': 'sensor.parity', 'options': {'display': 'watch', 'size': size}},
                                                                   attrs, value) or {}}]
                                # A second page holds a card of its own, so the layout has the pages it says.
                                if pages > 1:
                                    tiles.append({'entity': 'switch.parity', 'name': 'Lamp', 'state': 'on', 'a': {}, 'o': {},
                                                  'slot': shape['columns'] * down})
                                layouts.append({'key': str(len(cls.cases)), 'pages': pages, 'tiles': tiles})
                                cls.cases.append(case)
                screens.append({'key': f'{key}-{down}', 'width': shape['width'], 'height': shape['height'],
                                'columns': shape['columns'], 'rows': down, 'dpi': shape['dpi'], 'layouts': layouts})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screens.json'
            path.write_text(json.dumps(screens))
            out = subprocess.run(['node', str(WEB / 'wasm/layout_audit.mjs'), str(path)], check=True, capture_output=True, text=True).stdout
        cls.firmware = {}
        for report in json.loads(out):
            if 'error' in report:
                raise AssertionError(f"{report['screen']}: {report['error']}")
            objects = [o for o in report['objects'] if o['card'] == 0]
            box = next(o for o in objects if o['id'] == report['cards'][0]['object'])
            case = cls.cases[int(report['layout'])]
            labels = {o['text']: o for o in objects if o['type'] == 'label' and not o['icon']}
            circle = next((o for o in objects if o['type'] == 'object' and o['radius'] >= 999 and o['id'] != box['id']), None)
            name = labels.get('Glucose')
            number = next((o for text, o in labels.items() if text not in ('Glucose', case['unit'])), None)
            unit = labels.get(case['unit']) if case['unit'] else None
            cls.firmware[int(report['layout'])] = {'box': box, 'circle': circle, 'name': name, 'number': number, 'unit': unit}
        with tempfile.TemporaryDirectory() as tmp:
            cls.ts = run_ts('''
console.log(JSON.stringify(DATA.cases.map((c: any) => {
  const s = c.shape, pad = watchPadding(s, c.down), height = cardHeight(s, c.down, 1, c.row, c.pages > 1);
  const width = cardContent(s, s.columns, c.columns, 0);
  return { height, pad, card: watchCard(s, width, height - 2 * (pad + 1), c.value, c.unit, pad) };
})));''', {'cases': cls.cases}, tmp)

    def test_a_card_is_as_high_as_its_cell(self):
        known = 0
        for i, case in enumerate(self.cases):
            box = self.firmware[i]['box']
            drawn = box['y2'] - box['y1'] + 1
            if case['known']:
                self.assertLessEqual(abs(self.ts[i]['height'] - drawn), 1, f"{case['key']}: cardHeight")
                known += self.ts[i]['height'] != drawn
                continue
            self.assertEqual(self.ts[i]['height'], drawn, f"{case['key']}: cardHeight")
        self.assertTrue(known, f'{sorted(self.KNOWN)}: the preview draws the page bar as the screen does now; take them out of KNOWN')

    def test_the_head_the_number_and_the_unit_stand_where_the_firmware_puts_them(self):
        for i, case in enumerate(self.cases):
            fw, ts = self.firmware[i], self.ts[i]
            card, top = ts['card'], fw['box']['y1'] + ts['pad'] + 1
            where = case['key']
            self.assertEqual(card['stacked'], fw['circle'] is not None, f'{where}: the icon and the name above the number')
            if card['stacked'] and not case['known']:
                circle = fw['circle']
                self.assertEqual(card['circle']['size'], circle['x2'] - circle['x1'] + 1, f'{where}: the circle')
                self.assertEqual(card['circle']['y'], circle['y1'] - top, f'{where}: the circle from the top')
            for part, label in (('title', fw['name']), ('value', fw['number']), ('unit', fw['unit'])):
                mine = card[part]
                if label is None or mine is None:
                    self.assertEqual(mine is None, label is None, f'{where}: whether the {part} is drawn')
                    continue
                self.assertEqual(mine['line'], label['line_height'], f'{where}: the face of the {part}')
                if not case['known']:
                    self.assertEqual(mine['y'], label['y1'] - top, f'{where}: the {part} from the top')


class TopBar(unittest.TestCase):
    """The top bar: the look's fonts and margin scaled to each board as the build scales them, the gaps, and which items
    fit beside the name (header_bar.h)."""

    @classmethod
    def setUpClass(cls):
        compiler(), node()
        cls.boards = [(f'{key}-{way}', key, core.board_shape(board, way)) for key, board in core.SHAPES.items() if '/' not in key
                      for way in board['orientations']]
        texts = ['21.5 °C', 'Away', '7:12 PM', 'Sa 19 Sep', '1,249 W', 'A long text that runs on', '5 min ago', '']
        scenarios = []
        for i, (key, _, shape) in enumerate(cls.boards):
            for n in range(0, 7):
                for start in range(0, len(texts), 3):
                    items = [{'text': texts[(start + k) % len(texts)], 'icon': 'F0599' if (start + k) % 2 else None,
                              'shown': (start + k) % 5 != 4} for k in range(n)]
                    for name in ('Hall', 'The living room downstairs by the window'):
                        for home, back in ((False, False), (True, False), (False, True)):
                            scenarios.append({'shape': i, 'items': items, 'name': name, 'home': home, 'back': back})
        with tempfile.TemporaryDirectory() as tmp:
            cls.ts = run_ts('''
// A canvas that measures in whole pixels, so the C++ gets the same integer widths the mockup placed by.
const context = { font: "", measureText(text: string) {
  const size = Number(/(\\d+(?:\\.\\d+)?)px/.exec(this.font)?.[1] || 14), advance = [...text].length * Math.round(size * 0.6);
  return { width: advance, actualBoundingBoxLeft: 0, actualBoundingBoxRight: advance, actualBoundingBoxAscent: Math.round(size * 0.72),
           actualBoundingBoxDescent: 0 };
} };
(globalThis as any).document = { createElement: () => ({ getContext: () => context }) };
const metrics = DATA.shapes.map((shape: any) => barMetricsFor(shape));
const gaps = Array.from({ length: 121 }, (_, cap) => barGaps(cap));
const places = DATA.scenarios.map((s: any) => {
  const views = s.items.map((item: any) => ({ text: item.text || undefined, icon: item.icon, shown: item.shown }));
  const items = s.items.map((_: any, i: number) => ({ type: "text", id: String(i) }));
  const bar = barLayout(items, metrics[s.shape], s.name, (item: any) => views[Number(item.id)], s.home, s.back);
  const shown = bar.parts.filter((p) => p.shown);
  return { widths: shown.map((p) => p.width), cap: bar.cap, width: bar.metrics.width - bar.homeShift, natural: bar.natural,
           shift: bar.homeShift, first: bar.dropped.size, xs: bar.placed.map((p) => p.x), room: bar.nameRoom };
});
console.log(JSON.stringify({ metrics, gaps, places }));''', {'shapes': [s for _, _, s in cls.boards], 'scenarios': scenarios}, tmp)
            rows = ',\n'.join(f'  {{{p["cap"]}, {p["width"]}, {p["natural"]}, {len(p["widths"])}, {{{", ".join(map(str, p["widths"])) or "0"}}}}}'
                              for p in cls.ts['places'])
            cls.cpp = build_and_run(f'''#include "screen_text_en.h"
#include "components/smart_display/header_bar.h"
#include <cstdio>
struct Case {{ int cap, width, natural; size_t count; int widths[6]; }};
static const Case CASES[] = {{
{rows}
}};
int main() {{
  for (int cap = 0; cap <= 120; ++cap) {{ const auto g = header_bar::gaps(cap); std::printf("gaps %d %d %d\\n", g.icon, g.item, g.name); }}
  for (const auto &c : CASES) {{
    const auto p = header_bar::place(c.widths, c.count, header_bar::gaps(c.cap), c.width, c.natural);
    std::printf("place %zu %d", p.first, p.name_room);
    for (size_t i = p.first; i < c.count; ++i) std::printf(" %d", p.x[i]);
    std::printf("\\n");
  }}
}}
''', tmp)

    def test_the_bar_is_the_looks_fonts_at_the_boards_density(self):
        # barMetricsFor scales the look's sizes by the density in the editor; the build works each board's own out in
        # packages/looks/ from DISPLAY_DPI (FONT_HEADLINE_SIZE, FONT_SUBLABEL_BIG_SIZE, FONT_ICON_MINI_SIZE, HEADER_INSET,
        # and the Tessera mark at 17/24 of FONT_ICON_HOME_SIZE, as packages/core.yaml resizes it).
        values = {}
        for (key, board, shape), bar in zip(self.boards, self.ts['metrics']):
            v = values.setdefault(board, profiles.board_values(board))
            inset = int(v['HEADER_INSET'])
            wanted = {'name': int(v['FONT_HEADLINE_SIZE']), 'text': int(v['FONT_SUBLABEL_BIG_SIZE']), 'icon': int(v['FONT_ICON_MINI_SIZE']),
                      'inset': inset, 'mark': round(int(v['FONT_ICON_HOME_SIZE']) * 17 / 24), 'width': shape['width'] - 2 * inset}
            self.assertEqual({k: bar[k] for k in wanted}, wanted, key)

    def test_the_gaps_are_header_bar_gaps(self):
        firmware = [[int(v) for v in line.split()[1:]] for line in self.cpp.splitlines() if line.startswith('gaps ')]
        self.assertEqual([[g['icon'], g['item'], g['name']] for g in self.ts['gaps']], firmware)

    def test_the_items_that_fit_are_header_bar_place(self):
        firmware = [[int(v) for v in line.split()[1:]] for line in self.cpp.splitlines() if line.startswith('place ')]
        self.assertEqual(len(firmware), len(self.ts['places']))
        for mine, (first, room, *xs) in zip(self.ts['places'], firmware):
            # The firmware places beside the home key (page_header.h: `left += shift; width -= shift`); the mockup from
            # the bar's own left edge.
            self.assertEqual((mine['first'], mine['room'], mine['xs']), (first, room, [x + mine['shift'] for x in xs]), mine)


class TileSizes(unittest.TestCase):
    """A tile's size: sizes.ts, page_protocol.h and core.py."""

    @classmethod
    def setUpClass(cls):
        compiler(), node()
        cls.names = ['single', 'wide', 'tall', 'square', 'full', '', 'huge', '3x2', '2x3', '1x9', '9x1', '0x1', '1x0', '10x2',
                     '3x22', '3X2', '3*2', ' 3x2', '3x2 ', 'x', '3x', 'x2', 'ax2'] + [f'{c}x{r}' for c in range(1, 10) for r in range(1, 10)]
        cls.grids = sorted({(s['columns'], s['rows']) for _, _, s in SHAPES} | {(c, r) for c in range(1, 9) for r in range(1, 9)})
        with tempfile.TemporaryDirectory() as tmp:
            cls.ts = run_ts('''
const grids = DATA.grids.map(([columns, rows]: number[]) => ({ columns, rows }));
console.log(JSON.stringify({
  spans: DATA.names.map((name: string) => spanOf(name)),
  rows: DATA.names.map((name: string) => sizeRows(name)), columns: DATA.names.map((name: string) => sizeColumns(name)),
  offered: grids.map((g: any) => DATA.rect.map(([c, r]: number[]) => spanOffered(c, r, g))),
  sizes: grids.map((g: any) => DATA.rect.map(([c, r]: number[]) => sizeFor(c, r, g))),
}));''', {'names': cls.names, 'grids': cls.grids, 'rect': [[c, r] for c in range(1, 10) for r in range(1, 10)]}, tmp)
            names = cpp_strings(cls.names)
            grids = ', '.join(f'{{{c}, {r}}}' for c, r in cls.grids)
            cls.cpp = build_and_run(f'''#include "components/smart_display/page_protocol.h"
#include <cstdio>
static const char *NAMES[] = {{{names}}};
static const unsigned GRIDS[][2] = {{{grids}}};
int main() {{
  for (const char *name : NAMES) {{
    unsigned c = 0, r = 0;
    const bool span = page_protocol::span_of(name, c, r);
    std::printf("span %d %u %u\\n", span ? 1 : 0, span ? c : 0, span ? r : 0);
  }}
  for (const auto &g : GRIDS) {{
    std::printf("offered");
    for (unsigned c = 1; c <= 9; ++c) for (unsigned r = 1; r <= 9; ++r) std::printf(" %d", page_protocol::span_offered(c, r, g[0], g[1]) ? 1 : 0);
    std::printf("\\naccepts");
    for (const char *name : NAMES) std::printf(" %d", page_protocol::accepts_size(name, g[0], g[1]) ? 1 : 0);
    std::printf("\\n");
  }}
}}
''', tmp)
        cls.firmware = {tag: [line.split()[1:] for line in cls.cpp.splitlines() if line.startswith(tag + ' ')] for tag in ('span', 'offered', 'accepts')}

    def test_a_span_is_read_alike(self):
        for name, mine, (found, c, r) in zip(self.names, self.ts['spans'], self.firmware['span']):
            firmware = (int(c), int(r)) if found == '1' else None
            self.assertEqual(firmware, core.span_of(name), f'{name!r}: page_protocol::span_of and core.span_of')
            self.assertEqual(None if mine is None else (mine['columns'], mine['rows']), firmware, f'{name!r}: spanOf')

    def test_rows_and_columns_of_a_size(self):
        for name, rows, columns in zip(self.names, self.ts['rows'], self.ts['columns']):
            if name and name not in ('huge',) and core.is_size(name):
                self.assertEqual((rows, columns), (core.size_rows(name), core.size_columns(name)), name)

    def test_a_grid_offers_the_same_spans(self):
        rect = [(c, r) for c in range(1, 10) for r in range(1, 10)]
        for (gc, gr), mine, firmware in zip(self.grids, self.ts['offered'], self.firmware['offered']):
            python = [core.span_offered(c, r, core.Grid(gc, gr)) if gc * gr <= 64 else None for c, r in rect]
            self.assertEqual(mine, [v == '1' for v in firmware], f'{gc}x{gr}: spanOffered and page_protocol::span_offered')
            if gc * gr <= 64:
                self.assertEqual(mine, python, f'{gc}x{gr}: spanOffered and core.span_offered')

    def test_every_rectangle_the_editor_names_the_screen_takes(self):
        rect = [(c, r) for c in range(1, 10) for r in range(1, 10)]
        for (gc, gr), sizes, accepts in zip(self.grids, self.ts['sizes'], self.firmware['accepts']):
            accepted = {name for name, ok in zip(self.names, accepts) if ok == '1'}
            for (c, r), size in zip(rect, sizes):
                if size is None:
                    continue
                self.assertIn(size, accepted, f'{gc}x{gr}: sizeFor({c}, {r}) = {size}, which the screen refuses')
                if gc * gr <= 64:
                    self.assertEqual(core.Grid(gc, gr).dimensions(size), (c, r), f'{gc}x{gr}: {size} is not {c}x{r} in core')
            # And every span the screen takes is the size the editor gives its rectangle.
            for name in accepted:
                span = core.span_of(name)
                if span and span[0] <= 9 and span[1] <= 9:
                    self.assertEqual(sizes[rect.index(span)], name, f'{gc}x{gr}: {name}')


DOMAINS = ['light', 'switch', 'input_boolean', 'script', 'automation', 'remote', 'timer', 'camera', 'climate', 'vacuum', 'fan',
           'cover', 'scene', 'media_player', 'select', 'input_select', 'number', 'input_number', 'weather', 'sun', 'person',
           'alarm_control_panel', 'lock', 'sensor', 'binary_sensor', 'button', 'input_button', 'image', 'screen', 'calendar',
           'device_tracker', 'event', 'update', 'water_heater', 'humidifier', 'valve', 'lawn_mower', 'siren', 'todo']
STATES = ['', 'on', 'off', 'unknown', 'unavailable', 'open', 'closed', 'opening', 'closing', 'home', 'not_home', 'Office',
          'playing', 'standby', 'paused', 'idle', 'docked', 'cleaning', 'error', 'returning', 'active', 'streaming',
          'recording', 'disarmed', 'armed_away', 'triggered', 'arming', 'pending', 'disarming', 'locked', 'unlocked',
          'locking', 'unlocking', 'jammed', 'heat', 'cool', 'heat_cool', 'auto', 'dry', 'fan_only', 'sunny', 'clear-night',
          'partlycloudy', 'cloudy', 'fog', 'rainy', 'pouring', 'snowy', 'snowy-rainy', 'hail', 'lightning',
          'lightning-rainy', 'windy', 'windy-variant', 'exceptional', 'above_horizon', 'below_horizon',
          '2026-09-30T10:00:00+00:00', '21.5', '85', '70', '69.9', '30', '29', '0', '-3', 'abc', '12abc']
CLASSES = ['', 'battery', 'smoke', 'door', 'temperature', 'moisture', 'tamper', 'carbon_monoxide']
UNITS = ['', '°C', '°F', 'lx', 'kWh', 'Wh', '%', 'W']
HUES = [None, (0, 100), (30, 50), (200, 9.6), (200, 9.4), (359.6, 80), (120, 5), (45.5, 72.3), (275, 40), (300, 100),
        (60, 25), (17, 63), (240, 100), (181, 33.3)] + [(h, s) for h in range(0, 361, 15) for s in (10, 45, 77, 100)]


def palette_cases():
    cases = []
    for domain in DOMAINS:
        for state in STATES:
            if domain in ('sensor', 'binary_sensor'):
                cases += [{'entity': f'{domain}.x', 'state': state, 'a': {'device_class': dc, 'unit_of_measurement': unit}}
                          for dc in CLASSES for unit in UNITS]
            elif domain == 'light':
                cases += [{'entity': 'light.x', 'state': state, 'a': {} if hs is None else {'hs_color': list(hs)}} for hs in HUES]
            elif domain == 'automation':
                cases += [{'entity': 'automation.x', 'state': state, 'a': {'current': current}, 'runs': runs}
                          for current in (0, 1) for runs in (False, True)]
            else:
                cases.append({'entity': 'screen.clock' if domain == 'screen' else f'{domain}.x', 'state': state, 'a': {}})
    return cases


class Colours(unittest.TestCase):
    """A card's colour: tile-palette.ts tileActive and accent against Tile::active and tile_controls::accent, with a
    lamp's own colour through tile_controls::lamp_color while it is on (runtime_tiles: the tile's palette)."""

    @classmethod
    def setUpClass(cls):
        compiler(), node()
        cls.cases = palette_cases()
        with tempfile.TemporaryDirectory() as tmp:
            cls.ts = run_ts('''
console.log(JSON.stringify(DATA.cases.map((c: any) => {
  const value = { state: c.state, a: c.a };
  return [tileActive(c.entity, value, Boolean(c.runs)), accent(c.entity, value)];
})));''', {'cases': cls.cases}, tmp)
            rows = []
            for c in cls.cases:
                a = c['a']
                hs = a.get('hs_color')
                # page_receiver.cpp: std::lround of the value clamped to its range.
                hue = math.floor(min(max(hs[0], 0), 360) + 0.5) if hs else 0
                saturation = math.floor(min(max(hs[1], 0), 100) + 0.5) if hs else 0
                rows.append(f'  {{{json.dumps(c["entity"])}, {json.dumps(c["state"])}, {json.dumps(a.get("device_class", ""))}, '
                            f'{json.dumps(a.get("unit_of_measurement", ""))}, {int(bool(c.get("runs")))}, {int(a.get("current", 0) > 0)}, '
                            f'{int(bool(hs))}, {hue}, {saturation}}}')
            cls.cpp = build_and_run('''#include "screen_text_en.h"
#define THEME_TEST
#include "components/smart_display/tile_controls.h"
#include <cstdio>
struct Case { const char *entity, *state, *device_class, *unit; int runs, running, hs, hue, saturation; };
static const Case CASES[] = {
''' + ',\n'.join(rows) + '''
};
int main() {
  for (const auto &c : CASES) {
    runtime_tiles::Tile t;
    t.entity = c.entity; t.state = c.state; t.received = true; t.device_class = c.device_class; t.unit = c.unit;
    if (c.runs) t.tap = "run";
    t.running = c.running; t.has_hs_color = c.hs; t.hue = c.hue; t.saturation = c.saturation;
    const bool on = t.active();
    uint32_t colour = tile_controls::accent(t);
    if (t.domain() == "light" && on && t.has_hs_color) colour = tile_controls::lamp_color(t.hue, t.saturation);
    std::printf("%d %u\\n", on ? 1 : 0, colour);
  }
}
''', tmp)

    def test_active_and_accent_per_domain_and_state(self):
        firmware = [line.split() for line in self.cpp.splitlines()]
        self.assertEqual(len(firmware), len(self.cases))
        wrong = [(c, mine, (bool(int(on)), int(colour))) for c, mine, (on, colour) in zip(self.cases, self.ts, firmware)
                 if (mine[0], mine[1]) != (bool(int(on)), int(colour))]
        self.assertEqual(wrong[:10], [], f'{len(wrong)} of {len(self.cases)} cases differ')


class Thermostat(unittest.TestCase):
    """A thermostat's modes (barKeys, tile_controls::climate_bar_keys) and the widest temperature its -/+ measures
    (widestSetpoint, tile_controls::widest_setpoint)."""

    @classmethod
    def setUpClass(cls):
        compiler(), node()
        lists = [[], ['off'], ['off', 'heat'], ['heat', 'cool'], ['off', 'heat', 'cool', 'auto'], ['cool', 'HEAT', 'dry'],
                 ['off', 'heat', 'cool', 'heat_cool', 'auto', 'dry', 'fan_only'], ['fan_only', 'dry', 'auto', 'heat_cool', 'cool', 'heat'],
                 ['heat', 'cool', 'heat_cool', 'auto', 'dry', 'fan_only', 'eco', 'boost', 'away']]
        cls.bars = [{'modes': modes, 'state': state, 'room': room} for modes in lists
                    for state in ('off', 'heat', 'cool', 'dry', 'fan_only', 'Auto', 'eco') for room in range(0, 9)]
        cls.setpoints = [{'min': lo, 'max': hi, 'step': step} for lo in (7, 5, -20, 45, 0.5, -0.5, 10, 100)
                         for hi in (35, 30, 95, 110, 9.5, 1000) for step in (0.5, 1, 0.1, 0.25, 2, 5)]
        with tempfile.TemporaryDirectory() as tmp:
            cls.ts = run_ts('''
console.log(JSON.stringify({
  bars: DATA.bars.map((b: any) => barKeys({ hvac_modes: b.modes }, b.state, b.room).map((k) => k.mode ?? "more")),
  setpoints: DATA.setpoints.map((s: any) => widestSetpoint({ min_temp: s.min, max_temp: s.max, target_temp_step: s.step })),
}));''', {'bars': cls.bars, 'setpoints': cls.setpoints}, tmp)
            bars = ',\n'.join(f'  {{{json.dumps(json.dumps(b["modes"]))}, {json.dumps(b["state"])}, {b["room"]}}}' for b in cls.bars)
            setpoints = ',\n'.join(f'  {{{float(s["min"])}f, {float(s["max"])}f, {float(s["step"])}f}}' for s in cls.setpoints)
            cls.cpp = build_and_run(f'''#include "screen_text_en.h"
#define THEME_TEST
#include "components/smart_display/tile_controls.h"
#include <cstdio>
struct Bar {{ const char *modes, *state; unsigned room; }};
static const Bar BARS[] = {{
{bars}
}};
struct Setpoint {{ float minimum, maximum, step; }};
static const Setpoint SETPOINTS[] = {{
{setpoints}
}};
int main() {{
  for (const auto &b : BARS) {{
    runtime_tiles::Tile t; t.entity = "climate.x"; t.state = b.state; t.received = true; t.edit_extra().hvac_modes = b.modes;
    std::array<tile_controls::Key, 6> keys;
    const unsigned n = tile_controls::climate_bar_keys(t, keys, b.room);
    std::printf("bar");
    for (unsigned i = 0; i < n; ++i) std::printf(" %s", keys[i].arg.empty() ? "more" : keys[i].arg.c_str());
    std::printf("\\n");
  }}
  for (const auto &s : SETPOINTS) {{
    runtime_tiles::Tile t; t.entity = "climate.x"; t.minimum = s.minimum; t.maximum = s.maximum; t.step = s.step;
    std::printf("widest %s\\n", tile_controls::widest_setpoint(t).c_str());
  }}
}}
''', tmp)

    def test_the_modes_on_the_bar(self):
        firmware = [line.split()[1:] for line in self.cpp.splitlines() if line.startswith('bar')]
        for bar, mine, theirs in zip(self.bars, self.ts['bars'], firmware):
            self.assertEqual(mine, theirs, bar)

    def test_the_widest_temperature(self):
        firmware = [line.split(' ', 1)[1] for line in self.cpp.splitlines() if line.startswith('widest ')]
        for setpoint, mine, theirs in zip(self.setpoints, self.ts['setpoints'], firmware):
            self.assertEqual(mine, theirs, setpoint)


if __name__ == '__main__':
    unittest.main()
