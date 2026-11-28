#pragma once
// The sound output of a board's second chip as ESPHome's speaker (docs/SECOND_CHIP.md), so everything that plays on a
// speaker (a doorbell's chime, an alert's sound, a plugin's sounds: plugin_sound.h, kept_sound.h) plays on it as it is.
//
// play() takes sound of 16 bits at any rate, makes it mono and at most 24 kHz, and holds a second of it; loop() sends
// the chip as much as it has room for (chip_protocol::may_send), so the two seconds the chip holds ride out a loop
// that draws for half a second. A sound ends 300 ms after its last sample came: the chip plays out what it holds.
//
// The volume is the chip's: 0 to 1 runs evenly in decibels over the buzzer's range, as the volume of the other screens
// does (packages/features/audio-player.yaml), and 0 is silence.
//
// While no chip answers (chip_link.h), play() says it took the sound and lets it go: nothing waits for a chip that is
// not there.
#include <cstdint>

#include "chip_link.h"
#include "esphome/components/speaker/speaker.h"
#include "esphome/core/component.h"
#include "esphome/core/helpers.h"

namespace esphome::chip_link {

class ChipSpeaker : public Component, public speaker::Speaker {
 public:
  void set_link(ChipLink *link) { this->link_ = link; }
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::PROCESSOR; }

  using speaker::Speaker::play;
  size_t play(const uint8_t *data, size_t length) override;
  size_t play(const uint8_t *data, size_t length, TickType_t ticks_to_wait) override { return this->play(data, length); }
  void start() override;
  void stop() override;
  void finish() override;
  bool has_buffered_data() const override;
  void set_volume(float volume) override;
  void set_mute_state(bool mute_state) override;

 protected:
  // A second of 16 kHz between play() and the line.
  static constexpr uint32_t HELD = 16384;
  static constexpr uint32_t RATE_MOST = 24000;
  static constexpr uint32_t IDLE_MS = 300;
  // The volume's range in decibels, from just audible to the buzzer's loudest.
  static constexpr float RANGE_DB = 30.0f;

  void status_(uint8_t stream, uint8_t state, uint32_t taken, uint32_t played);
  uint32_t fill_() const { return this->head_ - this->tail_; }

  ChipLink *link_{nullptr};
  Mutex mutex_;
  int16_t *held_{nullptr};
  uint32_t head_{0}, tail_{0};
  uint32_t held_rate_{16000};   // of what is held
  uint8_t held_step_{1};        // how many frames that came in made one that is held
  // The stream on the chip.
  bool open_{false}, ending_{false}, finish_{false}, cut_{false}, volume_told_{false};
  uint8_t stream_{0}, step_{1};
  uint32_t rate_{0}, sent_{0}, played_{0}, last_ms_{0};
  uint8_t out_[chip_protocol::MOST];
};

}  // namespace esphome::chip_link
