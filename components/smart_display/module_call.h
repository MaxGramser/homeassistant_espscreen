#pragma once
// Calls between screens (module call, tier full; docs/CALLS.md): what runtime_tiles.h and the page receiver reach of it.
// ESP Screens holds every call (calls.py); this module only shows it: the list, a call going out, a call coming in, the
// call itself, and it says what a finger did. A video call shows on the camera full view of runtime_tiles.h (camera_open,
// live_view), with the hooks below, as a ring does; a call without a picture uses the same view with a stream of sound
// alone. The rest is module_call.cpp, a compilation unit of its own.
#include "esphome/core/defines.h"
#ifdef SD_MOD_CALL
#include <cstdint>
#include <functional>
#include <string>
#include "lvgl.h"
#include "live_view.h"

namespace esphome {
namespace speaker {
class Speaker;
}
}  // namespace esphome

namespace runtime_tiles {
namespace call {
// Bound at boot (packages/core.yaml): what a finger did goes to ESP Screens (esphome.screen_call).
extern std::function<void(const std::string &action, const std::string &to, bool video, const std::string &key)> report;
void bind_speaker(esphome::speaker::Speaker *speaker);
// The speaker's own volume: a ring goes to `ring_top` while it rings, and nothing of that reaches the media player, Home Assistant
// or a preference (packages/features/audio-player.yaml).
extern float ring_top;
extern std::function<float()> volume_get;
extern std::function<void(float)> volume_set;
// The switch "Call ringtone": off, a call lights the screen up and shows who calls, without a sound.
extern std::function<bool()> ring_on;

// The op `call` (state out, ring, live, held, end) and the op `contacts`: the list, as a JSON text of rows, in parts
// for a house with many screens (`append` a later part, `more` a part still to come).
void on_call(const std::string &state, const std::string &key, const std::string &name, const std::string &icon, bool video,
             const std::string &link, const std::string &talk, bool peer_camera, const std::string &why);
void on_contacts(const std::string &rows, bool append, bool more);
// The Call tile's tap.
void open_list();
// A Call tile set to one screen: straight to calling it.
void dial(const std::string &to, bool video);
// The bench's stand-ins for a finger (a diagnostic action in a bench's own YAML).
void bench_dial(const std::string &to, bool video);
void bench_answer();
void bench_end();

// The camera view as a call (runtime_tiles.h calls these from the camera's own functions).
bool shown();
bool holds();                                       // keeps the screen from standby
void build(lv_obj_t *root, const std::string &name);
live_view::Rect area();                             // the room of the other's picture
const std::string &link();
void sound_changed();
void closing();
void tick(uint32_t now);
}  // namespace call
}  // namespace runtime_tiles
#endif
