#pragma once
#include <cstdint>

namespace voice_wake {
// Coordinates ownership only. ESPHome's micro_wake_word performs recognition.
// Starting/stopping the detector is asynchronous; never hand its microphone to
// the network session until both the detector and the audio driver have stopped.
class Gate {
 public:
  enum Action { NONE = 0, START_WAKE = 1, STOP_WAKE = 2, START_VOICE = 4, FAILED = 8 };
  void configure(bool enabled, int model) {
    if (enabled_ != enabled || model_ != model) { restart_ = true; failed_ = false; }
    enabled_ = enabled; model_ = model;
  }
  void request(uint32_t now) { pending_ = true; requested_ = now; }
  void cancel() { pending_ = false; restart_ = true; }
  bool pending() const { return pending_; }
  bool ready() const { return state_ == ARMED && !restart_ && !pending_; }
  bool failed() const { return failed_; }

  int step(uint32_t now, bool detector_running, bool mic_stopped,
           bool speaker_stopped, bool voice_active, bool muted) {
    int action = NONE;
    if (muted) pending_ = false;
    if (pending_ && now - requested_ >= 5000) {
      pending_ = false; failed_ = true; action |= FAILED;
    }
    const bool stop = pending_ || voice_active || muted || !enabled_ || restart_ || failed_;
    if (state_ == STARTING) {
      if (detector_running) state_ = ARMED;
      else if (now - since_ >= 3000) {
        failed_ = true; pending_ = false; action |= FAILED;
        state_ = STOPPING;
      }
      // ESPHome start() queues a request before is_running() becomes true.
      // Keep ownership until that request has started or timed out, even if
      // the user disables wake detection in this small window.
      if (stop) action |= STOP_WAKE;
    }
    if (state_ == ARMED) {
      if (stop) state_ = STOPPING;
      else if (!detector_running) {
        failed_ = true; state_ = STOPPING; action |= FAILED;
      }
    }
    if (state_ == STOPPING) {
      action |= STOP_WAKE;
      if (!detector_running && mic_stopped) { state_ = QUIET; since_ = now; }
      return action;
    }
    if (state_ != QUIET) return action;
    if (voice_active || muted || !mic_stopped || !speaker_stopped) {
      since_ = now;
      return action;
    }
    if (pending_) {
      pending_ = false; restart_ = false; since_ = now;
      return action | START_VOICE;
    }
    // Cool down before arming detection after a reply, never after a wake:
    // the caller is already speaking when recognition transfers the microphone.
    if (now - since_ < 1000) return action;
    restart_ = false;
    if (enabled_ && !failed_) {
      state_ = STARTING; since_ = now;
      action |= START_WAKE;
    }
    return action;
  }

 private:
  enum State { QUIET, STARTING, ARMED, STOPPING } state_{QUIET};
  bool enabled_{false}, pending_{false}, restart_{false}, failed_{false};
  int model_{0};
  uint32_t since_{0}, requested_{0};
};
}  // namespace voice_wake
