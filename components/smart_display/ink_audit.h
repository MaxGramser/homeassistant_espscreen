#pragma once
// What the host render sees LVGL draw, for the ink audit (docs/GLASS_KINDS.md, "The audit"): where every glyph and
// word stands on the glass, which grounds cover what lies under them, and where pictures are. tools/render/run.py
// holds the first rule of a glass of ink against it for every picture it takes: a glyph or a word stands on ink or on
// paper, never on a raster and never on a picture.
//
// Only the host build has it (USE_HOST): a screen records nothing and carries none of this. It changes nothing LVGL
// draws; it listens to the draw tasks of every object (LV_EVENT_DRAW_TASK_ADDED) while a snapshot is taken, and
// draw_text.h tells it of a text a card paints itself, which has no object.
#ifdef USE_HOST
#include <lvgl.h>

#include <algorithm>
#include <string>
#include <vector>

namespace ink_audit {

// 'T' a text's ink box, 'G' a ground that covers what is under it, 'P' a picture. In the order LVGL drew them.
struct Seen {
  char kind;
  lv_area_t box;
  std::string text;
};
inline bool recording = false;
inline std::vector<Seen> seen;

// The box a text's ink lies in: the extent of its lines in the room it was given, by its alignment.
inline lv_area_t ink_box(const lv_area_t &room, const lv_draw_label_dsc_t &d) {
  lv_point_t size;
  lv_text_get_size(&size, d.text, d.font, d.letter_space, d.line_space, lv_area_get_width(&room), d.flag);
  const int spare = lv_area_get_width(&room) - size.x;
  lv_area_t box = room;
  if (d.align == LV_TEXT_ALIGN_CENTER) box.x1 += spare / 2;
  else if (d.align == LV_TEXT_ALIGN_RIGHT) box.x1 += spare;
  box.x1 += d.ofs_x;
  box.y1 += d.ofs_y;
  box.x2 = box.x1 + size.x - 1;
  box.y2 = box.y1 + size.y - 1;
  return box;
}
inline bool drawn(const lv_draw_label_dsc_t &d) { return d.text && *d.text && d.font && d.opa > LV_OPA_MIN; }
// What two areas share; false when they share nothing. (LVGL's own is in a private header that not every build reads.)
inline bool shared(lv_area_t &out, const lv_area_t &a, const lv_area_t &b) {
  out = {std::max(a.x1, b.x1), std::max(a.y1, b.y1), std::min(a.x2, b.x2), std::min(a.y2, b.y2)};
  return out.x1 <= out.x2 && out.y1 <= out.y2;
}

// A text a card paints itself (draw_text::label), with the layer's clip of that moment.
inline void text(const lv_area_t &room, const lv_area_t &clip, const lv_draw_label_dsc_t &d) {
  if (!recording || !drawn(d)) return;
  const lv_area_t box = ink_box(room, d);
  lv_area_t shown;
  if (shared(shown, box, clip)) seen.push_back({'T', shown, d.text});
}

// A draw task of an object: its text, a ground that covers, a picture; each cut to what shows of the object.
inline void task(lv_event_t *e) {
  if (!recording) return;
  lv_draw_task_t *t = lv_event_get_draw_task(e);
  auto *obj = static_cast<lv_obj_t *>(lv_event_get_target(e));
  if (!t || !obj) return;
  lv_area_t area;
  lv_draw_task_get_area(t, &area);
  switch (lv_draw_task_get_type(t)) {
    case LV_DRAW_TASK_TYPE_LABEL: {
      const lv_draw_label_dsc_t *d = lv_draw_task_get_label_dsc(t);
      if (!d || !drawn(*d)) return;
      lv_area_t box = ink_box(area, *d);
      if (lv_obj_area_is_visible(obj, &box)) seen.push_back({'T', box, d->text});
      return;
    }
    case LV_DRAW_TASK_TYPE_FILL: {
      const lv_draw_fill_dsc_t *d = lv_draw_task_get_fill_dsc(t);
      if (!d || d->opa < 250) return;
      if (lv_obj_area_is_visible(obj, &area)) seen.push_back({'G', area, ""});
      return;
    }
    case LV_DRAW_TASK_TYPE_IMAGE:
      if (lv_obj_area_is_visible(obj, &area)) seen.push_back({'P', area, ""});
      return;
    default:
      return;
  }
}

// Every object under `root` tells of its draw tasks from now on. Said before each snapshot: objects come and go.
inline void watch(lv_obj_t *root) {
  if (!root) return;
  bool heard = false;
  for (uint32_t i = 0, n = lv_obj_get_event_count(root); i < n && !heard; ++i)
    heard = lv_event_dsc_get_cb(lv_obj_get_event_dsc(root, i)) == task;
  if (!heard) {
    lv_obj_add_flag(root, LV_OBJ_FLAG_SEND_DRAW_TASK_EVENTS);
    lv_obj_add_event_cb(root, task, LV_EVENT_DRAW_TASK_ADDED, nullptr);
  }
  for (uint32_t i = 0, n = lv_obj_get_child_count(root); i < n; ++i) watch(lv_obj_get_child(root, i));
}

// What was seen, a line each: the kind, the box's corners, and a text with its line ends as spaces.
inline std::string report() {
  std::string out;
  for (const Seen &s : seen) {
    std::string words = s.text;
    for (char &c : words)
      if (c == '\n' || c == '\r') c = ' ';
    out += s.kind;
    out += ' ' + std::to_string(s.box.x1) + ' ' + std::to_string(s.box.y1) + ' ' + std::to_string(s.box.x2) + ' ' +
           std::to_string(s.box.y2) + ' ' + words + '\n';
  }
  return out;
}

}  // namespace ink_audit
#endif
