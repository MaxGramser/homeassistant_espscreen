#pragma once
// A sound file of ESP Screen Manager, kept by its name, and the screen's sound that plays once (docs/SOUNDS.md).
//
// The app chooses what a screen plays: a call's ringtone (a ring's `rt`, module_call.cpp), a doorbell's chime (a ring's
// `ch`, module_doorbell.cpp) and an alert's tone (the op `sound`). Each message carries the link of a WAV file of the app
// (docs/SCREEN_FILES.md) or `none` for silence. A Kept holds one such file: it downloads what a link names unless it has
// it (file_fetch.h), reads it (wav.h) and keeps it in PSRAM until a link names another, so the next ring plays at once.
// Its owner plays it on its own player; play() here is for a sound that belongs to no module (an alert's tone).
//
// What it does not know: what a sound is for, and when it plays. Without a speaker (USE_SPEAKER) or the download
// (SCREEN_PICTURES) there is nothing here, and each owner plays what it played before files came.
// ESPHome's defines say whether there is a speaker; the editor's preview (web/wasm, ESP_SCREEN_HOST) has none and no
// ESPHome, so it takes the file without them, as it does module_todo.cpp.
#ifndef ESP_SCREEN_HOST
#include "esphome/core/defines.h"
#endif
#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#ifdef USE_SPEAKER
#include "plugin_sound.h"
#endif

namespace kept_sound {

constexpr size_t MOST = 256 * 1024;   // the app sends at most 5 s of 16 kHz mono (160 KB); more is no sound of ours
constexpr uint32_t WAIT_MS = 1500;    // what waits for a file on its way, before it plays without it
// The word for silence: what the app sends when someone chose no sound.
inline bool silent(const std::string &link) { return link == "none"; }

#ifdef USE_SPEAKER
class Kept {
 public:
  explicit Kept(const char *what) : what_(what) {}
  // Asks for the file `link` names, unless it has it or it is on its way. `before_swap` runs before the old bytes go
  // (its owner stops what plays them).
  void want(const std::string &link, std::function<void()> before_swap = nullptr);
  // Whether it holds the file `link` names.
  bool has(const std::string &link) const;
  // Whether the file it was last asked for is still on its way, within WAIT_MS.
  bool waiting(uint32_t now) const;
  const tessera::Sound &sound() const { return sound_; }

 private:
  const char *what_;
  std::string name_, wanted_;
  uint8_t *file_ = nullptr;
  tessera::Sound sound_;
  uint32_t asked_ = 0;
};

// The sound that belongs to no module (an alert's tone): once, as soon as its file is here or within WAIT_MS.
void bind_speaker(esphome::speaker::Speaker *speaker);
void play(const std::string &link);
void stop();
#endif
// Every 50 ms with the downloads (packages/features/camera.yaml): the sound waiting for its file, and the player.
void loop();

}  // namespace kept_sound
