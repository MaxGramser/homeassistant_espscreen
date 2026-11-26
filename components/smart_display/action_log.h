#pragma once
// The line a screen leaves in Home Assistant's logbook for what a finger did on it (docs/ARCHITECTURE.md, "An action's
// line in the logbook"). Home Assistant runs an action that comes from an ESPHome device without a sender: the entity's
// own row names the action's domain and no device. So next to the action the screen calls `logbook.log` on the same
// entity, with a message that names the screen, the page and the tile.
// This file knows when a line is due (repeats on one entity fold into one line) and how its message reads. It knows
// nothing of ESPHome, the model or the texts: runtime_tiles.h hands it the names and sends the call.
// tests/test_action_log.cpp runs it.
#include <array>
#include <cstdint>
#include <string>

namespace action_log {

// A slider's steps, a volume key held down and a remote's keys reach one entity many times in a row: one line says
// that it was operated here, and the entity's own rows say what changed.
constexpr uint32_t FOLD_MS = 5000;

// The entities a line was written for last. Four: a finger works one card at a time, and a group's page a few lamps.
class Recent {
 public:
  // Whether an action on `entity` at `now` gets a line; counts it as written when it does. The millisecond counter
  // may wrap.
  bool due(const std::string &entity, uint32_t now) {
    const uint32_t key = hash(entity);
    Entry *oldest = &entries_[0];
    for (auto &e : entries_) {
      if (e.used && e.key == key) {
        if (now - e.at < FOLD_MS) return false;
        e.at = now;
        return true;
      }
      if (!e.used || (oldest->used && now - e.at > now - oldest->at)) oldest = &e;
    }
    *oldest = {true, key, now};
    return true;
  }

 private:
  struct Entry { bool used = false; uint32_t key = 0, at = 0; };
  static uint32_t hash(const std::string &text) {
    uint32_t h = 2166136261u;
    for (unsigned char c : text) h = (h ^ c) * 16777619u;
    return h;
  }
  std::array<Entry, 4> entries_{};
};

// The message: `with_tile` ("operated on {screen}, page {page}, tile {tile}") when the tile is known, `without_tile`
// ("operated on {screen}, page {page}") otherwise. Home Assistant shows it behind the entity's name, and alone in the
// entity's own logbook, so it names the screen itself and starts without a capital.
// The text is walked once: a name that holds braces of its own is left as it is.
inline std::string message(const std::string &with_tile, const std::string &without_tile, const std::string &screen,
                           const std::string &page, const std::string &tile) {
  const std::string &text = tile.empty() ? without_tile : with_tile;
  std::string out;
  out.reserve(text.size() + screen.size() + page.size() + tile.size());
  for (size_t at = 0; at < text.size();) {
    const std::string *value = nullptr;
    size_t length = 0;
    if (text.compare(at, 8, "{screen}") == 0) { value = &screen; length = 8; }
    else if (text.compare(at, 6, "{page}") == 0) { value = &page; length = 6; }
    else if (text.compare(at, 6, "{tile}") == 0) { value = &tile; length = 6; }
    if (value) { out += *value; at += length; }
    else out += text[at++];
  }
  return out;
}

}  // namespace action_log
