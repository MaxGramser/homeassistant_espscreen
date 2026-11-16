#pragma once
// Why render() draws every card next (runtime_tiles.h, mark_all and refresh_all), and the words its log line gives it:
// "every card drawn: <why>, N cards in X ms". A page that seems to load again is traced to its cause by that line (a
// 10.1 inch, 2026-11-15).
//
// What it knows: the reasons, one name each, and nothing else. What it does not know: LVGL, the model, the glass. Its
// words are log words a developer reads, never shown on a screen, so they stay English and the translations' lint
// skips this file by rule: tools/i18n.py leaves out every *_log.h, and tests/test_log_words.py holds that such a file
// knows nothing that draws or translates. tests/test_redraw_log.cpp proves every reason has its words.
#include <cstddef>
#include <cstdint>

namespace redraw_log {

enum class Why : uint8_t {
  unnamed,             // a caller that gave no reason
  nothing_named,       // a refresh that marked nothing draws everything
  display_setting,     // a display setting: only the look and the time (dirty_time)
  page_placed,
  layout_dropped_for_memory,
  wifi,                // Wi-Fi gone or back
  update_status_gone,  // an update's status cleared from the glass
  look_changed,        // light or dark, or the card look
  feed_fresh_again,
  feed_no_longer_fresh,
  protocol_problem,
  protocol_problem_over,
  layout_refused,
  new_layout,
  layout_complete,
  count,
};

constexpr const char *WORDS[] = {
    "unnamed",
    "a refresh that named nothing",
    "a display setting (dirty_time)",
    "a page placed",
    "the layout dropped for memory",
    "Wi-Fi gone or back",
    "an update's status gone",
    "the look changed",
    "feed fresh again",
    "feed no longer fresh",
    "a protocol problem",
    "a protocol problem over",
    "a layout refused",
    "a new layout",
    "a layout complete",
};
static_assert(sizeof(WORDS) / sizeof(WORDS[0]) == static_cast<size_t>(Why::count), "every reason has its words");

constexpr const char *words(Why why) {
  return static_cast<size_t>(why) < static_cast<size_t>(Why::count) ? WORDS[static_cast<size_t>(why)] : WORDS[0];
}

}  // namespace redraw_log
