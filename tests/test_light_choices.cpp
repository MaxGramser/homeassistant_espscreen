// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_light_choices.cpp -o /tmp/test_light_choices && /tmp/test_light_choices
// A light's colour and white shade as named choices (light_choices.h): which name a hue and a kelvin belong to, what
// each name sends, and how the keys stand.
#include "../components/smart_display/light_choices.h"
#include <cassert>
#include <cstdio>

using namespace light_choices;

static void a_hue_has_a_name() {
  // Each name is its own hue's.
  for (int i = 0; i < COLOURS; ++i) assert(colour_of(HUES[i]) == i);
  // Around the wheel: 350 degrees is red, not pink's far neighbour, and so is 360.
  assert(colour_of(350) == 0 && colour_of(360) == 0 && colour_of(5) == 0);
  assert(colour_of(40) == 1 && colour_of(60) == 2 && colour_of(100) == 3 && colour_of(200) == 4);
  assert(colour_of(230) == 5 && colour_of(290) == 6 && colour_of(335) == 7);
  assert(apart(350, 10) == 20 && apart(10, 350) == 20 && apart(0, 180) == 180);
}

static void a_white_shade_has_a_name() {
  // A lamp with the usual range: the shades lamps are sold in.
  assert(shade_kelvin(0, 2000, 6500) == 2700 && shade_kelvin(1, 2000, 6500) == 4000 && shade_kelvin(2, 2000, 6500) == 6000);
  assert(shade_of(2200, 2000, 6500) == 0 && shade_of(3000, 2000, 6500) == 0 && shade_of(3800, 2000, 6500) == 1);
  assert(shade_of(5500, 2000, 6500) == 2 && shade_of(6500, 2000, 6500) == 2);
  // A range that ends below cool: cool is its end.
  assert(shade_kelvin(2, 2200, 5000) == 5000 && shade_kelvin(1, 2200, 5000) == 4000);
  // A narrow range (a filament lamp, 2200 to 4000 K) holds fewer than three of them: its ends and its middle.
  assert(shade_kelvin(0, 2200, 4000) == 2200 && shade_kelvin(1, 2200, 4000) == 3100 && shade_kelvin(2, 2200, 4000) == 4000);
  assert(shade_of(2200, 2200, 4000) == 0 && shade_of(3200, 2200, 4000) == 1 && shade_of(3900, 2200, 4000) == 2);
  // Every shade lies in the light's range, and they never run back.
  for (int low = 1500; low <= 4000; low += 250)
    for (int high = low + 100; high <= 9000; high += 250) {
      int last = low;
      for (int n = 0; n < SHADES; ++n) {
        const int k = shade_kelvin(n, low, high);
        assert(k >= low && k <= high && k >= last);
        last = k;
      }
    }
}

static void the_keys_stand_even() {
  // Eight names with room for five beside each other: four over four.
  assert(grid(8, 500, 90, 10).columns == 4 && grid(8, 500, 90, 10).rows == 2);
  // Room for all: one row. Room for one: a column.
  assert(grid(8, 900, 90, 10).columns == 8 && grid(8, 900, 90, 10).rows == 1);
  assert(grid(8, 80, 90, 10).columns == 1 && grid(8, 80, 90, 10).rows == 8);
  // Three shades in a narrow room: three rows are not made of two and one.
  assert(grid(3, 400, 120, 10).columns == 3 && grid(3, 250, 120, 10).columns == 2 && grid(3, 250, 120, 10).rows == 2);
  assert(grid(8, 320, 90, 10).columns == 3 && grid(8, 320, 90, 10).rows == 3);
}

int main() {
  a_hue_has_a_name();
  a_white_shade_has_a_name();
  the_keys_stand_even();
  std::puts("light_choices: ok");
  return 0;
}
