#include "screen_text_en.h"
#include "components/smart_display/header_bar.h"
#include <cassert>
#include <cstdio>
using namespace header_bar;
int main() {
  assert(kind("clock") == Kind::clock && kind("analog") == Kind::analog && kind("date") == Kind::date);
  assert(kind("text") == Kind::text && kind("ago") == Kind::ago);
  for (const char *bad : {"", "Clock", "time", "state"}) assert(kind(bad) == Kind::none);

  uint32_t c = 0;
  assert(color("FFB300", c) && c == 0xFFB300);
  assert(color("43a047", c) && c == 0x43A047);
  for (const char *bad : {"", "FFB30", "FFB3000", "#FFB30", "GGGGGG"}) assert(!color(bad, c));

  // UTF-8: ASCII, two, three and four bytes; a broken sequence still moves on.
  std::string s = "a°—\U000F050F";
  size_t i = 0;
  assert(next_codepoint(s, i) == 'a' && next_codepoint(s, i) == 0xB0 && next_codepoint(s, i) == 0x2014);
  assert(next_codepoint(s, i) == 0xF050F && next_codepoint(s, i) == 0 && i == s.size());
  std::string broken = "\xE2" "x";
  i = 0;
  next_codepoint(broken, i);
  assert(next_codepoint(broken, i) == 'x');

  // The editor's agoText() uses the same words and thresholds.
  const int64_t now = 1789401840;
  assert(ago_text(now, 0) == "—" && ago_text(0, now) == "—");
  assert(ago_text(now - 59, now) == "Just now");
  assert(ago_text(now - 60, now) == "1 min ago");
  assert(ago_text(now - 3599, now) == "59 min ago");
  assert(ago_text(now - 3600, now) == "1 hour ago");
  assert(ago_text(now - 86399, now) == "23 hours ago");
  assert(ago_text(now - 86400, now) == "Yesterday");
  assert(ago_text(now - 172800, now) == "2 days ago");
  assert(ago_text(now - 604800, now) == "1 week ago");
  assert(ago_text(now - 2 * 604800, now) == "2 weeks ago");
  assert(ago_text(now - 2592000, now) == "1 month ago");
  assert(ago_text(now - 3 * 2592000, now) == "3 months ago");
  assert(ago_text(now - 31536000, now) == "1 year ago");
  assert(ago_text(now + 30, now) == "In 1 min");
  assert(ago_text(now + 600, now) == "In 10 min");
  assert(ago_text(now + 3600, now) == "In 1 hour");
  assert(ago_text(now + 7200, now) == "In 2 hours");
  assert(ago_text(now + 90000, now) == "Tomorrow");
  assert(ago_text(now + 3 * 86400, now) == "In 3 days");

  assert(date_text(2, 14, 9) == "Mo 14 Sep" && date_text(1, 1, 1) == "Su 1 Jan" && date_text(7, 31, 12) == "Sa 31 Dec");
  assert(date_text(0, 1, 1) == "—" && date_text(1, 1, 13) == "—");

  // Guition: digits 15 px high; CYD: 10 px.
  auto g = gaps(15);
  assert(g.icon == 6 && g.item == 19 && g.name == 24);
  auto small = gaps(10);
  assert(small.icon == 4 && small.item == 13 && small.name == 16);
  assert(gaps(1).icon == 2 && gaps(1).item == 6 && gaps(1).name == 8);

  // Everything fits: right-aligned with item gaps, the name keeps the rest.
  int widths[] = {80, 50, 49};
  auto p = place(widths, 3, g, 448, 100);
  assert(p.first == 0 && p.x[2] == 448 - 49 && p.x[1] == p.x[2] - 19 - 50 && p.x[0] == p.x[1] - 19 - 80);
  assert(p.name_room == p.x[0] - 24);
  // Too full: items leave from the front until the rest fits beside the name.
  int many[] = {86, 163, 50, 60};
  auto q = place(many, 4, g, 448, 100);
  assert(q.first == 1);
  int total = 163 + 50 + 60 + 2 * 19;
  assert(q.x[1] == 448 - total && q.name_room >= 100);
  // A long name keeps 35% of the width, never more than it needs.
  auto r = place(many, 4, g, 448, 400);
  assert(r.first == 2 && r.name_room >= 448 * 35 / 100);
  // Nothing to show: the name gets the whole width.
  auto empty = place(many, 0, g, 448, 400);
  assert(empty.first == 0 && empty.name_room == 448);
  // Items wider than the bar all leave.
  int huge[] = {500};
  auto none = place(huge, 1, g, 448, 50);
  assert(none.first == 1 && none.name_room == 448);

  // The screensaver clock's row: centred, with the bar's gaps.
  auto mid = centre(widths, 3, g, 448);
  const int row = 80 + 50 + 49 + 2 * 19;
  assert(mid.count == 3 && mid.x[0] == (448 - row) / 2 && mid.x[1] == mid.x[0] + 80 + 19 && mid.x[2] == mid.x[1] + 50 + 19);
  // Too full: items leave from the end, so the first (the temperature) stays.
  auto cut = centre(many, 4, g, 300);
  assert(cut.count == 2 && cut.x[0] == (300 - (86 + 19 + 163)) / 2);
  assert(centre(huge, 1, g, 448).count == 0 && centre(many, 0, g, 448).count == 0);
  std::puts("test_header_bar: PASS");
}
