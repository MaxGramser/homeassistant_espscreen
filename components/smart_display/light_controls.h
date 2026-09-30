#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include "screen_text.h"
#include "ui_scale.h"

namespace light_controls {
inline int clamp(int value, int low, int high) { return std::max(low, std::min(high, value)); }
// HA serializes list attributes as either JSON lists or Python tuples.
inline bool first_number(const std::string &text, float &value) {
  const char *p = text.c_str();
  while (*p == ' ' || *p == '[' || *p == '(') ++p;
  char *end;
  float parsed = std::strtof(p, &end);
  if (end == p || !std::isfinite(parsed)) return false;
  value = parsed;
  return true;
}
struct State {
  const char *entity = "";
  int hue = 0, kelvin = 3000, minimum = 0, maximum = 0;
  bool temperature_ready() const { return minimum >= 1000 && maximum <= 15000 && maximum > minimum; }
  void update(unsigned attribute, const std::string &text) {
    float number;
    if (!first_number(text, number)) return;
    if (attribute == 0 && number >= 0 && number <= 360) hue = clamp(std::lround(number), 0, 360);
    if (attribute == 1 && number >= 1000 && number <= 15000) kelvin = std::lround(number);
    if (attribute == 2) minimum = number >= 1000 && number <= 15000 ? std::lround(number) : 0;
    if (attribute == 3) maximum = number >= 1000 && number <= 15000 ? std::lround(number) : 0;
  }
};
}

#ifndef LIGHT_CONTROLS_TEST
#include "esphome/components/api/api_server.h"
#include "esphome/core/log.h"
#include "lvgl.h"
#include "screen_input.h"
#include "theme.h"
#include <functional>
namespace light_controls {
inline State states[8];
inline State fallback;
inline State *active = &fallback;
struct Row {
  lv_obj_t *box{}, *slider{}, *value{}, *icon{}, *title{};
  std::array<lv_obj_t *, 2> ends{};
  std::array<lv_obj_t *, 6> stripes{};
  bool dirty = false; unsigned index{}; bool off = false; int held = 0;
};
inline Row rows[3];
// The card the rows stand on: a hand's width, in the middle of the overlay that covers the glass.
inline lv_obj_t *card = nullptr;
inline std::function<void(int)> commits[3];
inline bool ready = false;
inline bool demo = false;
inline void state_updated(State *state);
// Where the three rows start, their pitch, the gap between them and the height of the glass they were built
// for: open() puts the rows that show in the middle of the room under the title with them.
inline int top, spacing, row_gap, glass_h;
inline bool strip = false;
inline int strip_width = 0, strip_row_width = 0, strip_gap = 0;
inline void subscribe(const char *const *entities, size_t count) {
#ifdef USE_API_HOMEASSISTANT_STATES
  static const char *attributes[] = {"hs_color", "color_temp_kelvin", "min_color_temp_kelvin", "max_color_temp_kelvin"};
  size_t slot = 0;
  for (size_t i = 0; i < count && slot < 8; ++i) {
    if (std::string(entities[i]).rfind("light.", 0) != 0) continue;
    bool duplicate = false;
    for (size_t j = 0; j < slot; ++j) if (std::string(states[j].entity) == entities[i]) duplicate = true;
    if (duplicate) continue;
    State *state = &states[slot++];
    state->entity = entities[i];
    for (unsigned a = 0; a < 4; ++a)
      esphome::api::global_api_server->subscribe_home_assistant_state(state->entity, attributes[a],
        [state, a](esphome::StringRef value) { state->update(a, std::string(value.c_str(), value.size())); state_updated(state); });
  }
#else
  (void) entities;
  (void) count;
#endif
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
    if (row.index == 0) active->hue = value;
    if (row.index == 1) {
      if (!active->temperature_ready()) return;
      value = clamp(value, active->minimum, active->maximum);
      active->kelvin = value;
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
// The colours of the three cards, for setup() and for a change of look.
inline void paint(Row &row) {
  lv_obj_set_style_bg_color(row.box, theme::color(theme::CARD), 0);
  lv_obj_set_style_border_color(row.box, theme::color(theme::LINE), 0);
  lv_obj_set_style_text_color(row.box, theme::color(theme::INK), 0);
  lv_obj_set_style_text_color(row.value, theme::color(theme::MUTED), 0);
  if (row.icon) lv_obj_set_style_text_color(row.icon, theme::color(theme::MUTED), 0);
  if (row.index < 2) lv_obj_set_style_border_color(row.slider, theme::color(theme::KNOB), LV_PART_KNOB);
  else lv_obj_set_style_bg_color(row.slider, theme::color(theme::KNOB), LV_PART_KNOB);
}
inline void restyle() {
  if (!ready) return;
  for (auto &row : rows) { paint(row); preview(row); }
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
  if (ready) return;
  ready = true;
  // The look decides the class, never the glass: a wide panel draws the same rows, only at its own density.
  const bool large = ui::large();
  top = ui::px(large ? 100 : 52);
  strip = height <= 200 && width >= 3 * height;
  strip_width = width;
  // The three rows share the room under the title. A row wants the look's pitch, keeps at least a finger and
  // its words, and the three together never take more than what is left, so the card fits any glass it lands
  // on (a 800 x 480 panel at 217 dpi asked for 122 x 1.28 = 156 px a row and ran off the bottom). Three rows
  // are two pitches and one card: the last row needs no gap under it, which is why the gap counts once more.
  const int wanted = ui::px(large ? 122 : 60), gap = ui::px(large ? 12 : 5);
  const int least = ui::touch_min() + lv_font_get_line_height(font) + ui::px(12);
  const int room = height - top - ui::px(large ? 18 : 8);
  spacing = std::max(least, std::min(wanted, (room + gap) / 3));
  row_gap = gap; glass_h = height;
  int margin = ui::px(large ? 20 : 12), w = width - 2 * margin, card_h = spacing - gap;
  if (strip) {
    strip_gap = ui::px(5);
    w = (width - 2 * margin - 2 * strip_gap) / 3;
    strip_row_width = w;
    card_h = std::max(1, height - top - ui::px(8));
  }
  int inset = ui::px(large ? 18 : 10), text_y = ui::px(large ? 14 : 5), track_h = ui::px(large ? 32 : 18);
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
    row.box = plain(parent, margin + (strip ? i * (w + strip_gap) : 0),
                    strip ? top : top + i * spacing, w, card_h);
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
      if (strip) lv_obj_add_flag(icon, LV_OBJ_FLAG_HIDDEN);
      else text_x += icon_h + (ui::px(large ? 6 : 4));
    }
    auto *label = row.title = lv_label_create(row.box); lv_label_set_text(label, names[i]);
    lv_obj_set_pos(label, text_x, text_y);
    if (strip) {
      lv_obj_set_width(label, std::max(1, w - text_x - inset - ui::px(42)));
      lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
    }
    row.value = lv_label_create(row.box); lv_obj_align(row.value, LV_ALIGN_TOP_RIGHT, -inset, text_y);
    row.slider = lv_slider_create(row.box);
    lv_obj_remove_style_all(row.slider);
    lv_obj_remove_flag(row.slider, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_ext_click_area(row.slider, ui::px(large ? 12 : 8));
    if (i < 2) {
      // The knob travels between the centres of the two round ends.
      row.ends[0] = round_end(row.box, track_x, track_y, track_h, i == 0 ? RAINBOW[0] : WARM);
      row.ends[1] = round_end(row.box, track_x + track_w - track_h, track_y, track_h, i == 0 ? RAINBOW[6] : COOL);
      unsigned segments = i == 0 ? 6 : 1;
      int span = track_w - track_h;
      for (unsigned n = 0; n < segments; ++n) {
        int start = n * span / segments, end = (n + 1) * span / segments;
        auto *stripe = row.stripes[n] = plain(row.box, track_x + radius + start, track_y, end - start, track_h);
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
    paint(row);
    preview(row);
  }
}
// Reflow a short screen's card when the hue row is absent: temperature and
// brightness get half the glass each, including the full width of their tracks.
inline void strip_resize(Row &row, int width) {
  lv_obj_set_width(row.box, width);
  const int inset = ui::px(10), track_w = width - 2 * inset;
  const int title_x = static_cast<int>(lv_obj_get_x(row.title));
  lv_obj_set_width(row.title, std::max(1, width - title_x - inset - ui::px(42)));
  lv_obj_align(row.value, LV_ALIGN_TOP_RIGHT, -inset, ui::px(5));
  if (row.index < 2) {
    const int h = lv_obj_get_height(row.ends[0]), span = track_w - h;
    lv_obj_set_x(row.ends[1], inset + span);
    const int segments = row.index == 0 ? 6 : 1;
    for (int n = 0; n < segments; ++n) {
      const int start = n * span / segments, end = (n + 1) * span / segments;
      lv_obj_set_x(row.stripes[n], inset + h / 2 + start);
      lv_obj_set_width(row.stripes[n], end - start);
    }
    lv_obj_set_width(row.slider, span);
  } else {
    const int value = lv_slider_get_value(row.slider);
    lv_obj_set_width(row.slider, track_w);
    const int h = lv_obj_get_height(row.slider), handle = ui::px(3);
    const int stub = std::max(h / 3, 2 * std::max(1, h / 8) + handle);
    const int below = track_w > stub ? 99 * stub / (track_w - stub) : 0;
    lv_slider_set_range(row.slider, 1 - below, 100);
    lv_slider_set_value(row.slider, value, LV_ANIM_OFF);
  }
}
// Late capability attributes may arrive after opening the card. Enable the
// waiting temperature slider without disturbing an in-progress gesture.
inline void state_updated(State *state) {
  if (!ready || state != active || !state->temperature_ready()) return;
  auto &row = rows[1];
  if (!lv_obj_has_state(row.slider, LV_STATE_DISABLED)) return;
  lv_slider_set_range(row.slider, state->minimum, state->maximum);
  lv_slider_set_value(row.slider, state->kelvin, LV_ANIM_OFF);
  lv_obj_remove_state(row.slider, LV_STATE_DISABLED);
  preview(row); row.dirty = false;
}
inline void open(const std::string &entity, bool color, bool temperature, int brightness) {
  active = &fallback;
  for (auto &state : states) if (entity == state.entity) { active = &state; break; }
  // The rows that show stand in the middle of the room under the title, the way every card centres what it
  // draws (overlay_card::centre), and only when that leaves more than a finger over: on a CYD and a Guition
  // three rows already fill the glass, so nothing there moves.
  int showing = (color ? 1 : 0) + (temperature ? 1 : 0) + 1;
  const int block = showing * spacing - row_gap;
  const int over = glass_h - top - ui::px(ui::large() ? 18 : 8) - block;
  int y = over > ui::touch_min() && !strip ? top + over / 2 : top;
  if (strip) {
    const int columns = std::max(2, showing);
    strip_row_width = (strip_width - 2 * ui::px(12) - (columns - 1) * strip_gap) / columns;
  }
  const int strip_left = strip ? (strip_width - showing * strip_row_width - (showing - 1) * strip_gap) / 2 : 0;
  int visible_slot = 0;
  for (unsigned i = 0; i < 3; ++i) {
    auto &row = rows[i];
    bool visible = i == 0 ? color : i == 1 ? temperature : true;
    if (!visible) { lv_obj_add_flag(row.box, LV_OBJ_FLAG_HIDDEN); continue; }
    lv_obj_remove_flag(row.box, LV_OBJ_FLAG_HIDDEN); lv_obj_set_y(row.box, y);
    if (strip) {
      lv_obj_set_x(row.box, strip_left + visible_slot++ * (strip_row_width + strip_gap));
      strip_resize(row, strip_row_width);
    }
    else y += spacing;
    lv_obj_remove_state(row.slider, LV_STATE_DISABLED);
    if (i == 1 && !active->temperature_ready()) lv_obj_add_state(row.slider, LV_STATE_DISABLED);
    if (i == 1 && active->temperature_ready()) lv_slider_set_range(row.slider, active->minimum, active->maximum);
    lv_slider_set_value(row.slider, i == 0 ? active->hue : i == 1 ? active->kelvin : clamp(brightness, 1, 100), LV_ANIM_OFF);
    row.off = i == 2 && brightness <= 0;
    preview(row); row.dirty = false;
    if (i == 1 && !active->temperature_ready()) lv_label_set_text(row.value, screen_text::tr(screen_text::txt::light_waiting));
  }
}
inline bool self_test() {
  auto *previous = active;
  State saved_fallback = fallback;
  int saved_values[3]; bool saved_hidden[3];
  std::function<void(int)> saved[3];
  int calls[3] = {0, 0, 0};
  for (unsigned i = 0; i < 3; ++i) {
    saved[i] = commits[i]; saved_values[i] = lv_slider_get_value(rows[i].slider);
    saved_hidden[i] = lv_obj_has_flag(rows[i].box, LV_OBJ_FLAG_HIDDEN);
    commits[i] = [&, i](int value) { if (value == (i == 0 ? 180 : i == 1 ? 4000 : 65)) ++calls[i]; };
  }
  fallback.minimum = 2200; fallback.maximum = 5000;
  open("diagnostic", true, true, 50);
  bool ok = true;
  for (unsigned i = 0; i < 3; ++i) {
    auto *slider = rows[i].slider;
    lv_slider_set_value(slider, i == 0 ? 180 : i == 1 ? 4000 : 65, LV_ANIM_OFF);
    for (int n = 0; n < 20; ++n) lv_obj_send_event(slider, LV_EVENT_VALUE_CHANGED, nullptr);
    ok &= calls[i] == 0;
    lv_obj_send_event(slider, LV_EVENT_RELEASED, nullptr);
    lv_obj_send_event(slider, LV_EVENT_RELEASED, nullptr);
    ok &= calls[i] == 1;
    lv_obj_send_event(slider, LV_EVENT_VALUE_CHANGED, nullptr);
    lv_obj_send_event(slider, LV_EVENT_PRESS_LOST, nullptr);
    lv_obj_send_event(slider, LV_EVENT_RELEASED, nullptr);
    ok &= calls[i] == 1;
  }
  for (unsigned mask = 0; mask < 4; ++mask) {
    open("diagnostic", mask & 1, mask & 2, 50);
    ok &= lv_obj_has_flag(rows[0].box, LV_OBJ_FLAG_HIDDEN) == !(mask & 1);
    ok &= lv_obj_has_flag(rows[1].box, LV_OBJ_FLAG_HIDDEN) == !(mask & 2);
    ok &= !lv_obj_has_flag(rows[2].box, LV_OBJ_FLAG_HIDDEN);
  }
  fallback = saved_fallback;
  open(previous->entity, !saved_hidden[0], !saved_hidden[1], saved_values[2]);
  active = previous;
  for (unsigned i = 0; i < 3; ++i) {
    commits[i] = saved[i];
    lv_slider_set_value(rows[i].slider, saved_values[i], LV_ANIM_OFF);
    preview(rows[i]); rows[i].dirty = false;
  }
  return ok;
}

}
#endif
