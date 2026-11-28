#pragma once
#ifdef SD_MOD_TEXT_CARD
// The template tile on the glass (module text_card, firmware 0.58.0): module_text_card.h plans, module_text_card.cpp
// paints the plan in one object per card.
#include "lvgl.h"

namespace runtime_tiles {
struct Widgets;
struct Tile;
}

namespace text_card_view {
struct View;  // a card's plan and its rows
// Draws the card into the slot's extra layer, `width` x `height` (the card's content).
void render(runtime_tiles::Widgets &w, const runtime_tiles::Tile &t, int width, int height);
// The slot shows another card: its plan goes.
void release(runtime_tiles::Widgets &w);
// Home Assistant rendered nothing: the card hides its own ground, as "Background: none" does.
bool empty(const runtime_tiles::Tile &t);
}  // namespace text_card_view
#endif  // SD_MOD_TEXT_CARD
