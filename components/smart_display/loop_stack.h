#pragma once
// The loop task's stack (docs/ARCHITECTURE.md, "The loop's stack"): how little of it may be left before the health
// lines say so out loud. The loop task runs LVGL, every card, the API and the page's build; its stack is
// loop_task_stack_size in packages/hardware/esp-idf.yaml. A Guition 10.1 with a large layout had 40 bytes left after a
// layout's commit and overflowed when a page of live tiles opened (2026-11-16); on an S3 or a classic ESP32 the same
// overflow has no hardware guard and corrupts memory silently, so a low reading must show without Debug mode.
//
// What it knows: the floor and the words. What it does not: how deep anything runs (tools/stack_chains.py measures
// that from the build). The figure is uxTaskGetStackHighWaterMark's, in bytes on ESP-IDF (StackType_t is uint8_t).
#if __has_include("esphome/core/log.h")
#include "esphome/core/log.h"
#endif

namespace loop_stack {

// Under this many bytes left, at any time since boot, the health lines warn.
constexpr unsigned FLOOR = 2048;

constexpr bool low(unsigned left) { return left < FLOOR; }

#ifdef ESP_LOGW
// `what` leads the line ("layout applied, " or nothing): the words stay those the health line always had.
inline void report(const char *what, unsigned left) {
  if (low(left))
    ESP_LOGW("health", "%sloop_stack_min_free=%u, under %u: the loop task came close to the end of its stack", what, left, FLOOR);
  else
    ESP_LOGI("health", "%sloop_stack_min_free=%u", what, left);
}
#endif

}  // namespace loop_stack
