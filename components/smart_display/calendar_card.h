#pragma once
// The calendar card: a Home Assistant calendar (or several on one card) that shows more as it gets more room, and a
// full screen a tap opens. This file only plans: what goes where, in which face and paint, and what a finger may hit.
// calendar_view.cpp paints a plan in one LVGL object per card, as the energy card does, so a week of events costs one
// object, not hundreds of labels (the CYD keeps its memory).
//
// The ladder (after Apple's widgets and the Watch, Fantastical, Superhuman, Readdle and Skylight: one thing per size,
// a tap opens instead of cramming, nothing hidden in silence):
//   Now      the head alone: the event of the moment (or Free) and until when, with a thin bar of how far it is.
//   Up next  the head and one block in the event's colour, its title as large as fits, never a word broken in two.
//   Agenda   up next and a few rows of what follows, the rest one quiet line.
//   Columns  a wide card: today and the next days side by side (Skylight's schedule).
//   Week     days as columns, hours as rows, a red line at now (four days of 16 mm, six readable hours).
// The full screen: a view key labelled with the view on show (Up next, Day, Week, Month), Today, back and forward.
// The week and a tall day scroll through the hours; the day has a strip of the week's days; the month a glance of
// dots or titles; a tapped event opens a sheet with everything Home Assistant knows of it.
// Every decision follows from the room and the board's faces and millimetres, never from a board's name.
#include "ui_scale.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>

namespace calendar_card {

// ---- The data the add-on sends (x.cal), relative to today in Home Assistant's time zone.
struct Event {
  int start = 0, end = 0;  // minutes from today 00:00 (negative: before today); an all-day event spans whole days
  uint8_t flags = 0;       // ALL_DAY, TENTATIVE, PRIVATE
  uint8_t cal = 0;         // which calendar of the card
  std::string title, place;
};
constexpr uint8_t ALL_DAY = 1, TENTATIVE = 2, PRIVATE = 4;
struct Data {
  int year = 0, month = 0, day = 0, weekday = 0;  // today; weekday 0 is Monday
  std::vector<uint32_t> colors;                   // one per calendar: Home Assistant's colour for it
  std::vector<std::string> names;                 // the calendars' names, for the event sheet
  std::vector<Event> events;                      // sorted by start
  int from = 0, to = 7;                           // days (from today) the events cover
  int left_out = 0;                               // events the message had no room for
  std::string notes;                              // the description of the event of the moment, or the next one
  bool asks = false;                              // the events are short: a tap asks the app for the rest (Detail)
  int glance_from = 0;                            // the month glance: its first day, from today
  std::vector<uint8_t> glance;                    // one mask per day from there: bit n = calendar n has something
  // "Status and booking" with booking on (the app sends it only for a calendar that takes new events): the calendar a
  // key books on, the place and the title the booking gets.
  std::string book_on, book_place, book_title;
};
// The rest of a tapped event, the app's answer when the events are short (Data::asks): its whole title, place and notes,
// for the event of that calendar, start and end.
struct Detail {
  int cal = -1, start = 0, end = 0;
  bool answered = false;
  std::string title, place, notes;
  bool of(const Event &e) const { return answered && e.cal == cal && e.start == start && e.end == end; }
};
inline bool all_day(const Event &e) { return e.flags & ALL_DAY; }
inline int day_of(int minute) { return minute >= 0 ? minute / 1440 : -((-minute + 1439) / 1440); }
inline bool on_day(const Event &e, int d) { return e.start < (d + 1) * 1440 && e.end > d * 1440; }
// A timed event of a day or more stands with the all-day ones in a week (as in Apple's and Google's calendars); a shorter
// one over midnight stands in both days' hours.
inline bool banded(const Event &e) { return all_day(e) || e.end - e.start >= 1440; }
// Where a timed event lies in the hours of `day`: its minutes from that midnight, cut to the day.
inline int start_in(const Event &e, int day) { return std::max(e.start - day * 1440, 0); }
inline int end_in(const Event &e, int day) { return std::min(e.end - day * 1440, 1440); }

// ---- The card's own choices (the tile's options, from the inspector).
struct Options {
  bool busy_free = false;  // "Free or busy": the head says Free, Starts soon or Busy, the title second
  int soon = 0;            // minutes before an event that the head calls "Starts soon" (0: never)
  std::string start_view;  // the full screen's first view: "", "up_next", "day", "week", "month"
  bool from_monday = false;  // a week from its Monday instead of from today
  int hours_from = 0, hours_to = 0;  // the hours a week shows (0, 0: the events' own, eight to eight at least)
  bool week_numbers = false;  // the month's weeks numbered (ISO 8601, as most of Europe counts them)
  bool room = false;      // "Status and booking": the room's state in one large word, green or red (a door's sign)
  bool book = false;      // ... with keys that book it now (the app sends it only for a calendar that takes new events)
  int booking = -1;       // the end (minutes of the day) of a booking on its way: its key says so until the events come
};

// ---- What the card says, in the screen's language (calendar_view.cpp fills it from the screen's texts).
struct Words {
  std::string free, busy, starts_soon, private_title, all_day, today, tomorrow, nothing, nothing_more;
  std::string until, next, left, in, more, earlier, later, week, more_week, days_view;  // with {x} where a value goes
  std::array<std::string, 7> days, days_long, letters;
  std::array<std::string, 12> months, months_short;
  std::array<std::string, 4> views, view_notes;  // Up next, Day, Week, Month and a line under each in the choice
  std::string today_key;
  std::string booking;  // a booking on its way ("Booking...")
  std::string calendars;  // the heading of the calendars in the view choice
  std::string also;  // "+{x} now": how many more events run at the same time (empty: not said)
  std::function<std::string(int)> clock;          // a minute of the day as the screen writes times
  std::function<std::string(int)> duration;       // minutes as the screen writes a span ("50 min", "2 h 10 min")
};
inline std::string with(const std::string &pattern, const std::string &value) {
  const auto at = pattern.find("{x}");
  return at == std::string::npos ? pattern + " " + value : pattern.substr(0, at) + value + pattern.substr(at + 3);
}
inline std::string span(const Words &w, int a, int b) { return w.clock((a % 1440 + 1440) % 1440) + " – " + w.clock((b % 1440 + 1440) % 1440); }
inline std::string plain_duration(int minutes) {
  char b[24];
  if (minutes >= 1440 && minutes % 1440 == 0) snprintf(b, sizeof b, "%d d", minutes / 1440);
  else if (minutes < 60) snprintf(b, sizeof b, "%d min", minutes);
  else if (minutes % 60) snprintf(b, sizeof b, "%d h %d", minutes / 60, minutes % 60);
  else snprintf(b, sizeof b, "%d h", minutes / 60);
  return b;
}

inline std::string dur(const Words &w, int minutes) { return w.duration ? w.duration(minutes) : plain_duration(minutes); }

// ---- The plan: rectangles, texts and the places a finger may hit, in the card's own coordinates.
enum Face : uint8_t { LABEL, SMALL, CONTROL, HEADLINE, VALUE, DIGITS, ICON, TILE_ICON, FACES };
enum Role : uint8_t {
  INK, MUTED, SUBTLE, TRACK, GRID, SOFT, CARD, KEY, NOW, ON_NOW, RAISED, RAISED_LINE, SCRIM, ACCENT, ACCENT_TINT,
  ON_TINT, ON_ICON, OFF_TINT, OFF_ICON,                 // the head's circle while an event runs, and while none does
  CAL_KEY, CAL_BLOCK, CAL_INK, CAL_TRACK,               // a calendar's own colour, its pale block, words on it, a track
  CAL_KEY_PAST, CAL_BLOCK_PAST, CAL_INK_PAST, ROLES
};
struct Paint { Role role = INK; uint8_t cal = 0; };
// Two colours a calendar never has: the room's free and busy (Home Assistant's green and red, calendar_paint.h).
constexpr uint8_t FREE_COLOUR = 254, BUSY_COLOUR = 255;
inline Paint cal(Role r, uint8_t c) { return Paint{r, c}; }
// `cw` > 0: drawn only inside (cx, cy, cw, ch), so a rounded shape can be cut to a strip of itself (the card's edge).
struct Box { int x = 0, y = 0, w = 0, h = 0, radius = 0; Paint paint; uint8_t opa = 255; int border = 0; Paint line; int cx = 0, cy = 0, cw = 0, ch = 0; };
enum Align : uint8_t { LEFT, CENTRE, RIGHT };
struct Text { int x = 0, y = 0, w = 0; Face face = SMALL; Paint paint; Align align = LEFT; std::string s; };
enum HitKind : uint8_t { HIT_NONE, HIT_EVENT, HIT_DAY, HIT_VIEW_KEY, HIT_TODAY, HIT_PREV, HIT_NEXT, HIT_CLOSE, HIT_VIEW, HIT_SHEET, HIT_SCRIM,
                         HIT_BOOK,       // a room's key that books it now: arg the minutes, the booking's end as minutes of the day
                         HIT_CALENDAR }; // a calendar's key in the view choice: arg the calendar, shown or hidden
struct Hit { int x = 0, y = 0, w = 0, h = 0; HitKind kind = HIT_NONE; int arg = 0; };
struct Scene {
  std::vector<Box> boxes;
  std::vector<Text> texts;
  std::vector<Hit> hits;
  int height = 0;  // a scrolling part's full height
  void clear() { boxes.clear(); texts.clear(); hits.clear(); height = 0; }
};

// ---- The board: line heights and widths of its faces, and its icon circle.
struct Measure {
  std::array<int, FACES> line{};
  std::function<int(Face, const std::string &)> width;
  int circle = 54;  // the board's icon circle (TILE_ICON_SIZE)
};
inline int L(const Measure &m, Face f) { return m.line[f]; }
inline bool large() { return ui::large(); }
inline int P(int big, int small) { return ui::px(large() ? big : small); }
// The bold label face on the standard look; the compact look's label is 11 px, too small to read a list on the CYD,
// so it takes its 14 px control face for both lines (the second in the muted paint).
inline Face title_face() { return large() ? LABEL : CONTROL; }
inline Face meta_face() { return large() ? SMALL : CONTROL; }
inline Face num_face() { return large() ? HEADLINE : CONTROL; }

// A line that never leaves its box: too long ends in three dots.
inline std::string fit(const Measure &m, Face f, const std::string &s, int w) {
  if (w <= 0) return "";
  if (m.width(f, s) <= w) return s;
  std::string out = s;
  const std::string dots = "...";
  while (!out.empty()) {
    // Cut whole UTF-8 characters.
    do out.pop_back(); while (!out.empty() && (static_cast<uint8_t>(out.back()) & 0xC0) == 0x80);
    if (!out.empty() && (static_cast<uint8_t>(out.back()) & 0x80)) { out.pop_back(); continue; }
    while (!out.empty() && out.back() == ' ') out.pop_back();
    if (m.width(f, out + dots) <= w) return out + dots;
  }
  return m.width(f, dots) <= w ? dots : "";
}
// Words wrapped onto at most `lines` lines; the last one ends in dots when the rest does not fit. A word wider than the
// box is never broken in two: it stands alone and ends in dots.
inline std::vector<std::string> wrap(const Measure &m, Face f, const std::string &s, int w, int lines) {
  std::vector<std::string> out, words;
  std::string cur;
  for (char c : s) { if (c == ' ') { if (!cur.empty()) words.push_back(cur); cur.clear(); } else cur += c; }
  if (!cur.empty()) words.push_back(cur);
  std::string line;
  size_t i = 0;
  while (i < words.size() && (int) out.size() < lines) {
    const std::string trial = line.empty() ? words[i] : line + " " + words[i];
    if (m.width(f, trial) <= w || line.empty()) {
      if (line.empty() && m.width(f, words[i]) > w) { out.push_back(fit(m, f, words[i], w)); ++i; line.clear(); continue; }
      line = trial; ++i;
    } else { out.push_back(line); line.clear(); }
  }
  if (!line.empty() && (int) out.size() < lines) out.push_back(line);
  if (i < words.size() && !out.empty()) {
    std::string rest = out.back();
    for (size_t k = i; k < words.size(); ++k) rest += " " + words[k];
    out.back() = fit(m, f, rest, w);
  }
  return out;
}
inline int lines_needed(const Measure &m, Face f, const std::string &s, int w) { return (int) wrap(m, f, s, w, 99).size(); }
inline int longest_word(const Measure &m, Face f, const std::string &s) {
  int most = 0; std::string cur;
  for (size_t i = 0; i <= s.size(); ++i) {
    if (i == s.size() || s[i] == ' ') { most = std::max(most, m.width(f, cur)); cur.clear(); }
    else cur += s[i];
  }
  return most;
}

// ---- Building a scene.
struct Pen {
  Scene &sc;
  const Measure &m;
  void box(int x, int y, int w, int h, Paint p, int radius = 0, uint8_t opa = 255) {
    if (w <= 0 || h <= 0) return;
    sc.boxes.push_back({x, y, w, h, radius, p, opa, 0, {}});
  }
  void framed(int x, int y, int w, int h, Paint p, Paint line, int radius, int border = 1) {
    if (w <= 0 || h <= 0) return;
    sc.boxes.push_back({x, y, w, h, radius, p, 255, border, line});
  }
  void text(int x, int y, int w, Face f, Paint p, const std::string &s, Align a = LEFT) {
    if (w <= 0 || s.empty()) return;
    sc.texts.push_back({x, y, w, f, p, a, fit(m, f, s, w)});
  }
  int para(int x, int y, int w, Face f, Paint p, const std::string &s, int lines) {
    const auto rows = wrap(m, f, s, w, lines);
    for (size_t i = 0; i < rows.size(); ++i) sc.texts.push_back({x, y + (int) i * L(m, f), w, f, p, LEFT, rows[i]});
    return (int) rows.size() * L(m, f);
  }
  void hit(int x, int y, int w, int h, HitKind k, int arg = 0) { sc.hits.push_back({x, y, w, h, k, arg}); }
};

// An event's block in its calendar's pale colour; a tentative one (Home Assistant's status tentative, which its own
// calendar stripes) is the card with a line in the calendar's colour round it: it reads on every glass and costs no
// stripes to draw.
inline void event_block(Pen &p, int x, int y, int w, int h, const Event &e, bool past, int radius) {
  if (e.flags & TENTATIVE) p.framed(x, y, w, h, Paint{CARD}, cal(past ? CAL_KEY_PAST : CAL_KEY, e.cal), radius, P(2, 1));
  else p.box(x, y, w, h, cal(past ? CAL_BLOCK_PAST : CAL_BLOCK, e.cal), radius);
}

// ---- What is on now.
struct Moment { int day = 0, minute = 0; int at() const { return day * 1440 + minute; } };
struct Status { int now = -1, next = -1, also = 0; bool soon = false; };
// A timed event that runs now wins over an all-day one (Home Assistant's state picks the earliest start, so a day-long
// event would hide the meeting); the next is the first that starts after now.
inline Status status(const Data &d, Moment t, const Options &o) {
  Status s;
  const int T = t.at();
  for (size_t i = 0; i < d.events.size(); ++i) {
    const auto &e = d.events[i];
    if (all_day(e)) continue;
    if (e.start <= T && T < e.end) { if (s.now < 0) s.now = (int) i; else ++s.also; }
    else if (e.start > T && (s.next < 0 || e.start < d.events[s.next].start)) s.next = (int) i;
  }
  if (s.next < 0)
    for (size_t i = 0; i < d.events.size(); ++i)
      if (all_day(d.events[i]) && d.events[i].start > T) { s.next = (int) i; break; }
  s.soon = s.now < 0 && s.next >= 0 && o.soon > 0 && !all_day(d.events[s.next]) && d.events[s.next].start - T <= o.soon;
  return s;
}
inline std::string title_of(const Event &e, const Words &w) { return (e.flags & PRIVATE) || e.title.empty() ? w.private_title : e.title; }
// The date of a day from today (the month's day number), with the months' lengths.
inline int days_in(int year, int month) {
  static const int n[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  return month == 2 && ((year % 4 == 0 && year % 100) || year % 400 == 0) ? 29 : n[(month + 11) % 12];
}
struct Date { int year, month, day, weekday; };
inline Date date_of(const Data &d, int offset) {
  Date r{d.year, d.month, d.day, ((d.weekday + offset) % 7 + 7) % 7};
  while (offset > 0) { if (++r.day > days_in(r.year, r.month)) { r.day = 1; if (++r.month > 12) { r.month = 1; ++r.year; } } --offset; }
  while (offset < 0) { if (--r.day < 1) { if (--r.month < 1) { r.month = 12; --r.year; } r.day = days_in(r.year, r.month); } ++offset; }
  return r;
}
inline std::string short_day(const Words &w, const Data &d, int day, int today) {
  if (day == today) return w.today;
  if (day == today + 1) return w.tomorrow;
  const Date dt = date_of(d, day);
  // A week or more away the day names its month too ("Wed 4 Nov"): "Wed 4" would read as this week's.
  const bool far = std::abs(day - today) >= 7 && !w.months_short[dt.month - 1].empty();
  return w.days[dt.weekday] + " " + std::to_string(dt.day) + (far ? " " + w.months_short[dt.month - 1] : "");
}
inline std::string long_day(const Words &w, const Data &d, int day) {
  const Date dt = date_of(d, day);
  return w.days_long[dt.weekday] + " " + std::to_string(dt.day) + " " + w.months[dt.month - 1];
}
inline std::string at_time(const Words &w, const Data &d, int minute, int today, bool end = false) {
  const int day = day_of(end ? minute - 1 : minute), clock = ((minute % 1440) + 1440) % 1440;
  return day == today ? w.clock(clock) : short_day(w, d, day, today) + " " + w.clock(clock);
}
inline std::string when(const Words &w, const Data &d, const Event &e, int today) { return at_time(w, d, e.start, today); }
// An event's times; one over midnight names its days ("Wed 22:00 – Thu 06:00").
inline std::string span_of(const Words &w, const Data &d, const Event &e) {
  const int a = day_of(e.start), z = day_of(e.end - 1);
  if (a == z) return span(w, e.start, e.end);
  return w.days[date_of(d, a).weekday] + " " + w.clock(((e.start % 1440) + 1440) % 1440) + " – " +
         w.days[date_of(d, z).weekday] + " " + w.clock(((e.end % 1440) + 1440) % 1440);
}

// How long a running event still goes: the time left ("50 min left", a night shift's "7 h left"); more than half a day
// on another day reads better as the day and time it ends ("Until Thu 17:00" over "26 h 50 left").
inline bool far_end(const Event &e, Moment t) { return day_of(e.end - 1) != t.day && e.end - t.at() > 720; }
inline std::string left_of(const Words &w, const Data &d, const Event &e, Moment t) {
  return far_end(e, t) ? with(w.until, at_time(w, d, e.end, t.day, true)) : with(w.left, dur(w, e.end - t.at()));
}
// The head's two lines on a small card: what runs (or Free), and until when or what comes next.
// `brief`: the second line when the whole one does not fit, the one thing it must say (until when, when the next starts).
struct HeadWords { std::string first, second, brief; bool on = false; };
inline HeadWords head_words(const Data &d, Moment t, const Options &o, const Words &w, const std::string &name) {
  HeadWords h;
  const Status s = status(d, t, o);
  h.on = s.now >= 0;
  if (s.now >= 0) {
    const auto &e = d.events[s.now];
    const std::string until = with(w.until, at_time(w, d, e.end, t.day, true)), left = far_end(e, t) ? "" : with(w.left, dur(w, e.end - t.at()));
    if (o.busy_free) { h.first = w.busy; h.second = until + " · " + title_of(e, w); }
    else { h.first = title_of(e, w); h.second = left.empty() ? until : until + " · " + left; }
    h.brief = until;
  } else if (s.next >= 0) {
    const auto &e = d.events[s.next];
    if (s.soon) { h.first = w.starts_soon; h.second = with(w.in, dur(w, e.start - t.at())) + " · " + title_of(e, w); h.brief = with(w.in, dur(w, e.start - t.at())); }
    else { h.first = w.free; h.second = with(w.next, when(w, d, e, t.day)) + " · " + title_of(e, w); h.brief = with(w.next, when(w, d, e, t.day)); }
  } else { h.first = w.free; h.second = h.brief = w.nothing; }
  (void) name;
  return h;
}

// ---- The head every tile has: the round icon, a bold first line, a quiet second line (runtime_tiles head_row's rule:
// the circle the board's size, the lines with the look's spacing, all in the middle of the room).
inline int head_gap() { return P(6, 1); }
inline int head_height(const Measure &m) { return std::max(m.circle, L(m, LABEL) + head_gap() + L(m, SMALL)); }
inline const char *GLYPH_ON = "\U000F00EF", *GLYPH_OFF = "\U000F00EE", *GLYPH_CLOSE = "\U000F0156",
                  *GLYPH_LEFT = "\U000F0141", *GLYPH_RIGHT = "\U000F0142", *GLYPH_MENU = "\U000F035D",
                  *GLYPH_CHECK = "\U000F012C", *GLYPH_PLACE = "\U000F07D9", *GLYPH_CLOCK = "\U000F0150",
                  *GLYPH_CALENDAR = "\U000F00ED";
inline void head(Pen &p, int x, int y, int w, int h, bool on, const std::string &first, const std::string &second, const std::string &brief = "") {
  const auto &m = p.m;
  const int circle = std::max(1, std::min(m.circle, h)), gap = head_gap();
  const int block = std::max(circle, L(m, LABEL) + gap + L(m, SMALL)), y0 = y + std::max(0, (h - block) / 2);
  // A room lower than the two lines keeps the circle inside it (the lines may reach into the card's padding).
  const int cy = block > h ? y + (h - circle) / 2 : y0 + (block - circle) / 2;
  p.box(x, cy, circle, circle, Paint{on ? ON_TINT : OFF_TINT}, circle / 2);
  const Face g = circle >= P(40, 28) ? TILE_ICON : ICON;
  p.sc.texts.push_back({x, cy + (circle - L(m, g)) / 2, circle, g, Paint{on ? ON_ICON : OFF_ICON}, CENTRE, on ? GLYPH_ON : GLYPH_OFF});
  const int tx = x + circle + P(10, 12), tw = w - (tx - x), th = L(m, LABEL) + gap + L(m, SMALL), ty = block > h ? y + (h - th) / 2 : y0 + (block - th) / 2;
  p.text(tx, ty, tw, LABEL, Paint{INK}, first);
  // A second line that does not fit says its one essential thing whole ("Until 15:00") rather than cut ("Until 15:00 · 50...").
  p.text(tx, ty + L(m, LABEL) + gap, tw, SMALL, Paint{MUTED}, !brief.empty() && m.width(SMALL, second) > tw ? brief : second);
}

inline int module_pad() { return P(12, 6); }
inline int module_radius() { return P(14, 8); }
inline int row_gap() { return P(10, 4); }

// ---- Up next: the event of the moment, or the next one, in a block of its colour. The title takes the largest face
// in which it fits on two lines with every word whole; the time sits above it, how far it has come under it.
inline int up_next_min(const Measure &m) { return 2 * module_pad() + L(m, meta_face()) + P(6, 3) + L(m, title_face()) + P(10, 5) + P(6, 4); }
inline void up_next(Pen &p, int x, int y, int w, int h, const Data &d, Moment t, const Options &o, const Words &wd) {
  const auto &m = p.m;
  const int mp = module_pad();
  const Face mf = meta_face();
  const Status s = status(d, t, o);
  const int i = s.now >= 0 ? s.now : s.next;
  if (i < 0) {
    p.box(x, y, w, h, Paint{TRACK}, module_radius());
    p.text(x + mp, y + (h - L(m, mf)) / 2, w - 2 * mp, mf, Paint{MUTED}, wd.nothing);
    return;
  }
  const auto &e = d.events[i];
  const bool running = s.now >= 0;
  const Paint ink = running ? cal(CAL_INK, e.cal) : Paint{INK}, soft = running ? cal(CAL_INK, e.cal) : Paint{MUTED};
  if (running) event_block(p, x, y, w, h, e, false, module_radius());
  else p.box(x, y, w, h, Paint{TRACK}, module_radius());
  p.hit(x, y, w, h, HIT_EVENT, i);
  const int bar = P(4, 3), tx = x + mp + bar + P(10, 6), W = x + w - mp - tx;
  p.box(x + mp, y + mp, bar, h - 2 * mp, cal(CAL_KEY, e.cal), bar / 2);
  std::string left_words, right_words;
  if (running) { left_words = all_day(e) ? wd.all_day : span_of(wd, d, e); right_words = left_of(wd, d, e, t); }
  else {
    const std::string at = all_day(e) ? wd.all_day : span_of(wd, d, e);
    left_words = (o.busy_free && s.soon ? wd.starts_soon : wd.next.substr(0, wd.next.find("{x}"))) ;
    while (!left_words.empty() && left_words.back() == ' ') left_words.pop_back();
    const int day = day_of(e.start);
    left_words += (left_words.empty() ? "" : " · ") + (day == t.day ? at : short_day(wd, d, day, t.day) + " " + at);
    // Days away, the days count ("in 3 d"), not the hours of them.
    const int days = day_of(e.start) - t.day;
    right_words = with(wd.in, e.start - t.at() > 720 && days > 0 ? dur(wd, days * 1440) : dur(wd, std::max(1, e.start - t.at())));
  }
  const int rw = m.width(mf, right_words) + 2, lw = W - rw - P(8, 4);
  const bool both = m.width(mf, left_words) <= lw;
  p.text(tx, y + mp, both ? lw : W, mf, soft, left_words);
  if (both) p.text(tx + W - rw, y + mp, rw, mf, soft, right_words, RIGHT);
  const int bar_h = running ? P(6, 4) + P(10, 5) : 0, top = y + mp + L(m, mf) + P(6, 3), room = y + h - mp - bar_h - top;
  Face face = title_face();
  int lines = 1;
  const std::string title = title_of(e, wd);
  for (Face c : {VALUE, HEADLINE, title_face()}) {
    if (!L(m, c)) continue;
    const int need = lines_needed(m, c, title, W);
    if (need <= 2 && need * L(m, c) <= room && longest_word(m, c, title) <= W) { face = c; lines = need; break; }
  }
  lines = std::max(1, std::min(lines, room / std::max(1, L(m, face))));
  p.para(tx, top + std::max(0, (room - lines * L(m, face)) / 2), W, face, ink, title, lines);
  if (running) {
    const int bh = P(6, 4), by = y + h - mp - bh, done = std::clamp(1000 * (t.at() - e.start) / std::max(1, e.end - e.start), 0, 1000);
    // More than one event at a time: the bar leaves room at its end for how many more run now (a tap opens the day).
    const std::string also = s.also && !wd.also.empty() ? with(wd.also, std::to_string(s.also)) : "";
    const int aw = also.empty() ? 0 : m.width(mf, also) + P(12, 6), bw = W - aw;
    p.box(tx, by, bw, bh, cal(CAL_TRACK, e.cal), bh / 2);
    p.box(tx, by, std::max(bh, bw * done / 1000), bh, cal(CAL_KEY, e.cal), bh / 2);
    if (aw) p.text(tx + bw, by + bh / 2 - L(m, mf) / 2, aw, mf, soft, also, RIGHT);
  }
}

// ---- The rows of what follows.
inline int event_row(const Measure &m) { return L(m, title_face()) + P(2, 1) + L(m, meta_face()); }
inline int row_of(const Measure &m, const Event &e) { return all_day(e) ? L(m, title_face()) : event_row(m); }
inline int shown_day(const Event &e, int today) { return std::max(day_of(e.start), today); }
inline std::vector<int> coming(const Data &d, Moment t, const Status &s, int from = -9999, int to = 9999) {
  std::vector<int> out;
  const int T = t.at();
  for (size_t i = 0; i < d.events.size(); ++i) {
    const auto &e = d.events[i];
    if ((int) i == s.now || e.end <= T) continue;
    const int day = shown_day(e, t.day);
    if (day < from || day > to) continue;
    out.push_back((int) i);
  }
  std::stable_sort(out.begin(), out.end(), [&](int a, int b) {
    const auto &x = d.events[a], &y = d.events[b];
    const int dx = shown_day(x, t.day), dy = shown_day(y, t.day);
    if (dx != dy) return dx < dy;
    if (all_day(x) != all_day(y)) return all_day(x);
    return x.start < y.start;
  });
  return out;
}
inline void event_line(Pen &p, int x, int y, int w, const Data &d, const Event &e, int index, const Words &wd, bool past = false) {
  const auto &m = p.m;
  const int bar = P(4, 3), h = row_of(m, e), tx = x + bar + P(10, 6), tw = w - (tx - x);
  p.box(x, y, bar, h, cal(past ? CAL_KEY_PAST : CAL_KEY, e.cal), bar / 2);
  p.hit(x, y, w, h, HIT_EVENT, index);
  if (all_day(e)) {
    const int aw = m.width(meta_face(), wd.all_day) + 2;
    p.text(tx, y, tw - aw - P(8, 4), title_face(), Paint{past ? MUTED : INK}, title_of(e, wd));
    p.text(tx + tw - aw, y + (h - L(m, meta_face())) / 2, aw, meta_face(), Paint{MUTED}, wd.all_day, RIGHT);
    return;
  }
  p.text(tx, y, tw, title_face(), Paint{past ? MUTED : INK}, title_of(e, wd));
  const std::string times = span_of(wd, d, e), with_place = times + (e.place.empty() ? "" : " · " + e.place);
  p.text(tx, y + L(m, title_face()) + P(2, 1), tw, meta_face(), Paint{MUTED}, m.width(meta_face(), with_place) <= tw ? with_place : times);
}
// The list module: a grey block of rows grouped by day. Wide enough (70 mm), the date stands in a column at the left;
// narrow, a quiet day word heads each day. At most `cap` rows; the last line says how many more there are.
// `shown`: the event the up next block above already shows (the next one while nothing runs), left out of the rows.
inline void list(Pen &p, int x, int y, int w, int h, const Data &d, Moment t, const Status &s, const Words &wd, int cap, int shown = -1) {
  const auto &m = p.m;
  const int mp = module_pad(), W = w - 2 * mp, bottom = y + h - mp, gap = row_gap();
  p.box(x, y, w, h, Paint{TRACK}, module_radius());
  auto items = coming(d, t, s);
  items.erase(std::remove(items.begin(), items.end(), shown), items.end());
  const Face mf = meta_face();
  if (items.empty()) { p.text(x + mp, y + (h - L(m, mf)) / 2, W, mf, Paint{MUTED}, wd.nothing_more); return; }
  const bool date_column = w >= ui::mm(70);
  const Face num = num_face();
  int widest_day = 0;
  for (auto &day_name : wd.days) widest_day = std::max(widest_day, m.width(SMALL, day_name));
  const int date_w = std::max(widest_day, m.width(num, "30")) + P(14, 8), caption_h = L(m, SMALL) + P(4, 2);
  // In the date column a day's first row is at least as tall as its date (the weekday over the number), so a day of
  // one all-day line never lets the next day's date run into it.
  const int date_h = L(m, SMALL) + L(m, num);
  auto row_h = [&](int k, bool first) { const int h = row_of(m, d.events[items[k]]); return first && date_column ? std::max(h, date_h) : h; };
  auto need_of = [&](int k, int day) {
    const int dd = shown_day(d.events[items[k]], t.day);
    const bool nd = dd != day;
    return row_h(k, nd) + (nd ? (date_column ? 0 : caption_h) : P(6, 2)) + (nd && day != -9999 ? gap : 0);
  };
  auto fitting = [&](int reserve) {
    int yy = y + mp, day = -9999, k = 0;
    for (; k < (int) items.size() && k < cap; ++k) {
      const int need = need_of(k, day), left = (int) items.size() - k - 1;
      if (yy + need + (left > 0 ? reserve : 0) > bottom) break;
      yy += need; day = shown_day(d.events[items[k]], t.day);
    }
    return k;
  };
  int show = fitting(gap + L(m, mf));
  if (show == 0) show = std::min((int) items.size(), std::max(1, fitting(0)));
  int yy = y + mp, day = -9999;
  for (int k = 0; k < show; ++k) {
    const auto &e = d.events[items[k]];
    const int dd = shown_day(e, t.day);
    const bool nd = dd != day;
    if (nd && day != -9999) yy += gap;
    if (nd) {
      if (date_column) {
        const Date dt = date_of(d, dd);
        const Paint c = dd == t.day ? Paint{NOW} : Paint{MUTED};
        p.text(x + mp, yy, date_w, SMALL, c, wd.days[dt.weekday]);
        p.text(x + mp, yy + L(m, SMALL), date_w, num, dd == t.day ? Paint{NOW} : Paint{INK}, std::to_string(dt.day));
      } else { p.text(x + mp, yy, W, SMALL, Paint{MUTED}, short_day(wd, d, dd, t.day)); yy += caption_h; }
      day = dd;
    } else yy += P(6, 2);
    event_line(p, x + mp + (date_column ? date_w : 0), yy, W - (date_column ? date_w : 0), d, e, items[k], wd);
    yy += row_h(k, nd);
  }
  // "12 more this week" counts this week only. The app keeps the nearest events, so when the ones it sent reach past
  // Sunday, none of this week was left out; when they do not, the rest is said without the week ("40 more").
  const int sunday = 6 - d.weekday;
  bool past_week = false;
  for (const auto &e : d.events) past_week |= shown_day(e, t.day) > sunday;
  int week_rest = 0;
  for (int k = show; k < (int) items.size(); ++k) week_rest += shown_day(d.events[items[k]], t.day) <= sunday;
  const bool whole_week = past_week || d.left_out == 0;
  const int rest = whole_week ? week_rest : (int) items.size() - show + d.left_out;
  if (rest > 0 && yy + gap + L(m, mf) <= bottom)
    p.text(x + mp + (date_column ? date_w : 0), yy + gap, W - (date_column ? date_w : 0), mf, Paint{MUTED},
           with(whole_week ? wd.more_week : wd.more, std::to_string(rest)));
}
// Columns: today and the next days side by side, the event of the moment above the first.
inline void columns(Pen &p, int x, int y, int w, int h, const Data &d, Moment t, const Options &o, const Words &wd, int n) {
  const auto &m = p.m;
  const Status s = status(d, t, o);
  const int gap = P(12, 6), cw = (w - (n - 1) * gap) / n, mp = module_pad();
  for (int k = 0; k < n; ++k) {
    const int day = t.day + k, cx = x + k * (cw + gap);
    if (day > d.to) break;
    p.box(cx, y, cw, h, Paint{TRACK}, module_radius());
    const int W = cw - 2 * mp;
    p.text(cx + mp, y + mp, W, SMALL, day == t.day ? Paint{NOW} : Paint{MUTED}, short_day(wd, d, day, t.day));
    int yy = y + mp + L(m, SMALL) + P(8, 4);
    if (k == 0 && s.now >= 0 && yy + up_next_min(m) <= y + h - mp) { up_next(p, cx + mp / 2, yy, cw - mp, up_next_min(m), d, t, o, wd); yy += up_next_min(m) + P(8, 4); }
    const auto items = coming(d, t, s, day, day);
    int i = 0;
    const int cnt = (int) items.size();
    for (; i < cnt; ++i) {
      const int rh = row_of(m, d.events[items[i]]);
      const bool more_after = i < cnt - 1;
      if (yy + rh > y + h - mp || (more_after && yy + rh + P(8, 4) + L(m, meta_face()) > y + h - mp)) break;
      event_line(p, cx + mp, yy, W, d, d.events[items[i]], items[i], wd);
      yy += rh + P(10, 4);
    }
    if (i < cnt) p.text(cx + mp, std::min(yy, y + h - mp - L(m, meta_face())), W, meta_face(), Paint{MUTED}, with(wd.more, std::to_string(cnt - i)));
    else if (cnt == 0 && !(k == 0 && s.now >= 0)) p.text(cx + mp, yy, W, meta_face(), Paint{MUTED}, wd.nothing);
  }
}

// ---- The week: days as columns, hours as rows.
// The hour column: as wide as the screen's longest hour ("00:00", or "10 PM" on a 12-hour clock).
inline int gutter(const Measure &m, const Words *wd = nullptr) {
  int w = m.width(SMALL, "00:00");
  for (int h = 0; wd && wd->clock && h < 24; ++h) w = std::max(w, m.width(SMALL, wd->clock(h * 60)));
  return w + P(10, 4);
}
// A day's head ("Wed 30") needs about six characters; the 16 mm a column needs for a title are more on every board.
inline int day_min(const Measure &m) { return std::max(ui::mm(16), m.width(SMALL, "000 00") + P(10, 6)); }
inline int fit_days(const Measure &m, int w) { return std::clamp((w - gutter(m)) / std::max(1, day_min(m)), 1, 7); }
inline int hour_min(const Measure &m) { return L(m, title_face()) + P(10, 4); }
inline int hour_pref(const Measure &m) { return 2 * L(m, SMALL) + P(4, 2); }
inline int header_h(const Measure &m) { return L(m, num_face()) + P(10, 4); }
inline int allday_h(const Measure &m) { return L(m, SMALL) + P(8, 4); }
// Four days of 16 mm and six hours tall enough that a half-hour event keeps its title (the full screen: three days).
inline bool week_fits(const Measure &m, int w, int h, bool card = true) {
  return fit_days(m, w) >= (card ? 4 : 3) && (h - header_h(m) - 2 * allday_h(m) - L(m, SMALL)) / hour_pref(m) >= 6;
}
struct Lane { int index, lane, lanes; };
inline std::vector<Lane> lanes_of(const Data &d, int day) {
  std::vector<int> evs;
  for (size_t i = 0; i < d.events.size(); ++i) if (!banded(d.events[i]) && on_day(d.events[i], day)) evs.push_back((int) i);
  std::stable_sort(evs.begin(), evs.end(), [&](int a, int b) { return start_in(d.events[a], day) < start_in(d.events[b], day); });
  std::vector<Lane> out;
  std::vector<int> ends;
  size_t cluster = 0;
  int cluster_end = -1;
  auto close = [&]() { const int n = std::max(1, (int) ends.size()); for (size_t i = cluster; i < out.size(); ++i) out[i].lanes = n; ends.clear(); cluster = out.size(); };
  for (int i : evs) {
    const int a = start_in(d.events[i], day), z = end_in(d.events[i], day);
    if (a >= cluster_end && !out.empty()) close();
    int lane = -1;
    for (int k = 0; k < (int) ends.size(); ++k) if (ends[k] <= a) { lane = k; break; }
    if (lane < 0) { lane = (int) ends.size(); ends.push_back(0); }
    ends[lane] = z; cluster_end = std::max(cluster_end, z);
    out.push_back({i, lane, 1});
  }
  close();
  return out;
}
struct WeekShape {
  int d0 = 0, days = 7, gw = 0, cw = 0;
  int h0 = 8, h1 = 20, hour_h = 0;
  bool bare = false;
};
// The day heads of a week: the name quiet, the date in ink, today's date white in a red circle. A tap picks the day.
inline int week_heads(Pen &p, int x, int y, const WeekShape &ws, const Data &d, Moment t, const Words &wd) {
  const auto &m = p.m;
  const Face num = num_face();
  if (ws.bare) {
    const int hh = L(m, SMALL) + L(m, num) + P(6, 3);
    for (int k = 0; k < ws.days; ++k) {
      const int day = ws.d0 + k, cx = x + ws.gw + k * ws.cw;
      const Date dt = date_of(d, day);
      const bool weekend = dt.weekday >= 5;
      p.text(cx, y, ws.cw, SMALL, Paint{weekend ? SUBTLE : MUTED}, wd.letters[dt.weekday], CENTRE);
      const std::string ds = std::to_string(dt.day);
      if (day == t.day) {
        const int c = L(m, num), cwid = std::max(c, m.width(num, ds) + P(8, 4));
        p.box(cx + (ws.cw - cwid) / 2, y + L(m, SMALL), cwid, c, Paint{NOW}, c / 2);
        p.text(cx + (ws.cw - cwid) / 2, y + L(m, SMALL), cwid, num, Paint{ON_NOW}, ds, CENTRE);
      } else p.text(cx, y + L(m, SMALL), ws.cw, num, Paint{weekend ? SUBTLE : INK}, ds, CENTRE);
      p.hit(cx, y, ws.cw, hh, HIT_DAY, day);
    }
    return hh;
  }
  const int hh = header_h(m);
  for (int k = 0; k < ws.days; ++k) {
    const int day = ws.d0 + k, cx = x + ws.gw + k * ws.cw;
    const Date dt = date_of(d, day);
    const bool weekend = dt.weekday >= 5;
    const std::string name = wd.days[dt.weekday], ds = std::to_string(dt.day);
    const int nw = m.width(SMALL, name), dw = m.width(num, ds), sp = P(6, 3), circ = L(m, num) + P(2, 0);
    const int cwid = std::max(circ, dw + P(10, 6)), tw = nw + sp + (day == t.day ? cwid : dw), x0 = cx + std::max(0, (ws.cw - tw) / 2);
    p.text(x0, y + (hh - L(m, SMALL)) / 2 + P(2, 1), nw + 2, SMALL, Paint{weekend ? SUBTLE : MUTED}, name);
    if (day == t.day) {
      p.box(x0 + nw + sp, y + (hh - circ) / 2, cwid, circ, Paint{NOW}, circ / 2);
      p.text(x0 + nw + sp, y + (hh - L(m, num)) / 2, cwid, num, Paint{ON_NOW}, ds, CENTRE);
    } else p.text(x0 + nw + sp, y + (hh - L(m, num)) / 2, dw + 2, num, Paint{weekend ? SUBTLE : INK}, ds);
    p.hit(cx, y, ws.cw, hh, HIT_DAY, day);
  }
  return hh;
}
// All-day events (and timed ones of a day or more) in rows under the heads, spanning their days, stacked where they
// share one. Three rows at most: when more are stacked, the third says per day how many more there are, and a tap on it
// opens that day, which lists them all (Apple's "+2").
inline int all_day_rows(Pen &p, int x, int y, const WeekShape &ws, const Data &d, const Words &wd) {
  const auto &m = p.m;
  const int ah = allday_h(m), most = 3;
  std::vector<std::array<bool, 7>> used;
  std::vector<std::array<int, 3>> placed;  // event, first day, end day (exclusive), with its lane in `lane_of`
  std::vector<int> lane_of;
  for (size_t i = 0; i < d.events.size(); ++i) {
    const auto &e = d.events[i];
    if (!banded(e)) continue;
    const int a = std::max(day_of(e.start), ws.d0), z = std::min(day_of(e.end - 1) + 1, ws.d0 + ws.days);
    if (a >= z) continue;
    int lane = 0;
    for (;; ++lane) {
      if (lane >= (int) used.size()) used.push_back({});
      bool free = true;
      for (int k = a; k < z; ++k) free = free && !used[lane][k - ws.d0];
      if (free) break;
    }
    for (int k = a; k < z; ++k) used[lane][k - ws.d0] = true;
    placed.push_back({(int) i, a, z});
    lane_of.push_back(lane);
  }
  const int lanes = (int) used.size(), shown = lanes > most ? most - 1 : lanes;
  std::array<int, 7> hidden{};
  for (size_t j = 0; j < placed.size(); ++j) {
    const auto &e = d.events[placed[j][0]];
    const int a = placed[j][1], z = placed[j][2], lane = lane_of[j];
    if (lane >= shown) { for (int k = a; k < z; ++k) ++hidden[k - ws.d0]; continue; }
    const int bx = x + ws.gw + (a - ws.d0) * ws.cw + P(2, 1), bw = (z - a) * ws.cw - P(4, 2);
    event_block(p, bx, y + lane * ah + P(2, 1), bw, ah - P(4, 2), e, false, P(6, 3));
    p.text(bx + P(8, 4), y + lane * ah + (ah - L(m, SMALL)) / 2, bw - P(16, 8), SMALL, cal(CAL_INK, e.cal), title_of(e, wd));
    p.hit(bx, y + lane * ah, bw, ah, HIT_EVENT, placed[j][0]);
  }
  if (shown < lanes)
    for (int k = 0; k < ws.days; ++k) {
      if (!hidden[k]) continue;
      const int cx = x + ws.gw + k * ws.cw, ty = y + shown * ah;
      p.text(cx + P(8, 4), ty + (ah - L(m, SMALL)) / 2, ws.cw - P(12, 6), SMALL, Paint{MUTED}, "+" + std::to_string(hidden[k]));
      p.hit(cx, ty, ws.cw, ah, HIT_DAY, ws.d0 + k);
    }
  return std::min(lanes, most) * ah;
}
// The hours and their events, from h0 to h1 at hour_h a row, from y. `x` is the left of the hour column.
inline void week_grid(Pen &p, int x, int y, const WeekShape &ws, const Data &d, Moment t, const Words &wd, bool tags, int tag_top, int tag_foot) {
  const auto &m = p.m;
  const int gridw = ws.cw * ws.days, gh = ws.hour_h * (ws.h1 - ws.h0), gx = x + ws.gw;
  for (int k = 0; k < ws.days; ++k) if (date_of(d, ws.d0 + k).weekday >= 5) p.box(gx + k * ws.cw, y, ws.cw, gh, Paint{SOFT});
  const bool now_shown = t.day >= ws.d0 && t.day < ws.d0 + ws.days && t.minute >= ws.h0 * 60 && t.minute < ws.h1 * 60;
  const int ny = y + (t.minute - ws.h0 * 60) * ws.hour_h / 60;
  for (int h = ws.h0; h <= ws.h1; ++h) {
    const int ly = y + (h - ws.h0) * ws.hour_h;
    p.box(gx, std::min(ly, y + gh - 1), gridw, 1, Paint{GRID});
    const bool near = now_shown && std::abs(ly - ny) < L(m, SMALL);
    if (near || h == ws.h1) continue;
    if (ws.bare) {
      // Only the number of the hour; on a 12-hour clock the 12-hour one (wd.clock writes 13:00 as "1 PM").
      const bool h12 = wd.clock && wd.clock(13 * 60).rfind("13", 0) != 0;
      if (h % 3 == 0) p.text(x, ly - L(m, SMALL) / 2, ws.gw - P(6, 3), SMALL, Paint{MUTED}, std::to_string(h12 && h % 12 ? h % 12 : h12 ? 12 : h), RIGHT);
      continue;
    }
    p.text(x, ly - L(m, SMALL) / 2, ws.gw - P(8, 4), SMALL, Paint{MUTED}, wd.clock(h * 60), RIGHT);
  }
  for (int k = 0; k <= ws.days; ++k) p.box(std::min(gx + k * ws.cw, gx + gridw - 1), y, 1, gh, Paint{GRID});
  const int T = t.at(), inset = P(3, 1);
  for (int k = 0; k < ws.days; ++k) {
    const int day = ws.d0 + k;
    for (auto &ln : lanes_of(d, day)) {
      const auto &e = d.events[ln.index];
      const int base = day * 1440;
      const int a = std::max(e.start - base, ws.h0 * 60), z = std::min(e.end - base, ws.h1 * 60);
      if (z <= a) continue;
      const int lw = (ws.cw - 2 * inset) / ln.lanes, bx = gx + k * ws.cw + inset + ln.lane * lw;
      const int by = y + (a - ws.h0 * 60) * ws.hour_h / 60 + 1, bh = std::max(P(14, 8), (z - a) * ws.hour_h / 60 - 2);
      const bool past = e.end <= T;
      event_block(p, bx, by, lw - P(2, 1), bh, e, past, P(6, 3));
      p.box(bx, by, P(4, 2), bh, cal(past ? CAL_KEY_PAST : CAL_KEY, e.cal), 0);
      p.hit(bx, by, lw, bh, HIT_EVENT, ln.index);
      if (ws.bare) continue;
      const int tx = bx + P(4, 2) + P(6, 3), tw = bx + lw - P(2, 1) - tx - P(4, 2);
      if (tw < P(16, 10) || bh < L(m, SMALL)) continue;
      const Paint ink = cal(past ? CAL_INK_PAST : CAL_INK, e.cal);
      // A short block (half an hour) still names itself: one line in the small face, in the middle of the block.
      const Face tf = bh - 2 * P(4, 1) >= L(m, title_face()) ? title_face() : SMALL;
      const int pad = tf == SMALL && bh - 2 * P(4, 1) < L(m, SMALL) ? (bh - L(m, SMALL)) / 2 : P(4, 1), room = bh - 2 * pad;
      const std::string title = title_of(e, wd);
      const int need = longest_word(m, tf, title) > tw ? 1 : lines_needed(m, tf, title, tw);
      const bool time_line = room >= need * L(m, tf) + L(m, SMALL) && e.end - e.start >= 45;
      const int lines = std::clamp(need, 1, std::max(1, (room - (time_line ? L(m, SMALL) : 0)) / L(m, tf)));
      const int used = p.para(tx, by + pad, tw, tf, ink, title, lines);
      if (time_line) p.text(tx, by + pad + used, tw, SMALL, ink, span(wd, e.start, e.end));
    }
  }
  // Hours out of the window are never lost in silence: a quiet tag at the top or foot of a day says how many.
  for (int k = 0; tags && k < ws.days; ++k) {
    int before = 0, after = 0;
    for (auto &e : d.events) if (!banded(e) && on_day(e, ws.d0 + k)) { if (end_in(e, ws.d0 + k) <= ws.h0 * 60) ++before; else if (start_in(e, ws.d0 + k) >= ws.h1 * 60) ++after; }
    for (int side = 0; side < 2; ++side) {
      const int n = side ? after : before;
      if (!n || (side ? tag_foot : tag_top) <= 0) continue;
      const std::string w = with(side ? wd.later : wd.earlier, std::to_string(n));
      const int tw = std::min(ws.cw - 2 * inset, m.width(SMALL, w) + P(14, 6)), th = L(m, SMALL) + P(2, 0);
      const int ty = side ? y + gh + (tag_foot - th) / 2 : y - tag_top + (tag_top - th) / 2;
      p.box(gx + k * ws.cw + (ws.cw - tw) / 2, ty, tw, th, Paint{TRACK}, th / 2);
      p.text(gx + k * ws.cw + (ws.cw - tw) / 2, ty + (th - L(m, SMALL)) / 2, tw, SMALL, Paint{MUTED}, w, CENTRE);
    }
  }
  // Now: a red line across the week, strong over today, with the time in a red tag in the hour column.
  if (now_shown) {
    p.box(gx, ny, gridw, 1, Paint{NOW}, 0, 90);
    const int tx = gx + (t.day - ws.d0) * ws.cw;
    p.box(tx, ny - 1, ws.cw, P(2, 2), Paint{NOW});
    const int dot = P(10, 6);
    p.box(std::max(gx, tx - dot / 2), ny - dot / 2 + 1, dot, dot, Paint{NOW}, dot / 2);
    if (!ws.bare) {
      const std::string nt = wd.clock(t.minute);
      const int tw = m.width(SMALL, nt) + P(10, 4), th = L(m, SMALL) + P(2, 0);
      p.box(x + std::max(0, ws.gw - P(6, 2) - tw), ny - th / 2, tw, th, Paint{NOW}, th / 2);
      p.text(x + std::max(0, ws.gw - P(6, 2) - tw), ny - th / 2 + (th - L(m, SMALL)) / 2, tw, SMALL, Paint{ON_NOW}, nt, CENTRE);
    }
  }
}
// The hours a week shows: the events' hours, eight to eight at least, in `rows` rows around now when not all fit.
inline void hours_of(WeekShape &ws, const Data &d, Moment t, int rows) {
  int h0 = 8, h1 = 20;
  for (int k = 0; k < ws.days; ++k)
    for (auto &e : d.events)
      if (!banded(e) && on_day(e, ws.d0 + k)) { h0 = std::min(h0, start_in(e, ws.d0 + k) / 60); h1 = std::max(h1, (end_in(e, ws.d0 + k) + 59) / 60); }
  h0 = std::max(0, h0); h1 = std::min(24, h1);
  if (rows > 0 && h1 - h0 > rows) { const int start = std::clamp(t.minute / 60 - rows / 3, h0, h1 - rows); h0 = start; h1 = start + rows; }
  ws.h0 = h0; ws.h1 = h1;
}
// A week on a card: heads, all-day rows and a window of hours (no scrolling on a page: AGENTS.md).
inline int week_start(const Data &d, Moment t, const Options &o) { return o.from_monday ? t.day - date_of(d, t.day).weekday : t.day; }
inline void week(Pen &p, int x, int y, int w, int h, const Data &d, Moment t, const Words &wd, bool bare = false, const Options &o = Options{}) {
  const auto &m = p.m;
  WeekShape ws;
  ws.bare = bare;
  ws.days = bare ? 7 : fit_days(m, w);
  // A week on a wall starts today: the days to come, not the ones gone since Monday (as Skylight's users keep it).
  ws.d0 = week_start(d, t, o);
  ws.gw = bare ? m.width(SMALL, "00") + P(10, 6) : gutter(m, &wd);
  ws.cw = (w - ws.gw) / ws.days;
  int yy = y + week_heads(p, x, y, ws, d, t, wd);
  if (!bare) yy += all_day_rows(p, x, yy, ws, d, wd);
  const int top_pad = L(m, SMALL) / 2, avail = y + h - yy - top_pad - P(4, 2);
  const int unit = bare ? P(14, 8) : hour_pref(m);
  WeekShape probe = ws;
  hours_of(probe, d, t, 0);
  if (o.hours_to > o.hours_from) { probe.h0 = o.hours_from; probe.h1 = o.hours_to; }
  const int range = probe.h1 - probe.h0, pref = std::max(1, avail / unit), least = std::max(1, avail / (bare ? P(14, 8) : hour_min(m)));
  const int rows = range <= pref ? range : std::max(pref, std::min({range, 8, least}));
  hours_of(ws, d, t, rows);
  if (o.hours_to > o.hours_from) {
    ws.h0 = o.hours_from; ws.h1 = o.hours_to;
    if (ws.h1 - ws.h0 > rows) { const int start = std::clamp(t.minute / 60 - rows / 3, ws.h0, ws.h1 - rows); ws.h0 = start; ws.h1 = start + rows; }
  }
  bool before = false, after = false;
  for (int k = 0; !bare && k < ws.days; ++k)
    for (auto &e : d.events)
      if (!banded(e) && on_day(e, ws.d0 + k)) { before |= end_in(e, ws.d0 + k) <= ws.h0 * 60; after |= start_in(e, ws.d0 + k) >= ws.h1 * 60; }
  const int strip = L(m, SMALL) + P(6, 3), tt = before ? strip : 0, tf = after ? strip : 0;
  ws.hour_h = std::max(1, (avail - tt - tf) / std::max(1, ws.h1 - ws.h0));
  week_grid(p, x, yy + top_pad + tt, ws, d, t, wd, !bare, tt, tf);
}

// ---- "Status and booking": a room's sign. The state in one word as large as the faces go, in green or red, until
// when, what is on or comes next; on a free room the keys that book it now (15 min, 30 min, 1 h, until the next
// meeting), as many as fit before the next. A wide card keeps the room's day beside it. Too low for the word and its
// line, it says both in one ("Free · Until 13:30") and leaves booking to the full screen.
inline void pill(Pen &p, int x, int y, int w, int h, Paint fill, Paint ink, Face f, const std::string &s) {
  p.box(x, y, w, h, fill, h / 2);
  p.text(x, y + (h - L(p.m, f)) / 2, w, f, ink, s, CENTRE);
}
inline int room_min(const Measure &m) { return P(18, 8) * 2 + L(m, SMALL) + L(m, LABEL); }
inline void room(Pen &p, int w, int h, const Data &d, Moment t, const Options &o, const Words &wd, const std::string &name) {
  const auto &m = p.m;
  const Status s = status(d, t, o);
  const bool busy = s.now >= 0;
  const uint8_t c = busy ? BUSY_COLOUR : FREE_COLOUR;
  const bool split = w >= ui::mm(120) && h >= ui::mm(50);
  const int sw = split ? w * 55 / 100 : w, mp = P(18, 8);
  p.box(0, 0, sw, h, cal(CAL_BLOCK, c), module_radius());
  const Paint ink = cal(CAL_INK, c);
  const int x = mp, W = sw - 2 * mp, bottom = h - mp;
  p.text(x, mp, W * 2 / 3, SMALL, ink, name);
  p.text(x + W * 2 / 3, mp, W / 3, SMALL, ink, wd.clock(t.minute), RIGHT);
  const int top = mp + L(m, SMALL) + P(4, 2);
  const Event *e = busy ? &d.events[s.now] : s.next >= 0 ? &d.events[s.next] : nullptr;
  const bool next_today = e && day_of(e->start) == t.day;
  // The foot: on a busy room the bar of the meeting; on a free one the keys that fit before the next meeting.
  const int key_h = std::max(ui::touch_min(), L(m, CONTROL) + P(18, 8)), bar_h = P(8, 5);
  struct Key { std::string word; int end; };
  std::vector<Key> keys;
  if (!busy && o.book) {
    const int T = t.at(), free_until = next_today ? e->start : (t.day + 1) * 1440;
    for (int minutes : {15, 30, 60})
      if (T + minutes <= free_until) keys.push_back({dur(wd, minutes), T + minutes});
    if (next_today && free_until - T < 120 && free_until - T > 15) keys.push_back({with(wd.until, wd.clock(free_until % 1440)), free_until});
    if (keys.size() > 3) keys.erase(keys.begin() + 2);
  }
  if (!keys.empty() && bottom - key_h - P(14, 6) - top < L(m, LABEL)) keys.clear();
  const int foot = busy ? bar_h : keys.empty() ? 0 : key_h;
  const Face big = L(m, VALUE) ? VALUE : HEADLINE, sub = large() ? HEADLINE : LABEL, mf = meta_face();
  const std::string state = busy ? wd.busy : wd.free;
  const std::string until = busy ? with(wd.until, at_time(wd, d, e->end, t.day, true)) : next_today ? with(wd.until, wd.clock(e->start % 1440)) : "";
  const std::string what = busy ? title_of(*e, wd) : "";
  const Event *after = busy ? (s.next >= 0 && day_of(d.events[s.next].start) == t.day ? &d.events[s.next] : nullptr) : next_today ? e : nullptr;
  const std::string next = after ? with(wd.next, wd.clock(after->start % 1440)) + " · " + title_of(*after, wd) : "";
  const int room_h = bottom - foot - (foot ? P(14, 6) : 0) - top;
  int need = L(m, big) + (until.empty() ? 0 : L(m, sub));
  const bool show_what = !what.empty() && need + P(8, 3) + L(m, title_face()) <= room_h;
  if (show_what) need += P(8, 3) + L(m, title_face());
  const bool show_next = !next.empty() && need + P(10, 4) + L(m, mf) <= room_h;
  if (show_next) need += P(10, 4) + L(m, mf);
  if (need > room_h) {
    p.text(x, top + std::max(0, (room_h - L(m, LABEL)) / 2), W, LABEL, ink, until.empty() ? state : state + " · " + until);
  } else {
    int y = top + (room_h - need) / 2;
    p.text(x, y, W, big, ink, state); y += L(m, big);
    if (!until.empty()) { p.text(x, y, W, sub, ink, until); y += L(m, sub); }
    if (show_what) { y += P(8, 3); p.text(x, y, W, title_face(), ink, what); y += L(m, title_face()); }
    if (show_next) { y += P(10, 4); p.text(x, y, W, mf, ink, next); }
  }
  if (busy) {
    const int by = bottom - bar_h, done = std::clamp(1000 * (t.at() - e->start) / std::max(1, e->end - e->start), 0, 1000);
    p.box(x, by, W, bar_h, cal(CAL_TRACK, c), bar_h / 2);
    p.box(x, by, std::max(bar_h, W * done / 1000), bar_h, cal(CAL_KEY, c), bar_h / 2);
    p.hit(0, 0, sw, h, HIT_EVENT, s.now);
  } else if (!keys.empty()) {
    const int gap = P(10, 5);
    int n = (int) keys.size(), kw = (W - (n - 1) * gap) / n;
    for (auto &k : keys) if (m.width(CONTROL, k.word) + P(16, 8) > kw && n > 2) { n = 2; kw = (W - gap) / 2; }
    for (int i = 0; i < n; ++i) {
      const int kx = x + i * (kw + gap), ky = bottom - key_h;
      // A booking on its way: its key says so, the others rest, until the events come back with it.
      const bool going = o.booking == keys[i].end;
      pill(p, kx, ky, kw, key_h, Paint{CARD}, going ? Paint{MUTED} : ink, CONTROL, going && !wd.booking.empty() ? wd.booking : keys[i].word);
      if (o.booking < 0) p.hit(kx - gap / 2, ky - P(8, 4), kw + gap, key_h + P(16, 8), HIT_BOOK, keys[i].end);
    }
  }
  if (!split) return;
  // The room's day beside it: every meeting of today, the past ones pale.
  const int lx = sw + P(18, 8), lw = w - lx;
  const Face hf = large() ? HEADLINE : LABEL;
  p.text(lx, mp, lw, hf, Paint{INK}, wd.today);
  int yy = mp + L(m, hf) + P(12, 6), shown = 0, today = 0;
  for (auto &ev : d.events) today += day_of(ev.start) == t.day;
  for (size_t i = 0; i < d.events.size(); ++i) {
    const auto &ev = d.events[i];
    if (day_of(ev.start) != t.day) continue;
    if (yy + event_row(m) + (shown + 1 < today ? L(m, mf) + P(14, 6) : 0) > h) {
      p.text(lx, yy, lw, mf, Paint{MUTED}, with(wd.more, std::to_string(today - shown)));
      break;
    }
    event_line(p, lx, yy, lw, d, ev, (int) i, wd, ev.end <= t.at());
    yy += event_row(m) + P(14, 6);
    ++shown;
  }
  if (!today) p.text(lx, yy, lw, mf, Paint{MUTED}, wd.nothing);
}

// ---- The card on a page: it picks the richest view its room allows.
enum View : uint8_t { NOW_VIEW, UP_NEXT, AGENDA, COLUMNS, WEEK, DAY, BLOCKS, MONTH };
// A day's column holds a title of about fifteen characters, and is never less than a hand wide.
inline int column_min(const Measure &m) { return std::max(ui::mm(30), m.width(title_face(), std::string(15, 'n')) + 2 * module_pad() + P(16, 10)); }
inline View tile_view(const Measure &m, int w, int h) {
  const int hh = head_height(m), gap = P(12, 6);
  const bool wide = w * 10 >= h * 16;
  if (h - hh - gap > 0 && week_fits(m, w, h - hh - gap)) return WEEK;
  const int ncol = std::min(4, (w + gap) / (column_min(m) + gap));
  if (wide && ncol >= 3 && h - hh - gap >= up_next_min(m) + 2 * module_pad() + L(m, SMALL) + 2 * event_row(m)) return COLUMNS;
  const int list_two = 2 * module_pad() + 2 * event_row(m) + row_gap();
  const bool side = wide && (w - gap) / 2 >= ui::mm(45) && h - hh - gap >= std::max(up_next_min(m) + P(20, 10), list_two);
  if (side || h - hh - gap >= up_next_min(m) + gap + list_two) return AGENDA;
  if (h - hh - gap >= up_next_min(m)) return UP_NEXT;
  return NOW_VIEW;
}
// The card's own edge around the content the plan draws in: its padding on each side and its corner radius.
struct Edge { int left = 0, top = 0, right = 0, bottom = 0, radius = 0; };
inline View plan_tile(Scene &sc, const Measure &m, int w, int h, const Data &d, Moment t, const Options &o, const Words &wd, const std::string &name, const Edge &edge = Edge{}) {
  sc.clear();
  Pen p{sc, m};
  const View v = tile_view(m, w, h);
  const HeadWords hw = head_words(d, t, o, wd, name);
  const int hh = head_height(m), gap = P(12, 6);
  const Status s = status(d, t, o);
  // "Free or busy": the head says it on every size (Free, Starts soon, Busy, and until when); else the name and the day.
  const std::string head_first = o.busy_free ? hw.first : name;
  const std::string day_line = o.busy_free ? hw.second : long_day(wd, d, t.day);
  const int shown = s.now >= 0 ? -1 : s.next;
  // A room's sign on every card with room for its word; a single cell keeps the head (Free, Busy, until when).
  if (o.room && v != NOW_VIEW && h >= room_min(m)) { room(p, w, h, d, t, o, wd, name); return v; }
  switch (v) {
    case WEEK: {
      head(p, 0, 0, w, hh, hw.on, head_first, o.busy_free ? day_line : hw.on ? hw.first + " · " + hw.second : day_line);
      week(p, 0, hh + gap, w, h - hh - gap, d, t, wd, false, o);
      break;
    }
    case COLUMNS: {
      head(p, 0, 0, w, hh, hw.on, head_first, day_line);
      columns(p, 0, hh + gap, w, h - hh - gap, d, t, o, wd, std::min(4, (w + gap) / (column_min(m) + gap)));
      break;
    }
    case AGENDA: {
      head(p, 0, 0, w, hh, hw.on, head_first, day_line);
      const int y = hh + gap, H = h - y;
      const bool wide = w * 10 >= h * 16 && (w - gap) / 2 >= ui::mm(45);
      if (wide) { const int lw = (w - gap) / 2; up_next(p, 0, y, lw, H, d, t, o, wd); list(p, lw + gap, y, w - lw - gap, H, d, t, s, wd, large() ? 4 : 3, shown); }
      else {
        const int list_two = 2 * module_pad() + 2 * event_row(m) + row_gap();
        const int uh = std::max(up_next_min(m), std::min(H - gap - list_two, up_next_min(m) + L(m, large() ? VALUE : HEADLINE)));
        up_next(p, 0, y, w, uh, d, t, o, wd);
        list(p, 0, y + uh + gap, w, H - uh - gap, d, t, s, wd, large() ? 4 : 3, shown);
      }
      break;
    }
    case UP_NEXT: {
      head(p, 0, 0, w, hh, hw.on, head_first, day_line);
      up_next(p, 0, hh + gap, w, h - hh - gap, d, t, o, wd);
      break;
    }
    default: {
      // Now: the head alone, with a thin bar of how far the event has come when a little room is left.
      const int bar = P(6, 4), room = hh + P(14, 6) + bar;
      if (s.now >= 0 && h >= room) {
        const int y0 = (h - room) / 2;
        head(p, 0, y0, w, hh, hw.on, hw.first, hw.second, hw.brief);
        const auto &e = d.events[s.now];
        const int done = std::clamp(1000 * (t.at() - e.start) / std::max(1, e.end - e.start), 0, 1000), by = y0 + hh + P(14, 6);
        p.box(0, by, w, bar, Paint{TRACK}, bar / 2);
        p.box(0, by, std::max(bar, w * done / 1000), bar, cal(CAL_KEY, e.cal), bar / 2);
      } else {
        head(p, 0, 0, w, h, hw.on, hw.first, hw.second, hw.brief);
        if (s.now >= 0 && edge.radius > 0) {
          // No room for the bar inside: the card's own bottom edge fills as the event goes, a strip of the card's shape
          // (its rounded corners too), in the event's colour.
          const auto &e = d.events[s.now];
          const int done = std::clamp(1000 * (t.at() - e.start) / std::max(1, e.end - e.start), 0, 1000);
          const int X = -edge.left, Y = -edge.top, W = w + edge.left + edge.right, H = h + edge.top + edge.bottom, strip = P(4, 3);
          Box b;
          b.x = X; b.y = Y; b.w = W; b.h = H; b.radius = edge.radius; b.paint = cal(CAL_KEY, e.cal);
          b.cx = X; b.cy = Y + H - strip; b.cw = std::max(1, W * done / 1000); b.ch = strip;
          sc.boxes.push_back(b);
        }
      }
      break;
    }
  }
  return v;
}

// ---- The full screen.
struct Full {
  Scene fixed;   // the header, the day heads, the all-day rows: they stay while the hours scroll
  Scene scroll;  // the hours (week, a tall day), drawn in a scrolling box
  int sx = 0, sy = 0, sw = 0, sh = 0;  // the scrolling box; sh 0 when there is none
  int scroll_to = 0;                   // where it opens: an hour before now
  Scene overlay;  // the view key's choice or an event's sheet
  View view = DAY;
  bool month_list = false;  // the month keeps the chosen day's events with it (a tap on a day stays in the month)
};
struct State {
  View view = UP_NEXT;  // the view on show
  bool chosen = false;  // the view key was used: the full screen keeps that view while it stays open
  int day = 0;          // the day the day view (and the month's list) shows, from today
  int week = 0;         // steps forward or back in the week view, each as many days as the glass shows
  int month = 0;        // months forward or back
  bool menu = false;    // the view key's choice is open
  int sheet = -1;       // the event whose sheet is open
  Detail detail;        // the rest of it, once the app answered
  uint8_t hidden = 0;   // calendars hidden on the glass from the view choice (bit n: calendar n), until it closes
};
// The views a glass takes: the week where it holds three days and six hours, else the day; the month on any glass.
inline View first_view(const Measure &m, int w, int h, const Options &o) {
  if (o.start_view == "up_next") return UP_NEXT;
  if (o.start_view == "day") return DAY;
  if (o.start_view == "month") return MONTH;
  const bool week_ok = week_fits(m, w, h, false);
  if (o.start_view == "week") return week_ok ? WEEK : BLOCKS;
  return week_ok ? WEEK : DAY;
}
inline int key_size(const Measure &m) { return std::max(ui::touch_min(), L(m, ICON) + P(14, 6)); }
struct HeaderPlace { int view_x = 0, view_w = 0, bottom = 0; };
// The header: close, the name with the week or day under it, the view key, Today, back and forward. Narrow glass keeps
// close, the view key and Today; back and forward are a swipe there.
inline HeaderPlace header(Pen &p, int width, int margin, const std::string &name, const std::string &second, const std::string &view_word, const Words &wd, const std::string &period = "") {
  const auto &m = p.m;
  const int d = key_size(m), y = margin;
  auto round_key = [&](int x, const char *g, HitKind k) {
    p.box(x, y, d, d, Paint{KEY}, d / 2);
    p.sc.texts.push_back({x, y + (d - L(m, ICON)) / 2, d, ICON, Paint{INK}, CENTRE, g});
    p.hit(x - P(4, 2), y - P(4, 2), d + P(8, 4), d + P(8, 4), k);
  };
  round_key(margin, GLYPH_CLOSE, HIT_CLOSE);
  const Face kf = SMALL, tf = large() ? HEADLINE : CONTROL;
  const int word_w = m.width(kf, wd.today_key) + P(28, 14), gw = L(m, ICON), vw = m.width(kf, view_word) + gw + P(30, 14), g = P(16, 8);
  const int tx = margin + d + P(14, 8);
  const bool arrows = width - 2 * margin >= d + g + vw + g + 2 * d + word_w + 2 * g;
  auto view_x = [&](int today_w) { return width - margin - (arrows ? 2 * (d + P(8, 4)) : 0) - today_w - g - vw; };
  // Today in words where the name fits beside the keys; on narrow glass Today is a round key with the calendar icon, so
  // the name and the period under it keep their room (Max's choice of five, 11 October).
  const bool icon = m.width(tf, name) > view_x(word_w) - P(14, 8) - tx;
  const int today_w = icon ? d : word_w;
  int rx = width - margin;
  if (arrows) { rx -= d; round_key(rx, GLYPH_RIGHT, HIT_NEXT); rx -= P(8, 4); }
  rx -= today_w;
  if (icon) round_key(rx, GLYPH_CALENDAR, HIT_TODAY);
  else {
    p.box(rx, y, today_w, d, Paint{KEY}, d / 2);
    p.text(rx, y + (d - L(m, kf)) / 2, today_w, kf, Paint{INK}, wd.today_key, CENTRE);
    p.hit(rx, y - P(4, 2), today_w, d + P(8, 4), HIT_TODAY);
  }
  if (arrows) round_key(rx - P(8, 4) - d, GLYPH_LEFT, HIT_PREV);
  const int vx = view_x(today_w);
  p.box(vx, y, vw, d, Paint{KEY}, d / 2);
  p.text(vx + P(16, 8), y + (d - L(m, kf)) / 2, vw - gw - P(16, 8), kf, Paint{INK}, view_word);
  p.sc.texts.push_back({vx + vw - gw - P(10, 4), y + (d - L(m, ICON)) / 2, gw, ICON, Paint{INK}, CENTRE, GLYPH_MENU});
  p.hit(vx, y - P(4, 2), vw, d + P(8, 4), HIT_VIEW_KEY);
  const int tw = vx - P(14, 8) - tx, th = L(m, tf) + L(m, SMALL);
  p.text(tx, y + (d - th) / 2, tw, tf, Paint{INK}, name);
  // Narrow glass names the period short ("14 – 20 Oct"); wide glass has room for the long form.
  const bool short_line = !period.empty() && (icon || m.width(SMALL, second) > tw);
  p.text(tx, y + (d - th) / 2 + L(m, tf), tw, SMALL, Paint{MUTED}, short_line ? period : second);
  return {vx, vw, y + d};
}
// The day: a strip of the week's days with a dot per calendar busy that day; under it the chosen day, as blocks in
// their colours (the Watch's list), earlier events of today folded into one line, or on tall glass as a timeline.
inline int strip_height(const Measure &m) { return L(m, SMALL) + L(m, num_face()) + P(6, 3) + P(8, 4) + P(10, 4); }
inline void day_strip(Pen &p, int x, int y, int w, const Data &d, Moment t, const Words &wd, int sel, int d0) {
  const auto &m = p.m;
  const Face num = num_face();
  const int cw = w / 7, dot = P(8, 4), sh = strip_height(m);
  for (int k = 0; k < 7; ++k) {
    const int day = d0 + k, cx = x + k * cw;
    const Date dt = date_of(d, day);
    const bool weekend = dt.weekday >= 5;
    if (day == sel) p.box(cx + P(2, 1), y, cw - P(4, 2), sh, Paint{TRACK}, P(12, 6));
    p.hit(cx, y, cw, sh, HIT_DAY, day);
    p.text(cx, y + P(4, 2), cw, SMALL, Paint{weekend ? SUBTLE : MUTED}, wd.days[dt.weekday], CENTRE);
    const int ny = y + P(4, 2) + L(m, SMALL);
    const std::string ds = std::to_string(dt.day);
    if (day == t.day) {
      const int c = L(m, num) + P(2, 0), cwid = std::max(c, m.width(num, ds) + P(10, 6));
      p.box(cx + (cw - cwid) / 2, ny, cwid, c, Paint{NOW}, c / 2);
      p.text(cx + (cw - cwid) / 2, ny + (c - L(m, num)) / 2, cwid, num, Paint{ON_NOW}, ds, CENTRE);
    } else p.text(cx, ny, cw, num, Paint{weekend ? SUBTLE : INK}, ds, CENTRE);
    std::vector<uint8_t> cals;
    for (auto &e : d.events) if (on_day(e, day) && std::find(cals.begin(), cals.end(), e.cal) == cals.end()) cals.push_back(e.cal);
    if (cals.size() > 4) cals.resize(4);
    const int n = (int) cals.size(), dw = n * dot + std::max(0, n - 1) * P(4, 2), dx = cx + (cw - dw) / 2, dy = ny + L(m, num) + P(6, 3);
    for (int k2 = 0; k2 < n; ++k2) p.box(dx + k2 * (dot + P(4, 2)), dy, dot, dot, cal(CAL_KEY, cals[k2]), dot / 2);
  }
}
inline void day_list(Pen &p, int x, int y, int w, int h, const Data &d, Moment t, const Status &s, const Words &wd, int sel) {
  const auto &m = p.m;
  const int T = t.at(), mp = P(10, 5), bottom = y + h;
  const Face mf = meta_face(), tf = title_face();
  std::vector<int> day;
  int earlier = 0;
  for (size_t i = 0; i < d.events.size(); ++i) {
    const auto &e = d.events[i];
    if (!on_day(e, sel)) continue;
    if (sel == t.day && !all_day(e) && e.end <= T) { ++earlier; continue; }
    day.push_back((int) i);
  }
  std::stable_sort(day.begin(), day.end(), [&](int a, int b) {
    const auto &x1 = d.events[a], &y1 = d.events[b];
    if (all_day(x1) != all_day(y1)) return all_day(x1);
    return x1.start < y1.start;
  });
  int yy = y;
  if (earlier) { p.text(x + P(4, 2), yy, w, mf, Paint{MUTED}, with(wd.earlier, std::to_string(earlier))); yy += L(m, mf) + P(8, 4); }
  if (day.empty()) { p.text(x + P(4, 2), yy, w, mf, Paint{MUTED}, wd.nothing); return; }
  const int bh = L(m, tf) + P(2, 1) + L(m, mf) + 2 * mp, ah = L(m, tf) + 2 * P(6, 3);
  for (size_t k = 0; k < day.size(); ++k) {
    const auto &e = d.events[day[k]];
    const int h1 = all_day(e) ? ah : bh, left = (int) day.size() - (int) k - 1;
    if (yy + h1 > bottom || (left > 0 && yy + h1 + P(8, 4) + L(m, mf) > bottom)) {
      p.text(x + P(4, 2), std::min(yy, bottom - L(m, mf)), w, mf, Paint{MUTED}, with(wd.more, std::to_string((int) day.size() - (int) k)));
      break;
    }
    const bool running = day[k] == s.now, past = sel == t.day && !all_day(e) && e.end <= T;
    event_block(p, x, yy, w, h1, e, past, P(12, 6));
    const int bar = P(4, 3);
    p.box(x + mp, yy + mp / 2 + P(2, 1), bar, h1 - mp - P(4, 2), cal(CAL_KEY, e.cal), bar / 2);
    p.hit(x, yy, w, h1, HIT_EVENT, day[k]);
    const int tx = x + mp + bar + P(10, 6), W = x + w - mp - tx;
    const Paint ink = cal(past ? CAL_INK_PAST : CAL_INK, e.cal);
    if (all_day(e)) { p.text(tx, yy + (h1 - L(m, tf)) / 2, W, tf, ink, title_of(e, wd)); yy += h1 + P(8, 4); continue; }
    p.text(tx, yy + mp, W, tf, ink, title_of(e, wd));
    const std::string right = running ? left_of(wd, d, e, t) : "";
    const int rw = right.empty() ? 0 : m.width(mf, right) + 2;
    const std::string meta = span_of(wd, d, e) + (e.place.empty() ? "" : " · " + e.place);
    p.text(tx, yy + mp + L(m, tf) + P(2, 1), W - rw - (rw ? P(8, 4) : 0), mf, ink, meta);
    if (rw) p.text(tx + W - rw, yy + mp + L(m, tf) + P(2, 1), rw, mf, ink, right, RIGHT);
    yy += h1 + P(8, 4);
  }
}
// The month (a glance, after Fantastical's and Apple's): six weeks, a dot per calendar with something that day, or on
// large cells the first titles; today in red, the chosen day on a grey pad. Wide glass keeps the chosen day's events
// beside it.
// Returns whether the chosen day's events stand with the month (beside it, or under it on square and tall glass): a tap
// on a day then only changes that list; else it opens the day.
// The ISO 8601 number of the week a day lies in (its Thursday's year counts).
inline int iso_week(const Data &d, int day) {
  const int thursday = day - date_of(d, day).weekday + 3;
  const Date th = date_of(d, thursday);
  int yday = th.day - 1;
  for (int mo = 1; mo < th.month; ++mo) yday += days_in(th.year, mo);
  return yday / 7 + 1;
}
inline bool month(Pen &p, int x, int y, int w, int h, const Data &d, Moment t, const Words &wd, int sel, int months_ahead, bool numbers = false) {
  const auto &m = p.m;
  const bool side = w >= ui::mm(150) && w * 10 >= h * 14;
  // Square and tall glass (the 4-inch Guition, standing screens): the month on top, the chosen day's events under it,
  // as the iPhone's Calendar keeps them; the month then takes the control face for its numbers and shows dots.
  const Face hf = large() ? HEADLINE : CONTROL;
  const int list_min = L(m, hf) + P(10, 5) + 2 * event_row(m) + P(20, 10);
  const bool below = !side && h * 10 >= w * 8 && h * 42 / 100 >= list_min;
  const Face num = below ? CONTROL : num_face();
  // The grid: the Monday on or before the first of the month on show.
  int offset_first = t.day - (date_of(d, t.day).day - 1);
  for (int k = 0; k < months_ahead; ++k) { const Date f = date_of(d, offset_first); offset_first += days_in(f.year, f.month); }
  for (int k = 0; k > months_ahead; --k) { const Date prev = date_of(d, offset_first - 1); offset_first -= days_in(prev.year, prev.month); }
  const Date mfirst = date_of(d, offset_first);
  const int g0 = offset_first - mfirst.weekday;
  const int rows = (mfirst.weekday + days_in(mfirst.year, mfirst.month) + 6) / 7;
  // A day with dots: the number (today's in its circle), a gap and a row of dots, in the middle of its cell with room
  // round them, so they stay on the chosen day's pad and off the lines. Under the month the list gives up height for it.
  const int dot = P(8, 4), circle = L(m, num) + P(2, 0), dot_gap = P(4, 2), dots_h = circle + dot_gap + dot;
  const int head = L(m, SMALL) + P(8, 4);
  // The list under it keeps room for its heading, one event and its "N more" (a tap on the day opens all of them).
  const int list_least = L(m, hf) + P(10, 5) + event_row(m) + L(m, meta_face()) + P(12, 6);
  const int gh = below ? std::min(std::max(h * 56 / 100, head + rows * (dots_h + 2 * P(10, 5))), h - list_least) : h;
  const int mw = side ? w * 58 / 100 : w, gap = P(16, 8);
  // Week numbers: a narrow quiet column at the left of the weeks.
  const int nw = numbers ? m.width(SMALL, "00") + P(14, 6) : 0;
  const int ox = x + nw;
  const int cw = (mw - nw) / 7, ch = (gh - head) / rows;
  for (int k = 0; k < 7; ++k) p.text(ox + k * cw, y, cw, SMALL, Paint{k >= 5 ? SUBTLE : MUTED}, wd.days[k], CENTRE);
  const bool titles = ch >= L(m, num) + P(10, 6) + 2 * (L(m, SMALL) + P(4, 2));
  auto num_y = [&](int cy) { return titles ? cy + (below ? P(3, 2) : P(6, 3)) : cy + std::max(0, (ch - dots_h) / 2); };
  for (int r = 0; numbers && r < rows; ++r)
    p.text(x, num_y(y + head + r * ch + 1) + (circle - L(m, SMALL)) / 2, nw - P(6, 3), SMALL, Paint{SUBTLE}, std::to_string(iso_week(d, g0 + 7 * r)), RIGHT);
  for (int r = 0; r <= rows; ++r) p.box(ox, std::min(y + head + r * ch, y + gh - 1), cw * 7, 1, Paint{GRID});
  for (int i = 0; i < rows * 7; ++i) {
    const int day = g0 + i, cx = ox + (i % 7) * cw, cy = y + head + (i / 7) * ch + 1;
    const Date dt = date_of(d, day);
    const bool in = dt.month == mfirst.month, weekend = (i % 7) >= 5;
    if (day == sel) p.box(cx + P(3, 1), cy + P(3, 1), cw - P(6, 2), ch - P(6, 3), Paint{TRACK}, P(10, 5));
    p.hit(cx, cy, cw, ch, HIT_DAY, day);
    const std::string ds = std::to_string(dt.day);
    const int ny = num_y(cy);
    if (day == t.day) {
      const int c = L(m, num) + P(2, 0), cwid = std::max(c, m.width(num, ds) + P(10, 6));
      p.box(cx + (cw - cwid) / 2, ny, cwid, c, Paint{NOW}, c / 2);
      p.text(cx + (cw - cwid) / 2, ny + (c - L(m, num)) / 2, cwid, num, Paint{ON_NOW}, ds, CENTRE);
    } else p.text(cx, ny, cw, num, Paint{!in || weekend ? SUBTLE : INK}, ds, CENTRE);
    const int top = titles ? ny + L(m, num) + (below ? P(2, 1) : P(6, 3)) : ny + circle + dot_gap;
    std::vector<int> evs;
    for (size_t k = 0; k < d.events.size(); ++k) if (on_day(d.events[k], day)) evs.push_back((int) k);
    if (titles && day >= d.from && day <= d.to) {
      const int lh = L(m, SMALL) + P(4, 2), fit_n = std::max(0, (cy + ch - P(4, 2) - top) / lh);
      for (int k = 0; k < (int) evs.size() && k < fit_n; ++k) {
        if (k == fit_n - 1 && (int) evs.size() > fit_n) { p.text(cx + P(6, 3), top + k * lh, cw - P(12, 6), SMALL, Paint{MUTED}, "+" + std::to_string((int) evs.size() - k)); break; }
        const auto &e = d.events[evs[k]];
        p.box(cx + P(4, 2), top + k * lh, cw - P(8, 4), lh - P(2, 1), cal(in ? CAL_BLOCK : CAL_BLOCK_PAST, e.cal), P(4, 2));
        p.text(cx + P(10, 5), top + k * lh + (lh - P(2, 1) - L(m, SMALL)) / 2, cw - P(20, 10), SMALL, cal(in ? CAL_INK : CAL_INK_PAST, e.cal), title_of(e, wd));
      }
    } else {
      // Beyond the events the screen holds: the glance's own masks, one bit per calendar.
      uint8_t mask = 0;
      if (day >= d.from && day <= d.to) for (int k : evs) mask |= uint8_t(1u << std::min<int>(d.events[k].cal, 7));
      else if (day - d.glance_from >= 0 && day - d.glance_from < (int) d.glance.size()) mask = d.glance[day - d.glance_from];
      std::vector<uint8_t> cals;
      for (uint8_t c = 0; c < 8; ++c) if (mask & (1u << c)) cals.push_back(c);
      if (cals.size() > 4) cals.resize(4);
      const int n = (int) cals.size(), dw = n * dot + std::max(0, n - 1) * P(4, 2), dx = cx + (cw - dw) / 2;
      for (int k = 0; k < n && top + dot <= cy + ch - 1; ++k) p.box(dx + k * (dot + P(4, 2)), top, dot, dot, cal(in ? CAL_KEY : CAL_KEY_PAST, cals[k]), dot / 2);
    }
  }
  if (side) {
    const int lx = x + mw + gap, lw = w - mw - gap;
    p.text(lx, y, lw, hf, Paint{INK}, long_day(wd, d, sel));
    day_list(p, lx, y + L(m, hf) + P(10, 5), lw, h - L(m, hf) - P(10, 5), d, t, Status{}, wd, sel);
  } else if (below) {
    // Compact rows under the month: the bar, the title and the time, as the agenda draws them.
    const int ly = y + gh + P(12, 6), bottom = y + h;
    p.text(x, ly, w, hf, Paint{INK}, long_day(wd, d, sel));
    std::vector<int> day;
    for (size_t k = 0; k < d.events.size(); ++k) if (on_day(d.events[k], sel)) day.push_back((int) k);
    std::stable_sort(day.begin(), day.end(), [&](int a, int b) {
      const auto &e1 = d.events[a], &e2 = d.events[b];
      if (all_day(e1) != all_day(e2)) return all_day(e1);
      return e1.start < e2.start;
    });
    int yy = ly + L(m, hf) + P(10, 5);
    const Face mf = meta_face();
    if (day.empty()) p.text(x, yy, w, mf, Paint{MUTED}, wd.nothing);
    for (size_t k = 0; k < day.size(); ++k) {
      const auto &e = d.events[day[k]];
      const int rh = row_of(m, e), left = (int) day.size() - (int) k - 1;
      if (yy + rh > bottom || (left > 0 && yy + rh + P(8, 4) + L(m, mf) > bottom)) {
        p.text(x, std::min(yy, bottom - L(m, mf)), w, mf, Paint{MUTED}, with(wd.more, std::to_string((int) day.size() - (int) k)));
        break;
      }
      event_line(p, x, yy, w, d, e, day[k], wd, sel == t.day && !all_day(e) && e.end <= t.at());
      yy += rh + P(10, 4);
    }
  }
  return side || below;
}
// A tapped event: a sheet over the view with everything Home Assistant knows of it.
inline void sheet(Pen &p, int width, int height, int margin, const Data &d, Moment t, const Words &wd, int index, const Detail &more = Detail{}) {
  const auto &m = p.m;
  if (index < 0 || index >= (int) d.events.size()) return;
  // The app's answer takes the place of the short title and place, and brings this event's own notes.
  Event e = d.events[index];
  const bool answered = more.of(e);
  if (answered && !(e.flags & PRIVATE)) { if (!more.title.empty()) e.title = more.title; e.place = more.place; }
  p.box(0, 0, width, height, Paint{SCRIM}, 0, 128);
  p.hit(0, 0, width, height, HIT_SCRIM);
  const int w = std::min(width - 2 * margin, ui::mm(95)), pad = P(20, 10);
  const Face tf = large() ? HEADLINE : CONTROL, mf = meta_face();
  // An event's own notes (the app's answer) take a few lines more than the short notes of the event of the moment.
  const int k = key_size(m), most_notes = answered ? (large() ? 6 : 4) : (large() ? 3 : 2), iw = L(m, ICON) + P(10, 4);
  const Status s = status(d, t, Options{});
  const std::string &note = answered ? more.notes : d.notes;
  const bool has_note = !note.empty() && (answered || index == (s.now >= 0 ? s.now : s.next));
  // The title on up to two lines (the whole of it is why the sheet was opened), the notes on the lines they take: the
  // sheet is as tall as what it holds.
  const int W0 = w - 2 * pad, tw = W0 - m.circle - P(10, 12) - k - P(10, 4);
  const std::string title = title_of(e, wd);
  const int title_lines = std::max(1, (int) wrap(m, LABEL, title, tw, 2).size());
  const int lines_note = has_note ? std::max(1, std::min(most_notes, (int) wrap(m, mf, note, W0 - iw, most_notes).size())) : 0;
  const int th = title_lines * L(m, LABEL) + head_gap() + L(m, SMALL), hh = std::max({k, m.circle, th});
  const int H = 2 * pad + hh + P(16, 6) + L(m, tf) + L(m, mf) + P(12, 4) + (e.place.empty() ? 0 : L(m, mf) + P(12, 4)) + lines_note * L(m, mf);
  const int h = std::min(H, height - 2 * margin), x = (width - w) / 2, y = std::max(margin, (height - h) / 2);
  p.framed(x, y, w, h, Paint{RAISED}, Paint{RAISED_LINE}, P(22, 14));
  p.hit(x, y, w, h, HIT_SHEET);
  int yy = y + pad;
  const int W = w - 2 * pad;
  const int circle = std::min(m.circle, hh);
  p.box(x + pad, yy + (hh - circle) / 2, circle, circle, cal(CAL_BLOCK, e.cal), circle / 2);
  const Face g = circle >= P(40, 28) ? TILE_ICON : ICON;
  p.sc.texts.push_back({x + pad, yy + (hh - L(m, g)) / 2, circle, g, cal(CAL_KEY, e.cal), CENTRE, GLYPH_CALENDAR});
  const int tx = x + pad + circle + P(10, 12);
  p.para(tx, yy + (hh - th) / 2, tw, LABEL, Paint{INK}, title, title_lines);
  p.text(tx, yy + (hh - th) / 2 + title_lines * L(m, LABEL) + head_gap(), tw, SMALL, Paint{MUTED}, e.cal < d.names.size() ? d.names[e.cal] : "");
  const int kx = x + pad + W - k;
  p.box(kx, yy + (hh - k) / 2, k, k, Paint{KEY}, k / 2);
  p.sc.texts.push_back({kx, yy + (hh - k) / 2 + (k - L(m, ICON)) / 2, k, ICON, Paint{INK}, CENTRE, GLYPH_CLOSE});
  p.hit(kx - P(4, 2), yy + (hh - k) / 2 - P(4, 2), k + P(8, 4), k + P(8, 4), HIT_CLOSE);
  yy += hh + P(16, 6);
  const int day = day_of(e.start);
  p.sc.texts.push_back({x + pad, yy + (L(m, tf) - L(m, ICON)) / 2, iw, ICON, Paint{MUTED}, LEFT, GLYPH_CLOCK});
  p.text(x + pad + iw, yy, W - iw, tf, Paint{INK}, long_day(wd, d, day));
  yy += L(m, tf);
  const bool running = !all_day(e) && e.start <= t.at() && t.at() < e.end;
  p.text(x + pad + iw, yy, W - iw, mf, Paint{MUTED}, (all_day(e) ? wd.all_day : span_of(wd, d, e)) + (running ? " · " + left_of(wd, d, e, t) : ""));
  yy += L(m, mf) + P(12, 4);
  if (!e.place.empty()) {
    p.sc.texts.push_back({x + pad, yy + (L(m, mf) - L(m, ICON)) / 2, iw, ICON, Paint{MUTED}, LEFT, GLYPH_PLACE});
    p.text(x + pad + iw, yy, W - iw, mf, Paint{INK}, e.place);
    yy += L(m, mf) + P(12, 4);
  }
  if (has_note && yy < y + h - pad) p.para(x + pad + iw, yy, W - iw, mf, Paint{MUTED}, note, std::min(lines_note, (y + h - pad - yy) / std::max(1, L(m, mf))));
}
// The view key's choice: four views, the one on show ticked, in a sheet under the key.
// The view key's choice: the four views, and under them the card's calendars when it has more than one, a tap showing
// or hiding one while the full screen stays open (only where the glass has room for the row).
inline void choice(Pen &p, int width, int height, int margin, const HeaderPlace &hp, View on, const Words &wd, const Data &d, uint8_t hidden, const std::string &week_word) {
  const auto &m = p.m;
  p.box(0, hp.bottom + P(6, 3), width, height - hp.bottom - P(6, 3), Paint{SCRIM}, 0, 76);
  p.hit(0, 0, width, height, HIT_SCRIM);
  const Face tf = title_face(), mf = meta_face();
  const int rh = L(m, tf) + L(m, mf) + 2 * P(12, 6), w = std::min(width - 2 * margin, std::max(ui::mm(70), hp.view_w * 3));
  const int chip_h = std::max(ui::touch_min(), L(m, CONTROL) + P(16, 8)), caption = L(m, SMALL) + P(12, 6);
  const int room = height - hp.bottom - P(8, 4) - margin, views_h = 4 * rh + 2 * P(8, 4);
  const int calendars_h = caption + chip_h + P(14, 6);
  const bool chips = d.names.size() > 1 && views_h + calendars_h <= room;
  const int sheet_h = std::min(views_h + (chips ? calendars_h : 0), room);
  const int x = std::clamp(hp.view_x + hp.view_w - w, margin, width - margin - w), y = hp.bottom + P(8, 4);
  p.framed(x, y, w, sheet_h, Paint{RAISED}, Paint{RAISED_LINE}, P(18, 10));
  p.hit(x, y, w, sheet_h, HIT_SHEET);
  const View views[] = {UP_NEXT, DAY, WEEK, MONTH};
  for (int i = 0; i < 4; ++i) {
    const int ry = y + P(8, 4) + i * rh;
    if (ry + rh > y + sheet_h) break;
    const bool chosen = views[i] == on || (views[i] == WEEK && on == BLOCKS);
    if (chosen) p.box(x + P(8, 4), ry, w - 2 * P(8, 4), rh, Paint{ACCENT_TINT}, P(12, 6));
    const int ix = P(20, 10), cw = L(m, ICON);
    p.text(x + ix, ry + P(12, 6), w - 2 * ix - cw, tf, Paint{INK}, views[i] == WEEK ? week_word : wd.views[i]);
    p.text(x + ix, ry + P(12, 6) + L(m, tf), w - 2 * ix - cw, mf, Paint{MUTED}, wd.view_notes[i]);
    if (chosen) p.sc.texts.push_back({x + w - ix - cw, ry + (rh - L(m, ICON)) / 2, cw, ICON, Paint{ACCENT}, CENTRE, GLYPH_CHECK});
    p.hit(x, ry, w, rh, HIT_VIEW, (int) views[i]);
  }
  if (!chips) return;
  const int ix = P(20, 10), dot = P(12, 7);
  int yy = y + views_h - P(8, 4) + P(2, 1);
  p.text(x + ix, yy, w - 2 * ix, SMALL, Paint{MUTED}, wd.calendars);
  yy += caption;
  int cx = x + ix, row = 0;
  for (size_t c = 0; c < d.names.size() && c < 8; ++c) {
    const bool shown = !(hidden & (1u << c));
    const int tw = std::min(m.width(CONTROL, d.names[c]), w / 2), chip_w = dot + P(10, 5) + tw + P(32, 16);
    if (cx + chip_w > x + w - ix) { if (row) break; ++row; cx = x + ix; yy += chip_h + P(8, 4); if (yy + chip_h > y + sheet_h) break; }
    if (shown) p.box(cx, yy, chip_w, chip_h, cal(CAL_BLOCK, (uint8_t) c), chip_h / 2);
    else p.framed(cx, yy, chip_w, chip_h, Paint{RAISED}, Paint{GRID}, chip_h / 2, P(2, 1));
    p.box(cx + P(16, 8), yy + (chip_h - dot) / 2, dot, dot, shown ? cal(CAL_KEY, (uint8_t) c) : Paint{SUBTLE}, dot / 2);
    p.text(cx + P(16, 8) + dot + P(10, 5), yy + (chip_h - L(m, CONTROL)) / 2, tw + 2, CONTROL, shown ? cal(CAL_INK, (uint8_t) c) : Paint{MUTED}, d.names[c]);
    p.hit(cx, yy, chip_w, chip_h, HIT_CALENDAR, (int) c);
    cx += chip_w + P(10, 5);
  }
}
inline const char *view_word(const Words &wd, View v) { return (v == UP_NEXT ? wd.views[0] : v == DAY ? wd.views[1] : v == MONTH ? wd.views[3] : wd.views[2]).c_str(); }
// Plans the whole full screen for a state; returns the view drawn (a week the glass cannot hold becomes the Watch's
// week without words; a day on tall glass becomes a scrolling timeline).
inline View plan_full(Full &f, const Measure &m, int width, int height, int margin, const Data &all, Moment t, const Options &o, const Words &wd, const std::string &name, const State &st) {
  // Calendars hidden from the view choice leave the plan, their events and their dots in the month.
  Data kept;
  if (st.hidden) {
    kept = all;
    kept.events.clear();
    for (auto &e : all.events) if (!(st.hidden & (1u << std::min<int>(e.cal, 7)))) kept.events.push_back(e);
    for (auto &mask : kept.glance) mask &= uint8_t(~st.hidden);
  }
  const Data &d = st.hidden ? kept : all;
  f.fixed.clear(); f.scroll.clear(); f.overlay.clear(); f.sh = 0; f.scroll_to = 0; f.month_list = false;
  Pen p{f.fixed, m};
  const int body_y = margin + key_size(m) + P(12, 6), bw = width - 2 * margin, bh = height - body_y - margin;
  View v = st.view;
  const bool week_ok = week_fits(m, bw, bh, false);
  if (v == WEEK && !week_ok) v = BLOCKS;
  // The week moves by the days it shows: three days on narrow glass, so forward shows the next three, none skipped.
  const int week_days = v == BLOCKS ? 7 : fit_days(m, bw), week_d0 = week_start(d, t, o) + week_days * st.week;
  // Fewer days than a week are named by their count, "3 days", as Google's calendar does; the key and its choice agree.
  const int fits = week_ok ? fit_days(m, bw) : 7;
  const std::string week_word = fits < 7 ? with(wd.days_view, std::to_string(fits)) : wd.views[2];
  std::string second;
  if (v == WEEK || v == BLOCKS) {
    const Date wk = date_of(d, week_d0);
    second = wd.months[wk.month - 1] + " " + std::to_string(wk.year);
  } else if (v == MONTH) {
    const Date dt = date_of(d, t.day);
    int mo = dt.month - 1 + st.month, yr = dt.year;
    while (mo < 0) { mo += 12; --yr; }
    while (mo > 11) { mo -= 12; ++yr; }
    second = wd.months[mo] + " " + std::to_string(yr);
  } else second = long_day(wd, d, v == DAY ? st.day : t.day);
  // The period on show, short: "18 – 24 Oct", "Sun 18 Oct", "October 2026".
  auto month_short = [&](int month) { return wd.months_short[month - 1].empty() ? wd.months[month - 1] : wd.months_short[month - 1]; };
  std::string period;
  if (v == WEEK || v == BLOCKS) {
    const Date a = date_of(d, week_d0), z = date_of(d, week_d0 + week_days - 1);
    period = a.month == z.month ? std::to_string(a.day) + " – " + std::to_string(z.day) + " " + month_short(z.month)
                                : std::to_string(a.day) + " " + month_short(a.month) + " – " + std::to_string(z.day) + " " + month_short(z.month);
  } else if (v == DAY || v == UP_NEXT) {
    const Date dt = date_of(d, v == DAY ? st.day : t.day);
    period = wd.days[dt.weekday] + " " + std::to_string(dt.day) + " " + month_short(dt.month);
  } else {
    const Date dt = date_of(d, t.day);
    int mo = dt.month - 1 + st.month, yr = dt.year;
    while (mo < 0) { mo += 12; --yr; }
    while (mo > 11) { mo -= 12; ++yr; }
    period = month_short(mo + 1) + " " + std::to_string(yr);
  }
  const HeaderPlace hp = header(p, width, margin, name, second, v == WEEK ? week_word : std::string(view_word(wd, v)), wd, period);
  const Status s = status(d, t, o);
  if (v == UP_NEXT) {
    const int uh = std::max(up_next_min(m), std::min(bh / 2, up_next_min(m) + 2 * L(m, VALUE)));
    up_next(p, margin, body_y, bw, uh, d, t, o, wd);
    list(p, margin, body_y + uh + P(12, 6), bw, bh - uh - P(12, 6), d, t, s, wd, 12, s.now >= 0 ? -1 : s.next);
  } else if (v == MONTH) {
    f.month_list = month(p, margin, body_y, bw, bh, d, t, wd, st.day, st.month, o.week_numbers);
  } else if (v == DAY) {
    // The strip runs from today, a week at a time, as the week does.
    const int w0 = week_start(d, t, o), d0 = w0 + 7 * ((st.day - w0) >= 0 ? (st.day - w0) / 7 : -((w0 - st.day + 6) / 7));
    day_strip(p, margin, body_y, bw, d, t, wd, st.day, d0);
    const int y = body_y + strip_height(m) + P(12, 6), h = body_y + bh - y;
    // Tall glass (standing up): the day as a scrolling timeline, hours down; a list would leave half the glass empty.
    if (h / hour_pref(m) >= 12) {
      WeekShape ws;
      ws.days = 1; ws.d0 = st.day; ws.gw = gutter(m, &wd); ws.cw = bw - ws.gw;
      const int ar = all_day_rows(p, margin, y, ws, d, wd);
      ws.h0 = 0; ws.h1 = 24;
      ws.hour_h = std::max(hour_pref(m), (h - ar) / 12);
      f.sx = margin; f.sy = y + ar; f.sw = bw; f.sh = h - ar;
      Pen sp{f.scroll, m};
      const int top = L(m, SMALL);
      week_grid(sp, 0, top, ws, d, t, wd, false, 0, 0);
      f.scroll.height = top + 24 * ws.hour_h + top;
      f.scroll_to = std::clamp((st.day == t.day ? t.minute / 60 - 1 : 7) * ws.hour_h, 0, std::max(0, f.scroll.height - f.sh));
    } else day_list(p, margin, y, bw, h, d, t, s, wd, st.day);
  } else {
    // The week: the heads and all-day rows stay, the hours scroll; it opens an hour before now.
    WeekShape ws;
    ws.bare = v == BLOCKS;
    ws.days = week_days;
    ws.d0 = week_d0;
    ws.gw = ws.bare ? m.width(SMALL, "00") + P(10, 6) : gutter(m, &wd);
    ws.cw = (bw - ws.gw) / ws.days;
    int y = body_y + week_heads(p, margin, body_y, ws, d, t, wd);
    if (!ws.bare) y += all_day_rows(p, margin, y, ws, d, wd);
    const int h = body_y + bh - y;
    if (ws.bare) {
      // The Watch's week on small glass: seven narrow days of colour without words, the hours every three, no scroll.
      WeekShape probe = ws; hours_of(probe, d, t, 0);
      ws.h0 = probe.h0; ws.h1 = probe.h1;
      const int top = L(m, SMALL) / 2;
      ws.hour_h = std::max(1, (h - top - P(4, 2)) / std::max(1, ws.h1 - ws.h0));
      week_grid(p, margin, y + top, ws, d, t, wd, false, 0, 0);
    } else {
      ws.h0 = 0; ws.h1 = 24;
      if (o.hours_to > o.hours_from) { ws.h0 = o.hours_from; ws.h1 = o.hours_to; }
      // Generous rows: about eleven hours on the glass, never less than a half-hour event needs for its title.
      ws.hour_h = std::max(hour_pref(m), h / std::min(11, ws.h1 - ws.h0));
      f.sx = margin; f.sy = y; f.sw = bw; f.sh = h;
      Pen sp{f.scroll, m};
      const int top = L(m, SMALL);
      week_grid(sp, 0, top, ws, d, t, wd, false, 0, 0);
      f.scroll.height = top + (ws.h1 - ws.h0) * ws.hour_h + top;
      const bool this_week = t.day >= ws.d0 && t.day < ws.d0 + ws.days;
      f.scroll_to = std::clamp(((this_week ? t.minute / 60 - 1 : 7) - ws.h0) * ws.hour_h, 0, std::max(0, f.scroll.height - f.sh));
    }
  }
  Pen op{f.overlay, m};
  if (st.menu) choice(op, width, height, margin, hp, v, wd, all, st.hidden, week_word);
  else if (st.sheet >= 0) sheet(op, width, height, margin, d, t, wd, st.sheet, st.detail);
  f.view = v;
  return v;
}

}  // namespace calendar_card
