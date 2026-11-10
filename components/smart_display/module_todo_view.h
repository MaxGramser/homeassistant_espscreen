#pragma once
#ifdef SD_MOD_TODO
// The to-do card on the glass (module todo, docs/TODO.md): module_todo.h plans, module_todo.cpp paints the plan in one
// object per card, hears the finger, and asks the app for what it ticks, adds, renames or removes.
#include "lvgl.h"

namespace runtime_tiles {
struct Widgets;
struct Tile;
}

namespace todo_view {
struct View;  // a card's plan and its list
// Draws the card into the slot's extra layer, `width` x `height` (the card's content).
void render(runtime_tiles::Widgets &w, const runtime_tiles::Tile &t, int width, int height);
// The slot shows another card: its plan goes.
void release(runtime_tiles::Widgets &w);
// A tap on the card: true when it was a row's (the item is ticked) or the key that adds an item (the full screen opens
// with its keyboard), else the card's own tap goes on and opens the full screen.
bool card_tap(runtime_tiles::Widgets &w, const runtime_tiles::Tile &t);
// The full screen of the card at `index`, built into `root` (the card layer show_detail cleaned).
void open(lv_obj_t *root, const runtime_tiles::Tile &t, unsigned index);
// Every way a card closes: the keyboard and what was typed go with it.
void closed();
}  // namespace todo_view
#endif  // SD_MOD_TODO
