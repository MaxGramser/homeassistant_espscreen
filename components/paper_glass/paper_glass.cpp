// The paper glass (paper_glass.h): LVGL's pixels to ink, and the printer's word to the panel.
// Every pixel LVGL draws passes through this file, a whole glass at a turn of a page, so it is built for speed where
// the rest of a firmware is built for size (the ink step took 280 ms of a turn at -Os, 2026-11-27).
#pragma GCC optimize("O3")
#include "paper_glass.h"

#include <algorithm>

#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"
#include "paper_ink.h"

namespace esphome::paper_glass {

static const char *const TAG = "paper_glass";
// The rows of ink made at a time: the band is this many of the panel's longest rows, so a flush of any shape goes to
// the driver in pieces of at most this size, and the band costs a few tens of KB whatever the panel.
static constexpr int BAND_ROWS = 16;

static PaperGlass *the_glass = nullptr;  // the printer's Glass is plain function pointers: one paper glass a screen

void PaperGlass::setup() {
  const int longest = std::max(this->panel_->get_native_width(), this->panel_->get_native_height());
  this->band_pixels_ = static_cast<size_t>(longest) * BAND_ROWS;
  RAMAllocator<uint8_t> allocator;
  this->band_ = allocator.allocate(this->band_pixels_ * 2);
  if (this->band_ == nullptr) {
    this->mark_failed(LOG_STR("No memory for the band of ink"));
    return;
  }
  the_glass = this;
  paper::inks() = this->inks_;
  auto &printer = paper::printer();
  if (!this->partial_) printer.rules = paper_print::poster();
  printer.glass.print = [](bool whole) { the_glass->print_(whole); };
  printer.glass.later = [](uint32_t ms) {
    the_glass->set_timeout("print", ms, []() { paper::printer().tick(millis()); });
  };
  // Idle to LVGL until a refresh runs: ESPHome's LVGL draws only while every display's loop is done.
  this->disable_loop();
}

void PaperGlass::dump_config() {
  ESP_LOGCONFIG(TAG,
                "Paper glass:\n"
                "  Inks: %u\n"
                "  Partial refresh: %s",
                this->inks_, YESNO(this->partial_));
}

// While the panel refreshes this loop runs, which is what holds LVGL's drawing; the panel going idle ends it.
void PaperGlass::loop() {
  if (this->printing_ && this->panel_->is_updating()) return;
  this->printing_ = false;
  this->disable_loop();
  paper::printer().printed(millis());
}

void PaperGlass::print_(bool whole) {
  if (whole) this->panel_->request_full_update();
  this->printing_ = true;
  this->enable_loop();
  this->panel_->update();
}

void PaperGlass::update() {
  const uint32_t glass = static_cast<uint32_t>(this->panel_->get_native_width()) * this->panel_->get_native_height();
  const uint32_t permille = glass == 0 ? 0 : std::min<uint64_t>(1000, static_cast<uint64_t>(this->drawn_pixels_) * 1000 / glass);
  // A page's worth says what it took, for whoever wonders where a slow turn of a page goes.
  if (permille >= 500)
    ESP_LOGI(TAG, "%u pixels: %u ms as ink, %u ms into the driver", (unsigned) this->drawn_pixels_,
             (unsigned) (this->ink_us_ / 1000), (unsigned) (this->driver_us_ / 1000));
  this->drawn_pixels_ = 0;
  this->ink_us_ = this->driver_us_ = 0;
  paper::printer().drawn(static_cast<uint16_t>(permille), millis());
}

void PaperGlass::fill(Color color) {
  this->panel_->fill(color);
  this->drawn_pixels_ += static_cast<uint32_t>(this->get_width()) * this->get_height();
}

void HOT PaperGlass::draw_pixel_at(int x, int y, Color color) {
  const uint8_t g = paper_ink::grey(paper_ink::level(paper_ink::luma(color.r, color.g, color.b), x, y, this->inks_), this->inks_);
  this->panel_->draw_pixel_at(x, y, Color(g, g, g));
  this->drawn_pixels_++;
}

// LVGL's flush: a block of RGB565. It goes to the driver as ink, a band of rows at a time, each pixel the ink of its
// own place on the glass.
void HOT PaperGlass::draw_pixels_internal(int x_start, int y_start, int w, int h, const uint8_t *ptr,
                                          display::ColorBitness bitness, bool big_endian, int x_offset, int y_offset,
                                          int x_pad) {
  if (w <= 0 || h <= 0) return;
  this->drawn_pixels_ += static_cast<uint32_t>(w) * h;
  if (bitness != display::COLOR_BITNESS_565 || this->band_ == nullptr || static_cast<size_t>(w) > this->band_pixels_) {
    this->panel_->draw_pixels_at(x_start, y_start, w, h, ptr, bitness, big_endian, x_offset, y_offset, x_pad);
    return;
  }
  const int stride = x_offset + w + x_pad;
  const uint8_t *source = ptr + (static_cast<size_t>(y_offset) * stride + x_offset) * 2;
  const int rows_a_band = std::max<int>(1, static_cast<int>(this->band_pixels_ / w));
  for (int row = 0; row < h; row += rows_a_band) {
    const int rows = std::min(rows_a_band, h - row);
    const uint32_t began = micros();
    paper_ink::block(source, this->band_, w, h, stride, row, rows, x_start, y_start, big_endian, this->inks_);
    const uint32_t inked = micros();
    this->panel_->draw_pixels_at(x_start, y_start + row, w, rows, this->band_, display::COLOR_BITNESS_565, big_endian);
    this->ink_us_ += inked - began;
    this->driver_us_ += micros() - inked;
  }
}

}  // namespace esphome::paper_glass
