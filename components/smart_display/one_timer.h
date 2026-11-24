#pragma once
// Several waits on one timer. A module keeps the moment of each of its waits here and asks its one timer (a script of
// packages/core.yaml that the latest ask replaces) for the soonest; when the timer fires, reached() says which waits
// are due. The timer may still fire for a wait that stopped: nothing is reached then. Free of ESPHome, and the
// millisecond counter may wrap. screen_standby.h and alert_life.h use it, and their tests run it.
#include <cstdint>

namespace one_timer {

template <int N> class Waits {
 public:
  void set(int which, uint32_t ms, uint32_t now) { moments_[which] = {true, now + ms}; }
  void stop(int which) { moments_[which].set = false; }
  bool waiting(int which) const { return moments_[which].set; }
  // True once, when the wait's moment has come.
  bool reached(int which, uint32_t now) {
    auto &m = moments_[which];
    if (!m.set || static_cast<int32_t>(now - m.at) < 0) return false;
    m.set = false;
    return true;
  }
  // Asks `later` for the soonest wait, when there is one.
  void ask(uint32_t now, void (*later)(uint32_t)) const {
    int32_t soonest = -1;
    for (const auto &m : moments_) {
      if (!m.set) continue;
      const int32_t left = static_cast<int32_t>(m.at - now) > 0 ? static_cast<int32_t>(m.at - now) : 0;
      if (soonest < 0 || left < soonest) soonest = left;
    }
    if (soonest >= 0) later(static_cast<uint32_t>(soonest));
  }

 private:
  struct Moment {
    bool set = false;
    uint32_t at = 0;
  };
  Moment moments_[N];
};

}  // namespace one_timer
