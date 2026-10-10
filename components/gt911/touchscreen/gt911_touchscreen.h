#pragma once

#include "esphome/components/i2c/i2c.h"
#include "esphome/components/touchscreen/touchscreen.h"
#include "esphome/core/component.h"
#include "esphome/core/hal.h"

namespace esphome::gt911 {

class GT911ButtonListener {
 public:
  virtual void update_button(uint8_t index, bool state) = 0;
};

class GT911Touchscreen final : public touchscreen::Touchscreen, public i2c::I2CDevice {
 public:
  /// Power-cycle the Waveshare board rail, release touch reset, then probe both GT911 addresses.
  void setup() override;
  void dump_config() override;
  bool can_proceed() override { return this->setup_done_; }

  /// Set a interrupt pin (supports hardware interrupts or expander connected).
  void set_interrupt_pin(GPIOPin *pin) { this->interrupt_pin_ = pin; }
  void set_reset_pin(GPIOPin *pin) { this->reset_pin_ = pin; }
  void set_power_pin(GPIOPin *pin) { this->power_pin_ = pin; }
  void register_button_listener(GT911ButtonListener *listener) { this->button_listeners_.push_back(listener); }

 protected:
  void update_touches() override;

  bool init_sequence_();
  bool configuration_valid_(uint8_t *switches, uint16_t *x_res, uint16_t *y_res);
  /// @brief Perform the internal setup routine for the GT911 touchscreen.
  ///
  /// This function checks the I2C address, configures the interrupt pin (if available),
  /// reads the touchscreen mode from the controller, and attempts to read calibration
  /// data (maximum X and Y values) if not already set.
  ///
  /// Sets @ref setup_done_ after applying the state validated by configuration_valid_().
  void setup_internal_(uint8_t switches, uint16_t x_res, uint16_t y_res);
  i2c::ErrorCode probe_address_(uint8_t address, uint8_t *switches);
  /// @brief True if the touchscreen setup has completed successfully.
  bool setup_done_{false};
  /// @brief read device information registers from gt911 (product-id, firmware-version, config-version and resolution)
  void read_device_info_();

  GPIOPin *interrupt_pin_{nullptr};
  GPIOPin *reset_pin_{nullptr};
  GPIOPin *power_pin_{nullptr};
  std::vector<GT911ButtonListener *> button_listeners_;
  uint8_t button_state_{0xFF};  // last button state. Initial FF guarantees first update.
};

}  // namespace esphome::gt911
