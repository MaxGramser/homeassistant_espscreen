// ILI9488 DBI Type B, 16 data pins. LVGL owns rotation; this driver owns transport only.
// A small internal DMA buffer is reused only after the transfer completion semaphore.
#pragma once
#include "esphome/components/display/display.h"
#include "esphome/core/gpio.h"
#include "esp_lcd_panel_io.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <initializer_list>

namespace esphome::ili9488_i80 {
class ILI9488I80 : public display::Display {
 public:
  void setup() override;
  void dump_config() override;
  void update() override { this->do_update_(); }
  float get_setup_priority() const override { return setup_priority::HARDWARE; }
  display::DisplayType get_display_type() override { return display::DISPLAY_TYPE_COLOR; }
  void draw_pixel_at(int x, int y, Color color) override;
  void draw_pixels_at(int x, int y, int w, int h, const uint8_t *ptr, display::ColorOrder order,
                      display::ColorBitness bitness, bool big_endian, int x_offset, int y_offset, int x_pad) override;
  void set_data_pin(size_t index, InternalGPIOPin *pin) { data_pins_[index] = pin; }
  void set_dc_pin(InternalGPIOPin *pin) { dc_pin_ = pin; }
  void set_wr_pin(InternalGPIOPin *pin) { wr_pin_ = pin; }
  void set_rd_pin(InternalGPIOPin *pin) { rd_pin_ = pin; }
  void set_data_rate(uint32_t rate) { data_rate_ = rate; }
  void set_madctl(uint8_t value) { madctl_ = value; }
  void set_invert_colors(bool value) { invert_colors_ = value; }
 protected:
  int get_width_internal() override { return 320; }
  int get_height_internal() override { return 480; }
  bool command_(uint8_t command, std::initializer_list<uint8_t> data = {});
  bool window_(int x, int y, int w, int h);
  bool send_(size_t pixels);
  bool check_(esp_err_t error);
  static bool IRAM_ATTR complete_(esp_lcd_panel_io_handle_t, esp_lcd_panel_io_event_data_t *, void *context);
  InternalGPIOPin *data_pins_[16]{};
  InternalGPIOPin *dc_pin_{nullptr}, *wr_pin_{nullptr}, *rd_pin_{nullptr};
  esp_lcd_i80_bus_handle_t bus_{nullptr};
  esp_lcd_panel_io_handle_t io_{nullptr};
  SemaphoreHandle_t done_{nullptr};
  static constexpr size_t BUFFER_PIXELS = 320 * 16;
  uint16_t *buffer_{nullptr};
  uint32_t data_rate_{10000000};
  uint8_t madctl_{0x08};
  bool invert_colors_{false};
};
}  // namespace esphome::ili9488_i80
