// Browser platform adapter. Every widget is created by ESPHome-generated setup
// and drawn by runtime_tiles.h. This file owns only transport, time and input.
#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>
#include "lvgl.h"
#include "../../components/smart_display/runtime_tiles.h"
#include "../../components/smart_display/renderer_host_api.h"
#include "generated/firmware_renderer_manifest.h"
#include "generated/profiles.h"
#include "generated/text.h"

static_assert(ESP_SCREEN_RENDERER_ABI == 3, "Update the host adapter for the renderer ABI change");

namespace {
lv_display_t *display{};
lv_indev_t *pointer{};
FirmwareUi firmware{};
std::vector<uint32_t> draw_buffer, framebuffer;
int width{}, height{}, page{};
lv_point_t position{};
bool pressed = false, dirty = true;
uint32_t epoch = 0, epoch_at = 1000;
int utc_offset = 0;
std::string last_result, diagnostics, outgoing_action;

void flush(lv_display_t *d, const lv_area_t *area, uint8_t *pixels) {
  // LVGL's native 32-bit pixels are BGRA; ImageData is RGBA. Keep draw memory
  // separate, otherwise a partial refresh modifies its own input while copying.
  const int span = area->x2 - area->x1 + 1;
  for (int y = area->y1; y <= area->y2; ++y) {
    for (int x = area->x1; x <= area->x2; ++x) {
      auto *s = pixels + ((y - area->y1) * span + x - area->x1) * 4;
      framebuffer[y * width + x] = s[2] | uint32_t(s[1]) << 8 | uint32_t(s[0]) << 16 | 0xFF000000u;
    }
  }
  lv_display_flush_ready(d);
}

void read_pointer(lv_indev_t *, lv_indev_data_t *data) {
  data->point = position;
  data->state = pressed ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
}

void show_page() { runtime_tiles::show_page(page, firmware.prev, firmware.next, firmware.number); dirty = true; }
void nav(lv_event_t *event) {
  int step = static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(event)));
  if (screen_input::touch_guard.accept_repeat(esphome::millis(), step < 0 ? 11 : 12)) {
    page += step;
    show_page();
  }
}
}

extern "C" {
int preview_init(int w, int h, int display_dpi, int columns, int rows) {
  if (display || w < 160 || h < 160 || w > 2560 || h > 2560 || columns < 1 || rows < 1 ||
      columns > 8 || rows > 8 || columns * rows > 64) return 0;
  width = w; height = h;
  lv_init();
  lv_tick_set_cb(esphome::millis);
  draw_buffer.resize(size_t(width) * height);
  framebuffer.resize(draw_buffer.size());
  display = lv_display_create(width, height);
  lv_display_set_color_format(display, LV_COLOR_FORMAT_XRGB8888);
  lv_display_set_flush_cb(display, flush);
  lv_display_set_buffers(display, draw_buffer.data(), nullptr, draw_buffer.size() * sizeof(uint32_t), LV_DISPLAY_RENDER_MODE_FULL);
  firmware = setup_firmware_ui(lv_screen_active(), display_dpi);
  if (!firmware.room) return 0;
  runtime_tiles::grid = {size_t(columns), size_t(rows)};
  ui::configure(display_dpi, firmware.look);
  firmware.bind();
  for (size_t i = 0; i < runtime_tiles::grid.slots(); ++i) firmware.cell(i);
  runtime_tiles::room_label = firmware.room;
  runtime_tiles::time_label = firmware.time;
  runtime_tiles::enabled = true;
  runtime_tiles::screen_awake = [] { return true; };
  runtime_tiles::now_time = [] {
    auto now = esphome::ESPTime::from_epoch_local(epoch + (esphome::millis() - epoch_at) / 1000 + utc_offset);
    now.timestamp -= utc_offset;
    return now;
  };
  runtime_tiles::refresh = [] { dirty = true; };
  runtime_tiles::layout_changed = show_page;
  runtime_tiles::dismiss = [] { runtime_tiles::hide_detail(); dirty = true; };
  runtime_tiles::back_home = [] { runtime_tiles::hide_detail(); page = 0; show_page(); };
  runtime_tiles::touch_input::turn_page = [](int step) { page += step; show_page(); };
  lv_obj_add_event_cb(firmware.prev, nav, LV_EVENT_CLICKED, reinterpret_cast<void *>(-1));
  lv_obj_add_event_cb(firmware.next, nav, LV_EVENT_CLICKED, reinterpret_cast<void *>(1));
  pointer = lv_indev_create();
  lv_indev_set_type(pointer, LV_INDEV_TYPE_POINTER);
  lv_indev_set_display(pointer, display);
  lv_indev_set_read_cb(pointer, read_pointer);
  show_page();
  return 1;
}

const char *preview_receive(const char *message) {
  last_result = runtime_tiles::receive(message ? message : "");
  dirty = true;
  return last_result.c_str();
}
const char *preview_next_action() {
  auto &queue = esphome::api::host_api_server.outgoing;
  if (queue.empty()) return "";
  outgoing_action = std::move(queue.front()); queue.pop_front();
  return outgoing_action.c_str();
}
void preview_action_response(unsigned call_id, int success, const char *error) {
  esphome::api::host_api_server.handle_action_response(call_id, success != 0, esphome::StringRef(error ? error : ""));
  dirty = true;
}
void preview_time(uint32_t milliseconds, uint32_t unix_seconds, int offset_seconds) {
  esphome::host_millis = milliseconds + 1000;
  epoch = unix_seconds; epoch_at = esphome::host_millis; utc_offset = offset_seconds;
}
void preview_touch(int x, int y, int down) {
  const bool was_pressed = pressed;
  position = {std::clamp(x, 0, width - 1), std::clamp(y, 0, height - 1)};
  pressed = down != 0;
  if (pressed && !was_pressed) runtime_tiles::touch_input::pressed(position.x, position.y, 0, false);
  else if (was_pressed) runtime_tiles::touch_input::moved(position.x, position.y, 0, 1);
  lv_indev_read(pointer);
  if (!pressed && was_pressed) runtime_tiles::touch_input::released();
}
void preview_cancel() {
  screen_input::touch_guard.consume();
  lv_indev_wait_release(pointer);
  pressed = false;
  lv_indev_read(pointer);
  runtime_tiles::touch_input::released();
}
void preview_render() {
  runtime_tiles::tick();
  if (dirty) { dirty = false; runtime_tiles::render(firmware.room); }
  lv_timer_handler();
  lv_refr_now(display);
}
const uint32_t *preview_frame() { return framebuffer.data(); }
int preview_page() { return page; }
const char *preview_diagnostics() {
  JsonDocument doc;
  doc["page"] = page;
  doc["count"] = runtime_tiles::model.count;
  doc["columns"] = runtime_tiles::grid.columns;
  doc["rows"] = runtime_tiles::grid.rows;
  doc["source"] = ESP_SCREEN_FIRMWARE_RENDERER_SOURCE_SHA256;
  auto tiles = doc["tiles"].to<JsonArray>();
  for (auto &w : runtime_tiles::widgets) {
    if (!w.tile || lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN)) continue;
    auto tile = tiles.add<JsonObject>();
    lv_area_t bounds; lv_obj_get_coords(w.tile, &bounds);
    tile["x"] = bounds.x1; tile["y"] = bounds.y1;
    tile["width"] = lv_obj_get_width(w.tile); tile["height"] = lv_obj_get_height(w.tile);
    tile["title"] = lv_label_get_text(w.title);
    tile["mode"] = w.extra_mode;
    tile["state"] = runtime_tiles::model.tiles[w.index].state;
    tile["pending"] = runtime_tiles::model.tiles[w.index].pending;
  }
  auto icons = doc["icons"].to<JsonArray>();
  std::function<void(lv_obj_t *)> inspect = [&](lv_obj_t *object) {
    if (!lv_obj_is_visible(object)) return;
    if (lv_obj_check_type(object, &lv_label_class)) {
      const char *text = lv_label_get_text(object);
      // Material Design Icons occupy Unicode's supplementary private-use plane.
      if (std::strlen(text) >= 4 && static_cast<unsigned char>(text[0]) == 0xF3) {
        lv_area_t bounds; lv_obj_get_coords(object, &bounds);
        auto icon = icons.add<JsonObject>();
        icon["x"] = bounds.x1; icon["y"] = bounds.y1;
        icon["width"] = lv_obj_get_width(object); icon["height"] = lv_obj_get_height(object);
      }
    }
    for (uint32_t i = 0; i < lv_obj_get_child_count(object); ++i) inspect(lv_obj_get_child(object, i));
  };
  inspect(lv_screen_active());
  diagnostics.clear(); serializeJson(doc, diagnostics);
  return diagnostics.c_str();
}
}
