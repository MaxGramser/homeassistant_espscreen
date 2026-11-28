// The parts a card is made of, as this glass shows them (docs/GLASS_KINDS.md). A card says what a thing is (a disc
// that says a state, a key chosen among its row, a mark in a state's colour, a part that waits) and gets back how it
// stands on the glass it is on. It never asks which glass that is.
//
//   theme.h          the tones: a role as a colour on a glass that is lit, as an ink on a glass of ink
//   theme_parts.h    the parts (this file): one name and one meaning each, and the one place the two glasses part
//   theme_lit.h      every part on a glass that is lit      (namespace theme::on_lit)
//   theme_ink.h      every part on a glass of ink            (namespace theme::on_ink)
//
// Every part below is one line: THEME_ON_GLASS picks the stylesheet. In a build that cannot stand on a glass of ink
// (glass_kind.h) it is the lit one at compile time, and theme_ink.h is not in the build at all.
//
// A new part: say here what it is, give it to both stylesheets, and hold the ink one in tests/test_theme_parts.cpp
// (a glyph never stands on a tone between ink and paper). A new kind of glass: a third stylesheet and a third arm
// here; no card changes. tests/test_glass_kinds.py holds that no file outside this layer asks which glass it is on.
//
// Included at the end of the pure half of theme.h, and only there: read by itself this file is empty, so the order
// in which a build includes the component's headers does not matter. Free of LVGL. The LVGL half that puts a part on
// an object (theme::wear, theme::rim) is at the end of theme.h.
#if defined(THEME_READS_ITS_PARTS) && !defined(THEME_PARTS_READ)
#define THEME_PARTS_READ

namespace theme {

// How a part stands on the glass: its ground, what stands on that (a glyph, a word), how much of the ground shows,
// and the line around it.
struct Dress {
  uint32_t ground = 0;
  uint32_t ink = 0;
  uint8_t opa = 255;
  uint8_t rim = 0;    // pixels; 0 for no line
  uint32_t line = 0;  // the line's colour, where there is one
};
// The tones of a clock face of the screensaver, in the face's own look (module_clock_faces.cpp).
struct ClockTones {
  uint32_t face = 0, ink = 0, soft = 0, tick = 0, minor = 0, hand = 0, edge = 0, accent = 0, raised = 0;
  bool hands_rimmed = false;  // a hand has a rim of the face's tone around it
};
// And of Bauhaus: the school's five colours, the clock's hands and marks, and its dial.
struct BauhausTones { uint32_t cream = 0, black = 0, red = 0, yellow = 0, blue = 0, hand = 0, mark = 0, face = 0; };

}  // namespace theme

#define THEME_READS_A_STYLESHEET
#include "theme_lit.h"
#ifdef GLASS_MAY_BE_INK
#include "theme_ink.h"
#define THEME_ON_GLASS(part) (inked() ? on_ink::part : on_lit::part)
#else
#define THEME_ON_GLASS(part) (on_lit::part)
#endif
#undef THEME_READS_A_STYLESHEET

namespace theme {

// ---- A state's colour on its way to the glass
// Home Assistant's colour for a state, as a fill: itself, with the greys of "off" taken from the table in dark.
inline uint32_t state(uint32_t color) { return THEME_ON_GLASS(state(color)); }
// The same drawn as a glyph, a line or words on the page or a card.
inline uint32_t foreground(uint32_t color) { return THEME_ON_GLASS(foreground(color)); }
// The pale share of a colour where nothing stands on it: a halo, an unlit segment, the area under a graph.
inline uint32_t tint(uint32_t color, uint8_t amount) { return THEME_ON_GLASS(tint(color, amount)); }
// The pale ground under a glyph or under words: a module's own disc, a badge, an empty cover's square.
inline uint32_t field(uint32_t color, uint8_t amount) { return THEME_ON_GLASS(field(color, amount)); }
// A tile's icon in its state's colour.
inline uint32_t icon(uint32_t color) { return THEME_ON_GLASS(icon(color)); }
// A tile's disc and the glyph on it, where the pair says whether the tile is on (tile_disc gives both).
inline uint32_t disc(uint32_t color) { return THEME_ON_GLASS(disc(color)); }
inline uint32_t on_disc(uint32_t color) { return THEME_ON_GLASS(on_disc(color)); }
// A slider's track under its fill.
inline uint32_t track(uint32_t color) { return THEME_ON_GLASS(track(color)); }
// What a colour marks: a dot before a state, a robot's light bar, a lamp's own colour on its icon, the line of now.
inline uint32_t mark(uint32_t color) { return THEME_ON_GLASS(mark(color)); }
// The same on the dark stage (a ring at the door): a mark in a role's colour.
inline uint32_t stage_mark(Role role) { return THEME_ON_GLASS(stage_mark(role)); }
// The glyph or the number of what is off or cannot be reached.
inline uint32_t absent() { return THEME_ON_GLASS(absent()); }
// Words that stand back: a second line, a time, a placeholder. `amount` of the words' own colour over their ground.
inline uint32_t soft(uint32_t words, uint32_t ground, uint8_t amount) { return THEME_ON_GLASS(soft(words, ground, amount)); }
// The ground of the one chosen among its row (a mode in use), in the colour Home Assistant gives that choice.
inline uint32_t chosen(uint32_t color) { return THEME_ON_GLASS(chosen(color)); }
// What lies over a page while a sheet stands on it.
inline uint32_t scrim() { return THEME_ON_GLASS(scrim()); }
// The knob of a switch.
inline uint32_t toggle_knob(bool on) { return THEME_ON_GLASS(toggle_knob(on)); }

// ---- A card and what stands in it
// Keys drawn inside a card of any colour (a wide tile's direct controls): a shade away from the card, towards the
// middle, so they read on white, on a pastel and on graphite alike.
inline uint32_t key_on(uint32_t card, uint8_t depth) { return THEME_ON_GLASS(key_on(card, depth)); }
// A card under a finger (firmware 0.2.95+).
inline uint32_t pressed(uint32_t card) { return THEME_ON_GLASS(pressed(card)); }
inline uint32_t pressed(Face f) { return THEME_ON_GLASS(pressed(f)); }
// The card's colour as this look draws it, and one kept as its light value (a tile's background: a swatch, or 0).
inline uint32_t surface(Face f) { return THEME_ON_GLASS(surface(f)); }
inline uint32_t surface(uint32_t own) { return THEME_ON_GLASS(surface(own)); }
// The hairline around a card.
inline uint32_t outline(Face f) { return THEME_ON_GLASS(outline(f)); }
inline uint32_t outline(uint32_t own) { return THEME_ON_GLASS(outline(own)); }
// A key in a colour of its own (KEY_SWATCHES), by its name; 0 for none.
inline uint32_t key_swatch(const std::string &name) {
  for (const auto &s : KEY_SWATCHES) if (name == s.name) return THEME_ON_GLASS(key_swatch(s.key));
  return 0;
}

// ---- Lines and strengths
// The line that sets a key off from its card, in pixels.
inline int hairline() { return THEME_ON_GLASS(hairline()); }
// The line a ground needs to be a shape at all where its colour is the card's own; 0 where its colour says it.
inline int shape_rim() { return THEME_ON_GLASS(shape_rim()); }
// A line in a colour of its own.
inline uint32_t line(uint32_t color) { return THEME_ON_GLASS(line(color)); }
// The strength of a part a lit glass shows faintly and that holds nothing to read: a glow, a key that leads nowhere.
inline uint8_t gone(uint8_t opa) { return THEME_ON_GLASS(gone(opa)); }
// The strength of a part a lit glass dims but that must still be read: a row that waits, a ring around a mark.
inline uint8_t whole(uint8_t opa) { return THEME_ON_GLASS(whole(opa)); }
// The strength of a ground that lets what lies under it through.
inline uint8_t solid(uint8_t opa) { return THEME_ON_GLASS(solid(opa)); }
// Whether this glass shows a shade at all: a part at part strength, words on a picture under a shade. Asked by the
// few that leave something out or put it elsewhere where there is none (a ring at half strength, a picture under a
// tile's words). It is no way to ask which glass this is: a colour or a ground comes from a part above.
inline bool shades() { return THEME_ON_GLASS(shades()); }

// ---- The stage: a view over the whole glass that is dark in both looks where the glass is lit (a player, a clock
// at rest, a camera)
// Its ground, from the colour the view would take there (a cover's, or black).
inline uint32_t stage_ground(uint32_t own) { return THEME_ON_GLASS(stage_ground(own)); }
// Whether it takes a colour read from a cover.
inline bool stage_coloured(bool own) { return THEME_ON_GLASS(stage_coloured(own)); }
// The words and glyphs on it.
inline uint32_t stage_ink() { return THEME_ON_GLASS(stage_ink()); }

// ---- Parts with a ground and what stands on it
// A disc that says a state by the glyph on it: an alarm's, a lock's, the head of a calendar. `on` is whether the
// state is the one the disc stands for (armed, locked, an event running); `amount` is the pale share where it has one.
inline Dress state_disc(uint32_t color, bool available, bool on, uint8_t amount = 38) {
  return THEME_ON_GLASS(state_disc(color, available, on, amount));
}
// A tile's own disc and its glyph; `key` for a key tile, whose circle is the tile itself.
inline Dress tile_disc(uint32_t color, bool available, bool key) { return THEME_ON_GLASS(tile_disc(color, available, key)); }
// The words a key tile carries on its circle.
inline uint32_t on_key(uint32_t color, bool available) { return THEME_ON_GLASS(on_key(color, available)); }
// One half of a switch between two views (Daily, Hourly), chosen or not.
inline Dress half(bool chosen) { return THEME_ON_GLASS(half(chosen)); }
// A dot of a pager: the page on the glass, or another, which is `rest` at `rest_opa` where the glass shows that.
inline Dress pager_dot(bool current, Role rest, uint8_t rest_opa = 255) { return THEME_ON_GLASS(pager_dot(current, rest, rest_opa)); }
// A key that is a haze of the words' colour over what lies under it.
inline Dress haze(uint32_t words, uint8_t opa) { return THEME_ON_GLASS(haze(words, opa)); }
// A body in a colour of its own, drawn full or as its outline: the sun by day, the moon by night.
inline Dress orb(uint32_t color, bool full) { return THEME_ON_GLASS(orb(color, full)); }
// A rail something runs along: `amount` of the words' colour over the ground.
inline Dress rail(uint32_t words, uint32_t ground, uint8_t amount) { return THEME_ON_GLASS(rail(words, ground, amount)); }

// ---- A calendar's own colour on the calendar card (calendar_card.h): what marks an event, its block, the words on
// it, a progress track, and each of the first three once the event is past.
inline uint32_t calendar_key(uint32_t c) { return THEME_ON_GLASS(calendar_key(c)); }
inline uint32_t calendar_block(uint32_t c) { return THEME_ON_GLASS(calendar_block(c)); }
inline uint32_t calendar_ink(uint32_t c) { return THEME_ON_GLASS(calendar_ink(c)); }
inline uint32_t calendar_track(uint32_t c) { return THEME_ON_GLASS(calendar_track(c)); }
inline uint32_t calendar_key_past(uint32_t c) { return THEME_ON_GLASS(calendar_key_past(c)); }
inline uint32_t calendar_block_past(uint32_t c) { return THEME_ON_GLASS(calendar_block_past(c)); }
inline uint32_t calendar_ink_past(uint32_t c) { return THEME_ON_GLASS(calendar_ink_past(c)); }

// ---- The screensaver's clock faces, each in the face's own look (dark, light, or the screen's)
inline ClockTones clock(bool in_dark) { return THEME_ON_GLASS(clock(in_dark)); }
inline BauhausTones bauhaus(bool in_dark) { return THEME_ON_GLASS(bauhaus(in_dark)); }

}  // namespace theme

#endif  // THEME_READS_ITS_PARTS
