#pragma once
// The vacuum card of the module (the module vacuum_card, tier full): what it knows beyond the robot's own state, and the
// decisions it makes that need no LVGL. Pure, for tests/test_vacuum_model.cpp.
//
// The add-on sends the block (screen_manager/app/vacuum_card.py) to a screen whose hello says vacuum_card:
//   map     the robot's map on its device (an image or camera entity) and its mark, which changes with the picture;
//   rooms   the areas someone linked to the robot's segments in Home Assistant, each with its icon and floor, in Home
//           Assistant's order; `vacuum.clean_area` cleans them; `floors` names the floors when there is more than one;
//   unmapped the robot cleans by area, but no area is linked yet (Home Assistant's own empty state);
//   rt      the routines: buttons on the robot's device that run something;
//   err     why it stopped, in Home Assistant's words; pg and ar how far it is and the floor it did, while it cleans.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>
#include "tile_catalogue.h"

namespace vacuum_model {

constexpr size_t MAX_ROOMS = 24, MAX_FLOORS = 6, MAX_ROUTINES = 24;

struct Room {
  std::string area, name;
  uint32_t icon = 0;   // the area's icon as a codepoint, 0 for none (the card draws Home Assistant's area icon then)
  uint8_t floor = 0;   // index into Data::floors
};
struct Routine { std::string entity, name; };
struct Data {
  std::string map_entity, map_mark;
  std::vector<Room> rooms;
  std::vector<std::string> floors;
  bool unmapped = false;
  std::vector<Routine> routines;
  std::string error;
  int progress = -1;       // 0-100 while cleaning, -1 unknown
  float area = NAN;        // m² this run
  bool has_map() const { return !map_entity.empty() && !map_mark.empty(); }
  // The card offers cleaning per room: rooms to pick, or the empty state that says how to link them.
  bool by_room() const { return !rooms.empty() || unmapped; }
};

// ---- What the robot can do (VacuumEntityFeature), as Home Assistant's more-info dialog reads it ----
// A robot that reports no features (unavailable, an older app) keeps the keys it may have: Start, Pause and Dock.
struct Can { bool start, pause, stop, dock, locate, by_area; };
inline Can can(uint32_t supported) {
  namespace f = tile_catalogue::vacuum;
  if (!supported) return {true, true, false, true, false, false};
  return {(supported & (f::START | f::PAUSE)) != 0, (supported & f::PAUSE) != 0, (supported & f::STOP) != 0,
          (supported & f::RETURN_HOME) != 0, (supported & f::LOCATE) != 0, (supported & f::CLEAN_AREA) != 0};
}

// The two keys under the robot, as Home Assistant's dialog offers them. The first follows what it does: Pause while it
// cleans and can pause, else Stop, else Dock (a robot with neither, such as SwitchBot's, ends a run by going home);
// Resume while paused; Start otherwise. The second is Dock; Stop where it cannot go home (Miele) while it runs, and while
// it is on its way home Stop, or nothing (Dock is what it does already).
enum class Key : uint8_t { NONE, START, RESUME, PAUSE, STOP, DOCK };
inline Key first_key(const std::string &state, const Can &c) {
  if (state == "cleaning") return c.pause ? Key::PAUSE : c.stop ? Key::STOP : c.dock ? Key::DOCK : Key::NONE;
  if (state == "paused") return Key::RESUME;
  return c.start ? Key::START : c.dock ? Key::DOCK : Key::NONE;
}
inline Key second_key(const std::string &state, const Can &c) {
  const Key first = first_key(state, c);
  if (state == "returning") return c.stop ? Key::STOP : Key::NONE;
  if (c.dock && first != Key::DOCK) return Key::DOCK;
  if (!c.dock && c.stop && first != Key::STOP && (state == "cleaning" || state == "paused")) return Key::STOP;
  return Key::NONE;
}
// The action of a key, Home Assistant's.
inline const char *service(Key k) {
  switch (k) {
    case Key::START: case Key::RESUME: return "vacuum.start";
    case Key::PAUSE: return "vacuum.pause";
    case Key::STOP: return "vacuum.stop";
    case Key::DOCK: return "vacuum.return_to_base";
    default: return "";
  }
}

// ---- The rooms someone picks, in the order they tapped them (Home Assistant cleans them in that order where the
// robot can; its own view says the order may not be kept) ----
// A tap on a picked room takes it out; the others keep their order.
inline void toggle(std::vector<uint8_t> &picked, uint8_t room) {
  auto at = std::find(picked.begin(), picked.end(), room);
  if (at != picked.end()) picked.erase(at);
  else if (picked.size() < MAX_ROOMS) picked.push_back(room);
}
// A room's place in the order, 1 for the first; 0 while not picked.
inline int place(const std::vector<uint8_t> &picked, uint8_t room) {
  auto at = std::find(picked.begin(), picked.end(), room);
  return at == picked.end() ? 0 : static_cast<int>(at - picked.begin()) + 1;
}
// Picks that still name a room after the rooms changed (a room unlinked, another map): the rest go.
inline void keep_valid(std::vector<uint8_t> &picked, size_t rooms) {
  picked.erase(std::remove_if(picked.begin(), picked.end(), [&](uint8_t r) { return r >= rooms; }), picked.end());
}
// The value of vacuum.clean_area's cleaning_area_id, which Home Assistant renders from a template into a list:
// "{{ ['kitchen', 'living_room'] }}". Area ids are Home Assistant's slugs; anything else is left out.
inline bool area_id(const std::string &id) {
  if (id.empty() || id.size() > 40) return false;
  for (char c : id) if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
  return true;
}
inline std::string areas_template(const Data &d, const std::vector<uint8_t> &picked) {
  std::string out = "{{ [";
  bool first = true;
  for (uint8_t r : picked) {
    if (r >= d.rooms.size() || !area_id(d.rooms[r].area)) continue;
    out += (first ? "'" : ", '") + d.rooms[r].area + "'";
    first = false;
  }
  return first ? std::string() : out + "] }}";
}

// ---- The rooms page: one floor at a time, pages only when they don't all fit ----
// The rooms of `floor`, in their order (indexes into Data::rooms).
inline std::vector<uint8_t> on_floor(const Data &d, int floor) {
  std::vector<uint8_t> out;
  for (size_t i = 0; i < d.rooms.size(); ++i) if (d.floors.size() < 2 || d.rooms[i].floor == floor) out.push_back(static_cast<uint8_t>(i));
  return out;
}
inline int pages(int count, int per_page) { return per_page <= 0 || count <= 0 ? 1 : (count + per_page - 1) / per_page; }
// Columns for `count` tiles where at most `fit` stand side by side: even rows (four as two and two, never three and one).
inline int even_columns(int count, int fit) {
  if (count <= 0 || fit <= 0) return 1;
  int cols = std::min(count, fit);
  const int rows = (count + cols - 1) / cols;
  return (count + rows - 1) / rows;
}

}  // namespace vacuum_model
