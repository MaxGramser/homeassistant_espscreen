// The screensaver's clock faces (module clock_faces, tier full; docs/SCREENSAVER.md, docs/MODULES.md): Glass, Classic
// and Bauhaus beside the digital clock every screen has. A lite screen compiles none of it, says no clock_faces in its
// hello, and ESP Screens sends it no face. Compiled on its own, as module_vacuum_card.cpp is: every header of this component lands in
// main.cpp, and on Xtensa the literal pool of one object file must stay within reach of all of its code (an S3 build of
// the Guition failed to link with the faces inline). runtime_tiles.h knows it by its header, and a face uses
// the clock's own fonts, words and row of entities.
//
// Every size follows the glass (its short side S, ui::mm) and every letter is one of the board's own font steps, the
// largest that fits. Nothing stands still long enough to mark the glass: the whole clock is drawn again every minute
// (apply_screen_settings), Glass and Classic then stand a fraction further along a slow circle of a millimetre, and
// Bauhaus gives one square a new shape every minute and the whole glass a new composition every ten. The seconds hand
// moves on its own every second (tick), redrawing only the strip it leaves and the strip it takes.
#include "esphome/core/defines.h"
#ifdef SD_MOD_CLOCK_FACES
#include "esphome/core/log.h"
#include "runtime_tiles.h"

namespace runtime_tiles {
namespace clock_faces {

constexpr float PI = 3.14159265f;

// ---- what a face paints in one draw event: lines with round or square ends and filled circles, in their order
struct Paint {
  struct Mark { bool dot; float x1, y1, x2, y2; int w; uint32_t c; bool round; };  // a dot: its middle x1, y1 and radius x2
  std::vector<Mark> marks;
  size_t moving = SIZE_MAX;  // the seconds hand's marks start here (tick moves them)
  void line(float x1, float y1, float x2, float y2, int w, uint32_t c, bool round = true) { marks.push_back({false, x1, y1, x2, y2, std::max(1, w), c, round}); }
  void dot(float x, float y, float r, uint32_t c) { marks.push_back({true, x, y, r, 0, 0, c, false}); }
};
inline void paint_draw(lv_event_t *e) {
  auto *p = static_cast<Paint *>(lv_event_get_user_data(e));
  auto *layer = lv_event_get_layer(e);
  lv_area_t a;
  lv_obj_get_coords(static_cast<lv_obj_t *>(lv_event_get_target(e)), &a);
  for (const auto &m : p->marks) {
    if (m.dot) {
      lv_draw_rect_dsc_t d;
      lv_draw_rect_dsc_init(&d);
      d.bg_color = theme::rgb(m.c); d.bg_opa = LV_OPA_COVER; d.radius = LV_RADIUS_CIRCLE;
      const int r = std::max(1, (int) std::lround(m.x2)), x = a.x1 + (int) std::lround(m.x1), y = a.y1 + (int) std::lround(m.y1);
      lv_area_t q{x - r, y - r, x + r - 1, y + r - 1};
      lv_draw_rect(layer, &d, &q);
      continue;
    }
    lv_draw_line_dsc_t d;
    lv_draw_line_dsc_init(&d);
    d.color = theme::rgb(m.c); d.width = m.w; d.opa = LV_OPA_COVER; d.round_start = d.round_end = m.round;
    d.p1.x = a.x1 + (lv_value_precise_t) std::lround(m.x1); d.p1.y = a.y1 + (lv_value_precise_t) std::lround(m.y1);
    d.p2.x = a.x1 + (lv_value_precise_t) std::lround(m.x2); d.p2.y = a.y1 + (lv_value_precise_t) std::lround(m.y2);
    lv_draw_line(layer, &d);
  }
}
inline void paint_free(lv_event_t *e) { delete static_cast<Paint *>(lv_event_get_user_data(e)); }
// A layer the size of `parent` that draws its marks; the Paint goes with it.
inline Paint &painter(lv_obj_t *parent, lv_obj_t **made = nullptr) {
  auto *o = lv_obj_create(parent);
  lv_obj_remove_style_all(o);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_size(o, lv_pct(100), lv_pct(100));
  auto *p = new Paint();
  lv_obj_add_event_cb(o, paint_draw, LV_EVENT_DRAW_MAIN, p);
  lv_obj_add_event_cb(o, paint_free, LV_EVENT_DELETE, p);
  if (made) *made = o;
  return *p;
}
inline lv_obj_t *box(lv_obj_t *parent, int x, int y, int w, int h, uint32_t color, int radius = 0) {
  auto *o = lv_obj_create(parent);
  lv_obj_remove_style_all(o);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_pos(o, x, y);
  lv_obj_set_size(o, std::max(1, w), std::max(1, h));
  lv_obj_set_style_bg_color(o, theme::rgb(color), 0);
  lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
  lv_obj_set_style_radius(o, radius, 0);
  return o;
}
inline int line_h(const lv_font_t *f) { return f ? lv_font_get_line_height(f) : 0; }
inline int digits_h(const lv_font_t *f) { int t = 0, h = 0; if (f) digit_box(f, t, h); return h; }
// Digits centred on (cx, y) with their visible top at y.
inline void digits_at(lv_obj_t *p, const std::string &s, int cx, int y, const lv_font_t *f, uint32_t ink) {
  if (!f) return;
  int t, h;
  digit_box(f, t, h);
  const int w = text_width(s, f) + 2;
  saver_text(p, f, ink, {cx - w / 2, y - t, w, line_h(f)}, s);
}
inline void digits_mid(lv_obj_t *p, const std::string &s, int cx, int cy, const lv_font_t *f, uint32_t ink) { digits_at(p, s, cx, cy - digits_h(f) / 2, f, ink); }
// The digit steps from large to small, the bedside step only where the board has one, then the two value fonts.
inline std::vector<const lv_font_t *> steps() {
  std::vector<const lv_font_t *> out;
  for (auto *f : {bedside_font, display_font, setpoint_font, clock_font, watch_value_font, watch_font})
    if (f && line_h(f) > 16 && std::find(out.begin(), out.end(), f) == out.end()) out.push_back(f);
  std::sort(out.begin(), out.end(), [](auto *a, auto *b) { return line_h(a) > line_h(b); });
  return out;
}
// The largest step whose `s` fits w and whose digits are at most h tall; the smallest one there is otherwise.
inline const lv_font_t *largest(const std::string &s, int w, int h) {
  const auto all = steps();
  for (auto *f : all) if (text_width(s, f) <= w && digits_h(f) <= h) return f;
  return all.empty() ? watch_font : all.back();
}
// The first of these fonts in which every text fits w.
inline const lv_font_t *fitting(std::initializer_list<const lv_font_t *> fonts, const std::vector<std::string> &texts, int w) {
  const lv_font_t *last = nullptr;
  for (auto *f : fonts) {
    if (!f) continue;
    last = f;
    bool ok = true;
    for (const auto &t : texts) ok = ok && text_width(t, f) <= w;
    if (ok) return f;
  }
  return last;
}

// ---- colours: theme.h's roles, read by the face's own look (dark, light, or the screen's)
inline bool dark_look(const SaverFace &f) { return f.look == SaverFace::DARK || (f.look == SaverFace::FOLLOW && theme::dark); }
inline uint32_t role(theme::Role r, bool dark) { return dark ? theme::ROLES[r].dark : theme::ROLES[r].light; }
struct Ink { bool dark; uint32_t face, ink, soft, tick, minor, hand, edge, accent, raised; };
inline Ink ink(const SaverFace &f) {
  Ink k;
  k.dark = dark_look(f);
  k.face = k.dark ? role(theme::CAMERA_PAGE, true) : role(theme::PAGE, false);
  k.ink = role(theme::INK, k.dark);
  k.soft = theme::mix(k.ink, k.face, 150);
  k.tick = theme::mix(k.ink, k.face, k.dark ? 225 : 235);
  k.minor = theme::mix(k.ink, k.face, k.dark ? 120 : 110);
  k.hand = role(theme::CLOCK_HAND, k.dark);
  k.edge = k.dark ? k.face : theme::mix(k.ink, k.face, 200);
  k.accent = theme::ha::ORANGE;
  k.raised = role(theme::CARD, k.dark);
  return k;
}

// ---- where the hands stand. The hour and the minute hand move once a minute, when the clock is drawn again.
inline float hour_angle(const esphome::ESPTime &t) { return (t.hour % 12 + t.minute / 60.f) * PI / 6; }
inline float minute_angle(const esphome::ESPTime &t) { return t.minute * PI / 30; }
inline float second_angle(int second) { return second * PI / 30; }

// The hands as the reference watch draws them: a thin stem out of the middle, then a capsule, white with a dark rim on
// a pale face; the seconds a thin orange line through the middle with a short tail, its marks last so tick can move it.
struct Hands { float cx, cy, hour, minute, second, tail; int blade, stem, sec; uint32_t hand, edge, accent, face; bool rim, seconds; };
inline void second_marks(Paint &p, const Hands &h, int second) {
  p.marks.resize(std::min(p.marks.size(), p.moving));
  p.moving = p.marks.size();
  const float a = second_angle(second), dx = std::sin(a), dy = -std::cos(a);
  p.line(h.cx - dx * h.tail, h.cy - dy * h.tail, h.cx + dx * h.second, h.cy + dy * h.second, h.sec, h.accent);
  p.dot(h.cx, h.cy, h.blade * 0.42f, h.accent);
  p.dot(h.cx, h.cy, std::max(1.f, h.blade * 0.16f), h.face);
}
inline void hands(Paint &p, const Hands &h, const esphome::ESPTime &t) {
  auto hand = [&](float a, float len) {
    const float dx = std::sin(a), dy = -std::cos(a), stem = std::max<float>(ui::mm(2), len * 0.16f);
    if (h.rim) {
      const int rim = std::max(1, h.blade / 7);
      p.line(h.cx, h.cy, h.cx + dx * stem, h.cy + dy * stem, h.stem + 2 * rim, h.edge);
      p.line(h.cx + dx * stem, h.cy + dy * stem, h.cx + dx * len, h.cy + dy * len, h.blade + 2 * rim, h.edge);
    }
    p.line(h.cx, h.cy, h.cx + dx * stem, h.cy + dy * stem, h.stem, h.hand);
    p.line(h.cx + dx * stem, h.cy + dy * stem, h.cx + dx * len, h.cy + dy * len, h.blade, h.hand);
  };
  hand(hour_angle(t), h.hour);
  hand(minute_angle(t), h.minute);
  const float r = h.blade * 0.62f;
  if (h.rim) p.dot(h.cx, h.cy, r + std::max(1, h.blade / 7), h.edge);
  p.dot(h.cx, h.cy, r, h.hand);
  if (h.seconds) second_marks(p, h, t.second);
}

// ---- the face on the glass now, for tick: its hands' layer and how its seconds hand stands
inline lv_obj_t *hands_obj = nullptr;
inline Hands shown;
inline int shown_second = -1;
// The box the seconds hand covers at `second`, in the layer's own coordinates, a little grown for its ends and dots.
inline lv_area_t second_box(const Hands &h, int second) {
  const float a = second_angle(second), dx = std::sin(a), dy = -std::cos(a);
  const float x1 = h.cx - dx * h.tail, y1 = h.cy - dy * h.tail, x2 = h.cx + dx * h.second, y2 = h.cy + dy * h.second;
  const int grow = std::max(h.sec, h.blade) + 2;
  return {(int) std::floor(std::min({x1, x2, h.cx})) - grow, (int) std::floor(std::min({y1, y2, h.cy})) - grow,
          (int) std::ceil(std::max({x1, x2, h.cx})) + grow, (int) std::ceil(std::max({y1, y2, h.cy})) + grow};
}
// Every second (saver_tick): the seconds hand one step on, only its old and its new strip drawn again.
void tick(const esphome::ESPTime &t) {
  if (!hands_obj || !shown.seconds || !t.is_valid() || t.second == shown_second) return;
  auto *p = static_cast<Paint *>(lv_obj_get_user_data(hands_obj));
  if (!p) return;
  lv_area_t coords;
  lv_obj_get_coords(hands_obj, &coords);
  for (int second : {shown_second, (int) t.second}) {
    if (second < 0) continue;
    lv_area_t box = second_box(shown, second);
    lv_area_move(&box, coords.x1, coords.y1);
    lv_obj_invalidate_area(hands_obj, &box);
  }
  second_marks(*p, shown, t.second);
  shown_second = t.second;
}
void forget() { hands_obj = nullptr; shown_second = -1; }
inline void keep_hands(lv_obj_t *o, Paint &p, const Hands &h, const esphome::ESPTime &t) {
  lv_obj_set_user_data(o, &p);
  hands_obj = o;
  shown = h;
  shown_second = h.seconds && t.is_valid() ? t.second : -1;
}

// ---- Glass: the dial is the glass. The ticks follow its outline, inset; every board has square corners today, so the
// ring is a rectangle (GLASS_CORNER, the radius a board with rounded glass would give).
constexpr float GLASS_CORNER = 0;
inline float rect_sdf(float x, float y, float hx, float hy, float r) {
  const float qx = std::fabs(x) - (hx - r), qy = std::fabs(y) - (hy - r);
  return std::hypot(std::max(qx, 0.f), std::max(qy, 0.f)) + std::min(std::max(qx, qy), 0.f) - r;
}
// How far from the middle a ray at `theta` (clockwise from 12) leaves the ring.
inline float ring_edge(float theta, float hx, float hy, float r) {
  const float dx = std::sin(theta), dy = -std::cos(theta);
  float lo = 0, hi = hx + hy;
  for (int i = 0; i < 32; ++i) { const float m = (lo + hi) / 2; (rect_sdf(m * dx, m * dy, hx, hy, r) < 0 ? lo : hi) = m; }
  return lo;
}
struct Seg { float x1, y1, x2, y2, w; };
// Whether a numeral's box, grown by `air`, touches a tick (sampled along it, half its width on either side).
inline bool touches(const std::vector<Seg> &ticks, float l, float t, float r, float b, float air) {
  for (const auto &s : ticks) for (int i = 0; i <= 12; ++i) {
    const float x = s.x1 + (s.x2 - s.x1) * i / 12, y = s.y1 + (s.y2 - s.y1) * i / 12, g = air + s.w / 2;
    if (x >= l - g && x <= r + g && y >= t - g && y <= b + g) return true;
  }
  return false;
}
inline void glass(lv_obj_t *stage, const SaverFace &f, const Ink &k, int W, int Hh, const esphome::ESPTime &now) {
  const int S = std::min(W, Hh);
  const float cx = W / 2.f, cy = Hh / 2.f;
  const float m = std::max<float>(ui::mm(2), S * 0.03f), hx = cx - m, hy = cy - m, r = GLASS_CORNER;
  const float major = S * 0.075f, minor = S * 0.034f;
  const int wmaj = std::max(3, (int) std::lround(S * 0.0095f)) | 1, wmin = std::max(1, (int) std::lround(S * 0.0042f));
  const int numerals = f.numerals;
  const lv_font_t *nf = numerals ? largest("12", W, (int) (S * (numerals == 4 ? 0.13f : 0.085f))) : nullptr;
  auto &p = painter(stage);
  std::vector<Seg> ticks;
  for (int i = 0; i < 60; ++i) {
    const float a = i * PI / 30, dx = std::sin(a), dy = -std::cos(a), e = ring_edge(a, hx, hy, r);
    const bool hour = i % 5 == 0;
    const int n = i / 5 == 0 ? 12 : i / 5;
    if (hour && nf && (numerals == 12 || n % 3 == 0)) continue;  // the numeral stands in its tick's place
    const float len = hour ? major : minor;
    const Seg s{cx + dx * e, cy + dy * e, cx + dx * (e - len), cy + dy * (e - len), (float) (hour ? wmaj : wmin)};
    ticks.push_back(s);
    p.line(s.x1, s.y1, s.x2, s.y2, hour ? wmaj : wmin, hour ? k.tick : k.minor, false);
  }
  // Each numeral starts just inside the short ticks and moves toward the middle until no tick comes within a clear gap:
  // on long glass the 12 is wider than the room between its neighbours.
  const float air = std::max<float>(ui::mm(1), S * 0.012f);
  if (nf) for (int n = 1; n <= 12; ++n) {
    if (numerals == 4 && n % 3) continue;
    const float a = n * PI / 6, dx = std::sin(a), dy = -std::cos(a), e = ring_edge(a, hx, hy, r);
    const std::string s = std::to_string(n);
    const float w = text_width(s, nf), h = digits_h(nf);
    float d = e - minor - air - (std::fabs(dx) * w / 2.f + std::fabs(dy) * h / 2.f);
    for (; d > 0; d -= 1) {
      const float x = cx + dx * d, y = cy + dy * d;
      if (!touches(ticks, x - w / 2, y - h / 2, x + w / 2, y + h / 2, air)) break;
    }
    digits_mid(stage, s, (int) std::lround(cx + dx * d), (int) std::lround(cy + dy * d), nf, k.ink);
  }
  if (!now.is_valid()) return;
  lv_obj_t *layer = nullptr;
  auto &hp = painter(stage, &layer);
  const float inner = std::min(hx, hy);
  const int blade = std::max(6, (int) std::lround(S * 0.036f));
  const Hands h{cx, cy, inner * 0.62f, inner - major * 0.35f, inner - minor * 0.4f, S * 0.06f, blade, std::max(3, blade / 3),
                std::max(2, (int) std::lround(S * 0.0055f)), k.hand, k.edge, k.accent, k.face, !k.dark, f.seconds};
  hands(hp, h, now);
  keep_hands(layer, hp, h, now);
}

// ---- Classic: a round dial, and beside it (long glass) or under it (standing glass) the day: its date large, the
// month, and the clock's row (the temperature and the entities) one to a line, as many as fit. On square glass the date
// stands in a window at 3, as on a watch.
inline void dial(lv_obj_t *stage, const SaverFace &f, const Ink &k, float cx, float cy, float R, bool window, const esphome::ESPTime &now) {
  box(stage, (int) (cx - R), (int) (cy - R), (int) (2 * R), (int) (2 * R), k.raised, LV_RADIUS_CIRCLE);
  auto &p = painter(stage);
  const float ro = R * 0.94f, major = R * 0.09f, minor = R * 0.045f;
  const int wmaj = std::max(3, (int) std::lround(R * 0.022f)) | 1, wmin = std::max(1, (int) std::lround(R * 0.008f));
  for (int i = 0; i < 60; ++i) {
    const float a = i * PI / 30, dx = std::sin(a), dy = -std::cos(a);
    const bool hour = i % 5 == 0;
    const float len = hour ? major : minor;
    p.line(cx + dx * ro, cy + dy * ro, cx + dx * (ro - len), cy + dy * (ro - len), hour ? wmaj : wmin, hour ? k.tick : k.minor, false);
  }
  const lv_font_t *nf = largest("12", (int) (2 * R), (int) (R * 0.15f));
  const float inset = ro - major - R * 0.07f;
  for (int n = 1; n <= 12; ++n) {
    if (window && n == 3) continue;
    const float a = n * PI / 6, dx = std::sin(a), dy = -std::cos(a);
    const std::string s = std::to_string(n);
    const float d = inset - (std::fabs(dx) * text_width(s, nf) / 2.f + std::fabs(dy) * digits_h(nf) / 2.f);
    digits_mid(stage, s, (int) std::lround(cx + dx * d), (int) std::lround(cy + dy * d), nf, k.ink);
  }
  if (window && now.is_valid() && now.day_of_week >= 1 && now.day_of_week <= 7 && label_font) {
    // The weekday and the day in a framed box in the place of 3, the day in the accent.
    const std::string day = tr(txt::date_weekdays_short + now.day_of_week - 1), number = std::to_string(now.day_of_month);
    const int pad = ui::mm(1) + 2, space = text_width(" ", label_font);
    const int dw = text_width(day, label_font), nw = text_width(number, label_font);
    const int ww = dw + space + nw + 2 * pad + 4, wh = line_h(label_font) + pad;
    auto *o = box(stage, (int) (cx + inset) - ww, (int) cy - wh / 2, ww, wh, k.face, ui::mm(1));
    lv_obj_set_style_border_width(o, std::max(1, wmin), 0);
    lv_obj_set_style_border_color(o, theme::rgb(k.minor), 0);
    saver_text(o, label_font, k.soft, {pad, (wh - line_h(label_font)) / 2 - 1, dw + 2, line_h(label_font)}, day, LV_TEXT_ALIGN_LEFT);
    saver_text(o, label_font, k.accent, {pad + dw + space, (wh - line_h(label_font)) / 2 - 1, nw + 2, line_h(label_font)}, number, LV_TEXT_ALIGN_LEFT);
  }
  if (!now.is_valid()) return;
  lv_obj_t *layer = nullptr;
  auto &hp = painter(stage, &layer);
  const int blade = std::max(5, (int) std::lround(R * 0.055f));
  const Hands h{cx, cy, R * 0.48f, R * 0.78f, R * 0.86f, R * 0.14f, blade, std::max(3, blade / 3), std::max(2, (int) std::lround(R * 0.011f)),
                k.hand, k.edge, k.accent, k.face, !k.dark, f.seconds};
  hands(hp, h, now);
  keep_hands(layer, hp, h, now);
}
// One line of the clock's row: its icon (if it has one) and its text, as the top bar shows the item.
struct Line { uint32_t icon; std::string text; };
inline std::vector<Line> row_lines(const std::vector<header_bar::Item> &row, const std::string &degrees, const esphome::ESPTime &now) {
  std::vector<Line> out;
  if (!row.empty()) {
    for (const auto &item : row) {
      auto text = page_header::item_text(item, now, now_epoch(), screen_settings::current.clock_24h != 0);
      if (!text.empty() || item.icon) out.push_back({item.icon, text});
    }
  } else if (!degrees.empty()) {
    out.push_back({0, degrees});
  }
  return out;
}
// The day's block: its fonts and how many of the row's lines it takes, for a column w wide and h tall. `stacked`: beside
// the dial, every part under the one before; else (under the dial) the date as one row and the rest in a centred column.
struct Day { const lv_font_t *big = nullptr, *word = nullptr, *value = nullptr; int lines = 0, width = 0, height = 0; };
// The lines' icons stand in one column, so every text starts at the same place whether its line has an icon or not.
inline bool with_icons(const std::vector<Line> &lines) {
  return header_icon_font && std::any_of(lines.begin(), lines.end(), [](const Line &l) { return l.icon != 0; });
}
inline int line_w(const Line &l, const lv_font_t *value, bool icons) {
  return (icons ? line_h(header_icon_font) + ui::mm(2) : 0) + text_width(l.text, value);
}
inline Day plan_day(const std::string &weekday, const std::string &month, const std::string &number, const std::vector<Line> &lines,
                    int w, int h, int dial_d, bool stacked) {
  Day d;
  const int g = ui::mm(2), gap = ui::mm(1);
  d.word = fitting({watch_value_font, watch_font, label_font}, {weekday, month}, stacked ? w : w / 2);
  std::vector<std::string> texts;
  for (const auto &l : lines) texts.push_back(l.text);
  d.value = fitting({watch_value_font, watch_font, label_font}, texts, std::max(1, w - (header_icon_font ? line_h(header_icon_font) + ui::mm(2) : 0)));
  const int row_h = std::max(header_icon_font ? line_h(header_icon_font) : 0, line_h(d.value));
  const int words = line_h(d.word);
  for (d.lines = (int) lines.size(); d.lines >= 0; --d.lines) {
    const int rows = d.lines ? 2 * g + d.lines * row_h + (d.lines - 1) * gap : 0;
    const int room = std::min(h - (stacked ? 2 * words + 2 * g : 0) - rows, (int) (dial_d * 0.3f));
    const int side = stacked ? w : w - std::max(text_width(weekday, d.word), text_width(month, d.word)) - ui::mm(4);
    d.big = largest(number, side, room);
    if (digits_h(d.big) <= room) break;
  }
  d.lines = std::max(0, d.lines);
  const int dh = digits_h(d.big);
  int widest = stacked ? std::max({text_width(number, d.big), text_width(weekday, d.word), text_width(month, d.word)})
                       : text_width(number, d.big) + ui::mm(4) + std::max(text_width(weekday, d.word), text_width(month, d.word));
  for (int i = 0; i < d.lines; ++i) widest = std::max(widest, line_w(lines[i], d.value, with_icons(lines)));
  d.width = std::min(w, widest);
  d.height = (stacked ? 2 * words + 2 * g + dh : std::max(dh, 2 * words)) + (d.lines ? 2 * g + d.lines * row_h + (d.lines - 1) * gap : 0);
  return d;
}
inline void draw_day(lv_obj_t *stage, const Ink &k, const Day &d, const std::string &weekday, const std::string &month,
                     const std::string &number, const std::vector<Line> &lines, int x, int y, bool stacked) {
  const int g = ui::mm(2), gap = ui::mm(1), words = line_h(d.word);
  int t, dh;
  digit_box(d.big, t, dh);
  int yy = y;
  if (stacked) {
    saver_text(stage, d.word, k.accent, {x, yy, d.width, words}, weekday, LV_TEXT_ALIGN_LEFT);
    yy += words + g;
    saver_text(stage, d.big, k.ink, {x, yy - t, text_width(number, d.big) + 2, line_h(d.big)}, number, LV_TEXT_ALIGN_LEFT);
    yy += dh + g;
    saver_text(stage, d.word, k.soft, {x, yy, d.width, words}, month, LV_TEXT_ALIGN_LEFT);
    yy += words;
  } else {
    // The day's number with the weekday over the month beside it, the pair on the digits' middle.
    const int nw = text_width(number, d.big), side = std::max(text_width(weekday, d.word), text_width(month, d.word));
    const int group = nw + ui::mm(4) + side, gx = x + (d.width - group) / 2, rh = std::max(dh, 2 * words);
    saver_text(stage, d.big, k.ink, {gx, yy + (rh - dh) / 2 - t, nw + 2, line_h(d.big)}, number, LV_TEXT_ALIGN_LEFT);
    saver_text(stage, d.word, k.accent, {gx + nw + ui::mm(4), yy + rh / 2 - words, side + 2, words}, weekday, LV_TEXT_ALIGN_LEFT);
    saver_text(stage, d.word, k.soft, {gx + nw + ui::mm(4), yy + rh / 2, side + 2, words}, month, LV_TEXT_ALIGN_LEFT);
    yy += rh;
  }
  if (!d.lines) return;
  yy += 2 * g;
  // Under the dial the lines stand in one centred column, left-aligned within it.
  int col = d.width;
  if (!stacked) { col = 0; for (int i = 0; i < d.lines; ++i) col = std::max(col, line_w(lines[i], d.value, with_icons(lines))); }
  const int lx = stacked ? x : x + (d.width - col) / 2;
  const int iw = header_icon_font ? line_h(header_icon_font) : 0, row_h = std::max(iw, line_h(d.value));
  for (int i = 0; i < d.lines; ++i) {
    const auto &l = lines[i];
    const int xx = lx + (with_icons(lines) ? iw + ui::mm(2) : 0);
    if (l.icon && header_icon_font)
      saver_text(stage, header_icon_font, k.soft, {lx, yy + (row_h - iw) / 2, iw + 2, iw}, tile_icon::utf8(l.icon), LV_TEXT_ALIGN_LEFT);
    saver_text(stage, d.value, k.ink, {xx, yy + (row_h - line_h(d.value)) / 2, std::max(1, lx + d.width - xx), line_h(d.value)}, l.text, LV_TEXT_ALIGN_LEFT);
    yy += row_h + gap;
  }
}
inline void classic(lv_obj_t *stage, const SaverFace &f, const Ink &k, int W, int Hh, const esphome::ESPTime &now,
                    const std::vector<header_bar::Item> &row, const std::string &degrees) {
  const int S = std::min(W, Hh);
  const int m = std::max<int>(ui::mm(3), S * 0.05f);
  const bool side = W >= Hh * 1.3f, under = Hh >= W * 1.3f;
  const int D = S - 2 * m;
  if ((side || under) && now.is_valid() && now.month >= 1 && now.month <= 12) {
    const std::string weekday = weekday_text(now), month = tr(txt::date_months + now.month - 1), number = std::to_string(now.day_of_month);
    const auto lines = row_lines(row, degrees, now);
    if (side) {
      // The dial and the day as one group in the middle of the glass.
      const int gap = std::max<int>(m, W * 0.05f), room = W - 2 * m - D - gap;
      const Day d = plan_day(weekday, month, number, lines, room, Hh - 2 * m, D, true);
      const int x0 = std::max(m, (W - (D + gap + d.width)) / 2);
      dial(stage, f, k, x0 + D / 2.f, Hh / 2.f, D / 2.f, false, now);
      draw_day(stage, k, d, weekday, month, number, lines, x0 + D + gap, (Hh - d.height) / 2, true);
    } else {
      const int gap = std::max<int>(m, Hh * 0.04f), room = Hh - 2 * m - D - gap;
      const Day d = plan_day(weekday, month, number, lines, W - 2 * m, room, D, false);
      const int y0 = std::max(m, (Hh - (D + gap + d.height)) / 2);
      dial(stage, f, k, W / 2.f, y0 + D / 2.f, D / 2.f, false, now);
      draw_day(stage, k, d, weekday, month, number, lines, (W - d.width) / 2, y0 + D + gap, false);
    }
    return;
  }
  dial(stage, f, k, W / 2.f, Hh / 2.f, D / 2.f, !side && !under, now);
}

// ---- Bauhaus: the glass as a grid of squares, each a shape in the school's colours, and a round clock with a ring.
// One square takes a new shape every minute, the whole glass a new composition every ten minutes, and the clock then
// moves to another spot near the middle, up to a twentieth of the short side away.
inline uint32_t mix32(uint32_t x) { x ^= x >> 16; x *= 0x7feb352du; x ^= x >> 15; x *= 0x846ca68bu; x ^= x >> 16; return x; }
inline void bauhaus(lv_obj_t *stage, const SaverFace &f, const Ink &k, int W, int Hh, const esphome::ESPTime &now) {
  const bool dk = k.dark;
  const uint32_t cream = role(theme::BAUHAUS_CREAM, dk), black = role(theme::BAUHAUS_BLACK, dk), red = role(theme::BAUHAUS_RED, dk);
  const uint32_t colours[] = {red, role(theme::BAUHAUS_YELLOW, dk), role(theme::BAUHAUS_BLUE, dk), black, cream};
  const uint32_t hand = dk ? role(theme::BAUHAUS_CREAM, false) : role(theme::BAUHAUS_BLACK, false);
  const int S = std::min(W, Hh);
  lv_obj_set_style_bg_color(stage, theme::rgb(cream), 0);
  const int n = 3, cell = std::max(1, S / n);
  const int rows = std::max(n, (Hh + cell / 2) / cell), cols = std::max(n, (W + cell / 2) / cell), cells = rows * cols;
  const int hour = now.is_valid() ? now.hour : 0, minute = now.is_valid() ? now.minute : 0;
  const uint32_t period = (uint32_t) (now.is_valid() ? now.day_of_year : 0) * 144u + hour * 6 + minute / 10;
  // How often each square was drawn anew since this composition began, one square a minute.
  std::vector<uint8_t> turns(cells, 0);
  for (int m = 1; m <= minute % 10; ++m) ++turns[mix32(period * 977u + m) % cells];
  for (int r = 0; r < rows; ++r) for (int c = 0; c < cols; ++c) {
    uint32_t seed = mix32(period * 7919u + (r * cols + c) * 131u + turns[r * cols + c] * 31337u);
    auto next = [&]() { seed = mix32(seed + 0x9e3779b9u); return seed & 0x7FFF; };
    const int x = c * W / cols, y = r * Hh / rows, w = (c + 1) * W / cols - x, h = (r + 1) * Hh / rows - y, e = std::min(w, h);
    const uint32_t ground = colours[next() % 5];
    uint32_t fig = colours[next() % 5];
    if (fig == ground) fig = ground == cream ? black : cream;
    auto *square = box(stage, x, y, w, h, ground);
    switch (next() % 5) {
      case 0: box(square, (w - e) / 2 + e / 8, (h - e) / 2 + e / 8, e * 3 / 4, e * 3 / 4, fig, LV_RADIUS_CIRCLE); break;  // a circle
      case 1: { const int q = next() % 4; box(square, q & 1 ? w - e : -e, q & 2 ? h - e : -e, 2 * e, 2 * e, fig, LV_RADIUS_CIRCLE); } break;  // a quarter
      case 2: { const bool up = next() & 1; box(square, (w - e) / 2, up ? -e / 2 : h - e / 2, e, e, fig, LV_RADIUS_CIRCLE); } break;  // a half
      case 3: box(square, 0, 0, w / 2, h, fig); break;  // half the square
      default: for (int i = 0; i < 3; ++i) box(square, 0, i * h / 3 + h / 12, w, std::max(2, h / 6), fig); break;  // stripes
    }
  }
  const float turn = period * 2.39996f, reach = S * 0.05f;
  const float cx = W / 2.f + std::cos(turn) * reach, cy = Hh / 2.f + std::sin(turn) * reach, R = S * 0.36f;
  // A ring in the hands' colour keeps the clock its own object, also where a shape of its colour touches it.
  auto *face = box(stage, (int) (cx - R), (int) (cy - R), (int) (2 * R), (int) (2 * R), dk ? black : cream, LV_RADIUS_CIRCLE);
  lv_obj_set_style_border_width(face, std::max(2, (int) (R * 0.035f)), 0);
  lv_obj_set_style_border_color(face, theme::rgb(hand), 0);
  auto &p = painter(stage);
  for (int i = 0; i < 12; ++i) {
    const float a = i * PI / 6;
    p.dot(cx + std::sin(a) * R * 0.84f, cy - std::cos(a) * R * 0.84f, i % 3 ? R * 0.025f : R * 0.05f, i % 3 ? hand : red);
  }
  if (!now.is_valid()) return;
  lv_obj_t *layer = nullptr;
  auto &hp = painter(stage, &layer);
  const int w = std::max(6, (int) (R * 0.09f));
  hp.line(cx, cy, cx + std::sin(hour_angle(now)) * R * 0.48f, cy - std::cos(hour_angle(now)) * R * 0.48f, w, hand);
  hp.line(cx, cy, cx + std::sin(minute_angle(now)) * R * 0.72f, cy - std::cos(minute_angle(now)) * R * 0.72f, w * 2 / 3, hand);
  hp.dot(cx, cy, w * 0.75f, red);
  const Hands h{cx, cy, 0, 0, R * 0.78f, 0, w, 0, std::max(2, w / 4), hand, hand, red, red, false, f.seconds};
  if (h.seconds) second_marks(hp, h, now.second);
  keep_hands(layer, hp, h, now);
}

// ---- the face on the glass: drawn whole into the screensaver's root, every minute
// Glass and Classic stand a fraction further along a slow circle every minute, up to a millimetre from their place.
inline lv_point_t drift(const esphome::ESPTime &now) {
  if (!now.is_valid()) return {0, 0};
  const float a = (now.hour * 60 + now.minute) * 0.7f, r = ui::mm(1);
  return {(int32_t) std::lround(std::cos(a) * r), (int32_t) std::lround(std::sin(a) * r)};
}
void draw(lv_obj_t *root, const SaverFace &f, const esphome::ESPTime &now, const std::vector<header_bar::Item> &row,
                 const std::string &degrees) {
  forget();
  const int W = overlay_card::screen_width(), Hh = overlay_card::screen_height();
  const Ink k = ink(f);
  lv_obj_set_style_bg_color(root, theme::rgb(k.face), 0);
  auto *stage = lv_obj_create(root);
  lv_obj_remove_style_all(stage);
  lv_obj_remove_flag(stage, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(stage, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_size(stage, W, Hh);
  if (f.kind != SaverFace::BAUHAUS) {
    const auto at = drift(now);
    lv_obj_set_pos(stage, at.x, at.y);
  } else {
    lv_obj_set_style_bg_opa(stage, LV_OPA_COVER, 0);
  }
  if (f.kind == SaverFace::GLASS) glass(stage, f, k, W, Hh, now);
  else if (f.kind == SaverFace::CLASSIC) classic(stage, f, k, W, Hh, now, row, degrees);
  else bauhaus(stage, f, k, W, Hh, now);
}

}  // namespace clock_faces
}  // namespace runtime_tiles
#endif
