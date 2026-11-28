// A sensor's meter on the glass (firmware 0.56.0, docs/METER.md): the plan of meter_card.h painted in one object per
// card, in its draw event, so a bar of a hundred cells or a ruler of fifty marks costs one object.
//
// Compiled on its own, as calendar_view.cpp is: every header of this component lands in main.cpp, and on Xtensa the
// literal pool of one object file must stay within reach of all of its code (page_receiver.cpp says how that broke).
#include "esphome/core/log.h"
#include "runtime_tiles.h"
#include "meter_paint.h"

#include <cstdlib>

namespace meter_view {
using runtime_tiles::Tile;
using runtime_tiles::Widgets;
namespace rt = runtime_tiles;
namespace mc = meter_card;

struct View : meter_paint::Look {};


// The board's fixed fonts, in meter_card::Face's order. The tile's icon size is this card's own (its icon label's font),
// not the first card on the glass that has one (rt::tile_icon_font): drawn while another page's cards were bound, a
// meter measured that card's icon font, fell to a face without its glyph and showed an empty disc until the sensor's
// next value (a Guition 10.1, 2026-11-15).
static std::array<const lv_font_t *, mc::FACES> faces(const Widgets &w) {
  return {rt::label_font, rt::small_font, rt::control_font, rt::watch_font, rt::watch_value_font, rt::setpoint_font,
          rt::watch_icon_font, rt::mini_icon_font, w.icon_font ? w.icon_font : rt::tile_icon_font(), rt::big_icon_font};
}
// The first codepoint of a UTF-8 text from `at`, moving `at` past it.
static uint32_t next_codepoint(const std::string &s, size_t &at) {
  const auto c = static_cast<unsigned char>(s[at]);
  const int n = c < 0x80 ? 1 : c < 0xE0 ? 2 : c < 0xF0 ? 3 : 4;
  uint32_t cp = n == 1 ? c : n == 2 ? c & 0x1F : n == 3 ? c & 0x0F : c & 0x07;
  for (int i = 1; i < n && at + i < s.size(); ++i) cp = cp << 6 | (static_cast<unsigned char>(s[at + i]) & 0x3F);
  at += n;
  return cp;
}
static mc::Measure measure(const std::array<const lv_font_t *, mc::FACES> &f) {
  mc::Measure m;
  for (int i = 0; i < mc::FACES; ++i) {
    // A board without a face (none has fewer today) never picks it: its line is taller than any card.
    m.line[i] = f[i] ? lv_font_get_line_height(f[i]) : 1 << 20;
    m.base[i] = f[i] ? f[i]->base_line : 0;
  }
  m.width = [f](mc::Face face, const std::string &s) { return f[face] ? rt::text_width(s, f[face]) : 1 << 20; };
  m.covers = [f](mc::Face face, const std::string &s) {
    if (!f[face]) return false;
    lv_font_glyph_dsc_t g;
    for (size_t at = 0; at < s.size();) {
      const uint32_t cp = next_codepoint(s, at);
      if (cp != ' ' && !lv_font_get_glyph_dsc(f[face], &g, cp, 0)) return false;
    }
    return true;
  };
  return m;
}
// A range's end as the screen writes numbers: whole numbers whole, the rest with up to two places ("0", "1600", "21,5").
static std::string end_words(float v) {
  char b[24];
  if (std::fabs(v - std::round(v)) < 1e-3f) snprintf(b, sizeof b, "%.0f", static_cast<double>(std::round(v)));
  else {
    snprintf(b, sizeof b, "%.2f", static_cast<double>(v));
    std::string s = b;
    while (s.back() == '0') s.pop_back();
    if (s.back() == '.') s.pop_back();
    return screen_text::localize(s == "-0" ? "0" : s);
  }
  return screen_text::localize(std::string(b) == "-0" ? "0" : b);
}
// The state as a number, NAN for anything else ("unknown", "unavailable", a word).
static float number_of(const std::string &state) {
  if (state.empty()) return NAN;
  char *end = nullptr;
  const float v = std::strtof(state.c_str(), &end);
  return end && *end == '\0' && std::isfinite(v) ? v : NAN;
}
static View *view_of(lv_obj_t *canvas) {
  auto *extra = canvas ? lv_obj_get_parent(canvas) : nullptr;
  auto *owner = extra ? rt::extra_owner(extra) : nullptr;
  return owner ? owner->meter : nullptr;
}
static void draw(lv_event_t *e) {
  auto *canvas = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  rt::CardScope look(canvas);  // drawn by LVGL, in its card's look (docs/THEME.md "A card's look")
  View *v = view_of(canvas);
  if (!v) return;
  lv_layer_t *layer = lv_event_get_layer(e);
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  meter_paint::paint(layer, *v, a.x1, a.y1);
}

void release(Widgets &w) {
  delete w.meter;
  w.meter = nullptr;
}
void render(Widgets &w, const Tile &t, int width, int height) {
  rt::begin_extra(w, "meter_card", width, height);
  if (!w.meter) w.meter = new View();
  auto *&canvas = w.parts[0];
  if (!canvas) {
    canvas = lv_obj_create(w.extra);
    lv_obj_remove_style_all(canvas);
    lv_obj_remove_flag(canvas, LV_OBJ_FLAG_CLICKABLE);  // the whole card opens the sensor's card
    lv_obj_remove_flag(canvas, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(canvas, draw, LV_EVENT_DRAW_MAIN, nullptr);
  }
  lv_obj_set_pos(canvas, 0, 0);
  lv_obj_set_size(canvas, width, height);
  View &v = *w.meter;
  v.faces = faces(w);
  static const Tile::Meter none;
  const Tile::Meter &o = t.meter ? *t.meter : none;
  // The range: the tile's own, else Home Assistant's: a percentage from 0 to 100, and anything else as its gauge card,
  // 0 to 100 too (the inspector says when the value falls outside it).
  v.low = std::isfinite(o.low) ? o.low : 0;
  v.high = std::isfinite(o.high) ? o.high : 100;
  const bool live = rt::fresh() && t.available();
  v.value = live ? number_of(t.state) : NAN;
  v.own = tile_controls::accent(t);
  v.ground = rt::card_surface(w);
  v.background = t.background != 0;
  v.icon = rt::icon_for(t);
  // The colours: one (the tile's own unless one was chosen), or two or three segments in Home Assistant's green,
  // orange and red unless chosen.
  v.colours = mc::Colours();
  v.colours.segments = o.segments;
  v.colours.thresholds = o.thresholds;
  static constexpr uint32_t TWO[] = {theme::ha::GREEN, theme::ha::RED}, THREE[] = {theme::ha::GREEN, theme::ha::ORANGE, theme::ha::RED};
  for (int i = 0; i < o.segments && i < 3; ++i)
    v.colours.colors[i] = o.colors[i] ? o.colors[i] : o.segments == 2 ? TWO[i] : o.segments == 3 ? THREE[i] : 0;
  v.colours.chosen = o.segments == 1 && o.colors[0] != 0;
  v.history = t.has_history ? t.history : std::vector<float>();
  mc::Data d;
  d.name = t.name.empty() ? t.entity : t.name;
  d.icon = v.icon;
  if (std::isfinite(v.value) && !t.extra().state_word.empty()) {
    // Home Assistant's own words for the value (a duration in hours and minutes): they carry their units.
    d.words = d.number = t.extra().state_word;
  } else if (std::isfinite(v.value)) {
    d.number = screen_text::localize(t.state);
    d.unit = t.unit;
    d.words = screen_text::with_unit(d.number, d.unit);
  } else {
    using namespace rt;
    d.words = d.number = live && !t.state.empty() && t.state != "unknown" ? t.state : std::string(tr(txt::ha_unavailable));
  }
  d.percent = t.unit == "%";
  d.low = end_words(v.low);
  d.high = end_words(v.high);
  int samples = 0;
  for (float x : v.history) samples += std::isfinite(x);
  d.graph = samples >= 2;
  const mc::Style style = o.style == 1 ? mc::TAPE : o.style == 2 ? mc::BAR : mc::RING;
  mc::plan(v.plan, measure(v.faces), d, style, width, height, v.high - v.low);
  lv_obj_invalidate(canvas);
}
}  // namespace meter_view
