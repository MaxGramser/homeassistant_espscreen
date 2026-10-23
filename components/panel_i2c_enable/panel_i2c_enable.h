#pragma once

#include <vector>

#include "esphome/components/i2c/i2c.h"
#include "esphome/core/component.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome {
namespace panel_i2c_enable {

// Switches a panel on through an I2C register before any display sets up. See __init__.py for why this is a
// component and not an on_boot automation: the shared on_boot runs at priority -100, far too late.
class PanelI2CEnable : public Component, public i2c::I2CDevice {
 public:
  // setup_priority::IO is after the I2C bus (BUS) and before every display, which is the whole point of this
  // component: the panel has to be live before the display driver talks to it.
  float get_setup_priority() const override { return setup_priority::IO; }

  void add_write(uint8_t reg, uint8_t value) { this->steps_.push_back({reg, value, 0}); }
  void add_delay(uint32_t ms) { this->steps_.push_back({0, 0, ms}); }

  void setup() override {
    for (const auto &step : this->steps_) {
      if (step.delay_ms != 0) {
        // Blocking on purpose: the panel must be ready before the next write, and before the display sets up.
        delay(step.delay_ms);
        continue;
      }
      const uint8_t payload[2] = {step.reg, step.value};
      if (this->write(payload, sizeof(payload)) != i2c::ERROR_OK) {
        ESP_LOGE("panel_i2c_enable", "write %02X <- %02X failed", step.reg, step.value);
        this->mark_failed();
        return;
      }
    }
  }

  void dump_config() override {
    ESP_LOGCONFIG("panel_i2c_enable", "Panel I2C enable:");
    ESP_LOGCONFIG("panel_i2c_enable", "  Address: 0x%02X", this->address_);
    ESP_LOGCONFIG("panel_i2c_enable", "  Steps: %u", (unsigned) this->steps_.size());
    if (this->is_failed())
      ESP_LOGE("panel_i2c_enable", "  The panel did not acknowledge: the display will not come up.");
  }

 protected:
  struct Step {
    uint8_t reg;
    uint8_t value;
    uint32_t delay_ms;
  };
  std::vector<Step> steps_;
};

}  // namespace panel_i2c_enable
}  // namespace esphome
