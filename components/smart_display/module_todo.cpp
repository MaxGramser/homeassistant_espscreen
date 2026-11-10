// The to-do card on the glass (module todo, docs/TODO.md): the plans of the module's header painted in one object per
// card, as the calendar card paints its plan (calendar_view.cpp), and the full screen a tap opens, with the list in a
// scrolling box and the keyboard in a sheet over it.
//
// A tick shows at once (docs/OPTIMISTIC.md): the screen marks the item, asks the app (the event esphome.screen_todo
// with the item's number), and Home Assistant's own list, which comes back through the app, squares it. A ticked item
// keeps its place for a moment, so the list does not move under a finger that ticks the next one.
//
// Compiled on its own, as calendar_view.cpp is: every header of this component lands in main.cpp, and on Xtensa the
// literal pool of one object file must stay within reach of all of its code (page_receiver.cpp says how that broke).
// The module's define comes from ESPHome's defines; the editor's preview (web/wasm/build.py) passes it on its command line.
#ifndef ESP_SCREEN_HOST
#include "esphome/core/defines.h"
#include "esphome/core/log.h"
#endif
#ifdef SD_MOD_TODO
#include "runtime_tiles.h"
#include "calendar_paint.h"
#include "module_todo.h"
#include "module_todo_view.h"

namespace todo_view {
using runtime_tiles::Tile;
using runtime_tiles::Widgets;
namespace rt = runtime_tiles;
namespace td = todo;
namespace cc = calendar_card;

// How long a ticked item keeps its place, and how long a tick waits for Home Assistant before it is taken back.
constexpr uint32_t HOLD_MS = 2000, ANSWER_MS = 8000;

struct View {
  cc::Scene scene;
  std::shared_ptr<const td::Data> data;
  int width = -1, height = -1;  // the content the plan was made for
  uint32_t stamp = 0;           // the marks the plan was made with
  std::string name, icon;
};

// ---- What a finger did and Home Assistant has not confirmed, and the list a finger is busy on.
struct Pending { std::string entity; uint32_t id; bool done; uint32_t at; };
struct Held { std::string entity; std::shared_ptr<const td::Data> shown; uint32_t ticked = 0; };
static std::vector<Pending> pending;
static std::vector<Held> held;
static uint32_t marks_stamp = 1;  // changes with every change of `pending`
static lv_timer_t *settle_timer = nullptr;

static const std::shared_ptr<const td::Data> &empty_list() {
  static const std::shared_ptr<const td::Data> none = [] { auto d = std::make_shared<td::Data>(); d->waiting = true; return d; }();
  return none;
}
static td::Marks marks_of(const std::string &entity) {
  td::Marks out;
  for (const auto &p : pending) if (p.entity == entity) out.emplace_back(p.id, p.done);
  return out;
}
// A new list squares the ticks it holds: what Home Assistant now says as the finger did is no longer pending.
static void square(const std::string &entity, const td::Data &d) {
  const size_t before = pending.size();
  pending.erase(std::remove_if(pending.begin(), pending.end(), [&](const Pending &p) {
    if (p.entity != entity) return false;
    for (const auto &it : d.items) if (it.id == p.id) return bool(it.flags & td::DONE) == p.done;
    return true;  // the item is gone from the list
  }), pending.end());
  if (pending.size() != before) ++marks_stamp;
}
// The list a card shows: the one the app sent last, except while a finger ticked within the last moments, when the
// list it ticked on stays as it stood.
static std::shared_ptr<const td::Data> shown(const Tile &t) {
  const auto &latest = t.extra().todo ? t.extra().todo : empty_list();
  const uint32_t now = esphome::millis();
  for (auto &h : held)
    if (h.entity == t.entity) {
      if (h.shown && h.shown != latest && now - h.ticked < HOLD_MS) return h.shown;
      if (h.shown != latest) { h.shown = latest; square(t.entity, *latest); }
      return latest;
    }
  held.push_back({t.entity, latest, now - HOLD_MS});
  square(t.entity, *latest);
  return latest;
}
static void repaint(const std::string &entity);
// After the moment a ticked item keeps its place, and when a tick stays unanswered: the cards follow.
static void settle(lv_timer_t *) {
  const uint32_t now = esphome::millis();
  std::vector<std::string> changed;
  for (auto it = pending.begin(); it != pending.end();) {
    if (now - it->at > ANSWER_MS) { changed.push_back(it->entity); it = pending.erase(it); ++marks_stamp; }
    else ++it;
  }
  bool waiting = !pending.empty();
  for (auto &h : held) {
    if (now - h.ticked >= HOLD_MS) changed.push_back(h.entity);
    else waiting = true;
  }
  if (!waiting && settle_timer) lv_timer_pause(settle_timer);
  std::sort(changed.begin(), changed.end());
  changed.erase(std::unique(changed.begin(), changed.end()), changed.end());
  for (const auto &entity : changed) repaint(entity);
}
static void watch() {
  if (!settle_timer) settle_timer = lv_timer_create(settle, 250, nullptr);
  lv_timer_resume(settle_timer);
}

// The board's fixed fonts, in calendar_card::Face's order (calendar_view.cpp has the same list).
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
// The list's own colours, in the order of module_todo.h's C_*: Home Assistant gives a to-do list no state colour, so
// it takes the blue of everything without one.
static std::vector<uint32_t> colours() {
  const uint32_t own = theme::ha::BLUE;
  return {theme::state(own), theme::tint(own, 40), theme::icon(own), theme::ha::RED, theme::hex(theme::BUTTON)};
}
// Days since 1970-01-01 of a date, and back (Howard Hinnant's civil algorithms).
static int days_of(int y, int m, int d) {
  y -= m <= 2;
  const int era = (y >= 0 ? y : y - 399) / 400, yoe = y - era * 400, doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  return era * 146097 + yoe * 365 + yoe / 4 - yoe / 100 + doy - 719468;
}
static void date_of(int z, int &m, int &d) {
  z += 719468;
  const int era = (z >= 0 ? z : z - 146096) / 146097, doe = z - era * 146097;
  const int yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365, doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const int mp = (5 * doy + 2) / 153;
  d = doy - (153 * mp + 2) / 5 + 1;
  m = mp < 10 ? mp + 3 : mp - 9;
}
// The card's words in the screen's language: its own (screen.todo) and the shared date words.
static const td::Words &words() {
  using namespace rt;
  static td::Words w;
  w.open = tr(txt::todo_open); w.all_done = tr(txt::todo_all_done); w.more = tr(txt::todo_more); w.completed = tr(txt::todo_completed);
  w.add = tr(txt::todo_add); w.added = tr(txt::todo_added); w.rename = tr(txt::todo_rename); w.remove = tr(txt::todo_remove);
  w.cancel = tr(txt::todo_cancel); w.clear = tr(txt::todo_clear); w.waiting = tr(txt::todo_waiting); w.empty = tr(txt::todo_empty);
  w.day = [](int days) -> std::string {
    if (days == 0) return tr(txt::calendar_today);
    if (days == 1) return tr(txt::calendar_tomorrow);
    if (days == -1) return tr(txt::todo_yesterday);
    const auto now = rt::now_time ? rt::now_time() : esphome::ESPTime{};
    if (!now.is_valid()) return "";
    const int day = days_of(now.year, now.month, now.day_of_month) + days;
    // The coming week by the day's name (the date words start on Sunday, as 1970-01-01 was a Thursday).
    if (days > 1 && days < 7) return tr(txt::date_weekdays + ((day % 7) + 11) % 7);
    int m = 1, d = 1;
    date_of(day, m, d);
    return std::to_string(d) + " " + tr(txt::date_months_short + (m - 1));
  };
  return w;
}

// ---- Asking the app: the event esphome.screen_todo, for the card at its place and the item by its number.
static void ask(const std::string &entity, unsigned index, const char *action, uint32_t id = 0, const std::string &text = "") {
  rt::library_event("esphome.screen_todo", {{"entity", entity}, {"i", std::to_string(index)}, {"a", action},
                                            {"n", std::to_string(id)}, {"t", text}});
  ESP_LOGI("todo", "Asked to %s on %s", action, entity.c_str());
}
static void tick(const Tile &t, unsigned index, const td::Item &it, const td::Marks &marks) {
  const bool done = !td::is_done(it, marks);
  pending.erase(std::remove_if(pending.begin(), pending.end(), [&](const Pending &p) { return p.entity == t.entity && p.id == it.id; }), pending.end());
  const uint32_t now = esphome::millis();
  // Ticked back to what Home Assistant says: nothing is pending any more, and the app still hears it.
  if (bool(it.flags & td::DONE) != done) pending.push_back({t.entity, it.id, done, now});
  ++marks_stamp;
  for (auto &h : held) if (h.entity == t.entity) h.ticked = now;
  watch();
  ask(t.entity, index, done ? "tick" : "untick", it.id);
}

// ---- The card on a page.
static View *view_of(lv_obj_t *canvas) {
  auto *extra = canvas ? lv_obj_get_parent(canvas) : nullptr;
  auto *owner = extra ? rt::extra_owner(extra) : nullptr;
  return owner ? owner->todo : nullptr;
}
static void draw(lv_event_t *e) {
  auto *canvas = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  View *view = view_of(canvas);
  if (!view) return;
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  calendar_paint::paint(lv_event_get_layer(e), view->scene, a.x1, a.y1, faces(), colours());
}
void release(Widgets &w) {
  delete w.todo;
  w.todo = nullptr;
}
void render(Widgets &w, const Tile &t, int width, int height) {
  rt::begin_extra(w, "todo_card", width, height);
  if (!w.todo) w.todo = new View();
  auto *&canvas = w.parts[0];
  if (!canvas) {
    canvas = lv_obj_create(w.extra);
    lv_obj_remove_style_all(canvas);
    lv_obj_remove_flag(canvas, LV_OBJ_FLAG_CLICKABLE);  // the card hears the finger; card_tap says what lay under it
    lv_obj_remove_flag(canvas, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(canvas, draw, LV_EVENT_DRAW_MAIN, nullptr);
  }
  lv_obj_set_pos(canvas, 0, 0);
  lv_obj_set_size(canvas, width, height);
  // A row's round box may reach a little into the card's own padding.
  lv_obj_add_flag(w.extra, LV_OBJ_FLAG_OVERFLOW_VISIBLE);
  View &v = *w.todo;
  const auto data = shown(t);
  const std::string name = t.name.empty() ? t.entity : t.name;
  // A plan only for what changed: the same list with the same ticks in the same room keeps the plan it has.
  if (data != v.data || width != v.width || height != v.height || v.stamp != marks_stamp || name != v.name || t.icon != v.icon) {
    v.data = data; v.width = width; v.height = height; v.stamp = marks_stamp; v.name = name; v.icon = t.icon;
    td::plan_tile(v.scene, measure(), width, height, name, *data, marks_of(t.entity), words(), t.icon);
    lv_obj_invalidate(canvas);
  }
}

// ---- The full screen.
static struct {
  std::string entity;
  unsigned index = 0;
  td::Full state;
  td::FullPlan plan;
  std::shared_ptr<const td::Data> data;
  lv_obj_t *fixed = nullptr, *scroller = nullptr, *content = nullptr, *overlay = nullptr;
  int width = 0, height = 0;
  bool typing = false;     // the key that adds an item on a card opens the full screen with its keyboard
  bool follow = false;     // the next list ends in what was just added: the list shows its end
  int overlay_y = 0;       // where the overlay's object begins on the glass: its plan is in the glass's coordinates
  lv_area_t pressed{0, 0, -1, -1};  // the key under the finger, in the overlay's own coordinates
  // A row dragged aside: which one (or none), how far, and where the finger came down.
  td::Swipe swipe;
  int swipe_row = -1, swipe_dx = 0, swipe_from = 0, down_row = -1;
  bool swiping = false, swipe_open = false, swallow = false;
  lv_point_t down{0, 0};
} full;

static bool is_open() {
  return rt::detail_root && !lv_obj_has_flag(rt::detail_root, LV_OBJ_FLAG_HIDDEN) && rt::detail_index == full.index && full.fixed;
}
static const Tile *tile_open() {
  return full.index < rt::model.count && rt::model.tiles[full.index].entity == full.entity ? &rt::model.tiles[full.index] : nullptr;
}
static void apply(bool keep_scroll);
static void repaint(const std::string &entity) {
  for (size_t i = 0; i < rt::model.count; ++i) if (rt::model.tiles[i].entity == entity) rt::refresh_tile(i);
  if (is_open() && full.entity == entity) apply(true);
}
// Where a layer's plan begins on the glass: the overlay's object covers only its sheet, so the list above the keys
// keeps its own touches, while its plan counts from the glass's corner.
static lv_area_t origin(lv_obj_t *o) {
  lv_area_t a;
  lv_obj_get_coords(o, &a);
  if (o == full.overlay) a.y1 -= full.overlay_y;
  return a;
}
static void paint_scene(lv_event_t *e, const cc::Scene &scene) {
  auto *o = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  const lv_area_t a = origin(o);
  lv_layer_t *layer = lv_event_get_layer(e);
  calendar_paint::paint(layer, scene, a.x1, a.y1, faces(), colours());
  if (o != full.overlay || full.pressed.x2 < full.pressed.x1) return;
  // The key under the finger, a shade darker at once.
  lv_draw_rect_dsc_t d;
  lv_draw_rect_dsc_init(&d);
  d.bg_color = lv_color_black();
  d.bg_opa = theme::dark ? LV_OPA_30 : LV_OPA_10;
  d.radius = ui::px(8);
  const lv_area_t k{a.x1 + full.pressed.x1, a.y1 + full.pressed.y1, a.x1 + full.pressed.x2, a.y1 + full.pressed.y2};
  lv_draw_rect(layer, &d, &k);
}
static const cc::Hit *under_finger(lv_obj_t *o, const cc::Scene &scene) {
  auto *input = lv_indev_active();
  if (!input) return nullptr;
  lv_point_t p;
  lv_indev_get_point(input, &p);
  const lv_area_t a = origin(o);
  return calendar_paint::hit(scene, p.x - a.x1, p.y - a.y1);
}
// ---- A row swiped to the left: its keys come in from its end. Only its strip is repainted while they move.
static void swipe_strip() {
  if (full.swipe_row < 0 || !full.content) return;
  lv_area_t a;
  lv_obj_get_coords(full.content, &a);
  const auto &sw = full.swipe;
  const lv_area_t strip{a.x1 + sw.x, a.y1 + sw.y, a.x1 + sw.x + sw.w - 1, a.y1 + sw.y + sw.h - 1};
  lv_obj_invalidate_area(full.content, &strip);
}
static void swipe_step(void *, int32_t dx) {
  full.swipe_dx = dx;
  swipe_strip();
  if (dx == 0 && !full.swipe_open && !full.swiping) full.swipe_row = -1;
}
static void swipe_to(int target) {
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, &full);
  lv_anim_set_exec_cb(&a, swipe_step);
  lv_anim_set_values(&a, full.swipe_dx, target);
  lv_anim_set_duration(&a, 140);
  lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
  lv_anim_start(&a);
}
// The row goes back: at once where the list itself changes, else on its way.
static void swipe_close(bool now) {
  if (full.swipe_row < 0) return;
  full.swipe_open = full.swiping = false;
  if (!now) { swipe_to(0); return; }
  lv_anim_delete(&full, swipe_step);
  swipe_strip();
  full.swipe_row = -1;
  full.swipe_dx = 0;
}
static void paint_content(lv_event_t *e) {
  paint_scene(e, full.plan.content);
  if (full.swipe_row < 0) return;
  auto *o = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  lv_area_t a;
  lv_obj_get_coords(o, &a);
  lv_layer_t *layer = lv_event_get_layer(e);
  const auto &sw = full.swipe;
  const lv_area_t keep = layer->_clip_area;
  const lv_area_t strip{std::max<int32_t>(keep.x1, a.x1 + sw.x), std::max<int32_t>(keep.y1, a.y1 + sw.y),
                        std::min<int32_t>(keep.x2, a.x1 + sw.x + sw.w - 1), std::min<int32_t>(keep.y2, a.y1 + sw.y + sw.h - 1)};
  if (strip.x1 > strip.x2 || strip.y1 > strip.y2) return;
  layer->_clip_area = strip;
  calendar_paint::paint(layer, sw.keys, a.x1 + sw.reveal + full.swipe_dx, a.y1, faces(), colours());
  layer->_clip_area = keep;
}
static cc::Measure measure();
static void list_down(lv_event_t *) {
  auto *input = lv_indev_active();
  full.swallow = false;
  full.down_row = -1;
  if (!input || !full.content) return;
  lv_indev_get_point(input, &full.down);
  lv_area_t a;
  lv_obj_get_coords(full.content, &a);
  const cc::Hit *hit = calendar_paint::hit(full.plan.content, full.down.x - a.x1, full.down.y - a.y1);
  if (hit && hit->kind == td::H_ROW) full.down_row = hit->arg;
}
// A finger that moves sideways on a row draws it aside; the list does not scroll meanwhile.
static void list_move(lv_event_t *) {
  auto *input = lv_indev_active();
  if (!input || !full.data || !full.scroller) return;
  lv_point_t p;
  lv_indev_get_point(input, &p);
  const int dx = p.x - full.down.x, dy = p.y - full.down.y;
  if (!full.swiping) {
    if (full.down_row < 0 || full.state.keys || lv_indev_get_scroll_obj(input) || std::abs(dx) < ui::px(12) || std::abs(dx) < 2 * std::abs(dy)) return;
    if (full.swipe_row != full.down_row) {
      swipe_close(true);
      if (!td::plan_swipe(full.swipe, measure(), full.plan, *full.data, words(), full.down_row)) {
        full.down_row = -1;
        return;
      }
      full.swipe_row = full.down_row;
      full.swipe_dx = 0;
    }
    lv_anim_delete(&full, swipe_step);
    full.swiping = full.swallow = true;
    full.swipe_from = full.swipe_dx - dx;
    lv_obj_remove_flag(full.scroller, LV_OBJ_FLAG_SCROLLABLE);
  }
  const int to = std::clamp(full.swipe_from + dx, -full.swipe.reveal, 0);
  if (to == full.swipe_dx) return;
  full.swipe_dx = to;
  swipe_strip();
}
// Let go: more than a third of the way shows the keys, less lets the row fall back.
static void list_up(lv_event_t *) {
  if (!full.swiping) return;
  full.swiping = false;
  if (full.scroller) lv_obj_add_flag(full.scroller, LV_OBJ_FLAG_SCROLLABLE);
  full.swipe_open = full.swipe_dx < -full.swipe.reveal / 3;
  swipe_to(full.swipe_open ? -full.swipe.reveal : 0);
}
static const cc::Scene *scene_of(lv_obj_t *o) {
  return o == full.fixed ? &full.plan.fixed : o == full.content ? &full.plan.content : o == full.overlay ? &full.plan.overlay : nullptr;
}
static void keys_down() {
  full.state.keys = false;
  full.state.renaming = 0;
  full.state.notice.clear();
  td::reset(full.state.entry);
}
// What the field holds goes to the list: a new item, or an item's new name. The keyboard stays for the next item.
static void send(const std::string &text) {
  auto &st = full.state;
  if (text.empty()) return;
  if (st.renaming) {
    ask(full.entity, full.index, "rename", st.renaming, text);
    keys_down();
    return;
  }
  ask(full.entity, full.index, "add", 0, text);
  st.notice = text;
  td::reset(st.entry);
  full.follow = true;
}
static void pressed_clear() {
  if (full.pressed.x2 < full.pressed.x1 || !full.overlay) return;
  const lv_area_t a = origin(full.overlay);
  const lv_area_t k{a.x1 + full.pressed.x1, a.y1 + full.pressed.y1, a.x1 + full.pressed.x2, a.y1 + full.pressed.y2};
  full.pressed = {0, 0, -1, -1};
  lv_obj_invalidate_area(full.overlay, &k);
}
// A finger lands on the keyboard: its key darkens before anything else happens.
static void finger_down(lv_event_t *e) {
  auto *o = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  const cc::Hit *hit = o == full.overlay ? under_finger(o, full.plan.overlay) : nullptr;
  pressed_clear();
  if (!hit || (hit->kind != td::H_KEY && hit->kind != td::H_OFFER && hit->kind != td::H_SEND)) return;
  const int g = hit->kind == td::H_KEY ? std::max(3, ui::px(6)) / 2 : 0;
  full.pressed = {hit->x + g, hit->y + g, hit->x + hit->w - 1 - g, hit->y + hit->h - 1 - g};
  const lv_area_t a = origin(o);
  const lv_area_t k{a.x1 + full.pressed.x1, a.y1 + full.pressed.y1, a.x1 + full.pressed.x2, a.y1 + full.pressed.y2};
  lv_obj_invalidate_area(o, &k);
}
static void finger_up(lv_event_t *) { pressed_clear(); }
// A key changed what is typed and nothing else: the keyboard is planned and painted again, the list and the head stay
// as they are. Where the sheet would begin elsewhere (it does not while the list has names to offer), everything is.
static void retype() {
  const Tile *t = tile_open();
  if (!t || !full.data || !full.overlay || !td::is_typing(*full.data, full.state)) { apply(true); return; }
  const int top = full.plan.covered ? 0 : full.plan.scroll_y + full.plan.scroll_h;
  const bool covered = full.plan.covered;
  const td::Keyboard k = td::plan_typing(full.plan, measure(), full.width, full.height, *full.data, words(), full.state);
  if (k.whole != covered || (k.whole ? 0 : k.top) != top) { apply(true); return; }
  lv_obj_invalidate(full.overlay);
}
// A tap on one of the three layers: the plan says what lies under the finger.
static void tapped(lv_event_t *e) {
  auto *o = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  const cc::Scene *sc = scene_of(o);
  const Tile *t = tile_open();
  if (!sc || !t || !full.data) return;
  // The finger that drew a row aside taps nothing when it lets go.
  if (full.swallow) { full.swallow = false; return; }
  const cc::Hit *hit = under_finger(o, *sc);
  auto &st = full.state;
  const auto &d = *full.data;
  if (full.swipe_row >= 0) {
    // A row lies aside: a tap on one of its keys acts on its item, any other tap lets it fall back.
    const cc::Hit *act = o == full.content && full.swipe_open ? under_finger(o, full.swipe.keys) : nullptr;
    if (!act || (act->kind != td::H_RENAME && act->kind != td::H_REMOVE)) { swipe_close(false); return; }
    st.sheet = full.swipe_row;
    hit = act;
    swipe_close(true);
  }
  if (!hit) {
    // Beside everything: the keyboard goes, as it does on a phone.
    if (st.keys && o != full.overlay) { keys_down(); apply(true); }
    return;
  }
  const bool key = hit->kind == td::H_KEY;
  // Keys follow each other faster than any other touch: only the rest takes the guard against a double tap.
  if (!key && !rt::allowed(esphome::millis(), 3300 + int(hit->kind), full.entity)) return;
  bool keep = true;
  if (hit->kind == td::H_CLOSE) {
    if (st.keys || st.sheet >= 0 || st.confirm) { keys_down(); st.sheet = -1; st.confirm = false; }
    else { rt::detail_command(-1); return; }
  } else if (hit->kind == td::H_HIDE) keys_down();
  else if (hit->kind == td::H_PANEL) return;
  else if (hit->kind == td::H_SCRIM || hit->kind == td::H_NO) { st.sheet = -1; st.confirm = false; }
  else if (hit->kind == td::H_FIELD) { st.keys = true; st.renaming = 0; st.notice.clear(); td::reset(st.entry); full.follow = true; }
  else if (hit->kind == td::H_ROW) {
    if (!(d.may & td::MAY_TICK) || hit->arg < 0 || size_t(hit->arg) >= d.items.size() || !rt::fresh()) return;
    tick(*t, full.index, d.items[hit->arg], marks_of(full.entity));
    repaint(full.entity);
    return;
  } else if (hit->kind == td::H_CLEAR) st.confirm = true;
  else if (hit->kind == td::H_YES) { if (rt::fresh()) ask(full.entity, full.index, "clear"); st.confirm = false; }
  else if (hit->kind == td::H_RENAME) {
    if (st.sheet < 0 || size_t(st.sheet) >= d.items.size()) return;
    st.renaming = d.items[st.sheet].id;
    td::reset(st.entry, roomy::plain(d.items[st.sheet].text));
    st.keys = true;
    st.sheet = -1;
  } else if (hit->kind == td::H_REMOVE) {
    if (st.sheet >= 0 && size_t(st.sheet) < d.items.size() && rt::fresh()) ask(full.entity, full.index, "remove", d.items[st.sheet].id);
    st.sheet = -1;
  } else if (hit->kind == td::H_OFFER) {
    const auto names = td::offers(d, st.entry.text);
    if (size_t(hit->arg) < names.size() && rt::fresh()) send(names[hit->arg]);
  } else if (hit->kind == td::H_SEND) { if (rt::fresh()) send(td::typed(st.entry)); }
  else if (key) {
    if (hit->arg == td::K_ENTER) { if (rt::fresh()) send(td::typed(st.entry)); }
    else { td::press(st.entry, hit->arg); retype(); return; }
  } else return;
  apply(keep);
}
// Held: a letter shows its accents, backspace keeps erasing, and an item opens its sheet.
static void held_down(lv_event_t *e) {
  auto *o = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  const cc::Scene *sc = scene_of(o);
  if (!sc || !full.data || full.swiping || full.swipe_row >= 0) return;
  const cc::Hit *hit = under_finger(o, *sc);
  if (!hit) return;
  auto &st = full.state;
  const bool again = lv_event_get_code(e) == LV_EVENT_LONG_PRESSED_REPEAT;
  if (hit->kind == td::H_KEY && hit->arg == td::K_BACK) td::press(st.entry, td::K_BACK);
  else if (again) return;
  else if (hit->kind == td::H_KEY && hit->arg >= 0 && hit->arg < 26) { if (!td::hold(st.entry, hit->arg)) return; }
  else if (hit->kind == td::H_ROW && o == full.content && !st.keys && (full.data->may & (td::MAY_RENAME | td::MAY_REMOVE))) st.sheet = hit->arg;
  else return;
  pressed_clear();
  if (hit->kind == td::H_KEY) retype(); else apply(true);
}
static lv_obj_t *layer(lv_obj_t *parent, void (*draw_cb)(lv_event_t *)) {
  auto *o = lv_obj_create(parent);
  lv_obj_remove_style_all(o);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(o, draw_cb, LV_EVENT_DRAW_MAIN, nullptr);
  lv_obj_add_event_cb(o, tapped, LV_EVENT_SHORT_CLICKED, nullptr);
  lv_obj_add_event_cb(o, held_down, LV_EVENT_LONG_PRESSED, nullptr);
  lv_obj_add_event_cb(o, held_down, LV_EVENT_LONG_PRESSED_REPEAT, nullptr);
  return o;
}
static void apply(bool keep_scroll) {
  const Tile *t = tile_open();
  if (!t || !full.fixed) return;
  swipe_close(true);
  const auto before = full.data;
  full.data = shown(*t);
  const int w = full.width, h = full.height;
  const int was = lv_obj_get_scroll_y(full.scroller), was_y = full.plan.scroll_y, was_h = full.plan.scroll_h;
  td::plan_full(full.plan, measure(), w, h, t->name.empty() ? t->entity : t->name, *full.data, marks_of(full.entity), words(), full.state);
  const auto &pl = full.plan;
  if (pl.scroll_y != was_y || pl.scroll_h != was_h || !keep_scroll) {
    lv_obj_set_pos(full.scroller, 0, pl.scroll_y);
    lv_obj_set_size(full.scroller, w, std::max(1, pl.scroll_h));
  }
  lv_obj_set_size(full.content, w, std::max(1, pl.content.height));
  lv_obj_update_layout(full.scroller);
  const int end = std::max(0, pl.content.height - pl.scroll_h);
  // What was just added stands at the end of what is open: the list shows it, above the keys.
  int to = keep_scroll ? std::min(was, end) : 0;
  if (full.follow && (full.data != before || !keep_scroll)) {
    int last = 0;
    for (const auto &hit : pl.content.hits) if (hit.kind == td::H_ROW && size_t(hit.arg) < full.data->items.size() && !(full.data->items[hit.arg].flags & td::DONE)) last = hit.y + hit.h;
    to = std::min(end, std::max(0, last - pl.scroll_h + ui::px(8)));
    if (full.data != before) full.follow = false;
  }
  lv_obj_scroll_to_y(full.scroller, to, LV_ANIM_OFF);
  lv_obj_invalidate(full.content);
  const bool overlay = !pl.overlay.boxes.empty();
  // The overlay hears the finger only where it draws: above a keyboard the list keeps its own touches.
  full.overlay_y = overlay && !pl.covered ? pl.scroll_y + pl.scroll_h : 0;
  lv_obj_set_pos(full.overlay, 0, full.overlay_y);
  lv_obj_set_size(full.overlay, w, std::max(1, h - full.overlay_y));
  if (!overlay) lv_obj_add_flag(full.overlay, LV_OBJ_FLAG_HIDDEN);
  else { lv_obj_remove_flag(full.overlay, LV_OBJ_FLAG_HIDDEN); lv_obj_move_foreground(full.overlay); lv_obj_invalidate(full.overlay); }
  lv_obj_invalidate(full.fixed);
}
void open(lv_obj_t *root, const Tile &t, unsigned index) {
  // The whole glass, as the calendar's full screen takes it.
  const int w = overlay_card::screen_width(), h = overlay_card::screen_height();
  lv_obj_set_pos(root, 0, 0);
  lv_obj_set_size(root, w, h);
  lv_obj_set_style_pad_all(root, 0, 0);
  full.state = td::Full{};
  full.entity = t.entity;
  full.index = index;
  full.width = w;
  full.height = h;
  full.pressed = {0, 0, -1, -1};
  full.follow = false;
  full.overlay_y = 0;
  lv_anim_delete(&full, swipe_step);
  full.swipe_row = full.down_row = -1;
  full.swipe_dx = 0;
  full.swiping = full.swipe_open = full.swallow = false;
  const auto data = shown(t);
  if (full.typing && (data->may & td::MAY_ADD)) { full.state.keys = true; td::reset(full.state.entry); full.follow = true; }
  full.typing = false;
  lv_obj_set_style_bg_color(root, theme::color(theme::CARD), 0);
  full.fixed = layer(root, [](lv_event_t *e) { paint_scene(e, full.plan.fixed); });
  lv_obj_set_pos(full.fixed, 0, 0);
  lv_obj_set_size(full.fixed, w, h);
  // The list scrolls in a box of its own; the finger that drags it ticks nothing (LVGL sends no click after a scroll).
  full.scroller = lv_obj_create(root);
  lv_obj_remove_style_all(full.scroller);
  lv_obj_set_scroll_dir(full.scroller, LV_DIR_VER);
  lv_obj_set_scrollbar_mode(full.scroller, LV_SCROLLBAR_MODE_ACTIVE);
  lv_obj_set_style_width(full.scroller, ui::px(4), LV_PART_SCROLLBAR);
  lv_obj_set_style_radius(full.scroller, ui::px(2), LV_PART_SCROLLBAR);
  lv_obj_set_style_bg_color(full.scroller, theme::color(theme::TICK), LV_PART_SCROLLBAR);
  lv_obj_set_style_bg_opa(full.scroller, LV_OPA_COVER, LV_PART_SCROLLBAR);
  full.content = layer(full.scroller, paint_content);
  lv_obj_set_pos(full.content, 0, 0);
  lv_obj_add_event_cb(full.content, list_down, LV_EVENT_PRESSED, nullptr);
  lv_obj_add_event_cb(full.content, list_move, LV_EVENT_PRESSING, nullptr);
  lv_obj_add_event_cb(full.content, list_up, LV_EVENT_RELEASED, nullptr);
  lv_obj_add_event_cb(full.content, list_up, LV_EVENT_PRESS_LOST, nullptr);
  lv_obj_add_event_cb(full.scroller, [](lv_event_t *) { swipe_close(true); }, LV_EVENT_SCROLL_BEGIN, nullptr);
  full.overlay = layer(root, [](lv_event_t *e) { paint_scene(e, full.plan.overlay); });
  lv_obj_add_event_cb(full.overlay, finger_down, LV_EVENT_PRESSED, nullptr);
  lv_obj_add_event_cb(full.overlay, finger_up, LV_EVENT_RELEASED, nullptr);
  lv_obj_add_event_cb(full.overlay, finger_up, LV_EVENT_PRESS_LOST, nullptr);
  apply(false);
  // A new list while it is open repaints it in place, where it is scrolled (docs/CARD_PARTS.md).
  rt::card_shaped(t, rt::entity_shape);
  rt::card_bind(full.fixed, t, [](lv_obj_t *, const Tile &, const rt::CardPart &) { apply(true); });
}
void closed() {
  lv_anim_delete(&full, swipe_step);
  full.swipe_row = full.down_row = -1;
  full.swipe_dx = 0;
  full.swiping = full.swipe_open = full.swallow = false;
  full.fixed = full.scroller = full.content = full.overlay = nullptr;
  full.state = td::Full{};
  full.data.reset();
  full.typing = false;
}

bool card_tap(Widgets &w, const Tile &t) {
  View *v = w.todo;
  auto *canvas = w.parts[0];
  if (!v || !v->data || !canvas) return false;
  const cc::Hit *hit = under_finger(canvas, v->scene);
  if (!hit) return false;
  if (hit->kind == td::H_ADD) {
    full.typing = true;
    rt::show_detail(w.index);
    return true;
  }
  if (hit->kind != td::H_ROW || hit->arg < 0 || size_t(hit->arg) >= v->data->items.size()) return false;
  if (!rt::fresh()) return true;
  tick(t, w.index, v->data->items[hit->arg], marks_of(t.entity));
  repaint(t.entity);
  return true;
}

}  // namespace todo_view
#endif  // SD_MOD_TODO
