// The energy card on the glass (firmware 0.47.0): the scene energy_card.h builds, painted in one object's draw event,
// with the dots on a timer of their own.
//
// Compiled on its own, as page_receiver.cpp is: every header of this component lands in main.cpp, and on Xtensa the
// literal pool of one object file must stay within reach of all of its code (page_receiver.cpp says how that broke).
#include "esphome/core/log.h"
#include "runtime_tiles.h"

#include <unordered_map>

namespace energy_view {
using runtime_tiles::Tile;
using runtime_tiles::Widgets;
namespace rt = runtime_tiles;
namespace ec = energy_card;

// A dot: its place on its line and a picture of it at that sub-pixel place, so it runs smoothly and stays in the
// middle of a line LVGL draws on whole pixels (an object can only stand on whole pixels).
struct Dot {
  // How far along its line, 0..1, and when it was last moved: a new value changes the pace, never the place.
  float phase = 0;
  uint32_t moved = 0;
  float cx = -1e6f, cy = -1e6f;
  int x0 = 0, y0 = 0, size = 0;
  uint32_t color = 0;
  std::vector<uint8_t> pixels;
  lv_image_dsc_t picture{};
};
struct View {
  ec::Scene scene;
  std::shared_ptr<const ec::Data> data;
  std::string widest;  // the widest number this card showed: a car passing 10 kW makes room once, not back and forth
  int width = 0, height = 0;
  std::vector<Dot> dots;
  std::array<const lv_font_t *, ec::FACES> faces{};
  lv_color_t ground{};  // the card's own colour, which the circles are filled with
  bool told = false;    // the host build logged where the circles stand
  // Every width the fit has measured, by face and text. The fit tries every form and font step and asks the same
  // few dozen strings some 8000 times; through LVGL's glyph tables that held the whole screen for about a second at
  // every new value. The words and most numbers stay from one value to the next, so the widths stay too.
  ec::ChoiceCache choice;  // the form, fonts and places the card chose, kept while its shape stays (energy_card.h)
  std::shared_ptr<std::unordered_map<std::string, int>> widths = std::make_shared<std::unordered_map<std::string, int>>();
};

static lv_timer_t *timer = nullptr;
// The energy cards that exist, on the glass or kept with a page off it (kept_pages.h). A kept page comes back on the
// glass without being drawn again, so nothing would wake a timer that rested: it rests only when no card exists.
static int views = 0;
constexpr uint32_t FRAME_MS = 40;  // 25 frames a second: a dot moves at most a few pixels a frame

static lv_color_t paint(ec::Paint p) {
  switch (p) {
    case ec::Paint::SOLAR: return theme::color(theme::ENERGY_SOLAR);
    case ec::Paint::GRID_IN: return theme::color(theme::ENERGY_GRID);
    case ec::Paint::GRID_OUT: return theme::color(theme::ENERGY_RETURN);
    case ec::Paint::BATTERY_OUT: return theme::color(theme::ENERGY_BATTERY_OUT);
    case ec::Paint::BATTERY_IN: return theme::color(theme::ENERGY_BATTERY_IN);
    case ec::Paint::DEVICE0: return theme::color(theme::ENERGY_DEVICE_1);
    case ec::Paint::DEVICE1: return theme::color(theme::ENERGY_DEVICE_2);
    case ec::Paint::DEVICE2: return theme::color(theme::ENERGY_DEVICE_3);
    case ec::Paint::DEVICE3: return theme::color(theme::ENERGY_DEVICE_4);
    case ec::Paint::REST: return theme::color(theme::ENERGY_REST);
    case ec::Paint::MUTED: return theme::color(theme::MUTED);
    case ec::Paint::IDLE: return theme::color(theme::LINE);
    case ec::Paint::ACCENT: return theme::color(theme::ACCENT);
    case ec::Paint::KEY: return theme::color(theme::KEY);
    case ec::Paint::ON_ACCENT: return theme::color(theme::ON_ACCENT);
    case ec::Paint::SUBTLE: return theme::color(theme::SUBTLE);
    case ec::Paint::INK: default: return theme::color(theme::INK);
  }
}

// The dot's picture at its centre (cx, cy), relative to the card: a disc of radius r, each pixel covered as far as the
// disc reaches over it.
static void paint_dot(Dot &dot, float cx, float cy, float r) {
  dot.cx = cx; dot.cy = cy;
  dot.size = int(std::ceil(2 * r)) + 3;
  dot.x0 = int(std::floor(cx - r)) - 1; dot.y0 = int(std::floor(cy - r)) - 1;
  // Only how much of each pixel the disc covers (A8): LVGL paints it in the dot's colour, a quarter of a colour picture.
  dot.pixels.assign(size_t(dot.size * dot.size), 0);
  for (int j = 0; j < dot.size; ++j)
    for (int i = 0; i < dot.size; ++i) {
      const float dx = dot.x0 + i + 0.5f - cx, dy = dot.y0 + j + 0.5f - cy;
      const float cover = std::clamp(r + 0.5f - std::sqrt(dx * dx + dy * dy), 0.f, 1.f);
      dot.pixels[size_t(j * dot.size + i)] = uint8_t(cover * 255 + 0.5f);
    }
  auto &h = dot.picture.header;
  h.magic = LV_IMAGE_HEADER_MAGIC; h.cf = LV_COLOR_FORMAT_A8; h.w = dot.size; h.h = dot.size; h.stride = dot.size;
  dot.picture.data = dot.pixels.data(); dot.picture.data_size = dot.pixels.size();
}

static View *view_of(lv_obj_t *canvas) {
  auto *extra = canvas ? lv_obj_get_parent(canvas) : nullptr;
  auto *owner = extra ? rt::extra_owner(extra) : nullptr;
  return owner ? owner->energy : nullptr;
}

static bool meets(const lv_area_t &clip, int x1, int y1, int x2, int y2) {
  return x1 <= clip.x2 && x2 >= clip.x1 && y1 <= clip.y2 && y2 >= clip.y1;
}

// The scene, painted in the order of power-flow-card-plus's layers: the header's keys, lines, dots, circles, the
// house's ring, words. Only what meets the area being redrawn is handed to LVGL: a moving dot redraws a few pixels.
static void paint_scene(lv_layer_t *layer, lv_obj_t *canvas, View *view, const ec::Scene &sc);
static void draw(lv_event_t *e) {
  auto *canvas = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  View *view = view_of(canvas);
  if (!view) return;
  paint_scene(lv_event_get_layer(e), canvas, view, view->scene);
}
static void paint_scene(lv_layer_t *layer, lv_obj_t *canvas, View *view, const ec::Scene &sc) {
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  const lv_area_t clip = layer->_clip_area;
  for (auto &b : sc.boxes) {
    if (!meets(clip, a.x1 + b.x, a.y1 + b.y, a.x1 + b.x + b.w - 1, a.y1 + b.y + b.h - 1)) continue;
    lv_draw_rect_dsc_t dsc;
    lv_draw_rect_dsc_init(&dsc);
    dsc.radius = b.radius; dsc.bg_color = paint(b.paint); dsc.bg_opa = LV_OPA_COVER;
    lv_area_t box{a.x1 + b.x, a.y1 + b.y, a.x1 + b.x + b.w - 1, a.y1 + b.y + b.h - 1};
    lv_draw_rect(layer, &dsc, &box);
  }
#if defined(USE_HOST) || defined(ESP_SCREEN_HOST)
  // Where the circles stand on the glass, once per scene, for the render harness's taps (tools/render/energy_tiles.py).
  if (!view->told) {
    view->told = true;
    for (auto &c : sc.circles)
      if (!c.entity.empty()) ESP_LOGI("energy", "energy: circle %s at %d,%d", c.entity.c_str(), a.x1 + int(c.c.x), a.y1 + int(c.c.y));
  }
#endif
  for (auto &l : sc.lines) {
    const int x1 = a.x1 + int(std::min(l.a.x, l.b.x)) - l.width, x2 = a.x1 + int(std::max(l.a.x, l.b.x)) + l.width;
    const int y1 = a.y1 + int(std::min(l.a.y, l.b.y)) - l.width, y2 = a.y1 + int(std::max(l.a.y, l.b.y)) + l.width;
    if (!meets(clip, x1, y1, x2, y2)) continue;
    lv_draw_line_dsc_t dsc;
    lv_draw_line_dsc_init(&dsc);
    dsc.color = paint(l.paint); dsc.width = l.width;
    dsc.p1.x = a.x1 + int(l.a.x); dsc.p1.y = a.y1 + int(l.a.y); dsc.p2.x = a.x1 + int(l.b.x); dsc.p2.y = a.y1 + int(l.b.y);
    lv_draw_line(layer, &dsc);
  }
  auto arcs = [&](const std::vector<ec::Arc> &list) {
    for (auto &arc : list) {
      const int cx = a.x1 + int(arc.c.x), cy = a.y1 + int(arc.c.y);
      if (!meets(clip, cx - arc.radius, cy - arc.radius, cx + arc.radius, cy + arc.radius)) continue;
      lv_draw_arc_dsc_t dsc;
      lv_draw_arc_dsc_init(&dsc);
      dsc.color = paint(arc.paint); dsc.width = arc.width; dsc.rounded = 0;
      dsc.center.x = cx; dsc.center.y = cy; dsc.radius = arc.radius;
      dsc.start_angle = int(std::lround(arc.a0)); dsc.end_angle = int(std::lround(arc.a1 >= 360 ? 360 : arc.a1));
      lv_draw_arc(layer, &dsc);
    }
  };
  arcs(sc.arcs);
  for (auto &arrow : sc.arrows) {
    const float xs[] = {arrow.tip.x, arrow.left.x, arrow.right.x}, ys[] = {arrow.tip.y, arrow.left.y, arrow.right.y};
    const int x1 = a.x1 + int(std::floor(*std::min_element(xs, xs + 3))), x2 = a.x1 + int(std::ceil(*std::max_element(xs, xs + 3)));
    const int y1 = a.y1 + int(std::floor(*std::min_element(ys, ys + 3))), y2 = a.y1 + int(std::ceil(*std::max_element(ys, ys + 3)));
    if (!meets(clip, x1, y1, x2, y2)) continue;
    lv_draw_triangle_dsc_t dsc;
    lv_draw_triangle_dsc_init(&dsc);
    dsc.color = paint(arrow.paint); dsc.opa = LV_OPA_COVER;
    dsc.p[0] = {a.x1 + int(std::lround(arrow.tip.x)), a.y1 + int(std::lround(arrow.tip.y))};
    dsc.p[1] = {a.x1 + int(std::lround(arrow.left.x)), a.y1 + int(std::lround(arrow.left.y))};
    dsc.p[2] = {a.x1 + int(std::lround(arrow.right.x)), a.y1 + int(std::lround(arrow.right.y))};
    lv_draw_triangle(layer, &dsc);
  }
  for (auto &dot : view->dots) {
    if (dot.pixels.empty()) continue;
    const int x1 = a.x1 + dot.x0, y1 = a.y1 + dot.y0;
    if (!meets(clip, x1, y1, x1 + dot.size - 1, y1 + dot.size - 1)) continue;
    lv_draw_image_dsc_t dsc;
    lv_draw_image_dsc_init(&dsc);
    dsc.src = &dot.picture;
    dsc.recolor = lv_color_hex(dot.color);
    dsc.recolor_opa = LV_OPA_COVER;
    lv_area_t box{x1, y1, x1 + dot.size - 1, y1 + dot.size - 1};
    lv_draw_image(layer, &dsc, &box);
  }
  for (auto &c : sc.circles) {
    const int x1 = a.x1 + int(std::lround(c.c.x - c.d / 2.f)), y1 = a.y1 + int(std::lround(c.c.y - c.d / 2.f));
    if (!meets(clip, x1, y1, x1 + c.d - 1, y1 + c.d - 1)) continue;
    lv_draw_rect_dsc_t dsc;
    lv_draw_rect_dsc_init(&dsc);
    dsc.radius = LV_RADIUS_CIRCLE; dsc.bg_color = view->ground; dsc.bg_opa = LV_OPA_COVER;
    dsc.border_width = c.border; dsc.border_color = paint(c.paint); dsc.border_opa = c.border ? LV_OPA_COVER : LV_OPA_TRANSP;
    lv_area_t box{x1, y1, x1 + c.d - 1, y1 + c.d - 1};
    lv_draw_rect(layer, &dsc, &box);
  }
  arcs(sc.ring);
  for (auto &t : sc.texts) {
    const lv_font_t *font = view->faces[t.face];
    if (!font) continue;
    const int h = lv_font_get_line_height(font);
    const int x1 = a.x1 + t.x, y1 = a.y1 + t.y;
    if (!meets(clip, x1, y1, x1 + t.w - 1, y1 + h - 1)) continue;
    lv_draw_label_dsc_t dsc;
    lv_draw_label_dsc_init(&dsc);
    dsc.font = font; dsc.color = paint(t.paint); dsc.text = t.s.c_str();
    dsc.align = t.centre ? LV_TEXT_ALIGN_CENTER : LV_TEXT_ALIGN_LEFT;
    lv_area_t box{x1, y1, x1 + t.w - 1, y1 + h - 1};
    lv_draw_label(layer, &dsc, &box);
  }
}

// Moves a card's dots to where they are now, redrawing the pixels each one leaves and enters.
static void advance(Widgets &w, uint32_t now) {
  View *view = w.energy;
  auto *canvas = w.parts[0];
  if (!view || !canvas || view->dots.size() != view->scene.flows.size()) return;
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  for (size_t i = 0; i < view->dots.size(); ++i) {
    auto &flow = view->scene.flows[i];
    auto &dot = view->dots[i];
    // Each dot moves on by the time since its last frame at its line's pace now. Its place worked out from the time
    // since the card started instead jumped at every new value: after an hour a pace a hundredth of a second shorter
    // moves it a whole line. A pause (the screen asleep, the card off the glass) resumes where it stopped.
    const float dt = dot.moved ? std::min(0.2f, (now - dot.moved) / 1000.f) : 0.f;
    dot.moved = now;
    dot.phase = std::fmod(dot.phase + dt / flow.seconds, 1.f);
    const ec::P p = ec::along(flow.path, dot.phase);
    if (std::fabs(p.x - dot.cx) < 0.05f && std::fabs(p.y - dot.cy) < 0.05f) continue;
    if (!dot.pixels.empty()) {
      lv_area_t old{a.x1 + dot.x0, a.y1 + dot.y0, a.x1 + dot.x0 + dot.size - 1, a.y1 + dot.y0 + dot.size - 1};
      lv_obj_invalidate_area(canvas, &old);
    }
    paint_dot(dot, p.x, p.y, view->scene.dot_r);
    lv_area_t now_area{a.x1 + dot.x0, a.y1 + dot.y0, a.x1 + dot.x0 + dot.size - 1, a.y1 + dot.y0 + dot.size - 1};
    lv_obj_invalidate_area(canvas, &now_area);
  }
}

// The dots' timer: it moves only cards on the glass, only while the screen is awake, and rests when no card exists.
static void tick(lv_timer_t *) {
  if (!rt::awake()) return;
  // A card open over the page hides the dots: nothing under it is drawn again.
  if (rt::detail_root && !lv_obj_has_flag(rt::detail_root, LV_OBJ_FLAG_HIDDEN)) return;
  const uint32_t now = esphome::millis();
  for (auto &w : rt::widgets) {
    if (!w.energy || w.extra_mode != "energy" || !w.extra || lv_obj_has_flag(w.extra, LV_OBJ_FLAG_HIDDEN) || !w.parts[0]) continue;
    if (w.tile && lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN)) continue;
    if (w.energy->scene.flows.empty()) continue;
    advance(w, now);
  }
  if (!views && timer) lv_timer_pause(timer);
}

void release(Widgets &w) {
  if (w.energy) --views;
  delete w.energy;
  w.energy = nullptr;
}

// The sensor behind a circle as the card a tap opens shows it: Home Assistant's own state and unit, and the circle's
// word (a source) or the device's name for a heading. False when the card has no such sensor.
struct Sensor { std::string entity, name, state, unit; };
static bool reading(const ec::Data &data, const std::string &entity, Sensor &out) {
  if (entity.empty()) return false;
  const ec::Reading *found = nullptr;
  for (auto &r : data.readings) if (r.entity == entity) found = &r;
  if (!found) return false;
  out.entity = entity; out.state = found->state; out.unit = found->unit;
  out.name = entity == data.solar_entity ? rt::tr(rt::txt::energy_solar) : entity == data.grid_entity ? rt::tr(rt::txt::energy_grid)
           : entity == data.battery_entity ? rt::tr(rt::txt::energy_battery) : entity;
  for (auto &d : data.devices) if (d.entity == entity) out.name = d.name;
  return true;
}

// The board's fixed fonts the card may use, largest first, and how wide a text is in them, remembered per view.
static ec::Measure measure_of(View &view) {
  view.faces = {rt::watch_value_font, rt::watch_font, rt::control_font, rt::small_font, rt::tile_icon_font(), rt::mini_icon_font, rt::watch_icon_font};
  ec::Measure m;
  for (int f = 0; f < ec::FACES; ++f) m.line[f] = view.faces[f] ? lv_font_get_line_height(view.faces[f]) : 0;
  const auto faces = view.faces;
  if (view.widths->size() > 256) view.widths->clear();  // a long run of new numbers does not grow it for ever
  m.width = [faces, widths = view.widths](ec::Face f, const std::string &s) {
    if (!faces[f]) return 1 << 20;
    std::string key(1, char(f));
    key += s;
    auto found = widths->find(key);
    if (found != widths->end()) return found->second;
    const int w = rt::text_width(s, faces[f]);
    widths->emplace(std::move(key), w);
    return w;
  };
  return m;
}
static ec::Words words_of(const ec::Data *data) {
  ec::Words words;
  words.solar = rt::tr(rt::txt::energy_solar); words.grid = rt::tr(rt::txt::energy_grid); words.battery = rt::tr(rt::txt::energy_battery);
  words.home = rt::tr(rt::txt::energy_home); words.other = rt::tr(rt::txt::energy_other);
  words.untracked = rt::tr(rt::txt::energy_untracked);
  words.decimal = screen_text::decimal_mark(); words.percent = screen_text::percent_sign();
  // The house is named as Home Assistant names it in its live power view: the home's own name.
  if (data && !data->home_name.empty()) words.home = data->home_name;
  // A period's words: the units, Today (the calendar card's), the days and months (the screen's own date words).
  words.units = {rt::tr(rt::txt::energy_day), rt::tr(rt::txt::energy_week), rt::tr(rt::txt::energy_month), rt::tr(rt::txt::energy_year)};
  words.today_key = rt::tr(rt::txt::calendar_today_key); words.today = rt::tr(rt::txt::calendar_today);
  for (int i = 0; i < 7; ++i) words.weekdays[i] = rt::tr(rt::txt::date_weekdays_short + (i + 1) % 7);
  for (int i = 0; i < 12; ++i) { words.months[i] = rt::tr(rt::txt::date_months + i); words.months_short[i] = rt::tr(rt::txt::date_months_short + i); }
  return words;
}
// The diagram of `data` in `width` x `height`: a period drawn calm, with lines and arrows; the power now as the tile
// chooses. The widest number shown so far keeps its room (measured in the smallest face, which orders them alike).
static ec::Scene diagram(View &view, const ec::Data &data, const ec::Measure &m, const ec::Words &words, int width, int height, bool lines) {
  ec::Scene sc;
  if (data.waiting) return sc;  // the app reads the period: the card shows it as soon as it comes
  if (!data.any()) {
    // Home Assistant knows no sensor for it in its Energy settings: say where to add them, as it hides its own view.
    sc.texts.push_back({rt::tr(data.energy() ? rt::txt::energy_no_energy : rt::txt::energy_no_power), ec::SMALL, 0,
                        std::max(0, height / 2 - m.line[ec::SMALL]), width, true, ec::Paint::MUTED});
    return sc;
  }
  for (float v : {data.solar_w, data.from_grid, data.to_grid, data.from_battery, data.to_battery, data.home}) {
    const std::string s = ec::amount(data, v, words.decimal);
    if (view.widest.empty() || m.width(ec::SMALL, s) > m.width(ec::SMALL, view.widest)) view.widest = s;
  }
  sc = ec::build(data, m, width, height, words, view.widest, &view.choice, lines || data.energy() ? ec::Style::LINES : ec::Style::DOTS);
  if (!sc.ok) {
    // Too small for the diagram (a size the editor does not offer): the house's use alone, as a watch card says it.
    const std::string value = ec::amount(data, data.home, words.decimal);
    int face = ec::WATCH_VALUE;
    while (face < ec::SMALL && (!view.faces[face] || m.width(ec::Face(face), value) > width)) ++face;
    const int ih = m.line[ec::ICON_MINI], vh = m.line[face], top = std::max(0, (height - ih - vh) / 2);
    sc.texts.push_back({ec::utf8(ec::ICON_HOME), ec::ICON_MINI, 0, top, width, true, ec::Paint::INK});
    sc.texts.push_back({value, ec::Face(face), 0, top + ih, width, true, ec::Paint::INK});
  }
  return sc;
}

void render(Widgets &w, const Tile &t, int width, int height) {
  rt::begin_extra(w, "energy", width, height);
  if (!w.energy) { w.energy = new View(); ++views; }
  View &view = *w.energy;
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
  const ec::Measure m = measure_of(view);
  const ec::Words words = words_of(t.extra().energy.get());
  // The circles take the card's own colour (a card may have a background of its own); a card without one, the page's.
  view.ground = lv_obj_get_style_bg_opa(w.tile, LV_PART_MAIN) > LV_OPA_50 ? lv_obj_get_style_bg_color(w.tile, LV_PART_MAIN) : theme::color(theme::PAGE);
  const bool resized = view.width != width || view.height != height;
  view.data = t.extra().energy;
  view.width = width; view.height = height;
  // A circle's sensor open over the card follows the card's moment.
  Sensor sensor;
  if (rt::detail_index == rt::SENSOR_DETAIL && view.data && reading(*view.data, rt::detail_sensor.entity, sensor))
    rt::sensor_detail_update(sensor.entity, sensor.state);
  ec::Scene sc;
  if (view.data && view.data->energy()) {
    // A period: its name over the diagram ("Today", "19 – 25 Oct"), so the card never passes for the power now.
    ec::Scene line;
    const int top = ec::caption(line, m, width, height, view.data->waiting ? "" : ec::period_text(*view.data, words));
    sc = diagram(view, *view.data, m, words, width, height - top, true);
    ec::shift(sc, top);
    sc.texts.insert(sc.texts.begin(), line.texts.begin(), line.texts.end());
  } else if (view.data) {
    sc = diagram(view, *view.data, m, words, width, height, t.energy_lines);
  }
  // The dots keep running where they were. Every value from Home Assistant is a new moment (a new `data`), so a dot
  // follows its line, not its index: a line that runs from the same place to the same place keeps its dot, and only a
  // line that is new starts one. Restarting them all at each value kept a slow dot (6 s at a few W) from ever
  // reaching the end of its line.
  auto same = [](const ec::P &a, const ec::P &b) { return std::fabs(a.x - b.x) < 0.5f && std::fabs(a.y - b.y) < 0.5f; };
  // A new value that leaves every circle, line and turn where it was (most of them: a number changes) is painted in
  // place, as docs/CARD_PARTS.md asks of every card: only the words that changed and the house's ring are drawn again,
  // and the dots go on as they were. Anything else (another source, a new line, another size) draws the card whole.
  const ec::Scene &was = view.scene;
  auto same_arcs = [&](const std::vector<ec::Arc> &x, const std::vector<ec::Arc> &y) {
    if (x.size() != y.size()) return false;
    for (size_t i = 0; i < x.size(); ++i)
      if (!same(x[i].c, y[i].c) || x[i].radius != y[i].radius || x[i].width != y[i].width || x[i].a0 != y[i].a0 ||
          x[i].a1 != y[i].a1 || x[i].paint != y[i].paint) return false;
    return true;
  };
  bool in_place = !resized && was.ok && sc.ok && was.circles.size() == sc.circles.size() && was.lines.size() == sc.lines.size() &&
                  was.flows.size() == sc.flows.size() && was.texts.size() == sc.texts.size() && view.dots.size() == sc.flows.size() &&
                  same_arcs(was.arcs, sc.arcs) && was.dot_r == sc.dot_r && was.arrows.size() == sc.arrows.size();
  for (size_t i = 0; in_place && i < sc.arrows.size(); ++i) {
    const auto &x = was.arrows[i], &y = sc.arrows[i];
    in_place = same(x.tip, y.tip) && same(x.left, y.left) && same(x.right, y.right) && x.paint == y.paint;
  }
  for (size_t i = 0; in_place && i < sc.circles.size(); ++i) {
    const auto &x = was.circles[i], &y = sc.circles[i];
    in_place = same(x.c, y.c) && x.d == y.d && x.border == y.border && x.paint == y.paint;
  }
  for (size_t i = 0; in_place && i < sc.lines.size(); ++i) {
    const auto &x = was.lines[i], &y = sc.lines[i];
    in_place = same(x.a, y.a) && same(x.b, y.b) && x.width == y.width && x.paint == y.paint;
  }
  for (size_t i = 0; in_place && i < sc.flows.size(); ++i) {
    const auto &x = was.flows[i], &y = sc.flows[i];
    in_place = x.paint == y.paint && !x.path.empty() && !y.path.empty() && same(x.path.front().at(0), y.path.front().at(0)) &&
               same(x.path.back().at(1), y.path.back().at(1));
  }
  for (size_t i = 0; in_place && i < sc.texts.size(); ++i) {
    const auto &x = was.texts[i], &y = sc.texts[i];
    in_place = x.face == y.face && x.x == y.x && x.y == y.y && x.w == y.w && x.centre == y.centre;
  }
  if (in_place) {
    lv_area_t a;
    lv_obj_get_coords(canvas, &a);
    auto invalidate = [&](int x1, int y1, int x2, int y2) {
      lv_area_t r{a.x1 + x1, a.y1 + y1, a.x1 + x2, a.y1 + y2};
      lv_obj_invalidate_area(canvas, &r);
    };
    for (size_t i = 0; i < sc.texts.size(); ++i) {
      const auto &x = was.texts[i], &y = sc.texts[i];
      if (x.s == y.s && x.paint == y.paint) continue;
      const int h = view.faces[y.face] ? lv_font_get_line_height(view.faces[y.face]) : 0;
      invalidate(y.x, y.y, y.x + y.w - 1, y.y + h - 1);
    }
    if (!same_arcs(was.ring, sc.ring))
      for (const std::vector<ec::Arc> *ring : {&was.ring, static_cast<const std::vector<ec::Arc> *>(&sc.ring)})
        for (auto &r : *ring) invalidate(int(r.c.x) - r.radius, int(r.c.y) - r.radius, int(r.c.x) + r.radius, int(r.c.y) + r.radius);
    view.scene = std::move(sc);
    view.told = false;
    // The dots keep their pictures and places: the next frame moves them at their lines' new pace.
    for (size_t i = 0; i < view.dots.size(); ++i) view.dots[i].color = lv_color_to_u32(paint(view.scene.flows[i].paint)) & 0xFFFFFF;
    return;
  }
  std::vector<Dot> dots(sc.flows.size());
  for (size_t i = 0; i < sc.flows.size(); ++i) {
    const auto &path = sc.flows[i].path;
    if (path.empty()) continue;
    for (size_t j = 0; j < view.scene.flows.size() && j < view.dots.size(); ++j) {
      const auto &old = view.scene.flows[j].path;
      if (old.empty() || !same(old.front().at(0), path.front().at(0)) || !same(old.back().at(1), path.back().at(1))) continue;
      dots[i].phase = view.dots[j].phase;
      dots[i].moved = view.dots[j].moved;
      break;
    }
  }
  view.scene = std::move(sc);
  view.told = false;
  view.dots = std::move(dots);
  for (size_t i = 0; i < view.dots.size(); ++i) {
    view.dots[i].color = lv_color_to_u32(paint(view.scene.flows[i].paint)) & 0xFFFFFF;
    view.dots[i].cx = -1e6f;  // repainted below at its place now
  }
  advance(w, esphome::millis());
  lv_obj_invalidate(canvas);
  if (!view.scene.flows.empty()) {
    if (!timer) timer = lv_timer_create(tick, FRAME_MS, nullptr);
    else lv_timer_resume(timer);
  }
}

bool tap(Widgets &w, const Tile &t, const lv_point_t &point) {
  // A card of a period opens its full screen, as a calendar card does; its circles open their sensors there.
  if (!t.energy_period.empty()) {
    rt::show_detail(w.index);
    return true;
  }
  View *view = w.energy;
  auto *canvas = w.parts[0];
  if (!view || !canvas || !view->scene.ok) return false;
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  const ec::Circle *hit = ec::hit(view->scene, float(point.x - a.x1), float(point.y - a.y1), ui::touch_min());
  Sensor sensor;
  if (!hit || !view->data || !reading(*view->data, hit->entity, sensor)) return false;
  (void) t;
  rt::open_sensor_detail(sensor.entity, sensor.name, sensor.state, sensor.unit);
  return true;
}

// ---- The full screen of a card of a period: the calendar card's header with the units, Today, back and forward, and
// the diagram of the period chosen under it. The period now of the tile's own unit is the tile's; any other the app
// reads when a key asks for it (ENERGY_EVENT, answered as op "energy": receive()).
struct Full {
  std::string entity;
  unsigned index = 0;
  int unit = 0, offset = 0;              // what the keys chose
  std::shared_ptr<const ec::Data> data;  // what the diagram shows: the tile's, or the app's answer
  unsigned asked = 0;                    // the request it waits for, 0 when none
  View view;                             // the diagram's scene and caches; a period runs no dots
  ec::Scene head;
  lv_obj_t *head_obj = nullptr, *canvas = nullptr;
  int width = 0, height = 0, top = 0;
};
static Full full;
static unsigned requests = 0;
static int margin() { return ui::px(ui::large() ? 16 : 9); }
static const Tile *tile_open() {
  return full.index < rt::model.count && rt::model.tiles[full.index].entity == full.entity ? &rt::model.tiles[full.index] : nullptr;
}
static bool is_open() {
  return rt::detail_root && !lv_obj_has_flag(rt::detail_root, LV_OBJ_FLAG_HIDDEN) && rt::detail_index == full.index && full.head_obj;
}
// The app's answer for this unit and offset, as history_request asks for a history: an event, which needs no permission
// to call Home Assistant's actions.
static void request(int unit, int offset) {
  if (rt::inbox.empty()) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef("esphome.screen_energy");
  request.is_event = true;
  full.asked = ++requests;
  const std::string keys[] = {"inbox", "unit", "offset", "session", "rev", "view"};
  const std::string values[] = {rt::inbox, ec::UNITS[unit], std::to_string(offset), rt::protocol_key(rt::transfer.lease), rt::layout_rev,
                                std::to_string(full.asked)};
  request.data.init(6);
  for (int i = 0; i < 6; ++i) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(keys[i]);
    entry.value = esphome::StringRef(values[i]);
    request.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
  ESP_LOGI("energy", "asked for the %s %d back", ec::UNITS[unit], -offset);
}
static void apply() {
  const Tile *t = tile_open();
  if (!t || !full.head_obj) return;
  const ec::Measure m = measure_of(full.view);
  const ec::Words words = words_of(full.data.get());
  const int w = full.width, h = full.height, mg = margin();
  // The line under the name: the period on show, or nothing while the app reads the one chosen.
  const bool shows = full.data && full.data->energy() && !full.data->waiting && !full.asked;
  full.head = ec::Scene{};
  full.top = ec::header(full.head, m, w, mg, t->name, shows ? ec::period_text(*full.data, words) : "", full.unit, full.offset == 0,
                        full.offset > -ec::max_back(full.unit), words);
  full.view.ground = theme::color(theme::CARD);
  // While the app reads the period chosen, the last one stays under the header.
  if (!full.asked) {
    full.view.scene = full.data ? diagram(full.view, *full.data, m, words, w - 2 * mg, std::max(1, h - full.top - mg), true) : ec::Scene{};
    full.view.data = full.data;
  }
  lv_obj_set_pos(full.canvas, mg, full.top);
  lv_obj_set_size(full.canvas, w - 2 * mg, std::max(1, h - full.top - mg));
  lv_obj_invalidate(full.head_obj);
  lv_obj_invalidate(full.canvas);
}
// The tile's own period now, else the app's answer for the one chosen.
static void choose(int unit, int offset) {
  const Tile *t = tile_open();
  if (!t) return;
  full.unit = unit;
  full.offset = std::clamp(offset, -ec::max_back(unit), 0);
  if (offset == 0 && ec::UNITS[unit] == t->energy_period) {
    full.asked = 0;
    full.data = t->extra().energy;
  } else {
    request(full.unit, full.offset);
  }
  apply();
}
static void tapped(lv_event_t *e) {
  auto *o = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  auto *input = lv_indev_active();
  if (!input || !tile_open()) return;
  lv_point_t p;
  lv_indev_get_point(input, &p);
  lv_area_t a;
  lv_obj_get_coords(o, &a);
  if (o == full.canvas) {
    // A circle opens its sensor's history, as on the card of the power now.
    const ec::Circle *hit = ec::hit(full.view.scene, float(p.x - a.x1), float(p.y - a.y1), ui::touch_min());
    Sensor sensor;
    if (hit && full.data && reading(*full.data, hit->entity, sensor) && rt::allowed(esphome::millis(), 3100, full.entity))
      rt::open_sensor_detail(sensor.entity, sensor.name, sensor.state, sensor.unit);
    return;
  }
  const ec::Hit *hit = ec::key_at(full.head, p.x - a.x1, p.y - a.y1);
  if (!hit || !rt::allowed(esphome::millis(), 3000 + hit->kind, full.entity)) return;
  switch (hit->kind) {
    case ec::HIT_CLOSE: rt::detail_command(-1); return;
    case ec::HIT_UNIT: choose(hit->arg, 0); return;
    case ec::HIT_TODAY: choose(full.unit, 0); return;
    case ec::HIT_PREV: choose(full.unit, full.offset - 1); return;
    case ec::HIT_NEXT: if (full.offset < 0) choose(full.unit, full.offset + 1); return;
  }
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
void open(lv_obj_t *root, const Tile &t, unsigned index) {
  // The whole glass, as the calendar card's full screen takes it (calendar_view.cpp open).
  const int w = overlay_card::screen_width(), h = overlay_card::screen_height();
  lv_obj_set_pos(root, 0, 0);
  lv_obj_set_size(root, w, h);
  lv_obj_set_style_pad_all(root, 0, 0);
  lv_obj_set_style_bg_color(root, theme::color(theme::CARD), 0);
  // It opens on the tile's own period, now.
  full.entity = t.entity;
  full.index = index;
  full.unit = ec::unit_index(t.energy_period);
  full.offset = 0;
  full.asked = 0;
  full.data = t.extra().energy;
  full.view.choice = ec::ChoiceCache{};
  full.view.widest.clear();
  full.width = w;
  full.height = h;
  full.head_obj = layer(root, [](lv_event_t *e) {
    paint_scene(lv_event_get_layer(e), static_cast<lv_obj_t *>(lv_event_get_current_target(e)), &full.view, full.head);
  });
  lv_obj_set_pos(full.head_obj, 0, 0);
  lv_obj_set_size(full.head_obj, w, h);
  full.canvas = layer(root, [](lv_event_t *e) {
    paint_scene(lv_event_get_layer(e), static_cast<lv_obj_t *>(lv_event_get_current_target(e)), &full.view, full.view.scene);
  });
  apply();
  // The tile's new numbers repaint it while it shows the tile's own period (docs/CARD_PARTS.md).
  rt::card_shaped(t, rt::entity_shape);
  rt::card_bind(full.head_obj, t, [](lv_obj_t *, const Tile &tile, const rt::CardPart &) {
    if (full.asked || full.offset != 0 || ec::UNITS[full.unit] != tile.energy_period) return;
    full.data = tile.extra().energy;
    apply();
  });
}
unsigned asked() { return full.asked; }
void receive(std::shared_ptr<const ec::Data> data, unsigned view) {
  if (!view || view != full.asked || !data || !data->energy()) return;
  if (ec::unit_index(data->period) != full.unit || data->offset != full.offset) return;
  full.asked = 0;
  full.data = std::move(data);
  if (is_open()) apply();
}
}  // namespace energy_view
