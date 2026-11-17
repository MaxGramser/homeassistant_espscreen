#pragma once
// The screen's look and scale (app 0.2.94, responsive boards).
//
// A screen hangs on a wall and is used from the same distance whatever its size, so every size the firmware
// draws is a physical one. Two looks exist: `standard` (the Guition's sizes at 170 dpi) and `compact` (the CYD's
// at 143 dpi, for glass too small for the standard). A board declares its look and its pixel density
// (DISPLAY_DPI = diagonal pixels / diagonal inches); ui::configure() turns that into one scale for every pixel
// size the C++ carries, so a 7-inch at 133 dpi draws the standard look at 78 % and a 294 dpi panel at 173 %.
// On the CYD and the Guition the scale is exactly 100: their pixels are the reference.
//
// Sizes that come from the board file (the tile grid, TILE_ICON_SIZE, the fonts) are already scaled there; ui::px()
// is for the sizes the C++ decides itself (paddings, key heights, strips), in the reference look's pixels.
#include <algorithm>
#include <cstdint>
#include <initializer_list>
#include <string>

namespace ui {
enum class Look : uint8_t { standard, compact };
inline Look look = Look::standard;
inline int dpi = 170;
inline int scale_pct = 100;
inline bool circular = false;
#ifdef SCREEN_ROUND
// A physical board's shape is fixed, so rectangular/lite builds discard the circular layout code at compile time.
inline constexpr bool round() { return SCREEN_ROUND != 0; }
#else
// The native browser renderer shares one binary between physical shapes.
inline bool round() { return circular; }
#endif
inline int reference_dpi(Look l) { return l == Look::compact ? 143 : 170; }
inline void configure(int display_dpi, const std::string &look_name, const std::string &shape_name = "rectangle") {
  look = look_name == "compact" ? Look::compact : Look::standard;
  dpi = display_dpi > 0 ? display_dpi : reference_dpi(look);
  scale_pct = (dpi * 100 + reference_dpi(look) / 2) / reference_dpi(look);
  circular = shape_name == "round";
}
// A size of the reference look, in this board's pixels.
inline int px(int n) {
  if (scale_pct == 100) return n;
  return n >= 0 ? (n * scale_pct + 50) / 100 : -((-n * scale_pct + 50) / 100);
}
// The large class of cards and pages belongs to the standard look; the compact look draws the small one.
inline bool large() { return look == Look::standard; }
// The widest a card with controls may get: beyond this the keys of a thermostat stand a hand apart. A picture
// (the media card's cover, a camera) is not capped, it may fill the glass. 110 mm of the reference look.
inline int control_max_width() { return px(look == Look::compact ? 620 : 740); }
// A size in millimetres of glass, whatever the board's density: what a finger, a thumb or an arm's length asks
// for is physical, and only the pixels under it differ per board.
inline int mm(int millimetres) { return (dpi * millimetres + 12) / 25; }
// The smallest thing a finger must be able to hit: 7 mm of glass. A drawn track may be thinner; its touch area
// is grown to this (overlay_card::touchable).
inline int touch_min() { return mm(7); }
// The space between two columns of a card that stands in two (overlay_card::columns).
inline int column_gap() { return mm(6); }
// A card is a stack of blocks that has to fit the glass it lands on. `shrink` takes `over` pixels from the
// blocks in the order they are given, never taking one below what it needs, and returns what could not be
// taken. `weight` is how many pixels of the stack one pixel of that block is worth: a row that appears twice
// weighs two, the space between four blocks weighs three. The order is the design decision, and every card
// makes it for itself: a robot gives up its portrait before its keys, a thermostat its word before its modes.
struct Give {
  int *value;
  int least;
  int weight = 1;
};
inline int shrink(std::initializer_list<Give> parts, int over) {
  for (const auto &part : parts) {
    if (over <= 0) break;
    const int room = *part.value - part.least, weight = part.weight > 0 ? part.weight : 1;
    if (room <= 0) continue;
    const int take = std::min(room, (over + weight - 1) / weight);
    *part.value -= take;
    over -= take * weight;
  }
  return over > 0 ? over : 0;
}
// The look's cell height: what a card is designed for. A cell taller than this centres its content on it;
// one at least twice as tall stacks its icon above its name and state.
inline int cell_height() { return px(look == Look::compact ? 52 : 108); }
}  // namespace ui
