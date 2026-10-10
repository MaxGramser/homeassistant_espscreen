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
#include <cstddef>
#include <cstdint>
#include <cstring>
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
// What the screen asks the app for: the room below the top bar, "1280x720".
inline std::string box_text(const Rect &area) { return std::to_string(area.w) + "x" + std::to_string(area.h); }

// ---- The task, on a P4 (live_view.cpp); elsewhere nothing streams ----
enum class Event : uint8_t {
  NONE,
  FIRST,   // the first picture is on the glass
  FAILED,  // the stream broke, or never came: the view asks again
  TURNED,  // the glass was turned meanwhile: the view asks again for its new shape
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
// Whether this screen streams: a P4 whose panel ESP-IDF made with an RGB565 frame buffer, and LVGL bound to say how
// the glass is turned (smart_display/__init__.py binds it).
bool available();
// Streams `url` into `area`, the screen as LVGL lays it out. False when it cannot start.
bool start(const std::string &url, const Rect &area);
// Ends the stream. Returns once nothing of it writes the glass any more, so LVGL may draw there again at once.
void stop();
bool running();
// The main loop, every 50 ms: frees what a finished task left and says what happened.
Event tick();
#else
inline bool available() { return false; }
inline bool start(const std::string &, const Rect &) { return false; }
inline void stop() {}
inline bool running() { return false; }
inline Event tick() { return Event::NONE; }
#endif

}  // namespace live_view
