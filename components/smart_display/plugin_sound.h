#pragma once
// A plugin's sounds (plugin API 0.8, docs/FIRMWARE_API.md in the plugins repository, "Sounds"): the samples of a WAV
// file in flash, which smart_display.sound() builds in from the plugin's folder, played on the screen's speaker
// (ts_speaker, the feature speaker) one at a time. Only a plugin that needs the speaker includes this.
#include <cstddef>
#include <cstdint>

#include "esphome/components/audio/audio.h"
#include "esphome/components/speaker/speaker.h"
#include "esphome/core/hal.h"

namespace tessera {

struct Sound {
  const uint8_t *data{};
  size_t length{0};        // bytes
  uint32_t rate{16000};
  uint8_t channels{1};
};

// One sound at a time on a speaker. play() starts one in place of the one that plays; loop(), from the plugin
// component's own loop(), hands the speaker as much as it takes now and never waits. A sound the speaker takes nothing
// of for a second is dropped: on a board whose microphone shares the speaker's bus (AUDIO_HALF_DUPLEX), a sound waits
// while something listens, and a moment later it is no longer the right one.
class SoundPlayer {
 public:
  void set_speaker(esphome::speaker::Speaker *speaker) { speaker_ = speaker; }
  void play(const Sound &sound) {
    if (speaker_ == nullptr || sound.length == 0) return;
    speaker_->set_audio_stream_info(esphome::audio::AudioStreamInfo(16, sound.channels, sound.rate));
    playing_ = &sound;
    played_ = 0;
    since_ = esphome::millis();
  }
  void stop() { playing_ = nullptr; }
  bool playing() const { return playing_ != nullptr; }
  bool playing(const Sound &sound) const { return playing_ == &sound; }
  void loop() {
    if (playing_ == nullptr || speaker_ == nullptr) return;
    const size_t taken = speaker_->play(playing_->data + played_, playing_->length - played_, 0);
    const uint32_t now = esphome::millis();
    if (taken > 0) {
      played_ += taken;
      since_ = now;
    } else if (now - since_ > GIVE_UP_MS) {
      playing_ = nullptr;
      return;
    }
    if (played_ >= playing_->length) playing_ = nullptr;
  }

 private:
  static constexpr uint32_t GIVE_UP_MS = 1000;
  esphome::speaker::Speaker *speaker_{};
  const Sound *playing_{};
  size_t played_{0};
  uint32_t since_{0};
};

}  // namespace tessera
