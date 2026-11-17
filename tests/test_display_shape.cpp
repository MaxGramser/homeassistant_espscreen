// Circular bounds include the entire touch rectangle, not just its centre or its drawn glyph.
#include "components/smart_display/display_shape.h"
#include <cassert>
#include <iostream>

static void inside(display_shape::Rect box, int side, int edge) {
  const int r = display_shape::radius(side, side, edge), c = side / 2;
  assert(box.w > 0 && box.h > 0);
  for (int x : {box.x, box.x + box.w})
    for (int y : {box.y, box.y + box.h})
      assert((x - c) * (x - c) + (y - c) * (y - c) <= r * r);
}
int main() {
  for (int side : {320, 466, 480, 720}) {
    const int touch = side * 75 / 466, edge = side * 11 / 466;
    const auto f = display_shape::home(side, side, edge, touch, side * 30 / 466,
                                       side * 33 / 466, side * 15 / 466, 4);
    for (auto box : {f.status, f.heading, f.grid, f.footer, display_shape::workspace(side, side, edge)})
      inside(box, side, edge);
    assert(f.status.y + f.status.h <= f.heading.y);
    assert(f.heading.y + f.heading.h < f.grid.y);
    assert(f.grid.y + f.grid.h < f.footer.y);
    assert(f.footer.h >= touch && f.footer.w >= 3 * touch);
    assert((f.grid.w - 8) / 2 >= touch && (f.grid.h - 4) / 2 >= touch);
  }
  std::cout << "PASS circular bounds: full touch bands, four tiles and native overlay workspace\n";
}
