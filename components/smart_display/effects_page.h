#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>
#include "runtime_model.h"
#include "screen_text.h"

// A light's effects page (firmware 0.2.70+, app 0.2.83+): the modes of a lamp such as a WLED, reached from the
// sparkles key at the top right of the light's colour card. One card of rows, each the name of something the lamp
// offers and what it is set to (the light's effect, and the select entities of its device: colour palette, preset,
// playlist), and under it a slider card per number entity of the device (speed, intensity). A row opens a picker:
// LVGL's roller with every name Home Assistant lists at that moment (asked for when the picker opens, one page of
// names per message), and the check key at the top right sends the name the drum stands on. Nothing here knows a brand: the rows,
// their names and their icons come from Home Assistant through the add-on.
//
// Like the settings page, the page is built when it opens and thrown away when it closes, so it costs nothing while
// closed. The model part (percentages, texts, what the page can show) stays free of LVGL for tests/test_effects_page.cpp.
namespace effects_page {
using runtime_tiles::NumberRow;
using runtime_tiles::OptionRow;
using runtime_tiles::Tile;

// LightEntityFeature.EFFECT: the light offers an effect list.
constexpr uint32_t EFFECT_FEATURE = 4;
// Names a picker holds at most; a WLED lists about 220 effects.
constexpr size_t MAX_NAMES = 400;
// How many of those names this screen can actually hold. A WLED light brings hundreds of effects and every one
// of them is a string in a list: on a board with little memory inside the chip the list itself was more than
// there was, and an allocation that fails aborts the firmware -- what a user sees is the screen restarting the
// moment the picker opens (Waveshare 800x480, 2026-09-20). The list is cut to what fits instead: the last
// effects of a very long list go, the screen stays. `left` is the free memory, 0 when nothing can say (the
// host and the tests), and then the ceiling holds.
constexpr size_t NAME_COST = sizeof(std::string) + 24;   // its place in the list and a name of average length
constexpr size_t NAME_RESERVE = 12 * 1024;               // what the rest of the firmware keeps for itself
inline size_t names_room(size_t left) {
  if (left == 0) return MAX_NAMES;
  return left > NAME_RESERVE ? std::min(MAX_NAMES, (left - NAME_RESERVE) / NAME_COST) : 0;
}
// A chosen name stays on its row while Home Assistant still reports the old one, this long at most.
constexpr uint32_t SENT_HOLD_MS = 4000;

inline int clamp(int value, int low, int high) { return std::max(low, std::min(high, value)); }
// Whether a light has an effects page: it offers effects, or its device has rows to show.
inline bool available(const Tile &t) {
  return t.domain() == "light" && ((t.supported & EFFECT_FEATURE) != 0 || !t.extra().option_rows.empty() || !t.extra().number_rows.empty());
}
// A number's place on its slider, 0-100 % of its range.
inline int percent_of(float value, float low, float high) {
  if (!std::isfinite(value) || !(high > low)) return 0;
  return clamp(static_cast<int>(std::lround((value - low) * 100 / (high - low))), 0, 100);
}
// The number a slider stands for, on the entity's own step and inside its range.
inline float value_at(int percent, float low, float high, float step) {
  float value = low + (high - low) * clamp(percent, 0, 100) / 100.0f;
  if (step > 0) value = low + std::round((value - low) / step) * step;
  return std::min(high, std::max(low, value));
}
// A number as Home Assistant's action takes it: "128", "12.5", never "128.000000".
inline std::string number_text(float value) {
  char b[24];
  snprintf(b, sizeof(b), "%.3f", value);
  std::string text = b;
  while (text.size() > 1 && text.back() == '0') text.pop_back();
  if (text.back() == '.') text.pop_back();
  return text;
}
inline std::string percent_text(int percent) { return screen_text::percent(percent); }
// The roller takes its names as one string, a line per name.
inline std::string joined(const std::vector<std::string> &names) {
  std::string out;
  for (size_t i = 0; i < names.size(); ++i) { if (i) out += '\n'; out += names[i]; }
  return out;
}
inline int index_of(const std::vector<std::string> &names, const std::string &name) {
  for (size_t i = 0; i < names.size(); ++i) if (names[i] == name) return static_cast<int>(i);
  return -1;
}
// The value a row shows: the name Home Assistant reports, a dash while it reports none.
inline std::string row_text(const std::string &current) {
  return current.empty() || current == "unknown" || current == "unavailable" || current == "None" ? "—" : current;
}

// The page's sizes in the look's pixels (ui::px); the compact look takes the small set.
struct Metrics {
  int width = 480, height = 480, pad = ui::px(20), bar_y = ui::px(16), bar = ui::px(60), title_y = ui::px(35), rows_y = ui::px(100), row_h = ui::px(56), inset = ui::px(18),
      icon = ui::px(26), gap = ui::px(12), number_h = ui::px(92), track_h = ui::px(28), number_inset = ui::px(16), roller_rows = 5, roller_row_h = ui::px(56), roller_pad = ui::px(10),
      radius = ui::px(18), knob = ui::px(4);
};
inline Metrics metrics(int width, int height) {
  Metrics m;
  m.width = width; m.height = height;
  if (!ui::large()) {
    m.pad = ui::px(12); m.bar_y = ui::px(8); m.bar = ui::px(40); m.title_y = ui::px(21); m.rows_y = ui::px(52); m.row_h = ui::px(34); m.inset = ui::px(10); m.icon = ui::px(18); m.gap = ui::px(6);
    m.number_h = ui::px(44); m.track_h = ui::px(14); m.number_inset = ui::px(9); m.roller_row_h = ui::px(30); m.roller_pad = ui::px(5); m.radius = ui::px(10); m.knob = ui::px(3);
  }
  return m;
}

// Where everything under the top bar stands. The rows and the slider cards have to fit between the bar and the
// bottom edge, and until now they were simply stacked: on a wide screen with a short glass (800x480 draws the
// standard look 28 % larger while its height stays 480) a light with three selects pushed its speed and
// intensity sliders off the screen. Two ways out, in this order:
//
// 1. a screen with width to spare puts the sliders beside the rows instead of under them, as the cover card
//    does on wide glass: the height the stack needed becomes width, which this board has;
// 2. what still does not fit is taken from the stack, the rows first (never under a finger, ui::touch_min)
//    and then the slider cards (never under their track and their line of text).
//
// `numbers` is how many slider cards there are (at most two), `text_h` the line height of the row font.
struct Placed {
  int rows_x = 0, rows_y = 0, rows_w = 0, rows_h = 0, row_h = 0;
  int number_x[2] = {0, 0}, number_y[2] = {0, 0}, number_w = 0, number_h = 0;
  bool beside = false;   // the sliders stand next to the rows
  bool scrolls = false;  // more rows than the glass holds; the card scrolls
};
// The least a slider card can be: its line of text at the top, its track at the bottom, the insets of both.
inline int least_number_h(const Metrics &m, int text_h) {
  return m.number_inset * 3 / 4 + text_h + m.number_inset + m.track_h + 2;
}
inline Placed place(const Metrics &m, int rows, int numbers, int text_h) {
  Placed p;
  numbers = std::max(0, std::min(2, numbers));
  rows = std::max(0, rows);
  const int full = m.width - 2 * m.pad, room = m.height - m.rows_y - m.pad;
  p.rows_x = m.pad; p.rows_y = m.rows_y; p.rows_w = full; p.row_h = m.row_h; p.number_h = m.number_h;
  p.number_w = numbers == 1 ? full : (full - m.gap) / 2;
  const int stacked = rows * p.row_h + (rows && numbers ? m.gap : 0) + (numbers ? p.number_h : 0);
  // Wide enough to stand in two: three units of width to two of height, the shape that made the cover card
  // split as well. A square or a portrait screen keeps the sliders under the rows.
  if (numbers > 0 && stacked > room && m.width * 2 >= m.height * 3) {
    p.beside = true;
    p.number_w = (full - m.gap) / 2;
    p.rows_w = full - m.gap - p.number_w;
  }
  // What each column asks for, and what it may give back.
  auto column_heights = [&](int &left, int &right) {
    left = rows * p.row_h;
    right = numbers * p.number_h + (numbers > 1 ? m.gap : 0);
    if (!p.beside) { left = left + (rows && numbers ? m.gap : 0) + (numbers ? p.number_h : 0); right = 0; }
  };
  int left = 0, right = 0;
  column_heights(left, right);
  int over = std::max(left, right) - room;
  if (over > 0) {
    const int least_row = std::min(p.row_h, ui::touch_min()), least_number = std::min(p.number_h, least_number_h(m, text_h));
    ui::shrink({{&p.row_h, least_row, std::max(1, rows)},
                {&p.number_h, least_number, p.beside ? std::max(1, numbers) : 1}}, over);
    column_heights(left, right);
  }
  // Still too many rows for the glass: the card takes the room there is and scrolls.
  p.rows_h = rows * p.row_h;
  const int rows_room = p.beside || !numbers ? room : room - m.gap - p.number_h;
  if (p.rows_h > rows_room) { p.rows_h = std::max(p.row_h, rows_room); p.scrolls = true; }
  for (int i = 0; i < numbers; ++i) {
    if (p.beside) {
      p.number_x[i] = m.pad + p.rows_w + m.gap;
      p.number_y[i] = m.rows_y + i * (p.number_h + m.gap);
    } else {
      p.number_x[i] = m.pad + i * (p.number_w + m.gap);
      p.number_y[i] = m.rows_y + p.rows_h + (rows ? m.gap : 0);
    }
  }
  // What is left over goes half above and half below, the way every card centres what it draws
  // (overlay_card::centre): a page whose block fills the glass does not move, and neither does one that scrolls.
  int bottom = p.rows_y + (rows ? p.rows_h : 0);
  for (int i = 0; i < numbers; ++i) bottom = std::max(bottom, p.number_y[i] + p.number_h);
  const int spare = m.height - m.pad - bottom;
  if (!p.scrolls && spare > ui::touch_min()) {
    const int shift = spare / 2;
    p.rows_y += shift;
    for (int i = 0; i < numbers; ++i) p.number_y[i] += shift;
  }
  return p;
}
}  // namespace effects_page

#ifndef EFFECTS_PAGE_TEST
#include "esphome/core/log.h"
#include "lvgl.h"
#include "overlay_card.h"
#include "theme.h"
#include "tile_icon.h"
namespace effects_page {
// ---- what the board profile wires up at boot ----
inline const lv_font_t *title_font = nullptr, *row_font = nullptr, *roller_font = nullptr, *icon_font = nullptr;
inline std::function<const Tile *(const std::string &)> tile_of;                                            // the open card's tile, else the first of that entity
inline std::function<void(const std::string &, const std::string &, const std::string &, const std::string &)> send;  // service, entity, key, value
inline std::function<void(const std::string &, unsigned)> ask;                                               // options_request
inline std::function<int()> drift;                                                                           // finger travel this touch
inline int tap_limit = 0;
inline uint32_t (*now)() = nullptr;

// ---- state while open ----
inline lv_obj_t *root = nullptr, *picker = nullptr;
inline std::string entity;   // the light
struct RowDrawn { lv_obj_t *card = nullptr, *value = nullptr; std::string entity, sent; uint32_t sent_at = 0; bool light = false; std::string name; };
struct NumberDrawn { lv_obj_t *slider = nullptr, *value = nullptr; std::string entity; float low = 0, high = 100, step = 1; bool dirty = false; };
inline std::vector<RowDrawn> rows;
inline std::vector<NumberDrawn> numbers;
// The picker's names: one entity at a time, page by page from the add-on.
struct Options { std::string entity; std::vector<std::string> names; unsigned next = 0, pages = 0; bool complete = false; uint32_t asked_at = 0; };
inline Options options;
inline lv_obj_t *roller = nullptr, *roller_note = nullptr;
inline int picker_row = -1;

inline uint32_t clock() { return now ? now() : lv_tick_get(); }
// The page's sizes from the screen (a page just made has no width of its own until LVGL lays it out).
inline Metrics screen_metrics() {
  return metrics(overlay_card::content_width(), overlay_card::screen_height());
}
inline bool visible() { return root != nullptr; }
inline bool steady() { return !drift || tap_limit <= 0 || drift() <= tap_limit; }
inline const Tile *tile() { return tile_of ? tile_of(entity) : nullptr; }
// Whether the colour card of this light shows the sparkles key.
inline bool offered(const std::string &light) { const Tile *t = tile_of ? tile_of(light) : nullptr; return t && available(*t); }

inline lv_obj_t *plain(lv_obj_t *parent, int x, int y, int w, int h) {
  auto *obj = lv_obj_create(parent);
  lv_obj_remove_style_all(obj);
  lv_obj_remove_flag(obj, static_cast<lv_obj_flag_t>(LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE));
  lv_obj_set_pos(obj, x, y);
  lv_obj_set_size(obj, w, h);
  return obj;
}
inline lv_obj_t *text(lv_obj_t *parent, const std::string &value, const lv_font_t *font, theme::Role color,
                      lv_text_align_t align = LV_TEXT_ALIGN_LEFT) {
  auto *label = lv_label_create(parent);
  lv_label_set_text(label, value.c_str());
  lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
  lv_obj_remove_flag(label, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_text_font(label, font, 0);
  lv_obj_set_style_text_color(label, theme::color(color), 0);
  lv_obj_set_style_text_align(label, align, 0);
  lv_obj_set_height(label, lv_font_get_line_height(font));
  return label;
}
inline lv_obj_t *card(lv_obj_t *parent, int x, int y, int w, int h, int radius) {
  auto *obj = plain(parent, x, y, w, h);
  lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(obj, theme::color(theme::CARD), 0);
  lv_obj_set_style_border_width(obj, 1, 0);
  lv_obj_set_style_border_color(obj, theme::color(theme::LINE), 0);
  lv_obj_set_style_radius(obj, radius, 0);
  return obj;
}
// The glyph a row shows: Home Assistant's icon when these fonts carry it, else one of the page's own.
inline std::string glyph(uint32_t icon, const char *fallback) {
  if (icon && icon_font) { lv_font_glyph_dsc_t dsc; if (lv_font_get_glyph_dsc(icon_font, &dsc, icon, 0)) return tile_icon::utf8(icon); }
  return fallback;
}
// A round key like the back key of every card, with a glyph in the middle.
inline lv_obj_t *round_key(lv_obj_t *parent, int x, int y, int size, const char *glyph, lv_event_cb_t handler) {
  auto *key = plain(parent, x, y, size, size);
  lv_obj_add_flag(key, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_bg_opa(key, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(key, theme::color(theme::KEY), 0);
  lv_obj_set_style_bg_color(key, theme::color(theme::KEY_PRESSED), LV_STATE_PRESSED);
  lv_obj_set_style_radius(key, LV_RADIUS_CIRCLE, 0);
  auto *label = text(key, glyph, icon_font ? icon_font : row_font, theme::INK);
  lv_obj_set_width(label, LV_SIZE_CONTENT);
  lv_obj_center(label);
  lv_obj_add_event_cb(key, handler, LV_EVENT_SHORT_CLICKED, nullptr);
  return key;
}
// The same top bar as every card: a round back key and the name in the middle, and on the picker the check key at
// the top right, where the colour card has its sparkles key.
inline lv_obj_t *top_bar(lv_obj_t *parent, const Metrics &m, const std::string &title, lv_event_cb_t back,
                         const char *right_glyph = nullptr, lv_event_cb_t right = nullptr) {
  auto *key = round_key(parent, m.pad, m.bar_y, m.bar, "\U000F004D", back);
  if (right_glyph && right) round_key(parent, m.width - m.pad - m.bar, m.bar_y, m.bar, right_glyph, right);
  const lv_font_t *heading = title_font ? title_font : row_font;
  auto *label = text(parent, title, heading, theme::INK, LV_TEXT_ALIGN_CENTER);
  lv_obj_set_width(label, m.width - 2 * (m.pad + m.bar + 8));
  lv_obj_set_pos(label, m.pad + m.bar + 8, m.bar_y + (m.bar - lv_font_get_line_height(heading)) / 2);
  return key;
}
inline lv_obj_t *page_root() {
  auto *obj = lv_obj_create(lv_screen_active());
  lv_obj_remove_style_all(obj);
  lv_obj_set_size(obj, lv_pct(100), lv_pct(100));
  // The page covers the glass, but its rows and sliders are worked with a finger, so they keep a hand's width
  // and stand in the middle: the padding makes the page's own room that card (overlay_card::content_width).
  // On a CYD and a Guition the glass is narrower than a hand already, so the padding is nought there.
  const int side = (overlay_card::screen_width() - overlay_card::content_width()) / 2;
  lv_obj_set_style_pad_left(obj, side, 0);
  lv_obj_set_style_pad_right(obj, side, 0);
  lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(obj, LV_OBJ_FLAG_CLICKABLE);  // nothing leaks through to what lies under it
  lv_obj_set_style_bg_color(obj, theme::color(theme::PAGE_SOFT), 0);
  lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
  lv_obj_move_foreground(obj);
  return obj;
}

// ---- the picker ----
inline void close_picker() {
  if (picker) { lv_obj_delete(picker); picker = nullptr; }
  roller = roller_note = nullptr;
  picker_row = -1;
}
inline void choose(const std::string &name) {
  if (picker_row < 0 || picker_row >= static_cast<int>(rows.size()) || name.empty()) return;
  auto &row = rows[picker_row];
  // What Home Assistant reports for the row now: the drum resting on it again sends nothing.
  std::string current;
  if (const Tile *t = tile()) {
    if (row.light) current = t->extra().effect;
    else for (auto &r : t->extra().option_rows) if (r.entity == row.entity) current = r.current;
  }
  if (name == row.sent || (row.sent.empty() && name == current)) return;
  row.sent = name; row.sent_at = clock();
  if (row.value) lv_label_set_text(row.value, name.c_str());
  ESP_LOGI("effects", "%s: %s", row.entity.c_str(), name.c_str());
  if (!send) return;
  if (row.light) send("light.turn_on", row.entity, "effect", name);
  else send("select.select_option", row.entity, "option", name);
}
// The check key: the name the drum stands on goes out, and the picker closes. Nothing is sent before it.
inline void confirm() {
  if (!roller) return;
  char name[64];
  lv_roller_get_selected_str(roller, name, sizeof(name));
  choose(name);
  close_picker();
}
inline void confirm_event(lv_event_t *) { if (steady()) confirm(); }
inline void show_roller() {
  if (!picker || !roller_note || options.names.empty()) return;
  auto *holder = lv_obj_get_parent(roller_note);
  const Metrics m = screen_metrics();
  lv_obj_add_flag(roller_note, LV_OBJ_FLAG_HIDDEN);
  const lv_font_t *font = roller_font ? roller_font : row_font;
  roller = lv_roller_create(holder);
  lv_obj_remove_style_all(roller);
  lv_obj_set_style_bg_opa(roller, LV_OPA_TRANSP, LV_PART_MAIN);
  lv_obj_set_style_text_font(roller, font, LV_PART_MAIN);
  lv_obj_set_style_text_color(roller, theme::color(theme::MUTED), LV_PART_MAIN);
  lv_obj_set_style_text_align(roller, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
  lv_obj_set_style_text_line_space(roller, std::max(0, m.roller_row_h - (int) lv_font_get_line_height(font)), LV_PART_MAIN);
  lv_obj_set_style_anim_duration(roller, 200, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(roller, LV_OPA_COVER, LV_PART_SELECTED);
  lv_obj_set_style_bg_color(roller, theme::color(theme::ACCENT_TINT), LV_PART_SELECTED);
  lv_obj_set_style_radius(roller, m.roller_row_h / 2, LV_PART_SELECTED);
  lv_obj_set_style_text_color(roller, theme::color(theme::INK), LV_PART_SELECTED);
  lv_obj_set_style_text_font(roller, font, LV_PART_SELECTED);
  lv_roller_set_options(roller, joined(options.names).c_str(), LV_ROLLER_MODE_NORMAL);
  lv_roller_set_visible_row_count(roller, m.roller_rows);
  // The card's width from the sizes, not from the card: a card made a moment ago has no width until LVGL lays it out.
  lv_obj_set_width(roller, m.width - 2 * m.pad - 2 * m.inset);
  lv_obj_center(roller);
  const auto &row = rows[picker_row];
  std::string current = !row.sent.empty() ? row.sent : row.light ? (tile() ? tile()->extra().effect : std::string()) : [&]() {
    if (auto *t = tile()) for (auto &r : t->extra().option_rows) if (r.entity == row.entity) return r.current;
    return std::string();
  }();
  int index = index_of(options.names, current);
  if (index >= 0) lv_roller_set_selected(roller, static_cast<uint32_t>(index), LV_ANIM_OFF);
}
// One page of names from the add-on (runtime_tiles::options_received); the roller appears with the last one.
inline void received(const std::string &for_entity, unsigned page, unsigned pages, std::vector<std::string> &&names) {
  if (!picker || for_entity != options.entity || options.complete) return;
  if (page != options.next) return;  // an answer to an older question, or one that arrived twice
  const size_t room = names_room(runtime_tiles::heap_room ? runtime_tiles::heap_room() : 0);
  if (options.names.capacity() < std::min(room, options.names.size() + names.size()))
    options.names.reserve(std::min(room, options.names.size() + names.size()));
  for (auto &name : names) { if (options.names.size() >= room) break; options.names.push_back(std::move(name)); }
  options.next = page + 1;
  options.pages = std::max(1u, pages);
  if (options.next < options.pages && options.names.size() < room) { options.asked_at = clock(); if (ask) ask(options.entity, options.next); return; }
  options.complete = true;
  if (options.names.empty()) { if (roller_note) lv_label_set_text(roller_note, screen_text::tr(screen_text::txt::effects_nothing)); return; }
  show_roller();
}
inline void picker_back(lv_event_t *) { if (steady()) close_picker(); }
inline void open_picker(int index) {
  if (!root || index < 0 || index >= static_cast<int>(rows.size())) return;
  close_picker();
  picker_row = index;
  const auto &row = rows[index];
  const Metrics m = screen_metrics();
  picker = page_root();
  top_bar(picker, m, row.name, picker_back, "\U000F012C", confirm_event);
  const int w = m.width - 2 * m.pad, h = m.roller_rows * m.roller_row_h + 2 * m.roller_pad;
  // The picker stands where the page's own block stands: what is left over goes half above and half below,
  // and only when more than a finger is left (place(), overlay_card::centre).
  const int spare = m.height - m.pad - m.rows_y - h;
  auto *holder = card(picker, m.pad, spare > ui::touch_min() ? m.rows_y + spare / 2 : m.rows_y, w, h, m.radius);
  roller_note = text(holder, screen_text::tr(screen_text::txt::effects_loading), row_font, theme::MUTED, LV_TEXT_ALIGN_CENTER);
  lv_obj_set_width(roller_note, w - 2 * m.inset);
  lv_obj_center(roller_note);
  // The names of the same entity from a moment ago serve again; anything else is asked for afresh.
  if (options.entity == row.entity && options.complete && !options.names.empty()) { show_roller(); return; }
  options = Options{};
  options.entity = row.entity;
  options.asked_at = clock();
  if (ask) ask(row.entity, 0);
  else lv_label_set_text(roller_note, screen_text::tr(screen_text::txt::effects_not_connected));
}

// ---- the page ----
inline void row_event(lv_event_t *e) {
  if (lv_event_get_code(e) != LV_EVENT_SHORT_CLICKED || !steady()) return;
  open_picker(static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e))));
}
inline void preview(NumberDrawn &n) {
  if (n.value) lv_label_set_text(n.value, percent_text(lv_slider_get_value(n.slider)).c_str());
}
inline void slider_event(lv_event_t *e) {
  auto &n = numbers[reinterpret_cast<intptr_t>(lv_event_get_user_data(e))];
  const auto code = lv_event_get_code(e);
  if (code == LV_EVENT_VALUE_CHANGED) { n.dirty = true; preview(n); }
  if (code == LV_EVENT_PRESS_LOST) n.dirty = false;
  if (code == LV_EVENT_RELEASED && n.dirty) {
    n.dirty = false;
    const float value = value_at(lv_slider_get_value(n.slider), n.low, n.high, n.step);
    ESP_LOGI("effects", "%s: %s", n.entity.c_str(), number_text(value).c_str());
    if (send) send("number.set_value", n.entity, "value", number_text(value));
  }
}
inline void back_event(lv_event_t *) { if (steady()) { close_picker(); if (root) { lv_obj_delete(root); root = nullptr; } rows.clear(); numbers.clear(); } }
inline void draw() {
  if (!root) return;
  lv_obj_clean(root);
  rows.clear(); numbers.clear();
  const Tile *t = tile();
  const Metrics m = screen_metrics();
  top_bar(root, m, t ? (t->name.empty() ? t->entity : t->name) : entity, back_event);
  const int w = m.width - 2 * m.pad;
  // The rows: the light's effect first, then the selects of its device.
  struct Spec { std::string entity, name, current, fallback; uint32_t icon; bool light; };
  std::vector<Spec> specs;
  if (t && (t->supported & EFFECT_FEATURE)) specs.push_back({t->entity, screen_text::tr(screen_text::txt::effects_effect), t->extra().effect, "\U000F0674", 0, true});
  if (t) for (auto &r : t->extra().option_rows) specs.push_back({r.entity, r.name, r.current, "\U000F0411", r.icon, false});
  const int row_text_h = lv_font_get_line_height(row_font);
  const size_t number_count = t ? std::min<size_t>(2, t->extra().number_rows.size()) : 0;
  const Placed at = place(m, static_cast<int>(specs.size()), static_cast<int>(number_count), row_text_h);
  const int row_h = at.row_h, w_rows = at.rows_w;
  if (!specs.empty()) {
    auto *holder = card(root, at.rows_x, at.rows_y, w_rows, at.rows_h, m.radius);
    // More rows than the glass holds: the card keeps LVGL's scrolling instead of drawing past the bottom edge.
    if (at.scrolls) {
      lv_obj_add_flag(holder, LV_OBJ_FLAG_SCROLLABLE);
      lv_obj_set_scroll_dir(holder, LV_DIR_VER);
      lv_obj_set_scrollbar_mode(holder, LV_SCROLLBAR_MODE_AUTO);
    }
    for (size_t i = 0; i < specs.size(); ++i) {
      auto &spec = specs[i];
      auto *row = plain(holder, 0, static_cast<int>(i) * row_h, w_rows, row_h);
      lv_obj_add_flag(row, LV_OBJ_FLAG_CLICKABLE);
      lv_obj_set_style_bg_opa(row, LV_OPA_COVER, LV_STATE_PRESSED);
      lv_obj_set_style_bg_color(row, theme::color(theme::CARD_PRESSED), LV_STATE_PRESSED);
      lv_obj_set_style_radius(row, m.radius, 0);
      lv_obj_add_event_cb(row, row_event, LV_EVENT_SHORT_CLICKED, reinterpret_cast<void *>(static_cast<intptr_t>(i)));
      const int icon_h = icon_font ? lv_font_get_line_height(icon_font) : 0, text_h = row_text_h;
      int x = m.inset;
      if (icon_font) {
        auto *icon = text(row, glyph(spec.icon, spec.fallback.c_str()), icon_font, theme::MUTED);
        lv_obj_set_width(icon, LV_SIZE_CONTENT);
        lv_obj_set_pos(icon, m.inset - 2, (row_h - icon_h) / 2);
        x += m.icon + 6;
      }
      auto *name = text(row, spec.name, row_font, theme::INK);
      lv_obj_set_pos(name, x, (row_h - text_h) / 2);
      const int chevron_w = icon_font ? m.icon : 0;
      lv_obj_set_width(name, std::max(20, w_rows / 2 - x));
      if (icon_font) {
        auto *chevron = text(row, "\U000F0142", icon_font, theme::CHEVRON);
        lv_obj_set_width(chevron, LV_SIZE_CONTENT);
        lv_obj_set_pos(chevron, w_rows - m.inset - chevron_w + 2, (row_h - icon_h) / 2);
      }
      auto *value = text(row, row_text(spec.current), row_font, theme::MUTED, LV_TEXT_ALIGN_RIGHT);
      const int value_x = w_rows / 2 + 4;
      lv_obj_set_pos(value, value_x, (row_h - text_h) / 2);
      lv_obj_set_width(value, std::max(20, w_rows - m.inset - chevron_w - 4 - value_x));
      RowDrawn drawn; drawn.card = row; drawn.value = value; drawn.entity = spec.entity; drawn.light = spec.light; drawn.name = spec.name;
      rows.push_back(std::move(drawn));
    }
  }
  // The numbers: slider cards side by side under the rows, or in a column beside them on wide glass (place()).
  if (number_count) {
    const size_t count = number_count;
    const int card_w = at.number_w;
    for (size_t i = 0; i < count; ++i) {
      const auto &n = t->extra().number_rows[i];
      auto *holder = card(root, at.number_x[i], at.number_y[i], card_w, at.number_h, m.radius);
      const int text_h = row_text_h, text_y = m.number_inset * 3 / 4;
      int tx = m.number_inset;
      if (icon_font) {
        auto *icon = text(holder, glyph(n.icon, "\U000F00DF"), icon_font, theme::MUTED);
        lv_obj_set_width(icon, LV_SIZE_CONTENT);
        const int icon_h = lv_font_get_line_height(icon_font);
        lv_obj_set_pos(icon, m.number_inset - 2, text_y + (text_h - icon_h) / 2);
        tx += m.icon - 2 + 5;
      }
      auto *name = text(holder, n.name, row_font, theme::INK);
      lv_obj_set_pos(name, tx, text_y);
      lv_obj_set_width(name, std::max(20, card_w - tx - m.number_inset - 52));
      auto *value = text(holder, percent_text(percent_of(n.value, n.low, n.high)), row_font, theme::MUTED, LV_TEXT_ALIGN_RIGHT);
      lv_obj_set_width(value, 50);
      lv_obj_set_pos(value, card_w - m.number_inset - 50, text_y);
      // Corners, handle and shortest fill as the colour card's brightness slider: the fill keeps the track's radius
      // (a smaller one makes LVGL draw it into a buffer of its own on every redraw).
      const int track_x = m.number_inset, track_w = card_w - 2 * m.number_inset, track_h = m.track_h, track_y = at.number_h - m.number_inset - track_h + 2;
      auto *slider = lv_slider_create(holder);
      lv_obj_remove_style_all(slider);
      lv_obj_remove_flag(slider, LV_OBJ_FLAG_SCROLLABLE);
      lv_obj_set_pos(slider, track_x, track_y); lv_obj_set_size(slider, track_w, track_h);
      lv_obj_set_ext_click_area(slider, ui::px(ui::large() ? 12 : 8));
      const int corner = track_h * 12 / 42;
      lv_obj_set_style_radius(slider, corner, LV_PART_MAIN);
      lv_obj_set_style_radius(slider, corner, LV_PART_INDICATOR);
      lv_obj_set_style_bg_opa(slider, LV_OPA_COVER, LV_PART_MAIN);
      lv_obj_set_style_bg_color(slider, theme::color(theme::ACCENT_TINT), LV_PART_MAIN);
      lv_obj_set_style_bg_opa(slider, LV_OPA_COVER, LV_PART_INDICATOR);
      lv_obj_set_style_bg_color(slider, theme::color(theme::ACCENT_BRIGHT), LV_PART_INDICATOR);
      const int handle = m.knob, back = std::max(1, track_h / 8) + handle / 2, half = track_h >> 1;
      lv_obj_set_style_bg_opa(slider, LV_OPA_COVER, LV_PART_KNOB);
      lv_obj_set_style_bg_color(slider, theme::color(theme::KNOB), LV_PART_KNOB);
      lv_obj_set_style_radius(slider, 2, LV_PART_KNOB);
      lv_obj_set_style_pad_left(slider, back + handle / 2 - half, LV_PART_KNOB);
      lv_obj_set_style_pad_right(slider, handle / 2 - back - (track_h - half), LV_PART_KNOB);
      lv_obj_set_style_pad_top(slider, -(track_h / 4), LV_PART_KNOB);
      lv_obj_set_style_pad_bottom(slider, -(track_h / 4), LV_PART_KNOB);
      lv_slider_set_range(slider, 0, 100);
      lv_slider_set_value(slider, percent_of(n.value, n.low, n.high), LV_ANIM_OFF);
      NumberDrawn drawn; drawn.slider = slider; drawn.value = value; drawn.entity = n.entity; drawn.low = n.low; drawn.high = n.high; drawn.step = n.step;
      numbers.push_back(std::move(drawn));
      lv_obj_add_event_cb(slider, slider_event, LV_EVENT_ALL, reinterpret_cast<void *>(static_cast<intptr_t>(i)));
    }
  }
}
// A state of the light while its page is open: rows follow Home Assistant, a row just chosen keeps its choice a
// moment, a slider under a finger is left alone.
inline void updated(const Tile &t) {
  if (!root || t.entity != entity) return;
  const uint32_t moment = clock();
  for (auto &row : rows) {
    std::string current;
    if (row.light) current = t.extra().effect;
    else for (auto &r : t.extra().option_rows) if (r.entity == row.entity) current = r.current;
    if (!row.sent.empty() && current != row.sent && moment - row.sent_at < SENT_HOLD_MS) continue;
    if (!row.sent.empty() && (current == row.sent || moment - row.sent_at >= SENT_HOLD_MS)) row.sent.clear();
    if (row.value) lv_label_set_text(row.value, row_text(current).c_str());
  }
  for (auto &n : numbers) {
    if (!n.slider || lv_obj_has_state(n.slider, LV_STATE_PRESSED) || n.dirty) continue;
    for (auto &r : t.extra().number_rows) if (r.entity == n.entity) {
      const int percent = percent_of(r.value, r.low, r.high);
      if (lv_slider_get_value(n.slider) != percent) { lv_slider_set_value(n.slider, percent, LV_ANIM_OFF); preview(n); }
    }
  }
}
inline void open(const std::string &light) {
  const Tile *t = tile_of ? tile_of(light) : nullptr;
  if (!t || !available(*t)) return;
  close_picker();
  entity = light;
  if (!root) root = page_root();
  lv_obj_move_foreground(root);
  draw();
  ESP_LOGI("effects", "Effects page of %s: %u rows, %u sliders", light.c_str(), (unsigned) rows.size(), (unsigned) numbers.size());
}
inline void close() {
  close_picker();
  rows.clear(); numbers.clear();
  options = Options{};
  if (root) { lv_obj_delete(root); root = nullptr; }
  entity.clear();
}
// A change of look while the page is open: drawn again in place, the picker closed.
inline void restyle() {
  if (!root) return;
  close_picker();
  lv_obj_set_style_bg_color(root, theme::color(theme::PAGE_SOFT), 0);
  draw();
}
}  // namespace effects_page
#endif
