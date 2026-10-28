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
// The panel's handle comes from ESP-IDF as ESPHome makes it (a linker wrap of esp_lcd_new_panel_dpi, glass_dsi.cpp),
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

#include "audio_owner.h"
#include "glass.h"
#include "picture_engine.h"
#include "picture_fetch.h"
// USE_LIVE_VIEW comes with ESPHome's defines (smart_display/__init__.py); a PC test has none and builds without it.
#if __has_include("esphome/core/defines.h")
#include "esphome/core/defines.h"
#endif

namespace live_view {

constexpr size_t MAX_HEAD = 2048;    // the answer's head or a part's head
constexpr uint32_t QUIET_MS = 6000;  // no byte for this long: the stream is gone
constexpr uint32_t REPORT_MS = 10000;
// A stream that failed this often for one opening of the view gives way to the stills of every board.
constexpr uint8_t TRIES = 3;
// A full view's sound: 16-bit mono at this rate (the board's resampler makes it its bus's), in parts of at most
// SOUND_PART bytes, and SOUND_BUFFER of it held between the stream and the speaker (a second). The buffer is room for a
// burst, not a delay: after a hiccup the app sends what it held back at once (up to 1.8 s of a camera's sound on a
// reTerminal D1001, 2026-10-25), and the main loop that catches up (SOUND_HIGH) comes by only every tick, about 50 ms
// in a ring's view. A burst can be larger than any buffer here, so a part that finds it full is still left out whole
// (173 in a ring of five minutes with a second, 227 and 237 with half a second): the buffer holds what fits, the main
// loop leaves out the oldest of it.
constexpr uint32_t SOUND_RATE = 16000;
constexpr size_t SOUND_PART = 4096;
constexpr size_t SOUND_BUFFER = 32768;
// The sound keeps up with the picture: with more than SOUND_HIGH held (a burst after a hiccup in the stream) the oldest
// goes, down to SOUND_LOW, which is also what the speaker waits for before it starts; the app's own queue drops its
// oldest the same way. Without it the sound would stay up to the buffer's second behind the picture.
constexpr size_t SOUND_LOW = SOUND_RATE * 2 * 150 / 1000;   // 150 ms
constexpr size_t SOUND_HIGH = SOUND_RATE * 2 * 400 / 1000;  // 400 ms
static_assert(SOUND_PART % 2 == 0 && SOUND_BUFFER % 2 == 0 && SOUND_LOW % 2 == 0 && SOUND_HIGH % 2 == 0,
              "the sound moves in whole samples, two bytes each");
static_assert(SOUND_LOW < SOUND_HIGH && SOUND_HIGH < SOUND_BUFFER, "the sound catches up before its buffer runs full");

// A link to a stream rather than to a still: the app serves both on its camera port, a still as .bmp.
inline bool is_stream(const std::string &url) {
  const size_t end = url.find_first_of("?#");
  const std::string path = url.substr(0, end);
  return path.size() > 6 && path.compare(path.size() - 6, 6, ".mjpeg") == 0;
}

// ---- The stream: plain HTTP/1.0 (no chunks), then parts, each with a head that names its Content-Length ----
// feed() takes the bytes as they come, in any pieces. A part is a picture (image/jpeg) or, for a full view with sound,
// a piece of the camera's sound (audio/L16, 16-bit mono at SOUND_RATE). Its bytes go where `room(length, audio)` says
// (nullptr: skip that part, one the task cannot take now) and `done(length, audio)` follows once they are all there.
// It returns false once the stream is no good: an answer other than 200, a head without its length or too long, a part
// over `most` bytes (the engine's picture limit, picture_engine::limits(); 0 takes none).
class Reader {
 public:
  explicit Reader(size_t most) : most_(most) {}
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
        if (!h.has_length || h.content_length == 0 || h.content_length > this->most_) {
          this->broken_ = true;
          continue;
        }
        this->need_ = h.content_length;
        this->got_ = 0;
        this->audio_ = h.audio;
        this->still_ = h.still;
        this->has_made_ = h.has_made;
        this->made_ = h.made;
        this->room_ = room(this->need_, this->audio_);
        this->in_body_ = true;
      } else {
        const size_t take = std::min(size, this->need_ - this->got_);
        if (this->room_) memcpy(this->room_ + this->got_, data, take);
        this->got_ += take;
        data += take;
        size -= take;
        if (this->got_ == this->need_) {
          this->in_body_ = false;
          if (this->room_) done(this->need_, this->audio_);
          this->room_ = nullptr;
          ++this->parts_;
        }
      }
    }
    return !this->broken_;
  }
  int status() const { return this->status_; }
  uint32_t parts() const { return this->parts_; }
  // Whether the part `done` was told of is the camera's still from before its stream came (X-Picture: still).
  bool still() const { return this->still_; }
  // And when the app made it (X-Made, its own milliseconds), when it said.
  bool has_made() const { return this->has_made_; }
  uint32_t made() const { return this->made_; }

 private:
  std::string head_;
  size_t most_ = 0;
  bool answered_ = false, in_body_ = false, broken_ = false, audio_ = false, still_ = false, has_made_ = false;
  uint32_t made_ = 0;
  int status_ = 0;
  size_t need_ = 0, got_ = 0;
  uint8_t *room_ = nullptr;
  uint32_t parts_ = 0;
};

// ---- Where things lie ----
// A rectangle of the screen as LVGL lays it out, and where it lies on a turned panel: the glass's (glass.h).
using glass::Rect;
using glass::on_panel;
// What the screen asks the app for: the room it has, "1280x720".
inline std::string box_text(const Rect &area) { return std::to_string(area.w) + "x" + std::to_string(area.h); }

// ---- A live tile (firmware dev): the picture fills its card, rounded, shaded under its name, the name over it ----
// A tile's still comes from the app with all of that baked in (picture_paint.py); a live tile's pictures come plain, at the
// card's size, and the screen lays the same over each of them before it reaches the glass, so the app on a Raspberry
// Pi does nothing per picture a screen can do itself. The shade is picture_paint's: the bottom FADE_PERCENT of the card,
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
  // The loader in the card's top right corner until the camera is live ("Until it is live", below): `loader` pixels
  // across, `loader_margin` from the card's edges, its ring `loader_arc` wide; 0: none.
  int loader = 0, loader_margin = 0, loader_arc = 0;
  uint16_t loader_ring = 0, loader_turn = 0;  // RGB565: the ring, and the arc that turns on it
};
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
// Everything a live tile lays over its picture, in the order picture_paint.py does it: the shade, the corners, the name.
inline void compose(uint16_t *px, int stride, int w, int h, const Look &look) {
  if (!look.tile) return;
  if (look.fade) fade(px, stride, w, h);
  if (look.radius > 0) round_corners(px, stride, w, h, look.radius, look.ground);
  if (look.name && look.name_w > 0 && look.name_h > 0)
    lay_over(px, stride, w, h, look.name, look.name_stride ? look.name_stride : look.name_w, look.name_x, look.name_y,
             look.name_w, look.name_h);
}

// ---- Until it is live ----
// A camera's stream starts with its stills: the app sends the camera's still at once, again every few seconds, until
// Home Assistant's WebRTC brings its first frame (camera_source.py), and marks each such part X-Picture: still. While those
// show, a live tile turns the firmware's spinner (runtime_tiles::spinner_create, LVGL's 900 ms turn) small in its top
// right corner, on a round shade so it reads over any picture; the full view turns it in its top bar (runtime_tiles,
// camera_warm). The first picture without the mark ends it (Event::LIVE). An app that marks nothing is live at once.
constexpr uint32_t LOADER_TURN_MS = 900;  // one turn, as lv_spinner_set_anim_params(900, 200)
constexpr uint32_t LOADER_STEP_MS = 50;   // the stream's task draws it again this often
constexpr unsigned LOADER_SHADE = 110;    // the round shade under it, of 255 black
constexpr float LOADER_ARC = 200;         // the arc's length in degrees, as LVGL's spinner
// Where the loader lies in a card of w x h: its square's top left corner; false when the card is too small for it.
inline bool loader_spot(const Look &look, int w, int h, int &x, int &y) {
  if (!look.tile || look.loader <= 0 || look.loader + 2 * look.loader_margin > std::min(w, h)) return false;
  x = w - look.loader_margin - look.loader;
  y = look.loader_margin;
  return true;
}
// The loader at `ms` into its turn, drawn over the pixels at x, y (a square of look.loader): the shade, the ring, and
// the arc as LVGL's spinner moves it: its end turns evenly, its start eases in and out behind it, both ends rounded.
inline void draw_loader(uint16_t *px, int stride, int x, int y, const Look &look, uint32_t ms) {
  const int size = look.loader;
  const float r = size / 2.0f;
  const float outer = r - std::max(2.0f, size / 7.0f), inner = outer - look.loader_arc;
  const float mid = (outer + inner) / 2, half = (outer - inner) / 2;
  const float p = static_cast<float>(ms % LOADER_TURN_MS) / LOADER_TURN_MS;
  const float eased = p * p * (3 - 2 * p);
  const float start = 360 * eased, end = LOADER_ARC + 360 * p;  // degrees, clockwise from three o'clock
  const float length = end - start;
  constexpr float RAD = 3.14159265f / 180;
  const float sx = mid * std::cos(start * RAD), sy = mid * std::sin(start * RAD);
  const float ex = mid * std::cos(end * RAD), ey = mid * std::sin(end * RAD);
  auto clamp01 = [](float v) { return v <= 0 ? 0.0f : v >= 1 ? 1.0f : v; };
  for (int j = 0; j < size; ++j) {
    for (int i = 0; i < size; ++i) {
      const float dx = i + 0.5f - r, dy = j + 0.5f - r;
      const float d = std::sqrt(dx * dx + dy * dy);
      const float shade = clamp01(r - d + 0.5f);
      if (shade <= 0) continue;
      uint16_t &p565 = px[static_cast<size_t>(y + j) * stride + x + i];
      p565 = blend(p565, 0, static_cast<unsigned>(shade * LOADER_SHADE));
      const float band = clamp01(std::min(outer - d, d - inner) + 0.5f);
      if (band > 0) p565 = blend(p565, look.loader_ring, static_cast<unsigned>(band * 255));
      float angle = std::atan2(dy, dx) / RAD - start;
      while (angle < 0) angle += 360;
      while (angle >= 360) angle -= 360;
      float on = angle <= length ? band : 0;
      const float cap_s = std::sqrt((dx - sx) * (dx - sx) + (dy - sy) * (dy - sy));
      const float cap_e = std::sqrt((dx - ex) * (dx - ex) + (dy - ey) * (dy - ey));
      on = std::max(on, clamp01(half - std::min(cap_s, cap_e) + 0.5f));
      if (on > 0) p565 = blend(p565, look.loader_turn, static_cast<unsigned>(on * 255));
    }
  }
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
  SOUND,   // its first sound came (a full view with sound): its owner shows the mute key
  LIVE,    // its first live picture is on the glass, after FIRST (or with it): no more stills ("Until it is live")
};
// A P4 (USE_LIVE_VIEW, smart_display/__init__.py) that shows pictures at all (SCREEN_PICTURES, features/camera.yaml).
// Its stills come as JPEG too, through the engine (picture_engine.h, docs/PICTURES.md "Formats"); LVGL is bound to the
// glass at boot (glass::bind, smart_display/__init__.py).
#if defined(USE_LIVE_VIEW) && defined(SCREEN_PICTURES)
// Whether this screen streams: a P4 whose panel ESP-IDF made with an RGB565 frame buffer, and LVGL bound.
bool available();
// Streams `url` into `area`, the screen as LVGL lays it out, looking as `look` says. -1 when it cannot start (no room
// for another stream, no memory): its owner shows its stills. `sound`: the stream may carry the camera's sound, which
// goes to the board's speaker (bind_speaker) unless muted, claimed from the audio owner (audio_owner.h) in `role`:
// CAMERA_SOUND for a camera someone opened, DOORBELL for the view a ring opened, which nothing takes the speaker from.
Handle open(const std::string &url, const Rect &area, const Look &look = Look{}, bool sound = false,
            audio_owner::Role role = audio_owner::Role::CAMERA_SOUND);
// Whether this board plays a live camera's sound: a speaker is bound (features/audio.yaml).
bool has_speaker();
// A stream's sound off or on again.
void mute(Handle handle, bool muted);
// Ends a stream. Returns once nothing of it writes the glass any more, so LVGL may draw there again at once; its ENDED
// comes with the next tick.
void close(Handle handle);
// The main loop, every 50 ms: frees what finished tasks left and tells each stream's owner what happened.
void tick(const std::function<void(Handle, Event)> &tell);
// How often the panel ran dry since boot (a frame of blue: glass.h, "The panel's share of the memory bus").
uint32_t misses();
// What the streams that run hold of the board's memory, about (docs/PICTURES.md: the streams take their share of the one
// picture budget while they run): each stream's input and its decoded picture of its room, from what the main loop
// set when it opened, so never read under a task.
size_t held_bytes();
#else
inline size_t held_bytes() { return 0; }
inline bool available() { return false; }
inline Handle open(const std::string &, const Rect &, const Look & = Look{}, bool = false,
                   audio_owner::Role = audio_owner::Role::CAMERA_SOUND) {
  return -1;
}
inline bool has_speaker() { return false; }
inline void mute(Handle, bool) {}
inline void close(Handle) {}
inline void tick(const std::function<void(Handle, Event)> &) {}
inline uint32_t misses() { return 0; }
#endif

}  // namespace live_view

// The speaker a live camera's sound plays on (features/audio.yaml binds the board's ts_speaker at boot); a board
// without the live view takes it and does nothing with it.
#ifdef USE_SPEAKER
namespace esphome::speaker {
class Speaker;
}
namespace live_view {
#if defined(USE_LIVE_VIEW) && defined(SCREEN_PICTURES)
void bind_speaker(esphome::speaker::Speaker *speaker);
#else
inline void bind_speaker(esphome::speaker::Speaker *) {}
#endif
}  // namespace live_view
#endif
