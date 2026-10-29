// The calendar card on the glass (firmware 0.56.0): the plans of calendar_card.h painted by calendar_paint.h, in one
// object per card, and the full screen a tap opens with its hours in a scrolling box.
//
// Compiled on its own, as energy_view.cpp is: every header of this component lands in main.cpp, and on Xtensa the
// literal pool of one object file must stay within reach of all of its code (page_receiver.cpp says how that broke).
#include "esphome/core/log.h"
#include "runtime_tiles.h"
#include "calendar_paint.h"

namespace calendar_view {
using runtime_tiles::Tile;
using runtime_tiles::Widgets;
namespace rt = runtime_tiles;
namespace cc = calendar_card;

struct View {
  cc::Scene scene;
  std::shared_ptr<const cc::Data> data;
  cc::Edge edge;  // the card's padding round the content: the canvas covers the whole card, for its edge's progress
  int width = 0, height = 0;  // the content the plan was made for
};

// The board's fixed fonts, in calendar_card::Face's order.
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
// The card's words in the screen's language: its own (screen.calendar) and the shared date and duration words.
static const cc::Words &words() {
  using namespace rt;
  static cc::Words w;
  w.free = tr(txt::calendar_free); w.busy = tr(txt::calendar_busy); w.starts_soon = tr(txt::calendar_starts_soon);
  w.private_title = tr(txt::calendar_private); w.all_day = tr(txt::calendar_all_day); w.today = tr(txt::calendar_today);
  w.tomorrow = tr(txt::calendar_tomorrow); w.nothing = tr(txt::calendar_nothing); w.nothing_more = tr(txt::calendar_nothing_more);
  w.until = tr(txt::calendar_until); w.next = tr(txt::calendar_next); w.left = tr(txt::calendar_left); w.in = tr(txt::calendar_in);
  w.more = tr(txt::calendar_more); w.earlier = tr(txt::calendar_earlier); w.later = tr(txt::calendar_later);
  w.more_week = tr(txt::calendar_more_week); w.days_view = tr(txt::calendar_days_view); w.today_key = tr(txt::calendar_today_key);
  w.booking = tr(txt::calendar_booking); w.calendars = tr(txt::calendar_calendars); w.also = tr(txt::calendar_also);
  // The date words start on Sunday (screen.date); the card's weeks start on Monday.
  for (int i = 0; i < 7; ++i) {
    w.days[i] = tr(txt::date_weekdays_short + (i + 1) % 7);
    w.days_long[i] = tr(txt::date_weekdays + (i + 1) % 7);
    w.letters[i] = tr(txt::date_weekdays_min + (i + 1) % 7);
  }
  for (int i = 0; i < 12; ++i) { w.months[i] = tr(txt::date_months + i); w.months_short[i] = tr(txt::date_months_short + i); }
  for (int i = 0; i < 4; ++i) { w.views[i] = tr(txt::calendar_views + i); w.view_notes[i] = tr(txt::calendar_view_notes + i); }
  w.clock = [](int minute) {
    char b[8];
    snprintf(b, sizeof b, "%02d:%02d", (minute / 60) % 24, minute % 60);
    return screen_text::clock_text(b, screen_settings::current.clock_24h != 0, true);
  };
  w.duration = [](int minutes) { return history_view::duration(static_cast<uint32_t>(std::max(0, minutes)) * 60u); };
  return w;
}
// A booking on its way (a key of a room's card was tapped): the card it is for, the end its key showed, and when; the
// key says so until the card's events change, or for twenty seconds.
static struct { std::string entity; int end = -1; uint32_t at = 0; std::shared_ptr<const cc::Data> data; } booking;
static cc::Options options(const Tile &t) {
  cc::Options o;
  o.room = t.calendar_room;
  o.busy_free = t.calendar_busy_free || t.calendar_room;
  o.soon = t.calendar_soon;
  o.start_view = t.calendar_view;
  o.from_monday = t.calendar_monday;
  o.hours_from = t.calendar_hours_from;
  o.hours_to = t.calendar_hours_to;
  o.week_numbers = t.calendar_week_numbers;
  const auto &x = t.extra().calendar;
  o.book = t.calendar_room && x && !x->book_on.empty();
  if (booking.end >= 0 && booking.entity == t.entity) {
    if (x != booking.data || esphome::millis() - booking.at > 20000) booking.end = -1;
    else o.booking = booking.end;
  }
  return o;
}
// Days from 1970-01-01 of a date (Howard Hinnant's days_from_civil), to put the screen's clock on the card's days.
static int civil(int y, int m, int d) {
  y -= m <= 2;
  const int era = (y >= 0 ? y : y - 399) / 400, yoe = y - era * 400;
  const int doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1, doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + doe - 719468;
}
// The card's data, or a day without events on today's date when the app has sent none yet.
static std::shared_ptr<const cc::Data> data_of(const Tile &t) {
  if (t.extra().calendar) return t.extra().calendar;
  auto d = std::make_shared<cc::Data>();
  const auto now = rt::now_time ? rt::now_time() : esphome::ESPTime{};
  if (now.is_valid()) { d->year = now.year; d->month = now.month; d->day = now.day_of_month; d->weekday = (now.day_of_week + 5) % 7; }
  else { d->year = 2026; d->month = 1; d->day = 1; d->weekday = 3; }
  return d;
}
// Now on the card's days: the screen's clock counted from the day the data calls today.
static cc::Moment moment(const cc::Data &d) {
  cc::Moment m;
  const auto now = rt::now_time ? rt::now_time() : esphome::ESPTime{};
  if (!now.is_valid() || !d.year) return m;
  m.day = civil(now.year, now.month, now.day_of_month) - civil(d.year, d.month, d.day);
  m.minute = now.hour * 60 + now.minute;
  return m;
}

// ---- The card on a page.
static View *view_of(lv_obj_t *canvas) {
  auto *extra = canvas ? lv_obj_get_parent(canvas) : nullptr;
  auto *owner = extra ? rt::extra_owner(extra) : nullptr;
  return owner ? owner->calendar : nullptr;
}
static void draw(lv_event_t *e) {
  auto *canvas = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  View *view = view_of(canvas);
  if (!view || !view->data) return;
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  calendar_paint::paint(lv_event_get_layer(e), view->scene, a.x1 + view->edge.left, a.y1 + view->edge.top, faces(), view->data->colors);
}
void release(Widgets &w) {
  delete w.calendar;
  w.calendar = nullptr;
}
void render(Widgets &w, const Tile &t, int width, int height) {
  rt::begin_extra(w, "calendar_card", width, height);
  if (!w.calendar) w.calendar = new View();
  auto *&canvas = w.parts[0];
  if (!canvas) {
    canvas = lv_obj_create(w.extra);
    lv_obj_remove_style_all(canvas);
    lv_obj_remove_flag(canvas, LV_OBJ_FLAG_CLICKABLE);  // the whole card opens the full screen
    lv_obj_remove_flag(canvas, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(canvas, draw, LV_EVENT_DRAW_MAIN, nullptr);
  }
  View &v = *w.calendar;
  // The canvas covers the whole card, its padding too, so a small card's progress can fill the card's own bottom edge;
  // the plan still draws in the content's coordinates.
  v.edge.left = lv_obj_get_style_space_left(w.tile, LV_PART_MAIN);
  v.edge.top = lv_obj_get_style_space_top(w.tile, LV_PART_MAIN);
  v.edge.right = lv_obj_get_style_space_right(w.tile, LV_PART_MAIN);
  v.edge.bottom = lv_obj_get_style_space_bottom(w.tile, LV_PART_MAIN);
  v.edge.radius = lv_obj_get_style_radius(w.tile, LV_PART_MAIN);
  lv_obj_add_flag(w.extra, LV_OBJ_FLAG_OVERFLOW_VISIBLE);
  lv_obj_refresh_ext_draw_size(w.extra);
  lv_obj_set_pos(canvas, -v.edge.left, -v.edge.top);
  lv_obj_set_size(canvas, width + v.edge.left + v.edge.right, height + v.edge.top + v.edge.bottom);
  v.data = data_of(t);
  v.width = width; v.height = height;
  cc::plan_tile(v.scene, measure(), width, height, *v.data, moment(*v.data), options(t), words(), t.name, v.edge);
  lv_obj_invalidate(canvas);
}

// A tap on a room's card (docs/CALENDAR.md, "Status and booking"): a booking key books the room from now to the end
// it showed, with calendar.create_event on the calendar the app named, the place and the title the card was given;
// Home Assistant takes the times in its own zone. The key says Booking until the events come back with it. Anything else
// on the card is the card's tap (its full screen). Returns whether the tap was a booking key's.
bool card_tap(Widgets &w, const Tile &t) {
  View *v = w.calendar;
  auto *canvas = w.parts[0];
  auto *input = lv_indev_active();
  if (!v || !v->data || !canvas || !input || !t.calendar_room) return false;
  lv_point_t p;
  lv_indev_get_point(input, &p);
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  const cc::Hit *hit = calendar_paint::hit(v->scene, p.x - a.x1 - v->edge.left, p.y - a.y1 - v->edge.top);
  if (!hit || hit->kind != cc::HIT_BOOK) return false;
  const auto &d = *v->data;
  const cc::Moment now = moment(d);
  const int start = now.at(), end = hit->arg;
  if (booking.end >= 0 || d.book_on.empty() || end <= start || !rt::fresh()) return true;
  auto stamp = [&](int minute) {
    const cc::Date dt = cc::date_of(d, cc::day_of(minute));
    const int m = ((minute % 1440) + 1440) % 1440;
    char b[24];
    snprintf(b, sizeof b, "%04d-%02d-%02d %02d:%02d:00", dt.year, dt.month, dt.day, m / 60, m % 60);
    return std::string(b);
  };
  const std::string from = stamp(start), until = stamp(end);
  using namespace rt;
  const std::string title = d.book_title.empty() ? tr(txt::calendar_booked) : d.book_title;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef("calendar.create_event");
  request.data.init(d.book_place.empty() ? 4 : 5);
  auto field = [&](const char *key, const std::string &value) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(key);
    entry.value = esphome::StringRef(value);
    request.data.push_back(entry);
  };
  field("entity_id", d.book_on);
  field("summary", title);
  field("start_date_time", from);
  field("end_date_time", until);
  if (!d.book_place.empty()) field("location", d.book_place);
  rt::send_action(request, d.book_on, true, false);
  ESP_LOGI("calendar", "Booked %s from %s until %s", d.book_on.c_str(), from.c_str(), until.c_str());
  booking.entity = t.entity; booking.end = end; booking.at = esphome::millis(); booking.data = v->data;
  cc::plan_tile(v->scene, measure(), v->width, v->height, d, now, options(t), words(), t.name, v->edge);
  lv_obj_invalidate(canvas);
  return true;
}

// ---- The full screen: what stays (header, day heads, all-day rows), the hours that scroll, and a sheet over them.
struct Full {
  cc::Full plan;
  cc::State state;
  std::string entity;
  unsigned index = 0;
  std::shared_ptr<const cc::Data> data;
  lv_obj_t *fixed = nullptr, *scroller = nullptr, *content = nullptr, *overlay = nullptr;
  int width = 0, height = 0;  // the glass: a new object reports its size only after LVGL's next layout pass
};
static Full full;
static int margin() { return ui::px(ui::large() ? 16 : 9); }
static void paint_scene(lv_event_t *e, const cc::Scene &sc) {
  auto *o = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  if (!full.data) return;
  lv_area_t a;
  lv_obj_get_coords(o, &a);
  calendar_paint::paint(lv_event_get_layer(e), sc, a.x1, a.y1, faces(), full.data->colors);
}
static void apply(bool keep_scroll);
static const Tile *tile_open() {
  return full.index < rt::model.count && rt::model.tiles[full.index].entity == full.entity ? &rt::model.tiles[full.index] : nullptr;
}
// A sheet opens on a short event (the app's `calendar_detail`): the app is asked for its whole title, place and notes,
// by the card's place, the event's calendar and its minutes from the day the data calls today. The sheet shows the short
// event until the answer comes.
static void ask(cc::State &st) {
  st.detail = cc::Detail{};
  if (!full.data || !full.data->asks || st.sheet < 0 || st.sheet >= (int) full.data->events.size()) return;
  const auto &e = full.data->events[st.sheet];
  if (e.flags & cc::PRIVATE) return;
  st.detail.cal = e.cal; st.detail.start = e.start; st.detail.end = e.end;
  char day[16];
  snprintf(day, sizeof day, "%04d-%02d-%02d", full.data->year, full.data->month, full.data->day);
  rt::library_event("esphome.screen_calendar", {{"entity", full.entity}, {"i", std::to_string(full.index)}, {"c", std::to_string(e.cal)},
                                                {"s", std::to_string(e.start)}, {"e", std::to_string(e.end)}, {"day", day},
                                                {"view", std::to_string(++rt::calendar_view_id)}});
  ESP_LOGI("calendar", "Asked for the event at %d of calendar %d", e.start, (int) e.cal);
}
// A tap on one of the three layers: the plan says what lies under the finger.
static void tapped(lv_event_t *e) {
  auto *o = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  const cc::Scene *sc = o == full.fixed ? &full.plan.fixed : o == full.content ? &full.plan.scroll : o == full.overlay ? &full.plan.overlay : nullptr;
  auto *input = lv_indev_active();
  if (!sc || !input) return;
  lv_point_t p;
  lv_indev_get_point(input, &p);
  lv_area_t a;
  lv_obj_get_coords(o, &a);
  const cc::Hit *hit = calendar_paint::hit(*sc, p.x - a.x1, p.y - a.y1);
  if (!hit || !rt::allowed(esphome::millis(), 3000 + hit->kind, full.entity)) return;
  auto &st = full.state;
  const int today = full.data ? moment(*full.data).day : 0;
  bool keep = true;
  switch (hit->kind) {
    case cc::HIT_CLOSE:
      if (st.menu || st.sheet >= 0) { st.menu = false; st.sheet = -1; break; }
      rt::detail_command(-1);
      return;
    case cc::HIT_SCRIM: st.menu = false; st.sheet = -1; break;
    case cc::HIT_SHEET: return;
    case cc::HIT_VIEW_KEY: st.menu = !st.menu; break;
    case cc::HIT_VIEW: st.view = static_cast<cc::View>(hit->arg); st.menu = false; st.chosen = true; st.week = st.month = 0; keep = false; break;
    case cc::HIT_EVENT: st.sheet = hit->arg; ask(st); break;
    case cc::HIT_CALENDAR: st.hidden ^= uint8_t(1u << std::clamp(hit->arg, 0, 7)); keep = full.plan.view == cc::WEEK; break;
    case cc::HIT_DAY:
      st.day = hit->arg;
      // A day of the week or of a narrow month opens that day; a wide month shows it beside the grid.
      if (full.plan.view == cc::WEEK || full.plan.view == cc::BLOCKS || (full.plan.view == cc::MONTH && !full.plan.month_list)) { st.view = cc::DAY; keep = false; }
      break;
    case cc::HIT_TODAY: st.day = today; st.week = st.month = 0; keep = false; break;
    case cc::HIT_PREV:
    case cc::HIT_NEXT: {
      const int step = hit->kind == cc::HIT_NEXT ? 1 : -1;
      if (full.plan.view == cc::MONTH) st.month += step;
      else if (full.plan.view == cc::DAY) st.day += step;
      else if (full.plan.view == cc::WEEK || full.plan.view == cc::BLOCKS) st.week += step;
      keep = full.plan.view == cc::WEEK;  // a week back or forward keeps the hours where they were
      break;
    }
    default: return;
  }
  apply(keep);
}
static lv_obj_t *layer(lv_obj_t *parent, void (*draw_cb)(lv_event_t *)) {
  auto *o = lv_obj_create(parent);
  lv_obj_remove_style_all(o);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(o, draw_cb, LV_EVENT_DRAW_MAIN, nullptr);
  lv_obj_add_event_cb(o, tapped, LV_EVENT_SHORT_CLICKED, nullptr);
  return o;
}
static void apply(bool keep_scroll) {
  const Tile *t = tile_open();
  if (!t || !full.fixed) return;
  full.data = data_of(*t);
  const int w = full.width, h = full.height;
  const int was = full.scroller && !lv_obj_has_flag(full.scroller, LV_OBJ_FLAG_HIDDEN) ? lv_obj_get_scroll_y(full.scroller) : -1;
  cc::plan_full(full.plan, measure(), w, h, margin(), *full.data, moment(*full.data), options(*t), words(), t->name, full.state);
  const auto &pl = full.plan;
  if (pl.sh > 0) {
    lv_obj_remove_flag(full.scroller, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_pos(full.scroller, pl.sx, pl.sy);
    lv_obj_set_size(full.scroller, pl.sw, pl.sh);
    lv_obj_set_size(full.content, pl.sw, pl.scroll.height);
    lv_obj_update_layout(full.scroller);
    lv_obj_scroll_to_y(full.scroller, keep_scroll && was >= 0 ? was : pl.scroll_to, LV_ANIM_OFF);
    lv_obj_invalidate(full.content);
  } else lv_obj_add_flag(full.scroller, LV_OBJ_FLAG_HIDDEN);
  if (pl.overlay.boxes.empty()) lv_obj_add_flag(full.overlay, LV_OBJ_FLAG_HIDDEN);
  else { lv_obj_remove_flag(full.overlay, LV_OBJ_FLAG_HIDDEN); lv_obj_move_foreground(full.overlay); lv_obj_invalidate(full.overlay); }
  lv_obj_invalidate(full.fixed);
}
void open(lv_obj_t *root, const Tile &t, unsigned index) {
  // The whole glass: another card left the layer a hand wide in the middle (overlay_card::frame pads it, centre moves
  // its content), and the full screen draws from the glass's own corner.
  const int w = overlay_card::screen_width(), h = overlay_card::screen_height();
  lv_obj_set_pos(root, 0, 0);
  lv_obj_set_size(root, w, h);
  lv_obj_set_style_pad_all(root, 0, 0);
  if (full.entity != t.entity || full.index != index) {
    // Another card: it opens on its own first view, today, at an hour before now.
    full.state = cc::State{};
    const auto m = measure();
    const int bw = w - 2 * margin(), bh = h - (margin() + cc::key_size(m) + ui::px(ui::large() ? 12 : 6)) - margin();
    full.state.view = cc::first_view(m, bw, bh, options(t));
    full.data = data_of(t);
    full.state.day = moment(*full.data).day;
  }
  full.state.menu = false;
  full.state.sheet = -1;
  full.state.hidden = 0;
  full.entity = t.entity;
  full.index = index;
  full.width = w;
  full.height = h;
  lv_obj_set_style_bg_color(root, theme::color(theme::CARD), 0);
  full.fixed = layer(root, [](lv_event_t *e) { paint_scene(e, full.plan.fixed); });
  lv_obj_set_pos(full.fixed, 0, 0);
  lv_obj_set_size(full.fixed, w, h);
  // The hours scroll in a box of their own; the finger that drags them taps nothing (LVGL sends no click after a scroll).
  full.scroller = lv_obj_create(root);
  lv_obj_remove_style_all(full.scroller);
  lv_obj_set_scroll_dir(full.scroller, LV_DIR_VER);
  lv_obj_set_scrollbar_mode(full.scroller, LV_SCROLLBAR_MODE_ACTIVE);
  lv_obj_set_style_width(full.scroller, ui::px(4), LV_PART_SCROLLBAR);
  lv_obj_set_style_radius(full.scroller, ui::px(2), LV_PART_SCROLLBAR);
  lv_obj_set_style_bg_color(full.scroller, theme::color(theme::TICK), LV_PART_SCROLLBAR);
  lv_obj_set_style_bg_opa(full.scroller, LV_OPA_COVER, LV_PART_SCROLLBAR);
  full.content = layer(full.scroller, [](lv_event_t *e) { paint_scene(e, full.plan.scroll); });
  lv_obj_set_pos(full.content, 0, 0);
  full.overlay = layer(root, [](lv_event_t *e) { paint_scene(e, full.plan.overlay); });
  lv_obj_set_pos(full.overlay, 0, 0);
  lv_obj_set_size(full.overlay, w, h);
  apply(false);
  // New events while it is open repaint it in place, where it is scrolled (docs/CARD_PARTS.md).
  rt::card_shaped(t, rt::entity_shape);
  rt::card_bind(full.fixed, t, [](lv_obj_t *, const Tile &, const rt::CardPart &) { apply(true); });
}
void detail(unsigned view, int cal, int start, int end, std::string title, std::string place, std::string notes, bool gone) {
  auto &d = full.state.detail;
  if (view != rt::calendar_view_id || full.state.sheet < 0 || d.answered || d.cal != cal || d.start != start || d.end != end) return;
  if (gone) return;  // the sheet keeps the short event
  d.title = std::move(title); d.place = std::move(place); d.notes = std::move(notes);
  d.answered = true;
  ESP_LOGI("calendar", "The rest of the event at %d of calendar %d came (%u bytes of notes)", start, cal, (unsigned) d.notes.size());
  if (rt::detail_root && !lv_obj_has_flag(rt::detail_root, LV_OBJ_FLAG_HIDDEN) && rt::detail_index == full.index) apply(true);
}
void minute() {
  if (!rt::detail_root || lv_obj_has_flag(rt::detail_root, LV_OBJ_FLAG_HIDDEN) || rt::detail_index != full.index || !tile_open()) return;
  apply(true);
}
}  // namespace calendar_view
