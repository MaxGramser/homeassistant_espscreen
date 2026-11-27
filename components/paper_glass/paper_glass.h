#pragma once
// The paper glass (docs/PAPER.md): a panel of e-paper as the display LVGL draws on. It stands between LVGL and
// ESPHome's own e-paper driver (epaper_spi) and does two things, each a plain file with a test of its own:
//
// - Every pixel LVGL flushes becomes an ink of the panel before the driver sees it (paper_ink.h), so what is between
//   two inks prints as a raster instead of being cut to one of them.
// - LVGL's drawing does not start a refresh by itself. The printer (paper_print.h) is told what was drawn and when a
//   finger was there, and says when the panel refreshes and whether it refreshes a part or all of itself.
//
// To LVGL this is an ordinary display that is busy while its panel refreshes: ESPHome's `update_when_display_idle`
// holds LVGL's drawing for exactly that long and calls update() after every round of drawing. To the driver this is
// the only one that draws on it and the only one that updates it. The driver stays ESPHome's own, untouched: its
// models, its partial refresh, its busy pin.
//
// Nothing here knows a board, a card or Home Assistant. The firmware reaches the printer through paper.h.
#include "esphome/components/display/display.h"
#include "esphome/components/epaper_spi/epaper_spi.h"
#include "esphome/core/component.h"
#include "paper.h"

namespace esphome::paper_glass {

class PaperGlass : public display::Display {
 public:
  void set_panel(epaper_spi::EPaperBase *panel) { this->panel_ = panel; }
  void set_inks(uint8_t inks) { this->inks_ = inks; }
  void set_partial(bool partial) { this->partial_ = partial; }

  void setup() override;
  void loop() override;
  void dump_config() override;
  // After the panel, which is set up with the processor's own parts.
  float get_setup_priority() const override { return setup_priority::PROCESSOR - 1.0f; }
  // LVGL finished a round of drawing: the printer hears how much of the glass it changed.
  void update() override;

  // ---- the display LVGL draws on ----
  void draw_pixel_at(int x, int y, Color color) override;
  void fill(Color color) override;
  display::DisplayType get_display_type() override { return this->panel_->get_display_type(); }
  // The panel is never turned: LVGL turns what it draws and what a finger touches (display.py).
  int get_width() override { return this->panel_->get_native_width(); }
  int get_height() override { return this->panel_->get_native_height(); }

 protected:
  void draw_pixels_internal(int x_start, int y_start, int w, int h, const uint8_t *ptr, display::ColorBitness bitness,
                            bool big_endian, int x_offset, int y_offset, int x_pad) override;
  int get_width_internal() override { return this->panel_->get_native_width(); }
  int get_height_internal() override { return this->panel_->get_native_height(); }
  void print_(bool whole);

  epaper_spi::EPaperBase *panel_{};
  uint8_t *band_{};          // a few rows of ink, between LVGL's pixels and the driver
  size_t band_pixels_{};     // how many pixels the band holds
  uint32_t drawn_pixels_{};  // pixels flushed since the last update()
  uint32_t ink_us_{}, driver_us_{};  // what they took: as ink, and into the driver's buffer
  uint8_t inks_{2};
  bool partial_{true};
  bool printing_{};
};

}  // namespace esphome::paper_glass
