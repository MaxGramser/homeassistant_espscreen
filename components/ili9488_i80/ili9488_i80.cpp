#include "ili9488_i80.h"
#include "pixels.h"
#include "esphome/core/log.h"
#include "esp_heap_caps.h"
#include <algorithm>

namespace esphome::ili9488_i80 {
static const char *const TAG = "ili9488_i80";

bool ILI9488I80::check_(esp_err_t error) {
  if (error == ESP_OK) return true;
  ESP_LOGE(TAG, "LCD transfer/setup failed: %s", esp_err_to_name(error));
  this->mark_failed();
  return false;
}

bool IRAM_ATTR ILI9488I80::complete_(esp_lcd_panel_io_handle_t, esp_lcd_panel_io_event_data_t *, void *context) {
  BaseType_t wake = pdFALSE;
  xSemaphoreGiveFromISR(static_cast<ILI9488I80 *>(context)->done_, &wake);
  return wake == pdTRUE;
}

bool ILI9488I80::command_(uint8_t command, std::initializer_list<uint8_t> data) {
  return !this->is_failed() && this->check_(esp_lcd_panel_io_tx_param(io_, command, data.begin(), data.size()));
}

void ILI9488I80::setup() {
  // No reads: RD must stay high. CS is tied active and reset follows the board reset.
  rd_pin_->setup();
  rd_pin_->digital_write(true);
  done_ = xSemaphoreCreateBinary();
  buffer_ = static_cast<uint16_t *>(heap_caps_malloc(BUFFER_PIXELS * sizeof(uint16_t), MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL));
  if (done_ == nullptr || buffer_ == nullptr) {
    ESP_LOGE(TAG, "Cannot allocate LCD DMA buffer/semaphore");
    this->mark_failed();
    return;
  }
  esp_lcd_i80_bus_config_t bus{};
  bus.dc_gpio_num = dc_pin_->get_pin();
  bus.wr_gpio_num = wr_pin_->get_pin();
  bus.clk_src = LCD_CLK_SRC_DEFAULT;
  bus.bus_width = 16;
  bus.max_transfer_bytes = BUFFER_PIXELS * sizeof(uint16_t);
  for (size_t i = 0; i < 16; ++i) bus.data_gpio_nums[i] = data_pins_[i]->get_pin();
  if (!check_(esp_lcd_new_i80_bus(&bus, &bus_))) return;
  esp_lcd_panel_io_i80_config_t io{};
  io.cs_gpio_num = -1;
  io.pclk_hz = data_rate_;
  io.trans_queue_depth = 1;
  io.lcd_cmd_bits = 8;
  io.lcd_param_bits = 8;  // IDF expands each parameter onto D0..D7 of the 16-bit bus.
  io.dc_levels.dc_idle_level = 1;
  io.dc_levels.dc_cmd_level = 0;
  io.dc_levels.dc_dummy_level = 0;
  io.dc_levels.dc_data_level = 1;
  io.on_color_trans_done = complete_;
  io.user_ctx = this;
  if (!check_(esp_lcd_new_panel_io_i80(bus_, &io, &io_))) return;
  if (!command_(0x01)) return;  // Software reset also makes OTA restarts deterministic.
  delay(150);
  // Register values from Elecrow's bundled LovyanGFX Panel_ILI9488 example.
  if (!command_(0xC0, {0x17, 0x15}) || !command_(0xC1, {0x41}) ||
      !command_(0xC5, {0x00, 0x12, 0x80}) || !command_(0xB1, {0xA0}) ||
      !command_(0xB4, {0x02}) || !command_(0xB6, {0x02, 0x22, 0x3B}) ||
      !command_(0xB7, {0xC6}) || !command_(0xF7, {0xA9, 0x51, 0x2C, 0x82}) ||
      !command_(0x3A, {0x55}) || !command_(0x36, {madctl_}) ||
      !command_(invert_colors_ ? 0x21 : 0x20) || !command_(0x11)) return;
  delay(120);
  if (!command_(0x38) || !command_(0x29)) return;
  delay(100);
}

bool ILI9488I80::window_(int x, int y, int w, int h) {
  const int right = x + w - 1, bottom = y + h - 1;
  return command_(0x2A, {uint8_t(x >> 8), uint8_t(x), uint8_t(right >> 8), uint8_t(right)}) &&
         command_(0x2B, {uint8_t(y >> 8), uint8_t(y), uint8_t(bottom >> 8), uint8_t(bottom)});
}

bool ILI9488I80::send_(size_t pixels) {
  if (!check_(esp_lcd_panel_io_tx_color(io_, 0x2C, buffer_, pixels * sizeof(uint16_t)))) return false;
  if (xSemaphoreTake(done_, pdMS_TO_TICKS(1000)) == pdTRUE) return true;
  // Do not reuse/free a buffer that DMA may still own. A failed display stays failed until restart.
  ESP_LOGE(TAG, "LCD DMA timed out");
  this->mark_failed();
  return false;
}

void ILI9488I80::draw_pixels_at(int x, int y, int w, int h, const uint8_t *ptr, display::ColorOrder order,
                               display::ColorBitness bitness, bool big_endian, int x_offset, int y_offset, int x_pad) {
  if (this->is_failed() || io_ == nullptr || w <= 0 || h <= 0) return;
  if (x < 0 || y < 0 || x + w > 320 || y + h > 480 || x_offset < 0 || y_offset < 0 || x_pad < 0) return;
  if (bitness != display::COLOR_BITNESS_565) {
    display::Display::draw_pixels_at(x, y, w, h, ptr, order, bitness, big_endian, x_offset, y_offset, x_pad);
    return;
  }
  const size_t stride = x_offset + w + x_pad;
  for (int row = 0; row < h;) {
    const int rows = std::min(h - row, int(BUFFER_PIXELS / w));
    for (int r = 0; r < rows; ++r) {
      const uint8_t *source = ptr + ((y_offset + row + r) * stride + x_offset) * 2;
      pack_pixels(buffer_ + r * w, source, w, big_endian, order == display::COLOR_ORDER_BGR);
    }
    if (!window_(x, y + row, w, rows) || !send_(w * rows)) return;
    row += rows;
  }
}

void ILI9488I80::draw_pixel_at(int x, int y, Color color) {
  if (this->is_failed() || io_ == nullptr || x < 0 || y < 0 || x >= 320 || y >= 480 ||
      !this->get_clipping().inside(x, y)) return;
  buffer_[0] = ((uint16_t(color.red) & 0xF8) << 8) | ((uint16_t(color.green) & 0xFC) << 3) | (color.blue >> 3);
  if (window_(x, y, 1, 1)) send_(1);
}

void ILI9488I80::dump_config() {
  ESP_LOGCONFIG(TAG, "ILI9488 320x480, 16-bit i80, %u Hz, MADCTL 0x%02X", (unsigned) data_rate_, madctl_);
}
}  // namespace esphome::ili9488_i80
