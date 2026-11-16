#pragma once
#ifdef SD_MOD_TEXT_EDIT
// A text's field on the glass (module text_edit, docs/TEXT_ENTITY.md): module_text_edit.h decides, module_text_edit.cpp
// shows the field with the keyboard under the page's top bar and sends what is typed.
#include "lvgl.h"

namespace runtime_tiles {
struct Tile;
}

namespace text_edit_view {
// The field of the text at `index`, built into `root` (the card layer show_detail cleaned).
void open(lv_obj_t *root, const runtime_tiles::Tile &t, unsigned index);
// Every way the page closes: what was typed and not sent goes with it, and Home Assistant hears nothing.
void closed();
}  // namespace text_edit_view
#endif  // SD_MOD_TEXT_EDIT
