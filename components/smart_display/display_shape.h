#pragma once
// The usable rectangles of circular glass. Pure geometry, independent of LVGL, board names and entity state.
// Native frames consume these bounds; controls, drawing and navigation stay with their existing owners.
// tests/test_display_shape.cpp checks whole rectangles, including the footer's touch band.
#include <algorithm>
#include <cmath>

namespace display_shape {
struct Rect { int x = 0, y = 0, w = 0, h = 0; };
inline int radius(int width, int height, int edge) {
  return std::max(0, std::min(width, height) / 2 - std::max(0, edge));
}
inline Rect band(int width, int height, int edge, int top, int bottom) {
  const int r = radius(width, height, edge), cy = height / 2;
  const int dy = std::max(std::abs(top - cy), std::abs(bottom - cy));
  const int half = dy < r ? static_cast<int>(std::floor(std::sqrt(double(r) * r - double(dy) * dy))) : 0;
  return {width / 2 - half, top, 2 * half, std::max(0, bottom - top)};
}
inline Rect workspace(int width, int height, int edge) {
  const int half = static_cast<int>(std::floor(radius(width, height, edge) / std::sqrt(2.0)));
  return {width / 2 - half, height / 2 - half, 2 * half, 2 * half};
}
inline Rect footer(int width, int height, int edge, int touch) {
  const int r = radius(width, height, edge);
  // Three finger-sized zones, with room for the native density-scaled dots between the outer keys.
  const int half = std::min(r, touch * 9 / 5);
  const int bottom = height / 2 + static_cast<int>(std::floor(std::sqrt(std::max(0.0, double(r) * r - double(half) * half))));
  return band(width, height, edge, std::max(height / 2, bottom - touch), bottom);
}
struct Home { Rect status, heading, grid, footer; };
inline Home home(int width, int height, int edge, int touch, int line, int mark, int gap, int row_gap) {
  Home f;
  const int top = height / 2 - radius(width, height, edge) + touch * 2 / 5;
  f.status = band(width, height, edge, top, top + line);
  const int title_y = top + line + row_gap;
  f.heading = band(width, height, edge, title_y, title_y + std::max(line, mark));
  f.footer = footer(width, height, edge, touch);
  f.grid = band(width, height, edge, f.heading.y + f.heading.h + gap, f.footer.y - gap);
  return f;
}
}  // namespace display_shape
