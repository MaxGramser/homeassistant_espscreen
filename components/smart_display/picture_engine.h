#pragma once
// The picture engine: decode, scale, turn (docs/PICTURE_ARCHITECTURE.md, section 3.2). What turns a picture's bytes into
// pixels and pixels into other pixels, and which formats this screen's decoder takes. Three engines, chosen by the chip
// when the firmware is built (engine_build.py), as the firmware chooses its modules: on an ESP32-P4 the hardware JPEG
// decoder and the PPA, with ppa_guard between (PICTURE_ENGINE_P4, picture_engine_p4.cpp); on an ESP32-S3 with PSRAM
// Espressif's software JPEG decoder, which decodes the stills LVGL draws and a live tile's pictures, and a blit by the
// CPU that copies a picture as it is (PICTURE_ENGINE_S3, picture_engine_s3.cpp); everywhere else the BMP decoder row by
// row (picture_fetch::Decoder) and no blit at all, since LVGL draws every still there: the inline stubs below, which
// cost no flash.
//
// The app sends a live tile's pictures at its card's size and turned as the glass is (the hello's picture_turn,
// live_stream.py), so an engine never has to scale or turn for a tile: the S3's blit does neither, and the P4's PPA does
// so only for an app that sends them upright (live_view.cpp, turn_between).
//
// The engine knows the decoder, the PPA, the guard and the decoder's memory; it knows nothing of streams, sockets,
// owners or LVGL objects. The glass (glass.h) is held around every decode and every blit: by the engine itself for a
// still it decodes into a buffer of its own (decode), by the caller for a stream's decode into the stream's own buffer
// (decode_into) and for a blit, so the stream's task keeps its stop check under the same lock it had.
//
// The 2D-DMA's own facts are the engine's and nobody else's: its units of 64 pixels for 16-bit output and 32 for 24- and
// 32-bit, its macro block of 16 rows on every P4 build ESPHome makes, its FIFO of 1536 bits and the turned block with a
// small leftover it never finishes (DIG-734), as ppa_guard.h holds them; every PPA call of the firmware, the streams',
// LVGL's and a plugin's, passes the guard through the linker's wrap (ppa_guard.cpp). The clockwise turn LVGL counts
// becomes the PPA's counter-clockwise angle in one place, ppa_angle, which tests/test_picture_engine.cpp checks on a PC.
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>
// The engine's define comes with ESPHome's defines (engine_build.py); a PC test has none and builds without it.
#if __has_include("esphome/core/defines.h")
#include "esphome/core/defines.h"
#endif

namespace picture_engine {

// A decoded still: `stride` pixels a row (the decoder writes whole MCUs, picture_jpeg.h), its buffer `bytes` long.
struct Still {
  int w = 0, h = 0, stride = 0;
  size_t bytes = 0;
  uint32_t waited_ms = 0, held_ms = 0;  // decode's wait for the glass, then its hold of it (the P4's hardware decoder)
};
// One copy: the block `bw` x `bh` at bx, by of the picture `in` (`in_w` pixels a row, `in_rows` rows, RGB565) to x, y
// of the picture `out` (`out_w` x `out_h`, `out_size` bytes), scaled by `scale` (the engine's own unit, as fit and cut
// below give it; AS_IS leaves the size) and turned `turn` degrees clockwise, as LVGL counts its rotation.
struct Block {
  const void *in = nullptr;
  int in_w = 0, in_rows = 0, bx = 0, by = 0, bw = 0, bh = 0;
  void *out = nullptr;
  size_t out_size = 0;
  int out_w = 0, out_h = 0, x = 0, y = 0;
  int scale = 16;  // AS_IS
  int turn = 0;
  // `in` is a camera's YUV420 (ESP's packed layout, as the P4's ISP gives it, BT.601 limited range), turned into RGB565
  // on the way; its block's offsets and size even. The screen's own camera on a tile of its own (live_view.cpp).
  bool yuv420 = false;
  // `out` wants each RGB565 pixel's two bytes swapped (a panel LVGL draws big-endian, glass::Panel::swapped).
  bool swap = false;
};
// A client of the PPA, one per stream; nullptr for none.
using Client = void *;

// ---- Where a picture goes, in the engine's own scale ----
// The P4's PPA scales in sixteenths (ESP-IDF's ppa_srm.c): a block of `n` pixels at `sixteenths` / 16 comes out this
// long. The shared code never counts in them: it asks fit or cut, and hands their `scale` to Block as it is. An engine
// that scales otherwise brings its own fit, cut and blit.
constexpr int AS_IS = 16;
inline int scaled(int n, int sixteenths) { return (sixteenths / 16) * n + (sixteenths % 16) * n / 16; }
constexpr int MAX_SIDE = 2048;      // a picture larger than this a side the engine does not take
constexpr int MAX_SCALE = 16 * 16;  // sixteen times: a 80 x 50 picture still fills the glass
// A picture of w x h as large as it fits in the room ax, ay, aw x ah, its proportions kept, in the middle: the app sends
// the camera's own size where that is smaller than the glass (a substream of 512 x 288 costs Home Assistant a fraction
// of a 1280 x 720 JPEG), and the engine scales it on its way to the frame buffer. Empty when even the least step does
// not fit, or for a picture over MAX_SIDE.
struct Fit {
  int x = 0, y = 0, w = 0, h = 0;
  int scale = 0;
  bool empty() const { return w <= 0 || h <= 0; }
};
inline Fit fit(int w, int h, int ax, int ay, int aw, int ah) {
  if (w <= 0 || h <= 0 || w > MAX_SIDE || h > MAX_SIDE || aw <= 0 || ah <= 0) return {};
  int s = std::min(16 * aw / w, 16 * ah / h);
  s = std::min(s, MAX_SCALE - 1);
  // The PPA's sums floor each part on their own: a step back where they round a pixel over the room.
  while (s > 0 && (scaled(w, s) > aw || scaled(h, s) > ah)) --s;
  if (s <= 0) return {};
  const int fw = scaled(w, s), fh = scaled(h, s);
  return {ax + (aw - fw) / 2, ay + (ah - fh) / 2, fw, fh, s};
}
// Where a picture of w x h goes in a card of cw x ch: the engine reads the block in_* of it and writes out_* at `scale`.
// Filling: the middle of the picture, scaled up only when it is smaller than the card. Whole (contain): all of it, as
// large as fits, in the middle.
struct Cut {
  int in_x = 0, in_y = 0, in_w = 0, in_h = 0;
  int out_x = 0, out_y = 0, out_w = 0, out_h = 0;
  int scale = 0;
  bool ok = false;
  bool covers(int cw, int ch) const { return ok && out_x == 0 && out_y == 0 && out_w == cw && out_h == ch; }
};
inline Cut cut(int w, int h, int cw, int ch, bool contain) {
  Cut c;
  if (w <= 0 || h <= 0 || cw <= 0 || ch <= 0 || w > MAX_SIDE || h > MAX_SIDE) return c;
  if (contain) {
    const Fit r = fit(w, h, 0, 0, cw, ch);
    if (r.empty()) return c;
    c.scale = r.scale;
    c.in_w = w;
    c.in_h = h;
    c.out_x = r.x, c.out_y = r.y, c.out_w = r.w, c.out_h = r.h;
    c.ok = true;
    return c;
  }
  // The least scale at which the picture covers the card: AS_IS for a picture the app sent at the card's size.
  int s = AS_IS;
  while (s < MAX_SCALE - 1 && (scaled(w, s) < cw || scaled(h, s) < ch)) ++s;
  while (s > 1 && scaled(w, s - 1) >= cw && scaled(h, s - 1) >= ch) --s;
  if (scaled(w, s) < cw || scaled(h, s) < ch) return c;
  // The largest block of the picture that, scaled, stays within the card.
  auto block = [s](int n, int room) {
    int in = std::min(n, (room * 16 + s - 1) / s);
    while (in > 1 && scaled(in, s) > room) --in;
    return in;
  };
  c.scale = s;
  c.in_w = block(w, cw);
  c.in_h = block(h, ch);
  c.in_x = (w - c.in_w) / 2;
  c.in_y = (h - c.in_h) / 2;
  c.out_w = scaled(c.in_w, s);
  c.out_h = scaled(c.in_h, s);
  c.out_x = (cw - c.out_w) / 2;
  c.out_y = (ch - c.out_h) / 2;
  c.ok = true;
  return c;
}

// ---- What this engine takes (docs/PICTURE_ARCHITECTURE.md, section 2.4) ----
// The numbers the shared code reads instead of a chip's: the burst every 2D-DMA client moves in, so the panel's own DMA
// gets its turn on the memory bus (glass.h, "The panel's share of the memory bus"), the largest picture a stream's
// part may be, a full view's and a tile's (0: no such stream), how many live camera tiles the screen streams at once
// (hw::caps, the hello's live_tiles, docs/PLATFORM_PLAN.md 4.1), whether a decode holds the glass, as one that runs on
// the 2D-DMA must (glass.h: its one user at a time), the most pictures a second a full view decodes (0: as they come;
// the pictures that come sooner are passed, and the sound plays on), the pictures a second all live tiles share
// (tile_pps), the core a stream's task decodes and copies on, and how many streams of every kind it holds at once (live
// tiles, a full view and a plugin's live places alike, one that is still ending counted: live_view::open). 0 takes no
// pictures at all, never "no limit".
struct Limits {
  int burst_bytes;
  size_t picture_bytes, tile_picture_bytes;
  uint8_t live_tiles;
  bool decode_on_glass;
  uint8_t view_pps;
  uint8_t tile_budget_pps;
  uint8_t stream_core;
  uint8_t streams;
};
// The pictures a second each of `tiles` live tiles shows: the engine's budget shared among them, at least 2 (fewer
// reads as stills) and at most `most` (hw::LIVE_TILE_PPS, every board alike). On a P4 four tiles keep their 6 each; an
// S3's budget of 8 would give two tiles 4 each and three 2 (its CPU decodes them all).
inline int tile_pps(int budget, int tiles, int most) {
  return std::max(2, std::min(most, budget / std::max(tiles, 1)));
}

// The PPA's angle for a turn as LVGL counts it: the PPA counts counter-clockwise (0, 90, 180, 270 as 0 to 3, the order
// of ppa_srm_rotation_angle_t and of ppa_guard::Angle), so LVGL's 90 is the PPA's 270 and the other way round. Written
// here once; the camera plugin's copy of its driver keeps its own (ppa_rotation_for_clockwise), as a copy must.
inline int ppa_angle(int turn) { return turn == 90 ? 3 : turn == 180 ? 2 : turn == 270 ? 1 : 0; }

#if defined(PICTURE_ENGINE_P4) && defined(SCREEN_PICTURES)
// The P4's: bursts of 64 bytes instead of ESP-IDF's 128, or the DSI bridge runs dry and the panel shows a frame of blue
// (lvgl/lvgl #9590); a full view's picture of at most 1 MB and a tile's of 384 KB, over what a 1280 x 800 JPEG of a busy
// camera is (150 to 250 KB) and a tile's room needs (docs/CAMERA.md, "Live on the P4 boards", 2026-10-10); four live
// tiles at once, measured on a reTerminal D1001 and a Guition 10.1 (docs/PLATFORM_PLAN.md 4.1), 24 pictures a second
// among them: 6 each, as before the budget.
constexpr Limits limits() { return {64, 1024 * 1024, 384 * 1024, 4, true, 0, 24, 1, 7}; }
#elif defined(PICTURE_ENGINE_S3) && defined(SCREEN_PICTURES)
// The S3's: no 2D engine, so no bursts; one live tile, its picture at most 128 KB (the app's JPEG of a 4-inch card is
// about 10 KB), decoded by the CPU off the glass on core 0, away from LVGL's; a full view's picture at most 256 KB, as
// the app sends it to fit the glass (a picture it would have to scale up is refused by blit, and the view keeps its
// stills), eight a second at most. Measured on a Guition 4848S040 (2026-10-28, docs/CAMERA.md "Live on an ESP32-S3"):
// each live tile costs about 11 KB of internal RAM for its socket's Wi-Fi and lwIP buffers, and two took it down to
// 16 KB, three to 3 KB, so one; its budget of 8 pictures a second is the one a second tile would share. With the tile
// decoding on core 1, LVGL's core was 38 % busy and LVGL refreshed 410 times in 10 s of dragging; on core 0, 23 % and
// 435. One stream of any kind at once: a full view that opened beside a live tile still ending took the internal RAM to
// 2 KB and the screen down with it (a tester's Guition 4848S040 with 7 pages, 2026-10-30, docs/CAMERA.md).
constexpr Limits limits() { return {0, 256 * 1024, 128 * 1024, 1, false, 8, 8, 0, 1}; }
#endif
#if (defined(PICTURE_ENGINE_P4) || defined(PICTURE_ENGINE_S3)) && defined(SCREEN_PICTURES)
// This screen's decoder takes JPEG: its questions name it first (runtime_tiles::picture_ask), the download gathers a
// JPEG answer whole (picture_fetch::Gather) and a P4's streams are JPEG (live_view.h).
constexpr bool JPEG = true;
// The formats the decoder takes whole, not row by row as it streams: named first in every question.
const std::vector<std::string> &whole_formats();
// The decoder made, on the main loop; true while it exists. The streams start it as they open.
bool start();
// Stills may be decoded (prepare_stills before): the decoder made, and LVGL holding the glass while it refreshes
// (glass::watch), so a decode in a download's task and LVGL's copy to the panel never run on the 2D-DMA at once.
bool ready();
// A buffer the decoder may read from (`got` what it is, rounded up), and one it may write to. free() them.
uint8_t *input(size_t bytes, size_t *got);
uint8_t *output(size_t bytes, size_t *got);
// A JPEG's size, and the decoded picture's stride and bytes (whole MCUs). False for a JPEG the decoder cannot read.
bool info(const uint8_t *data, size_t length, Still &out);
// A whole JPEG decoded into `into` (`into_size` bytes, at least `out.bytes` of info): RGB565 in LVGL's order. The caller
// holds the glass.
bool decode_into(const uint8_t *data, size_t length, uint8_t *into, size_t into_size);
// A whole JPEG decoded into a buffer of its own (free() it), the glass held meanwhile on a P4; nullptr before ready() or
// for a JPEG the decoder cannot read. From a download's task.
uint8_t *decode(const uint8_t *data, size_t length, Still &out);
#endif
#if (defined(PICTURE_ENGINE_P4) || defined(PICTURE_ENGINE_S3)) && defined(SCREEN_PICTURES)
// A client of the engine's copies, and its end: on a P4 a PPA client with the glass's bursts (glass.h), on an S3 a token.
Client client();
void drop(Client client);
// The copy: 0 when it is done, else ESP-IDF's error. The caller holds the glass. On a P4 the PPA's, through the guard,
// scaled and turned as the block says; on an S3 the CPU's, row by row, and only at AS_IS and turned 0 (the app sends a
// live tile's pictures at the card's size and turned as the glass is): anything else is refused.
int blit(Client client, const Block &block);
#else
inline Client client() { return nullptr; }
inline void drop(Client) {}
inline int blit(Client, const Block &) { return -1; }
#endif
#if !(defined(PICTURE_ENGINE_P4) || defined(PICTURE_ENGINE_S3)) || !defined(SCREEN_PICTURES)
constexpr Limits limits() { return {0, 0, 0, 0, false, 0, 0, 1, 0}; }
constexpr bool JPEG = false;
inline const std::vector<std::string> &whole_formats() {
  static const std::vector<std::string> none;
  return none;
}
inline bool start() { return false; }
inline bool ready() { return false; }
inline uint8_t *input(size_t, size_t *got) {
  if (got) *got = 0;
  return nullptr;
}
inline uint8_t *output(size_t, size_t *got) {
  if (got) *got = 0;
  return nullptr;
}
inline bool info(const uint8_t *, size_t, Still &) { return false; }
inline bool decode_into(const uint8_t *, size_t, uint8_t *, size_t) { return false; }
inline uint8_t *decode(const uint8_t *, size_t, Still &) { return nullptr; }
#endif

}  // namespace picture_engine
