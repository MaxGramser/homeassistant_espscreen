// A text's field on the glass (module text_edit, docs/TEXT_ENTITY.md): a tap on the tile of a Home Assistant text
// (text, input_text) opens a page with the page's top bar (the back key and the entity's name) and the screen's keyboard
// (keyboard_lvgl.h, docs/KEYBOARD.md) under a text area that holds the whole value over as many lines as it takes, the
// cursor at its end; a finger on the text puts the cursor there and drags it along. The check sends it with
// text.set_value or input_text.set_value through wish() (docs/OPTIMISTIC.md): the tile shows it at once, and Home
// Assistant's answer squares it (a refused value shows the old one again). Back closes the page and sends nothing.
//
// Compiled on its own, as module_todo.cpp is: every header of this component lands in main.cpp, and this keeps the
// keyboard in the boards that have the module. The module's define comes from ESPHome's defines; the editor's preview
// (web/wasm/build.py) passes it on its command line.
#ifndef ESP_SCREEN_HOST
#include "esphome/core/defines.h"
#include "esphome/core/log.h"
#endif
#ifdef SD_MOD_TEXT_EDIT
#include "runtime_tiles.h"
#include "calendar_paint.h"
#include "detail_bar.h"
#include "keyboard_lvgl.h"
#include "module_text_edit.h"
#include "module_text_edit_view.h"

namespace text_edit_view {
using runtime_tiles::Tile;
namespace rt = runtime_tiles;
namespace cc = calendar_card;

static struct {
  std::string entity;
  unsigned index = 0;
  keyboard::Entry entry;
  keyboard::Spec spec;
  keyboard::lvgl::Sheet keys;
  lv_obj_t *root = nullptr, *area = nullptr, *save = nullptr;
  cc::Scene scene;          // the text area's plan, in the page's coordinates
  text_edit::Area plan;
  int width = 0, height = 0, top = 0;
} page;

static calendar_paint::Faces faces() {
  return {rt::label_font, rt::small_font, rt::control_font, rt::watch_font, rt::watch_value_font, rt::clock_font,
          rt::mini_icon_font, rt::tile_icon_font()};
}
static cc::Measure measure() {
  cc::Measure m;
  const auto f = faces();
  for (int i = 0; i < cc::FACES; ++i) m.line[i] = f[i] ? lv_font_get_line_height(f[i]) : 0;
  m.width = [f](cc::Face face, const std::string &s) { return f[face] ? rt::text_width(s, f[face]) : 1 << 20; };
  m.circle = rt::cell_circle > 0 ? rt::cell_circle : ui::px(54);
  return m;
}
static Tile *tile_open() {
  return page.root && page.index < rt::model.count && rt::model.tiles[page.index].entity == page.entity ? &rt::model.tiles[page.index] : nullptr;
}
// The text area again, after a key or a finger moved the cursor: its own object alone is painted.
static void area_again() {
  if (!page.area) return;
  page.scene.clear();
  if (!lv_obj_has_flag(page.area, LV_OBJ_FLAG_HIDDEN))
    page.plan = text_edit::plan_area(page.scene, measure(), page.plan.x, page.plan.y, page.plan.w, page.plan.h, page.entry, page.spec.mask);
  lv_obj_invalidate(page.area);
  // The check in the top bar is faded while the text is too short to send, as the keyboard's own check is.
  if (page.save) lv_obj_set_style_opa(page.save, keyboard::sendable(page.entry, page.spec) ? LV_OPA_COVER : LV_OPA_40, 0);
}
// The keys at the bottom and the text area above them, from the top bar down to the keys. Glass too short for both
// (the keys take the whole glass) keeps the keyboard's own field, with its close key, and no area.
static void show() {
  if (!page.root) return;
  const cc::Measure m = measure();
  page.spec.field = false;
  keyboard::Place place = page.keys.show(page.root, m, faces(), page.width, page.height, page.top, page.entry, page.spec);
  const int gap = ui::px(12), line = cc::L(m, cc::CONTROL);
  if (place.whole || place.top - gap - page.top < line + 2 * ui::px(16)) {
    page.spec.field = true;
    place = page.keys.show(page.root, m, faces(), page.width, page.height, page.top, page.entry, page.spec);
    if (page.area) lv_obj_add_flag(page.area, LV_OBJ_FLAG_HIDDEN);
    if (page.save) lv_obj_add_flag(page.save, LV_OBJ_FLAG_HIDDEN);
    return;
  }
  // As wide as the keys stand, so the text and the keys line up.
  int kw = std::min(page.width, ui::mm(165));
  if (page.width - kw < ui::mm(24)) kw = page.width - 2 * ui::px(16);
  page.plan.x = (page.width - kw) / 2;
  page.plan.y = page.top;
  page.plan.w = kw;
  page.plan.h = place.top - gap - page.top;
  lv_obj_set_pos(page.area, page.plan.x, page.plan.y);
  lv_obj_set_size(page.area, page.plan.w, page.plan.h);
  lv_obj_remove_flag(page.area, LV_OBJ_FLAG_HIDDEN);
  if (page.save) lv_obj_remove_flag(page.save, LV_OBJ_FLAG_HIDDEN);
  area_again();
}
// The field as it stands, spaces and all, as Home Assistant's own field sends it; nothing while it is too short.
static void save() {
  Tile *t = tile_open();
  if (!t) return;
  const auto verdict = text_edit::sent(page.entry.text, t->state, page.spec);
  if (verdict == text_edit::Verdict::KEEP) return;
  if (verdict == text_edit::Verdict::SEND) {
    const std::string value = page.entry.text;
    rt::wish(*t, optimistic::Field::TEXT, value, t->domain() + ".set_value", "value", value);
  }
  rt::detail_command(-1);
}
static void area_draw(lv_event_t *e) {
  lv_area_t a;
  lv_obj_get_coords(page.area, &a);
  calendar_paint::paint(lv_event_get_layer(e), page.scene, a.x1 - page.plan.x, a.y1 - page.plan.y, faces(), {theme::hex(theme::BUTTON)});
}
// A finger on the text puts the cursor where it is, at once, and a finger held and dragged takes the cursor along, as
// on a phone: what the keys type next goes there.
static void area_finger(lv_event_t *) {
  auto *input = lv_indev_active();
  if (!input || !page.area) return;
  lv_point_t p;
  lv_indev_get_point(input, &p);
  lv_area_t a;
  lv_obj_get_coords(page.area, &a);
  const size_t at = text_edit::caret_at(page.plan, measure(), page.entry.text, p.x - a.x1 + page.plan.x, p.y - a.y1 + page.plan.y);
  if (at == keyboard::caret(page.entry)) return;
  keyboard::place(page.entry, at);
  area_again();
}
// What decides the page: the entity, whether Home Assistant has it, and its field's limits. A new value alone keeps the
// page and what is typed (Home Assistant's field keeps what a finger typed too); anything else builds it again.
static uint32_t shape(const Tile &t) {
  rt::Fingerprint f;
  f.add(t.entity);
  f.add(t.received && t.state != "unavailable" && rt::fresh() ? "1" : "0");
  f.add(t.secret ? "p" : "t");
  f.add(std::to_string(static_cast<int>(t.minimum)) + "-" + std::to_string(static_cast<int>(t.maximum)));
  return f.value;
}

void open(lv_obj_t *root, const Tile &t, unsigned index) {
  const int w = overlay_card::screen_width(), h = overlay_card::screen_height();
  lv_obj_set_pos(root, 0, 0);
  lv_obj_set_size(root, w, h);
  lv_obj_set_style_pad_all(root, 0, 0);
  page.keys.forget();
  page.entity = t.entity;
  page.index = index;
  page.root = root;
  page.width = w;
  page.height = h;
  page.top = detail_bar::bottom() + ui::px(12);
  page.spec = text_edit::spec(t.minimum, t.maximum, t.secret);
  keyboard::reset(page.entry, text_edit::start(t.state));
  // The top bar: back sends nothing, the check at the right saves, as the check at the keys' bottom right does.
  const auto bar = detail_bar::make(root, t.name.empty() ? t.entity : t.name, {detail_bar::BACK, [](lv_event_t *) { rt::detail_command(-1); }},
                                    {keyboard::I_CHECK, [](lv_event_t *) { if (tile_open() && rt::allowed(esphome::millis(), 3399, page.entity)) save(); }});
  page.save = bar.right[0];
  page.area = lv_obj_create(root);
  lv_obj_remove_style_all(page.area);
  lv_obj_remove_flag(page.area, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(page.area, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(page.area, area_draw, LV_EVENT_DRAW_MAIN, nullptr);
  lv_obj_add_event_cb(page.area, area_finger, LV_EVENT_PRESSED, nullptr);
  lv_obj_add_event_cb(page.area, area_finger, LV_EVENT_PRESSING, nullptr);
  auto &k = page.keys.on;
  // Keys follow each other faster than any other touch: only the rest takes the guard against a double tap.
  k.allow = [](cc::HitKind kind) { return tile_open() && (kind == keyboard::KEY || rt::allowed(esphome::millis(), 3400 + int(kind), page.entity)); };
  k.changed = [](const std::string &) { area_again(); };
  k.suggestion = nullptr;
  k.moved = [] { show(); };
  k.hidden = [] { rt::detail_command(-1); };
  k.send = [](const std::string &) { save(); };
  show();
  rt::card_shaped(t, shape);
}

void closed() {
  page.keys.forget();
  page.root = page.area = page.save = nullptr;
  page.scene.clear();
  keyboard::reset(page.entry);
}

}  // namespace text_edit_view
#endif  // SD_MOD_TEXT_EDIT
