// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_theme_parts.cpp -o /tmp/test_theme_parts && /tmp/test_theme_parts
// The parts a card is made of (components/smart_display/theme_parts.h) on both kinds of glass: every part goes to the
// stylesheet of the glass, the ink stylesheet keeps its rules for every part in every state and both looks, and the
// lit stylesheet is the colours the screens have always had.
#define THEME_TEST
// The part files before the theme and after it, as a build may include a component's headers in any order: read by
// themselves they are empty, and the theme reads them where they belong.
#include "../components/smart_display/theme_parts.h"
#include "../components/smart_display/theme_ink.h"
#include "../components/smart_display/theme_lit.h"
#include "../components/smart_display/theme.h"
#include "../components/smart_display/theme_lit.h"
#include "../components/smart_display/theme_ink.h"
#include "../components/smart_display/theme_parts.h"
#include <cassert>
#include <cstdio>
#include <vector>

using namespace theme;

static void look(bool d) { TestLook::set(d, d); }
static void glass(uint8_t inks) { paper::inks() = inks; }

int main() {
#ifndef GLASS_MAY_BE_INK
#error "the tests read components/paper_glass/paper.h: this build may be ink"
#endif
  const uint32_t states[] = {ha::AMBER, ha::RED, ha::BLUE, ha::TEAL, ha::PURPLE, ha::INDIGO, ha::GREEN, STATE_OFF};

  // ---- a glass of ink: the rules of theme_ink.h, held for every part, every state and both looks
  glass(2);
  assert(inked());
  for (bool d : {false, true}) {
    look(d);
    const uint32_t paper_tone = d ? 0x000000 : 0xFFFFFF, ink_tone = d ? 0xFFFFFF : 0x000000;
    // What carries a glyph or a word is paper or ink, and what stands on it is the other: never a tone between.
    std::vector<Dress> carrying;
    for (uint32_t c : states)
      for (bool available : {true, false}) {
        for (bool on : {true, false}) carrying.push_back(state_disc(c, available, on));
        for (bool key : {true, false}) carrying.push_back(tile_disc(c, available, key));
      }
    for (bool chosen : {true, false}) carrying.push_back(half(chosen));
    for (uint32_t words : {hex(INK), hex(CAMERA_INK)}) {
      carrying.push_back(haze(words, 40));
      carrying.push_back(haze(words, 110));
    }
    for (const Dress &part : carrying) {
      assert(part.ground == 0x000000 || part.ground == 0xFFFFFF);
      assert(part.ink == 0x000000 || part.ink == 0xFFFFFF);
      assert(part.ink != part.ground);
      assert(part.opa == 255);  // nothing shades
      // A ground that is the card's own tone is a shape only by its line, and that line is ink (or the words' own
      // colour on the dark stage).
      assert(part.rim == 0 || (part.rim == PAPER_RIM && part.line != part.ground));
    }
    // Colour carries no state; a shape does. On is a disc of ink with the glyph left open, off the glyph in a ring.
    for (uint32_t c : states) {
      const Dress on = state_disc(c, true, true), off = state_disc(c, true, false), away = state_disc(c, false, true);
      assert(on.ground == ink_tone && on.ink == paper_tone && on.rim == 0);
      assert(off.ground == paper_tone && off.ink == ink_tone && off.rim == PAPER_RIM);
      assert(away.ground == paper_tone && away.ink == ink_tone && away.rim == PAPER_RIM);
      // A tile says on by its own colour not being "off"; one that cannot be reached is its glyph alone, in ink.
      const Dress tile = tile_disc(c, true, false);
      assert((tile.ground == ink_tone) == (c != STATE_OFF) && (tile.rim == PAPER_RIM) == (c == STATE_OFF));
      const Dress gone_tile = tile_disc(c, false, false);
      assert(gone_tile.ink == ink_tone && gone_tile.rim == 0);
      // A key tile's circle is the tile: it keeps its ring whenever it is not a circle of ink, and its words are left
      // open in a circle of ink.
      const Dress key = tile_disc(c, true, true);
      assert((key.rim == 0) == (c != STATE_OFF) && tile_disc(c, false, true).rim == PAPER_RIM);
      assert(on_key(c, true) == (c != STATE_OFF ? paper_tone : ink_tone) && on_key(c, false) == ink_tone);
      // What a colour marks, the glyph of a state and the words of a state are ink, whatever the colour.
      assert(mark(c) == ink_tone && icon(c) == ink_tone && chosen(c) == ink_tone);
      // The pale ground under a glyph is the card; the pale share with nothing on it is a tone between, or nothing.
      assert(field(c, 38) == paper_tone);
      assert(tint(c, 38) != ink_tone);
    }
    assert(absent() == ink_tone);
    // Words that stand back are their own ink, not a mix of it.
    assert(soft(ink_tone, paper_tone, 190) == ink_tone && soft(hex(CAMERA_INK), 0, 200) == hex(CAMERA_INK));
    // Nothing is faded: gone or whole, and a see-through ground is solid from a quarter of its strength.
    for (int opa = 1; opa < 255; ++opa) {
      assert(gone(opa) == 0 && whole(opa) == 255);
      assert(solid(opa) == (opa >= 64 ? 255 : 0));
    }
    assert(solid(255) == 255 && solid(0) == 0);
    assert(!shades());
    // Only ink is a line.
    assert(hairline() == PAPER_RIM && shape_rim() == PAPER_RIM);
    assert(line(0x9E9E9E) == ink_tone && line(paper_tone) == paper_tone);
    // A pager's dots: the page on the glass ink, the others rings.
    assert(pager_dot(true, SUBTLE, 102).ground == ink_tone && pager_dot(true, SUBTLE, 102).rim == 0);
    assert(pager_dot(false, SUBTLE, 102).ground == paper_tone && pager_dot(false, SUBTLE, 102).rim == PAPER_RIM);
    assert(pager_dot(false, SUBTLE, 102).opa == 255);
    // The sun is a disc of ink, the moon a ring.
    assert(orb(ha::SUNNY, true).ground == ink_tone && orb(ha::SUNNY, true).rim == 0);
    assert(orb(hex(MOON), false).ground == paper_tone && orb(hex(MOON), false).rim == PAPER_RIM);
    // The stage is the page itself, with ink on it, and takes no colour from a cover.
    assert(stage_ground(0x3A2F6B) == paper_tone && stage_ink() == ink_tone && !stage_coloured(true));
    // A haze is the tone its ink stands on, in a ring of that ink: on the page, and on the dark stage of a picture.
    assert(haze(ink_tone, 40).ground == paper_tone && haze(ink_tone, 40).line == ink_tone && haze(ink_tone, 40).rim == PAPER_RIM);
    assert(haze(hex(CAMERA_INK), 56).ground == 0x000000 && haze(hex(CAMERA_INK), 56).line == hex(CAMERA_INK));
    assert(rail(ink_tone, paper_tone, 70).ground == paper_tone && rail(ink_tone, paper_tone, 70).rim == PAPER_RIM);
    // A switch that is off has a knob of ink on its pill of paper; a key takes no colour of its own.
    assert(toggle_knob(false) == ink_tone && toggle_knob(true) == paper_tone);
    assert(key_swatch("red") == 0 && key_swatch("green") == 0);
    // A scrim is black in either look.
    assert(scrim() == 0x000000);
    // A card of a colour of its own is a card, and a press has no shade.
    assert(surface(SWATCHES[0].light) == paper_tone && surface(Face{Face::SWATCH, 1}) == paper_tone);
    assert(pressed(paper_tone) == paper_tone && key_on(paper_tone, 20) == paper_tone);
    // A calendar: what marks is ink, what carries words is paper, the words are ink, past or not; a colour its giver
    // made paper stays paper.
    for (uint32_t c : {ha::BLUE, ha::GREEN, ha::RED}) {
      assert(calendar_key(c) == ink_tone && calendar_key_past(c) == ink_tone);
      assert(calendar_block(c) == paper_tone && calendar_block_past(c) == paper_tone);
      assert(calendar_ink(c) == ink_tone && calendar_ink_past(c) == ink_tone);
      assert(calendar_track(c) != ink_tone && calendar_track(c) != paper_tone);
    }
    assert(calendar_key(paper_tone) == paper_tone);
  }
  // A clock face is paper with everything on it in ink, or the other way round in its dark look, and a hand has a rim
  // of the face's tone. Bauhaus: ink, paper and the two tones between, its clock ink alone on a dial of paper.
  for (bool face_dark : {false, true}) {
    const uint32_t paper_tone = face_dark ? 0x000000 : 0xFFFFFF, ink_tone = face_dark ? 0xFFFFFF : 0x000000;
    const ClockTones k = clock(face_dark);
    assert(k.face == paper_tone && k.edge == paper_tone && k.hands_rimmed);
    for (uint32_t on_face : {k.ink, k.soft, k.tick, k.minor, k.hand, k.accent}) assert(on_face == ink_tone);
    const BauhausTones b = bauhaus(face_dark);
    assert(b.cream == paper_tone && b.black == ink_tone && b.face == paper_tone && b.hand == ink_tone && b.mark == ink_tone);
    for (uint32_t field_tone : {b.red, b.yellow, b.blue}) assert(field_tone != paper_tone && field_tone != ink_tone);
  }

  // ---- a glass that is lit: the colours the screens have always had
  glass(0);
  assert(!inked());
  for (bool d : {false, true}) {
    look(d);
    for (uint32_t c : states) {
      // A disc is the state's colour pale with the glyph in the colour itself, on or off, and never has a line.
      for (bool on : {true, false}) {
        const Dress disc_look = state_disc(c, true, on);
        assert(disc_look.ground == tint(c, 38) && disc_look.ink == icon(c) && disc_look.rim == 0);
        assert(state_disc(c, true, on, 40).ground == tint(c, 40));
      }
      assert(state_disc(c, false, true).ground == hex(TRACK) && state_disc(c, false, true).ink == hex(OFF));
      for (bool key : {true, false}) {
        assert(tile_disc(c, true, key).ground == disc(c) && tile_disc(c, true, key).ink == on_disc(c));
        assert(tile_disc(c, false, key).ground == hex(TRACK) && tile_disc(c, false, key).ink == hex(OFF));
      }
      assert(on_key(c, true) == hex(INK));
      // What a colour marks and the one chosen among its row are the colour itself; a field is its tint.
      assert(mark(c) == c && chosen(c) == c && field(c, 51) == tint(c, 51));
      assert(disc(c) == tint(c, 38) && on_disc(c) == icon(c) && track(c) == tint(c, 51));
      assert(calendar_key(c) == c && calendar_key_past(c) == mix(c, hex(CARD), 130));
      assert(calendar_block_past(c) == mix(calendar_block(c), hex(CARD), 130));
      assert(calendar_ink_past(c) == mix(calendar_ink(c), hex(CARD), 150));
    }
    assert(absent() == hex(OFF));
    assert(soft(0xFFFFFF, 0x000000, 190) == mix(0xFFFFFF, 0x000000, 190));
    // A part is as faint as its maker says, and the glass shades.
    for (int opa = 0; opa <= 255; ++opa) assert(gone(opa) == opa && whole(opa) == opa && solid(opa) == opa);
    assert(shades() && hairline() == 1 && shape_rim() == 0 && line(0x9E9E9E) == 0x9E9E9E);
    assert(pager_dot(true, SUBTLE, 102).ground == hex(INK) && pager_dot(true, SUBTLE, 102).opa == 255);
    assert(pager_dot(false, SUBTLE, 102).ground == hex(SUBTLE) && pager_dot(false, SUBTLE, 102).opa == 102);
    assert(pager_dot(false, TICK).ground == hex(TICK) && pager_dot(false, TICK).opa == 255);
    assert(half(true).ground == hex(CARD) && half(true).ink == hex(INK));
    assert(half(false).ground == hex(TRACK) && half(false).ink == hex(MUTED));
    assert(orb(ha::SUNNY, true).ground == ha::SUNNY && orb(hex(MOON), false).ground == hex(MOON));
    // The stage is dark in both looks, in a cover's colour where it has one.
    assert(stage_ground(0x3A2F6B) == 0x3A2F6B && stage_ink() == hex(CAMERA_INK) && stage_coloured(true) && !stage_coloured(false));
    assert(haze(hex(CAMERA_INK), 56).ground == hex(CAMERA_INK) && haze(hex(CAMERA_INK), 56).opa == 56);
    assert(rail(0xFFFFFF, 0x000000, 70).ground == mix(0xFFFFFF, 0x000000, 70));
    assert(toggle_knob(false) == hex(KNOB) && toggle_knob(true) == hex(KNOB));
    assert(key_swatch("red") == KEY_SWATCHES[0].key || key_swatch("red") != 0);
    assert(key_swatch("no such colour") == 0);
    assert(scrim() == hex(SCRIM));
  }
  for (bool face_dark : {false, true}) {
    const ClockTones k = clock(face_dark);
    assert(k.face == (face_dark ? ROLES[CAMERA_PAGE].dark : ROLES[PAGE].light));
    assert(k.ink == (face_dark ? ROLES[INK].dark : ROLES[INK].light) && k.accent == ha::ORANGE);
    assert(k.hands_rimmed == !face_dark);
    const BauhausTones b = bauhaus(face_dark);
    assert(b.mark == b.red && b.face == (face_dark ? b.black : b.cream));
  }
  look(false);
  std::puts("PASS: every part on a glass of ink keeps its rules in every state and both looks, and a lit glass has its colours");
  return 0;
}
