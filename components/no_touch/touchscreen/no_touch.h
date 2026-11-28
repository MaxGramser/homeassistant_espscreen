#pragma once
// A touch panel that is not there (components/no_touch/__init__.py): it never reports a touch. LVGL gets an input
// device that is never pressed, and the listeners of the shared tree never hear one. It reads nothing, and its poller
// stops at its first round.
#include "esphome/components/touchscreen/touchscreen.h"

namespace esphome::no_touch {

class NoTouch : public touchscreen::Touchscreen {
 public:
  void setup() override {
    this->x_raw_max_ = this->display_width_;
    this->y_raw_max_ = this->display_height_;
  }
  void update() override { this->stop_poller(); }
  void dump_config() override { ESP_LOGCONFIG("no_touch", "Touchscreen: none (the glass takes no finger)"); }

 protected:
  void update_touches() override {}
};

}  // namespace esphome::no_touch
