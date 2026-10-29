// A guard for the ESP32-P4's PPA, the engine that scales and turns a picture on its way to the glass. Under ESP-IDF 5.5
// a turned copy of some sizes never finishes: the task that asked for it waits for good on the driver's semaphore, no
// error, no log. On a screen whose glass is turned a quarter (the M5Stack Tab5: a 720x1280 panel shown as 1280x720)
// every copy is turned, LVGL's flush of each strip it draws as much as a live tile's picture, so sooner or later one of
// them hangs, the main loop stops behind it (LVGL holds the glass, live_view.cpp) and the task watchdog restarts the
// screen: a restart every few minutes with live camera tiles, found on a Tab5 of the dev channel (TR-4EFBDE,
// 2026-10-23, decoded by rebuilding its firmware: the crashed core sat idle).
//
// The cause is a hardware bug (Espressif's DIG-734): the 2D-DMA cuts a copy into units of 64 pixels by 16 rows (32 by
// 16 for 24- and 32-bit pixels) and when the last unit holds fewer bits than its FIFO (1536) it never counts the unit as
// received, so the DONE never comes. The driver knows and sets "bypass macro block order" for such a block, but in
// ESP-IDF 5.5.5 it works the leftover out from the input's width and height even when the block is turned, where the
// hardware cuts the turned output: a block whose turned leftover is small while its unturned one is not stalls on the
// first try (espressif/esp-idf #19023). Espressif's fix, 469aa16 on master (2026-01-29, "fix(ppa): fix for SRM
// operation potential block if do 90/270 degree rotation"), swaps width and height for 90 and 270 degrees before the
// check; the backport to 5.5 is promised but not in the ESP-IDF ESPHome 2026.9 builds with, so the firmware guards the
// call itself (ppa_guard.cpp, through a linker wrap of ppa_do_scale_rotate_mirror).
//
// The guard cannot set the bypass bit, only choose what it asks for. So it works out both rules, the hardware's (the fix)
// and the driver's (5.5.5), and a block the hardware would stall on while the driver leaves the bypass off is copied in
// pieces, each of which the hardware takes whole: its leftover is not small, or it is one unit, or the driver's own rule
// sets the bypass for it. Two pieces do in almost every case (the issue's 368x66 at 270 degrees goes as 368x65 and
// 368x1, the way its reporter worked around it); the rest are cut again, a few times at most. A block the driver takes
// as it is costs nothing. Every number here is the driver's: the FIFO's 1536 bits, the unit's 64 or 32 pixels, the macro
// block's rows, a scale's fraction in sixteenths and the truncation of a scaled size (ppa_srm.c, ppa_ll.h). The macro
// block is the engine's own: 16 rows on a firmware built for the P4's first revisions (the Tab5, the reTerminal D1001,
// most Guition panels: CONFIG_ESP32P4_SELECTS_REV_LESS_V3), and on one built for revision 3 (a Guition 10.1 of rev 3.2,
// its v3 profile) what the engine's register says, 32 unless set otherwise; the guard asks it as the driver does
// (ppa_srm.c, ppa_ll_srm_get_mb_size). Until 2026-10-27 it took 16 on every build, and on a rev 3 build it then judged
// some blocks safe that the engine stalls on (33x17 turned 270: the driver's rule sets the bypass for 16 rows, not 32).
// tests/test_ppa_guard.cpp proves the pieces cover the block once, land where the whole would, and are each safe, for
// both sizes.
//
// What the rules cannot do (measured 2026-10-27, docs/PLATFORM_PLAN.md 4.7): the stall is the memory bus's while the
// panel scans PSRAM, not the frame buffer's alone. On a Guition 10.1 the issue's 368x66 turned 270 stalled on its first
// copy into a PSRAM buffer no panel reads as well as into the frame buffer; on a reTerminal D1001 it came back at least
// 31 times before one stalled. And a copy both rules call safe stalls now and then too: a Tab5's live tile, 618x307
// turned 270 into its frame buffer (TR-2M2KX9), where 115,000 such copies on a Guition 10.1 and a D1001 never did. The
// guard keeps the blocks the hardware stalls on every time out of the engine; for the rest the PPA watch restarts the
// screen within four seconds (ppa_trace.h).
#pragma once
#include <cstdint>

namespace ppa_guard {

constexpr uint32_t FIFO_BITS = 12 * 128;  // the 2D-DMA's FIFO, as the driver's workaround counts it
constexpr uint32_t FRAG_MAX = 16;         // PPA_LL_SRM_SCALING_FRAG_MAX: a scale is a whole number and sixteenths
constexpr int MAX_PIECES = 32;
constexpr int MAX_DEPTH = 8;  // how often a piece may be cut again before the guard gives the block up

// The angle, counter-clockwise, as the PPA counts it (ppa_srm_rotation_angle_t: 0, 90, 180, 270 in that order).
enum Angle : uint8_t { A0 = 0, A90 = 1, A180 = 2, A270 = 3 };

// A scale the way the driver splits its float: a whole number and a fraction in sixteenths.
struct Scale {
  uint32_t whole = 1, frag = 0;
};

// What one call asks the engine for, as far as the stall is concerned.
struct Block {
  uint32_t w = 0, h = 0;  // the input block
  Angle angle = A0;
  Scale sx, sy;
  uint32_t unit_w = 64;  // a transaction unit's width in pixels: 64, or 32 for 24- and 32-bit output
  uint32_t mb = 16;      // a macro block's height in rows: 16, or 32 on a rev 3 build (the engine's register)
  uint32_t depth = 16;   // bits per output pixel
};

// A piece of the block: where it lies in the input block, and where its turned and scaled picture lies in the output
// block, both from the block's own corner.
struct Piece {
  uint32_t in_x = 0, in_y = 0, in_w = 0, in_h = 0, out_x = 0, out_y = 0;
};

// A size scaled the way the driver does it: the whole part, plus the fraction's share rounded down.
inline uint32_t scaled(uint32_t px, Scale s) { return px * s.whole + px * s.frag / FRAG_MAX; }
// Whether a position scales to a whole pixel: a piece may only start and end where it does.
inline bool exact(uint32_t px, Scale s) { return (px * s.frag) % FRAG_MAX == 0; }
inline bool turned(Angle a) { return a == A90 || a == A270; }

struct Size {
  uint32_t w = 0, h = 0;
};
// The output's width and height: from the input's height and width when turned.
inline Size output_of(const Block &b) {
  return turned(b.angle) ? Size{scaled(b.h, b.sy), scaled(b.w, b.sx)} : Size{scaled(b.w, b.sx), scaled(b.h, b.sy)};
}

// The rule for an output of `w` x `h`: cut into more than one unit, and the last unit holds fewer bits than the FIFO,
// or, with `equal_stalls`, no more than it. That is the block the DMA never finishes unless the bypass is set.
inline bool small_leftover(uint32_t w, uint32_t h, const Block &b, bool equal_stalls) {
  const uint32_t w_left = w % b.unit_w ? w % b.unit_w : b.unit_w;
  const uint32_t h_left = h % b.mb ? h % b.mb : b.mb;
  const uint32_t bits = w_left * h_left * b.depth;
  return (w > b.unit_w || h > b.mb) && (bits < FIFO_BITS || (equal_stalls && bits == FIFO_BITS));
}
// What the hardware does: the rule on the output as it comes out, turned (Espressif's fix, 469aa16), and a last unit
// of exactly the FIFO stalls too. Espressif's driver counts that one safe, master as much as 5.5.5, but a reTerminal
// D1001 (2026-10-27) restarted on it twice while its top bar was held: the line growing along the glass's edge is a
// 6-row strip, turned a 6-pixel-wide column of units of 6 x 16 x 16 bits, and the copies of 336x6 whole and of 864x6
// (a piece of 872x6) never came back while the panel read its frame buffer (the main loop waiting in ppa_do_operation,
// the guard's trace of the last calls naming the copy). Most such copies did come back, as in espressif/esp-idf #19096.
inline bool stalls(const Block &b) {
  const Size out = output_of(b);
  return small_leftover(out.w, out.h, b, true);
}
// What ESP-IDF 5.5.5's driver does: the rule on the input's own width and height, each with its own scale, turned or
// not, and strictly fewer bits than the FIFO.
inline bool driver_bypasses(const Block &b) { return small_leftover(scaled(b.w, b.sx), scaled(b.h, b.sy), b, false); }
// A block the engine takes whole: nothing to stall on, or the driver sets the bypass anyway.
inline bool safe(const Block &b) { return !stalls(b) || driver_bypasses(b); }

inline Block part(const Block &b, uint32_t w, uint32_t h) {
  Block p = b;
  p.w = w;
  p.h = h;
  return p;
}

// Where a piece at x, y of the block (w x h) lands in the output block, turned the engine's way: counter-clockwise, so
// at 90 degrees the input's last column becomes the output's first row, and at 270 its first row the output's last column.
inline void place(const Block &b, uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint32_t &out_x, uint32_t &out_y) {
  switch (b.angle) {
    case A0:
      out_x = scaled(x, b.sx);
      out_y = scaled(y, b.sy);
      break;
    case A90:
      out_x = scaled(y, b.sy);
      out_y = scaled(b.w - x - w, b.sx);
      break;
    case A180:
      out_x = scaled(b.w - x - w, b.sx);
      out_y = scaled(b.h - y - h, b.sy);
      break;
    case A270:
      out_x = scaled(b.h - y - h, b.sy);
      out_y = scaled(x, b.sx);
      break;
  }
}

namespace detail {

struct Plan {
  const Block &whole;
  Piece *pieces;
  int n = 0;
  bool failed = false;  // a piece the guard could not make safe, or more pieces than fit
};

inline void emit(Plan &p, uint32_t x, uint32_t y, const Block &b) {
  if (p.n >= MAX_PIECES) {
    p.failed = true;
    return;
  }
  Piece &piece = p.pieces[p.n++];
  piece.in_x = x;
  piece.in_y = y;
  piece.in_w = b.w;
  piece.in_h = b.h;
  place(p.whole, x, y, b.w, b.h, piece.out_x, piece.out_y);
}

inline bool column_cut_ok(const Block &b, uint32_t c) { return c > 0 && c < b.w && exact(c, b.sx); }
inline bool row_cut_ok(const Block &b, uint32_t r) { return r > 0 && r < b.h && exact(r, b.sy); }
inline bool both_safe_at_column(const Block &b, uint32_t c) {
  return column_cut_ok(b, c) && safe(part(b, c, b.h)) && safe(part(b, b.w - c, b.h));
}
inline bool both_safe_at_row(const Block &b, uint32_t r) {
  return row_cut_ok(b, r) && safe(part(b, b.w, r)) && safe(part(b, b.w, b.h - r));
}

// The last input position that scales to a whole pixel at or under `target`: `target` itself unscaled, or, when a
// scale's fraction puts no whole pixel there, the nearest one below it. 0 when there is none.
inline uint32_t position_of(uint32_t target, uint32_t limit, Scale s) {
  uint32_t found = 0;
  for (uint32_t px = 1; px < limit && scaled(px, s) <= target; ++px)
    if (exact(px, s)) found = px;
  return found;
}

// The output's last unit boundary along an axis of `size` pixels in units of `unit`: where its last, partial unit
// starts, or its last whole one when it is all whole units. 0 when it is one unit or less.
inline uint32_t last_unit(uint32_t size, uint32_t unit) {
  if (size <= unit) return 0;
  return size % unit ? size - size % unit : size - unit;
}
// The cut along the input's columns at the output's last unit boundary on the axis those columns feed (a turned
// block's rows), and the same along its rows, as input positions. 0 when there is none that is exact.
inline uint32_t aligned_column_cut(const Block &b) {
  const Size out = output_of(b);
  const uint32_t target = turned(b.angle) ? last_unit(out.h, b.mb) : last_unit(out.w, b.unit_w);
  return target ? position_of(target, b.w, b.sx) : 0;
}
inline uint32_t aligned_row_cut(const Block &b) {
  const Size out = output_of(b);
  const uint32_t target = turned(b.angle) ? last_unit(out.w, b.unit_w) : last_unit(out.h, b.mb);
  return target ? position_of(target, b.h, b.sy) : 0;
}

inline void cut(Plan &p, uint32_t x, uint32_t y, const Block &b, int depth);

// A cut into two pieces the engine takes whole, when there is one: the aligned cuts first, then every other.
inline bool cut_in_two(Plan &p, uint32_t x, uint32_t y, const Block &b) {
  const uint32_t ac = aligned_column_cut(b), ar = aligned_row_cut(b);
  uint32_t c = 0, r = 0;
  if (both_safe_at_column(b, ac)) c = ac;
  else if (both_safe_at_row(b, ar)) r = ar;
  if (!c && !r)
    for (uint32_t i = 1; i < b.w && !c; ++i)
      if (both_safe_at_column(b, i)) c = i;
  if (!c && !r)
    for (uint32_t i = 1; i < b.h && !r; ++i)
      if (both_safe_at_row(b, i)) r = i;
  if (c) {
    emit(p, x, y, part(b, c, b.h));
    emit(p, x + c, y, part(b, b.w - c, b.h));
    return true;
  }
  if (r) {
    emit(p, x, y, part(b, b.w, r));
    emit(p, x, y + r, part(b, b.w, b.h - r));
    return true;
  }
  return false;
}

inline void cut(Plan &p, uint32_t x, uint32_t y, const Block &b, int depth) {
  if (p.failed) return;
  if (safe(b)) {
    emit(p, x, y, b);
    return;
  }
  if (depth >= MAX_DEPTH) {
    p.failed = true;
    return;
  }
  if (cut_in_two(p, x, y, b)) return;
  // No cut makes both pieces safe at once: the last unit off, and each side on its own. A strip narrower than a unit
  // that is whole units long (a line LVGL draws across a turned glass) loses one unit at a time this way, until the
  // rest finds a cut in two, or is units alone.
  const uint32_t c = aligned_column_cut(b), r = aligned_row_cut(b);
  if (c) {
    cut(p, x, y, part(b, c, b.h), depth + 1);
    cut(p, x + c, y, part(b, b.w - c, b.h), depth + 1);
  } else if (r) {
    cut(p, x, y, part(b, b.w, r), depth + 1);
    cut(p, x, y + r, part(b, b.w, b.h - r), depth + 1);
  } else {
    p.failed = true;
  }
}

}  // namespace detail

// The pieces a block goes to the engine in: 1 and the block itself when the engine takes it whole, more when it would
// stall, 0 when the guard found no safe way (the block then goes as it is, as before the guard). Only a turned block is
// ever cut: unturned, the driver's rule is the hardware's. A block whose scaled size is not whole is left alone too,
// and one scaled by a fraction may stay whole when its cuts fall between pixels: every copy onto a turned glass at
// its own size (LVGL's flushes, a live tile) has a plan, and a camera's picture scaled to fill the full view almost
// always has one.
inline int plan(const Block &b, Piece *pieces) {
  if (b.w == 0 || b.h == 0 || b.unit_w == 0 || b.mb == 0 || b.depth == 0) return 0;
  const bool whole_block = !turned(b.angle) || safe(b) || !exact(b.w, b.sx) || !exact(b.h, b.sy);
  if (whole_block) {
    pieces[0] = Piece{0, 0, b.w, b.h, 0, 0};
    return 1;
  }
  detail::Plan p{b, pieces};
  detail::cut(p, 0, 0, b, 0);
  return p.failed ? 0 : p.n;
}

}  // namespace ppa_guard
