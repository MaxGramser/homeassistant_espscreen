#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_climate_card.cpp -o /tmp/test_climate_card && /tmp/test_climate_card
#include "../components/smart_display/climate_card.h"
#include <cassert>
#include <cstdlib>
#include <cstdio>

using namespace climate_card;

static bool inside(const Rect &r, int width, int top, int bottom) {
  return r.x >= 0 && r.right() <= width && r.y >= top && r.bottom() <= bottom;
}
static bool apart(const Rect &a, const Rect &b) {
  return a.right() <= b.x || b.right() <= a.x || a.bottom() <= b.y || b.bottom() <= a.y;
}

// Every part inside the card's area, nothing over anything else, and everything a finger uses big enough.
static void sound(const Metrics &m, const Layout &l, int width, int top, int bottom) {
  const Rect *parts[] = {&l.setpoint, &l.minus, &l.plus, &l.number};
  for (const Rect *r : parts) { assert(r->w > 0 && r->h > 0); assert(inside(*r, width, top, bottom)); }
  assert(inside(l.power, width, 0, bottom));
  // The keys stand at the two edges of the setpoint card with the number between them, all on one centre line.
  assert(l.minus.w == l.minus.h && l.plus.w == l.plus.h && l.minus.w == l.plus.w);
  assert(l.minus.w >= m.touch && l.minus.cy() == l.plus.cy() && std::abs(l.minus.cy() - l.setpoint.cy()) <= 1);
  assert(l.minus.right() <= l.number.x && l.number.right() <= l.plus.x);
  if (!l.caption.empty()) assert(l.caption.y == l.number.bottom() && l.caption.x == l.number.x);
  // The blocks share one width: the fan row is never wider than the setpoint above it (0.2.92 and before drew
  // the settings card at 94 % of the glass while its rows kept the capped width, leaving a white strip).
  if (l.mode_count) { assert(l.modes.w == l.setpoint.w || l.columns == 2); assert(l.modes.h >= m.min_key()); }
  if (l.row_count) {
    assert(l.settings.w == l.setpoint.w || l.columns == 2);
    for (int i = 0; i < l.row_count; ++i) {
      assert(inside(l.rows[i], width, top, bottom) && l.rows[i].h >= m.min_row());
      assert(l.row_icons[i].right() == l.row_tracks[i].x);
      assert(l.row_tracks[i].right() == l.rows[i].right() && l.row_tracks[i].w > 0);
      assert(l.rows[i].y >= l.settings.y && l.rows[i].bottom() <= l.settings.bottom());
    }
  }
  // Nothing overlaps: the blocks are a stack in one column, two stacks side by side in two.
  const Rect *blocks[] = {&l.status, &l.setpoint, &l.modes, &l.settings};
  for (const Rect *a : blocks)
    for (const Rect *b : blocks)
      if (a != b && !a->empty() && !b->empty()) assert(apart(*a, *b));
  if (l.columns == 1) {
    if (l.mode_count) assert(l.setpoint.bottom() <= l.modes.y);
    if (l.row_count) assert(l.setpoint.bottom() <= l.settings.y);
  } else {
    if (l.mode_count) assert(l.setpoint.right() <= l.modes.x);
    if (l.row_count) assert(l.setpoint.right() <= l.settings.x);
  }
  if (l.mode_count && l.row_count) assert(l.modes.bottom() <= l.settings.y);
  if (!l.status.empty()) assert(l.status.y >= top && l.status.bottom() <= l.setpoint.y);
}

static Metrics guition() {
  ui::configure(170, "standard");
  Metrics m; m.number_h = 64; m.number_w = 150; m.small_number_h = 38; m.small_number_w = 90;
  m.caption_h = 19; m.text_h = 25; m.status_h = 25; m.icon_h = 28; m.side = 20;
  m.bar = 60; m.bar_x = 16; m.bar_y = 16; m.touch = ui::touch_min();
  return m;
}
// The real CYD, measured on the glass: a 47 px setpoint, a 29 px card heading, 13 px captions.
static Metrics cyd() {
  ui::configure(143, "compact");
  Metrics m; m.large = false; m.number_h = 47; m.number_w = 103; m.small_number_h = 29; m.small_number_w = 62;
  m.caption_h = 13; m.text_h = 22; m.status_h = 25; m.icon_h = 28; m.side = 20;
  m.bar = 40; m.bar_x = 10; m.bar_y = 8; m.touch = ui::touch_min();
  return m;
}
// A 480 x 272 panel: as wide as the Guition, little more than half its height.
static Metrics short_wide() {
  ui::configure(128, "standard");
  Metrics m; m.number_h = 48; m.number_w = 113; m.small_number_h = 29; m.small_number_w = 68;
  m.caption_h = 14; m.text_h = 19; m.status_h = 19; m.icon_h = 21; m.side = 15;
  m.bar = 45; m.bar_x = 12; m.bar_y = 12; m.touch = ui::touch_min();
  return m;
}

// The Waveshare P4: square glass at 255 dpi, the standard look at 150 %. Its text font, which the state line is written
// in, is 31 px high (measured in the WASM preview), and climate_metrics() makes the line that tall (status_h).
static Metrics dense_square() {
  ui::configure(255, "standard");
  Metrics m; m.number_h = 96; m.number_w = 225; m.small_number_h = 57; m.small_number_w = 135;
  m.caption_h = 28; m.text_h = 31; m.status_h = m.text_h; m.icon_h = 42; m.side = 30;
  m.bar = 90; m.bar_x = 24; m.bar_y = 24; m.touch = ui::touch_min();
  return m;
}

int main() {
  // The Guition: the card it was designed on. Everything at its full size, in one column.
  {
    Metrics m = guition();
    const int width = 451, top = 84, bottom = 480 - m.margin();
    Layout l = layout(m, width, top, bottom, 3, 1);
    sound(m, l, width, top, bottom);
    assert(l.columns == 1 && l.mode_count == 3 && l.row_count == 1);
    assert(!l.status.empty() && !l.caption.empty());
    assert(l.setpoint.h >= 160 && l.minus.w >= 96);
    // Three modes and a fan row still leave the setpoint most of the card.
    assert(l.setpoint.h > l.modes.h && l.setpoint.h > l.settings.h);
  }
  // The Guition with everything a thermostat can have: six modes, fan and swing.
  {
    Metrics m = guition();
    const int width = 451, top = 84, bottom = 480 - m.margin();
    Layout l = layout(m, width, top, bottom, 6, 2);
    sound(m, l, width, top, bottom);
    assert(l.mode_count == 6 && l.row_count == 2 && l.columns == 1);
  }
  // A thermostat with one mode has no mode row: the power key already turns it on and off.
  {
    Metrics m = guition();
    Layout l = layout(m, 451, 84, 462, 1, 0);
    sound(m, l, 451, 84, 462);
    assert(l.mode_count == 0 && l.row_count == 0 && l.modes.empty() && l.settings.empty());
    assert(l.setpoint.h == m.setpoint_max());
  }
  // A device with no temperature to set (no TARGET_TEMPERATURE and no range: tile_controls::climate_setpoint) has no
  // setpoint card and no - and +: the state line, which says what it does and what it measures, then the modes and
  // the rows in one column, on a large glass and on the smallest. The line stays, also where a thermostat's gives way.
  for (int small = 0; small < 2; ++small) {
    Metrics m = small ? cyd() : guition();
    const int width = small ? 320 : 451, top = small ? 52 : 84, bottom = (small ? 240 : 480) - m.margin();
    for (int columns = 1; columns <= 2; ++columns) {
      Layout l = layout(m, width, top, bottom, 4, 2, columns, false, false);
      assert(l.columns == 1 && l.mode_count == 4 && l.row_count == 2);
      assert(l.setpoint.empty() && l.minus.empty() && l.plus.empty() && l.number.empty() && l.caption.empty());
      assert(!l.small_number && !l.caption_is_status && !l.range);
      assert(!l.status.empty() && inside(l.status, width, top, bottom));
      assert(inside(l.modes, width, top, bottom) && inside(l.settings, width, top, bottom));
      assert(l.status.bottom() <= l.modes.y && l.modes.bottom() <= l.settings.y);
      assert(l.modes.h >= m.min_key() && l.modes.w == l.settings.w);
      for (int i = 0; i < 2; ++i) assert(l.rows[i].h >= m.min_row() && l.rows[i].bottom() <= l.settings.bottom());
      // The blocks stand in the middle of the room under the line, as a thermostat's do.
      assert(std::abs((l.modes.y - l.status.bottom()) - (bottom - l.settings.bottom())) <= m.gap());
    }
    // With nothing but its modes, or nothing at all, the card is the line and what there is.
    Layout only = layout(m, width, top, bottom, 3, 0, 1, false, false);
    assert(only.mode_count == 3 && only.settings.empty() && only.setpoint.empty() && !only.status.empty());
    Layout bare = layout(m, width, top, bottom, 1, 0, 1, false, false);
    assert(bare.modes.empty() && bare.settings.empty() && bare.setpoint.empty() && !bare.status.empty());
    assert(need_height(m, 4, 2, false) < need_height(m, 4, 2));
  }
  // The CYD: the smallest glass that ships. Setpoint, modes and a fan row all keep their place.
  {
    Metrics m = cyd();
    const int width = 300, top = 50, bottom = 240 - m.margin();
    Layout l = layout(m, width, top, bottom, 3, 1);
    sound(m, l, width, top, bottom);
    assert(l.columns == 1 && l.mode_count == 3 && l.row_count == 1);
    assert(l.setpoint.h >= m.min_setpoint(false));
  }
  // The same CYD with fan and swing, which is what a real air conditioner brings: everything keeps its place,
  // and the state line, the word under the number and the size of the number give way in that order.
  {
    Metrics m = cyd();
    const int width = 320, top = 52, bottom = 240 - m.margin();
    Layout l = layout(m, width, top, bottom, 3, 2);
    sound(m, l, width, top, bottom);
    assert(l.row_count == 2 && l.mode_count == 3 && !l.settings.empty());
    assert(l.status.empty() && l.small_number);        // no room for a line of its own, so smaller digits
    assert(l.settings.bottom() <= bottom);             // and nothing hangs over the bottom edge
  }
  // A 480 x 272 panel: the stack still fits in one column, concessions and all.
  {
    Metrics m = short_wide();
    const int width = 480, top = 63, bottom = 272 - m.margin();
    Layout one = layout(m, width, top, bottom, 3, 2);
    sound(m, one, width, top, bottom);
    assert(one.columns == 1 && one.row_count == 2 && one.settings.bottom() <= bottom);
    assert(top + need_height(m, 3, 2) + m.margin() <= 272);
  }
  // Glass shorter still (a strip of 480 x 200): the card stands in two columns, the setpoint beside the rows.
  {
    Metrics m = short_wide();
    const int width = 480, top = 63, bottom = 200 - m.margin();
    assert(top + need_height(m, 3, 2) + m.margin() > 200);
    assert(min_column(m) * 2 + ui::column_gap() <= width);
    Layout two = layout(m, width, top, bottom, 3, 2, 2);
    sound(m, two, width, top, bottom);
    assert(two.columns == 2 && two.mode_count >= 1 && two.row_count == 2);
    // The setpoint keeps its keys a finger wide beside the number, and the rows stand next to it.
    assert(two.minus.w >= m.touch && two.setpoint.right() <= two.settings.x);
  }
  // Mode keys never get narrower than a finger: a row too small carries fewer keys.
  {
    Metrics m = guition();
    assert(mode_keys_fit(m, 451, 6) >= 3);
    assert(mode_keys_fit(m, 200, 6) == 3);
    assert(mode_keys_fit(m, 40, 6) == 1);
  }
  // A heat pump with five modes and a fan row on the P4: the state line keeps the height of the font it is written in
  // and stands clear of the setpoint card. With the old fixed 25 px the layout gave it six pixels too few, and once
  // the gaps had given way the line ran into the card (seen on the glass).
  {
    Metrics m = dense_square();
    const int width = 720, top = m.bar_y + m.bar + ui::px(8), bottom = 720 - m.margin();
    Layout l = layout(m, width, top, bottom, 5, 1);
    sound(m, l, width, top, bottom);
    if (!l.status.empty()) assert(l.status.h == m.text_h && l.status.y + m.text_h <= l.setpoint.y);
    else assert(l.caption_is_status);
    Metrics old = m; old.status_h = 25;
    Layout before = layout(old, width, top, bottom, 5, 1);
    assert(!before.status.empty() && before.status.y + m.text_h > before.setpoint.y);  // the bug this guards
  }
  printf("test_climate_card: ok\n");
  return 0;
}
