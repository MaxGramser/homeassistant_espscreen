// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_live_view.cpp -o /tmp/test_live_view && /tmp/test_live_view
// The parts of the P4's live camera a PC can check (live_view.h): the stream's framing in any pieces, where a
// rectangle of the screen lies on a turned panel (ESPHome's own sums for LVGL's flushes), and where a picture goes.
#include "../components/smart_display/live_view.h"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>

using namespace live_view;
using picture_engine::Cut;
using picture_engine::cut;
using picture_engine::scaled;

// The most a part may be, as a stream is opened with it (the P4 engine's full view: picture_engine::limits()).
constexpr size_t MOST = 1024 * 1024;

// fit as live_view asks it, for a room of the screen.
static Rect fit(int w, int h, const Rect &area, int &scale) {
  const picture_engine::Fit f = picture_engine::fit(w, h, area.x, area.y, area.w, area.h);
  scale = f.scale;
  return f.empty() ? Rect{} : Rect{f.x, f.y, f.w, f.h};
}

static std::string part(const std::string &body) {
  return "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + std::to_string(body.size()) + "\r\n\r\n" + body + "\r\n";
}

// Feeds `stream` in pieces of `step` bytes; returns the pictures that came whole, or "!" once it broke.
static std::vector<std::string> read(const std::string &stream, size_t step, size_t room = 64) {
  Reader reader(MOST);
  std::vector<std::string> pictures;
  std::vector<uint8_t> buffer(room);
  for (size_t at = 0; at < stream.size(); at += step) {
    const size_t n = std::min(step, stream.size() - at);
    const bool ok = reader.feed(
        reinterpret_cast<const uint8_t *>(stream.data() + at), n,
        [&](size_t length, bool) -> uint8_t * { return length <= buffer.size() ? buffer.data() : nullptr; },
        [&](size_t length, bool audio) {
          pictures.emplace_back((audio ? "sound:" : "") + std::string(reinterpret_cast<const char *>(buffer.data()), length));
        });
    if (!ok) { pictures.push_back("!"); break; }
  }
  return pictures;
}

static void framing() {
  const std::string head = "HTTP/1.0 200 OK\r\nContent-Type: multipart/x-mixed-replace;boundary=frame\r\n\r\n";
  const std::string stream = head + part("first picture") + part("second") + part("the third one");
  // Whole, byte by byte, and in pieces that cut heads and bodies anywhere: the same three pictures.
  for (size_t step : {stream.size(), size_t(1), size_t(3), size_t(7), size_t(64)}) {
    const auto got = read(stream, step);
    assert(got.size() == 3);
    assert(got[0] == "first picture" && got[1] == "second" && got[2] == "the third one");
  }
  // A picture the task has no room for is skipped, and the next one still comes.
  {
    const auto got = read(head + part(std::string(100, 'x')) + part("small"), 5, 64);
    assert(got.size() == 1 && got[0] == "small");
  }
  // A full view's sound comes as parts of its own between the pictures, told apart by their Content-Type.
  {
    const std::string sound = "--frame\r\nContent-Type: audio/L16;rate=16000\r\nContent-Length: 4\r\n\r\nabcd\r\n";
    const auto got = read(head + part("one") + sound + part("two"), 3);
    assert(got.size() == 3 && got[0] == "one" && got[1] == "sound:abcd" && got[2] == "two");
  }
  // An answer other than 200, a part without its length and a head that never ends break the stream.
  assert(read("HTTP/1.0 404 Not Found\r\n\r\nUnknown link", 4) == std::vector<std::string>{"!"});
  assert(read(head + "--frame\r\nContent-Type: image/jpeg\r\n\r\nxyz", 4) == std::vector<std::string>{"!"});
  assert(read(head + std::string(MAX_HEAD + 10, 'h'), 100).back() == "!");
  // A part over the most a stream was opened with breaks it too: no app sends one, so it is not a stream of pictures.
  assert(read(head + "--frame\r\nContent-Length: " + std::to_string(MOST + 1) + "\r\n\r\n", 9).back() == "!");
}

// An engine without a decoder opens its streams with 0: no part at all, never "no limit".
static void none() {
  Reader reader(0);
  const std::string stream = "HTTP/1.0 200 OK\r\n\r\n" + part("x");
  uint8_t room[8];
  assert(!reader.feed(reinterpret_cast<const uint8_t *>(stream.data()), stream.size(),
                      [&](size_t, bool) { return room; }, [](size_t, bool) {}));
}

// Until it is live: the stills before the camera's stream are marked, part by part, in any pieces.
static void marking() {
  const std::string head = "HTTP/1.0 200 OK\r\nContent-Type: multipart/x-mixed-replace;boundary=frame\r\n\r\n";
  const std::string still = "--frame\r\nContent-Type: image/jpeg\r\nX-Picture: still\r\nContent-Length: 5\r\n\r\nstill\r\n";
  const std::string stream = head + still + still + part("live") + part("live2");
  for (size_t step : {stream.size(), size_t(1), size_t(5)}) {
    Reader reader(MOST);
    uint8_t buffer[64];
    std::vector<bool> marks;
    for (size_t at = 0; at < stream.size(); at += step) {
      const size_t n = std::min(step, stream.size() - at);
      assert(reader.feed(reinterpret_cast<const uint8_t *>(stream.data() + at), n,
                         [&](size_t, bool) -> uint8_t * { return buffer; },
                         [&](size_t, bool) { marks.push_back(reader.still()); }));
    }
    assert((marks == std::vector<bool>{true, true, false, false}));
  }
}

// When the app made each picture (X-Made), in any pieces; a part without it says none.
static void made() {
  const std::string head = "HTTP/1.0 200 OK\r\nContent-Type: multipart/x-mixed-replace;boundary=frame\r\n\r\n";
  const std::string stamped = "--frame\r\nContent-Type: image/jpeg\r\nX-Made: 4294967290\r\nContent-Length: 4\r\n\r\nlive\r\n";
  const std::string odd = "--frame\r\nContent-Type: image/jpeg\r\nX-Made: 12ab\r\nContent-Length: 4\r\n\r\nlive\r\n";
  const std::string stream = head + stamped + part("live") + odd;
  for (size_t step : {stream.size(), size_t(1), size_t(7)}) {
    Reader reader(MOST);
    uint8_t buffer[64];
    std::vector<std::pair<bool, uint32_t>> seen;
    for (size_t at = 0; at < stream.size(); at += step) {
      const size_t n = std::min(step, stream.size() - at);
      assert(reader.feed(reinterpret_cast<const uint8_t *>(stream.data() + at), n,
                         [&](size_t, bool) -> uint8_t * { return buffer; },
                         [&](size_t, bool) { seen.emplace_back(reader.has_made(), reader.made()); }));
    }
    assert(seen.size() == 3 && seen[0].first && seen[0].second == 4294967290u && !seen[1].first && !seen[2].first);
  }
}

// The loader in a live tile's corner while its stills show: where it lies, and the spinner it draws as it turns.
static void loading() {
  Look look;
  look.tile = true;
  look.loader = 40;
  look.loader_margin = 8;
  look.loader_arc = 6;
  look.loader_ring = 0x39E7;
  look.loader_turn = 0x001F;
  int x = 0, y = 0;
  // In the top right corner of a card, and none in a card too small for it or in the full view.
  assert(loader_spot(look, 300, 200, x, y) && x == 300 - 8 - 40 && y == 8);
  assert(!loader_spot(look, 300, 55, x, y));
  Look view = look;
  view.tile = false;
  assert(!loader_spot(view, 1280, 720, x, y));
  look.loader = 0;
  assert(!loader_spot(look, 300, 200, x, y));
  look.loader = 40;
  // Drawn into a card of 100 x 60 at its spot, over white.
  const int w = 100, h = 60;
  std::vector<uint16_t> px(w * h, 0xFFFF);
  assert(loader_spot(look, w, h, x, y));
  auto at = [&](int i, int j) { return px[static_cast<size_t>(y + j) * w + x + i]; };
  draw_loader(px.data(), w, x, y, look, 0);
  // Outside its round shade nothing changes: the card around it and the square's own corners.
  assert(px[0] == 0xFFFF && px[w * h - 1] == 0xFFFF && at(0, 0) == 0xFFFF && at(39, 39) == 0xFFFF);
  // Its middle is shaded, not black; at the start of its turn the arc runs from three o'clock clockwise, so it lies
  // under the middle and the ring alone above it.
  assert(at(20, 20) != 0xFFFF && at(20, 20) != 0x0000);
  assert(at(20, 31) == 0x001F && at(20, 8) == 0x39E7);
  // Half a turn on (LVGL's 900 ms), the arc has gone round: above the middle, and the ring below it.
  std::fill(px.begin(), px.end(), 0xFFFF);
  draw_loader(px.data(), w, x, y, look, LOADER_TURN_MS / 2);
  assert(at(20, 8) == 0x001F && at(20, 31) == 0x39E7);
  // The arc is about LOADER_ARC of the ring at the start: count the ring's pixels wholly in one colour or the other.
  std::fill(px.begin(), px.end(), 0xFFFF);
  draw_loader(px.data(), w, x, y, look, 0);
  int arc = 0, ring = 0;
  for (int j = 0; j < 40; ++j)
    for (int i = 0; i < 40; ++i) arc += at(i, j) == 0x001F, ring += at(i, j) == 0x39E7;
  const float share = static_cast<float>(arc) / (arc + ring);
  assert(share > 0.5f && share < 0.66f);
  // Nothing outside its square: the rows over and under it are white.
  for (int i = 0; i < w; ++i) assert(px[static_cast<size_t>(y - 1) * w + i] == 0xFFFF && px[static_cast<size_t>(y + 40) * w + i] == 0xFFFF);
}

static void links() {
  assert(is_stream("http://192.168.1.20:8098/camera/abcdefghijklmnopqrstuvwx.mjpeg"));
  assert(is_stream("http://h/camera/t.mjpeg?x=1"));
  assert(!is_stream("http://192.168.1.20:8098/camera/abcdefghijklmnopqrstuvwx.bmp"));
  assert(!is_stream(""));
}

// The corners of a rectangle on a 800 x 1280 panel that LVGL lays out as 1280 x 800, turned as ESPHome turns its
// flushes (LvglComponent::draw_buffer_): the logical top left ends at the panel's top right for 90 degrees, and at
// its bottom left for 270.
static void panel() {
  const Rect r{10, 20, 300, 100};
  assert(on_panel(r, 0, 800, 1280) == r);
  assert((on_panel(r, 90, 800, 1280) == Rect{800 - 20 - 100, 10, 100, 300}));
  assert((on_panel(r, 180, 1280, 800) == Rect{1280 - 10 - 300, 800 - 20 - 100, 300, 100}));
  assert((on_panel(r, 270, 800, 1280) == Rect{20, 1280 - 10 - 300, 100, 300}));
  // The whole screen covers the whole panel either way.
  for (int turn : {90, 270}) assert((on_panel(Rect{0, 0, 1280, 800}, turn, 800, 1280) == Rect{0, 0, 800, 1280}));
  assert((on_panel(Rect{0, 0, 1280, 800}, 180, 1280, 800) == Rect{0, 0, 1280, 800}));
}

static void placing() {
  // The room below a top bar of 72 px on 1280 x 800: a 16:9 picture of 1280 x 720 at its own size in its middle.
  const Rect area{0, 72, 1280, 728};
  int s = 0;
  assert((fit(1280, 720, area, s) == Rect{0, 76, 1280, 720}) && s == 16);
  // A substream of 512 x 288 is scaled up by the PPA, in sixteenths: 2.5 times fills the width.
  assert((fit(512, 288, area, s) == Rect{0, 76, 1280, 720}) && s == 40);
  // A 4:3 camera fills the height; a picture larger than the room is scaled down, never over the top bar.
  assert((fit(640, 480, area, s) == Rect{160, 76, 960, 720}) && s == 24);
  assert((fit(1920, 1080, area, s) == Rect{40, 98, 1200, 675}) && s == 10);
  for (int w : {64, 333, 512, 704, 1280, 1920}) {
    for (int h : {48, 199, 288, 720, 1080}) {
      const Rect r = fit(w, h, area, s);
      assert(s > 0 && r.x >= area.x && r.y >= area.y && r.x + r.w <= area.x + area.w && r.y + r.h <= area.y + area.h);
      assert(r.w == scaled(w, s) && r.h == scaled(h, s));
    }
  }
  assert(fit(0, 10, area, s).empty() && s == 0);
  assert(fit(picture_engine::MAX_SIDE + 1, 100, area, s).empty());
  assert(box_text(area) == "1280x728");
}

// A live tile's card: the picture cut to fill it (the middle of it, scaled up only when smaller), or whole on black.
static void cutting() {
  // The app sends a filling picture at the card's size or a little more: cut at its own scale, the middle of it.
  Cut c = cut(434, 260, 434, 244, false);
  assert(c.ok && c.scale == 16 && c.in_x == 0 && c.in_y == 8 && c.in_w == 434 && c.in_h == 244 && c.covers(434, 244));
  // A substream smaller than the card is scaled up until it covers it, in sixteenths, and cut to it.
  c = cut(512, 288, 868, 488, false);
  assert(c.ok && c.scale == 28 && c.out_x >= 0 && c.out_y >= 0 && c.out_w <= 868 && c.out_h <= 488);
  assert(868 - c.out_w <= 2 && 488 - c.out_h <= 2);
  // A larger one is scaled down: the least scale that still covers.
  c = cut(1920, 1080, 434, 244, false);
  assert(c.ok && c.scale == 4 && scaled(1920, 4) >= 434 && scaled(1080, 4) >= 244);
  // Whole: as large as fits, in the middle, the rest of the card black.
  c = cut(1920, 1080, 434, 434, true);
  assert(c.ok && c.in_w == 1920 && c.in_h == 1080 && c.out_w <= 434 && c.out_x + c.out_w <= 434 && c.out_y > 0 && !c.covers(434, 434));
  assert(!cut(0, 10, 100, 100, false).ok && !cut(10, 10, 0, 100, true).ok);
}

// What a live tile lays over its picture, as picture_paint.py does: the shade, the corners, the name.
static void composing() {
  const int w = 40, h = 20;
  std::vector<uint16_t> px(w * h, 0xFFFF);  // white
  fade(px.data(), w, w, h);
  // The top of the card is untouched, the bottom row FADE_DEPTH / 255 towards black.
  assert(px[0] == 0xFFFF && px[(h - 1 - (h * FADE_PERCENT + 50) / 100) * w] == 0xFFFF);
  const uint16_t bottom = px[(h - 1) * w + 20];
  assert(bottom != 0xFFFF && ((bottom >> 11) & 31) < 31 && ((bottom >> 11) & 31) > 8);
  // Corners: the very corner is the ground, the middle of the card is not.
  std::fill(px.begin(), px.end(), 0xFFFF);
  round_corners(px.data(), w, w, h, 6, 0x001F);
  assert(px[0] == 0x001F && px[w - 1] == 0x001F && px[(h - 1) * w] == 0x001F && px[h * w - 1] == 0x001F);
  assert(px[10 * w + 20] == 0xFFFF && px[6 * w + 6] == 0xFFFF);
  // The name: opaque pixels replace, transparent ones leave the picture.
  std::fill(px.begin(), px.end(), 0x0000);
  const uint32_t name[4] = {0xFFFFFFFF, 0x00FFFFFF, 0x80FF0000, 0xFF00FF00};
  lay_over(px.data(), w, w, h, name, 2, 3, 4, 2, 2);
  assert(px[4 * w + 3] == 0xFFFF && px[4 * w + 4] == 0x0000 && px[5 * w + 4] == rgb565(0x00FF00));
  assert(((px[5 * w + 3] >> 11) & 31) > 10 && ((px[5 * w + 3] >> 11) & 31) < 20);  // half red
  // Off the card it is cut.
  lay_over(px.data(), w, w, h, name, 2, w - 1, h - 1, 2, 2);
  assert(px[h * w - 1] == 0xFFFF);
  // The full view lays nothing over its picture.
  std::fill(px.begin(), px.end(), 0x1234);
  compose(px.data(), w, w, h, Look{});
  assert(px[0] == 0x1234 && px[h * w - 1] == 0x1234);
}

int main() {
  none();
  framing();
  marking();
  made();
  loading();
  links();
  panel();
  placing();
  cutting();
  composing();
  std::puts("live_view: ok");
  return 0;
}
