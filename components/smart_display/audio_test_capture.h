#pragma once
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace audio_test {
// The microphone callback is the sole producer. begin()/discard() are called only
// after the ESPHome microphone has stopped, so its buffer cannot be freed under a callback.
// Audio remains local: stereo S16LE input, primary channel retained as mono S16LE.
class Capture {
 public:
  static constexpr size_t MAX_SAMPLES = 16000 * 5;
  void begin(int16_t *data, size_t capacity = MAX_SAMPLES) {
    data_ = data;
    capacity_ = capacity < MAX_SAMPLES ? capacity : MAX_SAMPLES;
    used_.store(0);
    active_.store(data && capacity_);
  }
  void stop() { active_.store(false); }
  bool active() const { return active_.load(); }
  size_t size() const { return used_.load(); }
  int16_t *data() const { return data_; }
  void push(const uint8_t *bytes, size_t length) {
    if (!active_.load()) return;
    size_t n = used_.load();
    for (size_t i = 0; i + 3 < length && n < capacity_; i += 4)
      data_[n++] = static_cast<int16_t>(uint16_t(bytes[i]) | (uint16_t(bytes[i + 1]) << 8));
    used_.store(n);
    if (n == capacity_) active_.store(false);
  }
  // Does not free memory: the caller uses the same allocator as begin().
  void discard() { begin(nullptr, 0); }

 private:
  int16_t *data_ = nullptr;
  size_t capacity_ = 0;
  std::atomic<size_t> used_{0};
  std::atomic<bool> active_{false};
};
}  // namespace audio_test
