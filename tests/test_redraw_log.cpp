// The reasons render() logs when it draws every card (components/smart_display/redraw_log.h).
#include <cassert>
#include <cstring>
#include <iostream>
#include <string_view>

#include "components/smart_display/redraw_log.h"

using redraw_log::TileWhy;
using redraw_log::Why;

int main() {
  // Every reason has words of its own, and none is empty.
  for (size_t i = 0; i < static_cast<size_t>(Why::count); ++i) {
    const char *a = redraw_log::words(static_cast<Why>(i));
    assert(a && *a);
    for (size_t j = 0; j < i; ++j) assert(std::strcmp(a, redraw_log::words(static_cast<Why>(j))) != 0);
  }
  // The log reads as it did before the reasons had a home of their own (the render log since a2e6d57e).
  static_assert(std::string_view(redraw_log::words(Why::new_layout)) == "a new layout");
  assert(std::strcmp(redraw_log::words(Why::feed_no_longer_fresh), "feed no longer fresh") == 0);
  assert(std::strcmp(redraw_log::words(Why::update_status_gone), "an update's status gone") == 0);
  // A value outside the list says "unnamed" instead of reading past the table.
  assert(std::strcmp(redraw_log::words(static_cast<Why>(200)), "unnamed") == 0);
  // Why one card was marked (render()'s slow-pass line): every reason has words of its own, none empty, and a value
  // outside the list says "unnamed".
  for (size_t i = 0; i < static_cast<size_t>(TileWhy::count); ++i) {
    const char *a = redraw_log::words(static_cast<TileWhy>(i));
    assert(a && *a);
    for (size_t j = 0; j < i; ++j) assert(std::strcmp(a, redraw_log::words(static_cast<TileWhy>(j))) != 0);
  }
  static_assert(std::string_view(redraw_log::words(TileWhy::state)) == "a state");
  assert(std::strcmp(redraw_log::words(static_cast<TileWhy>(200)), "unnamed") == 0);
  static_assert(std::string_view(redraw_log::NO_STEP) == "no step");
  std::cout << "redraw log: " << static_cast<int>(Why::count) << " reasons, each with words of its own\n";
}
