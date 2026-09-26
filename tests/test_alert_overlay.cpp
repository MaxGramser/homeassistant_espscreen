#include "screen_text_en.h"
#define THEME_TEST
#include "components/smart_display/alert_overlay.h"
#include <cassert>
#include <cstdio>
int main() {
  using screen_alert::make;
  const auto alert = make("Someone's at the door", "Door 3, back entrance", "doorbell", "orange", "Coming", 60, true, 48, 160, 12);
  assert(alert.title == "Someone's at the door" && alert.subtitle == "Door 3, back entrance" && alert.button == "Coming");
  assert(alert.icon == tile_icon::utf8(0xF12E6) && alert.color == 0xFFE1C6 && alert.timeout_seconds == 60 && alert.flash);
  // Icon: a name from the set, with mdi: prefix, spaces or capitals, or the hex codepoint of a carried glyph.
  for (const char *icon : {"doorbell", "mdi:doorbell", " Doorbell ", "F12E6", "f12e6", "mdi:F12E6"})
    assert(screen_alert::icon_codepoint(icon) == 0xF12E6);
  // Unknown names, a codepoint the fonts lack and junk draw the warning triangle.
  for (const char *icon : {"", "unknown", "mdi:", "F0000", "F12E", "\xF0\x9F\x94\x94", "mdi:not-in-the-set"})
    assert(screen_alert::icon_codepoint(icon) == 0xF002A);
  // Colour: palette names in any case; empty, none and anything unknown keep the normal card.
  assert(make("x", "", "", "Red", "", 0, false, 48, 160, 12).color == 0xFADADD);
  assert(make("x", "", "", " mint ", "", 0, false, 48, 160, 12).color == 0xD5F0EA);
  for (const char *color : {"", "none", "auto", "#ff0000", "0xFF0000"})
    assert(make("x", "", "", color, "", 0, false, 48, 160, 12).color == screen_alert::DEFAULT_CARD_COLOR);
  // The normal card is no colour of its own: the look draws it (theme::surface(0)).
  assert(screen_alert::DEFAULT_CARD_COLOR == 0);
  // Timeout: 0 and negatives wait for OK; a day is the ceiling.
  assert(make("x", "", "", "", "", 0, false, 48, 160, 12).timeout_seconds == 0);
  assert(make("x", "", "", "", "", -5, false, 48, 160, 12).timeout_seconds == 0);
  assert(make("x", "", "", "", "", 999999, false, 48, 160, 12).timeout_seconds == 86400);
  assert(!make("x", "", "", "", "", 0, false, 48, 160, 12).flash);
  // Title: trimmed, never empty, cut on a UTF-8 boundary; the subtitle keeps its line breaks.
  assert(make("   ", "", "", "", "", 0, false, 48, 160, 12).title == "Notification");
  assert(make("  Hi \n", "", "", "", "", 0, false, 48, 160, 12).title == "Hi");
  assert(make("\xC3\xA9\xC3\xA9\xC3\xA9", "", "", "", "", 0, false, 3, 160, 12).title == "\xC3\xA9");
  assert(make("x", "line 1\nline 2", "", "", "", 0, false, 48, 160, 12).subtitle == "line 1\nline 2");
  assert(make("x", std::string(300, 'a'), "", "", "", 0, false, 48, 160, 12).subtitle == std::string(157, 'a') + "...");
  assert(make(std::string(100, 'b'), "", "", "", "", 0, false, 48, 160, 12).title == std::string(45, 'b') + "...");
  // A text that fits is kept as it is; one cut short on a UTF-8 boundary still ends in the dots.
  assert(make("x", std::string(160, 'a'), "", "", "", 0, false, 48, 160, 12).subtitle == std::string(160, 'a'));
  assert(make("\xC3\xA9\xC3\xA9\xC3\xA9", "", "", "", "", 0, false, 5, 160, 12).title == "\xC3\xA9...");
  // Button: trimmed and capped; empty falls back to OK.
  assert(make("x", "", "", "", "", 0, false, 48, 160, 12).button == "OK");
  assert(make("x", "", "", "", "  Open  ", 0, false, 48, 160, 12).button == "Open");
  assert(make("x", "", "", "", std::string(40, 'c'), 0, false, 48, 160, 12).button == std::string(9, 'c') + "...");
  // The second button (firmware 0.3.3+): none unless it is asked for, trimmed and capped like the first, never "OK".
  assert(make("x", "", "", "", "", 0, false, 48, 160, 12).button2.empty());
  assert(make("x", "", "", "", "", 0, false, 48, 160, 12, "   ").button2.empty());
  assert(make("x", "", "", "", "Accept", 0, false, 48, 160, 12, " Decline ").button2 == "Decline");
  assert(make("x", "", "", "", "", 0, false, 48, 160, 12, std::string(40, 'd')).button2 == std::string(9, 'd') + "...");
  // The generated table carries every font glyph by name.
  assert(tile_icon::named("lightbulb") == 0xF0335 && tile_icon::named("alert-outline") == 0xF002A);
  assert(tile_icon::named("nope") == 0 && tile_icon::named("") == 0);
  assert(tile_icon::carried(0xF0335) && tile_icon::carried(0xF002A) && !tile_icon::carried(0xF0000) && !tile_icon::carried(0));
  assert(tile_icon::NAME_COUNT > 150);

  // The card on the glass (firmware 0.2.103+). The two boards each look was drawn on get the card they always had.
  using screen_alert::layout;
  ui::configure(170, "standard");  // the 4-inch Guition: 480 x 480, headline 32 px, subtitle 25 px a line
  auto g = layout(480, 480, 32, 25, false);
  assert(g.card_w == 420 && g.card_h == 320 && g.icon_x == 26 && g.icon_y == 22 && g.text_x == 90 && g.text_w == 304);
  assert(g.title_y == 26 && g.title_h == 32 && g.subtitle_y == 68 && g.subtitle_h == 150);
  assert(g.button_w == 150 && g.button_h == 60 && g.button_inset == 22 && g.image_w == 0 && g.image_h == 0);
  g = layout(480, 480, 32, 25, true);  // with a camera image: the picture across the top, the words under it
  assert(g.card_w == 420 && g.card_h == 452 && g.image_x == 14 && g.image_y == 14 && g.image_w == 392 && g.image_h == 220);
  assert(g.icon_y == 258 && g.title_y == 262 && g.subtitle_y == 304 && g.subtitle_h == 50);  // two whole lines of 25
  ui::configure(143, "compact");  // the CYD lying down: 320 x 240, headline 21 px, subtitle 16 px a line
  auto c = layout(320, 240, 21, 16, false);
  assert(c.card_w == 292 && c.card_h == 196 && c.icon_x == 18 && c.icon_y == 16 && c.text_x == 62 && c.text_w == 212);
  assert(c.title_y == 16 && c.title_h == 21 && c.subtitle_y == 44 && c.subtitle_h == 80);  // five whole lines of 16
  assert(c.button_w == 100 && c.button_h == 40 && c.button_inset == 14);
  // Two buttons on the CYD share the row in two halves, the first on the right: 292 - 2 x 14 - 8 = 256, 128 each.
  auto two = screen_alert::buttons(c, true);
  assert(two.w == 128 && two.w2 == 128 && two.x == 292 - 14 - 128 && two.x2 == 14);
  auto one = screen_alert::buttons(c, false);
  assert(one.x == c.button_x && one.w == c.button_w && one.w2 == 0);
  // The picture keeps its size in millimetres, whatever the glass: a 1024 x 600 seven-inch shows the 16:9 picture the
  // Guition does, above the words.
  ui::configure(170, "standard");
  g = layout(1024, 600, 32, 25, true, 16, 9);
  assert(g.image_w <= 392 && g.image_h <= 300 && g.icon_y > g.image_y + g.image_h);
  // The 4.3-inch's 800 x 480 is not wide enough for a 16:9 picture beside the words: it stays above.
  ui::configure(217, "standard");
  g = layout(800, 480, 40, 32, true);
  assert(g.image_y < g.icon_y && g.icon_y > g.image_y + g.image_h);
  // But a standing doorbell camera (3:4) goes on the left of the words there, taller than it could be above them, and
  // the button stays against the right edge of the card.
  g = layout(800, 480, 40, 32, true, 3, 4);
  assert(g.image_x == ui::px(14) && g.image_x + g.image_w < g.icon_x && g.image_h > g.image_w && g.image_h == ui::px(300));
  assert(g.button_x == g.card_w - g.button_inset - g.button_w);
  // A square camera on the square Guition: above the words, as wide as it is tall, in the middle of the card.
  ui::configure(170, "standard");
  g = layout(480, 480, 32, 25, true, 1, 1);
  assert(g.image_w == g.image_h && g.image_x == (g.card_w - g.image_w) / 2 && g.image_h > 220 && g.card_h <= 452);
  ui::configure(143, "compact");
  // Standing up the glass is narrower: the card takes the glass less its insets, the icon and the button keep their size.
  c = layout(240, 320, 21, 16, false);
  assert(c.card_w == 212 && c.card_h == 196 && c.text_w == 212 - 62 - 18 && c.button_w == 100 && c.icon_x == 18);
  // On any glass, lying down or standing up, every part stays on the card and the card on the glass.
  for (const char *look : {"standard", "compact"}) {
    for (int dpi : {110, 133, 143, 149, 170, 190, 217, 294}) {
      ui::configure(dpi, look);
      const int title = ui::px(ui::large() ? 32 : 21), line = ui::px(ui::large() ? 25 : 16);
      for (int w : {240, 320, 480, 600, 800, 1024, 1280}) {
        for (int h : {240, 320, 480, 600, 800, 1024, 1280}) {
          for (int shape = 0; shape < 6; ++shape) {
            const bool image = shape > 0;
            const int aw[] = {0, 392, 16, 1, 3, 21}, ah[] = {0, 220, 9, 1, 4, 9};
            const auto l = layout(w, h, title, line, image, aw[shape], ah[shape]);
            assert(l.card_w <= w && l.card_h <= h);
            assert(l.text_x + l.text_w < l.card_w || l.text_w == 0);
            assert(l.title_h == title && l.title_y + l.title_h <= l.subtitle_y && l.subtitle_h % line == 0);
            assert(l.button_x >= 0 && l.button_y >= 0 || l.card_w < l.button_w + 2 * l.button_inset);
            assert(l.button_x + l.button_w <= l.card_w && l.button_y + l.button_h <= l.card_h);
            if (image) {
              assert(l.image_x + l.image_w <= l.card_w && l.image_y + l.image_h <= l.card_h);
              // The picture stands above the words or beside them, never over them or the button.
              const bool over_them = l.image_y + l.image_h < l.icon_y;
              const bool beside_them = l.image_x + l.image_w <= l.icon_x && l.image_x + l.image_w <= l.button_x;
              assert(l.image_w == 0 || over_them || beside_them);
              // A picture never takes the words' last line: the subtitle keeps a line, or what a card without one gets.
              assert(l.subtitle_h >= std::min(line, screen_alert::plain(w, h, title, line).subtitle_h) || l.image_h == 0);
            } else {
              assert(l.image_w == 0 && l.image_h == 0);
            }
            // Two buttons stay on the card, in the column of words (never over a picture beside them), side by side.
            const auto b = screen_alert::buttons(l, true);
            assert(b.x + b.w == l.card_w - l.button_inset && b.w == b.w2);
            assert(b.x2 + b.w2 < b.x || b.w == 0);
            assert(b.x2 >= l.column_x + l.button_inset - 1 || b.w == 0);
            if (image && l.image_w > 0 && l.column_x > 0) assert(b.x2 >= l.image_x + l.image_w || b.w == 0);
            // The words end above the button, however little room the glass leaves them.
            if (l.subtitle_h > 0) assert(l.subtitle_y + l.subtitle_h <= l.card_h - l.button_inset - l.button_h);
          }
        }
      }
    }
  }
  ui::configure(170, "standard");
  std::puts("test_alert_overlay: PASS");
}
