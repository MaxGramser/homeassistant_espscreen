#pragma once
// A camera live, full screen, on the ESP32-P4 boards (docs/CAMERA.md, "Live on the P4 boards").
//
// A camera opened full screen refreshes its still every four seconds on every board (camera_view.h). A P4 can do far
// more: its hardware JPEG decoder makes a 1280 x 800 picture in 11 ms, and with the larger TCP window the P4 boards
// build with (smart_display/__init__.py) its Wi-Fi through the C6 brings 2 to 2.6 MB/s. Measured on the reTerminal
// D1001 (2026-10-10): 34 pictures a second of 64 KB, 18 to 20 of a real camera's 130 KB, and a picture on the glass
// 66 ms after Home Assistant made it. Drawn through LVGL the same pictures came at 4 a second: a whole-screen image
// costs LVGL 200 ms a frame, with touch waiting meanwhile.
//
// So the live picture goes past LVGL. ESP Screen Manager streams JPEGs (multipart/x-mixed-replace, one part per
// picture with its Content-Length, never faster than the screen takes them); a task of its own reads them, decodes
// each with the hardware decoder and has the PPA copy it into the panel's frame buffer, turned the way LVGL turns its
// own drawing (ESPHome's LvglComponent::draw_buffer_), and scaled to fill the room it has. The picture lies below the top bar, so the back key and the
// name stay LVGL's to draw: nothing of LVGL lies under the picture, and LVGL never draws there while it streams.
// The panel's handle comes from ESP-IDF as ESPHome makes it (a linker wrap of esp_lcd_new_panel_dpi, live_view.cpp),
// so every display platform on a P4 serves, and nothing of ESPHome's own classes is read.
//
// What a PC can check is here, free of sockets, LVGL and ESP-IDF (tests/test_live_view.cpp): the stream's framing,
// where a rectangle of the screen lies on the panel, and where a picture goes. live_view.cpp has the task.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>
#include <string>

#include "picture_fetch.h"
// USE_LIVE_VIEW comes with ESPHome's defines (smart_display/__init__.py); a PC test has none and builds without it.
#if __has_include("esphome/core/defines.h")
#include "esphome/core/defines.h"
#endif

namespace live_view {

// A picture's part is never larger than this (a 1280 x 800 JPEG of a busy camera is 150 to 250 KB).
constexpr size_t MAX_PICTURE = 1024 * 1024;
constexpr size_t MAX_HEAD = 2048;    // the answer's head or a part's head
constexpr uint32_t QUIET_MS = 6000;  // no byte for this long: the stream is gone
constexpr uint32_t REPORT_MS = 10000;
// A stream that failed this often for one opening of the view gives way to the stills of every board.
constexpr uint8_t TRIES = 3;
constexpr size_t TILE_PICTURE = 384 * 1024;  // a tile's picture is smaller (MAX_PICTURE is the full view's)

// A link to a stream rather than to a still: the app serves both on its camera port, a still as .bmp.
inline bool is_stream(const std::string &url) {
  const size_t end = url.find_first_of("?#");
  const std::string path = url.substr(0, end);
  return path.size() > 6 && path.compare(path.size() - 6, 6, ".mjpeg") == 0;
}

// ---- The stream: plain HTTP/1.0 (no chunks), then parts, each with a head that names its Content-Length ----
// feed() takes the bytes as they come, in any pieces. A part's bytes go where `room(length)` says (nullptr: skip that
// part, a picture the task cannot take now) and `done(length)` follows once they are all there. It returns false once
// the stream is no good: an answer other than 200, a head without its length or too long, a part over MAX_PICTURE.
class Reader {
 public:
  template<typename Room, typename Done> bool feed(const uint8_t *data, size_t size, Room room, Done done) {
    while (size > 0 && !this->broken_) {
      if (!this->in_body_) {
        const size_t take = std::min(size, MAX_HEAD - this->head_.size());
        this->head_.append(reinterpret_cast<const char *>(data), take);
        const auto h = picture_fetch::parse_head(this->head_.data(), this->head_.size());
        if (!h.complete) {
          if (this->head_.size() >= MAX_HEAD) this->broken_ = true;
          data += take;
          size -= take;
          continue;
        }
        // What of this piece lies past the head belongs to what follows.
        const size_t used = take - (this->head_.size() - h.length);
        data += used;
        size -= used;
        this->head_.clear();
        if (!this->answered_) {
          this->answered_ = true;
          this->status_ = h.status;
          if (h.status != 200) this->broken_ = true;
          continue;
        }
        if (!h.has_length || h.content_length == 0 || h.content_length > MAX_PICTURE) {
          this->broken_ = true;
          continue;
        }
        this->need_ = h.content_length;
        this->got_ = 0;
        this->room_ = room(this->need_);
        this->in_body_ = true;
      } else {
        const size_t take = std::min(size, this->need_ - this->got_);
        if (this->room_) memcpy(this->room_ + this->got_, data, take);
        this->got_ += take;
        data += take;
        size -= take;
        if (this->got_ == this->need_) {
          this->in_body_ = false;
          if (this->room_) done(this->need_);
          this->room_ = nullptr;
          ++this->parts_;
        }
      }
    }
    return !this->broken_;
  }
  int status() const { return this->status_; }
  uint32_t parts() const { return this->parts_; }

 private:
  std::string head_;
  bool answered_ = false, in_body_ = false, broken_ = false;
  int status_ = 0;
  size_t need_ = 0, got_ = 0;
  uint8_t *room_ = nullptr;
  uint32_t parts_ = 0;
};

// ---- Where things lie ----
struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  bool empty() const { return w <= 0 || h <= 0; }
  bool operator==(const Rect &o) const { return x == o.x && y == o.y && w == o.w && h == o.h; }
};
// Where a rectangle of the screen as LVGL lays it out lies on a panel of pw x ph, LVGL turned `turn` degrees clockwise:
// exactly ESPHome's own sums for a flushed area (LvglComponent::draw_buffer_), so a picture lands where LVGL would
// have drawn it.
inline Rect on_panel(const Rect &r, int turn, int pw, int ph) {
  switch (turn) {
    case 90: return {pw - r.y - r.h, r.x, r.h, r.w};
    case 180: return {pw - r.x - r.w, ph - r.y - r.h, r.w, r.h};
    case 270: return {r.y, ph - r.x - r.w, r.h, r.w};
    default: return r;
  }
}
// The PPA scales in sixteenths (ESP-IDF's ppa_srm.c): a block of `n` pixels at `sixteenths` / 16 comes out this long.
inline int scaled(int n, int sixteenths) { return (sixteenths / 16) * n + (sixteenths % 16) * n / 16; }
// A picture of w x h as large as it fits in `area`, its proportions kept, in the middle: the app sends the camera's own
// size where that is smaller than the glass (a substream of 512 x 288 costs Home Assistant a fraction of a 1280 x 720
// JPEG), and the PPA scales it on its way to the frame buffer. `sixteenths` is the scale for the PPA; the rectangle is
// empty when even 1/16 does not fit, or for a picture larger than the screen takes (MAX_SIDE).
constexpr int MAX_SIDE = 2048;
constexpr int MAX_SCALE = 16 * 16;  // sixteen times: a 80 x 50 picture still fills the glass
inline Rect fit(int w, int h, const Rect &area, int &sixteenths) {
  sixteenths = 0;
  if (w <= 0 || h <= 0 || w > MAX_SIDE || h > MAX_SIDE || area.empty()) return {};
  int s = std::min(16 * area.w / w, 16 * area.h / h);
  s = std::min(s, MAX_SCALE - 1);
  // The PPA's sums floor each part on their own: a step back where they round a pixel over the area.
  while (s > 0 && (scaled(w, s) > area.w || scaled(h, s) > area.h)) --s;
  if (s <= 0) return {};
  sixteenths = s;
  const int fw = scaled(w, s), fh = scaled(h, s);
  return {area.x + (area.w - fw) / 2, area.y + (area.h - fh) / 2, fw, fh};
}
// What the screen asks the app for: the room it has, "1280x720".
inline std::string box_text(const Rect &area) { return std::to_string(area.w) + "x" + std::to_string(area.h); }

// ---- A live tile (firmware dev): the picture fills its card, rounded, shaded under its name, the name over it ----
// A tile's still comes from the app with all of that baked in (tile_art.py); a live tile's pictures come plain, at the
// card's size, and the screen lays the same over each of them before it reaches the glass, so the app on a Raspberry
// Pi does nothing per picture a screen can do itself. The shade is tile_art's: the bottom FADE_PERCENT of the card,
// from clear to FADE_DEPTH / 255 black.
constexpr int FADE_PERCENT = 42;
constexpr int FADE_DEPTH = 150;
struct Look {
  bool tile = false;     // false: the full view, whose picture fills its room and has nothing over it
  bool contain = false;  // the whole picture in the middle of the card on black; else it fills the card, cut to it
  int radius = 0;        // the card's corners, over `ground` (RGB565, the page behind the card)
  uint16_t ground = 0;
  bool fade = false;     // the shade under the name
  // The name as LVGL draws it (ARGB8888, w x h with `stride` pixels a row), at x, y on the card; copied at open().
  const uint32_t *name = nullptr;
  int name_x = 0, name_y = 0, name_w = 0, name_h = 0, name_stride = 0;
};
// Where a picture of w x h goes in a card of cw x ch: the PPA reads the block in_* of it and writes out_* at
// `sixteenths` / 16. Filling: the middle of the picture, scaled up only when it is smaller than the card. Whole
// (contain): all of it, as large as fits, in the middle.
struct Cut {
  int in_x = 0, in_y = 0, in_w = 0, in_h = 0;
  int out_x = 0, out_y = 0, out_w = 0, out_h = 0;
  int sixteenths = 0;
  bool ok = false;
  bool covers(int cw, int ch) const { return ok && out_x == 0 && out_y == 0 && out_w == cw && out_h == ch; }
};
inline Cut cut(int w, int h, int cw, int ch, bool contain) {
  Cut c;
  if (w <= 0 || h <= 0 || cw <= 0 || ch <= 0 || w > MAX_SIDE || h > MAX_SIDE) return c;
  if (contain) {
    const Rect r = fit(w, h, Rect{0, 0, cw, ch}, c.sixteenths);
    if (r.empty()) return c;
    c.in_w = w;
    c.in_h = h;
    c.out_x = r.x, c.out_y = r.y, c.out_w = r.w, c.out_h = r.h;
    c.ok = true;
    return c;
  }
  // The least scale at which the picture covers the card: 16 (as it is) for a picture the app sent at the card's size.
  int s = 16;
  while (s < MAX_SCALE - 1 && (scaled(w, s) < cw || scaled(h, s) < ch)) ++s;
  while (s > 1 && scaled(w, s - 1) >= cw && scaled(h, s - 1) >= ch) --s;
  if (scaled(w, s) < cw || scaled(h, s) < ch) return c;
  // The largest block of the picture that, scaled, stays within the card.
  auto block = [s](int n, int room) {
    int in = std::min(n, (room * 16 + s - 1) / s);
    while (in > 1 && scaled(in, s) > room) --in;
    return in;
  };
  c.sixteenths = s;
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
// RGB565 in the chip's own byte order (as LVGL's and the decoder's), and LVGL's ARGB8888 (0xAARRGGBB).
inline uint16_t rgb565(uint32_t rgb) {
  return static_cast<uint16_t>(((rgb >> 8) & 0xF800) | ((rgb >> 5) & 0x07E0) | ((rgb >> 3) & 0x001F));
}
inline uint16_t blend(uint16_t under, uint16_t over, unsigned alpha) {  // alpha 0..255
  if (alpha >= 255) return over;
  if (alpha == 0) return under;
  const unsigned a = alpha + 1, b = 256 - a;
  const unsigned r = (((over >> 11) & 31) * a + ((under >> 11) & 31) * b) >> 8;
  const unsigned g = (((over >> 5) & 63) * a + ((under >> 5) & 63) * b) >> 8;
  const unsigned bl = ((over & 31) * a + (under & 31) * b) >> 8;
  return static_cast<uint16_t>(r << 11 | g << 5 | bl);
}
// The shade under a name: the bottom FADE_PERCENT of the card darkens row by row to FADE_DEPTH / 255 black.
inline void fade(uint16_t *px, int stride, int w, int h) {
  const int rows = std::max(1, (h * FADE_PERCENT + 50) / 100);
  for (int i = 0; i < rows; ++i) {
    const unsigned depth = static_cast<unsigned>(FADE_DEPTH * (i + 1) / rows);  // 0 at the top of the shade
    uint16_t *row = px + static_cast<size_t>(h - rows + i) * stride;
    for (int x = 0; x < w; ++x) row[x] = blend(row[x], 0, depth);
  }
}
// The card's rounded corners: what lies outside a circle of `radius` in each corner becomes `ground`, its edge
// smoothed by how much of each pixel lies outside.
inline void round_corners(uint16_t *px, int stride, int w, int h, int radius, uint16_t ground) {
  radius = std::min(radius, std::min(w, h) / 2);
  for (int y = 0; y < radius; ++y) {
    for (int x = 0; x < radius; ++x) {
      const float dx = radius - (x + 0.5f), dy = radius - (y + 0.5f);
      const float outside = std::sqrt(dx * dx + dy * dy) - radius + 0.5f;  // 0: inside, 1: wholly outside
      if (outside <= 0) continue;
      const unsigned a = outside >= 1 ? 255 : static_cast<unsigned>(outside * 255);
      uint16_t *corners[4] = {px + static_cast<size_t>(y) * stride + x, px + static_cast<size_t>(y) * stride + (w - 1 - x),
                              px + static_cast<size_t>(h - 1 - y) * stride + x,
                              px + static_cast<size_t>(h - 1 - y) * stride + (w - 1 - x)};
      for (auto *p : corners) *p = blend(*p, ground, a);
    }
  }
}
// LVGL's drawing of the name (ARGB8888, sw x sh, `sstride` pixels a row) laid over the picture at x, y.
inline void lay_over(uint16_t *px, int stride, int w, int h, const uint32_t *argb, int sstride, int x, int y, int sw,
                     int sh) {
  for (int j = 0; j < sh; ++j) {
    const int py = y + j;
    if (py < 0 || py >= h) continue;
    for (int i = 0; i < sw; ++i) {
      const int qx = x + i;
      if (qx < 0 || qx >= w) continue;
      const uint32_t c = argb[static_cast<size_t>(j) * sstride + i];
      const unsigned a = c >> 24;
      if (a) px[static_cast<size_t>(py) * stride + qx] = blend(px[static_cast<size_t>(py) * stride + qx], rgb565(c), a);
    }
  }
}
// Everything a live tile lays over its picture, in the order tile_art.py does it: the shade, the corners, the name.
inline void compose(uint16_t *px, int stride, int w, int h, const Look &look) {
  if (!look.tile) return;
  if (look.fade) fade(px, stride, w, h);
  if (look.radius > 0) round_corners(px, stride, w, h, look.radius, look.ground);
  if (look.name && look.name_w > 0 && look.name_h > 0)
    lay_over(px, stride, w, h, look.name, look.name_stride ? look.name_stride : look.name_w, look.name_x, look.name_y,
             look.name_w, look.name_h);
}

// ---- The streams, on a P4 (live_view.cpp); elsewhere nothing streams ----
// The full view and the live tiles of the page on the glass, each in a task of its own.
constexpr int MAX_STREAMS = 7;
using Handle = int;  // -1: none
enum class Event : uint8_t {
  NONE,
  FIRST,   // its first picture is on the glass
  FAILED,  // it broke, or never came: its owner asks again
  TURNED,  // the glass was turned meanwhile: its owner asks again for its new shape
  ENDED,   // closed by its owner, and gone
};
// A P4 (USE_LIVE_VIEW, smart_display/__init__.py) that shows pictures at all (SCREEN_PICTURES, features/camera.yaml).
#if defined(USE_LIVE_VIEW) && defined(SCREEN_PICTURES)
}  // namespace live_view
namespace esphome::lvgl {
class LvglComponent;
}
namespace live_view {
// LVGL, which says how the glass is turned (smart_display/__init__.py binds it at boot).
void bind(esphome::lvgl::LvglComponent *lvgl);
// Whether this screen streams: a P4 whose panel ESP-IDF made with an RGB565 frame buffer, and LVGL bound.
bool available();
// Streams `url` into `area`, the screen as LVGL lays it out, looking as `look` says. -1 when it cannot start (no room
// for another stream, no memory): its owner shows its stills.
Handle open(const std::string &url, const Rect &area, const Look &look = Look{});
// Ends a stream. Returns once nothing of it writes the glass any more, so LVGL may draw there again at once; its ENDED
// comes with the next tick.
void close(Handle handle);
// The main loop, every 50 ms: frees what finished tasks left and tells each stream's owner what happened.
void tick(const std::function<void(Handle, Event)> &tell);
#else
inline bool available() { return false; }
inline Handle open(const std::string &, const Rect &, const Look & = Look{}) { return -1; }
inline void close(Handle) {}
inline void tick(const std::function<void(Handle, Event)> &) {}
#endif

}  // namespace live_view
