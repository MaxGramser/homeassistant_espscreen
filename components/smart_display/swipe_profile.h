#pragma once
// Page swipe profiling for diagnostic builds only: compile with -DSWIPE_PROFILE=1. Without the
// define every hook below is an empty inline and the release firmware is unchanged.
// One INFO line per page switch, tag `swipe_prof`, times in ms from the swipe (show_page):
//   fill   CPU in the content pass (the placement and every card of the page)
//   first  swipe -> first frame on the glass  done   swipe -> frame that completes the content
//   gap    longest main-loop gap (touch is polled once per loop) from the swipe until done
//   frames per LVGL refresh: +start:layout/render/flush ms, flush calls, pixels
//   slots  CPU per slot in the content passes
//   parts  CPU per step of those passes, summed over the slots (see Part)
#include "lvgl.h"
#ifdef SWIPE_PROFILE
#include "esp_timer.h"
#include "esphome/core/log.h"
#include <algorithm>
#include <array>
#include <cstdio>
#include <string>
#endif

namespace swipe_profile {
// Steps of a content pass; `Lap` adds the time since its previous lap.
enum Part { TEXT, BUSY, LAYOUT, CUSTOM, PANEL, GEOMETRY, PALETTE, PLACE, HEADER, PARTS };
inline const char *const PART_NAMES[PARTS] = {"text", "busy", "layout", "custom", "panel", "geometry", "palette", "place", "header"};
#ifdef SWIPE_PROFILE
struct Frame { int64_t start = 0, render_start = 0, flush_start = 0; uint32_t layout = 0, render = 0, flush = 0, flushes = 0, pixels = 0; };
struct Swipe {
  bool active = false, complete = false, done = false;
  int from = -1, to = -1;
  int64_t t0 = 0, first = 0, finished = 0, last_probe = 0;
  uint32_t fill = 0, max_gap = 0;
  std::array<uint32_t, 6> slots{};
  std::array<uint32_t, PARTS> parts{};
  std::array<Frame, 24> frames{};
  unsigned count = 0, dropped = 0;
};
inline Swipe swipe;
inline Frame frame;
inline bool hooked = false;
inline int64_t now_us() { return esp_timer_get_time(); }
inline double ms(int64_t us) { return us / 1000.0; }

inline void emit(const char *outcome) {
  auto &s = swipe;
  std::string frames;
  char b[96];
  for (unsigned i = 0; i < s.count; ++i) {
    auto &f = s.frames[i];
    snprintf(b, sizeof(b), "%s+%.0f:%.1f/%.1f/%.1f:%u:%u", i ? "|" : "", ms(f.start - s.t0), ms(f.layout), ms(f.render), ms(f.flush),
             (unsigned) f.flushes, (unsigned) f.pixels);
    frames += b;
  }
  std::string slots;
  for (unsigned i = 0; i < s.slots.size(); ++i) { snprintf(b, sizeof(b), "%s%.1f", i ? "," : "", ms(s.slots[i])); slots += b; }
  std::string parts;
  for (unsigned i = 0; i < PARTS; ++i) { snprintf(b, sizeof(b), "%s%s:%.1f", i ? "," : "", PART_NAMES[i], ms(s.parts[i])); parts += b; }
  ESP_LOGI("swipe_prof", "%s %d->%d fill=%.1f first=%.0f done=%.0f gap=%.0f frames=%s%s slots=%s parts=%s", outcome, s.from, s.to,
           ms(s.fill), s.first ? ms(s.first - s.t0) : -1.0, s.finished ? ms(s.finished - s.t0) : -1.0,
           ms(s.max_gap), frames.c_str(), s.dropped ? "+more" : "", slots.c_str(), parts.c_str());
  s.active = false;
}

inline void display_event(lv_event_t *e) {
  auto code = lv_event_get_code(e);
  int64_t t = now_us();
  if (code == LV_EVENT_REFR_START) { frame = Frame{}; frame.start = t; return; }
  if (code == LV_EVENT_RENDER_START) { frame.render_start = t; frame.layout = t - frame.start; return; }
  if (code == LV_EVENT_FLUSH_START) {
    frame.flush_start = t;
    if (auto *area = static_cast<lv_area_t *>(lv_event_get_param(e))) frame.pixels += lv_area_get_size(area);
    return;
  }
  if (code == LV_EVENT_FLUSH_FINISH) { frame.flush += t - frame.flush_start; frame.flushes++; return; }
  if (code == LV_EVENT_RENDER_READY) { frame.render = t - frame.render_start; return; }
  if (code != LV_EVENT_REFR_READY || !swipe.active || swipe.done || !frame.flushes) return;
  auto &s = swipe;
  if (s.count < s.frames.size()) s.frames[s.count++] = frame; else s.dropped++;
  if (!s.first) s.first = t;
  // The frame that follows the last content pass puts the finished page on the glass.
  if (s.complete) { s.finished = t; s.done = true; }
}

// Runs at the start of every lv_timer_handler call, so the gap between two runs is one whole
// ESPHome loop: whatever LVGL, the page code and every other component spent in between.
inline void probe(lv_timer_t *) {
  int64_t t = now_us();
  auto &s = swipe;
  if (s.active) {
    int64_t from = s.last_probe > s.t0 ? s.last_probe : s.t0;
    s.max_gap = std::max<uint32_t>(s.max_gap, t - from);
    if (s.done) emit("swipe");
    else if (t - s.t0 > 3000000) emit("timeout");
  }
  s.last_probe = t;
}

inline void hook() {
  if (hooked) return;
  auto *display = lv_display_get_default();
  if (!display) return;
  hooked = true;
  for (auto code : {LV_EVENT_REFR_START, LV_EVENT_RENDER_START, LV_EVENT_FLUSH_START, LV_EVENT_FLUSH_FINISH, LV_EVENT_RENDER_READY, LV_EVENT_REFR_READY})
    lv_display_add_event_cb(display, display_event, code, nullptr);
  lv_timer_create(probe, 1, nullptr);
  // Every layout pass walks all of these, and every invalidation climbs their parents.
  struct Count { static uint32_t of(lv_obj_t *obj) { uint32_t n = 1; for (uint32_t i = 0; i < lv_obj_get_child_count(obj); ++i) n += of(lv_obj_get_child(obj, i)); return n; } };
  ESP_LOGI("swipe_prof", "objects: screen %u, top layer %u", (unsigned) Count::of(lv_display_get_screen_active(display)),
           (unsigned) Count::of(lv_display_get_layer_top(display)));
}

// A page switch starts; a switch that is still filling is reported as superseded.
inline void begin(int from, int to) {
  hook();
  if (swipe.active) emit("superseded");
  swipe = Swipe{};
  swipe.active = true; swipe.from = from; swipe.to = to; swipe.t0 = now_us(); swipe.last_probe = swipe.t0;
}
struct Timer {
  uint32_t *into; int64_t start;
  explicit Timer(uint32_t *target) : into(swipe.active && !swipe.done ? target : nullptr), start(now_us()) {}
  ~Timer() { if (into) *into += now_us() - start; }
};
// One card's steps in ms, for render()'s slow-pass line (runtime_tiles.h), as the build without the profile keeps them:
// a profiling build failed to compile without this since that line came (2026-11-16).
inline uint32_t slot_steps[PARTS] = {};
struct FillTimer : Timer { FillTimer() : Timer(&swipe.fill) {} };
struct SlotTimer : Timer {
  explicit SlotTimer(size_t slot) : Timer(slot < swipe.slots.size() ? &swipe.slots[slot] : nullptr) { for (auto &step : slot_steps) step = 0; }
};
struct Lap {
  int64_t last = now_us();
  void operator()(Part part) {
    int64_t t = now_us();
    slot_steps[part] += static_cast<uint32_t>((t - last) / 1000);
    if (swipe.active && !swipe.done) swipe.parts[part] += t - last;
    last = t;
  }
};
// The page's content is complete once the pass that just ran reaches the screen.
inline void content_complete() { if (swipe.active) swipe.complete = true; }
#else
inline void begin(int, int) {}
struct FillTimer { FillTimer() {} };
// Without the profile, one card's paint is still split into its steps, in ms by LVGL's tick, for render()'s slow-pass
// line (runtime_tiles.h): kept in statics, so the loop task's stack carries nothing more (the structs stay empty).
inline uint32_t slot_steps[PARTS] = {};
inline uint32_t lap_at = 0;
struct SlotTimer { explicit SlotTimer(size_t) { for (auto &step : slot_steps) step = 0; } };
struct Lap {
  Lap() { lap_at = lv_tick_get(); }
  void operator()(Part part) { const uint32_t t = lv_tick_get(); slot_steps[part] += t - lap_at; lap_at = t; }
};
inline void content_complete() {}
#endif
}  // namespace swipe_profile
