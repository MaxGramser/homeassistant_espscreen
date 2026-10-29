#pragma once
// The screen's governor (docs/PLATFORM_PLAN.md 4.10): what a busy screen gives up first, so the glass and the voice
// never do. Pure logic, free of LVGL and ESP-IDF, so tests/test_pressure.cpp checks it on a PC. Its whole API: on the
// main loop Governor::signal (a sign of trouble), touching (the finger) and tick (runtime_tiles.h pressure_tick, which
// also sets the shared levels); on any task level_of(Work), which live_view.cpp and the plugins (plugin API 0.21,
// tessera::squeeze) act on. STEPS and FLOOR below are the one place the order and the steps are written.
//
// The work of a screen in a fixed order, from what must never wait to what waits first: the glass, the voice
// assistant, a doorbell's ring, the live tiles, the screen's own camera (its video), its sensing (light level and
// motion) and the background (pictures fetched ahead for pages out of sight). Each work has a level: 0 runs as it is,
// 1 does half of it, 2 a quarter: half or a quarter of the pictures a second for a live tile, which pauses between them
// (live_view.cpp, pace), of the frames for the camera's video, of the samples for sensing. The glass, the voice and the
// doorbell are never squeezed.
//
// What squeezes, from the bottom of the order up (STEPS), one step for each sign of trouble: the panel ran dry (a
// glass miss), the main loop held up (ESPHome's "took a long time" for a component), the wake word's ring buffer
// reset (its inference fell behind). A sign within SIGNAL_WINDOW_MS of the last one climbs a step, once in
// ESCALATE_GAP_MS at most (a burst of twenty resets in half a second is one sign); every REST_MS without a sign the
// screen steps back down one, the highest work first. A sign of a work above the live tiles takes them at once: the
// wake word falling behind climbs straight to the step that squeezes the tiles (FLOOR), as its resets came seconds or
// a minute apart on a reTerminal D1001 and the slow climb then never reached them (2026-10-28). Measured on a reTerminal D1001 (2026-10-28): slider drags in a
// light's card with four live tiles and the camera's video brought 27 wake word resets and a frame of the panel run dry,
// and none of that without the tiles.
//
// And before any sign: while a finger is on the glass, the camera, sensing and the background step down one; once it
// drags or a page moves, the live tiles too. A second after it lets go, all back at once.
#include <atomic>
#include <cstdint>

namespace pressure {

enum Work : uint8_t { GLASS, VOICE, DOORBELL, LIVE_TILES, OWN_CAMERA, SENSING, BACKGROUND, WORKS };
enum Sign : uint8_t { GLASS_MISS, SLOW_LOOP, WAKE_WORD_RESET, SIGNS };

constexpr uint8_t MOST = 3;  // steps of pressure
// How many live tiles run on the glass now (live_view counts its tile streams): the heard rule needs two or more.
inline std::atomic<uint8_t> live_tiles{0};
// Each step's levels, by Work. The order of the table is the order of what gives up.
constexpr uint8_t STEPS[MOST + 1][WORKS] = {
    // GLASS VOICE DOORBELL LIVE_TILES OWN_CAMERA SENSING BACKGROUND
    {0, 0, 0, 0, 0, 0, 0},
    {0, 0, 0, 0, 1, 1, 1},
    {0, 0, 0, 1, 2, 1, 1},
    {0, 0, 0, 2, 2, 1, 1},
};
constexpr uint32_t SIGNAL_WINDOW_MS = 20000, REST_MS = 10000, ESCALATE_GAP_MS = 2000, LET_GO_MS = 1000;
// The least step each sign brings, by Sign: the wake word's reset at once to the step that squeezes the live tiles.
constexpr uint8_t FLOOR[SIGNS] = {0, 0, 2};

inline const char *sign_name(Sign s) {
  return s == GLASS_MISS ? "the panel ran dry" : s == SLOW_LOOP ? "the main loop held up" : "the wake word fell behind";
}

class Governor {
 public:
  // A sign of trouble at `now` (ms).
  void signal(Sign s, uint32_t now) {
    signs_[s]++;
    if (step_ < FLOOR[s]) {
      step_ = FLOOR[s];
      cause_ = s;
      last_sign_ = climbed_ = changed_ = stamp(now);
      return;
    }
    if (step_ > 0 && now - climbed_ < ESCALATE_GAP_MS) {
      last_sign_ = stamp(now);
      return;  // the same burst
    }
    if (step_ == 0 || now - last_sign_ <= SIGNAL_WINDOW_MS) {
      if (step_ < MOST) step_++;
    }
    cause_ = s;
    last_sign_ = climbed_ = changed_ = stamp(now);
  }
  // Someone hears the screen's microphone (plugin API 0.23, capturing(SOUND): its camera watched with its sound, a
  // call): a conversation, which goes before the live tiles on the sending side too. The tiles stay at a quarter while
  // it lasts, whatever the steps say; the camera, sensing and the background follow the steps as before. On a
  // reTerminal D1001 four live tiles beside its own video stalled its Wi-Fi uplink and the sound reached the viewer in
  // bursts a second late, 2.4 s at most (2026-10-29, docs/PLATFORM_PLAN.md 5.1).
  void heard(bool on) { heard_ = on; }
  bool heard() const { return heard_; }
  // The finger: on the glass, and whether it drags (past the tap's limit) or a page moves.
  void touching(bool down, bool dragging, uint32_t now) {
    if (down) {
      down_ = true;
      dragging_ = dragging_ || dragging;
      return;
    }
    if (down_) let_go_ = stamp(now);
    down_ = false;
  }
  // Four times a second: a step back down after REST_MS without a sign, one at a time; and the finger's hold ends.
  void tick(uint32_t now) {
    if (step_ > 0 && now - last_sign_ >= REST_MS && now - changed_ >= REST_MS) {
      step_--;
      changed_ = stamp(now);
    }
    if (!down_ && let_go_ && now - let_go_ >= LET_GO_MS) {
      let_go_ = 0;
      dragging_ = false;
    }
  }
  uint8_t level(Work w) const {
    uint8_t touch = 0;
    if (down_ || let_go_) {
      if (w == OWN_CAMERA || w == SENSING || w == BACKGROUND) touch = 1;
      if (w == LIVE_TILES && dragging_) touch = 1;
    }
    // While someone hears the microphone (a camera opened full screen with sound on another screen, a conversation),
    // the screen's own camera is the conversation: its frames go whole, whatever the step or a finger (2026-10-29, Max
    // and a Guition 10.1 watching a reTerminal D1001 full screen: each tap and each slow loop halved his picture there).
    if (w == OWN_CAMERA && heard_) return 0;
    const uint8_t stepped = STEPS[step_][w];
    // The live tiles give way while someone hears the microphone only when there are two or more of them: one tile
    // crowds nothing, and Max saw it squeezed for no reason (a reTerminal D1001 with one live tile, 2026-10-29).
    const uint8_t least = w == LIVE_TILES && heard_ && live_tiles.load(std::memory_order_relaxed) >= 2 ? MOST - 1 : 0;
    const uint8_t level = stepped > touch ? stepped : touch;
    return level > least ? level : least;
  }
  uint8_t step() const { return step_; }
  Sign cause() const { return cause_; }
  bool touched() const { return down_ || let_go_; }
  uint32_t signs(Sign s) const { return signs_[s]; }

 private:
  static uint32_t stamp(uint32_t now) { return now ? now : 1; }
  uint8_t step_ = 0;
  Sign cause_ = GLASS_MISS;
  uint32_t last_sign_ = 0, climbed_ = 0, changed_ = 0, let_go_ = 0;
  bool down_ = false, dragging_ = false, heard_ = false;
  uint32_t signs_[SIGNS] = {};
};

// The levels as the main loop set them last, for every task: live_view's streams, a plugin on the camera's task
// (tessera::squeeze). The main loop's governor is runtime_tiles::governor.
inline std::atomic<uint8_t> shared[WORKS];
inline uint8_t level_of(Work w) { return w < WORKS ? shared[w].load(std::memory_order_relaxed) : 0; }

}  // namespace pressure
