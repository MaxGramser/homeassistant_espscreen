#pragma once
// A picture that moves slowly over the glass (the screensaver's photos, app 0.4.89, and a plugin face over them, plugin
// API 0.14): the app cuts the photo a little larger than the glass (the place's `move`, picture_paint), and the screen shows
// the glass's piece of it, a pixel further every PIXEL_MS, from one corner of the room it has toward the opposite one
// and back, which corner by the photo's own mark. So slow that it reads as a still photo that breathes, and it costs one
// redraw of the glass every second and a half; nothing stands on the same pixels for long.
//
// Pure arithmetic, free of LVGL, so tests/test_picture_motion.cpp checks it on a PC; runtime_tiles.h moves the picture.
#include <algorithm>
#include <cstdint>
#include <string>

namespace picture_motion {

constexpr uint32_t PIXEL_MS = 1500;

// The room the piece has to move in (the picture's size less the glass's), and from which corner it starts: bit 0 the
// right edge, bit 1 the bottom one.
struct Path {
  int range_x = 0, range_y = 0;
  uint8_t corner = 0;
  bool moves() const { return range_x > 0 || range_y > 0; }
};
struct Offset { int x = 0, y = 0; };

// The same mark always takes the same corner; another photo most likely another.
inline uint8_t corner_of(const std::string &mark) {
  uint32_t h = 2166136261u;
  for (unsigned char c : mark) h = (h ^ c) * 16777619u;
  return static_cast<uint8_t>(h & 3u);
}

inline Path path(int picture_w, int picture_h, int glass_w, int glass_h, const std::string &mark) {
  Path p;
  p.range_x = std::max(0, picture_w - glass_w);
  p.range_y = std::max(0, picture_h - glass_h);
  p.corner = corner_of(mark);
  return p;
}

// Where the glass's piece starts in the picture, `elapsed` ms after the photo came: in the middle for a picture with no
// room, else along the diagonal, a pixel of the longer side every PIXEL_MS, and back once it reached the far corner.
inline Offset at(const Path &p, uint32_t elapsed) {
  if (!p.moves()) return {p.range_x / 2, p.range_y / 2};
  const uint32_t length = static_cast<uint32_t>(std::max(p.range_x, p.range_y));
  uint32_t step = (elapsed / PIXEL_MS) % (2 * length);
  if (step > length) step = 2 * length - step;
  Offset o{static_cast<int>(p.range_x * step / length), static_cast<int>(p.range_y * step / length)};
  if (p.corner & 1) o.x = p.range_x - o.x;
  if (p.corner & 2) o.y = p.range_y - o.y;
  return o;
}

}  // namespace picture_motion
