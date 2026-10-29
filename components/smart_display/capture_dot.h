#pragma once
// The screen's own camera in use (docs/PICTURES.md "Capture", plugin API 0.17; docs/PICTURE_ARCHITECTURE.md, section 3.8).
// A dot in the glass's top right corner, on top of everything (LVGL's system layer: pages, cards, the full view, the
// screensaver), while the screen's own camera is in use: Home Assistant taking pictures or a stream of it, which the core
// sees by itself on the camera with the id ts_camera (the feature `camera`, smart_display.register_plugin binds it
// through plugin_host::watch_camera), or a plugin that uses it on the screen itself (tessera::capturing). No plugin or
// setting takes it away. Solid while anyone watches (Home Assistant, or a plugin's Capture::CAMERA); a ring of the same
// size while the camera only senses on the screen (Capture::SENSING, plugin API 0.20: a light level, motion), so a
// glance tells "seen" from "counted". It lies in the top bar's row, so it never lies over a live picture (live_view.h
// stops one under anything LVGL draws). The rule is the screen's, not a plugin's: the plugin API only reports to it.
//
// Included by plugin_host.cpp alone, in a build with a plugin (a camera is always a plugin's).
#include <algorithm>
#include <cstdint>
#include <memory>
#include <vector>

#include "esphome/core/defines.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "lvgl.h"
#include "plugin_api.h"
#include "theme.h"
#include "ui_scale.h"
#ifdef USE_CAMERA
#include "esphome/components/camera/camera.h"
#endif

namespace capture_dot {
// A picture keeps the camera in use this long: Home Assistant's dashboards ask for a new one every ten seconds. A
// stream is in use while its pictures come; at five a second, a gap this long means it ended.
constexpr uint32_t PICTURE_IN_USE_MS = 12000;
constexpr uint32_t STREAM_QUIET_MS = 3000;
// The plugins that use the camera on the screen itself right now (tessera::capturing), each with how: sensing alone.
struct User {
  const tessera::Plugin *plugin;
  bool sensing;
};
inline std::vector<User> &users() {
  static std::vector<User> list;
  return list;
}
inline uint32_t picture_at = 0;   // millis() of the camera's last picture to Home Assistant, 0 before the first
inline bool streaming = false;
inline lv_obj_t *dot = nullptr;
inline bool dot_dark = false;
inline bool dot_ring = false;
enum State : uint8_t { OFF, SENSING, WATCHED };
inline State state(uint32_t now) {
  bool sensing = false;
  for (const User &user : users()) {
    if (!user.sensing) return WATCHED;
    sensing = true;
  }
  if (picture_at && now - picture_at < (streaming ? STREAM_QUIET_MS : PICTURE_IN_USE_MS)) return WATCHED;
  return sensing ? SENSING : OFF;
}
inline bool in_use(uint32_t now) { return state(now) != OFF; }
// The dot goes once the camera's last picture is old and no plugin uses it, and takes the look's colour (every 250 ms
// from the plugin host's tick, and at once when the camera is heard or a plugin says so).
inline void update(uint32_t now) {
  const State now_state = state(now);
  if (now_state == OFF) {
    if (dot) { lv_obj_delete(dot); dot = nullptr; ESP_LOGI("plugins", "the camera is no longer in use"); }
    return;
  }
  if (!dot) {
    const int d = std::max(6, ::ui::mm(2));
    dot = lv_obj_create(lv_layer_sys());
    lv_obj_remove_style_all(dot);
    lv_obj_remove_flag(dot, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_remove_flag(dot, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(dot, d, d);
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
    lv_obj_align(dot, LV_ALIGN_TOP_RIGHT, -std::max(3, ::ui::mm(1)), std::max(3, ::ui::mm(1)));
    lv_obj_set_style_border_width(dot, std::max(1, d / 5), 0);  // the ring's line, a fifth of the dot
    dot_dark = !theme::dark;          // coloured below
    dot_ring = now_state != SENSING;  // shaped below
    ESP_LOGI("plugins", "the camera is in use: the dot shows");
  }
  if (dot_dark != theme::dark) {
    dot_dark = theme::dark;
    const lv_color_t green = lv_color_hex(theme::foreground(theme::ha::GREEN));
    lv_obj_set_style_bg_color(dot, green, 0);
    lv_obj_set_style_border_color(dot, green, 0);
  }
  // Solid while anyone watches, a ring while the camera only senses.
  const bool ring = now_state == SENSING;
  if (dot_ring != ring) {
    dot_ring = ring;
    lv_obj_set_style_bg_opa(dot, ring ? LV_OPA_TRANSP : LV_OPA_COVER, 0);
    lv_obj_set_style_border_opa(dot, ring ? LV_OPA_COVER : LV_OPA_TRANSP, 0);
    ESP_LOGI("plugins", "the camera dot: %s", ring ? "a ring, the camera only senses" : "solid, someone watches");
  }
}
#ifdef USE_CAMERA
// The camera as Home Assistant uses it, heard as ESPHome's API hears it: a picture, a stream that starts or stops.
class Watch : public esphome::camera::CameraListener {
 public:
  void on_camera_image(const std::shared_ptr<esphome::camera::CameraImage> &) override { seen(); }
  void on_stream_start() override { streaming = true; seen(); }
  void on_stream_stop() override { streaming = false; update(esphome::millis()); }

 private:
  static void seen() {
    picture_at = esphome::millis() | 1;
    update(picture_at);
  }
};
inline void watch(esphome::camera::Camera *camera) {
  static Watch watcher;
  if (camera) camera->add_listener(&watcher);
}
#endif
// A plugin uses the camera on the screen itself, watched or for sensing alone, or no longer: the dot shows while any
// does, solid while one watches.
inline void capturing(const tessera::Plugin *plugin, bool sensing, bool on) {
  auto &using_it = users();
  const auto found = std::find_if(using_it.begin(), using_it.end(),
                                  [&](const User &u) { return u.plugin == plugin && u.sensing == sensing; });
  if (on && found == using_it.end()) {
    using_it.push_back({plugin, sensing});
    ESP_LOGI("plugins", "%s uses the camera on the screen%s", plugin->plugin_id(), sensing ? " to sense" : "");
  } else if (!on && found != using_it.end()) {
    using_it.erase(found);
    ESP_LOGI("plugins", "%s no longer uses the camera%s", plugin->plugin_id(), sensing ? " to sense" : "");
  }
  update(esphome::millis());
}
}  // namespace capture_dot
