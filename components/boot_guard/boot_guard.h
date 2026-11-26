#pragma once
// Strict confirmation of a new firmware image (components/boot_guard/README.md).
#include "esphome/core/component.h"
#include "esphome/core/defines.h"
#ifdef USE_TEXT_SENSOR
#include "esphome/components/text_sensor/text_sensor.h"
#endif
#ifdef USE_SAFE_MODE_PRESENT_FOR_BOOT_GUARD
#include "esphome/components/safe_mode/safe_mode.h"
#endif
#include "boot_guard_decision.h"

namespace esphome::boot_guard {

class BootGuard : public Component {
 public:
  void set_confirm_after(uint32_t ms) { this->cfg_.confirm_after_ms = ms; }
  void set_deadline(uint32_t ms) { this->cfg_.deadline_ms = ms; }
  void set_require_api_client(bool v) { this->cfg_.require_api_client = v; }
#ifdef USE_SAFE_MODE_PRESENT_FOR_BOOT_GUARD
  void set_safe_mode(safe_mode::SafeModeComponent *sm) { this->safe_mode_ = sm; }
#endif
#ifdef USE_TEXT_SENSOR
  void set_state_sensor(text_sensor::TextSensor *s) { this->state_sensor_ = s; }
#endif

  void setup() override;
  void loop() override;
  void dump_config() override;
  // After the network, so the first loop already sees a connection if there is one.
  float get_setup_priority() const override { return setup_priority::LATE; }

 protected:
  void publish_(const char *state);
  bool confirm_();
  void roll_back_(const char *why);

  Config cfg_{180000, 900000, true};
#ifdef USE_SAFE_MODE_PRESENT_FOR_BOOT_GUARD
  safe_mode::SafeModeComponent *safe_mode_{nullptr};
#endif
#ifdef USE_TEXT_SENSOR
  text_sensor::TextSensor *state_sensor_{nullptr};
#endif
  bool api_seen_{false};
  bool confirm_failed_{false};
  uint32_t last_report_ms_{0};
};

}  // namespace esphome::boot_guard
