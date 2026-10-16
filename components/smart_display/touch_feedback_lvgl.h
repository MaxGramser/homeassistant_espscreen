#pragma once
// touch_feedback.h for LVGL's own widgets, so no control of the core or of a plugin has to say anything itself
// (docs/PLUGINS.md, "Touch feedback"). Included by plugin_host.cpp alone: a screen without a plugin has none of it.
//
// A press: LVGL tells the input device which object a finger landed on before that object's own events. The press is
// said when that object, or a parent its events bubble up to, listens for a press, a tap or a hold: a tile, a key, a
// slider, a row of the settings, the top bar, a plugin's card. The page itself listens for a flick only, so a finger
// between the tiles or in the margin of the glass says nothing.
// A drag: when the finger landed on an lv_slider or an lv_arc, a listener goes onto it (once; it goes with the object),
// and every value it takes while the finger is down is handed to touch_feedback::moved().
#include "lvgl.h"
#include "lvgl_private.h"  // an event's filter (lv_event_dsc_t), which LVGL 9 keeps out of lvgl.h
#include "touch_feedback.h"

namespace touch_feedback::lvgl {

// Whether a listener of `object` hears a finger: a press, a tap, a hold, or all events.
inline bool hears_finger(lv_obj_t *object) {
  for (uint32_t i = 0, n = lv_obj_get_event_count(object); i < n; ++i) {
    switch (lv_obj_get_event_dsc(object, i)->filter & ~LV_EVENT_PREPROCESS) {
      case LV_EVENT_ALL: case LV_EVENT_PRESSED: case LV_EVENT_SHORT_CLICKED: case LV_EVENT_CLICKED:
      case LV_EVENT_LONG_PRESSED: case LV_EVENT_LONG_PRESSED_REPEAT: case LV_EVENT_RELEASED:
        return true;
      default: break;
    }
  }
  return false;
}
// The object or a parent its events reach takes the finger; the screen itself never counts.
inline bool takes_finger(lv_obj_t *object) {
  for (auto *o = object; o && lv_obj_get_parent(o); o = lv_obj_get_parent(o)) {
    if (hears_finger(o)) return true;
    if (!lv_obj_has_flag(o, LV_OBJ_FLAG_EVENT_BUBBLE)) return false;
  }
  return false;
}
inline bool is_value(lv_obj_t *o) {
#if LV_USE_ARC
  if (lv_obj_check_type(o, &lv_arc_class)) return true;
#endif
  return lv_obj_check_type(o, &lv_slider_class);
}
inline void value_changed(lv_event_t *e) {
  auto *o = lv_event_get_target_obj(e);
  auto *indev = lv_indev_active();
  // LVGL sets the value once more as the finger lifts, and code sets it while nobody touches: no step of a drag.
  if (!indev || lv_indev_get_state(indev) != LV_INDEV_STATE_PRESSED) return;
#if LV_USE_ARC
  if (lv_obj_check_type(o, &lv_arc_class)) {
    moved(o, lv_arc_get_value(o), lv_arc_get_min_value(o), lv_arc_get_max_value(o));
    return;
  }
#endif
  moved(o, lv_slider_get_value(o), lv_slider_get_min_value(o), lv_slider_get_max_value(o));
}
inline void follow(lv_obj_t *o) {
  for (uint32_t i = 0, n = lv_obj_get_event_count(o); i < n; ++i)
    if (lv_event_dsc_get_cb(lv_obj_get_event_dsc(o, i)) == value_changed) return;
  lv_obj_add_event_cb(o, value_changed, LV_EVENT_VALUE_CHANGED, nullptr);
}
inline void landed(lv_event_t *e) {
  auto *object = static_cast<lv_obj_t *>(lv_event_get_param(e));
  land();
  if (object == nullptr || !takes_finger(object)) return;
  press();
  for (auto *o = object; o && lv_obj_get_parent(o); o = lv_obj_get_parent(o))
    if (is_value(o)) {
      follow(o);
      return;
    }
}

// Once, when the first listener comes: every pointer the screen has (a board has one).
inline void listen() {
  static bool listening = false;
  if (listening) return;
  listening = true;
  for (auto *indev = lv_indev_get_next(nullptr); indev; indev = lv_indev_get_next(indev))
    if (lv_indev_get_type(indev) == LV_INDEV_TYPE_POINTER) lv_indev_add_event_cb(indev, landed, LV_EVENT_PRESSED, nullptr);
}

}  // namespace touch_feedback::lvgl
