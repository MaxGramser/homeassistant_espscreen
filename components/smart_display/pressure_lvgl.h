// The governor: what a busy screen gives up first.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in pressure.h.
// What proves it: tests/test_pressure.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- The governor (pressure.h, docs/PLATFORM_PLAN.md 4.10): what a busy screen gives up first ----
inline pressure::Governor governor;
// Signs that come from the log, on whichever task wrote the line (ESPHome hands every line at the screen's level, a
// warning with Debug mode off too, to its listeners): only counted there, and turned into signs on the main loop.
inline std::atomic<uint32_t> wake_word_resets{0}, loop_holds{0};
inline uint32_t wake_word_seen = 0, loop_holds_seen = 0, glass_misses_seen = 0;
// What the governor does, in words, for the "Pressure" sensor (core.yaml) and the log, once at every change.
inline std::function<void(const std::string &)> pressure_told;
inline std::string pressure_said;

// One line of the log, on any task: micro_wake_word's "Not enough free bytes in ring buffer ... Resetting" (its
// inference fell behind) and ESPHome's "<component> took a long time for an operation" (the main loop held up).
inline void pressure_log(void *, uint8_t level, const char *tag, const char *line, size_t length) {
  glass::note_log_line();  // every line written, for the panel watch (glass.h)
  if (level > ESPHOME_LOG_LEVEL_WARN || tag == nullptr || line == nullptr) return;
  const std::string_view text(line, length);
  if (strcmp(tag, "micro_wake_word") == 0 && text.find("ring buffer") != std::string_view::npos)
    wake_word_resets.fetch_add(1, std::memory_order_relaxed);
  else if (strcmp(tag, "component") == 0 && text.find("took a long time") != std::string_view::npos)
    loop_holds.fetch_add(1, std::memory_order_relaxed);
}

// The log's lines to pressure_log, through ESPHome's log listeners (the API's subscriptions use them too, so every
// screen has them).
inline void pressure_listen() {
#if defined(USE_LOGGER) && defined(USE_LOG_LISTENERS) && !defined(ESP_SCREEN_HOST)
#ifdef USE_API
  // The API's slot and the governor's (smart_display/__init__.py asks for it): with fewer, ESPHome would drop this
  // listener without a word, and the governor would see no wake word and no held-up loop (2026-10-28, a D1001).
  static_assert(ESPHOME_LOG_MAX_LISTENERS >= 2, "the governor's log listener has no slot (logger.request_log_listener)");
#endif
  if (esphome::logger::global_logger != nullptr) esphome::logger::global_logger->add_log_callback(nullptr, pressure_log);
#else
  ESP_LOGW("pressure", "no log listeners in this build: the governor sees no wake word and no held-up loop");
#endif
}

// The finger, from the touch panel's own path (touch_input) and the bench's: down, and whether it drags.
inline void pressure_finger(bool down, bool dragging) { governor.touching(down, dragging, esphome::millis()); }

inline std::string pressure_text() {
  using namespace pressure;
  if (governor.step() == 0 && !governor.touched() && !governor.heard()) return "normal";
  static const char *const NAMES[WORKS] = {"glass", "voice", "doorbell", "live tiles", "own camera", "sensing", "background"};
  std::string text;
  for (int w = LIVE_TILES; w < WORKS; ++w) {
    const uint8_t l = governor.level(static_cast<Work>(w));
    if (!l) continue;
    if (!text.empty()) text += ", ";
    text += NAMES[w];
    text += l == 1 ? " 1/2" : " 1/4";
  }
  if (text.empty()) return "normal";
  text += governor.step() ? std::string(" (") + sign_name(governor.cause()) + ")"
          : governor.touched() ? std::string(" (a finger)") : std::string(" (someone hears the microphone)");
  return text;
}

// Four times a second, on the main loop: new signs from the panel and the log, the rest, the finger's drag, and the
// levels for every task.
inline void pressure_tick(uint32_t now) {
  const uint32_t misses = glass::misses();
  if (misses != glass_misses_seen) { glass_misses_seen = misses; governor.signal(pressure::GLASS_MISS, now); }
  const uint32_t resets = wake_word_resets.load(std::memory_order_relaxed);
  if (resets != wake_word_seen) { wake_word_seen = resets; governor.signal(pressure::WAKE_WORD_RESET, now); }
  const uint32_t holds = loop_holds.load(std::memory_order_relaxed);
  if (holds != loop_holds_seen) { loop_holds_seen = holds; governor.signal(pressure::SLOW_LOOP, now); }
  // A slider held is a drag, whichever finger holds it (the touch panel's, or the bench's own pointer).
  if (captured_slider) governor.touching(true, true, now);
  governor.tick(now);
  glass::note_finger(governor.touched());
  for (int w = 0; w < pressure::WORKS; ++w)
    pressure::shared[w].store(governor.level(static_cast<pressure::Work>(w)), std::memory_order_relaxed);
  const std::string text = pressure_text();
  if (text != pressure_said) {
    pressure_said = text;
    ESP_LOGW("pressure", "%s", text.c_str());
    if (pressure_told) pressure_told(text);
  }
}

// The board's interval (250 ms): the store lets go of what no card draws, every picture says what it wants and the
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
