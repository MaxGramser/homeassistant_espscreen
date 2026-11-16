#include "screen_text_en.h"
// The colour table (firmware 0.2.54): the light look stays the design it was, the dark look reads well beside a bed.
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_theme.cpp -o /tmp/test_theme && /tmp/test_theme
#define THEME_TEST
#include "components/smart_display/theme.h"
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <type_traits>

using namespace theme;

static double channel(uint32_t value) {
  const double c = value / 255.0;
  return c <= 0.04045 ? c / 12.92 : std::pow((c + 0.055) / 1.055, 2.4);
}
static double luminance(uint32_t color) {
  return 0.2126 * channel(color >> 16 & 0xFF) + 0.7152 * channel(color >> 8 & 0xFF) + 0.0722 * channel(color & 0xFF);
}
// WCAG contrast ratio of two colours.
static double contrast(uint32_t a, uint32_t b) {
  double la = luminance(a), lb = luminance(b);
  if (la < lb) std::swap(la, lb);
  return (la + 0.05) / (lb + 0.05);
}
static int channel_gap(uint32_t a, uint32_t b) {
  int gap = 0;
  for (int shift = 0; shift <= 16; shift += 8) gap = std::max(gap, std::abs(int(a >> shift & 0xFF) - int(b >> shift & 0xFF)));
  return gap;
}
static void look(bool on) { TestLook::set(on, on); }

int main() {
  // ---- the light look is the design as it was
  assert(ROLES[PAGE].light == 0xE7E7E7 && ROLES[CARD].light == 0xFFFFFF && ROLES[LINE].light == 0xDDDDDD);
  assert(ROLES[INK].light == 0x1B1B1B && ROLES[MUTED].light == 0x616161 && ROLES[SLATE].light == 0x46525E);
  assert(ROLES[ACCENT].light == 0x009FE3 && ROLES[OFF].light == ha::GREY && ROLES[KNOB].light == 0xFFFFFF);
  look(false);
  assert(hex(PAGE) == 0xE7E7E7 && hex(INK) == 0x1B1B1B);

  // ---- mixing is LVGL's own: the ends are the two colours, the middle rounds down
  assert(mix(0x123456, 0xABCDEF, 255) == 0x123456 && mix(0x123456, 0xABCDEF, 0) == 0xABCDEF);
  assert(mix(0xFFFFFF, 0x000000, 128) == 0x808080);
  // The old tile circle (the state colour at 38 over white) and icon (at 205 over #333333) are exactly what tint() and
  // icon() give in the light look.
  for (uint32_t accent : {ha::AMBER, ha::TEAL, ha::INDIGO, ha::DEEP_ORANGE, ha::GREY}) {
    assert(tint(accent, 38) == mix(accent, 0xFFFFFF, 38));
    assert(icon(accent) == mix(accent, 0x333333, 205));
    assert(state(accent) == accent && foreground(accent) == accent);
  }
  // The halos and cover tracks that were written out by hand before are the same colours within two steps.
  assert(channel_gap(tint(ha::TEAL, 36), 0xDCF0EE) <= 2 && channel_gap(tint(ha::BLUE, 36), 0xE1EFFD) <= 2);
  assert(channel_gap(tint(ha::ORANGE, 36), 0xFFF0DA) <= 2 && channel_gap(tint(ha::RED, 36), 0xFDE4E2) <= 2);
  assert(channel_gap(tint(ha::SKY, 22), 0xEAF5FC) <= 2);
  assert(channel_gap(tint(ha::PURPLE, 37), 0xEFE8F7) <= 2 && channel_gap(tint(ha::PURPLE, 80), 0xDDD0EF) <= 2);
  assert(fill_opacity() == 51);

  // ---- named card colours: identity in light, deep in dark, the normal card for none or an unknown colour
  assert(SWATCH_COUNT == 9 && swatch("red") == 0xFADADD && swatch("gray") == 0xE5E7EB && swatch("none") == 0 && swatch("") == 0);
  assert(surface(0) == 0xFFFFFF && surface(0xFADADD) == 0xFADADD && surface(0x123456) == 0x123456);
  assert(outline(0) == 0xDDDDDD && outline(0xFADADD) == mix(0xFADADD, 0x000000, 220));
  assert(key_on(0xFFFFFF, 236) == mix(0xFFFFFF, 0x000000, 236));
  // A card under a finger: an eighth towards black, on a pastel too.
  assert(pressed(0xFFFFFF) == 0xE0E0E0 && pressed(0xD9EEDC) == mix(0xD9EEDC, 0x000000, 224));
  assert(lightness(pressed(0xFFFFFF)) < lightness(hex(PAGE)));

  // ---- the dark look
  look(true);
  assert(hex(PAGE) == 0x000000);
  assert(surface(0) == ROLES[CARD].dark && surface(0x123456) == ROLES[CARD].dark);
  for (const auto &s : SWATCHES) {
    assert(surface(s.light) == s.dark);
    // Light words read on every dark card colour, the slate of a value too.
    assert(contrast(ROLES[INK].dark, s.dark) >= 7.0);
    assert(contrast(ROLES[SLATE].dark, s.dark) >= 4.5);
    assert(contrast(ROLES[INK].light, s.light) >= 7.0);
  }
  // Text reads in both looks: names and values, secondary and quiet words, the top bar on the page.
  for (bool on : {false, true}) {
    look(on);
    assert(contrast(hex(INK), hex(CARD)) >= 7.0 && contrast(hex(INK), hex(PAGE)) >= 7.0);
    assert(contrast(hex(MUTED), hex(CARD)) >= 4.5 && contrast(hex(SUBTLE), hex(CARD)) >= 4.5);
    assert(contrast(hex(SLATE), hex(PAGE)) >= 4.5 && contrast(hex(INK_SOFT), hex(RAISED)) >= 4.5);
    assert(contrast(hex(INK), hex(RAISED)) >= 7.0 && contrast(hex(INK), hex(TRACK)) >= 7.0);
    assert(contrast(hex(ON_ACCENT), hex(BUTTON_DARK)) >= 4.5);
  }
  // The blue keys keep at least the contrast they always had (white on #009FE3, just under 3:1).
  look(false);
  const double blue_light = contrast(hex(ON_ACCENT), hex(ACCENT));
  look(true);
  assert(blue_light > 2.9 && contrast(hex(ON_ACCENT), hex(ACCENT)) >= blue_light);
  look(true);
  // Surfaces step up from the black page, a raised card and a key under a finger stand out.
  assert(lightness(hex(PAGE)) < lightness(hex(CARD)) && lightness(hex(CARD)) < lightness(hex(LINE)));
  assert(lightness(hex(CARD)) < lightness(hex(RAISED)) && lightness(hex(KEY)) < lightness(hex(KEY_PRESSED)));
  assert(lightness(hex(CARD)) < 40 && lightness(hex(INK)) > 200);
  // Dark greys land on the same step of red, green and blue on the panel (RGB565), so they stay grey.
  for (int role = 0; role < ROLE_COUNT; ++role) {
    const uint32_t c = ROLES[role].dark;
    const uint32_t r = c >> 16 & 0xFF, g = c >> 8 & 0xFF, b = c & 0xFF;
    if (r == g && g == b && r > 0 && r < 0xFF) assert((r >> 3) * 2 == (g >> 2));
  }

  // ---- an instrument (plugin API 0.27): dark in both looks, its words read on it, its lines show and stay quiet
  for (bool d : {false, true}) {
    auto v = [d](Role r) { return d ? ROLES[r].dark : ROLES[r].light; };
    assert(lightness(v(INSTRUMENT)) < 40);
    assert(contrast(v(INSTRUMENT_INK), v(INSTRUMENT)) >= 12.0);
    assert(contrast(v(INSTRUMENT_MUTED), v(INSTRUMENT)) >= 4.5);
    assert(contrast(v(INSTRUMENT_GLOW), v(INSTRUMENT)) >= 7.0);
    assert(contrast(v(INSTRUMENT_LINE), v(INSTRUMENT)) >= 1.4 && contrast(v(INSTRUMENT_LINE), v(INSTRUMENT)) < 3.0);
  }
  // A card that is an instrument's face (0.28): the instrument's ground and line in both looks, apart from every swatch.
  const bool was = dark;
  for (bool d : {false, true}) {
    look(d);
    assert(surface(Face::instrument()) == hex(INSTRUMENT) && outline(Face::instrument()) == hex(INSTRUMENT_LINE));
    // A press on it shows in both looks: its face is dark in both, so the press goes towards white in both.
    assert(lightness(pressed(Face::instrument())) > lightness(hex(INSTRUMENT)));
    // A swatch kept as its light value is that swatch; 0 and any other value is the card.
    for (size_t i = 0; i < SWATCH_COUNT; ++i) assert(Face::of(SWATCHES[i].light) == (Face{Face::SWATCH, uint8_t(i)}));
    assert(Face::of(0) == Face{} && surface(Face{}) == hex(CARD) && surface(0u) == hex(CARD));
    assert(Face::instrument().key() != 0 && Face{}.key() == 0);
  }
  look(was);

  // ---- Home Assistant's colours in the dark look
  assert(state(ha::GREY) == ROLES[OFF].dark && state(0xCFCFCF) == ROLES[HISTORY_OFF].dark && state(0xE6E6E6) == ROLES[HISTORY_EMPTY].dark);
  assert(state(ha::AMBER) == ha::AMBER && state(ha::TEAL) == ha::TEAL);
  // Bright state colours stay themselves; the deep ones are lifted until they read on graphite.
  assert(foreground(ha::AMBER) == ha::AMBER && foreground(ha::LIGHT_BLUE) == ha::LIGHT_BLUE);
  for (uint32_t deep : {ha::INDIGO, ha::DEEP_PURPLE, uint32_t{0}}) {
    assert(lightness(foreground(deep)) > lightness(deep));
    assert(contrast(foreground(deep), hex(CARD)) >= 3.0);
  }
  // A circle stays dark and tinted, its icon light; a slider track stays dark.
  for (uint32_t accent : {ha::AMBER, ha::TEAL, ha::INDIGO, ha::GREY, ha::DEEP_ORANGE}) {
    assert(lightness(tint(accent, 38)) < 110 && lightness(tint(accent, 51)) < 120);
    assert(contrast(icon(accent), tint(accent, 38)) >= 3.0);
  }
  // Keys in a card are lighter than the card, its hairline too; so is the card under a finger.
  assert(lightness(key_on(hex(CARD), 236)) > lightness(hex(CARD)));
  assert(pressed(hex(CARD)) == mix(hex(CARD), 0xFFFFFF, 224) && lightness(pressed(hex(CARD))) > lightness(hex(CARD)));
  assert(lightness(outline(0xFADADD)) > lightness(surface(0xFADADD)));
  assert(fill_opacity() < 51);

  // ---- the look is read here and written only by set_dark() and a card's scope (theme.h, Looks)
  static_assert(std::is_same<decltype(dark), const bool &>::value && std::is_same<decltype(screen_dark), const bool &>::value,
                "theme::dark and theme::screen_dark are read-only");
  assert(&dark == &Looks::now && &screen_dark == &Looks::screen);

  // ---- a card's look (docs/THEME.md "A card's look"): a scope is the screen's look or the other, then gives back what
  // was there, nested or not; the screen's own look never moves
  for (bool screen : {false, true}) {
    TestLook::set(screen, screen);
    {
      LookScope other(true);
      assert(dark == !screen && screen_dark == screen);
      {
        LookScope plain(false);
        assert(dark == screen);
        {
          LookScope again(true);
          assert(dark == !screen);
        }
        assert(dark == screen);
      }
      assert(dark == !screen);
      other.end();
      assert(dark == screen);
    }
    assert(dark == screen && screen_dark == screen);
    // A scope that ends early inside another gives back the look it found, not the screen's.
    {
      LookScope outer(true);
      LookScope inner(false);
      inner.end();
      assert(dark == !screen);
    }
    assert(dark == screen);
    assert(hex_in(CARD, true) == ROLES[CARD].dark && hex_in(CARD, false) == ROLES[CARD].light);
  }
  look(false);
  return 0;
}

// Home Assistant's palette (frontend src/resources/theme/color/color.globals.ts, as its 2026.9 frontend serves it): the
// state colours every card takes are these, value for value.
namespace palette_check {
using namespace theme::ha;
static_assert(RED == 0xF44336 && PURPLE == 0x926BC7 && DEEP_PURPLE == 0x6E41AB && INDIGO == 0x3F51B5 && BLUE == 0x2196F3,
              "theme.h ha:: must hold Home Assistant's palette");
static_assert(LIGHT_BLUE == 0x03A9F4 && CYAN == 0x00BCD4 && TEAL == 0x009688 && GREEN == 0x4CAF50 && LIME == 0xCDDC39,
              "theme.h ha:: must hold Home Assistant's palette");
static_assert(YELLOW == 0xFFEB3B && AMBER == 0xFFC107 && ORANGE == 0xFF9800 && DEEP_ORANGE == 0xFF6F22 && LIGHT_GREY == 0xBDBDBD,
              "theme.h ha:: must hold Home Assistant's palette");
static_assert(GREY == 0x9E9E9E && BLUE_GREY == 0x607D8B && ICE == 0xC0E0FF, "theme.h ha:: must hold Home Assistant's palette");
}  // namespace palette_check
