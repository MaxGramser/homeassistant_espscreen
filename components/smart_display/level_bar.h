#pragma once
// A level on a still glass (docs/PAPER.md, "A level"): what a slider is on a glass that cannot follow a finger. A
// refresh of e-paper takes longer than a drag, so a knob that slides shows nothing while the finger moves and jumps
// when it lifts. There a level is one shape that fills in steps, with a mark for each step and a key at each end: a
// tap on a step sets that level, the keys take one step down and up, and each tap is one refresh. The same thing
// e-readers and watches do with a value on a slow glass: fixed steps, set by a tap, a key at each side for one step.
// It fills as the slider of a lit glass fills, so the two are one control to the eye (the owner chose it from four
// drawn side by side, 2026-11-27: loose blocks between round keys stood apart from each other).
//
// This file is the rules, free of LVGL: where the keys and the blocks lie in a control's own rectangle, what a point
// in it picks, and how a value and a count of blocks turn into each other. still_glass_lvgl.h draws it on every
// lv_slider of a still glass and hears the finger; a lit glass keeps the slider it had. tests/test_level_bar.cpp.
#include <cstdint>

namespace level_bar {

// The blocks a range is cut into: ten, or one for each whole value of a range that has twelve or fewer (a fan of
// four speeds is four blocks, not ten of which six mean nothing).
constexpr int MOST = 10;
constexpr int steps_for(int low, int high) {
  const int span = high > low ? high - low : low - high;
  return span >= 1 && span <= 12 ? span : MOST;
}

// A slider's range often reaches a little past its real ends: below nothing, so that the least fill is still a stub
// to hold (-40 to 1000, or 1 less a few to 100), or past both ends of a blind. A level has no stub to draw, so it
// counts between the real ends: nothing, and a hundred or a thousand. A short range (a fan's speeds from 1) is left
// as it is.
constexpr int real_end(int end, int other) {
  const int span = end > other ? end - other : other - end;
  if (span <= 12) return end;
  if (end <= 1 && end > -(span / 4)) return 0;
  if (end > 100 && end - 100 < span / 4 && other < 100) return 100;
  if (end > 1000 && end - 1000 < span / 4 && other < 1000) return 1000;
  return end;
}

struct Box {
  int x = 0, y = 0, w = 0, h = 0;
  constexpr bool has(int px, int py) const { return px >= x && px < x + w && py >= y && py < y + h; }
};

// Where everything lies in a control of w x h, its own top left at (0, 0). A control thick enough for a finger has a
// key at each end: minus at the left and plus at the right of one lying down, minus at the bottom and plus at the top
// of one standing up. A key is as thick as the control, so keys and blocks stand in one line, and a sixth of the
// control's length, never less than a finger needs or more than the control is thick: as long as a wide control is
// thick, the two keys of a lamp's card left its ten blocks the room of ten lines, and as round keys narrower than the
// blocks they stood loose from them (a reTerminal Sticky's renders, 2026-11-27). A thin control (the slider under a
// tile's name) is blocks alone. `key_least` is the least side of a key a finger hits, in pixels.
struct Layout {
  bool upright = false;  // the blocks stand on each other, the first at the bottom
  bool keys = false;
  Box minus, plus;
  Box blocks;            // the room of all blocks
  int count = MOST;
  int gap = 0;
  // The part of the room the first `level` steps fill: from the bottom of one standing up, from the start of one lying.
  constexpr Box filled(int level) const {
    const int along = upright ? blocks.h : blocks.w;
    const int part = level <= 0 ? 0 : level >= count ? along : along * level / count;
    if (upright) return {blocks.x, blocks.y + blocks.h - part, blocks.w, part};
    return {blocks.x, blocks.y, part, blocks.h};
  }
  // Where step `n` ends along the room, counted from its start: where its mark stands.
  constexpr int mark(int n) const { return (upright ? blocks.h : blocks.w) * n / count; }
  // Block `n` of count, the first is 1.
  constexpr Box block(int n) const {
    const int along = upright ? blocks.h : blocks.w;
    const int from = (along + gap) * (n - 1) / count, to = (along + gap) * n / count - gap;
    if (upright) return {blocks.x, blocks.y + blocks.h - to, blocks.w, to - from};
    return {blocks.x + from, blocks.y, to - from, blocks.h};
  }
};
constexpr Layout layout(int w, int h, int count, int key_least, int gap) {
  Layout l;
  l.count = count < 1 ? 1 : count;
  l.gap = gap;
  l.upright = h > w;
  const int thick = l.upright ? w : h, along = l.upright ? h : w;
  int key = along / 6;
  if (key < key_least) key = key_least;
  if (key > thick) key = thick;
  l.keys = thick >= key_least && along >= key * 2 + l.count * (gap + 4) + gap * 4;
  if (!l.keys) {
    l.blocks = {0, 0, w, h};
  } else if (l.upright) {
    l.plus = {0, 0, w, key};
    l.minus = {0, h - key, w, key};
    l.blocks = {0, key + gap * 2, w, h - 2 * key - gap * 4};
  } else {
    l.minus = {0, 0, key, h};
    l.plus = {w - key, 0, key, h};
    l.blocks = {key + gap * 2, 0, w - 2 * key - gap * 4, h};
  }
  return l;
}

// What a point picks. A block picks its level; the first quarter of the first block, and anything before it, picks
// none of them, so a control without keys can still be set to nothing.
struct Pick {
  enum Kind : uint8_t { NONE, MINUS, PLUS, LEVEL } kind = NONE;
  int level = 0;
};
constexpr Pick pick(const Layout &l, int x, int y) {
  if (l.keys && l.minus.has(x, y)) return {Pick::MINUS, 0};
  if (l.keys && l.plus.has(x, y)) return {Pick::PLUS, 0};
  const int along = l.upright ? l.blocks.h : l.blocks.w;
  if (along <= 0) return {};
  // How far along the blocks, from their first: a point beside the control still counts for its nearest end.
  int at = l.upright ? l.blocks.y + l.blocks.h - 1 - y : x - l.blocks.x;
  if (at < 0) at = 0;
  if (at >= along) at = along - 1;
  const int quarter = along / (l.count * 4);
  if (at < quarter) return {Pick::LEVEL, 0};
  int level = at * l.count / along + 1;
  if (level > l.count) level = l.count;
  return {Pick::LEVEL, level};
}

// The blocks a value fills: the nearest count, and never none for a value above the range's start (a lamp at 3 % is
// on, and shows one block).
constexpr int level_of(int value, int low, int high, int count) {
  // How far the value lies from the range's start, counted the way the range runs.
  long span = high - low, far = value - low;
  if (span < 0) {
    span = -span;
    far = -far;
  }
  if (span == 0 || count < 1 || far <= 0) return 0;
  int level = static_cast<int>((far * count + span / 2) / span);
  if (level > count) level = count;
  if (level == 0 && value != low) level = 1;
  return level;
}
// The value of a count of blocks.
constexpr int value_of(int level, int low, int high, int count) {
  if (count < 1) return low;
  if (level <= 0) return low;
  if (level >= count) return high;
  return low + static_cast<int>(static_cast<long>(high - low) * level / count);
}
// The value one step down or up from `value`: to the next whole block that way, never past an end.
constexpr int step(int value, int direction, int low, int high, int count) {
  const int at = level_of(value, low, high, count);
  // A value between two blocks goes to the block below it for a step down, the one above for a step up.
  const int exact = value_of(at, low, high, count);
  const bool below = (high >= low) ? value < exact : value > exact;
  const bool above = (high >= low) ? value > exact : value < exact;
  int to = at + direction;
  if (direction < 0 && above) to = at;
  if (direction > 0 && below) to = at;
  return value_of(to < 0 ? 0 : to > count ? count : to, low, high, count);
}

}  // namespace level_bar
