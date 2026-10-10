#pragma once
// The frame every overlay gets: the card a tap opens (a light, a thermostat, a blind, a vacuum, a graph).
//
// Two rules, and they hold on every board:
//
//  * **The content is never wider than a hand spans.** A thermostat whose − and + sit at the far edges of a
//    ten-inch panel takes two hands; ui::control_max_width is the width one hand does span, and a card wider
//    than that keeps that width. On a CYD and a Guition nothing is capped: their glass is narrower already.
//  * **What is capped, is centred.** A card that does not fill the glass sits in the middle of it, left to
//    right and top to bottom, like a dialog. Not centring it would leave it stuck against a corner.
//
// A card that is a *picture* or a *graph* says so and is not capped: the media card's cover art, a camera's
// image and a day of a sensor are all nicer the bigger they are, and none of them is worked with a finger
// across its whole width (`overlay_card::frame(root, overlay_card::graph)`). What such a card *does* work
// with a finger - a row of range keys, a volume slider - keeps a hand's width all the same and stands in the
// middle of the card (`overlay_card::reach`). So: the picture is as wide as the glass, the controls are as
// wide as a hand, on a 2.8-inch screen and on a 10-inch one.
//
// Everything a finger must hit keeps at least `ui::touch_min()` of glass, whatever the card drew: a thin
// track may look thin, but its touch area is grown to the finger's size (`overlay_card::touchable`).
#include <algorithm>
#include <cstdint>
#include "lvgl.h"
#include "ui_scale.h"

namespace overlay_card {

// `controls` is capped to a hand's width, `picture` and `graph` fill the glass (see above).
enum Kind { controls, picture, graph };

inline int screen_width() { return lv_display_get_horizontal_resolution(lv_display_get_default()); }
inline int screen_height() { return lv_display_get_vertical_resolution(lv_display_get_default()); }

// The width a card's content may take: capped for controls, the whole glass for a picture. A card in two
// columns may take twice the cap, so each column keeps its own reach.
inline int content_width(Kind kind = controls, int columns = 1) {
  const int room = screen_width();
  if (kind != controls) return room;
  return std::min(room, columns * ui::control_max_width() + (columns - 1) * ui::column_gap());
}

// The room every card keeps between its content and the edge of its area, whatever the board and whatever the
// card: the vacuum's hero, the blind's keys, the thermostat's setpoint and the graph all start here.
inline int pad() { return ui::px(ui::large() ? 20 : 10); }

// Whether a card stands in one column or two. Glass that is short for its width - a 480 x 272 panel, a wide
// seven-inch - cannot give a tall control the millimetres it needs while half its width goes unused; such a
// card lays its controls beside the rest instead of under it, the way a web page turns a stack into two
// columns when the viewport allows. `need_height` is what the one-column form asks for, `min_column` the
// narrowest a column may be. The decision is the shape's (three units of width to two of height, the same
// rule as the effects page and the forecast), never a pixel count: a square or a portrait panel keeps its
// stack and lets the card give room in its own order, as the two first boards always did. Glass too
// narrow for two columns keeps one as well.
inline int columns(int need_height, int min_column) {
  if (need_height <= screen_height()) return 1;
  if (screen_width() * 2 < screen_height() * 3) return 1;
  return screen_width() >= 2 * min_column + ui::column_gap() ? 2 : 1;
}

// Give a card's root its room and put it in the middle of the glass, left to right. The root covers the glass and its
// padding makes the room: what the card draws stands in the room, while the top bar (detail_bar) reaches past the
// padding to the glass's own edges, so its keys stay put whatever width the card under it has.
inline void frame(lv_obj_t *root, Kind kind = controls, int columns = 1) {
  if (!root) return;
  const int side = (screen_width() - content_width(kind, columns)) / 2;
  lv_obj_set_pos(root, 0, 0);
  lv_obj_set_width(root, screen_width());
  lv_obj_set_style_pad_left(root, side, 0);
  lv_obj_set_style_pad_right(root, side, 0);
}

// Where the glass's left and top edges lie in `parent`'s coordinates, those lv_obj_set_pos takes (its content area):
// what stands on the glass rather than in a card (the top bar, the page bar) is placed with these on any page's root,
// capped by its padding or by its place. Read from the styles, not from the coordinates: those follow only at LVGL's
// next layout pass, and a page is built before that.
inline int glass_left(const lv_obj_t *parent) {
  int x = 0;
  for (const lv_obj_t *o = parent; o && lv_obj_get_parent(o); o = lv_obj_get_parent(o))
    x += lv_obj_get_style_x(o, LV_PART_MAIN) + lv_obj_get_style_pad_left(o, LV_PART_MAIN) +
         lv_obj_get_style_border_width(o, LV_PART_MAIN);
  return -x;
}
inline int glass_top(const lv_obj_t *parent) {
  int y = 0;
  for (const lv_obj_t *o = parent; o && lv_obj_get_parent(o); o = lv_obj_get_parent(o))
    y += lv_obj_get_style_y(o, LV_PART_MAIN) + lv_obj_get_style_pad_top(o, LV_PART_MAIN) +
         lv_obj_get_style_border_width(o, LV_PART_MAIN);
  return -y;
}

// Once a card is drawn, put its content in the middle of the glass from top to bottom as well. The first
// `pinned` children are the card's own top bar (the back key and the name): those stay where they are, at the
// top, whatever the content below them does. What stands on the glass rather than in the card (the pager across its
// foot, page_bar.h, marked FLOATING) stays where it is too, and the block is centred in the room above it. Only the
// block between them moves, and only when it leaves more than a finger's worth of room.
inline void centre(lv_obj_t *root, uint32_t pinned = 0) {
  if (!root) return;
  lv_obj_update_layout(root);
  int bar = 0, foot = screen_height(), top = INT32_MAX, bottom = 0;
  for (uint32_t i = 0; i < lv_obj_get_child_count(root); ++i) {
    lv_obj_t *child = lv_obj_get_child(root, i);
    if (!child || lv_obj_has_flag(child, LV_OBJ_FLAG_HIDDEN)) continue;
    const int y = lv_obj_get_y(child), end = y + lv_obj_get_height(child);
    if (lv_obj_has_flag(child, LV_OBJ_FLAG_FLOATING)) { foot = std::min(foot, y); continue; }
    if (i < pinned) { bar = std::max(bar, end); continue; }
    top = std::min(top, y);
    bottom = std::max(bottom, end);
  }
  if (bottom <= 0 || top == INT32_MAX) return;
  const int room = foot - bar - (bottom - top);
  if (room <= ui::touch_min()) return;
  const int shift = bar + room / 2 - top;
  if (shift == 0) return;
  for (uint32_t i = pinned; i < lv_obj_get_child_count(root); ++i) {
    lv_obj_t *child = lv_obj_get_child(root, i);
    if (child && !lv_obj_has_flag(child, LV_OBJ_FLAG_HIDDEN) && !lv_obj_has_flag(child, LV_OBJ_FLAG_FLOATING))
      lv_obj_set_y(child, lv_obj_get_y(child) + shift);
  }
}

// A row a finger works inside a card that fills the glass: never wider than a hand spans, and in the middle
// of the card. `room` is what the card would have given it (its width less its padding); `x` comes back as
// the place inside the card. On a CYD or a Guition the room is already narrower than a hand, so nothing moves.
struct Reach { int x, w; };
inline Reach reach(int card_width, int room) {
  const int w = std::min(room, ui::control_max_width());
  return {(card_width - w) / 2, w};
}

// Anything a finger must hit: the drawn size may be thinner than a finger, the touch area may not.
inline void touchable(lv_obj_t *object, int drawn_thickness) {
  if (!object) return;
  const int grow = std::max(0, (ui::touch_min() - drawn_thickness) / 2);
  lv_obj_set_ext_click_area(object, grow);
}

}  // namespace overlay_card
