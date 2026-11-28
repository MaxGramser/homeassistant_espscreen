#pragma once
// The keyboard on the glass (docs/KEYBOARD.md): keyboard.h's plan in one LVGL object of its own over the caller's page.
// It hears the finger (a tap, a long press for a letter's accents and for backspace that keeps erasing, the key under
// the finger a shade darker at once), types into the caller's Entry, and paints again only its own sheet when a key
// changes what is typed. What the keys mean to the caller it says through callbacks: a key changed the text, the text
// is sent, a suggestion is taken, its close key was tapped. The caller decides what a sent text does and whether the
// keyboard stays up, and puts it away with hide().
//
// One object, made on the first show() and kept while its parent lives: a page with a keyboard has one Sheet.
// Header only, as touch_feedback_lvgl.h is: every header of this component lands in main.cpp, where nothing of it is
// made unless a caller uses it, so a board without a user of the keyboard carries none of it (the CYD). A caller in a
// .cpp of its own (module_todo.cpp) has it made there.
#include "lvgl.h"
#include "calendar_paint.h"
#include "keyboard.h"
#include "theme.h"
#include "ui_scale.h"

#include <functional>
#include <string>

namespace keyboard::lvgl {
namespace cc = calendar_card;

struct Callbacks {
  // Asked before a tap acts, with the kind of place it hit (a key, the send key, a suggestion, the close key, the
  // sheet beside its keys): a caller's guard against a bounce, or a check that its page is still there. None: all act.
  std::function<bool(cc::HitKind)> allow;
  // A key changed the entry, with what the field holds. The place to set new suggestions in spec() before the sheet
  // is planned again.
  std::function<void(const std::string &)> changed;
  // The send key or the check key, with typed(): the caller sends it, and resets the entry or hides the keyboard. Never
  // while the field holds fewer characters than the spec's `least` (the keys are faded then).
  std::function<void(const std::string &)> send;
  // A suggestion was tapped: its place in spec().suggestions and its text.
  std::function<void(size_t, const std::string &)> suggestion;
  // The close key the keyboard has where it takes the whole glass.
  std::function<void()> hidden;
  // After a key, the sheet begins elsewhere (suggestions came or went without keep_row): the caller lays its page out
  // again and calls show(). None: the sheet moves by itself.
  std::function<void()> moved;
};

class Sheet {
 public:
  Callbacks on;

  // Shows the keyboard on `parent` (a page of `W` x `H` with its corner at the glass's), never above `top`, typing into
  // `entry`, or plans it again where it is. Returns where the sheet begins: the caller's page keeps what lies above.
  Place show(lv_obj_t *parent, const cc::Measure &m, const calendar_paint::Faces &faces, int W, int H, int top, Entry &entry,
             const Spec &spec) {
    measure_ = m; faces_ = faces; W_ = W; H_ = H; top_ = top; entry_ = &entry; spec_ = spec;
    if (obj_ && lv_obj_get_parent(obj_) != parent) { lv_obj_delete(obj_); obj_ = nullptr; }
    if (!obj_) make(parent);
    plan_now();
    place_obj();
    lv_obj_remove_flag(obj_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(obj_);
    lv_obj_invalidate(obj_);
    return place_;
  }
  void hide() {
    if (obj_) lv_obj_add_flag(obj_, LV_OBJ_FLAG_HIDDEN);
  }
  bool shown() const { return obj_ && !lv_obj_has_flag(obj_, LV_OBJ_FLAG_HIDDEN); }
  // The parent goes (a page that closes): nothing of the sheet is left to paint or to hear.
  void forget() {
    obj_ = nullptr;
    entry_ = nullptr;
    pressed_ = {0, 0, -1, -1};
  }
  Spec &spec() { return spec_; }
  const Place &place() const { return place_; }

 private:
  lv_obj_t *obj_ = nullptr;
  cc::Scene scene_;
  cc::Measure measure_;
  calendar_paint::Faces faces_{};
  Spec spec_;
  Entry *entry_ = nullptr;
  int W_ = 0, H_ = 0, top_ = 0;
  Place place_;
  int y_ = 0;                        // where its object begins: the plan counts from the page's corner
  lv_area_t pressed_{0, 0, -1, -1};  // the key under the finger, in the plan's coordinates

  void make(lv_obj_t *parent) {
    obj_ = lv_obj_create(parent);
    pressed_ = {0, 0, -1, -1};
    lv_obj_remove_style_all(obj_);
    lv_obj_remove_flag(obj_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(obj_, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(obj_, draw, LV_EVENT_DRAW_MAIN, this);
    lv_obj_add_event_cb(obj_, tapped, LV_EVENT_SHORT_CLICKED, this);
    lv_obj_add_event_cb(obj_, held, LV_EVENT_LONG_PRESSED, this);
    lv_obj_add_event_cb(obj_, held, LV_EVENT_LONG_PRESSED_REPEAT, this);
    lv_obj_add_event_cb(obj_, down, LV_EVENT_PRESSED, this);
    lv_obj_add_event_cb(obj_, up, LV_EVENT_RELEASED, this);
    lv_obj_add_event_cb(obj_, up, LV_EVENT_PRESS_LOST, this);
    lv_obj_add_event_cb(obj_, gone, LV_EVENT_DELETE, this);
  }
  void plan_now() {
    scene_.clear();
    place_ = plan(scene_, measure_, W_, H_, top_, *entry_, spec_);
  }
  // The object covers the sheet alone, so the caller's page above it keeps its own touches.
  void place_obj() {
    y_ = place_.whole ? 0 : place_.top;
    lv_obj_set_pos(obj_, 0, y_);
    lv_obj_set_size(obj_, W_, std::max(1, H_ - y_));
  }
  lv_area_t origin() const {
    lv_area_t a;
    lv_obj_get_coords(obj_, &a);
    a.y1 -= y_;
    return a;
  }
  // A key changed what is typed: the sheet alone is planned and painted again.
  void again() {
    const bool whole = place_.whole;
    const int top = place_.whole ? 0 : place_.top;
    plan_now();
    if (place_.whole != whole || (place_.whole ? 0 : place_.top) != top) {
      if (on.moved) { on.moved(); return; }
      place_obj();
    }
    lv_obj_invalidate(obj_);
  }
  bool under_finger(cc::Hit &out) const {
    auto *input = lv_indev_active();
    if (!input || !obj_) return false;
    lv_point_t p;
    lv_indev_get_point(input, &p);
    const lv_area_t a = origin();
    const cc::Hit *hit = calendar_paint::hit(scene_, p.x - a.x1, p.y - a.y1);
    if (!hit) return false;
    out = *hit;  // a copy: a callback may plan the sheet again
    return true;
  }
  void pressed_clear() {
    if (pressed_.x2 < pressed_.x1 || !obj_) return;
    const lv_area_t a = origin();
    const lv_area_t k{a.x1 + pressed_.x1, a.y1 + pressed_.y1, a.x1 + pressed_.x2, a.y1 + pressed_.y2};
    pressed_ = {0, 0, -1, -1};
    lv_obj_invalidate_area(obj_, &k);
  }
  static Sheet *of(lv_event_t *e) { return static_cast<Sheet *>(lv_event_get_user_data(e)); }

  static void draw(lv_event_t *e) {
    Sheet *k = of(e);
    const lv_area_t a = k->origin();
    lv_layer_t *layer = lv_event_get_layer(e);
    calendar_paint::paint(layer, k->scene_, a.x1, a.y1, k->faces_, {theme::hex(theme::BUTTON)});
    if (k->pressed_.x2 < k->pressed_.x1) return;
    // The key under the finger, a shade darker at once.
    lv_draw_rect_dsc_t d;
    lv_draw_rect_dsc_init(&d);
    d.bg_color = lv_color_black();
    d.bg_opa = theme::dark ? LV_OPA_30 : LV_OPA_10;
    d.radius = ui::px(8);
    const lv_area_t r{a.x1 + k->pressed_.x1, a.y1 + k->pressed_.y1, a.x1 + k->pressed_.x2, a.y1 + k->pressed_.y2};
    lv_draw_rect(layer, &d, &r);
  }
  // A finger lands: its key darkens before anything else happens.
  static void down(lv_event_t *e) {
    Sheet *k = of(e);
    cc::Hit hit;
    const bool found = k->under_finger(hit);
    k->pressed_clear();
    if (!found || (hit.kind != KEY && hit.kind != SUGGESTION && hit.kind != SEND)) return;
    // A faded send key takes no shade: it does nothing.
    if ((hit.kind == SEND || (hit.kind == KEY && hit.arg == K_ENTER)) && k->entry_ && !sendable(*k->entry_, k->spec_)) return;
    const int g = hit.kind == KEY ? std::max(3, ui::px(6)) / 2 : 0;
    k->pressed_ = {hit.x + g, hit.y + g, hit.x + hit.w - 1 - g, hit.y + hit.h - 1 - g};
    const lv_area_t a = k->origin();
    const lv_area_t r{a.x1 + k->pressed_.x1, a.y1 + k->pressed_.y1, a.x1 + k->pressed_.x2, a.y1 + k->pressed_.y2};
    lv_obj_invalidate_area(k->obj_, &r);
  }
  static void up(lv_event_t *e) { of(e)->pressed_clear(); }
  static void gone(lv_event_t *e) {
    Sheet *k = of(e);
    k->obj_ = nullptr;
    k->pressed_ = {0, 0, -1, -1};
  }
  static void tapped(lv_event_t *e) {
    Sheet *k = of(e);
    cc::Hit hit;
    if (!k->entry_ || !k->under_finger(hit)) return;
    if (k->on.allow && !k->on.allow(hit.kind)) return;
    if (hit.kind == PANEL) return;
    if (hit.kind == HIDE) { if (k->on.hidden) k->on.hidden(); return; }
    if (hit.kind == SUGGESTION) {
      if (hit.arg >= 0 && size_t(hit.arg) < k->spec_.suggestions.size() && k->on.suggestion) {
        const std::string text = k->spec_.suggestions[hit.arg];
        k->on.suggestion(size_t(hit.arg), text);
      }
      return;
    }
    if (hit.kind == SEND || (hit.kind == KEY && hit.arg == K_ENTER)) {
      if (k->on.send && sendable(*k->entry_, k->spec_)) k->on.send(typed(*k->entry_));
      return;
    }
    if (hit.kind != KEY) return;
    press(*k->entry_, hit.arg, k->spec_);
    if (k->on.changed) k->on.changed(k->entry_->text);
    k->again();
  }
  // Held: a letter shows its accents, backspace keeps erasing.
  static void held(lv_event_t *e) {
    Sheet *k = of(e);
    cc::Hit hit;
    if (!k->entry_ || !k->under_finger(hit) || hit.kind != KEY) return;
    const bool repeat = lv_event_get_code(e) == LV_EVENT_LONG_PRESSED_REPEAT;
    if (hit.arg == K_BACK) {
      press(*k->entry_, K_BACK, k->spec_);
      if (k->on.changed) k->on.changed(k->entry_->text);
    } else if (repeat || hit.arg < 0 || hit.arg >= keys(layout_of(k->spec_)) || !hold(*k->entry_, hit.arg, k->spec_)) {
      return;
    }
    k->pressed_clear();
    k->again();
  }
};

}  // namespace keyboard::lvgl
