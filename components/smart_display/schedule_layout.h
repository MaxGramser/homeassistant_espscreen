#pragma once
#include "ui_scale.h"
#include <algorithm>
namespace schedule_layout {
struct Rect { int x=0, y=0, w=0, h=0; };
struct Layout {
  int width, height, pad, gap, key, header, day_columns, day_rows, body_bottom;
  bool paged;
  Rect back, save, title, body, pager;
};
inline Layout place(int width, int height, int font_height) {
  Layout l{}; l.width = width; l.height = height;
  l.pad = ui::px(ui::large() ? 12 : 6); l.gap = ui::px(6);
  l.key = std::max(ui::touch_min(), ui::px(ui::large() ? 46 : 32));
  l.header = l.key + 2*l.pad;
  l.day_columns = std::clamp((width - 2*l.pad + l.gap)/(l.key + l.gap), 1, 8);
  l.day_rows = (8 + l.day_columns - 1)/l.day_columns;
  // Day selector, time pills, bar, slot tools and temperature controls. Small
  // glass gets three pages instead of shrinking any explicit touch target.
  int need = l.header + l.day_rows*(l.key+l.gap) + 4*l.key + 4*font_height + 8*l.gap;
  l.paged = need > height;
  l.back = {l.pad,l.pad,l.key,l.key};
  l.save = {width-l.pad-l.key,l.pad,l.key,l.key};
  l.title = {2*l.pad+l.key,l.pad,width-4*l.pad-2*l.key,l.key};
  l.body_bottom = height - l.pad - (l.paged ? l.key+l.gap : 0);
  l.body = {l.pad,l.header,width-2*l.pad,l.body_bottom-l.header};
  l.pager = {l.pad,height-l.pad-l.key,width-2*l.pad,l.key};
  return l;
}
}  // namespace schedule_layout
