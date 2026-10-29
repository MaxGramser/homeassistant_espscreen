#pragma once
// The screen's moments as lists (docs/PROFILES.md, "Hooks"): what a feature of the board (the camera) or a plugin wants
// to do at a moment of the core, added to a list instead of written into a substitution of packages/core.yaml. A
// substitution holds one piece of code, so a second feature that set it would silently replace the first; a list adds
// up. A feature adds its own at boot (features/camera.yaml), a plugin through plugin_host.cpp.
//
// The choices of the board's hardware (which touch panel, how the backlight dims, what a feature does at boot) stay
// substitutions: exactly one package of a board gives each.
#include <cstdint>
#include <functional>
#include <vector>

namespace screen_hooks {

// Every 250 ms, after runtime_tiles::tick(), with millis().
inline std::vector<std::function<void(uint32_t)>> &tick() {
  static std::vector<std::function<void(uint32_t)>> list;
  return list;
}
// The cards closed (runtime_tiles::dismiss): Back, standby, Back to page 1, another card.
inline std::vector<std::function<void()>> &cards_closed() {
  static std::vector<std::function<void()>> list;
  return list;
}
// Something on the glass that keeps the settings page from opening over it (a camera full screen): any true says so.
inline std::vector<std::function<bool()>> &keeps_settings_closed() {
  static std::vector<std::function<bool()>> list;
  return list;
}
// Something on the glass that counts as away from page 1, so "Back to page 1" closes it in time: any true says so.
inline std::vector<std::function<bool()>> &away() {
  static std::vector<std::function<bool()>> list;
  return list;
}
// An alert is about to show, after the settings page closed and before its card is made.
inline std::vector<std::function<void()>> &alert_show() {
  static std::vector<std::function<void()>> list;
  return list;
}

// Run a list: in screen_hooks.cpp, so the lambdas of packages/core.yaml that call them hold one call each.
void run_tick(uint32_t now_ms);
void run_cards_closed();
bool settings_kept_closed();
bool is_away();
void run_alert_show();

}  // namespace screen_hooks
