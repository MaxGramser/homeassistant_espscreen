#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include "screen_text.h"
#include "tile_icon.h"
#include "tile_icon_names.h"
#include "tile_palette.h"
#include "ui_scale.h"
#include <algorithm>

// The card a Home Assistant automation puts over the whole screen (api action
// show_alert). Pure text and lookups so both boards apply the same rules and
// tests/test_alert_overlay.cpp can check them; the profiles do the LVGL work.
namespace screen_alert {
constexpr const char *FALLBACK_ICON = "alert-outline";
constexpr const char *FALLBACK_BUTTON = "OK";
constexpr uint32_t DEFAULT_CARD_COLOR = 0;  // the normal card: theme::surface(0)
constexpr int MAX_TIMEOUT_SECONDS = 86400;

struct Alert {
  std::string title, subtitle, icon, button;  // icon: UTF-8 glyph for the icon font
  std::string button2;  // the second button (firmware 0.3.3+, show_alert_choice); empty: the card has one button
  uint32_t button_color = 0, button2_color = 0;  // a key colour (theme::KEY_SWATCHES); 0: the button's own paint
  uint32_t color = DEFAULT_CARD_COLOR;
  int timeout_seconds = 0;  // 0: stays until OK
  bool flash = false;
};

inline bool blank(char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r'; }
inline std::string trimmed(const std::string &text) {
  size_t begin = 0, end = text.size();
  while (begin < end && blank(text[begin])) ++begin;
  while (end > begin && blank(text[end - 1])) --end;
  return text.substr(begin, end - begin);
}
inline std::string lowercase(std::string text) {
  for (auto &c : text) if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
  return text;
}
// Cuts on a UTF-8 boundary: LVGL must never get half a code point. A text cut short ends in "...", within the limit,
// the way LVGL ends a line it cannot show whole (firmware 0.2.104; before, a subtitle that filled its lines exactly
// stopped in the middle of a word). A limit too small for the dots cuts without them.
inline std::string clipped(const std::string &text, size_t max_bytes) {
  if (text.size() <= max_bytes) return text;
  const std::string dots = max_bytes > 3 ? "..." : "";
  size_t end = max_bytes - dots.size();
  while (end > 0 && (static_cast<unsigned char>(text[end]) & 0xC0) == 0x80) --end;
  return text.substr(0, end) + dots;
}
// "doorbell", "mdi:doorbell" or the hex codepoint "F12E6" of a glyph the fonts carry;
// anything else draws the warning triangle.
inline uint32_t icon_codepoint(const std::string &value) {
  std::string name = lowercase(trimmed(value));
  if (name.rfind("mdi:", 0) == 0) name.erase(0, 4);
  if (uint32_t code = tile_icon::named(name)) return code;
  const uint32_t code = tile_icon::codepoint(name);
  if (code && tile_icon::carried(code)) return code;
  return tile_icon::named(FALLBACK_ICON);
}
inline int clamp_timeout(int seconds) {
  return seconds < 0 ? 0 : seconds > MAX_TIMEOUT_SECONDS ? MAX_TIMEOUT_SECONDS : seconds;
}
inline Alert make(const std::string &title, const std::string &subtitle, const std::string &icon,
                  const std::string &color, const std::string &button, int timeout, bool flash,
                  size_t title_max, size_t subtitle_max, size_t button_max, const std::string &button2 = "",
                  const std::string &button_color = "", const std::string &button2_color = "") {
  Alert alert;
  alert.title = clipped(trimmed(title), title_max);
  if (alert.title.empty()) alert.title = screen_text::tr(screen_text::txt::alert_notification);
  alert.subtitle = clipped(trimmed(subtitle), subtitle_max);
  alert.button = clipped(trimmed(button), button_max);
  if (alert.button.empty()) alert.button = FALLBACK_BUTTON;
  alert.button2 = clipped(trimmed(button2), button_max);
  alert.button_color = theme::key_swatch(lowercase(trimmed(button_color)));
  alert.button2_color = alert.button2.empty() ? 0 : theme::key_swatch(lowercase(trimmed(button2_color)));
  alert.icon = tile_icon::utf8(icon_codepoint(icon));
  const uint32_t card = tile_palette::color(lowercase(trimmed(color)));
  alert.color = card ? card : DEFAULT_CARD_COLOR;
  alert.timeout_seconds = clamp_timeout(timeout);
  alert.flash = flash;
  return alert;
}

// Where the parts of the alert card stand (firmware 0.2.103+), worked out on the glass the screen draws on.
//
// The card is drawn in the look's own pixels (ui::px: the standard look's at 170 dpi, the compact look's at 143 dpi),
// so it keeps its size in millimetres on every board, and then fitted to the canvas LVGL hands the screen, lying down or
// standing up. Nothing of it is written in a board file. The rules:
//
//  * The card is as wide as the look draws it, and never wider than the glass less an inset on each side. The icon,
//    the OK button and every distance keep their size, because a finger and an eye do; the text takes what is left.
//  * The title is one line of its font high, whatever that font is on this board, so a long title ends in an
//    ellipsis (LVGL only puts one on a label with a height). The subtitle takes the whole lines that fit between it
//    and the button, and ends in an ellipsis when its text is longer.
//  * With a camera picture the card makes room for it where it shows the most of that picture, in its own proportions:
//    across the top of the card, or on the left beside the words and the button (`above`, `beside`). A wide picture on
//    square glass goes on top, a standing doorbell camera on wide glass beside. On glass with no room for a picture at
//    all, the alert comes without it.
//
// Pure numbers, so tests/test_alert_overlay.cpp checks them and screen_manager/app/alert_layout.py can work out the same image box
// for ESP Screens (tests/test_alert_layout.py keeps the two alike); runtime_tiles::alert_place does the LVGL work.
// The subtitle's label is as tall as the whole lines that fit its room: a line cut in half across is no line at all, and
// a text too long for the lines there are ends in an ellipsis on the last one (long_mode: DOT).
inline int whole_lines(int room, int line) { return line > 0 ? room / line * line : room; }

struct Layout {
  int card_w = 0, card_h = 0;
  int icon_x = 0, icon_y = 0;
  int text_x = 0, text_w = 0;
  int title_y = 0, title_h = 0;
  int subtitle_y = 0, subtitle_h = 0;
  int button_x = 0, button_y = 0, button_w = 0, button_h = 0, button_inset = 0;
  int image_x = 0, image_y = 0, image_w = 0, image_h = 0;  // all 0 without an image
  int column_x = 0;  // where the column of words and the button starts: 0, or the right edge of a picture beside it
};

// The proportions of a camera picture before the screen has seen one: the design's 392 x 220, a camera's 16:9. Once
// the picture is there, its own proportions are used (runtime_tiles::camera_loaded lays the card out again).
constexpr int PICTURE_W = 392, PICTURE_H = 220;
// The largest a picture gets in the alert, in the look's pixels (ui::px): 392 wide and 300 high, about 58 x 45 mm on
// the standard look. A picture keeps that size in millimetres on every board, like everything else on the card, instead
// of growing with the glass: an alert is read at a glance, and the picture ESP Screens scales and sends for it stays
// small (at most 392 x 300 x 3 bytes on the wire at the standard look's density).
constexpr int PICTURE_MAX_W = 392, PICTURE_MAX_H = 300;

// How much of a picture of `aw` x `ah` proportions a frame of w x h shows, in pixels: the picture keeps its proportions
// inside the frame, so a frame wider or taller than the picture shows no more of it.
inline int picture_area(int w, int h, int aw, int ah) {
  if (w <= 0 || h <= 0 || aw <= 0 || ah <= 0) return 0;
  return std::min(w, h * aw / ah) * std::min(h, w * ah / aw);
}

// The card without a picture. `canvas_w` and `canvas_h` are the glass as LVGL draws it, `title_line` the line height of
// the title's font and `line` that of the subtitle's. ui::configure() must have run: every other size is the look's.
inline Layout plain(int canvas_w, int canvas_h, int title_line, int line) {
  const bool big = ui::large();
  Layout l;
  const int inset = ui::px(big ? 22 : 14);  // the card from the edge of the glass, and the button from the card's
  l.card_w = std::max(0, std::min(ui::px(big ? 420 : 292), canvas_w - 2 * inset));
  l.card_h = std::max(0, std::min(ui::px(big ? 320 : 196), canvas_h - 2 * inset));
  l.icon_x = ui::px(big ? 26 : 18);
  l.icon_y = ui::px(big ? 22 : 16);
  l.text_x = ui::px(big ? 90 : 62);
  l.text_w = std::max(0, l.card_w - l.text_x - l.icon_x);
  l.title_y = ui::px(big ? 26 : 16);
  l.title_h = title_line;
  l.subtitle_y = l.title_y + l.title_h + ui::px(big ? 10 : 7);
  l.button_w = ui::px(big ? 150 : 100);
  l.button_h = ui::px(big ? 60 : 40);
  l.button_inset = inset;
  l.button_x = l.card_w - inset - l.button_w;
  l.button_y = l.card_h - inset - l.button_h;
  l.subtitle_h = whole_lines(std::max(0, l.button_y - l.subtitle_y - ui::px(big ? 20 : 10)), line);
  return l;
}

// The picture across the top of the card, the words under it. The picture is as wide as the card less its inset, or
// narrower and in the middle when it is tall for its width; a card with a picture may come as close to the edge of the
// glass as its picture comes to the edge of the card. When that card is taller than the glass the subtitle gives up its
// second line first and the picture its height after that; on glass too low even for that, there is no picture
// (image_w and image_h 0).
inline Layout above(int canvas_w, int canvas_h, int title_line, int line, int aw, int ah) {
  const bool big = ui::large();
  Layout l = plain(canvas_w, canvas_h, title_line, line);
  const int image_inset = ui::px(big ? 14 : 10);
  const int widest = std::max(0, std::min(l.card_w - 2 * image_inset, ui::px(PICTURE_MAX_W)));
  l.image_h = std::min(widest * ah / aw, ui::px(PICTURE_MAX_H));
  int subtitle = ui::px(big ? 62 : 40);  // two lines of the subtitle between the title and the button
  const int image_gap = ui::px(16), button_gap = ui::px(4);
  const auto height = [&]() {
    return l.image_h + image_gap + ui::px(big ? 26 : 16) + title_line + ui::px(big ? 10 : 7) + subtitle + button_gap +
           l.button_h + l.button_inset;
  };
  const int over = height() - (canvas_h - 2 * image_inset);
  if (over > 0 &&
      ui::shrink({{&subtitle, std::min(subtitle, line)}, {&l.image_h, std::min(l.image_h, ui::px(96))}}, over) > 0)
    return plain(canvas_w, canvas_h, title_line, line);
  l.image_w = std::min(widest, l.image_h * aw / ah);
  l.image_x = (l.card_w - l.image_w) / 2;
  l.image_y = image_inset;
  const int shift = l.image_h + image_gap;
  l.card_h = std::max(0, std::min(height(), canvas_h - 2 * image_inset));
  l.icon_y += shift;
  l.title_y += shift;
  l.subtitle_y += shift;
  l.subtitle_h = whole_lines(subtitle, line);
  l.button_y = l.card_h - l.button_inset - l.button_h;
  return l;
}

// The picture on the left and the words and the button on the right, as on a card without a picture: the button stays
// against the right edge of the card, where it is on every alert. The words keep their column (never narrower than
// their narrowest); the picture takes the room beside them up to its largest size (the card grows with it, and may
// come as close to the edge of the glass as the picture comes to the edge of the card).
inline Layout beside(int canvas_w, int canvas_h, int title_line, int line, int aw, int ah) {
  const bool big = ui::large();
  Layout l = plain(canvas_w, canvas_h, title_line, line);
  const int image_inset = ui::px(big ? 14 : 10);
  const int room = canvas_w - 2 * l.button_inset;
  const int tallest = std::max(0, std::min(canvas_h - 4 * image_inset, ui::px(PICTURE_MAX_H)));
  const int narrowest = std::min(l.card_w, ui::px(big ? 300 : 210));
  const int column = std::max(narrowest, std::min(l.card_w, room - image_inset - tallest * aw / ah));
  l.image_h = std::max(0, std::min(tallest, std::min(room - column - image_inset, ui::px(PICTURE_MAX_W)) * ah / aw));
  l.image_w = l.image_h * aw / ah;
  // No smaller than the smallest picture above the words may get: less is a stamp, not a picture.
  if (l.image_h < std::min(tallest, ui::px(96))) return plain(canvas_w, canvas_h, title_line, line);
  l.card_h = std::max(l.card_h, l.image_h + 2 * image_inset);
  l.button_y = l.card_h - l.button_inset - l.button_h;
  const int shift = image_inset + l.image_w;  // the column of words starts where the picture ends
  l.card_w = shift + column;
  l.column_x = shift;
  l.image_x = image_inset;
  l.image_y = (l.card_h - l.image_h) / 2;
  l.icon_x += shift;
  l.text_x += shift;
  l.text_w = std::max(0, column - (l.text_x - shift) - (l.icon_x - shift));
  l.button_x = l.card_w - l.button_inset - l.button_w;
  return l;
}

// The card on this glass: without a picture, or with one where it shows the most of it, above the words or beside
// them. `aw` x `ah` are the proportions of the picture, PICTURE_W x PICTURE_H until the screen has one.
inline Layout layout(int canvas_w, int canvas_h, int title_line, int line, bool image, int aw = PICTURE_W,
                     int ah = PICTURE_H) {
  if (!image) return plain(canvas_w, canvas_h, title_line, line);
  if (aw <= 0 || ah <= 0) {
    aw = PICTURE_W;
    ah = PICTURE_H;
  }
  const Layout top = above(canvas_w, canvas_h, title_line, line, aw, ah);
  const Layout side = beside(canvas_w, canvas_h, title_line, line, aw, ah);
  return picture_area(side.image_w, side.image_h, aw, ah) > picture_area(top.image_w, top.image_h, aw, ah) ? side : top;
}
// The buttons along the bottom of the card (firmware 0.3.3+). One button stands against the right edge, as it always did.
// Two (show_alert_choice) share the whole row of the column in two equal halves, the first on the right: they read as one
// choice, each is as easy to hit as the card allows, and a word like "Remind me" fits on the CYD, where two buttons of
// the one button's width ended it in dots. Rendered against both of them standing on the right and against one at each
// edge, which pulled the two answers apart. Never over a picture beside the words: the row starts where the column does.
struct Buttons {
  int x = 0, w = 0;    // the first button, the one every alert has
  int x2 = 0, w2 = 0;  // the second: w2 is 0 without one
};
inline Buttons buttons(const Layout &l, bool two) {
  Buttons b{l.button_x, l.button_w};
  if (!two) return b;
  const int gap = ui::px(ui::large() ? 12 : 8);
  const int room = l.card_w - l.button_inset - (l.column_x + l.button_inset);
  b.w = b.w2 = std::max(0, (room - gap) / 2);
  b.x = l.card_w - l.button_inset - b.w;
  b.x2 = b.x - gap - b.w2;
  return b;
}
}  // namespace screen_alert
