// The stylesheet of a glass that is lit (docs/GLASS_KINDS.md): what every part of theme_parts.h is where a pixel is a
// colour and a frame is free. A state is a colour, a part that waits is paler, a key is a shade of its card, and a
// picture carries words under a shade.
//
// Included by theme_parts.h, inside the pure half of theme.h, and by nothing else: read by itself this file is empty.
// Its twin is theme_ink.h: the same names, each as a glass of ink shows it. A card never names either; it asks
// theme_parts.h for the part.
#if defined(THEME_READS_A_STYLESHEET) && !defined(THEME_LIT_STYLESHEET)
#define THEME_LIT_STYLESHEET 1

namespace theme::on_lit {

// ---- a state's colour
// Grey is what Home Assistant draws for something off; the add-on's timelines add a lighter grey for off and one for no
// data. In dark those greys come from the table; every other state colour stays itself.
inline uint32_t state(uint32_t color) {
  if (!dark) return color;
  if (color == STATE_OFF) return ROLES[OFF].dark;
  if (color == ROLES[HISTORY_OFF].light) return ROLES[HISTORY_OFF].dark;
  if (color == ROLES[HISTORY_EMPTY].light) return ROLES[HISTORY_EMPTY].dark;
  return color;
}
// Drawn as a glyph, a line or words on the page or a card. Dark lifts the deep ones (indigo, purple) until they read
// on graphite.
inline uint32_t foreground(uint32_t color) {
  color = state(color);
  if (!dark) return color;
  const uint32_t l = lightness(color);
  return l >= 110 ? color : mix(color, 0xFFFFFF, static_cast<uint8_t>(255 - (110 - l) * 3 / 2));
}
// The colour at `amount` over white in light, and over the card in dark, where the same share would vanish, a little
// more.
inline uint32_t tint(uint32_t color, uint8_t amount) {
  color = state(color);
  if (!dark) return mix(color, 0xFFFFFF, amount);
  const unsigned stronger = amount + amount / 3 + 8;
  return mix(color, hex(CARD), static_cast<uint8_t>(stronger > 255 ? 255 : stronger));
}
inline uint32_t field(uint32_t color, uint8_t amount) { return tint(color, amount); }
// A touch darker in light, so a pale bulb still shows; a touch lighter in dark.
inline uint32_t icon(uint32_t color) {
  color = state(color);
  return dark ? mix(foreground(color), 0xFFFFFF, 230) : mix(color, 0x333333, 205);
}
inline uint32_t disc(uint32_t color) { return tint(color, 38); }
inline uint32_t on_disc(uint32_t color) { return icon(color); }
inline uint32_t track(uint32_t color) { return tint(color, 51); }
inline uint32_t mark(uint32_t color) { return color; }
inline uint32_t stage_mark(Role role) { return hex(role); }
inline uint32_t absent() { return hex(OFF); }
inline uint32_t soft(uint32_t words, uint32_t ground, uint8_t amount) { return mix(words, ground, amount); }
inline uint32_t chosen(uint32_t color) { return color; }
inline uint32_t scrim() { return hex(SCRIM); }
inline uint32_t toggle_knob(bool) { return hex(KNOB); }
inline uint32_t key_swatch(uint32_t key) { return key; }

// ---- a card and what stands in it
inline uint32_t key_on(uint32_t card, uint8_t depth) {
  return dark ? mix(card, 0xFFFFFF, static_cast<uint8_t>(255 - (255 - depth) * 3 / 2)) : mix(card, 0x000000, depth);
}
// An eighth of the way to black in light and to white in dark, the same share on white, on a pastel and on graphite.
inline uint32_t pressed(uint32_t card) { return mix(card, dark ? 0xFFFFFF : 0x000000, 224); }
inline uint32_t surface(Face f) {
  switch (f.kind) {
    case Face::SWATCH: return dark ? SWATCHES[f.swatch].dark : SWATCHES[f.swatch].light;
    case Face::INSTRUMENT: return hex(INSTRUMENT);
    default: return hex(CARD);
  }
}
// Any light value that is no swatch stands as it is in the light look and is the card in the dark one.
inline uint32_t surface(uint32_t own) {
  if (!own) return hex(CARD);
  if (!dark) return own;
  for (const auto &s : SWATCHES) if (s.light == own) return s.dark;
  return hex(CARD);
}
// The card's own colour a little darker in light, a little lighter in dark.
inline uint32_t outline(Face f) {
  switch (f.kind) {
    case Face::SWATCH: return dark ? mix(surface(f), 0xFFFFFF, 232) : mix(SWATCHES[f.swatch].light, 0x000000, 220);
    case Face::INSTRUMENT: return hex(INSTRUMENT_LINE);
    default: return hex(LINE);
  }
}
inline uint32_t outline(uint32_t own) {
  if (!own) return hex(LINE);
  return dark ? mix(surface(own), 0xFFFFFF, 232) : mix(own, 0x000000, 220);
}
// An instrument's face is dark in both looks, so it goes towards white in both.
inline uint32_t pressed(Face f) { return mix(surface(f), dark || f.kind == Face::INSTRUMENT ? 0xFFFFFF : 0x000000, 224); }

// ---- lines and strengths
inline int hairline() { return 1; }
inline int shape_rim() { return 0; }
inline uint32_t line(uint32_t color) { return color; }
inline uint8_t gone(uint8_t opa) { return opa; }
inline uint8_t whole(uint8_t opa) { return opa; }
inline uint8_t solid(uint8_t opa) { return opa; }
inline bool shades() { return true; }
inline bool stage_coloured(bool own) { return own; }

// ---- a full-glass view that is dark in both looks: a player, a clock at rest
inline uint32_t stage_ground(uint32_t own) { return own; }
inline uint32_t stage_ink() { return hex(CAMERA_INK); }

// ---- parts with a ground and what stands on it
inline Dress state_disc(uint32_t color, bool available, bool, uint8_t amount) {
  return {available ? tint(color, amount) : hex(TRACK), available ? icon(color) : hex(OFF)};
}
inline Dress tile_disc(uint32_t color, bool available, bool) { return state_disc(color, available, true, 38); }
inline uint32_t on_key(uint32_t, bool) { return hex(INK); }
inline Dress half(bool chosen) { return {hex(chosen ? CARD : TRACK), hex(chosen ? INK : MUTED)}; }
inline Dress pager_dot(bool current, Role rest, uint8_t rest_opa) {
  return {hex(current ? INK : rest), 0, static_cast<uint8_t>(current ? 255 : rest_opa)};
}
inline Dress haze(uint32_t words, uint8_t opa) { return {words, words, opa}; }
inline Dress rail(uint32_t words, uint32_t ground, uint8_t amount) { return {mix(words, ground, amount), words}; }
inline Dress orb(uint32_t color, bool) { return {color, color}; }

// ---- a calendar's own colour (Home Assistant's, from its registry or the frontend's palette): an event's pale block,
// the words on it, a progress track, and what is past, a step towards the card. The same shares as Apple's and the
// frontend's events: the colour reads, the words stay dark (light in dark).
inline uint32_t calendar_key(uint32_t c) { return c; }
inline uint32_t calendar_block(uint32_t c) { return dark ? mix(c, hex(CARD), 80) : mix(c, 0xFFFFFF, 58); }
inline uint32_t calendar_ink(uint32_t c) { return dark ? mix(c, 0xFFFFFF, 110) : mix(c, 0x000000, 120); }
inline uint32_t calendar_track(uint32_t c) { return dark ? mix(c, hex(CARD), 90) : mix(c, 0xFFFFFF, 70); }
inline uint32_t calendar_past(uint32_t c) { return mix(c, hex(CARD), 130); }
inline uint32_t calendar_key_past(uint32_t c) { return calendar_past(c); }
inline uint32_t calendar_block_past(uint32_t c) { return calendar_past(calendar_block(c)); }
inline uint32_t calendar_ink_past(uint32_t c) { return mix(calendar_ink(c), hex(CARD), 150); }

// ---- the clock faces of the screensaver (module_clock_faces.cpp), each in the face's own look
inline uint32_t tone(Role r, bool in_dark) { return in_dark ? ROLES[r].dark : ROLES[r].light; }
inline ClockTones clock(bool in_dark) {
  ClockTones k;
  k.face = in_dark ? tone(CAMERA_PAGE, true) : tone(PAGE, false);
  k.ink = tone(INK, in_dark);
  k.soft = mix(k.ink, k.face, 150);
  k.tick = mix(k.ink, k.face, in_dark ? 225 : 235);
  k.minor = mix(k.ink, k.face, in_dark ? 120 : 110);
  k.hand = tone(CLOCK_HAND, in_dark);
  k.edge = in_dark ? k.face : mix(k.ink, k.face, 200);
  k.accent = ha::ORANGE;
  k.raised = tone(CARD, in_dark);
  k.hands_rimmed = !in_dark;
  return k;
}
inline BauhausTones bauhaus(bool in_dark) {
  BauhausTones b;
  b.cream = tone(BAUHAUS_CREAM, in_dark);
  b.black = tone(BAUHAUS_BLACK, in_dark);
  b.red = tone(BAUHAUS_RED, in_dark);
  b.yellow = tone(BAUHAUS_YELLOW, in_dark);
  b.blue = tone(BAUHAUS_BLUE, in_dark);
  b.hand = in_dark ? tone(BAUHAUS_CREAM, false) : tone(BAUHAUS_BLACK, false);
  b.mark = b.red;
  b.face = in_dark ? b.black : b.cream;
  return b;
}

}  // namespace theme::on_lit

#endif  // THEME_READS_A_STYLESHEET
