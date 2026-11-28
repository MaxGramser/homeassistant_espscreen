#pragma once
// A light's colour and white shade as named choices (docs/PAPER.md, "A colour by its name"): what the colour card's
// two spectrum rows are on a glass that shows no colour. A spectrum drawn in ink is a grey band that says nothing, and
// a knob on it says less, so there a colour is a word: a handful of keys with the colours' names, and three for the
// white shade. The key of what the light has now stands filled.
//
// This file is the rules, free of LVGL: which colours and shades there are, what each sends, which of them a light's
// hue or kelvin is nearest to, and how many keys go in a row. light_controls.h draws them where the glass is ink; a
// glass that is lit keeps its two sliders. tests/test_light_choices.cpp.
#include <cstdint>

namespace light_choices {

// The colours, around the wheel: the hue each one sends, at full saturation. The words are screen texts
// (light.color_red and on, in this order).
constexpr int COLOURS = 8;
constexpr int HUES[COLOURS] = {0, 30, 55, 120, 180, 240, 275, 320};  // red orange yellow green cyan blue purple pink

// The distance between two hues around the wheel.
constexpr int apart(int a, int b) {
  int d = (a - b) % 360;
  if (d < 0) d += 360;
  return d > 180 ? 360 - d : d;
}
// The colour a hue is nearest to.
constexpr int colour_of(int hue) {
  int best = 0;
  for (int i = 1; i < COLOURS; ++i)
    if (apart(hue, HUES[i]) < apart(hue, HUES[best])) best = i;
  return best;
}

// The white shades: warm, neutral and cool, as lamps are sold (2700 K, 4000 K, 6000 K), each held to the light's own
// range. A light whose range holds fewer than three of them gets the ends and the middle of what it has.
constexpr int SHADES = 3;
constexpr int NAMED[SHADES] = {2700, 4000, 6000};
constexpr int held(int kelvin, int low, int high) { return kelvin < low ? low : kelvin > high ? high : kelvin; }
constexpr int shade_kelvin(int n, int low, int high) {
  if (high <= low) return low;
  const int warm = held(NAMED[0], low, high), neutral = held(NAMED[1], low, high), cool = held(NAMED[2], low, high);
  if (warm == neutral || neutral == cool) return n <= 0 ? low : n == 1 ? low + (high - low) / 2 : high;
  return n <= 0 ? warm : n == 1 ? neutral : cool;
}
constexpr int shade_of(int kelvin, int low, int high) {
  int best = 0;
  for (int i = 1; i < SHADES; ++i) {
    const int a = kelvin - shade_kelvin(i, low, high), b = kelvin - shade_kelvin(best, low, high);
    if ((a < 0 ? -a : a) < (b < 0 ? -b : b)) best = i;
  }
  return best;
}

// How `count` keys stand in `room` pixels when the widest needs `widest` and two stand `gap` apart: as many beside
// each other as fit, and then as few rows as that takes with the rows evenly filled (eight keys with room for five
// stand four over four, not five over three).
struct Grid {
  int columns = 1, rows = 1;
};
constexpr Grid grid(int count, int room, int widest, int gap) {
  if (count < 1) return {};
  int fit = widest + gap > 0 ? (room + gap) / (widest + gap) : count;
  if (fit < 1) fit = 1;
  if (fit > count) fit = count;
  const int rows = (count + fit - 1) / fit;
  return {(count + rows - 1) / rows, rows};
}

}  // namespace light_choices
