// The glass of an ESP32-S3's RGB panel (glass.h says what and why; glass_core.cpp has what every panel kind shares): the
// panel ESPHome's display made (st7701s, or any platform that makes it through esp_lcd_new_rgb_panel), picked up as
// ESP-IDF makes it, and its frame buffer.
//
// The frame buffer lies in PSRAM, and the panel reads it through bounce buffers in internal RAM that the panel's
// interrupt fills with the CPU, through the data cache: what a task writes into the frame buffer reaches the glass with
// the next refill, without a write-back of its own. LVGL's flushes copy into the same buffer on the main loop, under the
// same lock (glass_core.cpp).
//
// What an RGB panel does not give: an underrun count. When a refill comes too late the driver restarts its DMA at the
// next VBlank and tells nobody (esp_lcd_panel_rgb.c, lcd_rgb_panel_try_restart_transmission), so a frame that slipped
// sideways shows only to an eye (packages/hardware/esp32s3-rgb.yaml). misses() stays 0 here; it says nothing.
#include "glass.h"
#if defined(GLASS_RGB)
#include <esp_lcd_panel_rgb.h>
#if defined(SCREEN_PICTURES)

#include "lvgl.h"  // LV_COLOR_16_SWAP, LVGL's byte order for this display

namespace glass {

// ---- The panel ESPHome's display made (the wrap of esp_lcd_new_rgb_panel at the end of this file) ----
static esp_lcd_panel_handle_t panel_handle = nullptr;
static Panel panel_facts;
static void *buffer = nullptr;

static void panel_made(esp_lcd_panel_handle_t made, const esp_lcd_rgb_panel_config_t *config) {
  panel_handle = made;
  panel_facts.swapped = LV_COLOR_16_SWAP;
  panel_facts.w = static_cast<int>(config->timings.h_res);
  panel_facts.h = static_cast<int>(config->timings.v_res);
  // A frame buffer of its own (not one the display hands in) of one RGB565 pixel to every 16-bit word of the bus.
  panel_facts.rgb565 = config->data_width == 16 && (config->bits_per_pixel == 0 || config->bits_per_pixel == 16) &&
                       !config->flags.no_fb && config->num_fbs <= 1;
}
Panel panel() { return panel_facts; }
bool direct() { return panel_handle != nullptr && panel_facts.rgb565 && bound(); }
void *frame_buffer() {
  if (!buffer && panel_handle && esp_lcd_rgb_panel_get_frame_buffer(panel_handle, 1, &buffer) != ESP_OK) buffer = nullptr;
  return buffer;
}
void tick() {}
uint32_t misses() { return 0; }
std::string watch_said() { return {}; }  // no panel watch either: nothing tells a frame that slipped
void note_log_line() {}
void note_finger(bool) {}

}  // namespace glass
#endif  // SCREEN_PICTURES

// ESP-IDF makes the RGB panel for ESPHome's display: its handle and its size are picked up here as they are made
// (-Wl,--wrap=esp_lcd_new_rgb_panel, engine_build.py on every S3 with an RGB panel). On a board without pictures
// (no camera feature: the SenseCAP Indicator D1) the wrap only passes the call on, so the link finds it either way
// (release 0.4.91's CI, 2026-10-30: "undefined reference to __wrap_esp_lcd_new_rgb_panel").
extern "C" esp_err_t __real_esp_lcd_new_rgb_panel(const esp_lcd_rgb_panel_config_t *config, esp_lcd_panel_handle_t *made);
extern "C" esp_err_t __wrap_esp_lcd_new_rgb_panel(const esp_lcd_rgb_panel_config_t *config, esp_lcd_panel_handle_t *made) {
  const esp_err_t err = __real_esp_lcd_new_rgb_panel(config, made);
#if defined(SCREEN_PICTURES)
  if (err == ESP_OK && made && config) glass::panel_made(*made, config);
#else
  (void) made;
  (void) config;
#endif
  return err;
}
#endif  // GLASS_RGB
