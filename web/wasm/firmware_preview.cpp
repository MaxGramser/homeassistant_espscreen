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
#include "image_transport.h"

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
    page = step < 0 ? runtime_tiles::previous_button_page(page) : runtime_tiles::sequential_page(page, step);
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
  preview_images::bind();
  for (size_t i = 0; i < runtime_tiles::grid.slots(); ++i) firmware.cell(i);
  runtime_tiles::room_label = firmware.room;
  runtime_tiles::time_label = firmware.time;
  runtime_tiles::enabled = true;
  // The virtual device enables the firmware's normal swipe setting. Since
  // protocol 2, this preference is no longer part of a layout packet.
  settings_screen::set("swipe_pages", 1);
  runtime_tiles::screen_awake = [] { return true; };
  runtime_tiles::now_time = [] {
    auto now = esphome::ESPTime::from_epoch_local(epoch + (esphome::millis() - epoch_at) / 1000 + utc_offset);
    now.timestamp -= utc_offset;
    return now;
  };
  runtime_tiles::refresh = [] { dirty = true; };
  runtime_tiles::layout_changed = show_page;
  runtime_tiles::dismiss = [] { runtime_tiles::hide_detail(); dirty = true; };
  runtime_tiles::back_home = [] { runtime_tiles::hide_detail(); runtime_tiles::navigation_history.clear(); page = runtime_tiles::home_page(); show_page(); };
  runtime_tiles::touch_input::turn_page = [](int target) { page = target; show_page(); };
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
  // A browser has no HA inbox entity, but firmware image events need an address.
  runtime_tiles::inbox = "preview";
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
  // A read-only preview did not send this request. Cancel the pending estimate
  // through the normal no-answer path, without pretending HA accepted it or
  // showing a refusal for an intentionally disabled transport.
  if (success < 0) {
    esphome::api::host_api_server.handle_action_response(call_id, false, esphome::StringRef(runtime_tiles::NO_ANSWER));
    dirty = true;
    return;
  }
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
  static uint32_t image_tick = 0;
  if (esphome::millis() - image_tick >= 250) {
    image_tick = esphome::millis(); runtime_tiles::camera_tick();
  }
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
  auto labels = doc["labels"].to<JsonArray>();
  auto sliders = doc["sliders"].to<JsonArray>();
  auto dropdowns = doc["dropdowns"].to<JsonArray>();
  std::function<void(lv_obj_t *)> inspect = [&](lv_obj_t *object) {
    if (!lv_obj_is_visible(object)) return;
    if (lv_obj_check_type(object, &lv_label_class)) {
      const char *text = lv_label_get_text(object);
      lv_area_t box;lv_obj_get_coords(object,&box);
      auto shown=labels.add<JsonObject>();shown["text"]=text;shown["x"]=box.x1;shown["y"]=box.y1;
      shown["width"]=lv_obj_get_width(object);shown["height"]=lv_obj_get_height(object);
      // Material Design Icons occupy Unicode's supplementary private-use plane.
      if (std::strlen(text) >= 4 && static_cast<unsigned char>(text[0]) == 0xF3) {
        lv_area_t bounds; lv_obj_get_coords(object, &bounds);
        auto icon = icons.add<JsonObject>();
        icon["x"] = bounds.x1; icon["y"] = bounds.y1;
        icon["width"] = lv_obj_get_width(object); icon["height"] = lv_obj_get_height(object);
        size_t at=0;const auto cp=header_bar::next_codepoint(std::string(text),at);
        const auto *font=lv_obj_get_style_text_font(object,LV_PART_MAIN);lv_font_glyph_dsc_t glyph;
        icon["codepoint"]=cp;icon["present"]=font&&font->get_glyph_dsc(font,&glyph,cp,0);
      }
    }
    if(lv_obj_check_type(object,&lv_slider_class)){
      lv_area_t box;lv_obj_get_coords(object,&box);auto slider=sliders.add<JsonObject>();
      slider["x"]=box.x1;slider["y"]=box.y1;slider["width"]=lv_obj_get_width(object);slider["height"]=lv_obj_get_height(object);
      slider["value"]=lv_slider_get_value(object);slider["disabled"]=lv_obj_has_state(object,LV_STATE_DISABLED);
    }
    if(lv_obj_check_type(object,&lv_dropdown_class)){
      lv_area_t box;lv_obj_get_coords(object,&box);auto dropdown=dropdowns.add<JsonObject>();
      dropdown["x"]=box.x1;dropdown["y"]=box.y1;dropdown["width"]=lv_obj_get_width(object);dropdown["height"]=lv_obj_get_height(object);
      dropdown["open"]=lv_dropdown_is_open(object);dropdown["options"]=lv_dropdown_get_options(object);dropdown["selected"]=lv_dropdown_get_selected(object);
      const char *symbol=lv_dropdown_get_symbol(object);size_t at=0;const auto cp=header_bar::next_codepoint(std::string(symbol?symbol:""),at);
      const auto *font=lv_obj_get_style_text_font(object,LV_PART_INDICATOR);lv_font_glyph_dsc_t glyph;
      dropdown["codepoint"]=cp;dropdown["symbol_present"]=font&&font->get_glyph_dsc(font,&glyph,cp,0);
      auto *list=lv_dropdown_get_list(object);
      if(list&&lv_obj_is_visible(list)&&lv_obj_get_child_count(list)){
        auto *label=lv_obj_get_child(list,0);lv_area_t bounds;lv_obj_get_coords(label,&bounds);
        auto rows=dropdown["rows"].to<JsonObject>();rows["x"]=bounds.x1;rows["y"]=bounds.y1;rows["width"]=lv_obj_get_width(label);
        rows["height"]=lv_font_get_line_height(lv_obj_get_style_text_font(label,LV_PART_MAIN))+lv_obj_get_style_text_line_space(label,LV_PART_MAIN);
      }
    }
    for (uint32_t i = 0; i < lv_obj_get_child_count(object); ++i) inspect(lv_obj_get_child(object, i));
  };
  inspect(lv_screen_active());
  auto images = doc["images"].to<JsonArray>();
  std::function<void(lv_obj_t *)> inspect_images = [&](lv_obj_t *object) {
    if (!lv_obj_is_visible(object)) return;
    if (lv_obj_check_type(object, &lv_image_class)) {
      auto item = images.add<JsonObject>();
      lv_area_t bounds; lv_obj_get_coords(object, &bounds);
      item["x"] = bounds.x1; item["y"] = bounds.y1;
      item["width"] = lv_obj_get_width(object); item["height"] = lv_obj_get_height(object);
      item["scale"] = lv_image_get_scale_x(object);
    }
    for (uint32_t i = 0; i < lv_obj_get_child_count(object); ++i) inspect_images(lv_obj_get_child(object, i));
  };
  inspect_images(lv_screen_active());
  diagnostics.clear(); serializeJson(doc, diagnostics);
  return diagnostics.c_str();
}
}
