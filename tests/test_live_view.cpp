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

// A stream's link and the same link's pictures one an ask; nothing for a link that is no stream's. And the answer to
// an ask as the screen reads it: its status, its length, its stamp and whether it is a still.
static void pulling() {
  assert(pull_path("/camera/abcdefghijklmnopqrstuvwx.mjpeg") == "/camera/abcdefghijklmnopqrstuvwx.jpg");
  assert(pull_path("/camera/abc.mjpeg?x=1") == "/camera/abc.jpg?x=1");
  assert(pull_path("/camera/abc.bmp").empty() && pull_path("/camera/abc.jpg").empty());
  const std::string ok = "HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\nX-Made: 4242\r\nX-Picture: still\r\n"
                         "Content-Length: 4\r\n\r\nJPEG";
  const auto h = picture_fetch::parse_head(ok.data(), ok.size());
  assert(h.complete && h.status == 200 && h.has_length && h.content_length == 4 && h.has_made && h.made == 4242 &&
         h.still && ok.substr(h.length) == "JPEG");
  const std::string none = "HTTP/1.1 204 No Content\r\nCache-Control: no-cache\r\n\r\n";
  const auto n = picture_fetch::parse_head(none.data(), none.size());
  assert(n.complete && n.status == 204 && !n.has_length && n.length == none.size());
  // How the app turned a tile's picture for a turned glass (X-Turn): a turn a glass has, else upright.
  assert(h.turn == 0);
  for (const char *value : {"90", "180", "270"}) {
    const std::string turned = std::string("HTTP/1.1 200 OK\r\nX-Turn: ") + value + "\r\nContent-Length: 4\r\n\r\nJPEG";
    assert(picture_fetch::parse_head(turned.data(), turned.size()).turn == std::stoi(value));
  }
  for (const char *value : {"45", "0", "2700", "9O", "", "-90"}) {
    const std::string odd = std::string("HTTP/1.1 200 OK\r\nX-Turn: ") + value + "\r\nContent-Length: 4\r\n\r\nJPEG";
    assert(picture_fetch::parse_head(odd.data(), odd.size()).turn == 0);
  }
  // A part of the app's stream says it the same way (live_stream.part_head).
  const std::string stream = "HTTP/1.0 200 OK\r\n\r\n--frame\r\nContent-Type: image/jpeg\r\nX-Turn: 270\r\n"
                             "Content-Length: 4\r\nX-Made: 7\r\n\r\nJPEG\r\n";
  Reader reader(MOST);
  uint8_t buffer[8];
  int turned = -1;
  assert(reader.feed(reinterpret_cast<const uint8_t *>(stream.data()), stream.size(),
                     [&](size_t, bool) -> uint8_t * { return buffer; }, [&](size_t, bool) { turned = reader.turn(); }));
  assert(turned == 270);
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

// A card turned as the glass turns it (the app's turned pictures, X-Turn): each pixel where on_panel puts it, with the
// card as the panel, and back; what the PPA still turns between a picture and the glass.
static void turning() {
  const int w = 7, h = 5;
  for (int turn : {0, 90, 180, 270}) {
    const int tw = turned_w(w, h, turn), th = turned_h(w, h, turn);
    assert(tw * th == w * h && (turn % 180 ? tw == h : tw == w));
    for (int y = 0; y < h; ++y)
      for (int x = 0; x < w; ++x) {
        const Rect g = in_turned(Rect{x, y, 1, 1}, turn, w, h);
        assert(g.x >= 0 && g.y >= 0 && g.x < tw && g.y < th);
        int ux = -1, uy = -1;
        upright_of(turn, w, h, g.x, g.y, ux, uy);
        assert(ux == x && uy == y);
      }
  }
  // As the app turns it (live_pictures.TURNS): on a glass turned 90 the card's top left lies at the top right.
  assert(in_turned(Rect{0, 0, 1, 1}, 90, w, h) == (Rect{h - 1, 0, 1, 1}));
  assert(in_turned(Rect{0, 0, 1, 1}, 270, w, h) == (Rect{0, w - 1, 1, 1}));
  assert(turn_between(270, 270) == 0 && turn_between(0, 90) == 90 && turn_between(90, 270) == 180 &&
         turn_between(270, 90) == 180 && turn_between(0, 0) == 0);
  // A full view's picture the app turned: its room worked out on it upright, and the picture scaled straight onto the
  // glass fills that room as the panel has it (a reTerminal D1001's 800 x 1280 panel, shown as 1280 x 800).
  const Rect room{0, 56, 1280, 744};
  for (int turn : {90, 270}) {
    const int pw = 720, ph = 1280;  // 1280 x 720 turned
    int scale = 0;
    const Rect where = fit(turned_w(pw, ph, turn), turned_h(pw, ph, turn), room, scale);
    const Rect target = on_panel(where, turn, 800, 1280);
    assert(target.w == scaled(pw, scale) && target.h == scaled(ph, scale));
    assert(target.x >= 0 && target.y >= 0 && target.x + target.w <= 800 && target.y + target.h <= 1280);
  }
}

// What a live tile lays over its picture, as picture_paint.py does it: the shade, the corners, the name. Each alone,
// then as one overlay against the three blends in turn, the way the firmware laid them before it (2026-10-28).
static void composing() {
  // The shade: nothing above it, the bottom row FADE_DEPTH / 255 towards black.
  const int w = 40, h = 20, shade = (h * FADE_PERCENT + 50) / 100;
  assert(fade_at(h - 1 - shade, h) == 0 && fade_at(h - shade, h) > 0 && fade_at(h - 1, h) == FADE_DEPTH);
  // The corners: the very corner is the ground, the middle of the card and the edge inside the round are not.
  assert(corner_at(0, 0, w, h, 6) == 255 && corner_at(w - 1, h - 1, w, h, 6) == 255 && corner_at(w - 1, 0, w, h, 6) == 255);
  assert(corner_at(20, 10, w, h, 6) == 0 && corner_at(6, 0, w, h, 6) == 0 && corner_at(0, 6, w, h, 6) == 0);
  // The name: LVGL's ARGB as it is, transparent pixels leave the picture.
  const uint32_t name[6] = {0xFFFFFFFF, 0x00FFFFFF, 0x80FF0000, 0xFF00FF00, 0x40FFFFFF, 0xFFFFFFFF};
  Look look;
  look.tile = look.fade = true;
  look.radius = 6;
  look.ground = 0x001F;
  look.name = name, look.name_x = 30, look.name_y = 14, look.name_w = 3, look.name_h = 2, look.name_stride = 3;
  // The marks over the shade: the name as LVGL drew it, a corner as the ground, nothing in the middle of the card.
  assert(marks_at(look, w, h, 30, 14).alpha == 255 && marks_at(look, w, h, 30, 14).color == 0xFFFF);
  assert(marks_at(look, w, h, 0, 0).alpha == 255 && marks_at(look, w, h, 0, 0).color == look.ground);
  assert(marks_at(look, w, h, 20, 2).alpha == 0 && marks_at(look, w, h, 20, h - 1).alpha == 0);
  // The full view lays nothing over its picture.
  assert(marks_at(Look{}, w, h, 0, 0).alpha == 0);
  // The squeezed mark (Look::badge): there only with `badge`, over what lies under it, and the rest as before.
  {
    const uint32_t mark[4] = {0xFFFFFFFF, 0x00000000, 0x99000000, 0xFFFFFFFF};
    Look squeezed = look;
    squeezed.badge = mark, squeezed.badge_x = 10, squeezed.badge_y = 4, squeezed.badge_w = 2, squeezed.badge_h = 2;
    assert(marks_at(squeezed, w, h, 10, 4).alpha == 0 && marks_at(squeezed, w, h, 10, 4, true).alpha == 255);
    assert(marks_at(squeezed, w, h, 10, 4, true).color == 0xFFFF && marks_at(squeezed, w, h, 11, 4, true).alpha == 0);
    assert(marks_at(squeezed, w, h, 10, 5, true).alpha == 0x99 && marks_at(squeezed, w, h, 10, 5, true).color == 0);
    assert(marks_at(squeezed, w, h, 30, 14, true).color == 0xFFFF && marks_at(squeezed, w, h, 0, 0, true).color == look.ground);
    // The overlay with it has more marks than the one without, and the one without is the plain one.
    size_t with = 0, without = 0, plain = 0;
    overlay_marks(squeezed, w, h, 0, nullptr, with, nullptr, nullptr, true);
    overlay_marks(squeezed, w, h, 0, nullptr, without);
    overlay_marks(look, w, h, 0, nullptr, plain);
    assert(with == without + 3 && without == plain);
  }
  {
    uint8_t depth[64];
    bool by_column = true;
    int from = -1;
    assert(overlay_shade(Look{}, w, h, 0, depth, by_column, from) == 0);
  }

  // A picture of every colour, and what the three blends in turn make of it, upright.
  std::vector<uint16_t> picture(w * h), want(w * h);
  for (int i = 0; i < w * h; ++i) picture[i] = static_cast<uint16_t>(i * 2654435761u >> 16);
  for (int y = 0; y < h; ++y)
    for (int x = 0; x < w; ++x) {
      uint16_t p = blend(picture[y * w + x], 0, fade_at(y, h));
      p = blend(p, look.ground, corner_at(x, y, w, h, look.radius));
      if (x >= 30 && x < 33 && y >= 14 && y < 16) {
        const uint32_t c = name[(y - 14) * 3 + (x - 30)];
        p = blend(p, rgb565(c), c >> 24);
      }
      want[y * w + x] = p;
    }
  auto near = [](uint16_t a, uint16_t b) {
    const int dr = ((a >> 11) & 31) - ((b >> 11) & 31), dg = ((a >> 5) & 63) - ((b >> 5) & 63), db = (a & 31) - (b & 31);
    return dr * dr <= 1 && dg * dg <= 4 && db * db <= 1;
  };
  for (int turn : {0, 90, 180, 270}) {
    const int tw = turned_w(w, h, turn), th = turned_h(w, h, turn);
    // The picture as the app turns it, a row wider than the card (a decoder's stride).
    const int stride = tw + 3;
    std::vector<uint16_t> turned(stride * th, 0x7777);
    for (int y = 0; y < h; ++y)
      for (int x = 0; x < w; ++x) {
        const Rect g = in_turned(Rect{x, y, 1, 1}, turn, w, h);
        turned[g.y * stride + g.x] = picture[y * w + x];
      }
    Overlay o{tw, th};
    std::vector<uint8_t> depth(std::max(w, h));
    o.shade_count = overlay_shade(look, w, h, turn, depth.data(), o.shade_by_column, o.shade_from);
    o.shade = depth.data();
    size_t pixels = 0;
    o.count = overlay_marks(look, w, h, turn, nullptr, pixels);
    std::vector<OverlaySegment> segments(o.count);
    std::vector<uint8_t> alpha(pixels);
    std::vector<uint16_t> color(pixels);
    assert(overlay_marks(look, w, h, turn, segments.data(), pixels, alpha.data(), color.data()) == o.count);
    o.segments = segments.data(), o.alpha = alpha.data(), o.color = color.data();
    lay_overlay(turned.data(), stride, o);
    for (int y = 0; y < h; ++y)
      for (int x = 0; x < w; ++x) {
        const Rect g = in_turned(Rect{x, y, 1, 1}, turn, w, h);
        assert(near(turned[g.y * stride + g.x], want[y * w + x]));
      }
    for (int gy = 0; gy < th; ++gy) assert(turned[gy * stride + tw] == 0x7777);  // nothing past the card's row
    // The shade darkens the card's bottom rows: on a card on its side, columns. The marks hold the four corners and the
    // name, a few pixels, never the middle of the card.
    assert(o.shade_by_column == (turn % 180 != 0) && o.shade_count == shade);
    const Rect bottom = in_turned(Rect{20, h - 1, 1, 1}, turn, w, h), top = in_turned(Rect{20, 0, 1, 1}, turn, w, h);
    const int along = o.shade_by_column ? bottom.x : bottom.y, away = o.shade_by_column ? top.x : top.y;
    assert(along >= o.shade_from && along < o.shade_from + o.shade_count);
    assert(away < o.shade_from || away >= o.shade_from + o.shade_count);
    if (turn == 90) assert(bottom.x == 0);       // the card's bottom along the glass's left
    if (turn == 270) assert(bottom.x == tw - 1);  // and along its right
    assert(pixels < static_cast<size_t>(w * h) / 4);
    const Rect middle = in_turned(Rect{20, 8, 1, 1}, turn, w, h);
    for (const OverlaySegment &seg : segments) assert(seg.y != middle.y || middle.x < seg.from || middle.x >= seg.to);
  }
}

int main() {
  none();
  framing();
  marking();
  made();
  pulling();
  loading();
  links();
  panel();
  placing();
  cutting();
  turning();
  composing();
  std::puts("live_view: ok");
  return 0;
}
