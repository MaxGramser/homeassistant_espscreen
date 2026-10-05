#pragma once
// The energy card on the glass (firmware 0.47.0): energy_card.h places everything, energy_view.cpp paints it. One LVGL
// object per card draws the whole scene in its draw event, so the card costs one object however many circles it has,
// and the dots run on their own timer, each frame redrawing only the few pixels a dot leaves and enters.
#include "lvgl.h"

namespace runtime_tiles {
struct Widgets;
struct Tile;
}

namespace energy_view {
struct View;  // the card's scene and its running dots
// Draws the card into the slot's extra layer, `width` x `height` (the card's content).
void render(runtime_tiles::Widgets &w, const runtime_tiles::Tile &t, int width, int height);
// The slot shows another card: its view goes.
void release(runtime_tiles::Widgets &w);
// A tap at `point` (screen coordinates): a circle with a sensor behind it opens that sensor's history, as a node of Home
// Assistant's own live view opens its more-info. True when it opened one.
bool tap(runtime_tiles::Widgets &w, const runtime_tiles::Tile &t, const lv_point_t &point);
}  // namespace energy_view
