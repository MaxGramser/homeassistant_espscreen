#pragma once
// The colour card's three rows: a light's colour, white shade and brightness (firmware 0.2.80+). Since dev the card is
// built the way the pages over a card are (group_page.h, effects_page.h): made when it opens and thrown away when it
// closes (runtime_tiles::colour_open, colour_close), painted from the light's tile on every change (paint), and a
// slider let go is a wish the runtime makes through `commits` (docs/OPTIMISTIC.md). It keeps no state of Home Assistant
// of its own. The values part stays free of LVGL for tests/test_light_controls.cpp.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include "screen_text.h"
#include "ui_scale.h"

namespace light_controls {
inline int clamp(int value, int low, int high) { return std::max(low, std::min(high, value)); }
// What the rows show: the light as its tile holds it, a wish included. `color` and `temperature` say which of the
// first two rows it has (its colour modes); brightness is 0 while it is off.
struct Values {
  int hue = 0, kelvin = 3000, minimum = 0, maximum = 0, brightness = 0;
  bool color = false, temperature = false;
  // A white-shade slider needs the light's own range; until Home Assistant names it the row waits.
  bool temperature_ready() const { return minimum >= 1000 && maximum <= 15000 && maximum > minimum; }
  // Which rows show and where: what decides whether the card is laid out again.
  bool same_rows(const Values &o) const { return color == o.color && temperature == o.temperature; }
};
}

#ifndef LIGHT_CONTROLS_TEST
#include "esphome/core/log.h"
#include "lvgl.h"
#include "screen_input.h"
#include "theme.h"
#include <functional>
namespace light_controls {
struct Row { lv_obj_t *box{}, *slider{}, *value{}, *icon{}; bool dirty = false; unsigned index{}; bool off = false; int held = 0; };
inline Row rows[3];
// The card the rows stand on: a hand's width, in the middle of the overlay that covers the glass.
inline lv_obj_t *card = nullptr;
inline std::function<void(int)> commits[3];
inline bool demo = false;
// What the rows show now (paint): a white shade let go is held to the light's own range.
inline Values shown;
// Where the three rows start, their pitch, the gap between them and the height of the glass they were built
// for: place() puts the rows that show in the middle of the room under the title with them.
inline int top, spacing, row_gap, glass_h;
// Rows a card adds under the three (a light's presets, module light_presets): counted when the rows share the room, and
// the place and size of a row, for the card to draw its own in the same shape (place() returns where it goes).
inline int extra = 0;
inline int row_x = 0, row_w = 0, row_h = 0, row_inset = 0, row_text_y = 0;
// A row's own white card, as each of the three has one (a change of look builds the card again).
inline lv_obj_t *row_card(lv_obj_t *parent, int x, int y, int w, int h) {
  auto *box = lv_obj_create(parent);
  lv_obj_remove_style_all(box);
  lv_obj_remove_flag(box, static_cast<lv_obj_flag_t>(LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE));
  lv_obj_set_pos(box, x, y); lv_obj_set_size(box, w, h);
  lv_obj_set_style_bg_opa(box, LV_OPA_COVER, 0);
  lv_obj_set_style_radius(box, ui::px(ui::large() ? 18 : 10), 0);
  lv_obj_set_style_border_width(box, 1, 0);
  lv_obj_set_style_bg_color(box, theme::color(theme::CARD), 0);
  lv_obj_set_style_border_color(box, theme::color(theme::LINE), 0);
  return box;
}
// The picker's own spectrum: the colours a light can take, not a look, so they stay the same in dark.
constexpr uint32_t WARM = 0xFF9C32, COOL = 0xC6E6FF;
inline constexpr uint32_t RAINBOW[] = {0xFF0000, 0xFFFF00, 0x00FF00, 0x00FFFF, 0x0000FF, 0xFF00FF, 0xFF0000};
// Temperature knob colour: the same warm-to-cool blend as the track under it.
inline lv_color_t kelvin_color(int value, int low, int high) {
  int mix = high > low ? clamp((value - low) * 255 / (high - low), 0, 255) : 128;
  return lv_color_hex(theme::mix(COOL, WARM, static_cast<uint8_t>(mix)));
}
inline void preview(Row &row) {
  int value = lv_slider_get_value(row.slider);
  if (row.index == 0) {
    lv_label_set_text_fmt(row.value, "%d°", value);
    lv_obj_set_style_bg_color(row.slider, lv_color_hsv_to_rgb(clamp(value, 0, 360) % 360, 100, 100), LV_PART_KNOB);
  } else if (row.index == 1) {
    lv_label_set_text_fmt(row.value, "%d K", value);
    lv_obj_set_style_bg_color(row.slider, kelvin_color(value, lv_slider_get_min_value(row.slider), lv_slider_get_max_value(row.slider)), LV_PART_KNOB);
  } else {
    // The range reaches below 1 only to draw the short stub that holds the handle at 1 %.
    if (value < 1) { lv_slider_set_value(row.slider, 1, LV_ANIM_OFF); value = 1; }
    // An off light shows only the track, as in Home Assistant, until the slider moves.
    lv_obj_set_style_bg_opa(row.slider, row.off ? LV_OPA_TRANSP : LV_OPA_COVER, LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(row.slider, row.off ? LV_OPA_TRANSP : LV_OPA_COVER, LV_PART_KNOB);
    lv_obj_set_style_bg_color(row.slider, theme::color(row.off ? theme::TRACK : theme::AMBER_TRACK), LV_PART_MAIN);
    if (row.off) lv_label_set_text(row.value, screen_text::tr(screen_text::txt::ha_off));
    else lv_label_set_text(row.value, screen_text::percent(value).c_str());
  }
}
inline void event(lv_event_t *e) {
  auto &row = *static_cast<Row *>(lv_event_get_user_data(e));
  auto code = lv_event_get_code(e);
  if (code == LV_EVENT_VALUE_CHANGED) {
    // On release LVGL sets the value once more from the last touch point; say so when that throws
    // a dragged slider to one of its ends, so a stray touch sample shows up in the log.
    auto *indev = lv_indev_active();
    const int value = lv_slider_get_value(row.slider);
    if (!indev || lv_indev_get_state(indev) != LV_INDEV_STATE_RELEASED) row.held = value;
    else if (row.dirty && screen_input::release_jump(row.held, value, lv_slider_get_min_value(row.slider), lv_slider_get_max_value(row.slider))) {
      static const char *const names[] = {"Color", "Color temperature", "Brightness"};
      lv_point_t point;
      lv_indev_get_point(indev, &point);
      ESP_LOGW("slider", "%s slider jumped on release: %d -> %d (touch x=%d y=%d)", names[row.index], row.held, value, (int) point.x, (int) point.y);
    }
    row.dirty = true; row.off = false; preview(row);
  }
  if (code == LV_EVENT_PRESS_LOST) row.dirty = false;
  if (code == LV_EVENT_RELEASED && row.dirty) {
    row.dirty = false;
    // A finger let go within the edge band of the glass meant the slider's end (screen_input::edge_snap).
    if (auto *indev = lv_indev_active()) {
      lv_point_t p;
      lv_indev_get_point(indev, &p);
      lv_area_t a;
      lv_obj_get_coords(row.slider, &a);
      const int screen = lv_display_get_horizontal_resolution(lv_obj_get_display(row.slider));
      const int snap = screen_input::edge_snap(p.x, a.x1, a.x2, screen, screen_input::edge_snap_band);
      if (snap) {
        const int end = snap > 0 ? lv_slider_get_max_value(row.slider) : lv_slider_get_min_value(row.slider);
        ESP_LOGI("slider", "Let go %d px from the %s edge: slider %d -> %d", snap > 0 ? screen - 1 - (int) p.x : (int) p.x, snap > 0 ? "right" : "left", (int) lv_slider_get_value(row.slider), end);
        lv_slider_set_value(row.slider, end, LV_ANIM_OFF);
        preview(row);
      }
    }
    int value = lv_slider_get_value(row.slider);
    if (row.index == 1) {
      if (!shown.temperature_ready()) return;
      value = clamp(value, shown.minimum, shown.maximum);
    }
    if (row.index == 2) value = clamp(value, 1, 100);
    if (!demo && commits[row.index]) commits[row.index](value);
  }
}
inline lv_obj_t *plain(lv_obj_t *parent, int x, int y, int w, int h) {
  auto *obj = lv_obj_create(parent);
  lv_obj_remove_style_all(obj);
  lv_obj_remove_flag(obj, static_cast<lv_obj_flag_t>(LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE));
  lv_obj_set_pos(obj, x, y); lv_obj_set_size(obj, w, h);
  return obj;
}
inline lv_obj_t *round_end(lv_obj_t *parent, int x, int y, int size, uint32_t color) {
  auto *end = plain(parent, x, y, size, size);
  lv_obj_set_style_radius(end, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_opa(end, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(end, lv_color_hex(color), 0);
  return end;
}
// The colours of a row's card, set when it is built (a change of look builds the card again).
inline void colours(Row &row) {
  lv_obj_set_style_bg_color(row.box, theme::color(theme::CARD), 0);
  lv_obj_set_style_border_color(row.box, theme::color(theme::LINE), 0);
  lv_obj_set_style_text_color(row.box, theme::color(theme::INK), 0);
  lv_obj_set_style_text_color(row.value, theme::color(theme::MUTED), 0);
  if (row.icon) lv_obj_set_style_text_color(row.icon, theme::color(theme::MUTED), 0);
  if (row.index < 2) lv_obj_set_style_border_color(row.slider, theme::color(theme::KNOB), LV_PART_KNOB);
  else lv_obj_set_style_bg_color(row.slider, theme::color(theme::KNOB), LV_PART_KNOB);
}
// Three white cards like the tiles: an icon, the name and the value, then a pill-shaped track.
// Colour and temperature are gradient pills with a round knob in the chosen colour; brightness
// is filled like the tile sliders, with the white handle inside the fill.
//
// `width` is the card's room, not the glass: a hue slider is dragged, so it keeps a hand's width like every
// other control (overlay_card::content_width). The board profile gives this the card it centred on the glass;
// before firmware 0.2.82 it got the whole screen and a ten-inch panel drew three sliders twenty-one
// centimetres wide across the top with two thirds of the glass empty under them.
inline void setup(lv_obj_t *parent, const lv_font_t *font, int width, int height, const lv_font_t *icon_font = nullptr) {
  // The look decides the class, never the glass: a wide panel draws the same rows, only at its own density.
  const bool large = ui::large();
  top = ui::px(large ? 100 : 52);
  // The three rows share the room under the title. A row wants the look's pitch, keeps at least a finger and
  // its words, and the three together never take more than what is left, so the card fits any glass it lands
  // on (a 800 x 480 panel at 217 dpi asked for 122 x 1.28 = 156 px a row and ran off the bottom). Three rows
  // are two pitches and one card: the last row needs no gap under it, which is why the gap counts once more.
  const int wanted = ui::px(large ? 122 : 60), gap = ui::px(large ? 12 : 5);
  const int least = ui::touch_min() + lv_font_get_line_height(font) + ui::px(12);
  const int room = height - top - ui::px(large ? 18 : 8);
  spacing = std::max(least, std::min(wanted, (room + gap) / (3 + extra)));
  row_gap = gap; glass_h = height;
  int margin = ui::px(large ? 20 : 12), w = width - 2 * margin, card_h = spacing - gap;
  int inset = ui::px(large ? 18 : 10), text_y = ui::px(large ? 14 : 5), track_h = ui::px(large ? 32 : 18);
  row_x = margin; row_w = w; row_h = card_h; row_inset = inset; row_text_y = text_y;
  int track_x = inset, track_w = w - 2 * inset, track_y = card_h - inset + (ui::px(large ? 2 : 3)) - track_h;
  // A row squeezed by a short screen keeps its words: the track moves right under them and gets thinner,
  // never thinner than something a finger can still drag.
  const int lowest = text_y + lv_font_get_line_height(font) + ui::px(large ? 6 : 3), foot = ui::px(large ? 8 : 4);
  if (track_y < lowest) {
    track_h = std::max(ui::px(large ? 18 : 10), card_h - lowest - foot);
    track_y = card_h - track_h - foot;
  }
  const int radius = track_h / 2;
  const char *names[] = {screen_text::tr(screen_text::txt::light_color), screen_text::tr(screen_text::txt::light_color_temperature), screen_text::tr(screen_text::txt::light_brightness)};
  const char *icons[] = {"\U000F03D8", "\U000F050F", "\U000F0335"};
  for (unsigned i = 0; i < 3; ++i) {
    auto &row = rows[i]; row.index = i;
    row.box = plain(parent, margin, top + i * spacing, w, card_h);
    lv_obj_set_style_bg_opa(row.box, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(row.box, ui::px(large ? 18 : 10), 0);
    lv_obj_set_style_border_width(row.box, 1, 0);
    lv_obj_set_style_text_font(row.box, font, 0);
    int text_x = inset;
    if (icon_font) {
      auto *icon = row.icon = lv_label_create(row.box); lv_label_set_text(icon, icons[i]);
      lv_obj_set_style_text_font(icon, icon_font, 0);
      int icon_h = lv_font_get_line_height(icon_font), text_h = lv_font_get_line_height(font);
      lv_obj_set_pos(icon, inset - (ui::px(large ? 2 : 1)), text_y + (text_h - icon_h) / 2);
      text_x += icon_h + (ui::px(large ? 6 : 4));
    }
    auto *label = lv_label_create(row.box); lv_label_set_text(label, names[i]);
    lv_obj_set_pos(label, text_x, text_y);
    row.value = lv_label_create(row.box); lv_obj_align(row.value, LV_ALIGN_TOP_RIGHT, -inset, text_y);
    row.slider = lv_slider_create(row.box);
    lv_obj_remove_style_all(row.slider);
    lv_obj_remove_flag(row.slider, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_ext_click_area(row.slider, ui::px(large ? 12 : 8));
    if (i < 2) {
      // The knob travels between the centres of the two round ends.
      round_end(row.box, track_x, track_y, track_h, i == 0 ? RAINBOW[0] : WARM);
      round_end(row.box, track_x + track_w - track_h, track_y, track_h, i == 0 ? RAINBOW[6] : COOL);
      unsigned segments = i == 0 ? 6 : 1;
      int span = track_w - track_h;
      for (unsigned n = 0; n < segments; ++n) {
        int start = n * span / segments, end = (n + 1) * span / segments;
        auto *stripe = plain(row.box, track_x + radius + start, track_y, end - start, track_h);
        lv_obj_set_style_bg_opa(stripe, LV_OPA_COVER, 0);
        lv_obj_set_style_bg_color(stripe, lv_color_hex(i == 0 ? RAINBOW[n] : WARM), 0);
        lv_obj_set_style_bg_grad_color(stripe, lv_color_hex(i == 0 ? RAINBOW[n + 1] : COOL), 0);
        lv_obj_set_style_bg_grad_dir(stripe, LV_GRAD_DIR_HOR, 0);
      }
      lv_obj_move_foreground(row.slider);
      lv_obj_set_pos(row.slider, track_x + radius, track_y); lv_obj_set_size(row.slider, span, track_h);
      lv_obj_set_style_bg_opa(row.slider, LV_OPA_TRANSP, LV_PART_MAIN);
      lv_obj_set_style_bg_opa(row.slider, LV_OPA_TRANSP, LV_PART_INDICATOR);
      lv_obj_set_style_bg_opa(row.slider, LV_OPA_COVER, LV_PART_KNOB);
      lv_obj_set_style_radius(row.slider, LV_RADIUS_CIRCLE, LV_PART_KNOB);
      lv_obj_set_style_pad_all(row.slider, ui::px(large ? 4 : 3), LV_PART_KNOB);
      lv_obj_set_style_border_width(row.slider, ui::px(large ? 4 : 3), LV_PART_KNOB);
      lv_obj_set_style_outline_width(row.slider, 1, LV_PART_KNOB);
      // A faint dark edge that lifts the white ring off a pale end of the track.
      lv_obj_set_style_outline_color(row.slider, lv_color_black(), LV_PART_KNOB);
      lv_obj_set_style_outline_opa(row.slider, LV_OPA_20, LV_PART_KNOB);
      lv_slider_set_range(row.slider, i == 0 ? 0 : 2000, i == 0 ? 360 : 6500);
    } else {
      // Corners, handle and shortest fill as in Home Assistant's 42 px control slider. The fill keeps
      // the track's radius: a smaller one makes LVGL draw the fill into its own full-size buffer on
      // every redraw (20 KB on the CYD) and clip it to the track.
      lv_obj_set_pos(row.slider, track_x, track_y); lv_obj_set_size(row.slider, track_w, track_h);
      int corner = track_h * 12 / 42;
      lv_obj_set_style_radius(row.slider, corner, LV_PART_MAIN);
      lv_obj_set_style_radius(row.slider, corner, LV_PART_INDICATOR);
      lv_obj_set_style_bg_opa(row.slider, LV_OPA_COVER, LV_PART_MAIN);
      lv_obj_set_style_bg_opa(row.slider, LV_OPA_COVER, LV_PART_INDICATOR);
      lv_obj_set_style_bg_color(row.slider, lv_color_hex(theme::ha::AMBER), LV_PART_INDICATOR);
      // White handle inside the end of the fill, as on the tiles (runtime_tiles::slider_handle).
      int handle = ui::px(large ? 4 : 3), back = std::max(1, track_h / 8) + handle / 2, half = track_h >> 1;
      lv_obj_set_style_bg_opa(row.slider, LV_OPA_COVER, LV_PART_KNOB);
      lv_obj_set_style_radius(row.slider, 2, LV_PART_KNOB);
      lv_obj_set_style_pad_left(row.slider, back + handle / 2 - half, LV_PART_KNOB);
      lv_obj_set_style_pad_right(row.slider, handle / 2 - back - (track_h - half), LV_PART_KNOB);
      lv_obj_set_style_pad_top(row.slider, -(track_h / 4), LV_PART_KNOB);
      lv_obj_set_style_pad_bottom(row.slider, -(track_h / 4), LV_PART_KNOB);
      // 1 % still shows a stub a third of the height wide: the range starts that far below 1.
      int stub = std::max(track_h / 3, 2 * std::max(1, track_h / 8) + handle), below = track_w > stub ? 99 * stub / (track_w - stub) : 0;
      lv_slider_set_range(row.slider, 1 - below, 100);
    }
    lv_obj_add_event_cb(row.slider, event, LV_EVENT_ALL, &row);
    colours(row);
    preview(row);
  }
}
// The rows the light has, in the middle of the room under the title, and only when that leaves more than a finger
// over: on a CYD and a Guition three rows already fill the glass, so nothing there moves. The way every card centres
// what it draws (overlay_card::centre).
inline int place(const Values &v) {
  const int showing = (v.color ? 1 : 0) + (v.temperature ? 1 : 0) + 1 + extra;
  const int block = showing * spacing - row_gap;
  const int over = glass_h - top - ui::px(ui::large() ? 18 : 8) - block;
  int y = over > ui::touch_min() ? top + over / 2 : top;
  for (unsigned i = 0; i < 3; ++i) {
    auto &row = rows[i];
    const bool visible = i == 0 ? v.color : i == 1 ? v.temperature : true;
    if (!visible) { lv_obj_add_flag(row.box, LV_OBJ_FLAG_HIDDEN); continue; }
    lv_obj_remove_flag(row.box, LV_OBJ_FLAG_HIDDEN); lv_obj_set_y(row.box, y); y += spacing;
  }
  return y;
}
// The light as it is now: each slider where the tile says, unless a finger holds it or has just let it go (its wish
// is on its way and comes back through the tile). A white shade waits for the light's range; an off light shows only
// the brightness track, as in Home Assistant.
inline void paint(const Values &v, bool fresh_card) {
  shown = v;
  const int values[3] = {clamp(v.hue, 0, 360), v.temperature_ready() ? clamp(v.kelvin, v.minimum, v.maximum) : v.kelvin,
                         clamp(v.brightness, 1, 100)};
  for (unsigned i = 0; i < 3; ++i) {
    auto &row = rows[i];
    if (!row.slider || (!fresh_card && (row.dirty || lv_obj_has_state(row.slider, LV_STATE_PRESSED)))) continue;
    if (i == 1) {
      if (v.temperature_ready()) {
        lv_obj_remove_state(row.slider, LV_STATE_DISABLED);
        lv_slider_set_range(row.slider, v.minimum, v.maximum);
      } else lv_obj_add_state(row.slider, LV_STATE_DISABLED);
    }
    if (lv_slider_get_value(row.slider) != values[i]) lv_slider_set_value(row.slider, values[i], LV_ANIM_OFF);
    row.off = i == 2 && v.brightness <= 0;
    preview(row); row.dirty = false;
    if (i == 1 && !v.temperature_ready()) lv_label_set_text(row.value, screen_text::tr(screen_text::txt::light_waiting));
  }
}
// The card is gone with its page (runtime_tiles::colour_close): nothing here points into it any more.
inline void forget() {
  for (auto &row : rows) row = Row{};
  card = nullptr;
}

}
#endif
