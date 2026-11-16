#pragma once
// A text a card paints itself, in its draw event (the meter, the calendar, the energy view, the weather chart, the
// text card, the vacuum tile).
//
// What it knows: LVGL does not draw a label when lv_draw_label is called. It queues a task with the descriptor and
// draws when it dispatches the layer, which on a board with a draw unit of its own (the P4's PPA) is after the draw
// event has returned. The descriptor holds a pointer to the text, not the text, so a text that lived in a local of the
// draw code is gone by then: the meter's icon stood in such a local and the ring showed an empty disc whenever other
// cards were drawn after it, as when a page came back, until the sensor's next value drew the card alone (a Guition
// 10.1, 2026-11-15). The vacuum tile drew freed memory for ever the same way (a boot loop with the tile on page 1).
// So every text drawn this way is copied by LVGL (text_local), whatever its lifetime: one strndup of a short text.
//
// What it does not know: fonts, colours, where a text goes. tests/test_draw_text.py keeps every lv_draw_label of the
// component in this file.
#include <lvgl.h>

namespace draw_text {
inline void label(lv_layer_t *layer, lv_draw_label_dsc_t &dsc, const lv_area_t &area) {
  if (!dsc.text) return;
  dsc.text_local = 1;
  lv_draw_label(layer, &dsc, &area);
}
}  // namespace draw_text
