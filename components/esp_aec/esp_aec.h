#pragma once

#include "../esp_audio_stack/audio_core_processor.h"
#include "esphome/core/automation.h"
#include "esphome/core/component.h"

#ifdef USE_ESP32

#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

namespace esphome::esp_aec {

using esp_audio_stack::AudioFeature;
using esp_audio_stack::AudioProcessor;
using esp_audio_stack::FeatureControl;
using esp_audio_stack::FrameSpec;
using esp_audio_stack::ProcessorTelemetry;

/// Standalone Espressif AEC wrapper.
///
/// Implements AudioProcessor with only the echo canceller enabled
/// (WebRTC or neural, depending on mode). Lower memory footprint than
/// EspAfe. Intended for devices that only need echo cancellation without the
/// full AFE pipeline.
///
/// Consumers see AEC as just another
/// AudioProcessor; picking EspAec vs EspAfe is a YAML choice.
class EspAec final : public Component, public AudioProcessor {
 public:
  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::PROCESSOR; }

  // Config setters (called from Python)
  void set_sample_rate(int sample_rate) { this->sample_rate_ = sample_rate; }
  void set_filter_length(int filter_length) { this->filter_length_ = filter_length; }
  void set_mode(int mode) { this->mode_ = mode; }
  // How hard the canceller presses down what its filter leaves (ESP-SR's NLP level, the FD modes): 0 normal, 1
  // aggressive, 2 very aggressive; -1 leaves the library's own (aggressive in ESP-SR 2.5.5).
  void set_nlp_level(int level) { this->nlp_level_ = level; }
  // On demand: the canceller works only while something needs it (a call, the doorbell's Talk: set_needed), and at
  // rest it hands the microphone on untouched without running the DSP at all, which is what costs the processor. Not
  // on demand, it works whenever the microphone runs, as it always did.
  void set_on_demand(bool on_demand) {
    this->on_demand_ = on_demand;
    this->needed_.store(!on_demand, std::memory_order_relaxed);
  }
  void set_needed(bool needed) {
    if (this->on_demand_) this->needed_.store(needed, std::memory_order_relaxed);
  }
  bool at_work() const { return this->needed_.load(std::memory_order_relaxed) && this->enabled(); }
  // The same while it runs (a measurement that compares the levels in one call): kept for every handle made after.
  void set_nlp_level_now(int level);

  // AudioProcessor interface
  bool is_initialized() const override { return this->handle_ != nullptr; }
  FrameSpec frame_spec() const override;
  bool process(const int16_t *in_mic, const int16_t *in_ref, int16_t *out, uint8_t mic_channels_in) override;
  FeatureControl feature_control(AudioFeature feature) const override;
  bool set_feature(AudioFeature feature, bool enabled) override;
  ProcessorTelemetry telemetry() const override;
  bool reconfigure(int type, int mode) override;
  uint32_t frame_spec_revision() const override { return this->frame_spec_revision_.load(std::memory_order_acquire); }

  int get_mode() const { return this->mode_; }
  bool enabled() const { return this->enabled_.load(std::memory_order_relaxed); }
  uint32_t startup_silence_frames() const { return this->startup_silence_frames_.load(std::memory_order_relaxed); }
  static const char *get_mode_name(int mode);
  const char *get_mode_name() const { return get_mode_name(this->mode_); }

  ~EspAec() override;

 protected:
  bool reinit_(int new_mode);
  static int afe_type_from_mode(int mode);
  static int afe_cost_from_mode(int mode);

  void *handle_{nullptr};
  int16_t *input_frame_{nullptr};
  // L1 fix: guards handle_ lifecycle between process() and reinit_() / destructor.
  SemaphoreHandle_t handle_mutex_{nullptr};
  int sample_rate_{16000};
  int filter_length_{4};
  int cached_frame_size_{512};
  int mode_{0};
  int nlp_level_{-1};
  // The level set on a handle the library just made (after every create: a mode change makes another).
  void apply_nlp_level_(void *handle);
  std::atomic<uint32_t> frame_spec_revision_{0};
  int last_frame_size_{0};
  // ESP-SR 2.5.5 P4 FD-low-cost workaround for all-zero initial input.
  bool input_started_{false};  // Protected by handle_mutex_.
  std::atomic<uint32_t> startup_silence_frames_{0};
  // Output bypass: keep the adaptive filter current while disabled, without resetting the I2S stream.
  std::atomic<bool> enabled_{true};
  bool on_demand_{false};
  std::atomic<bool> needed_{true};
};

// Action: esp_aec.set_mode
template<typename... Ts> class SetModeAction : public Action<Ts...>, public Parented<EspAec> {
 public:
  TEMPLATABLE_VALUE(std::string, mode)
  void play(const Ts &...x) override {
    std::string name = this->mode_.value(x...);
    // Decode the user-facing mode string into the (type, cost) pair that
    // EspAec::reconfigure expects. type: 0=SR, 1=VC, 2=FD; cost: 0=low, 1=high.
    int type;
    int cost;
    if (name == "sr_low_cost") {
      type = 0;
      cost = 0;
    } else if (name == "sr_high_perf") {
      type = 0;
      cost = 1;
    } else if (name == "voip_low_cost") {
      type = 1;
      cost = 0;
    } else if (name == "voip_high_perf") {
      type = 1;
      cost = 1;
    } else if (name == "fd_low_cost") {
      type = 2;
      cost = 0;
    } else if (name == "fd_high_perf") {
      type = 2;
      cost = 1;
    } else {
      return;
    }
    this->parent_->reconfigure(type, cost);
  }
};

}  // namespace esphome::esp_aec

#endif  // USE_ESP32
