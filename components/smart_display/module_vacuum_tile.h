#pragma once
// A robot vacuum's larger tile (docs/VACUUM.md, "A larger tile") of the module vacuum_card (tier full): what
// runtime_tiles.h reaches of it. vacuum_tile.h places its parts; module_vacuum_tile.cpp, a compilation unit of its own,
// paints them and takes their taps. A lite screen has neither and draws the keys.
// The WebAssembly preview and the host tests have no defines.h, and no module either.
#if __has_include("esphome/core/defines.h")
#include "esphome/core/defines.h"
#endif
#ifdef SD_MOD_VACUUM_CARD
#include "lvgl.h"
#include <string>

namespace runtime_tiles {
struct Widgets;
struct Tile;
namespace vacuum_face {
struct View;  // the tile's plan, its picks and what its finger presses
// Whether this tile draws the larger face: a vacuum whose controls are one of the four (the add-on sends them only to a
// screen whose hello says vacuum_tile).
bool shows(const Tile &t);
// Draws the face into the slot's extra layer, `width` x `height` (the card's content).
void render(Widgets &w, const Tile &t, int width, int height);
// The slot shows another card: the face's plan goes.
void release(Widgets &w);
// A tap on the card: true when it landed on one of the face's parts, which then acted; false lets the card's own tap go on.
bool card_tap(Widgets &w, const Tile &t);
// The map's place for the tile's picture: false when the face shows no map. In the content's coordinates.
bool map_place(const Widgets &w, int &x, int &y, int &width, int &height);
// The map's picture object (a part of the face), for the picture store's count of what is drawn.
lv_obj_t *picture(const Widgets &w);
// The tile's picture came, or went: on the map's place.
void picture_place(Widgets &w, const Tile &t);
// Every part a finger acts on, for the renders (tools/render/host.py, render_vacuum) and a diagnosis:
// "kind:arg@x,y;..." in the glass's coordinates, "" when the slot shows no face.
std::string describe(const Widgets &w);
}  // namespace vacuum_face
}  // namespace runtime_tiles
#endif
