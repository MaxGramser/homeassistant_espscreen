// A sound file of the app kept by its name, and the sound that plays once (kept_sound.h says why and what).
#include "kept_sound.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "file_fetch.h"
#ifdef USE_SPEAKER
#include "roomy.h"
#include "wav.h"
#endif

namespace kept_sound {

#ifdef USE_SPEAKER
static const char *const TAG = "sound";

void Kept::want(const std::string &link, std::function<void()> before_swap) {
  const std::string name = file_fetch::name_of(link);
  if (name.empty() || name == name_ || name == wanted_) return;
  wanted_ = name;
  asked_ = esphome::millis();
  const bool asked = file_fetch::get(link, MOST, [this, name, before_swap](bool ok, uint8_t *data, size_t size) {
    if (wanted_ == name) wanted_.clear();
    if (!ok) { ESP_LOGW(TAG, "%s %s did not come", what_, name.c_str()); return; }
    const wav::Sound w = wav::read(data, size);
    if (!w.ok || w.bits != 16 || w.channels > 2 || w.rate < 8000 || w.rate > 48000) {
      ESP_LOGW(TAG, "%s %s is no 16-bit sound", what_, name.c_str());
      roomy::release(data);
      return;
    }
    if (before_swap) before_swap();
    if (file_) roomy::release(file_);
    file_ = data;
    sound_.data = data + w.offset;
    sound_.length = w.size;
    sound_.rate = w.rate;
    sound_.channels = static_cast<uint8_t>(w.channels);
    name_ = name;
    ESP_LOGI(TAG, "%s %s: %u ms", what_, name.c_str(), (unsigned) (w.size * 1000 / (2u * w.channels * w.rate)));
  });
  if (!asked) wanted_.clear();
}

bool Kept::has(const std::string &link) const {
  const std::string name = file_fetch::name_of(link);
  return !name.empty() && name == name_;
}

bool Kept::waiting(uint32_t now) const { return !wanted_.empty() && now - asked_ < WAIT_MS; }

// ---- the sound that belongs to no module ----
static tessera::SoundPlayer player;
static Kept once("alert sound");
static std::string pending;  // the link that plays as soon as its file is here

void bind_speaker(esphome::speaker::Speaker *speaker) { player.set_speaker(speaker); }

void play(const std::string &link) {
  if (silent(link) || file_fetch::name_of(link).empty()) return;
  once.want(link, []() { player.stop(); });
  pending = link;
  loop();
}

void stop() {
  pending.clear();
  player.stop();
}

void loop() {
  if (!pending.empty()) {
    if (once.has(pending)) {
      player.play(once.sound());
      pending.clear();
    } else if (!once.waiting(esphome::millis())) {
      pending.clear();  // it did not come: an alert shows without its sound
    }
  }
  player.loop();
}
#else
void loop() {}
#endif

}  // namespace kept_sound
