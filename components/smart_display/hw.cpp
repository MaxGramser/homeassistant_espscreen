// The capability record (hw.h): the build's defines and the boot's findings resolved once, and written into the hello.
#include "hw.h"
#include "esphome/core/defines.h"
#include "hw_hello.h"
#include "live_view.h"
#ifdef SD_MOD_TEXT_CARD
#include "module_text_card.h"
#endif
#ifdef USE_ESP32
#include <esp_heap_caps.h>
#endif

namespace hw {

namespace {

Facts facts() {
  Facts f;
#ifdef HW_SPEAKER
  f.speaker = true;
#endif
#ifdef HW_MICROPHONE
  f.microphone = true;
#endif
#ifdef HW_ECHO_CANCEL
  f.echo_cancel = true;
#endif
#ifdef HW_CAMERA
  f.camera = true;
#endif
  f.live_video = live_view::available();
  f.live_tiles = picture_engine::limits().live_tiles;
#ifdef USE_ESP32
  f.psram_bytes = static_cast<uint32_t>(heap_caps_get_total_size(MALLOC_CAP_SPIRAM));
  f.internal_bytes = static_cast<uint32_t>(heap_caps_get_total_size(MALLOC_CAP_INTERNAL));
#endif
  return f;
}

}  // namespace

const Caps &caps() {
  static const Caps resolved = resolve(facts());
  return resolved;
}

void hello(JsonObject root) {
  const Caps &c = caps();
  auto caps = root["caps"].to<JsonObject>();
  caps["live"] = c.live_video;
  caps["speaker"] = c.speaker;
  caps["microphone"] = c.microphone;
  caps["echo_cancel"] = c.echo_cancel;
  caps["camera"] = c.camera;
  // A plugin hands this screen's own camera to a live tile of its own (plugin API 0.22): the app answers such a tile
  // "own:" (live_view.h is_own) instead of a link.
  caps["own_camera"] = live_view::own_offered();
  // On a turned glass the app may send its live pictures turned as it is (X-Turn): the screen copies them onto the glass
  // straight, and its PPA turns nothing per picture (live_view.cpp, show). LVGL's turn as the hello leaves.
  if (c.live_video && glass::turn() != 0) caps["picture_turn"] = glass::turn();
  caps["live_tiles"] = c.live_tiles;
  caps["psram_kb"] = c.psram_bytes / 1024;
  caps["internal_kb"] = c.internal_bytes / 1024;
#ifdef SD_MOD_TEXT_CARD
  // The template tiles this screen takes (module text_card): how many at once, and the bytes of rows each keeps.
  caps["text_tiles"] = text_card::MAX_TILES;
  caps["text_bytes"] = text_card::MAX_BYTES;
#endif
}

}  // namespace hw
