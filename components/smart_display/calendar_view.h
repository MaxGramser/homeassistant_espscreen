#pragma once
// The calendar card on the glass (firmware 0.56.0): calendar_card.h plans what goes where, calendar_paint.h paints it,
// this file holds the LVGL side. One object per card draws the whole card in its draw event; the full screen a tap
// opens has three: what stays, the hours that scroll, and a sheet over them (the view key's choice, an event).
#include "lvgl.h"

#include <string>

namespace runtime_tiles {
struct Widgets;
struct Tile;
}

namespace calendar_view {
struct View;  // a card's plan and its data
// Draws the card into the slot's extra layer, `width` x `height` (the card's content).
void render(runtime_tiles::Widgets &w, const runtime_tiles::Tile &t, int width, int height);
// The slot shows another card: its plan goes.
void release(runtime_tiles::Widgets &w);
// The full screen of the card at `index`, built into `root` (the card layer show_detail cleaned).
void open(lv_obj_t *root, const runtime_tiles::Tile &t, unsigned index);
// A tap on the card: true when it was a room's booking key (the card then books), else the card's own tap goes on.
bool card_tap(runtime_tiles::Widgets &w, const runtime_tiles::Tile &t);
// A new minute: the open full screen follows the clock (its now line, the minutes left), keeping where it is scrolled.
void minute();
// The app's answer to a tap on a short event (op "calendar_event", the question `view`): the event's whole title, place
// and notes, for its calendar, start and end; `gone`: the app no longer has it. The open sheet shows it.
void detail(unsigned view, int cal, int start, int end, std::string title, std::string place, std::string notes, bool gone);
}  // namespace calendar_view
