#pragma once

#include "esphome/components/audio_adc/audio_adc.h"
#include "esphome/components/i2c/i2c.h"
#include "esphome/core/component.h"

#include "es7210_const.h"

namespace esphome::es7210 {

enum ES7210BitsPerSample : uint8_t {
  ES7210_BITS_PER_SAMPLE_16 = 16,
  ES7210_BITS_PER_SAMPLE_18 = 18,
  ES7210_BITS_PER_SAMPLE_20 = 20,
  ES7210_BITS_PER_SAMPLE_24 = 24,
  ES7210_BITS_PER_SAMPLE_32 = 32,
};

class ES7210 final : public audio_adc::AudioAdc, public Component, public i2c::I2CDevice {
  /* Class for configuring an ES7210 ADC for microphone input.
   * Based on code from:
   * - https://github.com/espressif/esp-bsp/ (accessed 20241219)
   * - https://github.com/espressif/esp-adf/ (accessed 20241219)
   */
 public:
  void setup() override;
  void dump_config() override;

  void set_bits_per_sample(ES7210BitsPerSample bits_per_sample) { this->bits_per_sample_ = bits_per_sample; }
  bool set_mic_gain(float mic_gain) override;
  bool set_digital_gain(float gain);
  bool set_alc_enabled(bool enabled);
  float digital_gain() const { return this->digital_gain_; }
  bool alc_enabled() const { return this->alc_enabled_; }
  void set_alc_max_gain(float gain) { this->alc_max_gain_ = gain; }
  void set_alc_target(uint8_t target) { this->alc_target_ = target; }
  void set_alc_ramp_rate(uint8_t rate) { this->alc_ramp_rate_ = rate; }
  void set_sample_rate(uint32_t sample_rate) { this->sample_rate_ = sample_rate; }
  void set_tdm(bool enabled) { this->enable_tdm_ = enabled; }
  void set_reference(uint8_t channel, float gain) {
    this->reference_channel_ = channel;
    this->reference_gain_ = gain;
  }

  float mic_gain() override { return this->mic_gain_; };

 protected:
  /// @brief Updates an I2C registry address by modifying the current state
  /// @param reg_addr I2C register address
  /// @param update_bits Mask of allowed bits to be modified
  /// @param data Bit values to be written
  /// @return True if successful, false otherwise
  bool es7210_update_reg_bit_(uint8_t reg_addr, uint8_t update_bits, uint8_t data);

  /// @brief Convert floating point mic gain value to register value
  /// @param mic_gain Gain value to convert
  /// @return Corresponding register value for specified gain
  uint8_t es7210_gain_reg_value_(float mic_gain);

  bool configure_i2s_format_();
  bool configure_mic_gain_();
  bool configure_sample_rate_();
  bool configure_digital_gain_(float gain, bool alc_enabled);
  bool update_digital_gain_(float gain, bool alc_enabled);

  bool setup_complete_{false};
  bool enable_tdm_{false};
  uint8_t reference_channel_{0};  // Physical ADC number, 1-4; zero means no reference channel.
  float reference_gain_{0.0f};
  float mic_gain_{0};
  float digital_gain_{0.0f};
  float alc_max_gain_{12.0f};
  uint8_t alc_target_{0xF7};  // -12 to -6 dBFS
  uint8_t alc_ramp_rate_{6};
  bool alc_enabled_{false};
  ES7210BitsPerSample bits_per_sample_{ES7210_BITS_PER_SAMPLE_16};
  uint32_t sample_rate_{0};
};

}  // namespace esphome::es7210
