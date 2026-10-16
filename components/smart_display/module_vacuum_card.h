#pragma once
// The vacuum card of the module vacuum_card (tier full; docs/MODULES.md, docs/VACUUM.md): what runtime_tiles.h reaches of
// it. The card itself is module_vacuum_card.cpp, a compilation unit of its own; a lite screen has neither.
#include "esphome/core/defines.h"
#ifdef SD_MOD_VACUUM_CARD
#include <string>
#include "lvgl.h"
#include "runtime_model.h"

namespace runtime_tiles {
namespace vacuum_card {
// The card in the detail card's root, in the room show_detail gave it; `heading` is the top bar's name.
void render(Tile &t, lv_obj_t *heading, int width, int height);
// Whether the card takes the whole glass (landscape glass with a map, or low glass).
bool wide(const Tile &t);
// The card's own keys (800-899) and what they do.
bool handles(int cmd);
void command(Tile &t, int cmd);
// The back key: a view of the card goes back to the card (true), the card itself closes (false).
bool back();
// The map's picture: wanted each round while the card shows it, drawn while the store holds it.
void picture_want();
bool draws(const lv_image_dsc_t *image);
void forget_pictures();
// The card's objects are gone (another card is built), and the card closed.
void card_cleared();
void closed();
// Its view and its keys, for the renders and a diagnosis.
std::string describe();
}  // namespace vacuum_card
}  // namespace runtime_tiles
#endif
