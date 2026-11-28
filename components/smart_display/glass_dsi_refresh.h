// An ESP32-P4's MIPI-DSI panel with a DMA that repeats the frame buffer by itself (docs/CAMERA.md, "A frame's restart").
// Knows the panel's DMA channel and how to change it; knows nothing of what the glass shows or counts. No host test can
// reach it: the proof is the bench, with a camera on the glass (docs/CAMERA.md). Whoever initialises the panel again
// (esp_lcd_panel_init restarts the channel its own way) must call hold_refresh again.
#pragma once

#include <cstddef>

namespace glass {

using FrameSeen = void (*)();

// Puts the panel's DMA in the hardware's auto-reload, once, at the end of a frame. True when the DMA now repeats the
// frame by itself: from then on `frame_seen` is called for each frame from a timer, because the interrupt that told of a
// frame is gone. False when it keeps ESP-IDF's restart (the reason is in the log), which is also what a build without
// this does. Only with a living panel: the channel it knows is the one ESP-IDF made for it.
bool hold_refresh(void *frame_buffer, size_t bytes, FrameSeen frame_seen);

}  // namespace glass
