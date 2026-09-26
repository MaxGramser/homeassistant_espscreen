"""Build a board of a source tree as an ESPHome host program: the real UI of the screens, drawn in an SDL window.

A screen's firmware is packages/core.yaml plus the board's file under packages/boards/, which includes its own packages
(looks, features, hardware, cells) with relative includes (docs/PROFILES.md). This walks that include tree and writes a
copy of every file with the ESP32 hardware taken out, under the same relative layout, so the includes keep working. A
small host-hw.yaml stands in for the hardware: an SDL display `my_display` at the panel's own pixels (LVGL turns the
picture as on the glass), an SDL touchscreen `ts_touch` for the features' `!extend ts_touch`, and a template output for
every output id the chain named, so `back_light` and the backlight scripts still resolve. A handful of API actions let
tools/render/run.py drive and photograph it.

A variant is a board of the catalog (boards.yaml) the way it hangs: `guition`, or `waveshare43-portrait` for a board
whose glass is not square, built with the angle ESP Screens writes into a screen standing up (boards.json).

Needs the ESPHome CLI and SDL2 (`brew install sdl2`, or `apt install libsdl2-dev`). Everything it writes lives under
.esphome/render/ of this checkout.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import profiles  # noqa: E402

# Top-level blocks that are ESP32 hardware wherever they live (board file or hardware package).
HARDWARE_BLOCKS = ('esp32', 'psram', 'spi', 'i2c', 'ch422g', 'pca9554', 'tca9554', 'esp_ldo', 'esp32_hosted',
                   'display', 'esp32_rmt', 'i2s_audio')
# RENDER_PORT_BASE moves every variant's port, so two checkouts can render at the same time without meeting.
PORT_BASE = int(os.environ.get('RENDER_PORT_BASE', 6481))


@dataclass
class Variant:
    """One board the way it hangs, with what the host build needs of it."""
    key: str        # 'guition', 'waveshare43-portrait'
    board: str      # the board's key in the catalog
    file: str       # its board file under packages/boards/
    rotation: str   # the LVGL angle a screen standing up is built with, '' lying down
    port: int       # the host program's API port

    @property
    def name(self):
        return f'render-{self.key}'


def variants():
    """Every board of the catalog lying down, and standing up where its glass is not square, in the catalog's order."""
    shapes = json.loads((REPO / 'screen_manager/app/boards.json').read_text())
    found = []
    for board, entry in profiles.CATALOG.items():
        sides = shapes[board]['orientations']
        found.append((board, board, entry['file'], ''))
        if sides['portrait']['width'] != sides['landscape']['width']:
            found.append((f'{board}-portrait', board, entry['file'], str(sides['portrait']['rotation'])))
    return [Variant(key, board, file, rotation, PORT_BASE + i) for i, (key, board, file, rotation) in enumerate(found)]


def variant(key):
    for item in variants():
        if item.key == key:
            return item
    raise SystemExit(f'unknown variant {key}; one of {", ".join(v.key for v in variants())}')


# ---- a little YAML surgery on text, so comments and ESPHome tags (!extend, !remove, !lambda) stay as they are

def top_blocks(text):
    """[(key, start, end)] of the top-level YAML blocks."""
    starts = [(m.group(1), m.start()) for m in re.finditer(r'^([a-z_0-9]+):', text, re.M)]
    return [(key, start, starts[i + 1][1] if i + 1 < len(starts) else len(text)) for i, (key, start) in enumerate(starts)]


def blocks_of(text, key):
    return [block for block in top_blocks(text) if block[0] == key]


def drop_blocks(text, key):
    """Every top-level block `key:` removed; returns (text, [the removed blocks])."""
    removed = []
    while True:
        blocks = blocks_of(text, key)
        if not blocks:
            return text, removed
        _, start, end = blocks[0]
        removed.append(text[start:end])
        text = text[:start] + text[end:]


def drop_items(text, key, predicate):
    blocks = blocks_of(text, key)
    if not blocks:
        return text
    _, start, end = blocks[0]
    parts = re.split(r'(?m)^(?=  - )', text[start:end])
    return text[:start] + parts[0] + ''.join(item for item in parts[1:] if not predicate(item)) + text[end:]


def drop_sub(block, indent, key):
    """A key at `indent` spaces inside a block removed, with everything indented under it."""
    out, skipping = [], False
    for line in block.splitlines(keepends=True):
        depth = len(line) - len(line.lstrip(' '))
        if skipping:
            if not line.strip() or depth > indent:
                continue
            skipping = False
        if re.match(rf'^ {{{indent}}}{key}:', line):
            skipping = True
            continue
        out.append(line)
    return ''.join(out)


def shape_error(what):
    raise SystemExit(f'host build: {what} changed shape; update tools/render/host.py')


def host_common(text):
    """Calls the host cannot make, in any file of the chain."""
    text = text.replace('esp_get_free_heap_size()', '0u')
    # The resistive panel's raw readings and its affine correction: the SDL touchscreen reports pixels.
    text = re.sub(r'id\((\w+)\)\.filtered_raw_[xy]\(\)', '0', text)
    return re.sub(r'id\(\w+\)\.set_raw_correction\([^;]*\);', '/* XPT2046 affine correction: not on the host */', text)


def host_core(tree):
    """packages/core.yaml with the host's stand-ins: no debug component, Wi-Fi or Wi-Fi sensors, a fixed IP text, the
    host's clock, and LVGL's snapshot for the render action."""
    text = (tree / 'packages' / 'core.yaml').read_text()
    # Keep the complete production boot action. Adding a list in another package
    # would replace its shorthand mapping instead of appending an automation.
    def offscreen_boot(match):
        original = ''.join('  ' + line if line.strip() else line for line in match[1].splitlines(keepends=True))
        original = original.replace('      priority:', '    - priority:', 1)
        return ('  on_boot:\n    - priority: 1000\n      then:\n'
                '        - lambda: id(my_display).set_headless(true);\n' + original)
    text, n = re.subn(r'(?m)^  on_boot:\n((?:^    [^\n]*\n|^\n)+)', offscreen_boot, text, count=1)
    if n != 1:
        shape_error('esphome.on_boot of packages/core.yaml')
    text, _ = drop_blocks(text, 'debug')
    text, _ = drop_blocks(text, 'wifi')
    text = drop_items(text, 'sensor', lambda item: re.match(r'  - platform: (debug|wifi_signal)\b', item))
    text, n = re.subn(r'(?m)^  - platform: wifi_info\n(?:    #[^\n]*\n)*    ip_address:\n(?:      #[^\n]*\n)*      id: (\w+)\n'
                      r'      name: "IP address"\n      entity_category: diagnostic\n',
                      lambda m: f'  - platform: template\n    id: {m.group(1)}\n    name: "IP address"\n'
                                f'    entity_category: diagnostic\n    lambda: \'return {{"127.0.0.1"}};\'\n', text)
    if n != 1:
        shape_error('the wifi_info IP sensor of packages/core.yaml')
    text, n = re.subn(r'(?m)^time:\n  - platform: homeassistant\n', 'time:\n  - platform: host\n    timezone: Europe/Amsterdam\n', text)
    if n != 1:
        shape_error('the homeassistant time of packages/core.yaml')
    text = host_common(text)
    if '-DLV_USE_SNAPSHOT=1' not in text:
        text, n = re.subn(r'(?m)^(  platformio_options:\n    build_flags:\n)', r'\1      - -DLV_USE_SNAPSHOT=1\n', text, count=1)
        if n != 1:
            shape_error('esphome.platformio_options.build_flags of packages/core.yaml')
    # KEPT_PAGES_HOST=1: the host program keeps and prepares its pages as a board with PSRAM does (docs/KEPT_PAGES.md).
    # Its renders must match a run without it pixel for pixel: tools/compare_renders.py over the two outputs.
    if os.environ.get('KEPT_PAGES_HOST') == '1':
        text = re.sub(r'(?m)^(  platformio_options:\n    build_flags:\n)', r'\1      - -DKEPT_PAGES_HOST=1\n', text, count=1)
    return text


@dataclass
class Chain:
    """What the walk of one board's include tree found: the ids the host stand-ins must carry."""
    outputs: list = field(default_factory=list)
    displays: list = field(default_factory=list)
    touches: list = field(default_factory=list)
    files: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    touch_interval: str = ''  # how often the board reads its touch panel; the SDL one is read as often


def host_file(text, chain, rel):
    """One package of the chain (board file, hardware, look, feature, cells) without its ESP32 hardware."""
    for key in HARDWARE_BLOCKS:
        text, removed = drop_blocks(text, key)
        for block in removed:
            if key == 'display':
                chain.displays += re.findall(r'(?m)^    id: (\w+)', block)
            chain.notes.append(f'{rel}: dropped {key}:')
    text, removed = drop_blocks(text, 'output')
    for block in removed:
        ids = re.findall(r'(?m)^    id: (\w+)', block)
        chain.outputs += ids
        chain.notes.append(f'{rel}: dropped output: ({", ".join(ids)})')
    # A board's or a hardware file's own touch panel (it has a platform) goes; a feature's `!extend` stays, less the
    # resistive panel's raw range (the SDL touchscreen reports pixels).
    changes = []
    for key, start, end in top_blocks(text):
        if key != 'touchscreen':
            continue
        block = text[start:end]
        if re.search(r'(?m)^  (- )?platform:', block):
            chain.touches += re.findall(r'(?m)^  (?:- )?id: (\w+)', block) + re.findall(r'(?m)^    id: (\w+)', block)
            interval = re.search(r'(?m)^    update_interval: (\S+)', block)
            if interval:
                chain.touch_interval = interval[1]
            changes.append((start, end, ''))
            chain.notes.append(f'{rel}: dropped touchscreen: platform')
        elif 'calibration:' in block:
            changes.append((start, end, drop_sub(block, 4, 'calibration')))
    for start, end, new in reversed(changes):
        text = text[:start] + new + text[end:]
    # Boot steps that talk to an I2C expander (a panel's setup lines on some Waveshare boards).
    for key, start, end in blocks_of(text, 'esphome'):
        block = text[start:end]
        if 'id(expander)' in block:
            block = drop_sub(block, 2, 'on_boot')
            if 'id(expander)' in block:
                raise SystemExit(f'{rel}: esphome: still talks to the expander outside on_boot')
            text = text[:start] + ('' if not re.search(r'(?m)^  [a-z_0-9]+:', block) else block) + text[end:]
            chain.notes.append(f'{rel}: dropped esphome.on_boot (expander)')
            break
    text = re.sub(r'(?m)^  hardware_uart: \w+\n', '', text)
    return host_common(text)


INCLUDE = re.compile(r'!include\s+([^\s{}]+\.yaml)')


def walk(tree, source, mirror, chain):
    """Write the host copy of `source` (a file under tree/packages) at the same place under `mirror`, then of every
    file it includes."""
    rel = source.relative_to(tree / 'packages')
    if rel in chain.files:
        return
    chain.files.append(rel)
    text = source.read_text()
    for include in INCLUDE.findall(text):
        target = (source.parent / include).resolve()
        if not target.is_file():
            raise SystemExit(f'{rel}: include {include} does not exist in {tree}')
        if tree / 'packages' not in target.parents:
            raise SystemExit(f'{rel}: include {include} leaves packages/; the mirror cannot follow it')
        walk(tree, target, mirror, chain)
    host = host_file(text, chain, rel)
    if not top_blocks(host):
        host += '\n# Nothing of this file runs on the host.\n{}\n'
    (mirror / rel).parent.mkdir(parents=True, exist_ok=True)
    (mirror / rel).write_text(host)


def host_hw(board_text, chain):
    """The host stand-ins for the hardware the walk took out."""
    size = {key: re.search(rf'(?m)^  {key}: "?(\d+)"?', board_text) for key in ('PANEL_W', 'PANEL_H')}
    if not all(size.values()):
        raise SystemExit('the board file names no numeric PANEL_W / PANEL_H')
    displays, touches = sorted(set(chain.displays)) or ['my_display'], sorted(set(chain.touches)) or ['ts_touch']
    if len(displays) != 1 or len(touches) != 1:
        raise SystemExit(f'expected one display and one touchscreen in the chain, found {displays} and {touches}')
    text = f'''# Host stand-ins for the board's hardware (tools/render/host.py): the panel's own pixels on an offscreen SDL surface.
display:
  - platform: sdl
    id: {displays[0]}
    dimensions:
      width: {size["PANEL_W"][1]}
      height: {size["PANEL_H"][1]}
    auto_clear_enabled: false
    update_interval: never

touchscreen:
  - platform: sdl
    id: {touches[0]}
    display: {displays[0]}
'''
    # Read as often as the board reads its own touch panel: LVGL's swipe counts movement between reads, so a panel
    # read more slowly than the real one would make a finger look like it stops.
    if chain.touch_interval:
        text += f'    update_interval: {chain.touch_interval}\n'
    outputs = list(dict.fromkeys(chain.outputs))
    if outputs:
        text += '\noutput:\n' + ''.join(f"  - platform: template\n    id: {i}\n    type: float\n    write_action:\n"
                                        f"      - lambda: ''\n" for i in outputs)
    return text


# The actions tools/render/run.py drives the program with: a PNG of what LVGL draws (the top layer blended in), whether
# the page is placed and drawn, a page by number, a fixed clock so every render shows the same time, and a live picture
# asked for again (tools/render/camera_tiles.py).
ACTIONS = '''    - action: render_live_reset
      then:
        - lambda: |-
            runtime_tiles::live_wish = runtime_tiles::LiveWish{};
            runtime_tiles::live_release();
            ESP_LOGI("render", "live reset");
    - action: render_png
      variables:
        path: string
      then:
        - lambda: |-
            lv_obj_update_layout(lv_screen_active());
            lv_draw_buf_t *base = lv_snapshot_take(lv_screen_active(), LV_COLOR_FORMAT_RGB888);
            lv_draw_buf_t *top = lv_snapshot_take(lv_layer_top(), LV_COLOR_FORMAT_ARGB8888);
            if (!base) { ESP_LOGE("render", "snapshot failed"); return; }
            std::string part = path + ".part";
            FILE *f = fopen(part.c_str(), "wb");
            int w = base->header.w, h = base->header.h;
            fprintf(f, "P6\\n%d %d\\n255\\n", w, h);
            for (int y = 0; y < h; ++y) {
              const uint8_t *row = base->data + y * base->header.stride;
              const uint8_t *over = top ? top->data + y * top->header.stride : nullptr;
              for (int x = 0; x < w; ++x) {
                int b = row[x * 3], g = row[x * 3 + 1], r = row[x * 3 + 2];
                if (over) {
                  int a = over[x * 4 + 3];
                  b = (over[x * 4] * a + b * (255 - a)) / 255;
                  g = (over[x * 4 + 1] * a + g * (255 - a)) / 255;
                  r = (over[x * 4 + 2] * a + r * (255 - a)) / 255;
                }
                uint8_t px[3] = {(uint8_t) r, (uint8_t) g, (uint8_t) b};
                fwrite(px, 1, 3, f);
              }
            }
            fclose(f);
            rename(part.c_str(), path.c_str());
            lv_draw_buf_destroy(base);
            if (top) lv_draw_buf_destroy(top);
            ESP_LOGI("render", "saved %s", path.c_str());
    - action: render_appearance_probe
      variables:
        control: int
      then:
        - lambda: |-
            if (control > 0) runtime_tiles::show_detail(0);
            if (control < 0) id(close_cards).execute();
            ESP_LOGI("render", "appearance tiles=%p pages=%p detail=%p active=%d visible=%d title=[%s] name=[%s] blue=%d",
                     runtime_tiles::model.tiles.begin(), runtime_tiles::model.page_data.records.begin(), runtime_tiles::detail_root,
                     runtime_tiles::active_index, runtime_tiles::detail_root && !lv_obj_has_flag(runtime_tiles::detail_root, LV_OBJ_FLAG_HIDDEN),
                     runtime_tiles::model.title.c_str(), runtime_tiles::model.tiles[0].name.c_str(),
                     runtime_tiles::model.tiles[0].background == tile_palette::color("blue"));
    - action: render_probe
      then:
        - lambda: |-
            int shown = 0;
            for (auto &w : runtime_tiles::widgets)
              if (w.tile && !lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN)) ++shown;
            ESP_LOGI("render", "probe page=%d applied=%d shown=%d tiles=%u alert=%d pages=%d", (int) id(tile_page),
                     runtime_tiles::applied_page, shown, (unsigned) runtime_tiles::model.count, (int) id(alert_active),
                     (int) runtime_tiles::page_count());
    - action: render_page
      variables:
        page: int
      then:
        - lambda: |-
            id(tile_page) = page;
            runtime_tiles::show_page(id(tile_page), id(page_prev), id(page_next), id(page_number));
    - action: render_time
      variables:
        epoch: int
      then:
        - lambda: |-
            auto fixed = esphome::ESPTime::from_epoch_local((time_t) epoch);
            runtime_tiles::now_time = [fixed]() { return fixed; };
            if (!id(ui_refresh).is_running()) id(ui_refresh).execute();
'''
# What a finger does and what is on the glass in the moment after it, for the checks that must look into that moment
# instead of at the page once it has settled (the top bar's name in dots for a second after a page change, GitHub #27;
# an alert card before and after its picture arrives): a second pointer whose point and state the driver sets, and one
# log line with the page title as the label shows it and every part of the alert card where LVGL placed it.
PROBES = '''    - action: render_finger
      variables:
        x: int
        y: int
        down: bool
      then:
        - lambda: |-
            // A finger on the SDL touchscreen, so it takes the path a finger on the glass takes: ESPHome's touchscreen
            // (its transform, on_update and on_release, the touch guard, the page swipe) and LVGL after it. The point
            // (x, y) of the screen goes back through the turn ESPHome's LVGL gives a touch (LvglComponent::
            // rotate_coordinates, LVGL_ROTATION) to the panel's pixels, and back through the board's touch transform
            // (TOUCH_SWAP_XY, TOUCH_MIRROR_X, TOUCH_MIRROR_Y) to what its touch controller would report.
            auto *sdl = id(my_display);
            const int w = sdl->get_width(), h = sdl->get_height();
            int nx = x, ny = y;
            switch ((int) id(screen_lvgl).get_rotation()) {
              case 90: nx = w - y - 1; ny = x; break;
              case 180: nx = w - x - 1; ny = h - y - 1; break;
              case 270: nx = y; ny = h - x - 1; break;
              default: break;
            }
            const int ax = ${TOUCH_MIRROR_X} ? w - 1 - nx : nx, ay = ${TOUCH_MIRROR_Y} ? h - 1 - ny : ny;
            sdl->mouse_x = ${TOUCH_SWAP_XY} ? ay : ax;
            sdl->mouse_y = ${TOUCH_SWAP_XY} ? ax : ay;
            sdl->mouse_down = down;
    - action: render_offline_swipe
      variables:
        forward: bool
      then:
        - lambda: |-
            id(render_offline_verified) = false;
            auto *sdl = id(my_display);
            sdl->set_timeout("offline-start", 1000, [sdl, forward]() {
              id(render_offline_verified) = !runtime_tiles::ha_connected();
              const uint32_t start = esphome::millis();
              sdl->set_interval("offline-finger", 5, [sdl, forward, start]() {
                id(render_offline_verified) &= !runtime_tiles::ha_connected();
                const uint32_t elapsed = esphome::millis() - start;
                const float progress = std::min(1.0f, elapsed < 150 ? 0.0f : (elapsed - 150) / 180.0f);
                const int w = sdl->get_width(), h = sdl->get_height();
                const int cw = lv_display_get_horizontal_resolution(lv_display_get_default());
                const int ch = lv_display_get_vertical_resolution(lv_display_get_default());
                const int x = cw * (forward ? 0.99f - 0.69f * progress : 0.01f + 0.69f * progress);
                const int y = ch * 0.6f;
                int nx = x, ny = y;
                switch ((int) id(screen_lvgl).get_rotation()) {
                  case 90: nx = w - y - 1; ny = x; break;
                  case 180: nx = w - x - 1; ny = h - y - 1; break;
                  case 270: nx = y; ny = h - x - 1; break;
                  default: break;
                }
                const int ax = ${TOUCH_MIRROR_X} ? w - 1 - nx : nx, ay = ${TOUCH_MIRROR_Y} ? h - 1 - ny : ny;
                sdl->mouse_x = ${TOUCH_SWAP_XY} ? ay : ax;
                sdl->mouse_y = ${TOUCH_SWAP_XY} ? ax : ay;
                sdl->mouse_down = elapsed < 335;
                if (elapsed >= 335) sdl->cancel_interval("offline-finger");
              });
            });
    - action: render_offline_result
      then:
        - lambda: 'ESP_LOGI("render", "offline verified=%d", (int) id(render_offline_verified));'
    - action: render_navigation
      then:
        - lambda: |-
            lv_obj_update_layout(lv_screen_active());
            auto center = [](lv_obj_t *o) {
              lv_area_t a{0, 0, -2, -2};
              if (o && !lv_obj_has_flag(o, LV_OBJ_FLAG_HIDDEN)) lv_obj_get_coords(o, &a);
              return lv_point_t{(lv_coord_t)((a.x1+a.x2)/2), (lv_coord_t)((a.y1+a.y2)/2)};
            };
            const auto tile = center(runtime_tiles::widgets[0].tile), prev = center(id(page_prev)),
                       header = center(runtime_tiles::header_renderer.leading_target());
            lv_font_glyph_dsc_t house{}, chevron{};
            lv_font_get_glyph_dsc(runtime_tiles::header_home_font, &house, 0xF02DC, 0);
            lv_font_get_glyph_dsc(runtime_tiles::header_back_font, &chevron, 0xF0141, 0);
            ESP_LOGI("render", "leading heights home=%u back=%u", (unsigned) house.box_h, (unsigned) chevron.box_h);
            ESP_LOGI("render", "navigation page=%d footer=%d back=%d grid_height=%d tile=%d,%d prev=%d,%d header=%d,%d",
                     (int) id(tile_page), (int) runtime_tiles::applied_bar, (int) runtime_tiles::header_back(),
                     (int) lv_obj_get_height(id(tile_scroll)), (int) tile.x, (int) tile.y,
                     (int) prev.x, (int) prev.y, (int) header.x, (int) header.y);
    - action: render_problem
      then:
        - lambda: |-
            lv_obj_update_layout(lv_screen_active());
            auto *panel = runtime_tiles::boot_panel;
            bool covers = false;
            if (panel) {
              lv_area_t a, b; lv_obj_get_coords(panel, &a); lv_obj_get_coords(lv_obj_get_parent(panel), &b);
              covers = a.x1 <= b.x1 && a.y1 <= b.y1 && a.x2 >= b.x2 && a.y2 >= b.y2
                       && lv_obj_get_style_bg_opa(panel, LV_PART_MAIN) == LV_OPA_COVER
                       && lv_obj_has_flag(panel, LV_OBJ_FLAG_CLICKABLE)
                       && lv_obj_get_index(panel) == lv_obj_get_child_count(lv_obj_get_parent(panel)) - 1;
              ESP_LOGI("render", "problem bounds=%d,%d,%d,%d parent=%d,%d,%d,%d opaque=%u index=%ld children=%u clickable=%d",
                       (int)a.x1, (int)a.y1, (int)a.x2, (int)a.y2, (int)b.x1, (int)b.y1, (int)b.x2, (int)b.y2,
                       (unsigned)lv_obj_get_style_bg_opa(panel, LV_PART_MAIN), (long)lv_obj_get_index(panel),
                       (unsigned)lv_obj_get_child_count(lv_obj_get_parent(panel)), (int)lv_obj_has_flag(panel, LV_OBJ_FLAG_CLICKABLE));
            }
            ESP_LOGI("render", "problem=%u covers=%d spinner=%d", (unsigned) runtime_tiles::protocol_problem,
                     (int) covers, (int) (runtime_tiles::boot_spinner && !lv_obj_has_flag(runtime_tiles::boot_spinner, LV_OBJ_FLAG_HIDDEN)));
    - action: render_state
      then:
        - lambda: |-
            lv_obj_update_layout(lv_screen_active());
            auto box = [](lv_obj_t *o) {
              lv_area_t a{0, 0, -1, -1};
              if (o && !lv_obj_has_flag(o, LV_OBJ_FLAG_HIDDEN)) lv_obj_get_coords(o, &a);
              return a;
            };
            auto *room = runtime_tiles::room_label;
            const lv_area_t name = box(room);
            ESP_LOGI("render", "state page=%d name=[%s] shown=[%s] name_box=%d,%d,%d,%d", (int) id(tile_page),
                     runtime_tiles::header_name.c_str(), room ? lv_label_get_text(room) : "", (int) name.x1, (int) name.y1,
                     (int) name.x2, (int) name.y2);
            const auto &p = runtime_tiles::alert_parts;
            const bool on = id(alert_active) && p.card && !lv_obj_has_flag(lv_obj_get_parent(p.card), LV_OBJ_FLAG_HIDDEN);
            const lv_area_t card = box(p.card), frame = box(runtime_tiles::alert_frame), icon = box(p.icon), title = box(p.title),
                            subtitle = box(p.subtitle), button = box(p.button), button2 = box(p.button2);
            ESP_LOGI("render", "alert on=%d card=%d,%d,%d,%d frame=%d,%d,%d,%d icon=%d,%d,%d,%d title=%d,%d,%d,%d "
                     "subtitle=%d,%d,%d,%d button=%d,%d,%d,%d button2=%d,%d,%d,%d picture=%d", (int) on,
                     (int) card.x1, (int) card.y1, (int) card.x2, (int) card.y2, (int) frame.x1, (int) frame.y1, (int) frame.x2,
                     (int) frame.y2, (int) icon.x1, (int) icon.y1, (int) icon.x2, (int) icon.y2, (int) title.x1, (int) title.y1,
                     (int) title.x2, (int) title.y2, (int) subtitle.x1, (int) subtitle.y1, (int) subtitle.x2, (int) subtitle.y2,
                     (int) button.x1, (int) button.y1, (int) button.x2, (int) button.y2,
                     (int) button2.x1, (int) button2.y1, (int) button2.x2, (int) button2.y2, (int) (runtime_tiles::alert_picture != nullptr));
'''
# The alarm panel's card as it stands (firmware 0.3.3+): whether it is open, the keypad, what its lines say, the centre
# of every key a finger uses (the back key, the mode or Disarm keys in their order, the keypad's twelve), and every part
# of the card that does not lie inside the glass or that lies over another key.
ALARM_PROBE = '''    - action: render_alarm
      then:
        - lambda: |-
            using namespace runtime_tiles;
            lv_obj_update_layout(lv_screen_active());
            const bool open = detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN);
            auto centre = [](lv_obj_t *o) {
              lv_area_t a; lv_obj_get_coords(o, &a);
              return std::to_string((a.x1 + a.x2) / 2) + "," + std::to_string((a.y1 + a.y2) / 2);
            };
            std::string modes, keys, faults;
            const int sw = lv_display_get_horizontal_resolution(lv_display_get_default()),
                      sh = lv_display_get_vertical_resolution(lv_display_get_default());
            std::vector<lv_area_t> hits;
            auto check = [&](lv_obj_t *o, const char *what) {
              lv_area_t a; lv_obj_get_coords(o, &a);
              if (a.x1 < 0 || a.y1 < 0 || a.x2 >= sw || a.y2 >= sh) faults += std::string(what) + " outside;";
              for (auto &b : hits) if (a.x1 <= b.x2 && b.x1 <= a.x2 && a.y1 <= b.y2 && b.y1 <= a.y2) faults += std::string(what) + " overlaps;";
              hits.push_back(a);
            };
            if (open) {
              lv_obj_t *back = lv_obj_get_child(detail_root, 0);
              check(back, "back");
              for (unsigned i = 0; i < detail_action_count; ++i) { modes += centre(detail_actions[i]) + ";"; check(detail_actions[i], "mode"); }
              for (auto *k : alarm_keys) if (k) { keys += centre(k) + std::string(lv_obj_has_state(k, LV_STATE_DISABLED) ? "d;" : ";"); check(k, "key"); }
              for (uint32_t i = 0; i < lv_obj_get_child_count(detail_root); ++i) {
                lv_area_t a; lv_obj_get_coords(lv_obj_get_child(detail_root, i), &a);
                if (a.x1 < 0 || a.y1 < 0 || a.x2 >= sw || a.y2 >= sh) faults += "part " + std::to_string(i) + " outside;";
              }
              ESP_LOGI("render", "alarm open=%d pad=%d back=%s title=[%s] status=[%s] line=[%s] modes=%s keys=%s faults=%s locked=%u",
                       (int) open, (int) alarm_pad_open(), centre(back).c_str(),
                       lv_label_get_text(lv_obj_get_child(detail_root, 1)), detail_status ? lv_label_get_text(detail_status) : "",
                       alarm_line ? lv_label_get_text(alarm_line) : "", modes.c_str(), keys.c_str(), faults.c_str(),
                       (unsigned) alarm_lock.remaining_s(esphome::millis()));
            } else {
              ESP_LOGI("render", "alarm open=0 pad=0 back= title=[] status=[] line=[] modes= keys= faults= locked=%u",
                       (unsigned) alarm_lock.remaining_s(esphome::millis()));
            }
'''
# A board with the calibration wizard shows it on the first start; the renders skip it, as a calibrated screen does.
SKIP_CALIBRATION = '''    - action: render_skip_calibration
      then:
        - lambda: |-
            if (!screen_calibration::active) return;
            screen_calibration::active = false;
            if (screen_calibration::isolation) screen_calibration::isolation(false);
            lv_screen_load(screen_calibration::home);
'''


class Build:
    """The host build of one variant of one tree, under `work` (the tree's own .esphome/render/ by default)."""

    def __init__(self, item, tree=REPO, work=None, esphome=('esphome',)):
        self.variant, self.tree = item, Path(tree).resolve()
        self.work = Path(work or REPO / '.esphome' / 'render' / 'build').resolve()
        self.esphome = list(esphome)  # the command, which may be more than one word ('python -m esphome')

    @property
    def program(self):
        name = self.variant.name
        return self.work / '.esphome' / 'build' / name / '.pioenvs' / name / 'program'

    def components(self):
        """This tree's smart_display component as links, so ESPHome builds the C++ of the tree being rendered."""
        target = self.work / 'components' / 'smart_display'
        shutil.rmtree(self.work / 'components', ignore_errors=True)
        target.mkdir(parents=True)
        for source in (self.tree / 'components' / 'smart_display').iterdir():
            if source.name != '__pycache__':
                (target / source.name).symlink_to(source)

    def package(self):
        """Write the host mirror of this variant's chain; returns the host package's text."""
        item, tree = self.variant, self.tree
        mirror_root = self.work / 'host' / item.key
        shutil.rmtree(mirror_root, ignore_errors=True)
        mirror = mirror_root / 'packages'
        mirror.mkdir(parents=True)
        (mirror / 'core.yaml').write_text(host_core(tree))
        chain = Chain()
        board = tree / 'packages' / 'boards' / item.file
        if not board.is_file():
            raise SystemExit(f'{tree} has no packages/boards/{item.file}')
        walk(tree, board, mirror, chain)
        (mirror_root / 'host-hw.yaml').write_text(host_hw(board.read_text(), chain))
        (mirror_root / 'chain.txt').write_text('\n'.join([str(f) for f in chain.files] + [''] + chain.notes) + '\n')
        chain_text = ''.join((mirror / f).read_text() for f in chain.files)
        actions = ACTIONS + PROBES + ALARM_PROBE + (SKIP_CALIBRATION if 'screen_calibration::' in chain_text else '')
        turned = f'\n  LVGL_ROTATION: "{item.rotation}"' if item.rotation else ''
        rel = f'host/{item.key}'
        return f'''# Host build of {item.key} from {tree} (tools/render/host.py): core and board chain, hardware swapped for SDL.
substitutions:
  FONT_DIR: "{tree / 'fonts'}"{turned}

packages:
  core: !include {rel}/packages/core.yaml
  board: !include {rel}/packages/boards/{item.file}
  host_hw: !include {rel}/host-hw.yaml

external_components:
  - source:
      type: local
      path: components
    components: [smart_display]

globals:
  - id: render_offline_verified
    type: bool
    initial_value: 'false'

api:
  port: {item.port}
  actions:
{actions}'''

    def config(self):
        """Write the host package and the config that includes it; returns the config's path."""
        name = self.variant.name
        (self.work / f'{name}-package.yaml').write_text(self.package())
        path = self.work / f'{name}.yaml'
        path.write_text(f'substitutions:\n  DEVICE_NAME: "{name}"\n  DEVICE_FRIENDLY_NAME: "{self.variant.key} screen"\n'
                        f'packages:\n  display: !include {name}-package.yaml\nhost:\n')
        return path

    def compile(self):
        """Compile the program; returns (ok, the compiler's output)."""
        self.work.mkdir(parents=True, exist_ok=True)
        self.components()
        path = self.config()
        result = subprocess.run([*self.esphome, 'compile', str(path)], capture_output=True, text=True, cwd=self.work)
        output = result.stdout + result.stderr
        (self.work / 'logs').mkdir(exist_ok=True)
        (self.work / 'logs' / f'compile-{self.variant.name}.log').write_text(output)
        return result.returncode == 0 and 'Successfully compiled' in output, output
