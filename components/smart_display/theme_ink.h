// The stylesheet of a glass of ink (docs/GLASS_KINDS.md, docs/PAPER.md "Ink"): what every part of theme_parts.h is
// where a pixel is one of a few inks and a change is a print. Its rules, each held by tests/test_theme_parts.cpp:
//
//   - A glyph or a word is ink on paper or paper on ink, never on a tone between them: a raster through a letter
//     breaks it. So what carries one is paper (with a rim of ink, since paper on paper is no shape) or ink.
//   - Colour carries no state; a shape does. On is a disc of ink with its glyph left open, off the glyph in a ring.
//   - Nothing is paler for waiting, and nothing shades: a part at part strength is whole or gone.
//   - A tone between ink and paper is only for what has nothing on it: a track, a field of a drawing.
//
// Included by theme_parts.h, inside the pure half of theme.h, in a build that may stand on a glass of ink
// (glass_kind.h, GLASS_MAY_BE_INK), and by nothing else: read by itself, or in a build that is never ink, this file is
// empty (tests/test_glass_lit.cpp holds that). Its twin is theme_lit.h: the same names on a glass that is lit. A card
// never names either; it asks theme_parts.h for the part.
#if defined(THEME_READS_A_STYLESHEET) && defined(GLASS_MAY_BE_INK) && !defined(THEME_INK_STYLESHEET)
#define THEME_INK_STYLESHEET 1

namespace theme::on_ink {

inline uint32_t paper() { return hex(CARD); }
inline uint32_t ink() { return hex(INK); }
// The tone ink of this colour stands on: black under a light ink, white under a dark one.
constexpr uint32_t under(uint32_t words) { return ink_value(Ink::PAPER, lightness(words) >= 128); }

// ---- a state's colour
// The ink itself for any state, and the tone of what is not there for "off" and the greys of a history that say the
// same.
inline uint32_t state(uint32_t color) {
  if (color == STATE_OFF) return hex(OFF);
  if (color == ROLES[HISTORY_OFF].light) return hex(HISTORY_OFF);
  if (color == ROLES[HISTORY_EMPTY].light) return hex(HISTORY_EMPTY);
  return ink();
}
inline uint32_t foreground(uint32_t color) {
  color = state(color);
  if (!dark) return color;
  const uint32_t l = lightness(color);
  return l >= 110 ? color : mix(color, ink_value(Ink::INK, true), static_cast<uint8_t>(255 - (110 - l) * 3 / 2));
}
// The pale share of a colour with nothing on it is the lighter tone, and of "off" nothing: the card itself.
inline uint32_t tint(uint32_t color, uint8_t) { return color == STATE_OFF ? paper() : ink_value(Ink::SOFT, dark); }
// The pale ground under a glyph or under words is the card: the glyph stands alone there, or in a rim its maker gives.
inline uint32_t field(uint32_t, uint8_t) { return paper(); }
// A glyph is ink; whether its state is on is its disc's to say.
inline uint32_t icon(uint32_t) { return ink(); }
inline uint32_t disc(uint32_t color) { return color == STATE_OFF ? paper() : ink(); }
inline uint32_t on_disc(uint32_t color) { return color == STATE_OFF ? ink() : paper(); }
// Under a fill of ink the track is the lighter tone.
inline uint32_t track(uint32_t) { return ink_value(Ink::SOFT, dark); }
// What a colour marks (a dot, a bar, a lamp's own colour on its icon) is ink.
inline uint32_t mark(uint32_t) { return ink(); }
// On the dark stage a mark is the stage's own ink.
inline uint32_t stage_mark(Role) { return hex(CAMERA_INK); }
// What is off or cannot be reached is ink too: a grey glyph or number is a raster, and the word beside it says so.
inline uint32_t absent() { return ink(); }
inline uint32_t soft(uint32_t words, uint32_t, uint8_t) { return words; }
// The one chosen among its row is ink, with what stands on it left open.
inline uint32_t chosen(uint32_t) { return hex(KEY_ON); }
// A scrim is black in either look: mixed with what lies under it, it would be a grey.
inline uint32_t scrim() { return ink_value(Ink::PAPER, true); }
// The knob of a switch that is off is ink, on its pill of paper.
inline uint32_t toggle_knob(bool on) { return on ? hex(KNOB) : ink(); }
// A key takes no colour of its own: it would be a raster under its word.
inline uint32_t key_swatch(uint32_t) { return 0; }

// ---- a card and what stands in it
// A key on a card is the card's own paper, and its maker gives it a rim.
inline uint32_t key_on(uint32_t card, uint8_t) { return card; }
// A press has no shade: nothing prints under a finger, and a shade drawn for nobody would only be a second refresh.
inline uint32_t pressed(uint32_t card) { return card; }
// A card of a colour of its own is a card: its pastel would be a raster under every word on it.
inline uint32_t surface(Face f) { return f.kind == Face::INSTRUMENT ? hex(INSTRUMENT) : paper(); }
inline uint32_t surface(uint32_t) { return paper(); }
inline uint32_t outline(Face f) { return f.kind == Face::INSTRUMENT ? hex(INSTRUMENT_LINE) : hex(LINE); }
inline uint32_t outline(uint32_t) { return hex(LINE); }
inline uint32_t pressed(Face f) { return surface(f); }

// ---- lines and strengths
// Only ink is a line, and a line of one pixel is a row of dots on some panels.
inline int hairline() { return PAPER_RIM; }
inline int shape_rim() { return PAPER_RIM; }
inline uint32_t line(uint32_t color) { return color == paper() ? color : ink(); }
// A part a lit glass shows faintly, with nothing in it to read (a glow, a key that leads nowhere), is not there.
inline uint8_t gone(uint8_t) { return 0; }
// A part a lit glass dims that must still be read keeps its ink whole.
inline uint8_t whole(uint8_t) { return 255; }
// A ground that lets what is under it through is solid from a quarter of its strength, and gone under it.
inline uint8_t solid(uint8_t opa) { return opa == 255 ? 255 : opa >= 64 ? 255 : 0; }
inline bool shades() { return false; }
inline bool stage_coloured(bool) { return false; }

// ---- a full-glass view that is dark in both looks on a lit glass is the page itself here: there is no light to save,
// and a colour read from a cover would be a raster over the whole glass
inline uint32_t stage_ground(uint32_t) { return hex(PAGE); }
inline uint32_t stage_ink() { return ink(); }

// ---- parts with a ground and what stands on it
// A disc that says a state: on is ink with the glyph left open, off the glyph in a ring, and what cannot be reached
// the glyph in a ring too.
inline Dress state_disc(uint32_t, bool available, bool on, uint8_t) {
  if (!available) return {hex(TRACK), ink(), 255, PAPER_RIM, ink()};
  return {on ? ink() : paper(), on ? paper() : ink(), 255, static_cast<uint8_t>(on ? 0 : PAPER_RIM), ink()};
}
// A tile's own disc: the same pair, but a tile that cannot be reached is its glyph alone. A key tile, whose circle is
// the tile itself, keeps its ring then.
inline Dress tile_disc(uint32_t color, bool available, bool key) {
  Dress d = state_disc(color, available, color != STATE_OFF, 38);
  if (!key && !available) d.rim = 0;
  return d;
}
// The words a key tile carries on its circle: left open in a circle of ink, ink on one of paper.
inline uint32_t on_key(uint32_t color, bool available) { return available && color != STATE_OFF ? paper() : ink(); }
inline Dress half(bool chosen) { return {hex(chosen ? KEY_ON : TRACK), hex(chosen ? KEY_ON_ICON : MUTED)}; }
// The page on the glass is a dot of ink and the others are rings: a pale dot is three pixels of raster.
inline Dress pager_dot(bool current, Role, uint8_t) {
  return {current ? ink() : paper(), 0, 255, static_cast<uint8_t>(current ? 0 : PAPER_RIM), ink()};
}
// A key that is a haze of its ink on a lit glass is the tone that ink stands on, in a ring of the ink.
inline Dress haze(uint32_t words, uint8_t) { return {under(words), words, 255, PAPER_RIM, words}; }
// A body in a colour of its own (the sun, the moon): full it is a disc of ink, else a ring.
inline Dress orb(uint32_t, bool full) {
  return {full ? ink() : paper(), ink(), 255, static_cast<uint8_t>(full ? 0 : PAPER_RIM), ink()};
}
// A rail is paper with a rim, and what runs along it fills it with ink.
inline Dress rail(uint32_t words, uint32_t, uint8_t) { return {hex(TRACK), words, 255, PAPER_RIM, ink()}; }

// ---- a calendar's own colour: which calendar an event is of is not told here. What marks is ink, what carries words
// is paper (its painter gives it a rim), and the words are ink.
// A colour its giver already made paper (the keyboard's special keys, a to-do list's disc) stays paper: ink there
// hid the glyph on it.
inline uint32_t calendar_key(uint32_t c) { return c == paper() ? c : ink(); }
inline uint32_t calendar_block(uint32_t) { return paper(); }
inline uint32_t calendar_ink(uint32_t) { return ink(); }
inline uint32_t calendar_track(uint32_t) { return ink_value(Ink::SOFT, dark); }
inline uint32_t calendar_key_past(uint32_t c) { return calendar_key(c); }
inline uint32_t calendar_block_past(uint32_t) { return paper(); }
inline uint32_t calendar_ink_past(uint32_t) { return ink(); }

// ---- the clock faces of the screensaver: the face is paper and everything on it ink, or the other way round in the
// dark look. A pale face would print as a raster over the whole glass, a grey tick as loose dots and a white hand with
// a pale rim as next to nothing (seen on a reTerminal Sticky's Glass face, 2026-11-27). A hand is solid ink with a rim
// of the face's own tone, which keeps it clear of the numeral it crosses.
inline ClockTones clock(bool in_dark) {
  ClockTones k;
  k.face = ink_value(Ink::PAPER, in_dark);
  k.ink = k.soft = k.tick = k.minor = k.hand = k.accent = ink_value(Ink::INK, in_dark);
  k.edge = k.raised = k.face;
  k.hands_rimmed = true;
  return k;
}
// Bauhaus: the school's black is ink and its cream paper, and its three colours are the two tones between them:
// fields with nothing on them, which a raster may be. The clock that stands on them is ink alone, its hour marks and
// its hub too (a red dot was a few grey pixels), on a dial of the look's paper.
inline BauhausTones bauhaus(bool in_dark) {
  BauhausTones b;
  b.cream = ink_value(Ink::PAPER, in_dark);
  b.black = ink_value(Ink::INK, in_dark);
  b.red = b.blue = ink_value(Ink::FIRM, in_dark);
  b.yellow = ink_value(Ink::SOFT, in_dark);
  b.hand = b.mark = b.black;
  b.face = b.cream;
  return b;
}

}  // namespace theme::on_ink

#endif  // THEME_READS_A_STYLESHEET
