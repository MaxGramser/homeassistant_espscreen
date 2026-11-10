#pragma once
// What this screen's hardware can do, in one record (docs/PLATFORM_PLAN.md, section 3.3): whether it streams a camera
// live, has a speaker, a microphone, echo cancellation and a camera of its own, how many live camera tiles it runs at
// once, and how much memory it has. The firmware, the hello to the app, the editor and the plugins all read this one
// record, so no code anywhere infers a capability from a board's name, a chip or a pin.
//
// Two halves make it. The build's half comes from what the configuration contains (hw_build.py reads the config and
// defines HW_SPEAKER, HW_MICROPHONE, HW_ECHO_CANCEL and HW_CAMERA when a component of that kind is built in: a part
// file (packages/hardware/parts/) brings the component, the board only names the part). The boot's half is what only
// the running screen knows: whether its panel and picture engine stream (live_view::available) and how much memory
// the chip and the PSRAM hold. resolve() puts them together and is pure, so tests/test_hw.cpp checks it on a PC.
#include <cstdint>

namespace hw {

// How many live camera tiles a screen runs at once is its picture engine's (picture_engine::limits, docs/PLATFORM_PLAN.md
// section 4.1): four on every P4 board, so a user reads "4" rather than finding out which tile stopped, the fifth on a
// page showing its stills. The streams a screen can hold (live_view::MAX_STREAMS) is a ceiling above it: four tiles, the
// full view, a plugin's places.
// The pictures a second a live tile shows at most, every board alike. Ten since 2026-11-09: a reTerminal D1001 with four
// tiles reached 8 at this limit, with no reset of its wake word (6 until then, when 10 a second each cost 51 resets in
// three minutes, 2026-10-28, before the panel's DMA repeated its frame by itself and the guard cut what stalled). Each tile gets
// its share of the engine's budget up to this (picture_engine::tile_pps), a busy screen half or a quarter of that
// (live_view.cpp, pace; the governor, pressure.h).
constexpr uint8_t LIVE_TILE_PPS = 10;
// The pictures a second a live tile of the screen's own camera shows at most. Its frame comes over no network and is not
// decoded; what limits it is the PPA, which takes 50 to 60 ms to bring a frame of 1280 x 720 down to a tile, so a camera
// of 30 frames a second gives it every second one: 15, evenly, on a reTerminal D1001 with nothing else on the page, 8 to 10
// beside three live tiles and a video viewer (2026-11-09, docs/PLATFORM_PLAN.md 4.11).
constexpr uint8_t OWN_TILE_PPS = 15;

struct Caps {
  bool live_video = false;   // streams a camera live on the glass: a P4 with the picture engine and a direct frame buffer
  bool speaker = false;      // plays sound (a speaker component is built in)
  bool microphone = false;   // hears (a microphone component is built in)
  bool echo_cancel = false;  // the microphone's path takes the speaker's sound back out (an echo canceller is built in)
  bool camera = false;       // a camera of the board's own (the esp_video_camera component is built in)
  uint8_t live_tiles = 0;    // live camera tiles at once: the engine's with live video, 0 without
  // Motion (screen_motion.h, docs/MOTION.md): dims laid on the glass itself, a card before its dim, a change of the whole glass
  // behind the backlight. A full-tier screen whose frame buffer a task may write; never a lite one (the CYD).
  bool motion = false;
  uint32_t psram_bytes = 0, internal_bytes = 0;  // the heaps as the chip reports them at boot
};

// What the halves hand resolve(): the build's defines, and the boot's findings.
struct Facts {
  bool speaker = false, microphone = false, echo_cancel = false, camera = false;
  bool live_video = false;
  bool direct_glass = false;  // a frame buffer a task may write past LVGL (glass::direct)
  bool full_tier = false;     // the build's tier (modules.py: 8 MB of flash or more)
  uint8_t live_tiles = 0;  // the engine's (picture_engine::limits)
  uint32_t psram_bytes = 0, internal_bytes = 0;
};

constexpr Caps resolve(const Facts &f) {
  Caps c{};
  c.live_video = f.live_video;
  c.speaker = f.speaker;
  c.microphone = f.microphone;
  c.echo_cancel = f.echo_cancel && f.microphone && f.speaker;  // cancelling echo needs both ends
  c.camera = f.camera;
  c.live_tiles = f.live_video ? f.live_tiles : 0;
  c.motion = f.direct_glass && f.full_tier;
  c.psram_bytes = f.psram_bytes;
  c.internal_bytes = f.internal_bytes;
  return c;
}

// The record, resolved once on its first call. Call it after the display exists (the hello, a plugin's setup, the main
// loop); never from a constructor that runs before the glass is bound.
const Caps &caps();

}  // namespace hw
