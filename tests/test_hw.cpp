// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_hw.cpp -o /tmp/test_hw && /tmp/test_hw
// The capability record (hw.h): resolve() puts the build's defines and the boot's findings together. Pure, so it runs
// here: live tiles follow live video, echo cancellation needs both a speaker and a microphone, and the memory passes
// through unchanged.
#include "../components/smart_display/hw.h"
#include <cassert>
#include <cstdio>

int main() {
  // A P4 with everything: the Tab5, the reTerminal D1001.
  hw::Facts full;
  full.speaker = full.microphone = full.echo_cancel = full.camera = full.live_video = true;
  full.live_tiles = 4;  // the P4 engine's (picture_engine::limits)
  full.psram_bytes = 32u * 1024 * 1024;
  full.internal_bytes = 768u * 1024;
  constexpr hw::Facts nothing{};
  const hw::Caps a = hw::resolve(full);
  assert(a.live_video && a.speaker && a.microphone && a.echo_cancel && a.camera);
  assert(a.live_tiles == 4);
  // Motion is a full-tier screen with a frame buffer a task may write, and nothing less: never a lite screen (the CYD)
  // whatever its glass, never a full one without the buffer.
  assert(!a.motion);
  hw::Facts moving = full;
  moving.direct_glass = moving.full_tier = true;
  assert(hw::resolve(moving).motion);
  moving.full_tier = false;
  assert(!hw::resolve(moving).motion);
  moving.full_tier = true;
  moving.direct_glass = false;
  assert(!hw::resolve(moving).motion);
  assert(a.psram_bytes == 32u * 1024 * 1024 && a.internal_bytes == 768u * 1024);

  // An S3 board with a speaker and no live video: no live tiles, whatever else it has.
  hw::Facts still = full;
  still.live_video = false;
  const hw::Caps b = hw::resolve(still);
  assert(!b.live_video && b.live_tiles == 0 && b.speaker);

  // An echo canceller without a microphone (a configuration error, or a part that brings the canceller alone) counts
  // for nothing: cancelling echo needs both ends.
  hw::Facts half = full;
  half.microphone = false;
  assert(!hw::resolve(half).echo_cancel && !hw::resolve(half).microphone);
  hw::Facts mute = full;
  mute.speaker = false;
  assert(!hw::resolve(mute).echo_cancel);

  // Nothing at all: the host, the WASM preview, a CYD.
  static_assert(!hw::resolve(nothing).live_video && hw::resolve(nothing).live_tiles == 0, "a bare board streams nothing");

  std::puts("test_hw: ok");
  return 0;
}
