#pragma once
// A plugin's sounds (plugin API 0.8, docs/FIRMWARE_API.md in the plugins repository, "Sounds"): the samples of a WAV
// file in flash, which smart_display.sound() builds in from the plugin's folder, played on the screen's speaker
// (ts_speaker, the feature speaker) one at a time. Only a plugin that needs the speaker includes this.
#include <algorithm>
#include <cstddef>
#include <cstdint>

#include "esphome/core/defines.h"
// ESPHome's esphome.h includes every header of smart_display, also on a board without a speaker: there this is empty.
#ifdef USE_SPEAKER
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
// add() (plugin API 0.11) plays a sound after the ones handed to it before, each followed by silence until `span_ms`
// after its start: the speaker then spaces a run of clicks evenly by itself, however late the screen's loop comes round
// while it draws. At most QUEUE wait; more are left out, so a run never trails behind the finger.
class SoundPlayer {
 public:
  static constexpr uint8_t QUEUE = 2;
  void set_speaker(esphome::speaker::Speaker *speaker) { speaker_ = speaker; }
  void play(const Sound &sound) {
    waiting_ = 0;
    start(sound, 0);
  }
  void add(const Sound &sound, uint32_t span_ms) {
    if (speaker_ == nullptr || sound.length == 0) return;
    if (playing_ == nullptr) {
      start(sound, span_ms);
      return;
    }
    if (waiting_ < QUEUE) queue_[(first_ + waiting_++) % QUEUE] = {&sound, span_ms};
  }
  void stop() {
    playing_ = nullptr;
    waiting_ = 0;
  }
  bool playing() const { return playing_ != nullptr; }
  bool playing(const Sound &sound) const { return playing_ == &sound; }
  void loop() {
    if (playing_ == nullptr || speaker_ == nullptr) return;
    const uint32_t now = esphome::millis();
    for (;;) {
      size_t taken;
      if (played_ < playing_->length) {
        taken = speaker_->play(playing_->data + played_, playing_->length - played_, 0);
        played_ += taken;
      } else {
        // The silence after the sound, in the sound's own format, from a block of zeros.
        static const uint8_t ZEROS[512] = {};
        taken = speaker_->play(ZEROS, std::min(sizeof ZEROS, silence_), 0);
        silence_ -= std::min(taken, silence_);
      }
      if (taken == 0) {
        if (now - since_ > GIVE_UP_MS) stop();
        return;
      }
      since_ = now;
      if (played_ < playing_->length || silence_ > 0) continue;
      if (waiting_ == 0) {
        playing_ = nullptr;
        return;
      }
      const auto next = queue_[first_];
      first_ = (first_ + 1) % QUEUE;
      --waiting_;
      start(*next.sound, next.span_ms);
    }
  }

 private:
  static constexpr uint32_t GIVE_UP_MS = 1000;
  void start(const Sound &sound, uint32_t span_ms) {
    if (speaker_ == nullptr || sound.length == 0) return;
    speaker_->set_audio_stream_info(esphome::audio::AudioStreamInfo(16, sound.channels, sound.rate));
    playing_ = &sound;
    played_ = 0;
    const size_t frame = 2u * sound.channels, span = static_cast<size_t>(span_ms) * sound.rate / 1000 * frame;
    silence_ = span > sound.length ? span - sound.length : 0;
    silence_ -= silence_ % frame;
    since_ = esphome::millis();
  }
  struct Waiting {
    const Sound *sound;
    uint32_t span_ms;
  };
  esphome::speaker::Speaker *speaker_{};
  const Sound *playing_{};
  size_t played_{0}, silence_{0};
  uint32_t since_{0};
  Waiting queue_[QUEUE]{};
  uint8_t first_{0}, waiting_{0};
};

}  // namespace tessera

#endif  // USE_SPEAKER
