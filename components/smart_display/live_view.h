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
// where a rectangle of the screen lies on the panel, and where a picture goes; and the rules of its sound
// (tests/test_live_sound.cpp). live_view.cpp has the task.
#include <algorithm>
#include <atomic>
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
constexpr size_t SOUND_BUFFER = 49152;  // 1.5 s at 16 kHz mono
// The sound keeps up with the picture: with more than SOUND_HIGH held (a burst after a hiccup in the stream) the oldest
// goes, down to SOUND_LOW, which is also what the speaker waits for before it starts; the app's own queue drops its
// oldest the same way. Without it the sound would stay up to the buffer's second behind the picture.
// 400 and 1200 ms (150 and 400 until 2026-10-29): the app's push stream puts a part of sound behind each picture, and on
// the way through Home Assistant (go2rtc, aiortc, the pictures made) a part waited up to 635 ms by the viewer's own
// count where the window was 400, so it was cut and the buffer ran dry in turns: small snippets out of joint, the same
// from a screen's camera and from an EZVIZ (Max, both screens). A quarter of a second more latency, which Max takes for
// sound that stays whole ("200 ms extra is fine, 3 s is not").
constexpr size_t SOUND_LOW = SOUND_RATE * 2 * 400 / 1000;    // 400 ms
constexpr size_t SOUND_HIGH = SOUND_RATE * 2 * 1200 / 1000;  // 1200 ms
// In a conversation (the part's X-Sound: talk) sound is someone speaking to you: 200 ms of run-up. Above a second the oldest
// goes. Measured on a call from a reTerminal D1001 to a Guition 10.1 (2026-11-10): with 600 ms, 5.2 s of 38 s of sound was thrown
// away in pieces of up to 2 s, as the Wi-Fi brings sound in bursts of up to a second while pictures and sound share the link.
// Clean sound goes first: a voice up to a second late is fine, and a voice with holes is not (docs/CALLS.md, "The voice").
constexpr size_t SOUND_TALK_LOW = SOUND_RATE * 2 * 200 / 1000;    // 200 ms
constexpr size_t SOUND_TALK_HIGH = SOUND_RATE * 2 * 1000 / 1000;  // 1 s
// How long a conversation's sound may be gone before it takes a new run-up: a moment's empty buffer is normal, the speaker
// has its own to play from, and a run-up at every one is a hole of 200 ms each time.
constexpr uint32_t SOUND_TALK_GONE_MS = 400;
static_assert(SOUND_TALK_LOW % 2 == 0 && SOUND_TALK_HIGH % 2 == 0 && SOUND_TALK_LOW < SOUND_TALK_HIGH, "whole samples");
static_assert(SOUND_PART % 2 == 0 && SOUND_BUFFER % 2 == 0 && SOUND_LOW % 2 == 0 && SOUND_HIGH % 2 == 0,
              "the sound moves in whole samples, two bytes each");
static_assert(SOUND_LOW < SOUND_HIGH && SOUND_HIGH < SOUND_BUFFER, "the sound catches up before its buffer runs full");

// ---- A stream's sound, its rules pure (tests/test_live_sound.cpp drives them with a buffer, a speaker and an owner of
// its own); live_view.cpp hands them FreeRTOS's stream buffer, the board's speaker and audio_owner::the() ----

// What the stream's task puts into the sound buffer of a part of `length` bytes, with `space` bytes free in it: nothing
// while the sound is held back (muted, or the speaker someone else's), and whole samples only, all of them or none.
// The buffer, every piece read from it and every write to the speaker stay on a sample's first byte: a speaker one byte
// off plays seconds of full-scale noise (a ring on a reTerminal D1001, 2026-10-25), and a part cut to the room left was
// an odd count that put every later sample a byte off. `full`: a part left out for want of room, counted.
struct SoundPart {
  size_t send = 0;
  bool full = false;
};
inline SoundPart sound_part(size_t length, size_t space, bool held_back) {
  if (held_back) return {};
  const size_t whole = length & ~static_cast<size_t>(1);
  if (space < whole) return {0, true};
  return {whole, false};
}
// Whether the main loop hands the sound to the speaker now: not once the stream stops, and held back while muted or
// while the speaker is someone else's, as in the task.
inline bool sound_on(bool stopping, bool muted, bool yielded) { return !stopping && !muted && !yielded; }

// The main loop's half: from the buffer to the speaker, every tick. It starts once SOUND_LOW waits (so it does not
// stutter at its first gap), and after the buffer ran dry waits for that again instead of playing each part as it
// trickles in (snippets out of joint, 2026-10-29); a conversation's sound (X-Sound: talk) has the smaller run-up and is
// only dry once it has been gone SOUND_TALK_GONE_MS. Behind the picture (more than SOUND_HIGH held, a burst after a
// hiccup in the stream) the oldest goes, down to SOUND_LOW, and the rest of the piece the speaker had not taken first:
// before the speaker is fed, so a speaker that is full does not hold the catching up back until the buffer runs full.
// Whole samples throughout: a piece goes only from a sample's first byte, and a write the speaker took an odd number of
// bytes of goes on from the very next byte.
// `Buffer`: held() the bytes waiting, take(into, most) takes up to `most` of them. `Speaker`: start(), stop(), and
// play(data, n), which returns what it took. `piece` holds SOUND_PART bytes.
struct SoundPump {
  bool speaking = false, dry = false;
  size_t piece_left = 0, piece_at = 0;  // what the speaker took part of, the rest of it next tick
  uint32_t fed_ms = 0;                  // when the speaker last got a piece
  // For the stream's last line: the times the oldest was left out and how much, the times the buffer ran dry while
  // speaking, and writes the speaker took an odd number of bytes of (which should be none).
  uint32_t caught_up = 0, caught_up_bytes = 0, ran_dry = 0, odd_taken = 0;

  template<typename Buffer, typename Speaker>
  void tick(bool on, bool talk, uint32_t now_ms, uint8_t *piece, Buffer &buffer, Speaker &speaker) {
    const size_t low = talk ? SOUND_TALK_LOW : SOUND_LOW, high = talk ? SOUND_TALK_HIGH : SOUND_HIGH;
    if (!on) {
      if (this->speaking) speaker.stop();
      this->speaking = false;
      this->piece_left = 0;
      return;
    }
    if (!this->speaking) {
      if (buffer.held() < low) return;
      speaker.start();
      this->speaking = true;
      this->dry = false;
    }
    if (this->dry) {
      if (buffer.held() < low) return;  // a new run-up first, as at the start
      this->dry = false;
    }
    const size_t held = buffer.held();
    if (held > high && (this->piece_at & 1) == 0) {
      ++this->caught_up;
      this->caught_up_bytes += this->piece_left;
      this->piece_left = 0;
      for (size_t drop = held - low; drop > 0;) {
        const size_t n = buffer.take(piece, std::min(drop, SOUND_PART));
        if (n == 0) break;
        this->caught_up_bytes += n;
        drop -= n;
      }
    }
    for (int rounds = 0; rounds < 8; ++rounds) {
      if (this->piece_left == 0) {
        this->piece_left = buffer.take(piece, SOUND_PART);
        this->piece_at = 0;
        if (this->piece_left == 0) {
          // Nothing waited at all: the buffer ran dry; in a conversation only once the sound has been gone a while.
          if (rounds == 0 && (!talk || now_ms - this->fed_ms > SOUND_TALK_GONE_MS)) {
            this->dry = true;
            ++this->ran_dry;
          }
          return;
        }
      }
      this->fed_ms = now_ms;
      const size_t taken = speaker.play(piece + this->piece_at, this->piece_left);
      if (taken & 1) ++this->odd_taken;
      this->piece_at += taken;
      this->piece_left -= taken;
      if (taken == 0) return;  // the speaker's own buffer is full: the rest next tick
    }
  }
};

// The full view's link while the streams of the page under it end (live_begin, live_tick): one connection at a time,
// since an S3 has internal RAM for one stream's network buffers (docs/CAMERA.md, "Live on an ESP32-S3").
// tests/test_live_view.cpp.
struct ViewWait {
  // A stream that will not end by then: the view opens beside it, where the engine holds a second (a P4). An S3 holds
  // one (picture_engine::limits().streams): its view waits on, showing the stills meanwhile, as one opened beside a
  // tile's took a tester's Guition 4848S040 down (2026-10-30).
  static constexpr uint32_t WAIT_MS = 2000;
  std::string link;    // the view's link while it waits, empty when none
  uint32_t since = 0;  // since when it waits
  bool waiting() const { return !link.empty(); }
  // Whether the view opens now: at once when no stream of the page is ending; beside one still ending only where the
  // engine holds a second (`beside`) and once it has waited WAIT_MS.
  static constexpr bool may_open(bool ending, bool beside, uint32_t waited) {
    return !ending || (beside && waited >= WAIT_MS);
  }
  struct Begin { bool open = false; std::string url; };
  // live_begin: the view asks to open `asked`, with `ending` read after the page's tiles were told to stop. Either the
  // link to open, or nothing while it waits, kept here. `asked` is copied first: live_tick asks with `link` itself,
  // which is cleared on the way, and opened with the cleared one the view asked ":80" and tried again 10 s later
  // (0.4.91 and 0.4.92, docs/open-issues/full-view-first-link-empty-host.md).
  Begin begin(const std::string &asked, uint32_t now, bool ending, bool beside) {
    Begin b{true, asked};
    if (ending && link.empty()) since = now;
    if (ending && !may_open(ending, beside, now - since)) { link = b.url; return {}; }
    link.clear();
    return b;
  }
};

// The role a full view's sound claims (live_begin): the view a ring opened holds the speaker as the ring (DOORBELL),
// which nothing takes from it, and so claims nothing of its own (SoundClaim); a call's view as the call; any other full
// view as a camera's sound, which the voice assistant may borrow and a ring takes (audio_owner.h). A call over a ring is
// the call. tests/test_live_sound.cpp.
constexpr audio_owner::Role view_role(bool ring_shown, bool call_shown) {
  return call_shown ? audio_owner::Role::CALL : ring_shown ? audio_owner::Role::DOORBELL : audio_owner::Role::CAMERA_SOUND;
}
// The stream's sound and the audio owner (audio_owner.h, docs/PLATFORM_PLAN.md 3.4). A stream with sound claims the
// speaker in the role its opener gave: as CAMERA_SOUND music pauses for it, and a voice session or a doorbell takes it
// and gives it back, since the camera stays open. Taken, its sound is held back as when muted (`yielded`, and `drop`
// empties what waited, stale by the time the speaker is back); given back, it plays again. A ring's view (DOORBELL)
// claims nothing here: module_doorbell holds both sides for as long as the ring is up, so the wake word rests under an
// open ring also while its stream breaks and comes back, and closing the view leaves the ring's claim alone. Released
// as claimed, before the stream is freed.
struct SoundClaim {
  bool claims = false;
  audio_owner::Role role = audio_owner::Role::CAMERA_SOUND;
  audio_owner::Side side = audio_owner::Side::OUT;
  uint32_t id = 0;
  // Set on the main loop (the owner's callbacks), read by the stream's task.
  std::atomic<bool> yielded{false};

  void claim(audio_owner::Owner &owner, bool sound, audio_owner::Role opened_as, uint32_t slot,
             std::function<void()> drop) {
    if (!sound || opened_as == audio_owner::Role::DOORBELL) return;
    this->claims = true;
    this->role = opened_as;
    this->side = audio_owner::Side::OUT;
    this->id = slot;
    audio_owner::Claim c;
    c.role = this->role;
    c.id = this->id;
    c.lost = [this, drop]() {
      this->yielded = true;
      if (drop) drop();
    };
    c.regained = [this]() { this->yielded = false; };
    owner.claim(this->side, c);
  }
  void release(audio_owner::Owner &owner) {
    if (this->claims) owner.release(this->side, this->role, this->id);
    this->claims = false;
  }
};

// The app's answer for a live tile of this screen's own camera (plugin API 0.22): no link, the tile is drawn from the
// camera's frames on the screen itself (open, own_frame). "own:", with "?fit=contain" as any tile's link may have.
inline bool is_own(const std::string &url) { return url.compare(0, 4, "own:") == 0; }
// A link to a stream rather than to a still: the app serves both on its camera port, a still as .bmp. The own camera's
// answer counts as one.
inline bool is_stream(const std::string &url) {
  if (is_own(url)) return true;
  const size_t end = url.find_first_of("?#");
  const std::string path = url.substr(0, end);
  return path.size() > 6 && path.compare(path.size() - 6, 6, ".mjpeg") == 0;
}
// The same link's pictures one an ask (the app's .jpg on a stream's token, live_stream.py pull): a live tile asks for
// each, so nothing queues on the way and its bytes are what it shows. Empty for a path that is no stream's.
inline std::string pull_path(const std::string &path) {
  if (!is_stream(path)) return "";
  const size_t found = path.find_first_of("?#"), end = found == std::string::npos ? path.size() : found;
  return path.substr(0, end - 6) + ".jpg" + path.substr(end);
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
        this->talk_ = h.talk;
        this->turn_ = h.turn;
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
  // And whether the part is sound of a conversation (X-Sound: talk).
  bool talk() const { return this->talk_; }
  // And how the app turned it for a turned glass (X-Turn: 90, 180, 270), 0 upright.
  int turn() const { return this->turn_; }

 private:
  std::string head_;
  size_t most_ = 0;
  bool answered_ = false, in_body_ = false, broken_ = false, audio_ = false, still_ = false, has_made_ = false, talk_ = false;
  uint32_t made_ = 0;
  int turn_ = 0;
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
  // The mark of a squeezed tile, as LVGL draws it (ARGB8888 as the name, where the loader turns): laid over the pictures
  // only while the governor squeezes the live tiles (pressure.h, docs/PLATFORM_PLAN.md 4.10); copied at open().
  const uint32_t *badge = nullptr;
  int badge_x = 0, badge_y = 0, badge_w = 0, badge_h = 0, badge_stride = 0;
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
// ---- What a live tile lays over its pictures, made once ----
// The shade, the corners and the name, in picture_paint.py's order, made once when a stream's first picture comes
// (Overlay), in the way its pictures lie: upright, or turned as the glass when the app sends them so (X-Turn, caps
// picture_turn). Each picture then costs the shade's darkening, as before, and one blend for each pixel of the corners
// and the name; no corner is worked out and nothing is turned per picture.
//
// A card of w x h turned as a glass of `turn` degrees turns it (glass::on_panel, the card as the panel): its size, where
// a rectangle of it lies, and which upright pixel lies at gx, gy of it.
inline bool sideways(int turn) { return turn == 90 || turn == 270; }
inline int turned_w(int w, int h, int turn) { return sideways(turn) ? h : w; }
inline int turned_h(int w, int h, int turn) { return sideways(turn) ? w : h; }
inline Rect in_turned(const Rect &r, int turn, int w, int h) {
  return on_panel(r, turn, turned_w(w, h, turn), turned_h(w, h, turn));
}
inline void upright_of(int turn, int w, int h, int gx, int gy, int &x, int &y) {
  switch (turn) {
    case 90: x = gy, y = h - 1 - gx; break;
    case 180: x = w - 1 - gx, y = h - 1 - gy; break;
    case 270: x = w - 1 - gy, y = gx; break;
    default: x = gx, y = gy;
  }
}
// The turn from the way a picture lies to the glass: what the PPA still turns on its way there.
inline int turn_between(int lies, int glass_turn) { return ((glass_turn - lies) % 360 + 360) % 360; }

// The shade under a name: the bottom FADE_PERCENT of the card darkens row by row to FADE_DEPTH / 255 black; how much
// at row `y` of a card `h` high.
inline unsigned fade_at(int y, int h) {
  const int rows = std::max(1, (h * FADE_PERCENT + 50) / 100);
  const int i = y - (h - rows);
  return i < 0 ? 0 : static_cast<unsigned>(FADE_DEPTH * (i + 1) / rows);  // 0 above the shade
}
// The card's rounded corners: what lies outside a circle of `radius` in each corner becomes the ground, its edge smoothed
// by how much of each pixel lies outside; how much at x, y of a w x h card.
inline unsigned corner_at(int x, int y, int w, int h, int radius) {
  radius = std::min(radius, std::min(w, h) / 2);
  const int cx = x < radius ? x : w - 1 - x, cy = y < radius ? y : h - 1 - y;  // as in the top left corner
  if (cx >= radius || cy >= radius) return 0;
  const float dx = radius - (cx + 0.5f), dy = radius - (cy + 0.5f);
  const float outside = std::sqrt(dx * dx + dy * dy) - radius + 0.5f;  // 0: inside, 1: wholly outside
  return outside <= 0 ? 0 : outside >= 1 ? 255 : static_cast<unsigned>(outside * 255);
}
// What lies over the shade at x, y of a live tile's card (w x h, upright): the corners and then the name, as one colour
// and how much of the picture it covers, so that one blend(picture, color, alpha) after the shade is the two blends
// to within a step of RGB565.
struct Cover {
  uint16_t color = 0;
  uint8_t alpha = 0;
};
// The ARGB8888 pixel at x, y of an image w x h laid at ix, iy (`stride` pixels a row, 0 for w), or 0 outside it.
inline uint32_t argb_at(const uint32_t *px, int ix, int iy, int w, int h, int stride, int x, int y) {
  if (!px || x < ix || y < iy || x >= ix + w || y >= iy + h) return 0;
  return px[static_cast<size_t>(y - iy) * (stride ? stride : w) + (x - ix)];
}
// `badge`: with the mark of a squeezed tile over the rest (Look::badge).
inline Cover marks_at(const Look &look, int w, int h, int x, int y, bool badge = false) {
  if (!look.tile) return {};
  const unsigned corner = look.radius > 0 ? corner_at(x, y, w, h, look.radius) : 0;
  const uint32_t name = argb_at(look.name, look.name_x, look.name_y, look.name_w, look.name_h, look.name_stride, x, y);
  const uint32_t mark =
      badge ? argb_at(look.badge, look.badge_x, look.badge_y, look.badge_w, look.badge_h, look.badge_stride, x, y) : 0;
  const unsigned over = name >> 24, top = mark >> 24;
  if (!corner && !top) return {rgb565(name), static_cast<uint8_t>(over)};
  if (!corner && !over) return {rgb565(mark), static_cast<uint8_t>(top)};
  if (!over && !top) return {look.ground, static_cast<uint8_t>(corner)};
  // The name or the mark over a corner's edge, or over each other: each layer over what lies under it, how much of the
  // picture still shows and the colour laid over it so far, weighted by how much it covers.
  float keep = 1, r = 0, g = 0, b = 0;
  auto lay = [&](unsigned alpha, uint16_t c) {
    const float a = alpha / 255.0f;
    keep *= 1 - a;
    r = r * (1 - a) + a * ((c >> 11) & 31) / 31.0f;
    g = g * (1 - a) + a * ((c >> 5) & 63) / 63.0f;
    b = b * (1 - a) + a * (c & 31) / 31.0f;
  };
  lay(corner, look.ground);
  lay(over, rgb565(name));
  lay(top, rgb565(mark));
  const float covers = 1 - keep;
  auto level = [&](float v, int most) { return static_cast<unsigned>(std::min<float>(most, v / covers * most + 0.5f)); };
  return {static_cast<uint16_t>(level(r, 31) << 11 | level(g, 63) << 5 | level(b, 31)),
          static_cast<uint8_t>(std::min(255.0f, covers * 255 + 0.5f))};
}
// The overlay of a card as its pictures lie, `w` x `h` of them, in two parts. The shade: how deep it darkens each row
// (or, on a card that lies on its side, each column) from `shade_from` on, `shade_count` of them. The marks (the
// corners and the name): segments of a row whose pixels each have a colour and how much they cover, one after another
// in `alpha` and `color`. A gap of fewer than MARK_GAP pixels without a mark stays in its segment.
constexpr int MARK_GAP = 8;
struct OverlaySegment {
  uint16_t y = 0, from = 0, to = 0;
  uint32_t at = 0;
};
struct Overlay {
  int w = 0, h = 0;
  bool shade_by_column = false;
  int shade_from = 0, shade_count = 0;
  const uint8_t *shade = nullptr;
  const OverlaySegment *segments = nullptr;
  int count = 0;
  const uint8_t *alpha = nullptr;
  const uint16_t *color = nullptr;
};
// The shade of an upright card w x h whose pictures lie turned `turn`, into `depth` (room for the longer side): whether
// it goes by column, from where, and how many rows or columns it darkens (0: none).
inline int overlay_shade(const Look &look, int w, int h, int turn, uint8_t *depth, bool &by_column, int &from) {
  by_column = sideways(turn);
  from = 0;
  if (!look.tile || !look.fade) return 0;
  const int along = by_column ? turned_w(w, h, turn) : turned_h(w, h, turn);
  int first = -1, last = -1;
  for (int k = 0; k < along; ++k) {
    int x = 0, y = 0;
    upright_of(turn, w, h, by_column ? k : 0, by_column ? 0 : k, x, y);
    depth[k] = static_cast<uint8_t>(fade_at(y, h));
    if (depth[k]) {
      if (first < 0) first = k;
      last = k;
    }
  }
  if (first < 0) return 0;
  from = first;
  for (int k = first; k <= last; ++k) depth[k - first] = depth[k];
  return last - first + 1;
}
// The marks' segments of that card: with `segments` null only counted (how many, and the pixels they hold, for the
// memory), else written, and with `alpha` and `color` their pixels too.
inline int overlay_marks(const Look &look, int w, int h, int turn, OverlaySegment *segments, size_t &pixels,
                         uint8_t *alpha = nullptr, uint16_t *color = nullptr, bool badge = false) {
  const int tw = turned_w(w, h, turn), th = turned_h(w, h, turn);
  int count = 0;
  pixels = 0;
  for (int gy = 0; gy < th; ++gy) {
    int gx = 0;
    while (gx < tw) {
      int x = 0, y = 0;
      upright_of(turn, w, h, gx, gy, x, y);
      if (!marks_at(look, w, h, x, y, badge).alpha) {
        ++gx;
        continue;
      }
      // A segment: from this mark to the last one with no gap of MARK_GAP between.
      const int from = gx;
      int to = gx + 1, quiet = 0;
      for (int at = gx + 1; at < tw && quiet < MARK_GAP; ++at) {
        upright_of(turn, w, h, at, gy, x, y);
        if (marks_at(look, w, h, x, y, badge).alpha) {
          to = at + 1;
          quiet = 0;
        } else {
          ++quiet;
        }
      }
      if (segments) {
        segments[count] = OverlaySegment{static_cast<uint16_t>(gy), static_cast<uint16_t>(from), static_cast<uint16_t>(to),
                                         static_cast<uint32_t>(pixels)};
        for (int at = from; alpha && at < to; ++at) {
          upright_of(turn, w, h, at, gy, x, y);
          const Cover c = marks_at(look, w, h, x, y, badge);
          alpha[pixels + at - from] = c.alpha;
          color[pixels + at - from] = c.color;
        }
      }
      pixels += static_cast<size_t>(to - from);
      ++count;
      gx = to;
    }
  }
  return count;
}
// The overlay laid over a picture of its size (`stride` pixels a row): the shade, then one blend a mark.
inline void lay_overlay(uint16_t *px, int stride, const Overlay &o) {
  if (o.shade_count > 0) {
    if (o.shade_by_column) {
      for (int y = 0; y < o.h; ++y) {
        uint16_t *row = px + static_cast<size_t>(y) * stride + o.shade_from;
        for (int i = 0; i < o.shade_count; ++i) row[i] = blend(row[i], 0, o.shade[i]);
      }
    } else {
      for (int i = 0; i < o.shade_count; ++i) {
        uint16_t *row = px + static_cast<size_t>(o.shade_from + i) * stride;
        const unsigned depth = o.shade[i];
        for (int x = 0; x < o.w; ++x) row[x] = blend(row[x], 0, depth);
      }
    }
  }
  for (int s = 0; s < o.count; ++s) {
    const OverlaySegment &seg = o.segments[s];
    uint16_t *p = px + static_cast<size_t>(seg.y) * stride + seg.from;
    const uint8_t *a = o.alpha + seg.at;
    const uint16_t *c = o.color + seg.at;
    for (int i = 0, n = seg.to - seg.from; i < n; ++i)
      if (a[i]) p[i] = blend(p[i], c[i], a[i]);
  }
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
// A stream's task runs below the voice assistant's wake word (ESPHome's micro_wake_word inference, priority 3) and above
// the main loop (1), and waits for and holds the glass at glass::WRITER_PRIORITY (glass::wait_as_writer), in turn with
// the other streams and a still's download, then goes back: composing a picture and reading the app run below the
// voice. At WRITER_PRIORITY throughout, four tiles' composing (30 ms of wall clock a picture on a reTerminal D1001) and
// the screen's own video (priority 4) left the wake word's inference behind 644 times in an hour at rest (2026-10-28).
constexpr unsigned STREAM_PRIORITY = 2;
static_assert(STREAM_PRIORITY > 1 && STREAM_PRIORITY < 3, "between the main loop (1) and the wake word's inference (3)");
static_assert(STREAM_PRIORITY < glass::WRITER_PRIORITY, "a stream is raised to the writers' priority only for the glass");

// The streams the main loop holds, as open() and tick() count them, pure (tests/test_live_view.cpp). A stream counts from
// open() until the tick that frees it, also once it was closed (`ending`): its task may still hold its connection and
// its memory until then. Another may open while fewer than the engine's `most` (picture_engine::limits().streams) are
// held, one still ending counted: a full view beside a live tile that had not ended took a tester's S3 down
// (2026-10-30). beside(): whether the engine holds a second stream at all; an S3 does not, so its full view waits for
// the page's stream to end however long it takes.
struct Census {
  int held = 0, ending = 0;
};
template<typename Streams> Census census(const Streams &streams) {
  Census c;
  for (const auto *s : streams) {
    if (!s) continue;
    ++c.held;
    if (s->stopping) ++c.ending;
  }
  return c;
}
inline bool room_for(const Census &c, int most) { return c.held < most; }
inline bool beside(int most) { return most > 1; }

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
// Whether this screen streams: a P4 or an S3 whose panel ESP-IDF made with an RGB565 frame buffer a task may write
// (glass::direct), and LVGL bound.
bool available();
// And whether it streams a camera full screen too: not where the engine takes no full view's picture; its view then
// shows the stills of every board.
bool full_view();
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
// Whether a stream that was closed is still there: its task may still hold its connection and its memory until it ends
// and the next tick frees it (about one picture's time). A full view opens after it, never beside it: one connection at
// a time, as an S3 has internal RAM for one stream's network buffers and not for two (docs/CAMERA.md, "Live on an
// ESP32-S3").
bool ending();
// Whether another stream may open now: fewer than the engine's streams at once (picture_engine::limits), one still
// ending counted. And whether the engine holds a second one at all; an S3 does not, so its full view waits for the
// page's stream to end however long it takes.
bool room_for_another();
bool beside();
// The main loop, every 50 ms: frees what finished tasks left and tells each stream's owner what happened.
void tick(const std::function<void(Handle, Event)> &tell);
// How often the panel ran dry since boot (a frame of blue: glass.h, "The panel's share of the memory bus").
uint32_t misses();
// The screen's own camera on a tile of its own (plugin API 0.22, docs/PLATFORM_PLAN.md 4.11). A plugin with the camera
// offers its frames once (own_offer, its setup), and the hello then says "own_camera", so the app answers such a tile
// "own:". While a tile of it is open, own_wanted says so, and the plugin hands each frame to own_frame on its camera's
// task: the tile takes one when its pace says (hw::OWN_TILE_PPS, a busy screen's share of that), copies it into its card with
// the PPA (scaled, from the camera's YUV420 or RGB565) when the glass is free at once, and lays it onto the glass on its
// own task. Never waits: a frame it cannot take now goes by.
void own_offer();
bool own_offered();
bool own_wanted();
void own_frame(const uint8_t *data, int width, int height, bool yuv420);
// What the streams that run hold of the board's memory, about (docs/PICTURES.md: the streams take their share of the one
// picture budget while they run): each stream's input and its decoded picture of its room, from what the main loop
// set when it opened, so never read under a task.
size_t held_bytes();
#else
inline size_t held_bytes() { return 0; }
inline bool available() { return false; }
inline bool full_view() { return false; }
inline Handle open(const std::string &, const Rect &, const Look & = Look{}, bool = false,
                   audio_owner::Role = audio_owner::Role::CAMERA_SOUND) {
  return -1;
}
inline bool has_speaker() { return false; }
inline void mute(Handle, bool) {}
inline void close(Handle) {}
inline bool ending() { return false; }
inline bool room_for_another() { return false; }
inline bool beside() { return false; }
inline void tick(const std::function<void(Handle, Event)> &) {}
inline uint32_t misses() { return 0; }
inline void own_offer() {}
inline bool own_offered() { return false; }
inline bool own_wanted() { return false; }
inline void own_frame(const uint8_t *, int, int, bool) {}
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
