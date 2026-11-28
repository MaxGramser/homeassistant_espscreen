// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_calendar_card.cpp -o /tmp/test_calendar_card && /tmp/test_calendar_card
// The calendar card's plan (components/smart_display/calendar_card.h) on the faces of the boards it runs on: every
// box and line inside the room it got, the ladder of views growing with the room, no word broken in two, a timed
// event winning over an all-day one, and the full screen's hours scrolling where the glass holds a week.
#include "../components/smart_display/calendar_card.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>

using namespace calendar_card;

// Roboto's line is 1.17 of its size; widths in em, near enough for layout. A glyph of the icon font is one em.
static int line(int size) { return (int) std::lround(size * 1.172); }
static int wide(const std::string &s, int size) {
  double em = 0;
  for (size_t i = 0; i < s.size(); ++i) {
    const unsigned char c = s[i];
    if (c >= 0xF0) { em += 1.0; i += 3; }
    else if (c == ' ') em += 0.25;
    else if (c >= 'A' && c <= 'Z') em += 0.65;
    else if ((c & 0xC0) != 0x80) em += 0.56;
  }
  return (int) std::lround(em * size);
}
struct Board { const char *name, *look; int dpi, width, height, circle; int sizes[FACES]; };
// label, sublabel, sublabel_big, headline, watch_value, clock_digits, icon mini, icon (packages/looks via profiles)
static const Board BOARDS[] = {
  {"cyd", "compact", 143, 320, 240, 36, {11, 11, 14, 18, 22, 24, 18, 28}},
  {"guition", "standard", 170, 480, 480, 54, {18, 16, 21, 27, 38, 48, 26, 42}},
  {"waveshare43", "standard", 217, 800, 480, 69, {23, 20, 27, 34, 49, 61, 33, 54}},
  {"d1001", "standard", 189, 1280, 800, 60, {20, 18, 23, 30, 42, 54, 29, 47}},
  {"jc8012p4a1", "standard", 149, 1280, 800, 47, {16, 14, 18, 24, 33, 42, 23, 37}},
};
static Measure measure(const Board &b) {
  Measure m;
  for (int f = 0; f < FACES; ++f) m.line[f] = line(b.sizes[f]);
  const Board *bp = &b;
  m.width = [bp](Face f, const std::string &s) { return wide(s, bp->sizes[f]); };
  m.circle = b.circle;
  return m;
}
static Words words() {
  Words w;
  w.free = "Free"; w.busy = "Busy"; w.starts_soon = "Starts soon"; w.private_title = "Busy"; w.all_day = "All day";
  w.today = "Today"; w.tomorrow = "Tomorrow"; w.nothing = "Nothing planned"; w.nothing_more = "Nothing else this week";
  w.until = "Until {x}"; w.next = "Next {x}"; w.left = "{x} left"; w.in = "in {x}"; w.more = "{x} more";
  w.earlier = "{x} earlier"; w.later = "{x} later"; w.week = "Week {x}"; w.more_week = "{x} more this week"; w.days_view = "{x} days";
  w.days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"};
  w.days_long = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"};
  w.letters = {"Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"};
  w.months = {"January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"};
  w.views = {"Up next", "Day", "Week", "Month"};
  w.view_notes = {"What runs now", "One day", "Days side by side", "A glance at the month"};
  w.today_key = "Today";
  w.clock = [](int m) { char b[8]; snprintf(b, sizeof b, "%02d:%02d", m / 60 % 24, m % 60); return std::string(b); };
  return w;
}
static Data demo() {
  Data d;
  d.year = 2026; d.month = 10; d.day = 14; d.weekday = 2;
  d.colors = {0x4269D0, 0xF4BD4A, 0xFF725C}; d.names = {"Home", "Work", "School"}; d.from = -2; d.to = 14;
  auto ev = [&](int day, int a, int b, const char *t, uint8_t c, uint8_t f = 0, const char *pl = "") {
    Event e; e.start = day * 1440 + a; e.end = day * 1440 + b; e.title = t; e.cal = c; e.flags = f; e.place = pl; d.events.push_back(e);
  };
  ev(-2, 0, 5 * 1440, "Sprint week", 1, ALL_DAY);
  ev(-2, 600, 630, "Kick-off call", 1); ev(-1, 540, 600, "Dentist", 0, 0, "Main Street 12");
  ev(0, 495, 525, "School run", 0); ev(0, 660, 720, "Sign the lease", 0); ev(0, 810, 900, "Design review", 1, 0, "Room 2");
  ev(0, 930, 960, "Parent evening", 2); ev(0, 1020, 1080, "Presentation", 1); ev(0, 1140, 1320, "Dinner with friends", 0);
  ev(1, 0, 1440, "Bin day", 0, ALL_DAY); ev(1, 540, 585, "Drop off the car", 0); ev(2, 630, 720, "Contracts", 1);
  ev(2, 660, 690, "Coffee with Ana", 0); ev(3, 600, 660, "Football practice", 0);
  return d;
}
static void inside(const Scene &sc, int w, int h, const char *where) {
  for (auto &b : sc.boxes)
    if (b.x < 0 || b.y < -2 || b.x + b.w > w + 1 || b.y + b.h > h + 2) { fprintf(stderr, "%s: box %d,%d %dx%d leaves %dx%d\n", where, b.x, b.y, b.w, b.h, w, h); assert(false); }
  for (auto &t : sc.texts) assert(t.x >= -1 && t.x + t.w <= w + 2);
}
int main() {
  const Data d = demo();
  const Words wd = words();
  const Options o;
  const Moment now{0, 14 * 60 + 10};
  // A timed event that runs wins over the all-day one; the next is the first to start after now.
  const Status s = status(d, now, o);
  assert(s.now >= 0 && d.events[s.now].title == "Design review");
  assert(s.next >= 0 && d.events[s.next].title == "Parent evening");
  // "Starts soon": only when nothing runs, within the minutes the card was given.
  Options soon; soon.soon = 15;
  assert(status(d, Moment{0, 15 * 60 + 20}, soon).soon && !status(d, Moment{0, 15 * 60 + 5}, soon).soon);
  for (const auto &b : BOARDS) {
    ui::configure(b.dpi, b.look);
    const Measure m = measure(b);
    // Words wrap at spaces only: a word wider than the box stands alone and ends in dots.
    for (auto &row : wrap(m, LABEL, "Dinner with friends tonight", 3 * b.sizes[LABEL], 2)) assert(m.width(LABEL, row) <= 3 * b.sizes[LABEL]);
    assert(fit(m, SMALL, "A very long title that never fits", 40).find("...") != std::string::npos);
    // The ladder: a bigger card never shows a smaller view, and every plan stays inside its card.
    Scene sc;
    View last = NOW_VIEW;
    for (int k = 1; k <= 6; ++k) {
      const int w = b.width * k / 6 - 2 * 14, h = b.height * k / 6 - 2 * 14;
      if (w < 60 || h < 40) continue;
      const View v = plan_tile(sc, m, w, h, d, now, o, wd, "Family");
      inside(sc, w, h, b.name);
      assert(v >= last || v == AGENDA || last == COLUMNS);
      last = v;
    }
    // The full screen in every view, with the view key's choice and an event's sheet open.
    for (View view : {UP_NEXT, DAY, WEEK, MONTH}) {
      Full f;
      State st; st.view = view;
      plan_full(f, m, b.width, b.height, 14, d, now, o, wd, "Family", st);
      inside(f.fixed, b.width, b.height, b.name);
      if (f.sh > 0) {
        // The hours scroll: the whole day is there, and it opens before now.
        assert(f.scroll.height > f.sh && f.scroll_to > 0 && f.scroll_to <= f.scroll.height - f.sh);
        inside(f.scroll, f.sw, f.scroll.height, b.name);
      }
      st.menu = true; plan_full(f, m, b.width, b.height, 14, d, now, o, wd, "Family", st);
      assert(!f.overlay.hits.empty());
      st.menu = false; st.sheet = s.now; plan_full(f, m, b.width, b.height, 14, d, now, o, wd, "Family", st);
      inside(f.overlay, b.width, b.height, b.name);
    }
    // The large glass holds a week on the full screen; the CYD falls back to the day.
    State st; st.view = WEEK; Full f;
    const View v = plan_full(f, m, b.width, b.height, 14, d, now, o, wd, "Family", st);
    if (std::string(b.name) == "d1001" || std::string(b.name) == "jc8012p4a1") assert(v == WEEK);
    if (std::string(b.name) == "cyd") assert(v == BLOCKS);
    // Forward and back move by the days on show: on glass with three days the next step starts on the fourth, none skipped.
    auto days_shown = [&](int week, bool from_monday) {
      State ws; ws.view = WEEK; ws.week = week; Full wf; Options wo; wo.from_monday = from_monday;
      plan_full(wf, m, b.width, b.height, 14, d, now, wo, wd, "Family", ws);
      std::vector<int> days;
      for (auto &h : wf.fixed.hits) if (h.kind == HIT_DAY) days.push_back(h.arg);
      return days;
    };
    for (bool from_monday : {false, true}) {
      const auto here = days_shown(0, from_monday), next = days_shown(1, from_monday), back = days_shown(-1, from_monday);
      assert(!here.empty() && next.front() == here.back() + 1 && back.back() == here.front() - 1);
    }
    // A view of fewer days than seven is named by their count on its key and in the view choice, not "Week".
    {
      State ws; ws.view = WEEK; ws.menu = true; Full wf;
      plan_full(wf, m, b.width, b.height, 14, d, now, o, wd, "Family", ws);
      int n = 0; for (auto &h : wf.fixed.hits) n += h.kind == HIT_DAY;
      const std::string word = n < 7 ? std::to_string(n) + " days" : "Week";
      bool key = false, listed = false;
      for (auto &x : wf.fixed.texts) key |= x.s == word;
      for (auto &x : wf.overlay.texts) listed |= x.s == word;
      assert(key && listed);
    }
  }
  // Overlapping events stand side by side.
  const auto lanes = lanes_of(d, 2);
  assert(lanes.size() == 2 && lanes[0].lanes == 2 && lanes[1].lane == 1);
  // Over midnight: a night shift stands in the hours of both days, a conference of three days with the all-day ones,
  // and their times name their days.
  {
    Data e = demo();
    const Words wd = words();
    Event shift; shift.start = 1320; shift.end = 1440 + 360; shift.title = "Night shift"; e.events.push_back(shift);
    Event conf; conf.start = -1440 + 540; conf.end = 1440 + 1020; conf.title = "Conference"; e.events.push_back(conf);
    const int si = (int) e.events.size() - 2, ci = (int) e.events.size() - 1;
    auto has = [&](int day, int i) { for (auto &ln : lanes_of(e, day)) if (ln.index == i) return true; return false; };
    assert(has(0, si) && has(1, si) && !has(0, ci) && !has(1, ci));
    assert(banded(conf) && !banded(shift) && start_in(shift, 1) == 0 && end_in(shift, 1) == 360);
    assert(span_of(wd, e, shift) == "Wed 22:00 – Thu 06:00" && span_of(wd, e, e.events[3]) == "08:15 – 08:45");
    // Running since yesterday, it is listed under today; its head says until which day.
    assert(shown_day(conf, 0) == 0);
    Data only = e; only.events = {conf};
    assert(head_words(only, Moment{0, 600}, Options{}, wd, "Family").brief == "Until Tomorrow 17:00");
    // More all-day events than three rows: two rows and a third that counts the rest per day, opening that day.
    Data busy = demo();
    for (int k = 0; k < 6; ++k) { Event a; a.start = 0; a.end = 1440; a.flags = ALL_DAY; a.title = "Holiday"; busy.events.push_back(a); }
    const Measure m = measure(BOARDS[3]);
    Scene sc; Pen p{sc, m};
    WeekShape ws; ws.d0 = 0; ws.days = 7; ws.gw = 60; ws.cw = 160;
    const int rows = all_day_rows(p, 0, 0, ws, busy, wd);
    assert(rows == 3 * allday_h(m));
    bool plus = false, opens = false;
    for (auto &t : sc.texts) plus |= t.s == "+5";
    for (auto &h : sc.hits) opens |= h.kind == HIT_DAY && h.arg == 0;
    assert(plus && opens);
  }
  // A tapped short event: the sheet shows the short title until the app answers, then the whole title, place and notes
  // of that event (not of another one at the same time), on every board's glass.
  for (const auto &b : BOARDS) {
    ui::configure(b.dpi, b.look);
    const Measure m = measure(b);
    Data shortened = demo(); shortened.asks = true;
    const int k = 6;  // Parent evening, not the event of the moment
    Full f; State st; st.view = DAY; st.sheet = k;
    auto shown = [&](const std::string &text) { for (auto &t : f.overlay.texts) if (t.s.find(text) != std::string::npos) return true; return false; };
    plan_full(f, m, b.width, b.height, 14, shortened, now, o, wd, "Family", st);
    assert(shown("Parent") && !shown("Bring the reports"));
    st.detail.cal = shortened.events[k].cal; st.detail.start = shortened.events[k].start; st.detail.end = shortened.events[k].end;
    st.detail.answered = true; st.detail.title = "Parent evening with the class"; st.detail.place = "Hall"; st.detail.notes = "Bring the reports";
    plan_full(f, m, b.width, b.height, 14, shortened, now, o, wd, "Family", st);
    // The whole title, on two lines where one does not hold it.
    assert(shown("Hall") && shown("Bring") && shown("class"));
    inside(f.overlay, b.width, b.height, b.name);
    st.detail.start += 1;  // an answer for another event changes nothing
    plan_full(f, m, b.width, b.height, 14, shortened, now, o, wd, "Family", st);
    assert(!shown("Hall"));
  }
  // The agenda's last line counts this week only, and says "more" without the week when the app left out events of it.
  {
    ui::configure(BOARDS[2].dpi, BOARDS[2].look);
    const Measure m = measure(BOARDS[2]);
    auto last_line = [&](const Data &dd) {
      Scene sc;
      plan_tile(sc, m, 448, 448, dd, Moment{0, 8 * 60}, o, wd, "Family");
      for (auto &t : sc.texts) if (t.s.find("more") != std::string::npos) return t.s;
      return std::string();
    };
    auto busy_week = [] { Data b = demo(); for (int k = 0; k < 10; ++k) { Event e; e.start = (1 + k % 3) * 1440 + 600 + k * 30; e.end = e.start + 25; e.title = "Busy"; b.events.push_back(e); } return b; };
    Data later = busy_week();
    Event next_week; next_week.start = 9 * 1440 + 600; next_week.end = next_week.start + 60; next_week.title = "Next week"; later.events.push_back(next_week);
    later.left_out = 30;  // all of them after the week: the events reach past Sunday
    const std::string week = last_line(later);
    assert(week.find("this week") != std::string::npos && week.find("30") == std::string::npos);
    Data cut = busy_week(); cut.left_out = 30;  // the app's cut falls inside this week
    const std::string more = last_line(cut);
    assert(!more.empty() && more.find("this week") == std::string::npos);
  }
  printf("calendar card: ok\n");
  return 0;
}
