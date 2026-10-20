#pragma once
// The energy card on the glass (firmware 0.47.0): energy_card.h places everything, energy_view.cpp paints it. One LVGL
// object per card draws the whole scene in its draw event, so the card costs one object however many circles it has,
// and the dots run on their own timer, each frame redrawing only the few pixels a dot leaves and enters.
#include <memory>

#include "lvgl.h"

namespace runtime_tiles {
struct Widgets;
struct Tile;
}
namespace energy_card {
struct Data;
}

namespace energy_view {
struct View;  // the card's scene and its running dots
// Draws the card into the slot's extra layer, `width` x `height` (the card's content).
void render(runtime_tiles::Widgets &w, const runtime_tiles::Tile &t, int width, int height);
// The slot shows another card: its view goes.
void release(runtime_tiles::Widgets &w);
// A tap at `point` (screen coordinates): a circle with a sensor behind it opens that sensor's history, as a node of Home
// Assistant's own live view opens its more-info; a card of a period opens its full screen. True when it opened one.
bool tap(runtime_tiles::Widgets &w, const runtime_tiles::Tile &t, const lv_point_t &point);
// The full screen of a card of a period (docs/ENERGY.md): the calendar card's header, with the units, Today, back and
// forward, over the period's diagram, on the whole glass.
void open(lv_obj_t *root, const runtime_tiles::Tile &t, unsigned index);
// The request the full screen waits for (0: none), and the app's answer to one (op "energy").
unsigned asked();
void receive(std::shared_ptr<const energy_card::Data> data, unsigned view);
}  // namespace energy_view
