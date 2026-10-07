#include "es7210.h"
#include "es7210_const.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include <cinttypes>
#include <cmath>

namespace esphome::es7210 {

static const char *const TAG = "es7210";

static const size_t MCLK_DIV_FRE = 256;

// Mark the component as failed; use only in setup
#define ES7210_ERROR_FAILED(func) \
  if (!(func)) { \
    this->mark_failed(); \
    return; \
  }

// Return false; use outside of setup
#define ES7210_ERROR_CHECK(func) \
  if (!(func)) { \
    return false; \
  }

void ES7210::dump_config() {
  ESP_LOGCONFIG(TAG,
                "ES7210 audio ADC:\n"
                "  Bits Per Sample: %" PRIu8 "\n"
                "  Sample Rate: %" PRIu32,
                this->bits_per_sample_, this->sample_rate_);
  ESP_LOGCONFIG(TAG, "  Digital Gain: %.1f dB\n  ALC: %s\n  ALC Maximum Gain: %.1f dB", this->digital_gain_,
                ONOFF(this->alc_enabled_), this->alc_max_gain_);
  ESP_LOGCONFIG(TAG, "  TDM: %s", ONOFF(this->enable_tdm_));
  if (this->reference_channel_ != 0) {
    ESP_LOGCONFIG(TAG, "  Reference ADC: %u\n  Reference Gain: %.1f dB (fixed digital gain, no ALC)",
                  this->reference_channel_, this->reference_gain_);
  }

  if (this->is_failed()) {
    ESP_LOGE(TAG, "  Failed to initialize");
    return;
  }
}

void ES7210::setup() {
  // Software reset
  ES7210_ERROR_FAILED(this->write_byte(ES7210_RESET_REG00, 0xff));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_RESET_REG00, 0x32));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_CLOCK_OFF_REG01, 0x3f));

  // Set initialization time when device powers up
  ES7210_ERROR_FAILED(this->write_byte(ES7210_TIME_CONTROL0_REG09, 0x30));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_TIME_CONTROL1_REG0A, 0x30));

  // Configure HFP for all ADC channels
  ES7210_ERROR_FAILED(this->write_byte(ES7210_ADC12_HPF2_REG23, 0x2a));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_ADC12_HPF1_REG22, 0x0a));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_ADC34_HPF2_REG20, 0x0a));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_ADC34_HPF1_REG21, 0x2a));

  // Secondary I2S mode settings
  ES7210_ERROR_FAILED(this->es7210_update_reg_bit_(ES7210_MODE_CONFIG_REG08, 0x01, 0x00));

  // Configure analog power
  ES7210_ERROR_FAILED(this->write_byte(ES7210_ANALOG_REG40, 0xC3));

  // Set mic bias
  ES7210_ERROR_FAILED(this->write_byte(ES7210_MIC12_BIAS_REG41, 0x70));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_MIC34_BIAS_REG42, 0x70));

  // Configure I2S settings, sample rate, and microphone gains
  ES7210_ERROR_FAILED(this->configure_i2s_format_());
  ES7210_ERROR_FAILED(this->configure_sample_rate_());
  ES7210_ERROR_FAILED(this->configure_mic_gain_());
  ES7210_ERROR_FAILED(this->configure_digital_gain_(this->digital_gain_, this->alc_enabled_));

  // Power on mics 1 through 4
  ES7210_ERROR_FAILED(this->write_byte(ES7210_MIC1_POWER_REG47, 0x08));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_MIC2_POWER_REG48, 0x08));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_MIC3_POWER_REG49, 0x08));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_MIC4_POWER_REG4A, 0x08));

  // Power down DLL
  ES7210_ERROR_FAILED(this->write_byte(ES7210_POWER_DOWN_REG06, 0x04));

  // Power on MIC1-4 bias & ADC1-4 & PGA1-4 Power
  ES7210_ERROR_FAILED(this->write_byte(ES7210_MIC12_POWER_REG4B, 0x0F));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_MIC34_POWER_REG4C, 0x0F));

  // Enable device
  ES7210_ERROR_FAILED(this->write_byte(ES7210_RESET_REG00, 0x71));
  ES7210_ERROR_FAILED(this->write_byte(ES7210_RESET_REG00, 0x41));

  this->setup_complete_ = true;
}

bool ES7210::set_mic_gain(float mic_gain) {
  this->mic_gain_ = clamp<float>(mic_gain, ES7210_MIC_GAIN_MIN, ES7210_MIC_GAIN_MAX);
  if (this->setup_complete_) {
    return this->configure_mic_gain_();
  }
  return true;
}

bool ES7210::set_digital_gain(float gain) {
  if (this->is_failed() || !std::isfinite(gain) || gain < -95.5f || gain > 32.0f)
    return false;
  gain = roundf(gain * 2.0f) / 2.0f;
  // Preserve the manual value while ALC owns the gain registers.
  if (this->alc_enabled_) {
    this->digital_gain_ = gain;
    return true;
  }
  return this->update_digital_gain_(gain, false);
}

bool ES7210::set_alc_enabled(bool enabled) { return this->update_digital_gain_(this->digital_gain_, enabled); }

bool ES7210::update_digital_gain_(float gain, bool alc_enabled) {
  if (this->is_failed())
    return false;
  if (this->setup_complete_ && !this->configure_digital_gain_(gain, alc_enabled)) {
    // Keep the reported settings unchanged on an I2C error and try to restore the previous mode.
    this->configure_digital_gain_(this->digital_gain_, this->alc_enabled_);
    this->status_set_warning();
    ESP_LOGW(TAG, "Failed to apply digital gain/ALC settings");
    return false;
  }
  this->digital_gain_ = gain;
  this->alc_enabled_ = alc_enabled;
  this->status_clear_warning();
  return true;
}

bool ES7210::configure_digital_gain_(float gain, bool alc_enabled) {
  // ES7210 datasheet rev 21, registers 0x16-0x1E. ALC and fixed digital gain share registers.
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_ALC_SELECT_REG16, 0x0F, 0x00));
  const float active_gain = alc_enabled ? this->alc_max_gain_ : gain;
  const auto gain_value = static_cast<uint8_t>(roundf((active_gain + 95.5f) * 2.0f));
  for (uint8_t i = 0; i < 4; i++) {
    // Digital gain registers run ADC4 to ADC1. Keep a playback reference at unity.
    const uint8_t value = this->reference_channel_ == 4 - i ? 0xBF : gain_value;
    ES7210_ERROR_CHECK(this->write_byte(ES7210_ADC4_GAIN_REG1B + i, value));
  }
  if (alc_enabled) {
    ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_ALC_RAMP_REG17, 0x0F, this->alc_ramp_rate_));
    ES7210_ERROR_CHECK(this->write_byte(ES7210_ALC34_TARGET_REG18, this->alc_target_));
    ES7210_ERROR_CHECK(this->write_byte(ES7210_ALC12_TARGET_REG19, this->alc_target_));
    // ALC bits likewise run ADC4 (bit 0) to ADC1 (bit 3).
    const uint8_t mask = this->reference_channel_ == 0 ? 0x0F : 0x0F & ~(1U << (4 - this->reference_channel_));
    ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_ALC_SELECT_REG16, 0x0F, mask));
  }
  return true;
}

bool ES7210::configure_sample_rate_() {
  uint32_t mclk_fre = this->sample_rate_ * MCLK_DIV_FRE;
  int coeff = -1;

  for (size_t i = 0; i < (sizeof(ES7210_COEFFICIENTS) / sizeof(ES7210_COEFFICIENTS[0])); ++i) {
    if (ES7210_COEFFICIENTS[i].lrclk == this->sample_rate_ && ES7210_COEFFICIENTS[i].mclk == mclk_fre)
      coeff = static_cast<int>(i);
  }

  if (coeff >= 0) {
    // Set adc_div & doubler & dll
    uint8_t regv;
    ES7210_ERROR_CHECK(this->read_byte(ES7210_MAINCLK_REG02, &regv));
    regv = regv & 0x00;
    regv |= ES7210_COEFFICIENTS[coeff].adc_div;
    regv |= ES7210_COEFFICIENTS[coeff].doubler << 6;
    regv |= ES7210_COEFFICIENTS[coeff].dll << 7;

    ES7210_ERROR_CHECK(this->write_byte(ES7210_MAINCLK_REG02, regv));

    // Set osr
    regv = ES7210_COEFFICIENTS[coeff].osr;
    ES7210_ERROR_CHECK(this->write_byte(ES7210_OSR_REG07, regv));
    // Set lrck
    regv = ES7210_COEFFICIENTS[coeff].lrck_h;
    ES7210_ERROR_CHECK(this->write_byte(ES7210_LRCK_DIVH_REG04, regv));
    regv = ES7210_COEFFICIENTS[coeff].lrck_l;
    ES7210_ERROR_CHECK(this->write_byte(ES7210_LRCK_DIVL_REG05, regv));
  } else {
    // Invalid sample frequency
    ESP_LOGE(TAG, "Invalid sample rate");
    return false;
  }

  return true;
}

bool ES7210::configure_mic_gain_() {
  auto regv = this->es7210_gain_reg_value_(this->mic_gain_);
  for (uint8_t i = 0; i < 4; ++i) {
    ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_MIC1_GAIN_REG43 + i, 0x10, 0x00));
  }
  ES7210_ERROR_CHECK(this->write_byte(ES7210_MIC12_POWER_REG4B, 0xff));
  ES7210_ERROR_CHECK(this->write_byte(ES7210_MIC34_POWER_REG4C, 0xff));

  // Configure mic 1
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_CLOCK_OFF_REG01, 0x0b, 0x00));
  ES7210_ERROR_CHECK(this->write_byte(ES7210_MIC12_POWER_REG4B, 0x00));
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_MIC1_GAIN_REG43, 0x10, 0x10));
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_MIC1_GAIN_REG43, 0x0f, regv));

  // Configure mic 2
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_CLOCK_OFF_REG01, 0x0b, 0x00));
  ES7210_ERROR_CHECK(this->write_byte(ES7210_MIC12_POWER_REG4B, 0x00));
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_MIC2_GAIN_REG44, 0x10, 0x10));
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_MIC2_GAIN_REG44, 0x0f, regv));

  // Configure mic 3
  // MIC3 uses the ADC3/4 and MIC3/4 clock domains (bits 2 and 4), not the MIC1/2 domains.
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_CLOCK_OFF_REG01, 0x15, 0x00));
  ES7210_ERROR_CHECK(this->write_byte(ES7210_MIC34_POWER_REG4C, 0x00));
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_MIC3_GAIN_REG45, 0x10, 0x10));
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_MIC3_GAIN_REG45, 0x0f, regv));

  // Configure mic 4
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_CLOCK_OFF_REG01, 0x15, 0x00));
  ES7210_ERROR_CHECK(this->write_byte(ES7210_MIC34_POWER_REG4C, 0x00));
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_MIC4_GAIN_REG46, 0x10, 0x10));
  ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_MIC4_GAIN_REG46, 0x0f, regv));

  if (this->reference_channel_ != 0) {
    ES7210_ERROR_CHECK(this->es7210_update_reg_bit_(ES7210_MIC1_GAIN_REG43 + this->reference_channel_ - 1, 0x0f,
                                                 this->es7210_gain_reg_value_(this->reference_gain_)));
  }
  return true;
}

uint8_t ES7210::es7210_gain_reg_value_(float mic_gain) {
  // reg: 12 - 34.5dB, 13 - 36dB, 14 - 37.5dB
  mic_gain += 0.5f;
  if (mic_gain <= 33.0f) {
    return (uint8_t) (mic_gain / 3);
  }
  if (mic_gain < 36.0f) {
    return 12;
  }
  if (mic_gain < 37.0f) {
    return 13;
  }
  return 14;
}

bool ES7210::configure_i2s_format_() {
  // Configure bits per sample
  uint8_t reg_val = 0;
  switch (this->bits_per_sample_) {
    case ES7210_BITS_PER_SAMPLE_16:
      reg_val = 0x60;
      break;
    case ES7210_BITS_PER_SAMPLE_18:
      reg_val = 0x40;
      break;
    case ES7210_BITS_PER_SAMPLE_20:
      reg_val = 0x20;
      break;
    case ES7210_BITS_PER_SAMPLE_24:
      reg_val = 0x00;
      break;
    case ES7210_BITS_PER_SAMPLE_32:
      reg_val = 0x80;
      break;
    default:
      return false;
  }
  ES7210_ERROR_CHECK(this->write_byte(ES7210_SDP_INTERFACE1_REG11, reg_val));

  if (this->enable_tdm_) {
    ES7210_ERROR_CHECK(this->write_byte(ES7210_SDP_INTERFACE2_REG12, 0x02));
  } else {
    // Microphones 1 and 2 output on SDOUT1, microphones 3 and 4 output on SDOUT2
    ES7210_ERROR_CHECK(this->write_byte(ES7210_SDP_INTERFACE2_REG12, 0x00));
  }

  return true;
}

bool ES7210::es7210_update_reg_bit_(uint8_t reg_addr, uint8_t update_bits, uint8_t data) {
  uint8_t regv;
  ES7210_ERROR_CHECK(this->read_byte(reg_addr, &regv));
  regv = (regv & (~update_bits)) | (update_bits & data);
  return this->write_byte(reg_addr, regv);
}

}  // namespace esphome::es7210
