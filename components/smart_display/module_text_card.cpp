// The template tile on the glass (module text_card, firmware 0.58.0): the plan of the module's header painted in one
// object per card, as the calendar card paints its plan (calendar_view.cpp).
//
// Compiled on its own, as calendar_view.cpp is: every header of this component lands in main.cpp, and on Xtensa the
// literal pool of one object file must stay within reach of all of its code (page_receiver.cpp says how that broke).
// The module's define comes from ESPHome's defines; the editor's preview (web/wasm/build.py) passes it on its command line.
#ifndef ESP_SCREEN_HOST
#include "esphome/core/defines.h"
#endif
#ifdef SD_MOD_TEXT_CARD
#include "runtime_tiles.h"
#include "module_text_card.h"
#include "module_text_card_view.h"

namespace text_card_view {
using runtime_tiles::Tile;
using runtime_tiles::Widgets;
namespace rt = runtime_tiles;
namespace tc = text_card;
namespace cc = calendar_card;

struct View {
  tc::Scene scene;
  std::shared_ptr<const tc::Data> data;
  int width = -1, height = -1;  // the content the plan was made for
};

// The board's fixed fonts, in calendar_card::Face's order (calendar_view.cpp has the same list).
static std::array<const lv_font_t *, cc::FACES> faces() {
  return {rt::label_font, rt::small_font, rt::control_font, rt::watch_font, rt::watch_value_font, rt::clock_font,
          rt::mini_icon_font, rt::tile_icon_font()};
}
static cc::Measure measure() {
  cc::Measure m;
  const auto f = faces();
  for (int i = 0; i < cc::FACES; ++i) m.line[i] = f[i] ? lv_font_get_line_height(f[i]) : 0;
  m.width = [f](cc::Face face, const std::string &s) { return f[face] ? rt::text_width(s, f[face]) : 1 << 20; };
  return m;
}
static lv_color_t colour(uint8_t ink) {
  switch (ink) {
    case tc::INK: return theme::color(theme::INK);
    case tc::GOOD_INK: return lv_color_hex(theme::ha::GREEN);
    case tc::ALERT_INK: return lv_color_hex(theme::ha::RED);
    case tc::ACCENT_INK: return theme::color(theme::ACCENT);
    case tc::RULE: return theme::color(theme::MUTED);  // at RULE_OPA: seen on a card and, without one, on the page
    default: return theme::color(theme::MUTED);
  }
}
static View *view_of(lv_obj_t *canvas) {
  auto *extra = canvas ? lv_obj_get_parent(canvas) : nullptr;
  auto *owner = extra ? rt::extra_owner(extra) : nullptr;
  return owner ? owner->text : nullptr;
}
static void draw(lv_event_t *e) {
  auto *canvas = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  View *view = view_of(canvas);
  if (!view) return;
  lv_layer_t *layer = lv_event_get_layer(e);
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  const lv_area_t clip = layer->_clip_area;
  const auto f = faces();
  for (auto &mark : view->scene.marks) {
    lv_area_t r{a.x1 + mark.x, a.y1 + mark.y, a.x1 + mark.x + mark.w - 1, a.y1 + mark.y + mark.h - 1};
    if (r.x1 > clip.x2 || r.x2 < clip.x1 || r.y1 > clip.y2 || r.y2 < clip.y1) continue;
    lv_draw_rect_dsc_t d;
    lv_draw_rect_dsc_init(&d);
    d.bg_color = colour(mark.ink);
    d.bg_opa = mark.opa;
    d.radius = mark.radius;
    lv_draw_rect(layer, &d, &r);
  }
  for (auto &piece : view->scene.pieces) {
    const lv_font_t *font = f[piece.face];
    if (!font || piece.s.empty()) continue;
    const int h = lv_font_get_line_height(font);
    lv_area_t r{a.x1 + piece.x, a.y1 + piece.y, a.x1 + piece.x + piece.w - 1, a.y1 + piece.y + h - 1};
    if (r.x1 > clip.x2 || r.x2 < clip.x1 || r.y1 > clip.y2 || r.y2 < clip.y1) continue;
    lv_draw_label_dsc_t d;
    lv_draw_label_dsc_init(&d);
    d.font = font;
    d.color = colour(piece.ink);
    d.text = piece.s.c_str();
    d.align = piece.align == tc::RIGHT ? LV_TEXT_ALIGN_RIGHT : LV_TEXT_ALIGN_LEFT;
    // The plan already fitted the line to its box; a glyph's overhang may not wrap a left-aligned line onto a second.
    if (piece.align == tc::LEFT) d.flag = LV_TEXT_FLAG_EXPAND;
    lv_draw_label(layer, &d, &r);
  }
}
void release(Widgets &w) {
  delete w.text;
  w.text = nullptr;
}
void render(Widgets &w, const Tile &t, int width, int height) {
  rt::begin_extra(w, "text_card", width, height);
  if (!w.text) w.text = new View();
  auto *&canvas = w.parts[0];
  if (!canvas) {
    canvas = lv_obj_create(w.extra);
    lv_obj_remove_style_all(canvas);
    lv_obj_remove_flag(canvas, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_remove_flag(canvas, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(canvas, draw, LV_EVENT_DRAW_MAIN, nullptr);
  }
  lv_obj_set_pos(canvas, 0, 0);
  lv_obj_set_size(canvas, width, height);
  View &v = *w.text;
  const auto &data = t.extra().text;
  // A plan only for what changed: the same rows on the same room keep the plan they have.
  if (data != v.data || width != v.width || height != v.height) {
    v.data = data; v.width = width; v.height = height;
    if (data) tc::plan(v.scene, measure(), width, height, *data);
    else v.scene.clear();
    lv_obj_invalidate(canvas);
  }
}
bool empty(const Tile &t) { return t.extra().text && tc::empty(*t.extra().text); }

}  // namespace text_card_view
#endif  // SD_MOD_TEXT_CARD
